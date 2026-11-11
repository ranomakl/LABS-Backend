# -*- test-case-name: backend.test.test_valve_dosing -*-
"""Zugabe ueber das Auswahlventil (backend/drivers/valve_dosing.py), Stand 06.11.2026 - ohne Hardware.
Pumpe und Ventil sind Attrappen, die Zeit laeuft ueber eine task.Clock. Geprueft werden die Rechnung
(Flussrate, Schrittliste, Summen), die Reihenfolge Ventil/Pumpe, die Laufzeiten und alle Fehlerpfade.
Lauf am PC: .venv/Scripts/python -c "import sys; sys.argv=['trial','backend.test.test_valve_dosing'];
            from twisted.scripts.trial import run; run()"
"""
from twisted.internet import defer, task
from twisted.trial import unittest

from backend.devices import devicestate
from backend.drivers import valve_dosing as vd
from backend.drivers.longer_bt100_1f import Device, build_wire_frame

CONFIG = {"valve": "valve1", "water_port": 1, "dead_volume_ml": 0.5, "flush_factor": 1.5,
          "min_rate_ml_min": 0.018, "max_rate_ml_min": 5.0, "min_dose_seconds": 10}


def settings(**changes):
    return vd.DosingSettings({**CONFIG, **changes})


class SettingsTests(unittest.TestCase):
    def test_complete_config(self):
        s = settings()
        self.assertEqual((s.valve, s.water_port), ("valve1", 1))
        self.assertAlmostEqual(s.flush_volume_ml, 0.75)
        self.assertEqual((s.valve_timeout_s, s.settle_s), (20.0, 0.5))

    def test_every_required_key_is_required(self):
        for key in vd.REQUIRED_KEYS:
            config = dict(CONFIG)
            del config[key]
            error = self.assertRaises(ValueError, vd.DosingSettings, config)
            self.assertIn(key, str(error))

    def test_unknown_key_is_rejected(self):
        self.assertRaises(ValueError, settings, dead_volume=0.5)

    def test_nonsense_values_are_rejected(self):
        for changes in ({"dead_volume_ml": 0}, {"dead_volume_ml": -1}, {"flush_factor": 0.9}, {"water_port": 0},
                        {"min_rate_ml_min": 0}, {"min_rate_ml_min": 6}, {"min_dose_seconds": 0},
                        {"valve_timeout_s": 0}, {"settle_s": -1}):
            self.assertRaises(ValueError, settings, **changes)

    def test_not_a_mapping(self):
        self.assertRaises(ValueError, vd.DosingSettings, "valve1")


class RateTests(unittest.TestCase):
    def test_small_volumes_run_at_least_min_dose_seconds(self):
        self.assertAlmostEqual(vd.choose_rate(0.05, settings()), 0.3)     # 50 uL in 10 s
        self.assertAlmostEqual(vd.choose_rate(0.2, settings()), 1.2)      # 200 uL in 10 s

    def test_large_volumes_are_capped_at_max_rate(self):
        self.assertEqual(vd.choose_rate(50, settings()), 5.0)

    def test_tiny_volumes_use_min_rate(self):
        self.assertEqual(vd.choose_rate(0.001, settings()), 0.018)

    def test_given_rate_is_used_and_checked(self):
        self.assertEqual(vd.choose_rate(0.2, settings(), rate="2.5"), 2.5)
        self.assertRaises(ValueError, vd.choose_rate, 0.2, settings(), 9)
        self.assertRaises(ValueError, vd.choose_rate, 0.2, settings(), 0.001)

    def test_empty_or_zero_rate_means_automatic(self):
        for rate in (None, "", 0, "0", 0.0, " "):
            self.assertAlmostEqual(vd.choose_rate(0.2, settings(), rate), 1.2)

    def test_volume_must_be_positive(self):
        self.assertRaises(ValueError, vd.choose_rate, 0, settings())
        self.assertRaises(ValueError, vd.choose_rate, -0.1, settings())


class PlanTests(unittest.TestCase):
    def test_reagent_addition_is_valve_dose_valve_flush(self):
        steps = vd.plan_addition(3, 0.2, settings())
        self.assertEqual([repr(s) for s in steps],
                         ["Ventil->Port 3", "reagent 200 uL @ 1.2 mL/min", "Ventil->Port 1",
                          "water 750 uL @ 4.5 mL/min"])
        totals = vd.plan_totals(steps)
        self.assertAlmostEqual(totals["reagent_ml"], 0.2)
        self.assertAlmostEqual(totals["water_ml"], 0.75)
        self.assertAlmostEqual(totals["total_ml"], 0.95)
        self.assertAlmostEqual(totals["duration_s"], 20.0)

    def test_water_port_has_no_flush_step(self):
        steps = vd.plan_addition("1.0", 2.0, settings())
        self.assertEqual([repr(s) for s in steps], ["Ventil->Port 1", "water 2000 uL @ 5 mL/min"])

    def test_repeats_with_pause(self):
        steps = vd.plan_addition(1, 0.05, settings(), repeats=3, pause_s=5)
        self.assertEqual([s.kind for s in steps], ["valve", "pump", "pause", "pump", "pause", "pump"])
        self.assertAlmostEqual(vd.plan_totals(steps)["water_ml"], 0.15)

    def test_repeated_reagent_addition_flushes_every_time(self):
        steps = vd.plan_addition(2, 0.05, settings(), repeats=2)
        self.assertEqual([s.kind for s in steps], ["valve", "pump", "valve", "pump"] * 2)
        self.assertEqual([s.port for s in steps if s.kind == "valve"], [2, 1, 2, 1])

    def test_invalid_ports(self):
        self.assertRaises(ValueError, vd.plan_addition, 0, 0.2, settings())
        self.assertRaises(ValueError, vd.plan_addition, 17, 0.2, settings(), positions=16)
        self.assertRaises(ValueError, vd.plan_addition, 2.5, 0.2, settings())
        self.assertRaises(ValueError, vd.plan_addition, "abc", 0.2, settings())
        self.assertEqual(len(vd.plan_addition(16, 0.2, settings(), positions=16)), 4)

    def test_invalid_repeats_and_pause(self):
        self.assertRaises(ValueError, vd.plan_addition, 2, 0.2, settings(), repeats=0)
        self.assertRaises(ValueError, vd.plan_addition, 2, 0.2, settings(), repeats=1.5)
        self.assertRaises(ValueError, vd.plan_addition, 2, 0.2, settings(), pause_s=-1)


