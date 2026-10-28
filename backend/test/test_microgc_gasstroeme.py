# -*- test-case-name: backend.test.test_microgc_gasstroeme -*-
"""Drei Zellen an einem microGC (26.10.2026): der Messplan misst die Gasstroeme aus `streams` im Kreis
(Z1, Z2, Z3, Z1, ...), benennt die Laeufe '<prefix>_<Strom> <t> min', stellt vor jedem Lauf die Ventile
des Stroms und wartet flush_s, meldet die Konzentrationen als gc_<Strom>_<Label> und faehrt die
Abschlussmessung einmal je Strom. Ohne Geraet: _schedule_run als Fake (wie test_microgc_abschlussmessung),
fuer das Umschalten der Ventile ein Fake-Ventil und gefakte HTTP-Schritte.
Lauf: python -m twisted.trial backend.test.test_microgc_gasstroeme"""
import time

from twisted.internet import defer
from twisted.trial import unittest

from backend.drivers import inficon_microgc_fusion as gc
from backend.test.test_microgc_abschlussmessung import _device, _finish_next, _finished, _Log


STREAMS = ["Z1", "Z2", "Z3"]


def _schedule(device, minutes, until, final_run=True, continuous=False, elapsed_min=0.0, streams=STREAMS):
    schedule = device._schedule = gc._Schedule("26180", ["Kolbe"], minutes, 5, "/tmp/x", continuous=continuous,
                                               until_minutes=until, final_run=final_run, streams=streams)
    schedule.t0 = time.time() - 60.0 * elapsed_min
    return schedule


def _names(device):
    return [r[0] for r in device.runs]


class RoundRobinTests(unittest.TestCase):
    def test_runs_rotate_through_the_streams(self):
        device = _device()
        schedule = _schedule(device, [0, 10, 20, 30], until=200, final_run=False)
        for minute in (0, 10, 20, 30):
            device._schedule_due(schedule, minute)
            _finish_next(device)
        self.assertEqual(_names(device), ["26180_Z1_0 min", "26180_Z2_10 min", "26180_Z3_20 min", "26180_Z1_30 min"])
        self.assertTrue(_finished(device))

    def test_continuous_mode_rotates_too(self):
        device = _device()
        schedule = _schedule(device, [], until=100, continuous=True, final_run=False)
        device._schedule_next(schedule)
        for _ in range(4):
            _finish_next(device)
        streams = [name.split("_")[1] for name in _names(device)]
        self.assertEqual(streams, ["Z1", "Z2", "Z3", "Z1", "Z2"])

    def test_final_run_once_per_stream(self):
        device = _device()
        schedule = _schedule(device, [0], until=30)
        device._schedule_due(schedule, 0)
        _finish_next(device)
        self.assertFalse(_finished(device))
        schedule.t0 = time.time() - 60.0 * 30.5
        device._schedule_final_due(schedule)
        # drei Abschlussmessungen nacheinander, erst dann finished
        self.assertEqual(len(device.runs), 2)
        self.assertTrue(device.runs[1][0].startswith("26180_Z1_Ende 30"), device.runs[1][0])
        _finish_next(device)
        self.assertEqual(len(device.runs), 3)
        self.assertTrue(device.runs[2][0].startswith("26180_Z2_Ende 30"))
        self.assertFalse(_finished(device))
        _finish_next(device)
        self.assertTrue(device.runs[3][0].startswith("26180_Z3_Ende 30"))
        self.assertFalse(_finished(device))
        _finish_next(device)
        self.assertTrue(_finished(device))
        self.assertEqual(schedule.done, 4)
        self.assertFalse(schedule.is_open())
        self.assertEqual(len(device.runs), 4)

    def test_without_streams_everything_is_as_before(self):
        device = _device()
        schedule = _schedule(device, [0], until=30, streams=[])
        device._schedule_due(schedule, 0)
        _finish_next(device)
        schedule.t0 = time.time() - 60.0 * 30.5
        device._schedule_final_due(schedule)
        _finish_next(device)
        self.assertEqual(_names(device)[0], "26180_0 min")
        self.assertTrue(_names(device)[1].startswith("26180_Ende 30"))
        self.assertTrue(_finished(device))


class _Reply:
    def __init__(self, parameters=None, json=None):
        self.parameters = parameters or {}
        self.json = json


class _FakeValve:
    def __init__(self, log):
        self.positions = []
        self.log = log

    def set_position(self, position, **kwargs):
        self.positions.append(position)
        self.log.append((id(self), position))

        class Cmd:
            deferred_result = defer.succeed(None)
        return Cmd()


