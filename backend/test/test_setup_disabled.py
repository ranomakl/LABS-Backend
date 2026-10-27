# Prueft, dass Setup mit deaktivierten (enabled: false) und nicht erreichbaren Geraeten trotzdem
# startet (Zustand Paused) und nur die Experimente behaelt, deren Geraete verfuegbar sind.
# Aufruf: .venv/bin/python -m twisted.trial backend.test.test_setup_disabled
from twisted.internet import defer, reactor, task
from twisted.trial import unittest

from backend.setup.setup import Setup
from backend.setup import setupstates

CONFIG = {
    "listen port": 0, "destination port": 0, "log_level": "warn",
    "devices": {
        "aus": {"driver": "endress_hauser_liquiline", "address": "127.0.0.1:12353", "enabled": False},
        # Port 1 auf localhost: Verbindung wird sofort abgelehnt
        "tot": {"driver": "endress_hauser_liquiline", "address": "127.0.0.1:1"},
    },
    "experiments": {
        "braucht_aus": {"conditions": None, "stopconditions": None, "parameters": None,
                        "observables": [["aus", "ph_value", "float", "pH"]],
                        "commands": [["aus", "read_channel", [], {"channel": "ph"}]]},
        "braucht_tot": {"conditions": None, "stopconditions": None, "parameters": None, "observables": None,
                        "commands": [["tot", "read_all_channels", [], {}]]},
        "verschachtelt": {"conditions": None, "stopconditions": None, "parameters": None, "observables": None,
                          "commands": [["braucht_aus", {}]]},
    },
}


class SetupDisabledDevicesTest(unittest.TestCase):
    def setUp(self):
        Setup.listenTCP = staticmethod(lambda port, factory: None)   # kein echter Frontend-Port im Test

    @defer.inlineCallbacks
    def test_start_ohne_verfuegbare_geraete(self):
        setup = Setup(CONFIG)
        yield task.deferLater(reactor, 0.5, lambda: None)   # Verbindungsversuch auf Port 1 scheitert sofort
        self.assertIs(setup.state, setupstates.Paused)
        self.assertEqual(setup.disabled_devices, ["aus"])
        self.assertEqual(setup.experimentfactories, {})
        self.assertEqual(setup.skipped_experiments, {
            "braucht_aus": ["Geraet aus"],
            "braucht_tot": ["Geraet tot"],
            "verschachtelt": ["Experiment braucht_aus"],
        })

    @defer.inlineCallbacks
    def test_device_states_fuer_statusfenster(self):
        # 27.10.2026: /api/device_states listet ALLE Geraete aus der Config, auch die nicht verbundenen.
        setup = Setup(CONFIG)
        yield task.deferLater(reactor, 0.5, lambda: None)
        states = setup.remote_device_states()
        self.assertEqual([s["name"] for s in states], ["aus", "tot"])
        aus, tot = states
        self.assertFalse(aus["ok"])
        self.assertEqual(aus["state"], "deaktiviert")
        self.assertFalse(tot["ok"])
        self.assertEqual(tot["state"], "nicht verbunden")
        self.assertTrue(tot["reason"])                      # Fehlertext vorhanden
        self.assertEqual(tot["address"], "127.0.0.1:1")
        self.assertEqual(setup.unavailable_devices.keys(), {"tot"})
