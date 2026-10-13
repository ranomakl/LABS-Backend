# 13.10.2026 (Versuch 26175, 15:44-15:50): Nach "Stop Experiments" blieb die Bedingung "Devices stopped
# by <Lauf>" im ConditionHandler liegen; beim Ende des naechsten Laufs feuerte sie statt der eigenen,
# der neue Lauf blieb fuer immer Running. Zwei Sicherungen:
#   1. DevicesStateEqualsCondition markiert "schon ausgeloest" pro Bedingung (zwei Bedingungen auf
#      denselben Geraeten feuern beide).
#   2. Experiment.finish_experiment entfernt seine eigene, noch offene Stoppbedingung.
# Aufruf: .venv/bin/python -m twisted.trial backend.test.test_stoppbedingung_leiche
from twisted.internet import defer
from twisted.trial import unittest

from backend.conditions.conditionhandler import ConditionHandler
from backend.conditions.conditions import DevicesStateEqualsCondition
from backend.devices import devicestate
from backend.experiments.experiment import Experiment
from backend.experiments import experimentstates


class FakeDevice:
    def __init__(self, name):
        self.log_name = name
        self.stateobject = devicestate.Ready(self)
        self.observers = []

    @property
    def state(self):
        return type(self.stateobject)

    @state.setter
    def state(self, stateclass):
        self.stateobject = stateclass(self)
        for observer in list(self.observers):
            observer.update(self, "state", stateclass.__name__, 0.0)

    def subscribe(self, observer): self.observers.append(observer)
    def unsubscribe(self, observer):
        if observer in self.observers: self.observers.remove(observer)
    def stop(self): return defer.Deferred()
    def wait(self, condition): raise AssertionError("nicht erwartet")


class FakeSetup:
    def __init__(self):
        self.conditionhandler = ConditionHandler()
        self.config = {"log_level": "warn"}


class FakeFactory:
    def __init__(self):
        self.setup = FakeSetup()
        self.experiment_observable_details = []


def _experiment(factory, devices, name):
    return Experiment(factory, [], name, devices, {}, [], name, [])


class ZweiBedingungenTest(unittest.TestCase):
    def test_zwei_bedingungen_auf_denselben_geraeten_feuern_beide(self):
        d1, d2 = FakeDevice("a"), FakeDevice("b")
        handler = ConditionHandler()
        alt = handler.add_condition(DevicesStateEqualsCondition("alt", [d1, d2], devicestate.Stopped))
        neu = handler.add_condition(DevicesStateEqualsCondition("neu", [d1, d2], devicestate.Stopped))
        d1.state = devicestate.Stopped
        d2.state = devicestate.Stopped
        self.assertTrue(alt.called)
        self.assertTrue(neu.called, "zweite Bedingung wurde von der ersten blockiert")
        self.assertEqual(handler._conditions, {})


class StopHinterlaesstKeineLeicheTest(unittest.TestCase):
    def test_manueller_stop_raeumt_bedingung_auf_und_naechster_lauf_endet(self):
        factory = FakeFactory()
        handler = factory.setup.conditionhandler
        d1, d2 = FakeDevice("mfc"), FakeDevice("pumpe")
        devices = {"mfc": d1, "pumpe": d2}

        erster = _experiment(factory, devices, "erster")
        erster.state = experimentstates.Running
        erster.state = experimentstates.Stopped          # wie Setup.remote_stop
        self.assertEqual(handler._conditions, {}, "Stoppbedingung des gestoppten Laufs liegt noch im Handler")

        zweiter = _experiment(factory, devices, "zweiter")
        zweiter.state = experimentstates.Running
        fertig = zweiter._stop_devices(None)             # wie _commands_finished am Laufende
        fertig.addCallback(zweiter.set_state, experimentstates.Finished)
        d1.state = devicestate.Stopped
        d2.state = devicestate.Stopped
        self.assertTrue(fertig.called, "Laufende nicht erkannt")
        self.assertEqual(type(zweiter.stateobject), experimentstates.Finished)
        self.assertEqual(handler._conditions, {})
