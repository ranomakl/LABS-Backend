# -*- test-case-name: backend.test.test_gashandling -*-
"""Gashandling (19.11.2026, docs/gashandling_19-11-2026.txt): Geraet `gashandler` und die Routinen
gas_spuelung / gas_messweg in config.yml und config.dummy.yml. Prueft ohne Geraete:
- jeder Befehl der Routinen zeigt auf ein Geraet der Config und auf eine Methode des Treibers,
- jeder {Platzhalter} ist ein Parameter der Routine,
- der Gashandler ist wie ventil_z1-3 eingestellt (Low-Active-Platine, safe_state A) und nutzt einen Pin,
  den kein anderes Relais hat,
- der simulierte Gashandler-Pin ist in A losgelassen und in B auf Masse (Relais an).
Lauf: python -m twisted.trial backend.test.test_gashandling"""
import importlib
import re
from pathlib import Path

import yaml
from twisted.trial import unittest

from backend.drivers.relay_3_2_valve_base import build_output_pin

ROOT = Path(__file__).resolve().parents[2]
ROUTINEN = ("gas_spuelung", "gas_messweg")


def _config(name):
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


class GashandlingConfigTests(unittest.TestCase):
    def _pruefe_routinen(self, config):
        devices, experiments = config["devices"], config["experiments"]
        for name in ROUTINEN:
            self.assertIn(name, experiments)
            routine = experiments[name]
            parameter = set((routine.get("parameters") or {}).keys())
            for device, method, args, kwargs in routine["commands"]:
                self.assertIn(device, devices, f"{name}: Geraet {device} fehlt")
                driver = importlib.import_module(f"backend.drivers.{devices[device]['driver']}")
                self.assertTrue(callable(getattr(driver.Device, method, None)),
                                f"{name}: {device}.{method} gibt es im Treiber nicht")
                for wert in list(args) + list(kwargs.values()):
                    for platzhalter in re.findall(r"\{(\w+)\}", str(wert)):
                        self.assertIn(platzhalter, parameter, f"{name}: Platzhalter {platzhalter} ohne Parameter")
            for device, observable, _typ, _einheit in routine["observables"]:
                self.assertIn(device, devices, f"{name}: Observable-Geraet {device} fehlt")

    def _pruefe_gashandler(self, config):
        devices = config["devices"]
        g = devices["gashandler"]
        self.assertEqual(g["driver"], "raspi_gpio_relay_valve")
        self.assertTrue(g["inverted"])
        self.assertTrue(g["release_when_off"])
        self.assertEqual(g["safe_state"], "A")
        andere = [d["pin"] for n, d in devices.items() if n != "gashandler" and d.get("driver") == "raspi_gpio_relay_valve"]
        self.assertNotIn(g["pin"], andere, "Gashandler-Pin ist schon von einem anderen Relais belegt")

    def test_config_yml(self):
        config = _config("config.yml")
        self._pruefe_gashandler(config)
        self._pruefe_routinen(config)

    def test_config_dummy_yml(self):
        config = _config("config.dummy.yml")
        self._pruefe_gashandler(config)
        self.assertTrue(config["devices"]["gashandler"].get("simulate"), "Dummy-Config braucht simulate: true")
        self._pruefe_routinen(config)

    def test_spuelung_haelt_spuelweg_so_lange_wie_gespuelt_wird(self):
        # Das Routinenende stellt das Relais auf safe_state A. Damit der Spuelweg waehrend der ganzen Spuelung
        # offen bleibt, muss der Gashandler mit hold_position ueber `minutes` gehalten werden, nicht set_position.
        routine = _config("config.yml")["experiments"]["gas_spuelung"]
        relais = [c for c in routine["commands"] if c[0] == "gashandler"]
        self.assertEqual(len(relais), 1)
        self.assertEqual(relais[0][1], "hold_position")
        self.assertEqual(relais[0][3], {"position": "B", "minutes": "{minutes}"})
        pumpe = [c for c in routine["commands"] if c[0] == "dosing_pump"]
        self.assertEqual(pumpe[0][3]["minutes"], "{minutes}")

    def test_messweg_oeffnet_mfc_und_stellt_auf_a(self):
        routine = _config("config.yml")["experiments"]["gas_messweg"]
        befehle = [(c[0], c[1]) for c in routine["commands"]]
        self.assertIn(("gashandler", "set_position"), befehle)
        self.assertIn(("mfc1", "reset_counter"), befehle)
        self.assertIn(("mfc1", "open_valve"), befehle)
        self.assertEqual([c[3] for c in routine["commands"] if c[0] == "gashandler"], [{"position": "A"}])
        self.assertFalse(routine.get("parameters"))

    def test_simulierter_gashandler_pin(self):
        g = _config("config.yml")["devices"]["gashandler"]
        pin = build_output_pin(g["pin"], inverted=g["inverted"], initial_position=g["safe_state"], simulate=True,
                               release_when_off=g["release_when_off"])
        self.addCleanup(pin.close)
        self.assertEqual(pin.pin.function, "input")      # A = Messweg = losgelassen = Relais aus
        pin.on()
        self.assertEqual(pin.pin.function, "output")     # B = Spuelweg = Masse = Relais an
        self.assertEqual(pin.pin.state, 0)
        pin.off()
        self.assertEqual(pin.pin.function, "input")