# ---------------------------------------------------------------------------------------------------
# Ablauf mit Attrappen
# ---------------------------------------------------------------------------------------------------

class _Command:
    def __init__(self, time=None):
        self.time = time                      # Sendezeitpunkt, wie Command.time
        self.deferred_execution = defer.Deferred()
        self.deferred_result = defer.Deferred()


class _Reply:
    def __init__(self, **parameters):
        self.parameters = parameters


class _Log:
    def __init__(self):
        self.errors, self.warnings = [], []

    def info(self, *args, **kwargs):
        pass

    def warn(self, message, **kwargs):
        self.warnings.append(message.format(**kwargs))

    def error(self, message, **kwargs):
        self.errors.append(message.format(**kwargs))


class _Valve:
    commands = {"GET_POS": None}
    positions = 16
    state = devicestate.Ready

    def __init__(self, events):
        self.events = events
        self.position = 1
        self.stuck = False        # nimmt den Befehl an, bewegt sich aber nicht
        self.silent = False       # bestaetigt den Stellbefehl nie

    def set_position(self, port):
        command = _Command()
        self.events.append(("valve", port))
        if not self.stuck:
            self.position = int(port)
        if not self.silent:
            command.deferred_result.callback(None)
        return command

    def query(self, name):
        command = _Command()
        command.deferred_result.callback(_Reply(position=str(self.position)))
        return command


class _PhMeter:
    """Attrappe des pH-Geraets: liefert get_latest_update wie BaseObservable. Jede Base-Dose hebt den pH um
    `per_ml_up` je mL, jede Saeure-Dose senkt ihn; `dead` = reagiert nicht (leerer Vorrat)."""

    def __init__(self, clock, ph=7.0, status="Good"):
        self.clock, self.ph, self.status = clock, ph, status
        self.age = 0.0            # so alt ist der gelieferte Wert
        self.empty = False        # noch nie gemessen
        self.dead = False         # reagiert nicht auf Zugaben (Vorrat leer)

    def get_latest_update(self, name):
        if self.empty:
            raise IndexError
        if name.endswith("_status"):
            return (self.clock.seconds() - self.age, self.status)
        return (self.clock.seconds() - self.age, self.ph)


class _Base:
    def stop(self):
        self.events.append(("device stop",))
        return "stopped"


class _Pump(vd.ValveDosingMixIn, _Base):
    def __init__(self, dosing=CONFIG, valve=True, ph_meter=None):
        self.clock = task.Clock()
        self.callLater = self.clock.callLater
        self._dosing_now = self.clock.seconds
        self.events = []
        self.updates = []
        self.log = _Log()
        self.state = devicestate.Ready
        self.waits = []
        self.start_delay = 0.0     # so spaet bestaetigt die Pumpe den Start
        self._init_dosing(dosing)
        self.valve = _Valve(self.events)
        self.ph_meter = ph_meter
        devices = {"valve1": self.valve} if valve else {}
        if ph_meter is not None:
            devices["liquiline"] = ph_meter
        self.link_devices(devices)
        # pH-Aenderung je mL nach Port, wirkt beim Pumpenstopp. Wie im Labor (11.11.2026): 2 Saeure schwach,
        # 3 Saeure stark, 4 Base schwach, 5 Base stark. stark 20/mL (200 uL = 4), schwach 4/mL (200 uL = 0,8).
        self.ph_effect = {2: -4.0, 3: -20.0, 4: 4.0, 5: 20.0}

    def busy(self, condition):
        self.state = devicestate.Busy
        command = _Command()
        self.waits.append((condition, command))
        command.deferred_execution.callback(None)
        return command

    def update_observables(self, values, timestamp=None):
        self.updates.append(dict(values))

    def _dosing_pump_start(self, rate):
        command = _Command(time=self.clock.seconds())
        self.events.append(("start", round(self.clock.seconds(), 3), round(rate, 6)))
        if self.start_delay:
            self.clock.callLater(self.start_delay, command.deferred_result.callback, None)
        else:
            command.deferred_result.callback(None)
        return command

    def _dosing_pump_stop(self):
        command = _Command(time=self.clock.seconds())
        self.events.append(("stop", round(self.clock.seconds(), 3)))
        # pH-Attrappe: Reagenz wirkt, sobald es gefoerdert ist. Wirkung je mL nach Port (ph_effect), andere Ports 0.
        run = self._dosing
        if self.ph_meter is not None and run is not None and run.index and not self.ph_meter.dead:
            step = run.steps[run.index - 1]
            if step.kind == "pump" and step.role == "reagent":
                self.ph_meter.ph += self.ph_effect.get(self.valve.position, 0.0) * step.volume_ml
        command.deferred_result.callback(None)
        return command

    # Hilfen fuer die Tests
    def last(self, key):
        return [u[key] for u in self.updates if key in u][-1]

    def run_all(self, seconds=200, step=0.25):
        self.clock.advance(0)      # der Start ist ein callLater(0)
        for _ in range(int(seconds / step)):
            self.clock.advance(step)


