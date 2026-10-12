# Regressionstests zum Vorfall 08.10.2026 (Netzteil blieb an) und zum Review 12.10.2026
# (docs/fehlerpfad_nachbesserung_12-10-2026.md), Luecke 1: Abschaltbefehle laufen als CommandSeries;
# antwortet das Geraet nicht, muss die Serie scheitern (nicht still haengen) und das Abschalten muss
# wiederholt werden, bis das Geraet bestaetigt. Ohne Hardware, mit simulierter Uhr (task.Clock).
# Aufruf: .venv/bin/python -m twisted.trial backend.test.test_fehlerpfad_abschalten
import gc

from twisted.internet import task
from twisted.trial import unittest

from backend.commands import commandstate
from backend.commands.helpers_exceptions import CommandSeriesError
from backend.commands.parser import ParserParameterFactory, REParser
from backend.commands.results import Result
from backend.devices import devicestate
from backend.devices.base import SinglechannelBaseDevice
from backend.devices.helpers_exceptions import DeviceErrorError

OFF = ":01w12=0,,"


class FakeProtocol:
    """Zeichnet alles auf, was das Geraet schreibt. Antwortet nur, wenn `answers` True ist (50 ms spaeter)."""
    def __init__(self, device, clock):
        self.device, self.clock, self.writes, self.answers = device, clock, [], False

    def write_command(self, cmd):
        self.writes.append(cmd.parameters.commandstring)
        if self.answers:
            self.clock.callLater(0.05, self.device.receive, Result(":01ok"))


class FakePSU(SinglechannelBaseDevice):
    """Minimales Netzteil wie joyit_dpm86: final_commands = Ausgang aus, erwartet ':01ok'."""
    replies_commands = True
    log_name = "FakePSU"
    commands = {"SET_OUTPUT": ["w12", ParserParameterFactory(parserclass=REParser, pattern=r":01ok")]}

    def cmd_string(self, p): return f":01{p.commandstring}=0,,"
    def initial_commands(self): self.write("SET_OUTPUT")
    def final_commands(self): self.write("SET_OUTPUT")
    def handle_event(self, m): pass


class Recorder:
    def __init__(self): self.states = []
    def update(self, observable, key, value, timestamp):
        if key == "state":
            self.states.append(value)


