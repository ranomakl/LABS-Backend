# Schrittmodus (config step_mode, 13.10.2026): nach jedem fertigen Experiment Paused, naechstes nur per
# start(); Senden startet nie; leere Schlange bei start() -> Paused. Ohne step_mode: wie bisher.
# Aufruf: .venv/bin/python -m twisted.trial backend.test.test_schrittmodus
from twisted.internet import defer, reactor, task
from twisted.trial import unittest

from backend.setup.setup import Setup
from backend.setup import setupstates


class FakeExperiment:
    def __init__(self, experiment_id):
        self.id = experiment_id
        self.deferred = defer.Deferred()
        self.parameters = {}
        self.starting_time = 0
        self.executed = False

    def subscribe(self, observer): pass
    def unsubscribe(self, observer): pass

    def execute(self):
        self.executed = True
        return self.deferred


class FakeFactory:
    def __init__(self, store): self.store = store
    def get_experiment(self, experiment_id, **kwargs):
        exp = self.store[experiment_id] = FakeExperiment(experiment_id)
        return exp


def _config(step_mode):
    return {"listen port": 0, "destination port": 0, "log_level": "warn", "step_mode": step_mode,
            "devices": {}, "experiments": {}}


class _Base(unittest.TestCase):
    step_mode = True

    @defer.inlineCallbacks
    def setUp(self):
        Setup.listenTCP = staticmethod(lambda port, factory: None)
        self.setup = Setup(_config(self.step_mode))
        yield task.deferLater(reactor, 0.05, lambda: None)
        self.assertIs(self.setup.state, setupstates.Paused)
        self.created = {}
        self.setup.experimentfactories["fake"] = FakeFactory(self.created)

    def add(self, name):
        self.setup.add_experiment(name, "fake")
        return self.created[name]

    def overview(self):
        return self.setup.remote_station_overview()


class SchrittmodusTest(_Base):
    step_mode = True

    def test_senden_startet_nichts_und_knopf_startet_einen_schritt(self):
        a, b = self.add("a"), self.add("b")
        self.assertIs(self.setup.state, setupstates.Paused)
        self.assertFalse(a.executed)
        self.assertEqual(self.overview()["next_experiment_name"], "a")
        self.assertEqual(self.overview()["finished_runs"], 0)

        self.setup.start()
        self.assertIs(self.setup.state, setupstates.Busy)
        self.assertTrue(a.executed); self.assertFalse(b.executed)
        self.assertEqual(self.overview()["running_experiment_name"], "a")
        self.assertEqual(self.overview()["current_run_number"], 1)

        a.deferred.callback(None)
        self.assertIs(self.setup.state, setupstates.Paused)
        self.assertFalse(b.executed)                      # nicht von selbst weiter
        self.assertIsNone(self.setup.current_experiment)  # Paused meldet kein laufendes Experiment
        ov = self.overview()
        self.assertEqual((ov["running_experiment_name"], ov["finished_runs"], ov["next_experiment_name"],
                          ov["step_mode"]), ("", 1, "b", True))

        self.setup.start()
        self.assertTrue(b.executed)
        b.deferred.callback(None)
        self.assertIs(self.setup.state, setupstates.Paused)
        self.assertEqual(self.overview()["finished_runs"], 2)
        self.assertEqual(self.overview()["next_experiment_name"], "")

    def test_start_mit_leerer_schlange_bleibt_paused_und_senden_startet_nicht(self):
        self.setup.start()                                # nichts in der Schlange
        self.assertIs(self.setup.state, setupstates.Paused)
        c = self.add("c")
        self.assertFalse(c.executed)                      # die alte Falle: frueher sofortiger Start
        self.setup.start()
        self.assertTrue(c.executed)

    def test_senden_waehrend_ein_schritt_laeuft_reiht_nur_ein(self):
        a = self.add("a"); self.setup.start()
        b = self.add("b")
        self.assertFalse(b.executed)
        a.deferred.callback(None)
        self.assertIs(self.setup.state, setupstates.Paused)
        self.assertFalse(b.executed)

    def test_fehlgeschlagenes_experiment_bleibt_failed(self):
        a = self.add("a"); self.setup.start()
        a.deferred.errback(RuntimeError("kaputt"))
        self.assertIs(self.setup.state, setupstates.Failed)


class OhneSchrittmodusTest(_Base):
    step_mode = False

    def test_verhalten_wie_bisher(self):
        a, b = self.add("a"), self.add("b")
        self.setup.start()
        self.assertTrue(a.executed)
        a.deferred.callback(None)
        self.assertTrue(b.executed)                       # laeuft von selbst weiter
        self.assertIs(self.setup.state, setupstates.Busy)
        b.deferred.callback(None)
        self.assertIs(self.setup.state, setupstates.Ready)
        self.assertEqual(self.overview()["step_mode"], False)
        c = self.add("c")
        self.assertTrue(c.executed)                       # die bekannte Falle, unveraendert ohne step_mode


class UnbekannterTypTest(_Base):
    step_mode = True

    def test_unbekannter_typ_hinterlaesst_keine_leiche_in_der_schlange(self):
        self.assertRaises(setupstates.SetupStateError, self.setup.add_experiment, "x", "gibt_es_nicht")
        self.assertEqual(self.setup.experiment_id_order, [])
        a = self.add("a"); self.setup.start()
        self.assertTrue(a.executed)