class RunTests(unittest.TestCase):
    def test_reagent_addition_runs_in_order_with_exact_times(self):
        pump = _Pump()
        pump.add_from_port(3, 0.2)
        self.assertEqual(pump.state, devicestate.Busy)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "running")
        pump.run_all(60)
        # Ventil 3 -> 0,5 s Ruhe -> 10 s Dosis -> Ventil 1 -> 0,5 s -> 10 s Spuelen (0,75 mL bei 4,5 mL/min)
        self.assertEqual(pump.events, [("valve", 3), ("start", 0.5, 1.2), ("stop", 10.5),
                                       ("valve", 1), ("start", 11.0, 4.5), ("stop", 21.0)])
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "finished")
        self.assertAlmostEqual(pump.last("dosed_ml"), 0.2)
        self.assertAlmostEqual(pump.last("flushed_ml"), 0.75)
        self.assertAlmostEqual(pump.last("delivered_ml"), 0.95)
        self.assertEqual(pump.last("dosing_port"), 1)
        # Fluss im Monitoring: 0 -> 1,2 (Dosis) -> 0 -> 4,5 (Spuelen) -> 0
        self.assertEqual([x["dosing_flow_ml_min"] for x in pump.updates if "dosing_flow_ml_min" in x],
                         [0.0, 1.2, 0.0, 4.5, 0.0])
        self.assertEqual(pump.log.errors, [])
        self.assertFalse(pump._dosing.open)
        self.assertIsNone(pump._dosing.reagent_port)

    def test_finished_is_the_condition_the_pump_waits_for(self):
        pump = _Pump()
        pump.add_from_port(3, 0.2)
        condition, _ = pump.waits[0]
        self.assertEqual((condition.observable_name, condition.value), (vd.DOSING_OBSERVABLE, "finished"))
        self.assertIs(condition.observable_objects[0], pump)

    def test_water_only(self):
        pump = _Pump()
        pump.pump_water(0.05, repeats=3, pause_s=5)
        pump.run_all(60)
        self.assertEqual(pump.events, [("valve", 1), ("start", 0.5, 0.3), ("stop", 10.5),
                                       ("start", 15.5, 0.3), ("stop", 25.5),
                                       ("start", 30.5, 0.3), ("stop", 40.5)])
        self.assertAlmostEqual(pump.last("flushed_ml"), 0.15)
        self.assertAlmostEqual(pump.last("dosed_ml"), 0.0)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "finished")

    def test_valve_never_switches_while_the_pump_runs(self):
        pump = _Pump()
        pump.add_from_port(2, 0.05, repeats=3)
        pump.run_all(120)
        running = False
        for event in pump.events:
            if event[0] == "start":
                self.assertFalse(running)
                running = True
            elif event[0] == "stop":
                running = False
            else:
                self.assertFalse(running, pump.events)
        self.assertEqual(len([e for e in pump.events if e[0] == "valve"]), 6)

    def test_late_start_confirmation_shortens_the_wait(self):
        """Die Zeit zaehlt ab dem Senden des Startbefehls (Command.time), nicht ab der Bestaetigung."""
        pump = _Pump()
        pump.start_delay = 2.0
        pump.pump_water(0.05)
        pump.run_all(30)
        self.assertEqual(pump.events, [("valve", 1), ("start", 0.5, 0.3), ("stop", 10.5)])
        self.assertEqual(len(pump.log.warnings), 1)       # > 1 s: Volumen als ungenau gemeldet

    def test_given_rate(self):
        pump = _Pump()
        pump.pump_water(1.0, rate=2.0)
        pump.run_all(60)
        self.assertEqual(pump.events, [("valve", 1), ("start", 0.5, 2.0), ("stop", 30.5)])


