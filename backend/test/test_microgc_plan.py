# -*- test-case-name: backend.test.test_microgc_plan -*-
"""Reine Logik des GC-Messplans (13.10.2026): Namens-/Zeitparser, Konzentrationen aus Laufdaten,
Abbruchverhalten des Plans. Keine Geraetekommunikation. Lauf: python -m twisted.trial backend.test"""
import json
from pathlib import Path

from twisted.trial import unittest

from backend.drivers import inficon_microgc_fusion as gc

_FIXTURE = Path(__file__).resolve().parents[2] / "logs" / "2026" / "10" / "13" / "gc_run_1310" / "values.json"


def _run_data():
    return {
        "annotations": {"name": "26175_10 min", "tags": ["Kolbe", "MP"]},
        "runTimeStamp": "2026-10-13T07:20:34.338Z",
        "detectors": {
            "moduleA:tcd": {"analysis": {"peaks": [
                {"label": "H2", "concentration": 1.5, "normalizedConcentration": 1.4, "height": 1, "area": 2, "top": 0.3},
                {"label": "N2", "concentration": "77.2", "normalizedConcentration": 76.0, "height": 1, "area": 2, "top": 0.5},
                {"height": 3.0, "area": 9.0, "top": 2.5},
            ]}},
            "moduleC:tcd": {"analysis": {"peaks": [
                {"label": "1,3 Butadien", "concentration": 0, "normalizedConcentration": 0, "height": 1, "area": 2, "top": 0.7},
                {"label": "trans + cis 2 Buten", "concentration": None, "height": 1, "area": 2, "top": 0.9},
                {"label": "n Hexane", "concentration": 0.25, "height": 1, "area": 2, "top": 1.1},
            ]}},
            "moduleD:tcd": {"analysis": {}},
        },
    }


class ParserTests(unittest.TestCase):
    def test_observable_key(self):
        self.assertEqual(gc.observable_key("H2"), "gc_H2")
        self.assertEqual(gc.observable_key("n Hexane"), "gc_n_Hexane")
        self.assertEqual(gc.observable_key("1,3 Butadien"), "gc_1_3_Butadien")
        self.assertEqual(gc.observable_key("trans + cis 2 Buten"), "gc_trans_cis_2_Buten")

    def test_parse_minutes_separators_and_order(self):
        self.assertEqual(gc.parse_minutes("0;10;20"), [0.0, 10.0, 20.0])
        self.assertEqual(gc.parse_minutes("20, 0 10"), [0.0, 10.0, 20.0])
        self.assertEqual(gc.parse_minutes("5;5;5"), [5.0])
        self.assertEqual(gc.parse_minutes([0, "2.5"]), [0.0, 2.5])
        self.assertEqual(gc.parse_minutes(""), [])
        self.assertRaises(ValueError, gc.parse_minutes, "0;zehn")

    def test_run_name(self):
        self.assertEqual(gc.run_name("26175", 10.0), "26175_10 min")
        self.assertEqual(gc.run_name("26175", 0.5), "26175_0.5 min")
        self.assertEqual(gc.run_name("26175", 219), "26175_219 min")

    def test_safe_filename(self):
        self.assertEqual(gc.safe_filename("26175_10 min"), "26175_10_min")