class AbschaltenTest(unittest.TestCase):
    def setUp(self):
        self.clock = task.Clock()
        self.patch(commandstate.CommandState, "callLater", self.clock.callLater)   # Timeout-Timer
        self.patch(devicestate.DeviceState, "callLater", self.clock.callLater)     # stop()-Wiederholung
        self.patch(devicestate, "reactor", self.clock)                              # deferLater in handle_success
        self.dev = FakePSU("127.0.0.1:1")
        self.proto = self.dev.protocol = FakeProtocol(self.dev, self.clock)
        self.recorder = Recorder()
        self.dev.subscribe(self.recorder)

    def tearDown(self):
        # Innere Befehle einer gescheiterten Serie errbacken ohne Abnehmer ("Unhandled error in Deferred",
        # CommandRetryError) - das ist bekannt und beabsichtigt (die Serie meldet den Fehler), darf den
        # naechsten Test aber nicht als Fehler treffen.
        del self.dev, self.proto
        gc.collect()
        self.flushLoggedErrors()

    def advance(self, seconds, step=0.1):
        for _ in range(int(round(seconds / step))):
            self.clock.advance(step)

    def set_state(self, stateclass):
        self.dev._state = stateclass(self.dev)

    def test_timeout_innerhalb_serie_erreicht_serie(self):
        """Geraet in Ready antwortet nie: die Serie muss SCHEITERN und das Geraet nach Error gehen.
        Vorher: innerer Befehl Fail, Serie fuer immer NotSent, Geraet fuer immer NotReady."""
        self.set_state(devicestate.Ready)
        errors = []
        self.dev.stop().addErrback(lambda f: errors.append(f.value))
        self.advance(45)   # 4 Versuche x 2,5 s je Serien-Durchlauf, 4 Durchlaeufe = 40 s
        self.assertEqual(len(errors), 1, "Serie hat ihr Scheitern nicht gemeldet")
        self.assertIsInstance(errors[0], CommandSeriesError)
        self.assertIs(self.dev.state, devicestate.Error)
        self.assertIn("Error", self.recorder.states)
        self.assertGreaterEqual(self.proto.writes.count(OFF), 16)

    def test_abschalten_wird_wiederholt_bis_bestaetigt(self):
        """Geraet im Error-Zustand antwortet lange nicht: AUS wird immer wieder gesendet (vorher: 4x in
        10 s, dann nie wieder). Sobald es antwortet -> Stopped, danach keine weiteren Sendungen."""
        self.set_state(devicestate.Error)
        self.dev.stop().addErrback(lambda f: None)
        self.advance(50)
        writes_after_50 = self.proto.writes.count(OFF)
        self.advance(100)
        writes_after_150 = self.proto.writes.count(OFF)
        self.assertGreater(writes_after_50, 16, "erste Serie (16 Sendungen) wurde nicht wiederholt")
        self.assertGreater(writes_after_150, writes_after_50, "Wiederholung ist eingeschlafen")
        self.assertIs(self.dev.state, devicestate.Error)
        self.proto.answers = True                 # Geraet ist wieder da
        self.advance(10)
        self.assertIs(self.dev.state, devicestate.Stopped)
        writes_at_stop = self.proto.writes.count(OFF)
        self.advance(60)
        self.assertEqual(self.proto.writes.count(OFF), writes_at_stop, "nach Stopped darf nichts mehr gesendet werden")

    def test_wiederholung_auch_wenn_fehler_ausserhalb_error_zustand_begann(self):
        """Geraet war gesund (Ready), erst der Abschaltbefehl selbst bleibt unbeantwortet: auch dann muss die
        Wiederholung anlaufen (der Fehler wird vom NotReady-Zustand behandelt, nicht von Error)."""
        self.set_state(devicestate.Ready)
        self.dev.stop().addErrback(lambda f: None)
        self.advance(45)
        self.assertIs(self.dev.state, devicestate.Error)
        before = self.proto.writes.count(OFF)
        self.advance(10)
        self.assertGreater(self.proto.writes.count(OFF), before, "keine Wiederholung nach Error")
        self.proto.answers = True
        self.advance(10)
        self.assertIs(self.dev.state, devicestate.Stopped)

    def test_ohne_verbindung_sofort_fehler_dann_wiederholung(self):
        """Keine Verbindung (protocol None): stop() darf nicht abstuerzen, der Befehl scheitert sofort und
        sichtbar, und sobald eine Verbindung da ist, wird AUS gesendet."""
        self.set_state(devicestate.Error)
        self.dev.protocol = None
        errors = []
        self.dev.stop().addErrback(lambda f: errors.append(f.value))
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], DeviceErrorError)
        self.assertEqual(self.proto.writes, [])
        self.dev.protocol = self.proto
        self.proto.answers = True
        self.advance(6)                           # RETRY_INTERVAL = 5 s
        self.assertEqual(self.proto.writes.count(OFF), 1)
        self.assertIs(self.dev.state, devicestate.Stopped)

    def test_dringende_befehle_nacheinander_nicht_gleichzeitig(self):
        """Zwei stop() kurz hintereinander im Error-Zustand (z.B. Experiment-Abbruch und Bediener-Stop):
        nie zwei Befehle gleichzeitig auf der Leitung."""
        self.set_state(devicestate.Error)
        self.proto.answers = True                 # Antwort kommt 50 ms nach jedem Schreiben
        self.dev.stop().addErrback(lambda f: None)
        self.dev.stop().addErrback(lambda f: None)
        self.assertEqual(self.proto.writes.count(OFF), 1, "zweiter Befehl ging raus, waehrend der erste lief")
        self.advance(1)
        self.assertEqual(self.proto.writes.count(OFF), 2)
        self.assertIs(self.dev.state, devicestate.Stopped)

    def test_einzelbefehl_timeout_unveraendert(self):
        """Kontrolle: ein einzelner Befehl (keine Serie) verhaelt sich wie bisher - Retry, dann Fail -> Error."""
        self.set_state(devicestate.Ready)
        cmd = self.dev.write("SET_OUTPUT")
        cmd.deferred_result.addErrback(lambda f: None)
        self.advance(12)
        self.assertEqual(self.proto.writes.count(OFF), 4)
        self.assertIs(self.dev.state, devicestate.Error)