class FailureTests(unittest.TestCase):
    def assert_failed(self, pump, text):
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "failed")
        self.assertEqual(pump.state, devicestate.Error)
        self.assertIn(text, pump.last("dosing_step"))
        self.assertTrue(pump.log.errors)

    def test_invalid_port_fails_cleanly_without_moving_anything(self):
        pump = _Pump()
        pump.add_from_port(99, 0.2)
        self.assertEqual(pump.state, devicestate.Busy)        # Experiment laeuft an, kein Ausnahmefehler
        pump.run_all(5)
        self.assert_failed(pump, "Port 99")
        self.assertEqual(pump.events, [])

    def test_no_dosing_section(self):
        pump = _Pump(dosing=None)
        pump.add_from_port(2, 0.2)
        pump.run_all(5)
        self.assert_failed(pump, "dosing")
        self.assertEqual(pump.events, [])

    def test_valve_not_connected(self):
        pump = _Pump(valve=False)
        self.assertEqual(len(pump.log.errors), 1)             # schon beim Verbinden gemeldet
        pump.add_from_port(2, 0.2)
        pump.run_all(5)
        self.assert_failed(pump, "nicht verbunden")

    def test_valve_reports_wrong_position(self):
        pump = _Pump()
        pump.valve.stuck = True
        pump.add_from_port(3, 0.2)
        pump.run_all(60)
        self.assert_failed(pump, "Position 1 statt 3")
        self.assertEqual(pump.events, [("valve", 3)])         # Pumpe ist nie gestartet

    def test_valve_never_confirms(self):
        pump = _Pump()
        pump.valve.silent = True
        pump.add_from_port(3, 0.2)
        pump.run_all(30)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "running")
        pump.run_all(10)                                      # 20 s + 15 s Reserve
        self.assert_failed(pump, "nicht innerhalb")
        self.assertEqual(pump.events, [("valve", 3)])

    def test_valve_in_stopped_state(self):
        pump = _Pump()
        pump.valve.state = devicestate.Stopped
        pump.add_from_port(3, 0.2)
        pump.run_all(5)
        self.assert_failed(pump, "Stopped")
        self.assertEqual(pump.events, [])

    def test_second_request_while_one_is_running(self):
        pump = _Pump()
        pump.add_from_port(3, 0.2)
        pump.run_all(2)
        pump.add_from_port(4, 0.2)
        pump.run_all(1)
        self.assert_failed(pump, "es laeuft noch")

    def test_failure_while_pumping_reagent_goes_to_error_and_warns(self):
        """Kein eigener Stoppbefehl: der Error-Zustand laesst das Experiment scheitern, dessen stop()
        schaltet die Pumpe ueber final_commands ab (ein zweiter Stopp davor kollidiert auf der Leitung)."""
        pump = _Pump()
        pump.add_from_port(3, 0.2)
        pump.run_all(5)                                       # mitten in der Dosis
        pump._dosing_fail(pump._dosing, RuntimeError("Testfehler"))
        self.assertEqual(pump.events, [("valve", 3), ("start", 0.5, 1.2)])
        self.assert_failed(pump, "Testfehler")
        self.assertTrue(any("Reagenz von Port 3" in e for e in pump.log.errors), pump.log.errors)
        self.assertTrue(any("Abschaltpfad" in w for w in pump.log.warnings), pump.log.warnings)
        pump.run_all(60)
        self.assertEqual(len(pump.events), 2)                 # danach passiert nichts mehr


class StopTests(unittest.TestCase):
    def test_stop_during_the_dose(self):
        pump = _Pump()
        pump.add_from_port(3, 0.2)
        pump.run_all(5)
        self.assertEqual(pump.stop(), "stopped")
        # genau EIN Stopp: der Abschaltpfad des Geraets (final_commands), kein zweiter vom Baustein
        self.assertEqual(pump.events, [("valve", 3), ("start", 0.5, 1.2), ("device stop",)])
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "cancelled")
        self.assertEqual(pump.last("dosing_flow_ml_min"), 0.0)
        self.assertTrue(any("Reagenz von Port 3" in e for e in pump.log.errors))
        pump.run_all(60)
        self.assertEqual(len(pump.events), 3)
        self.assertNotEqual(pump.state, devicestate.Error)

    def test_stop_during_the_flush_still_warns_about_reagent(self):
        pump = _Pump()
        pump.add_from_port(3, 0.2)
        pump.run_all(15)                                      # Spuelen laeuft seit 4 s
        pump.stop()
        self.assertTrue(any("Reagenz von Port 3" in e for e in pump.log.errors))

    def test_stop_after_regular_end_is_silent(self):
        pump = _Pump()
        pump.add_from_port(3, 0.2)
        pump.run_all(60)
        updates = len(pump.updates)
        pump.stop()
        self.assertEqual(len(pump.updates), updates)
        self.assertEqual(pump.events[-1], ("device stop",))
        self.assertEqual(pump.log.errors, [])

    def test_stop_without_any_run(self):
        pump = _Pump()
        self.assertEqual(pump.stop(), "stopped")


class DriverWiringTests(unittest.TestCase):
    """Der echte BT100-1F-Treiber: Abschnitt dosing wird gelesen, Start/Stopp gehen als dringende
    WF-Frames raus."""

    def test_without_dosing_section_nothing_changes(self):
        device = Device("127.0.0.1:12399", pump_address=1)
        self.assertIsNone(device._dosing_settings)

    def test_dosing_section_is_checked_at_construction(self):
        device = Device("127.0.0.1:12399", pump_address=1, dosing=dict(CONFIG))
        self.assertEqual(device._dosing_settings.valve, "valve1")
        incomplete = {key: value for key, value in CONFIG.items() if key != "dead_volume_ml"}
        self.assertRaises(ValueError, Device, "127.0.0.1:12398", pump_address=1, dosing=incomplete)

    def test_start_and_stop_frames(self):
        device = Device("127.0.0.1:12399", pump_address=1, dosing=dict(CONFIG))
        sent = []
        device.send_cmd = sent.append
        start = device._dosing_pump_start(1.2)
        # 1,2 mL/min = 1 200 000 nL/min = 00 12 4F 80, State1 = 03 (Start, im Uhrzeigersinn)
        self.assertEqual(bytes(start.bytestring), build_wire_frame(1, b"WF" + bytes.fromhex("00124F80") + b"\x03"))
        self.assertTrue(start.parameters.urgent and start.parameters.run_while_device_busy)
        stop = device._dosing_pump_stop()
        self.assertEqual(bytes(stop.bytestring), build_wire_frame(1, b"WF" + bytes.fromhex("00124F80") + b"\x02"))
        self.assertTrue(stop.parameters.urgent and stop.parameters.run_while_device_busy)
        self.assertEqual(len(sent), 3)                        # Start, Stopp, RF zum Zuruecklesen
        self.assertEqual(bytes(sent[2].bytestring), build_wire_frame(1, b"RF"))

    def test_mixin_stop_comes_first_in_the_mro(self):
        self.assertIs(Device.stop, vd.ValveDosingMixIn.stop)
        self.assertIs(Device.link_devices, vd.ValveDosingMixIn.link_devices)


