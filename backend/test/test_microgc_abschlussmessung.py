# -*- test-case-name: backend.test.test_microgc_abschlussmessung -*-
"""GC-Abschlussmessung (16.10.2026, Wunsch Rafael): Nach dem Ende der Elektrolyse (until_minutes) und
nach dem letzten planmaessigen Lauf misst der microGC noch EINMAL ('<prefix>_Ende <t> min'); erst
danach ist der Messplan 'finished' und das Experiment endet. Ohne Geraet: _schedule_run wird durch ein
Fake-Deferred ersetzt (der Test beendet jeden Lauf selbst), die Zeit ueber schedule.t0 gestellt.
Lauf: python -m twisted.trial backend.test.test_microgc_abschlussmessung"""
import time

from twisted.trial import unittest

from backend.drivers import inficon_microgc_fusion as gc


class _FakeTimer:
    def __init__(self):
        self.cancelled = False

    def active(self):
        return not self.cancelled

    def cancel(self):
        self.cancelled = True


class _FakeDeferred:
    """Ersatz fuer das Lauf-Deferred: der Test loest das Laufende selbst aus (finish)."""
    def __init__(self):
        self.callbacks = []

    def addBoth(self, callback, *args):
        self.callbacks.append((callback, args))

    def finish(self, result=None):
        for callback, args in self.callbacks:
            callback(result, *args)


class _Log:
    def info(self, *a, **k):
        pass
    warn = error = info


def _device():
    device = gc.Device.__new__(gc.Device)
    device._schedule = None
    device.updates = []
    device.runs = []           # (name, minute) der gestarteten Laeufe
    device.pending = []        # offene Fake-Deferreds, in Startreihenfolge
    device.update_observables = lambda values, timestamp=None: device.updates.append(values)
    device.log = _Log()

    def fake_run(schedule, name, minute):
        d = _FakeDeferred()
        device.runs.append((name, minute))
        device.pending.append(d)
        return d
    device._schedule_run = fake_run
    return device


def _schedule(device, minutes, until, final_run=True, continuous=False, elapsed_min=0.0):
    schedule = device._schedule = gc._Schedule("26175", ["Kolbe"], minutes, 5, "/tmp/x", continuous=continuous,
                                               until_minutes=until, final_run=final_run)
    schedule.t0 = time.time() - 60.0 * elapsed_min
    return schedule


def _finish_next(device):
    device.pending.pop(0).finish(None)


def _finished(device):
    return {gc.SCHEDULE_OBSERVABLE: "finished"} in device.updates


class ScheduleFlagTests(unittest.TestCase):
    def test_flags(self):
        s = gc._Schedule("x", [], [0, 10], 5, "/tmp/x", until_minutes=30, final_run=True)
        self.assertTrue(s.final_run)
        self.assertFalse(s.final_done)
        self.assertTrue(s.is_open())

    def test_no_final_run_when_a_planned_point_is_at_or_after_the_end(self):
        s = gc._Schedule("x", [], [0, 10, 30], 5, "/tmp/x", until_minutes=30, final_run=True)
        self.assertFalse(s.final_run)
        self.assertTrue(s.final_done)

    def test_no_final_run_without_until(self):
        s = gc._Schedule("x", [], [0, 10], 5, "/tmp/x", until_minutes=None, final_run=True)
        self.assertFalse(s.final_run)

    def test_not_requested(self):
        s = gc._Schedule("x", [], [0, 10], 5, "/tmp/x", until_minutes=30, final_run=False)
        self.assertFalse(s.final_run)
        self.assertTrue(s.final_done)

    def test_truthy(self):
        for value in (True, "true", "True", "ja", "1", "yes"):
            self.assertTrue(gc._truthy(value), value)
        for value in (False, "false", "", None, "0", "nein"):
            self.assertFalse(gc._truthy(value), value)