def _real_run_device(flush_s=7.0):
    """Geraet mit echtem _schedule_run, aber gefakten HTTP-Schritten: Leerlauf sofort, Lauf sofort fertig,
    Laufdaten mit einem H2-Peak."""
    device = gc.Device.__new__(gc.Device)
    device._schedule = None
    device.updates = []
    device.update_observables = lambda values, timestamp=None: device.updates.append(dict(values))
    device.log = _Log()
    device.flush_s = flush_s
    device.switch_after_s = 0.0
    device.valve_log = []
    device.v1, device.v2 = _FakeValve(device.valve_log), _FakeValve(device.valve_log)
    device.streams = {"Z1": {"ventil_1": "A", "ventil_2": "B"}, "Z2": {"ventil_1": "B", "ventil_2": "A"}}
    device._valves = {"ventil_1": device.v1, "ventil_2": device.v2}
    device.waits = []
    device.callLater = lambda delay, fn, *a: (device.waits.append(delay), fn(*a))
    device._poll_status = lambda schedule, is_done, max_seconds, what: defer.succeed("public:ready")
    device.locations = iter(["/runData/a", "/runData/b", "/runData/b", "/runData/c"])
    run_data = {"runTimeStamp": "t", "annotations": {},
                "detectors": {"moduleA": {"analysis": {"peaks": [{"label": "H2", "concentration": 12.5}]}}}}

    def urgent_query(command_name, **kwargs):
        if command_name == "LAST_RUN_LOCATION":
            return defer.succeed(_Reply({"last_run_location": next(device.locations)}))
        if command_name == "RUN_DATA":
            return defer.succeed(_Reply(json=run_data))
        raise AssertionError(command_name)
    device._urgent_query = urgent_query
    device.run_bodies = []

    def write(command_name, command_values=None, **kwargs):
        device.run_bodies.append(command_values["json_body"])

        class Cmd:
            deferred_result = defer.succeed(None)
        return Cmd()
    device.write = write
    device.save_dir_writes = []
    return device


class SwitchStreamTests(unittest.TestCase):
    def test_valves_are_set_and_flushed_before_the_run(self):
        device = _real_run_device(flush_s=7.0)
        schedule = gc._Schedule("26180", ["Kolbe"], [0], 5, self.mktemp(), until_minutes=30, streams=["Z1", "Z2"])
        results = []
        device._schedule_run(schedule, "26180_Z1_0 min", 0, stream="Z1").addBoth(results.append)
        self.assertEqual(device.v1.positions, ["A"])
        self.assertEqual(device.v2.positions, ["B"])
        self.assertEqual(device.waits, [7.0])
        self.assertEqual(schedule.last_stream, "Z1")
        self.assertEqual(device.run_bodies[0]["annotations"], {"name": "26180_Z1_0 min", "tags": ["Kolbe", "Z1"]})
        self.assertEqual(len(results), 1)
        self.assertNotIsInstance(results[0], Exception)
        published = [u for u in device.updates if "gc_Z1_H2" in u]
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["gc_Z1_H2"], 12.5)
        self.assertEqual(published[0]["gc_stream"], "Z1")
        self.assertNotIn("gc_H2", published[0])

    def test_same_stream_again_skips_valves_and_flush(self):
        device = _real_run_device(flush_s=7.0)
        schedule = gc._Schedule("26180", [], [0, 1], 5, self.mktemp(), until_minutes=30, streams=["Z1"])
        device._schedule_run(schedule, "a", 0, stream="Z1")
        device._schedule_run(schedule, "b", 1, stream="Z1")
        self.assertEqual(device.v1.positions, ["A"])
        self.assertEqual(device.waits, [7.0])

    def test_switching_to_the_other_stream_sets_both_valves(self):
        device = _real_run_device(flush_s=0.0)
        schedule = gc._Schedule("26180", [], [0, 1], 5, self.mktemp(), until_minutes=30, streams=["Z1", "Z2"])
        device._schedule_run(schedule, "a", 0, stream="Z1")
        device._schedule_run(schedule, "b", 1, stream="Z2")
        self.assertEqual(device.v1.positions, ["A", "B"])
        self.assertEqual(device.v2.positions, ["B", "A"])
        self.assertEqual(device.waits, [])   # flush_s 0: kein Warten