# ---------------------------------------------------------------------------------------------------
# Rezept (add_recipe, 10.11.2026)
# ---------------------------------------------------------------------------------------------------

class ParseAdditionsTests(unittest.TestCase):
    def test_full_line(self):
        self.assertEqual(vd.parse_additions("Leitsalz=3:5;Wasser=20;Saeure 1=4:1.2;NaOH=5:1.2"),
                         [("Leitsalz", 3, 5.0), ("Wasser", None, 20.0), ("Saeure 1", 4, 1.2), ("NaOH", 5, 1.2)])

    def test_zero_or_empty_volume_drops_the_entry(self):
        self.assertEqual(vd.parse_additions("Leitsalz=3:5;Saeure 2=6:0;NaOH=5:;Wasser=0.0"), [("Leitsalz", 3, 5.0)])
        self.assertEqual(vd.parse_additions(""), [])
        self.assertEqual(vd.parse_additions(None), [])

    def test_port_zero_drops_the_entry(self):
        # vorfuellen: ein Volumen fuer mehrere Ports, nicht genutzte Ports stehen auf 0
        self.assertEqual(vd.parse_additions("Wasser=5;Port A=2:2;Port B=3:2;Port C=0:2;Port D=0.0:2"),
                         [("Wasser", None, 5.0), ("Port A", 2, 2.0), ("Port B", 3, 2.0)])

    def test_frontend_floats_for_ports(self):
        # Die Parameter kommen aus dem Frontend als float ("3.0") in den Text.
        self.assertEqual(vd.parse_additions("Leitsalz=3.0:5.0;NaOH=5.0:1.2"), [("Leitsalz", 3, 5.0), ("NaOH", 5, 1.2)])

    def test_unnamed_entries(self):
        self.assertEqual(vd.parse_additions("3:5; 2"), [("Port 3", 3, 5.0), ("Wasser", None, 2.0)])

    def test_bad_entries(self):
        for text in ("Leitsalz=abc:5", "Leitsalz=3:abc", "Leitsalz=2.5:1", "Leitsalz=3:-1"):
            self.assertRaises(ValueError, vd.parse_additions, text)


class RecipePlanTests(unittest.TestCase):
    ADDITIONS = [("Leitsalz", 3, 5.0), ("Wasser", None, 20.0), ("Saeure 1", 4, 1.2), ("NaOH", 5, 1.2)]

    def test_order_flushing_and_fill(self):
        steps = vd.plan_recipe(self.ADDITIONS, settings(), target_volume_ml=50)
        self.assertEqual([repr(s) for s in steps], [
            "Ventil->Port 3", "reagent 5000 uL @ 5 mL/min", "Ventil->Port 1", "water 750 uL @ 4.5 mL/min",
            "water 20000 uL @ 5 mL/min",                                   # Ventil steht schon auf Wasser
            "Ventil->Port 4", "reagent 1200 uL @ 5 mL/min", "Ventil->Port 1", "water 750 uL @ 4.5 mL/min",
            "Ventil->Port 5", "reagent 1200 uL @ 5 mL/min", "Ventil->Port 1", "water 750 uL @ 4.5 mL/min",
            "water 20350 uL @ 5 mL/min"])                                  # Auffuellen: 50 - 29.65
        labels = []
        for step in steps:
            if step.label not in labels:
                labels.append(step.label)
        self.assertEqual(labels, ["Leitsalz", "Wasser", "Saeure 1", "NaOH", "Auffuellen auf 50 mL"])
        totals = vd.plan_totals(steps)
        self.assertAlmostEqual(totals["reagent_ml"], 7.4)
        self.assertAlmostEqual(totals["total_ml"], 50.0)

    def test_pause_between_additions(self):
        steps = vd.plan_recipe(self.ADDITIONS[:2], settings(), pause_s=30)
        self.assertEqual([s.kind for s in steps], ["valve", "pump", "valve", "pump", "pause", "pump"])
        self.assertEqual(steps[4].label, "Wasser")

    def test_without_target_volume_nothing_is_filled(self):
        steps = vd.plan_recipe(self.ADDITIONS[:1], settings(), target_volume_ml=0)
        self.assertEqual(len(steps), 4)
        steps = vd.plan_recipe(self.ADDITIONS[:1], settings(), target_volume_ml="")
        self.assertEqual(len(steps), 4)

    def test_exact_target_volume_needs_no_fill(self):
        steps = vd.plan_recipe(self.ADDITIONS[:1], settings(), target_volume_ml=5.75)
        self.assertEqual(len(steps), 4)

    def test_start_volume_counts(self):
        steps = vd.plan_recipe(self.ADDITIONS[:1], settings(), target_volume_ml=10, start_volume_ml=4)
        self.assertAlmostEqual(steps[-1].volume_ml, 0.25)

    def test_budget_exceeded_is_an_error_before_anything_moves(self):
        error = self.assertRaises(ValueError, vd.plan_recipe, self.ADDITIONS, settings(), target_volume_ml=28)
        self.assertIn("29.650 mL", str(error))
        self.assertIn("Zielvolumen 28.000 mL", str(error))

    def test_empty_recipe(self):
        self.assertRaises(ValueError, vd.plan_recipe, [], settings())
        self.assertEqual(len(vd.plan_recipe([], settings(), target_volume_ml=10)), 2)   # nur Auffuellen

    def test_bad_numbers(self):
        self.assertRaises(ValueError, vd.plan_recipe, self.ADDITIONS[:1], settings(), target_volume_ml=-1)
        self.assertRaises(ValueError, vd.plan_recipe, self.ADDITIONS[:1], settings(), pause_s=-1)
        self.assertRaises(ValueError, vd.plan_recipe, [("x", 17, 1.0)], settings(), positions=16)