class FinalRunTests(unittest.TestCase):
    def test_waits_for_the_end_then_runs_exactly_once(self):
        """Plan 0;10 min, Elektrolyse 30 min: beide Laeufe sind lange vor dem Ende fertig -> der Plan
        bleibt offen, bei 30 min kommt die Abschlussmessung, danach finished. Keine weitere."""
        device = _device()
        schedule = _schedule(device, [0, 10], until=30)
        device._schedule_due(schedule, 0)
        _finish_next(device)
        device._schedule_due(schedule, 10)
        _finish_next(device)
        self.assertEqual([r[0] for r in device.runs], ["26175_0 min", "26175_10 min"])
        self.assertEqual(schedule.remaining, 0)
        self.assertFalse(_finished(device))
        self.assertTrue(schedule.is_open())

        schedule.t0 = time.time() - 60.0 * 30.2     # Elektrolyse zu Ende, Timer feuert
        device._schedule_final_due(schedule)
        self.assertEqual(len(device.runs), 3)
        self.assertTrue(device.runs[2][0].startswith("26175_Ende 30"), device.runs[2][0])
        self.assertTrue(schedule.final_done)
        _finish_next(device)
        self.assertTrue(_finished(device))
        self.assertEqual(schedule.done, 3)
        self.assertFalse(schedule.is_open())
        self.assertEqual(len(device.runs), 3)

    def test_waits_for_a_still_running_planned_run(self):
        """Der letzte planmaessige Lauf (25 min) laeuft noch, als die Elektrolyse (30 min) endet:
        erst dessen Ende abwarten, dann die Abschlussmessung."""
        device = _device()
        schedule = _schedule(device, [0, 25], until=30)
        device._schedule_due(schedule, 0)
        _finish_next(device)
        device._schedule_due(schedule, 25)
        self.assertEqual(schedule.active, 25)
        device._schedule_final_due(schedule)
        self.assertEqual(len(device.runs), 2)           # noch kein Ende-Lauf
        _finish_next(device)                            # 25-min-Lauf fertig
        self.assertEqual(len(device.runs), 3)
        self.assertTrue(device.runs[2][0].startswith("26175_Ende"))
        _finish_next(device)
        self.assertTrue(_finished(device))

    def test_overdue_planned_run_still_comes_before_the_final_run(self):
        """Ende waehrend ein planmaessiger Lauf noch in der Warteschlange steht (ueberfaellig):
        erst der, dann die Abschlussmessung."""
        device = _device()
        schedule = _schedule(device, [0, 28], until=30)
        device._schedule_due(schedule, 0)               # laeuft lange
        device._schedule_due(schedule, 28)              # wartet in due
        device._schedule_final_due(schedule)
        _finish_next(device)                            # 0-min-Lauf fertig -> 28-min-Lauf startet
        self.assertEqual(device.runs[1][0], "26175_28 min")
        _finish_next(device)                            # -> Abschlussmessung
        self.assertTrue(device.runs[2][0].startswith("26175_Ende"))
        _finish_next(device)
        self.assertTrue(_finished(device))
        self.assertEqual(len(device.runs), 3)

    def test_no_final_run_when_plan_ends_at_until(self):
        device = _device()
        schedule = _schedule(device, [0, 30], until=30)
        self.assertFalse(schedule.final_run)
        device._schedule_due(schedule, 0)
        _finish_next(device)
        device._schedule_due(schedule, 30)
        _finish_next(device)
        self.assertEqual(len(device.runs), 2)
        self.assertTrue(_finished(device))

    def test_without_final_run_as_before(self):
        device = _device()
        schedule = _schedule(device, [0, 10], until=30, final_run=False)
        device._schedule_due(schedule, 0)
        _finish_next(device)
        device._schedule_due(schedule, 10)
        _finish_next(device)
        self.assertEqual(len(device.runs), 2)
        self.assertTrue(_finished(device))

    def test_failed_planned_run_does_not_block_the_final_run(self):
        device = _device()
        schedule = _schedule(device, [0], until=30)
        device._schedule_due(schedule, 0)
        from twisted.python import failure
        device.pending.pop(0).finish(failure.Failure(RuntimeError("Geraetefehler")))
        self.assertEqual(schedule.failed, 1)
        device._schedule_final_due(schedule)
        self.assertEqual(len(device.runs), 2)
        _finish_next(device)
        self.assertTrue(_finished(device))

    def test_continuous_mode_adds_one_final_run_after_the_end(self):
        """Dauermessung bis 1 min: Laeufe solange elapsed < until; danach genau eine Abschlussmessung."""
        device = _device()
        schedule = _schedule(device, [], until=1, continuous=True)
        device._schedule_next(schedule)                 # erster Dauerlauf
        self.assertEqual(len(device.runs), 1)
        schedule.t0 = time.time() - 60.0 * 1.5          # Ende vorbei, Lauf laeuft noch
        device._schedule_final_due(schedule)
        self.assertEqual(len(device.runs), 1)
        _finish_next(device)                            # Dauerlauf fertig -> Abschlussmessung
        self.assertEqual(len(device.runs), 2)
        self.assertTrue(device.runs[1][0].startswith("26175_Ende"))
        _finish_next(device)
        self.assertEqual(len(device.runs), 2)
        self.assertTrue(_finished(device))

    def test_continuous_mode_final_run_even_if_timer_came_late(self):
        """Letzter Dauerlauf endet nach until, bevor der Ende-Timer gefeuert hat: trotzdem genau
        eine Abschlussmessung, keine zweite durch den Timer."""
        device = _device()
        schedule = _schedule(device, [], until=1, continuous=True)
        device._schedule_next(schedule)
        schedule.t0 = time.time() - 60.0 * 1.5
        _finish_next(device)                            # -> Abschlussmessung ohne Timer
        self.assertEqual(len(device.runs), 2)
        device._schedule_final_due(schedule)            # Timer kommt spaeter
        _finish_next(device)
        device._schedule_final_due(schedule)
        self.assertEqual(len(device.runs), 2)
        self.assertTrue(_finished(device))

    def test_cancel_while_waiting_for_the_final_run(self):
        """Stop zwischen letztem planmaessigem Lauf und Abschlussmessung: Plan gilt als offen, wird
        abgebrochen, der Ende-Timer gestoppt, nichts startet mehr."""
        device = _device()
        schedule = _schedule(device, [0], until=30)
        device._schedule_due(schedule, 0)
        _finish_next(device)
        timer = _FakeTimer()
        schedule.timers = [timer]
        device._cancel_schedule("stop")
        self.assertTrue(schedule.cancelled)
        self.assertTrue(timer.cancelled)
        self.assertIn({gc.SCHEDULE_OBSERVABLE: "cancelled"}, device.updates)
        device._schedule_final_due(schedule)
        self.assertEqual(len(device.runs), 1)

    def test_cancel_after_regular_end_is_silent(self):
        device = _device()
        schedule = _schedule(device, [0], until=30)
        device._schedule_due(schedule, 0)
        _finish_next(device)
        device._schedule_final_due(schedule)
        _finish_next(device)
        self.assertTrue(_finished(device))
        device.updates.clear()
        device._cancel_schedule("stop")
        self.assertFalse(schedule.cancelled)
        self.assertEqual(device.updates, [])
