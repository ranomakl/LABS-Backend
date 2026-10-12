# Regressionstests zum Review 12.10.2026 (docs/fehlerpfad_nachbesserung_12-10-2026.md), Luecke 2:
# Ein Verbindungsverlust (seriell: USB-Adapter weg) muss als Geraetefehler erkannt werden, das Geraet
# muss sich wiederverbinden, und ein laufendes Experiment muss darauf reagieren (uebrige Geraete
# abschalten, Messwerte sichern). Ohne Hardware, mit simulierter Uhr.
# Aufruf: .venv/bin/python -m twisted.trial backend.test.test_fehlerpfad_verbindungsverlust
import gc
import json
import os
from types import SimpleNamespace

from twisted.internet import task, defer, error, reactor
from twisted.internet.serialport import SerialPort
from twisted.protocols.basic import LineReceiver
from twisted.python import failure
from twisted.trial import unittest

from backend.commands import commandstate
from backend.commands.parser import ParserParameterFactory, REParser
from backend.commands.results import Result
from backend.conditions.conditionhandler import ConditionHandler
from backend.conditions import conditions as conditions_module
from backend.devices import devicestate
from backend.devices.base import SinglechannelBaseDevice, AbstractBaseDevice, BaseDeviceProtocol
from backend.experiments import experiment as experiment_module
from backend.experiments.experiment import Experiment
from backend.experiments import experimentstates

OFF = ":01w12=0,,"


class FakeProtocol:
    def __init__(self, device, clock, answers=True):
        self.device, self.clock, self.writes, self.answers = device, clock, [], answers

    def write_command(self, cmd):
        self.writes.append(cmd.parameters.commandstring)
        if self.answers:
            self.clock.callLater(0.05, self.device.receive, Result(":01ok"))


class FakeDevice(SinglechannelBaseDevice):
    replies_commands = True
    log_name = "FakeDevice"
    commands = {"SET_OUTPUT": ["w12", ParserParameterFactory(parserclass=REParser, pattern=r":01ok")],
                "READ": ["r30", ParserParameterFactory(parserclass=REParser, pattern=r":01ok")]}

    def cmd_string(self, p): return f":01{p.commandstring}=0,,"
    def initial_commands(self): self.write("SET_OUTPUT")      # wie joyit_dpm86: Ausgang aus beim Verbinden
    def final_commands(self): self.write("SET_OUTPUT")
    def handle_event(self, m): pass


class Recorder:
    def __init__(self): self.updates = []
    def update(self, observable, key, value, timestamp): self.updates.append((key, value))
    def states(self): return [v for k, v in self.updates if k == "state"]


def lost_connection(device, reason=None):
    """Spielt nach, was Twisted bei einem seriellen Geraet beim Abziehen des Adapters tut:
    BaseDeviceProtocol.connectionLost - und sonst nichts (keine Factory-Meldung)."""
    protocol = BaseDeviceProtocol()
    protocol.device = device
    device.protocol = protocol
    protocol.connectionLost(reason or failure.Failure(error.ConnectionDone()))