class RecipeRunTests(unittest.TestCase):
    LINE = "Leitsalz=3.0:1.0;Wasser=2.0;Saeure 1=4.0:0.2;Saeure 2=6.0:0.0;NaOH=5.0:0.2"

    def test_recipe_runs_through_and_reports_each_addition(self):
        pump = _Pump()
        pump.add_recipe(self.LINE, target_volume="10.0", pause_s="0.0")
        self.assertEqual(pump.state, devicestate.Busy)
        pump.run_all(400)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "finished")
        valves = [e[1] for e in pump.events if e[0] == "valve"]
        self.assertEqual(valves, [3, 1, 4, 1, 5, 1])
        starts = [e for e in pump.events if e[0] == "start"]
        self.assertEqual(len(starts), 8)       # Leitsalz, Spuelen, Wasser, Saeure, Spuelen, NaOH, Spuelen, Auffuellen
        additions = [u["dosing_addition"] for u in pump.updates if "dosing_addition" in u]
        self.assertEqual(additions, ["", "1/5: Leitsalz", "2/5: Wasser", "3/5: Saeure 1", "4/5: NaOH",
                                     "5/5: Auffuellen auf 10 mL", "fertig"])
        self.assertAlmostEqual(pump.last("dosed_ml"), 1.4)
        self.assertAlmostEqual(pump.last("delivered_ml"), 10.0)
        self.assertEqual(pump.log.errors, [])
        self.assertIsNone(pump._dosing.reagent_port)

    def test_priming_recipe_with_own_title(self):
        pump = _Pump()
        pump.add_recipe("Wasser=0.1;Port A=2.0:0.05;Port B=3.0:0.05;Port C=0.0:0.05;Port D=0.0:0.05",
                        target_volume=0, title="Vorfuellen")
        pump.run_all(200)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "finished")
        self.assertEqual([e[1] for e in pump.events if e[0] == "valve"], [1, 2, 1, 3, 1])
        self.assertEqual(pump._dosing.title, "Vorfuellen")
        self.assertEqual(pump.log.errors, [])

    def test_budget_error_fails_cleanly_without_moving_anything(self):
        pump = _Pump()
        pump.add_recipe(self.LINE, target_volume=2.0)
        pump.run_all(5)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "failed")
        self.assertEqual(pump.state, devicestate.Error)
        self.assertEqual(pump.events, [])
        self.assertIn("Zielvolumen", pump.last("dosing_step"))

    def test_stop_in_the_middle_names_the_addition(self):
        pump = _Pump()
        pump.add_recipe(self.LINE, target_volume=10)
        pump.run_all(3)                       # mitten im Leitsalz
        pump.stop()
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "cancelled")
        self.assertEqual(len(pump.log.errors), 1)       # Reagenz von Port 3 im Schlauch
        self.assertIn("Port 3", pump.log.errors[0])


# ---------------------------------------------------------------------------------------------------
# pH-Regelung in vier Schritten (regulate_ph / add_recipe_ph, 11.11.2026) - Flaschen fest in der Config
# ---------------------------------------------------------------------------------------------------

PH_PORTS = {"saeure_schwach": 2, "saeure_stark": 3, "base_schwach": 4, "base_stark": 5}
PH_CONFIG = {**CONFIG, "ph_device": "liquiline", "ph_ports": PH_PORTS}


def make_ph_pump(ph, ports=PH_PORTS):
    pump = _Pump(dosing={**PH_CONFIG, "ph_ports": ports})
    meter = _PhMeter(pump.clock, ph=ph)
    pump.ph_meter = meter
    pump.link_devices({"valve1": pump.valve, "liquiline": meter})
    pump.log.errors = []
    return pump, meter


def doses(pump):
    """[(Port, Dose uL)] je Reagenz-Dose in der Reihenfolge der Ausfuehrung (Rate = Volumen / 10 s)."""
    out, port = [], None
    for e in pump.events:
        if e[0] == "valve":
            port = e[1]
        elif e[0] == "start" and port != 1:
            out.append((port, round(e[2] / 6.0 * 1000)))
    return out