class PreswitchTests(unittest.TestCase):
    """27.10.2026 Variante B: switch_after_s nach dem Laufstart stehen die Ventile schon auf dem naechsten
    Strom; der naechste Lauf schaltet dann nicht mehr um und wartet kein flush_s."""

    def _schedule(self, device, **kwargs):
        schedule = gc._Schedule("26180", [], [0, 10], 5, self.mktemp(), until_minutes=30, streams=["Z1", "Z2"], **kwargs)
        return schedule

    def test_valves_switch_to_next_stream_after_start(self):
        device = _real_run_device(flush_s=7.0)
        device.switch_after_s = 60.0
        schedule = self._schedule(device)
        schedule.next_stream()                       # wie _schedule_next: Z1 ist dran, Z2 kommt als naechstes
        schedule.active_name = "a"
        device._schedule_run(schedule, "a", 0, stream="Z1")
        self.assertEqual(device.v1.positions, ["A", "B"])   # Z1, dann vorgezogen Z2
        self.assertEqual(device.v2.positions, ["B", "A"])
        self.assertEqual(device.waits, [7.0, 60.0])          # einmal flush, dann der Umschalt-Timer
        self.assertEqual(schedule.last_stream, "Z2")
        # naechster Lauf Z2: Ventile stehen schon -> kein Umschalten, kein flush; nach dem Start wird
        # wieder vorgezogen auf den dann naechsten Strom (Z1) gestellt
        schedule.next_stream()
        schedule.active_name = "b"
        device._schedule_run(schedule, "b", 10, stream="Z2")
        self.assertEqual(device.v1.positions, ["A", "B", "A"])
        self.assertEqual(device.waits, [7.0, 60.0, 60.0])    # nur ein weiterer Timer, kein zweites flush
        self.assertEqual(schedule.last_stream, "Z1")

    def test_disabled_by_default(self):
        device = _real_run_device(flush_s=0.0)
        schedule = self._schedule(device)
        schedule.active_name = "a"
        device._schedule_run(schedule, "a", 0, stream="Z1")
        self.assertEqual(device.v1.positions, ["A"])
        self.assertEqual(device.waits, [])

    def test_ignored_when_run_is_no_longer_active(self):
        device = _real_run_device(flush_s=0.0)
        device.switch_after_s = 60.0
        schedule = self._schedule(device)
        schedule.active_name = "anderer Lauf"
        device._schedule_run(schedule, "a", 0, stream="Z1")
        self.assertEqual(device.v1.positions, ["A"])         # kein vorgezogenes Umschalten
        self.assertEqual(schedule.last_stream, "Z1")

    def test_peek_next_stream(self):
        device = _real_run_device()
        schedule = self._schedule(device, final_run=True)
        schedule.next_stream()
        self.assertEqual(device._peek_next_stream(schedule), "Z2")       # Listenmodus, remaining 2
        schedule.remaining = 1
        self.assertEqual(device._peek_next_stream(schedule), "Z1")       # danach Abschlussserie ab Z1
        schedule.final_done = True
        self.assertIsNone(device._peek_next_stream(schedule))            # nichts mehr
        schedule.final_pending = 30.0; schedule.final_streams = ["Z2"]
        self.assertEqual(device._peek_next_stream(schedule), "Z2")       # Abschluss: naechster der Reihe
        schedule.cancelled = True
        self.assertIsNone(device._peek_next_stream(schedule))


class StreamNamesTests(unittest.TestCase):
    def _device(self):
        device = gc.Device.__new__(gc.Device)
        device.streams = {"Z1": {"v": "A"}, "Z2": {"v": "B"}}
        device._valves = {"v": object()}
        return device

    def test_parsing(self):
        device = self._device()
        self.assertEqual(device._stream_names(""), [])
        self.assertEqual(device._stream_names(None), [])
        self.assertEqual(device._stream_names("alle"), ["Z1", "Z2"])
        self.assertEqual(device._stream_names("Z2;Z1"), ["Z2", "Z1"])

    def test_unknown_stream_is_an_error(self):
        self.assertRaises(ValueError, self._device()._stream_names, "Z9")

    def test_missing_valve_is_an_error(self):
        device = self._device()
        device._valves = {}
        self.assertRaises(ValueError, device._stream_names, "alle")

    def test_config_parsing(self):
        device = gc.Device.__new__(gc.Device)
        device.streams = {}
        for entry in [{"name": "Z1", "valves": {"a": "A"}}]:
            device.streams[str(entry["name"])] = {str(k): str(v) for k, v in dict(entry["valves"]).items()}
        self.assertEqual(device.streams, {"Z1": {"a": "A"}})


class VentileRuhelageBeimStopp(unittest.TestCase):
    """28.10.2026: Beim Stopp des GC (Experimentende, Stop Experiments) gehen die Gasstrom-Ventile in die
    Ruhelage (safe_state, sonst A) - vorher blieb das zuletzt gestellte Ventil auf B (ventiltest-1-19)."""

    def _device(self):
        device = gc.Device.__new__(gc.Device)
        device.log = _Log()
        device.valve_log = []
        device.v1, device.v2 = _FakeValve(device.valve_log), _FakeValve(device.valve_log)
        device.v2.safe_state = "B"   # ein Ventil, dessen Ruhelage B ist
        device._valves = {"ventil_1": device.v1, "ventil_2": device.v2}
        return device

    def test_alle_ventile_in_ruhelage(self):
        device = self._device()
        device._valves_to_rest()
        self.assertEqual(device.v1.positions, ["A"])
        self.assertEqual(device.v2.positions, ["B"])

    def test_ohne_ventile_passiert_nichts(self):
        device = self._device()
        device._valves = {}
        self.assertIsNone(device._valves_to_rest())

    def test_stop_stellt_ventile_zurueck(self):
        device = self._device()
        device._schedule = None
        called = []
        parent = [b for b in gc.Device.__mro__[1:] if hasattr(b, "stop")][0]
        original = parent.stop
        parent.stop = lambda self_: called.append("parent_stop") or "ok"
        try:
            self.assertEqual(device.stop(), "ok")
        finally:
            parent.stop = original
        self.assertEqual(called, ["parent_stop"])
        self.assertEqual(device.v1.positions, ["A"])