class VerbindungsverlustGeraetTest(unittest.TestCase):
    def setUp(self):
        self.clock = task.Clock()
        self.patch(commandstate.CommandState, "callLater", self.clock.callLater)
        self.patch(devicestate.DeviceState, "callLater", self.clock.callLater)
        self.patch(devicestate, "reactor", self.clock)
        self.patch(AbstractBaseDevice, "callLater", self.clock.callLater)       # Reconnect-Timer
        self.patch(conditions_module, "reactor", self.clock)                     # TimeCondition
        self.dev = FakeDevice("127.0.0.1:1")
        self.recorder = Recorder()
        self.dev.subscribe(self.recorder)
        self.connect_attempts = 0

    def tearDown(self):
        del self.dev
        gc.collect()
        self.flushLoggedErrors()

    def advance(self, seconds, step=0.1):
        for _ in range(int(round(seconds / step))):
            self.clock.advance(step)

    def fake_connect(self, fail_times):
        """Ersetzt device.connect(): scheitert `fail_times` mal (Geraetedatei fehlt), dann verbindet es."""
        def connect():
            self.connect_attempts += 1
            if self.connect_attempts <= fail_times:
                raise OSError("could not open port: No such file or directory")   # wie serial.SerialException
            return self.dev.connection_done(FakeProtocol(self.dev, self.clock))
        self.dev.connect = connect

    def test_verbindungsverlust_fuehrt_zu_error(self):
        """Vorher: nur protocol=None, Geraet blieb Ready/Busy, niemand erfuhr davon."""
        self.dev._state = devicestate.Ready(self.dev)
        lost_connection(self.dev)
        self.assertIs(self.dev.state, devicestate.Error)
        self.assertIn("Error", self.recorder.states())
        self.assertIsNone(self.dev.protocol)
        errorcodes = [v for k, v in self.recorder.updates if k == "errorcode"]
        self.assertEqual(len(errorcodes), 1)
        self.assertIsInstance(errorcodes[0], str, "errorcode muss ein String sein (values.json wird mit json.dump geschrieben)")

    def test_verbindungsverlust_im_busy_zustand(self):
        """Das ist der Laborfall: Netzteil ist Busy (Elektrolysezeit laeuft), Adapter faellt aus."""
        from backend.conditions.conditions import TimeCondition
        self.dev._state = devicestate.Ready(self.dev)
        self.dev.protocol = FakeProtocol(self.dev, self.clock)
        self.dev.busy(TimeCondition("Elektrolyse", 600))
        self.assertIs(self.dev.state, devicestate.Busy)
        lost_connection(self.dev)
        self.assertIs(self.dev.state, devicestate.Error)

    def test_wiederverbindung_und_sicherer_zustand(self):
        """Nach dem Verlust wird alle RECONNECT_INTERVAL s neu verbunden; nach Erfolg laufen die
        initial_commands (= Ausgang aus) und das Geraet ist wieder Ready."""
        self.dev._state = devicestate.Ready(self.dev)
        self.fake_connect(fail_times=2)
        lost_connection(self.dev)
        self.advance(0.5)
        self.assertEqual(self.connect_attempts, 0)
        self.advance(2.0)
        self.assertEqual(self.connect_attempts, 1)
        self.assertIs(self.dev.state, devicestate.Error)
        self.advance(2.0)
        self.assertEqual(self.connect_attempts, 2)
        self.advance(2.0)
        self.assertEqual(self.connect_attempts, 3)
        self.advance(1.0)
        self.assertIs(self.dev.state, devicestate.Ready)
        self.assertEqual(self.dev.protocol.writes, [OFF], "initial_commands (Ausgang aus) nach Wiederverbindung fehlen")
        self.assertIn("Initializing", self.recorder.states())
        self.advance(10)
        self.assertEqual(self.connect_attempts, 3, "nach Erfolg darf nicht weiter verbunden werden")

    def test_stop_waehrend_verbindung_weg_sendet_aus_nach_rueckkehr(self):
        """Experiment-Abbruch ruft stop() auf, solange keine Verbindung da ist: darf nicht werfen; nach der
        Wiederverbindung schaltet initial_commands aus, und die stop()-Wiederholung bestaetigt Stopped."""
        self.dev._state = devicestate.Ready(self.dev)
        self.fake_connect(fail_times=3)
        lost_connection(self.dev)
        self.dev.stop().addErrback(lambda f: None)     # darf nicht werfen
        self.advance(9)                                 # 3 Fehlversuche a 2 s, 4. Versuch verbindet
        self.assertIn(OFF, self.dev.protocol.writes)
        self.advance(10)
        self.assertIn(self.dev.state, (devicestate.Ready, devicestate.Stopped))

    def test_absichtliches_shutdown_kein_reconnect(self):
        self.dev._state = devicestate.Shutdown(self.dev)
        self.fake_connect(fail_times=0)
        lost_connection(self.dev)
        self.advance(10)
        self.assertEqual(self.connect_attempts, 0)
        self.assertIs(self.dev.state, devicestate.Shutdown)

    def test_doppelmeldung_tcp_idempotent(self):
        """Bei TCP melden Protocol UND Factory den Verlust - es darf nur EIN Reconnect-Zyklus laufen."""
        self.dev._state = devicestate.Ready(self.dev)
        self.fake_connect(fail_times=99)
        lost_connection(self.dev)
        self.dev.connection_lost(failure.Failure(error.ConnectionLost()))
        self.advance(2.1)
        self.assertEqual(self.connect_attempts, 1)