class PhPortsSettingsTests(unittest.TestCase):
    def test_ports_are_read(self):
        s = vd.DosingSettings(PH_CONFIG)
        self.assertEqual(s.ph_ports, PH_PORTS)
        self.assertEqual((s.ph_device, s.ph_observable, s.ph_max_age_s), ("liquiline", "ph_value", 15.0))
        self.assertIsNone(vd.DosingSettings(CONFIG).ph_ports)

    def test_missing_bottle_is_zero(self):
        s = vd.DosingSettings({**PH_CONFIG, "ph_ports": {"saeure_stark": 3, "base_stark": 5}})
        self.assertEqual(s.ph_ports, {"base_stark": 5, "base_schwach": 0, "saeure_stark": 3, "saeure_schwach": 0})

    def test_bad_ports_are_rejected(self):
        for ports in ({"base_stark": 1}, {"base_stark": 2.5}, {"base_stark": 5, "base_schwach": 5}, {"naoh": 5}, "5"):
            self.assertRaises(ValueError, vd.DosingSettings, {**PH_CONFIG, "ph_ports": ports})


class PhRegelungTests(unittest.TestCase):
    """Attrappe: stark 20 pH/mL (200 uL = 4, 50 uL = 1), schwach 4 pH/mL (200 uL = 0,8, 50 uL = 0,2)."""

    def test_schritt_1_und_2(self):
        # 4 -> +4 -> 8 (gleiche Seite) -> 12: Seite gewechselt -> Schritt 2 starke Saeure 50 uL: 11, 10, 9 fertig
        pump, meter = make_ph_pump(4.0)
        pump.regulate_ph(9.0, 0.2, wait_s=0)
        pump.run_all(600)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "finished", pump.last("dosing_step"))
        self.assertEqual(doses(pump), [(5, 200), (5, 200), (3, 50), (3, 50), (3, 50)])
        self.assertAlmostEqual(meter.ph, 9.0)
        self.assertEqual(pump.last("ph_additions"), 5)

    def test_alle_vier_schritte_nie_zurueck(self):
        # 8,4 -> 12,4 (S1) -> starke Saeure 50 x4 -> 8,4 (S2, Seite gewechselt) -> S3 schwache Base 200 +0,8 -> 9,2
        # -> Toleranz 0,1: Seite gewechselt -> S4 schwache Saeure 50 -0,2 -> 9,0 fertig
        pump, meter = make_ph_pump(8.4)
        pump.regulate_ph(9.0, 0.1, wait_s=0)
        pump.run_all(900)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "finished", pump.last("dosing_step"))
        self.assertEqual(doses(pump), [(5, 200), (3, 50), (3, 50), (3, 50), (3, 50), (4, 200), (2, 50)])
        self.assertAlmostEqual(meter.ph, 9.0)
        labels = [u["dosing_addition"] for u in pump.updates if "dosing_addition" in u]
        self.assertTrue(any(l.startswith("Dose 6, Schritt 3: schwache Base 200 uL (Port 4") for l in labels), labels)
        self.assertTrue(any(l.startswith("Dose 7, Schritt 4: schwache Saeure 50 uL (Port 2") for l in labels), labels)

    def test_eigene_volumina(self):
        pump, meter = make_ph_pump(4.0)
        pump.regulate_ph(9.0, 0.2, vol_gross=0.1, vol_klein=0.02, wait_s=0)
        pump.run_all(600)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "finished")
        self.assertEqual(doses(pump)[0], (5, 100))

    def test_auffuellen_nach_erreichtem_ziel(self):
        pump, meter = make_ph_pump(4.0)
        pump.regulate_ph(9.0, 0.2, wait_s=0, target_volume=20, start_volume=5)
        pump.run_all(900)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "finished")
        self.assertAlmostEqual(pump.last("delivered_ml"), 15.0)          # 20 - 5 schon drin
        labels = [u["dosing_addition"] for u in pump.updates if "dosing_addition" in u]
        self.assertEqual(labels[-2], "Auffuellen auf 20 mL")

    def test_ohne_zielvolumen_kein_auffuellen(self):
        pump, meter = make_ph_pump(8.9)
        pump.regulate_ph(9.0, 0.2, wait_s=0, target_volume=0)
        pump.run_all(10)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "finished")
        self.assertEqual(pump.events, [])

    def test_fehlende_schwache_flaschen_nehmen_die_starken(self):
        pump, meter = make_ph_pump(8.4, ports={"saeure_stark": 3, "base_stark": 5})
        pump.regulate_ph(9.0, 0.1, wait_s=0)
        pump.run_all(2000)
        self.assertEqual({p for p, _ in doses(pump)}, {3, 5})
        self.assertIn(pump.last(vd.DOSING_OBSERVABLE), ("finished", "failed"))

    def test_keine_flasche_fuer_eine_richtung(self):
        pump, meter = make_ph_pump(7.0, ports={"saeure_stark": 3, "saeure_schwach": 2})
        pump.regulate_ph(9.0, 0.2, wait_s=0)
        pump.run_all(5)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "failed")
        self.assertEqual(pump.events, [])
        self.assertIn("keine Flasche fuer Base", pump.last("dosing_step"))

    def test_ph_ports_fehlen_in_der_config(self):
        pump = _Pump(dosing={**CONFIG, "ph_device": "liquiline"})
        meter = _PhMeter(pump.clock, ph=7.0)
        pump.ph_meter = meter
        pump.link_devices({"valve1": pump.valve, "liquiline": meter})
        pump.regulate_ph(9.0, 0.2)
        pump.run_all(5)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "failed")
        self.assertIn("ph_ports", pump.last("dosing_step"))

    def test_reagiert_nicht_und_zielvolumen(self):
        pump, meter = make_ph_pump(4.0)
        meter.dead = True
        pump.regulate_ph(9.0, 0.2, wait_s=0)
        pump.run_all(600)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "failed")
        self.assertIn("reagiert nicht", pump.last("dosing_step"))
        self.assertEqual(len(doses(pump)), 3)
        pump, meter = make_ph_pump(4.0)
        pump.regulate_ph(9.0, 0.2, wait_s=0, target_volume=10, start_volume=9.5)
        pump.run_all(10)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "failed")
        self.assertEqual(pump.events, [])
        self.assertIn("Zielvolumen", pump.last("dosing_step"))

    def test_falsche_eingaben(self):
        for kwargs in ({"vol_klein": 0.3}, {"tolerance": 0}, {"target_ph": 15}, {"target_volume": 5, "start_volume": 5}):
            pump, meter = make_ph_pump(7.0)
            pump.regulate_ph(**{"target_ph": 9.0, "tolerance": 0.2, "wait_s": 0, **kwargs})
            pump.run_all(5)
            self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "failed", kwargs)
            self.assertEqual(pump.events, [])

    def test_wartet_auf_den_ersten_ph_wert(self):
        pump, meter = make_ph_pump(8.9)
        meter.empty = True
        pump.clock.callLater(3.0, setattr, meter, "empty", False)
        pump.regulate_ph(9.0, 0.2, wait_s=0)
        pump.run_all(10)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "finished")
        self.assertIn("warte auf pH-Wert", [u.get("dosing_step") for u in pump.updates])

    def test_alter_fehlender_schlechter_ph_wert(self):
        for prepare, text in ((lambda m: setattr(m, "age", 60.0), "alt"),
                              (lambda m: setattr(m, "empty", True), "kein pH-Wert"),
                              (lambda m: setattr(m, "status", "Not assigned"), "nicht Good")):
            pump, meter = make_ph_pump(7.0)
            prepare(meter)
            pump.regulate_ph(9.0, 0.2, wait_s=0)
            pump.run_all(30)
            self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "failed", text)
            self.assertIn(text, pump.last("dosing_step"))
            self.assertEqual(pump.events, [])

    def test_stop_mitten_in_der_regelung(self):
        pump, meter = make_ph_pump(4.0)
        pump.regulate_ph(9.0, 0.2, wait_s=30)
        pump.run_all(3)
        pump.stop()
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "cancelled")


