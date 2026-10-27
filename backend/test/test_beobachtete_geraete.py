# 27.10.2026: Geraete, die ein Experiment nur unter observables fuehrt (kein eigener Befehl, z.B. die
# GC-Ventile in kolbe_elektrolyse_3x), werden mitbeobachtet (Updates landen in observed_updates ->
# values.json), zaehlen aber nicht zu den Befehlsgeraeten (devices_and_channels: stop/wait).
# Aufruf: .venv/bin/python -m twisted.trial backend.test.test_beobachtete_geraete
from twisted.trial import unittest

from backend.experiments.experimentfactory import ExperimentFactory


class FakeDevice:
    def __init__(self):
        self.subscribers = []
    def subscribe(self, observer): self.subscribers.append(observer)
    def unsubscribe(self, observer): self.subscribers.remove(observer)
    def befehl(self, **kwargs): pass


class FakeSetup:
    def __init__(self, devices):
        self.devices_and_channels = devices
        self.experimentfactories = {}
        self.config = {"log_level": "warn"}


CONFIG = {"conditions": None, "stopconditions": None, "parameters": None,
          "observables": [["befehlsgeraet", "wert", "float", ""], ["ventil", "position", "str", ""]],
          "commands": [["befehlsgeraet", "befehl", [], {}]]}


class BeobachteteGeraeteTest(unittest.TestCase):
    def setUp(self):
        self.befehlsgeraet, self.ventil = FakeDevice(), FakeDevice()
        self.setup = FakeSetup({"befehlsgeraet": self.befehlsgeraet, "ventil": self.ventil})
        self.factory = ExperimentFactory(self.setup, CONFIG, "test")

    def test_factory_trennt_befehls_und_beobachtungsgeraete(self):
        self.assertEqual(self.factory.devices_and_channels, {"befehlsgeraet": self.befehlsgeraet})
        self.assertEqual(self.factory.observed_only_devices, {"ventil": self.ventil})

    def test_experiment_zeichnet_beobachtete_geraete_auf(self):
        exp = self.factory.get_experiment("lauf1")
        self.assertEqual(exp.devices_and_channels, {"befehlsgeraet": self.befehlsgeraet})   # stop/wait nur hier
        self.assertEqual(set(exp.observed_devices), {"befehlsgeraet", "ventil"})
        exp.update(self.ventil, "position", "B", 12.5)
        self.assertEqual(exp.observed_updates["ventil"]["position"], [(12.5, "B")])

    def test_abonnieren_ueber_observed_devices(self):
        exp = self.factory.get_experiment("lauf2")
        for device in exp.observed_devices.values():   # wie experimentstates.Running.enter
            device.subscribe(exp)
        self.assertEqual(self.ventil.subscribers, [exp])
        self.assertEqual(self.befehlsgeraet.subscribers, [exp])