class EchterSerialPortTest(unittest.TestCase):
    """Echter Twisted-SerialPort an einem Pseudo-Terminal: Schliessen der Gegenseite (= Adapter abgezogen)
    muss BaseDeviceProtocol.connectionLost und damit device.connection_lost ausloesen. Laeuft mit dem
    echten Reactor, Dauer ca. 1 s."""
    @defer.inlineCallbacks
    def test_pty_schliessen_fuehrt_zu_error(self):
        if not hasattr(os, "openpty"):
            raise unittest.SkipTest("kein PTY auf dieser Plattform")
        master, slave = os.openpty()
        path = os.ttyname(slave)
        dev = FakeDevice(path)
        dev.RECONNECT_INTERVAL = 3600                      # im Test nicht wiederverbinden
        dev._state = devicestate.Ready(dev)
        protocol = dev.protocol_factory.buildProtocol(path)
        protocol.factory = dev.protocol_factory
        dev.protocol_factory.d_protocol.addCallback(lambda p: setattr(dev, "protocol", p))
        port = SerialPort(protocol, path, reactor, baudrate=9600)
        self.assertIs(dev.protocol, protocol)
        os.close(master)                                   # "Kabel ziehen"
        yield task.deferLater(reactor, 0.5, lambda: None)
        self.assertIs(dev.state, devicestate.Error)
        self.assertIsNone(dev.protocol)
        self.assertTrue(dev._reconnect_call is not None and dev._reconnect_call.active(), "kein Reconnect geplant")
        dev._reconnect_call.cancel()                       # Aufraeumen: Test-Reactor muss sauber bleiben
        os.close(slave)
        self.flushLoggedErrors()


class VerbindungsverlustExperimentTest(unittest.TestCase):
    """Ganzer Pfad: Netzteil verliert waehrend des Laufs die Verbindung -> Experiment Failed -> die Pumpe
    wird gestoppt, values.json/lauf.json werden geschrieben, der Setup-Deferred meldet den Fehler."""
    def setUp(self):
        self.clock = task.Clock()
        self.patch(commandstate.CommandState, "callLater", self.clock.callLater)
        self.patch(devicestate.DeviceState, "callLater", self.clock.callLater)
        self.patch(devicestate, "reactor", self.clock)
        self.patch(AbstractBaseDevice, "callLater", self.clock.callLater)
        self.patch(conditions_module, "reactor", self.clock)
        self.patch(Experiment, "write_report", lambda self: None)     # kein Unterprozess im Test
        self.psu = FakeDevice("127.0.0.1:1")
        self.pump = FakeDevice("127.0.0.1:2")
        for dev in (self.psu, self.pump):
            dev._state = devicestate.Ready(dev)
            dev.protocol = FakeProtocol(dev, self.clock)
            dev.connect = lambda: defer.Deferred()        # kein Reconnect im Test
        setup = SimpleNamespace(conditionhandler=ConditionHandler(), config={"log_level": "warn"})
        factory = SimpleNamespace(experiment_observable_details=[], setup=setup, experiment_name="test")
        self.experiment = Experiment(factory, [], "verbindungsverlust", {"psu": self.psu, "pump": self.pump},
                                     {}, [], "Test-Experiment", [])
        self.setup_errors = []
        self.experiment.deferred_success.addErrback(lambda f: self.setup_errors.append(f.value))

    def tearDown(self):
        del self.psu, self.pump, self.experiment
        gc.collect()
        self.flushLoggedErrors()

    def advance(self, seconds, step=0.1):
        for _ in range(int(round(seconds / step))):
            self.clock.advance(step)

    def test_experiment_reagiert_auf_verbindungsverlust(self):
        self.experiment.state = experimentstates.Running
        from backend.conditions.conditions import TimeCondition
        self.psu.busy(TimeCondition("Elektrolyse", 600))
        self.pump.busy(TimeCondition("Pumpe", 600))
        lost_connection(self.psu)
        self.assertIs(self.experiment.state, experimentstates.Failed)
        self.advance(1)
        self.assertIn(OFF, self.pump.protocol.writes, "Pumpe wurde nach Ausfall des Netzteils nicht gestoppt")
        self.assertEqual(len(self.setup_errors), 1, "Setup wurde nicht ueber das Scheitern informiert")
        values = self.experiment.log_path / "values.json"
        lauf = self.experiment.log_path / "lauf.json"
        self.assertTrue(values.exists())
        self.assertEqual(json.loads(lauf.read_text())["final_state"], "Failed")
        self.assertIs(self.psu.state, devicestate.Error)
        # Netzteil-stop() scheiterte ohne Verbindung -> Wiederholung ist geplant
        self.assertIsNotNone(self.psu.stateobject._retry_call)

    def test_experiment_reagiert_auf_shutdown(self):
        """Auch der Zustand Shutdown eines Geraets beendet das Experiment (vorher: lief weiter)."""
        self.experiment.state = experimentstates.Running
        self.psu.state = devicestate.Shutdown
        self.assertIs(self.experiment.state, experimentstates.Failed)
        self.advance(1)
        self.assertIn(OFF, self.pump.protocol.writes)