class ConcentrationTests(unittest.TestCase):
    def test_concentrations_from_run_data(self):
        values = gc.concentrations_from_run_data(_run_data())
        self.assertEqual(values["gc_H2"], 1.5)
        self.assertEqual(values["gc_H2_norm"], 1.4)
        self.assertEqual(values["gc_N2"], 77.2)          # Text wird zur Zahl
        self.assertEqual(values["gc_1_3_Butadien"], 0.0)  # 0 bleibt erhalten
        self.assertNotIn("gc_trans_cis_2_Buten", values)  # None -> ausgelassen
        self.assertEqual(values["gc_n_Hexane"], 0.25)
        self.assertNotIn("gc_n_Hexane_norm", values)
        self.assertTrue(all(isinstance(v, float) for v in values.values()))

    def test_empty_or_broken_run_data(self):
        self.assertEqual(gc.concentrations_from_run_data({}), {})
        self.assertEqual(gc.concentrations_from_run_data({"detectors": {"x": None}}), {})

    def test_real_run_data_from_device(self):
        """Laufdaten des echten Geraets vom 13.10.2026 (Luft): O2/N2 um 21/77 %, 25 benannte Peaks."""
        if not _FIXTURE.exists():
            raise unittest.SkipTest(f"{_FIXTURE} nicht vorhanden")
        run_data = json.load(open(_FIXTURE, encoding="utf-8"))["microgc"]["last_run_data"][-1][1]
        values = gc.concentrations_from_run_data(run_data)
        self.assertEqual(len([k for k in values if not k.endswith("_norm")]), 25)
        self.assertAlmostEqual(values["gc_O2"], 21.3, places=1)
        self.assertAlmostEqual(values["gc_N2"], 77.4, places=1)
        self.assertIn("gc_n_Heptane", values)
        self.assertIn("gc_1_3_Butadien", values)


class _FakeTimer:
    def __init__(self):
        self.cancelled = False
    def active(self):
        return not self.cancelled
    def cancel(self):
        self.cancelled = True


class ScheduleCancelTests(unittest.TestCase):
    """_cancel_schedule() ohne Geraet: nur der Plan-Zustand und die Timer."""

    def _device(self):
        device = gc.Device.__new__(gc.Device)
        device._schedule = None
        device.updates = []
        device.update_observables = lambda values, timestamp=None: device.updates.append(values)
        class _Log:
            def info(self, *a, **k): pass
            warn = error = info
        device.log = _Log()
        return device

    def test_cancel_stops_timers_and_marks_schedule(self):
        device = self._device()
        schedule = device._schedule = gc._Schedule("26175", ["Kolbe"], [0, 10, 20], 5, "/tmp/x")
        schedule.timers = [_FakeTimer(), _FakeTimer()]
        schedule.due = [10.0]
        device._cancel_schedule("stop")
        self.assertTrue(schedule.cancelled)
        self.assertTrue(all(t.cancelled for t in schedule.timers) or schedule.timers == [])
        self.assertEqual(schedule.due, [])
        self.assertEqual(device.updates, [{gc.SCHEDULE_OBSERVABLE: "cancelled"}])

    def test_cancel_after_regular_end_is_silent(self):
        device = self._device()
        schedule = device._schedule = gc._Schedule("26175", [], [0], 5, "/tmp/x")
        schedule.remaining = 0
        device._cancel_schedule("stop")
        self.assertFalse(schedule.cancelled)
        self.assertEqual(device.updates, [])

    def test_cancel_without_schedule(self):
        device = self._device()
        device._cancel_schedule("stop")   # darf nicht werfen
        self.assertEqual(device.updates, [])


class PlanTimesTests(unittest.TestCase):
    """gc_minutes-Eingabe -> Zeitpunkte/Modus (13.10.2026, nach dem 7.5-Vorfall bei Versuch 26175)."""

    def test_list_is_fixed_points(self):
        self.assertEqual(gc.plan_times("0;10;20", 219), ([0.0, 10.0, 20.0], False))

    def test_single_number_is_interval_until_end(self):
        self.assertEqual(gc.plan_times("10", 35), ([0.0, 10.0, 20.0, 30.0], False))
        self.assertEqual(gc.plan_times(7.5, 15), ([0.0, 7.5, 15.0], False))

    def test_zero_is_continuous(self):
        self.assertEqual(gc.plan_times("0", 219), ([], True))
        self.assertEqual(gc.plan_times(0, 1), ([], True))

    def test_single_number_without_duration_stays_single_point(self):
        self.assertEqual(gc.plan_times("7.5", None), ([7.5], False))
        self.assertEqual(gc.plan_times("7.5", ""), ([7.5], False))
        self.assertEqual(gc.plan_times("0", None), ([0.0], False))