class AnsatzTests(unittest.TestCase):
    """ansatz = feste Zugaben -> pH-Regelung -> Auffuellen. Leitsalz an Port 6 (wirkt nicht), Saeure 1 = Port 3."""
    LINE = "Leitsalz=6.0:0.1;Wasser=0.2;Saeure 1=3.0:0.01;Saeure 2=0.0:0.1"

    def test_zugaben_dann_regelung_dann_auffuellen(self):
        # Saeure 1 10 uL stark = -0,2 -> 4,8; dann starke Base 200 = +4 -> 8,8: im Fenster; auffuellen auf 10
        pump, meter = make_ph_pump(5.0)
        pump.add_recipe_ph(self.LINE, target_ph=9.0, tolerance=0.2, wait_s=20, target_volume=10, pause_s=0)
        pump.run_all(900)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "finished", pump.last("dosing_step"))
        valves = [e[1] for e in pump.events if e[0] == "valve"]
        self.assertEqual(valves, [6, 1, 3, 1, 5, 1, 1])
        self.assertAlmostEqual(meter.ph, 8.8)
        self.assertAlmostEqual(pump.last("delivered_ml"), 10.0)
        labels = [u["dosing_addition"] for u in pump.updates if "dosing_addition" in u]
        self.assertEqual(labels[1:4], ["Leitsalz", "Wasser", "Saeure 1"])
        self.assertTrue(any(l.startswith("Dose 1, Schritt 1: starke Base 200 uL (Port 5") for l in labels), labels)
        self.assertEqual(labels[-2], "Auffuellen auf 10 mL")
        self.assertEqual(pump.log.errors, [])

    def test_ohne_feste_zugaben_wie_ph_regelung(self):
        pump, meter = make_ph_pump(8.4)
        pump.add_recipe_ph("Leitsalz=6.0:0", target_ph=9.0, tolerance=0.1, wait_s=0, target_volume=20)
        pump.run_all(1200)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "finished", pump.last("dosing_step"))
        self.assertEqual(doses(pump), [(5, 200), (3, 50), (3, 50), (3, 50), (3, 50), (4, 200), (2, 50)])
        self.assertAlmostEqual(pump.last("delivered_ml"), 20.0)

    def test_budget_der_festen_zugaben_vor_dem_start(self):
        pump, meter = make_ph_pump(7.0)
        pump.add_recipe_ph(self.LINE, target_ph=9.0, target_volume=1.0)
        pump.run_all(5)
        self.assertEqual(pump.last(vd.DOSING_OBSERVABLE), "failed")
        self.assertEqual(pump.events, [])
        self.assertIn("Zielvolumen", pump.last("dosing_step"))
