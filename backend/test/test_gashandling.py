# -*- test-case-name: backend.test.test_gashandling -*-
"""Gashandling an Messstand II (docs/gashandling_19-11-2026.txt): Geraete mfc2, gashandler, lowflow_pumpe, ventil_waste
und die Routinen gas_spuelung / gas_messweg / gc_messung in config.messstand2.yml und config.messstand2.dummy.yml.
Am 19.11.2026 zuerst in config.yml (Messstand I) gebaut, am 25.11.2026 nach Messstand II umgezogen und aus den
Messstand-I-Configs entfernt. Prueft ohne Geraete:
- jeder Befehl der Routinen zeigt auf ein Geraet der Config und auf eine Methode des Treibers,
- jeder {Platzhalter} ist ein Parameter der Routine,
- die drei Relais haben die Pins der Pinbelegung Messstand II, eindeutig, safe_state A, kein release_when_off
  (neue Platine ohne 5-V-Problem), Relaismodule Low-Active, Pumpeneingang nicht invertiert,
- die simulierten Pins schalten richtig herum,
- Messstand I (config.yml, config.dummy.yml) enthaelt kein Gashandling mehr, mfc2 ist dort deaktiviert.
Lauf: python -m twisted.trial backend.test.test_gashandling"""
import importlib
import re
from pathlib import Path

import yaml
from twisted.trial import unittest

from backend.drivers.relay_3_2_valve_base import build_output_pin

ROOT = Path(__file__).resolve().parents[2]
ROUTINEN = ("gas_spuelung", "gas_messweg", "gc_messung")
CONFIGS = ("config.messstand2.yml", "config.messstand2.dummy.yml")
RELAIS = {"gashandler": 27, "lowflow_pumpe": 17, "ventil_waste": 22}   # Pinbelegung Messstand II 25.11.2026
# Relaismodule sind Low-Active (Pin Low = an). Die Low-Flow-Pumpe nicht: ihr Pin las am 25.11. Low bei
# ausgeschalteter Pumpe -> inverted: false, sonst liefe sie ab Backend-Start (safe_state A = Pin High).
# Am Geraet bestaetigt 25.11. 16:03: Relais klickt, Pumpe laeuft nur waehrend gas_spuelung.
INVERTED = {"gashandler": True, "lowflow_pumpe": False, "ventil_waste": True}
HALTEN = {"position": "B", "minutes": "{minutes}"}


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

    def _pruefe_relais(self, config):
        devices = config["devices"]
        for name, pin in RELAIS.items():
            d = devices[name]
            self.assertEqual(d["driver"], "raspi_gpio_relay_valve", name)
            self.assertEqual(d["pin"], pin, name)
            self.assertEqual(d["address"], f"GPIO{pin}", name)
            self.assertIs(d["inverted"], INVERTED[name], name)
            self.assertNotIn("release_when_off", d, f"{name}: neue Platine ohne 5-V-Problem")
            self.assertEqual(d["safe_state"], "A", name)                       # A = Relais aus = spannungslos
        pins = [d["pin"] for d in devices.values() if d.get("driver") == "raspi_gpio_relay_valve"]
        self.assertEqual(len(pins), len(set(pins)), "ein GPIO-Pin ist doppelt belegt")

    def test_config_messstand2_yml(self):
        config = _config("config.messstand2.yml")
        self._pruefe_relais(config)
        self._pruefe_routinen(config)
        devices = config["devices"]
        for name in RELAIS:
            self.assertFalse(devices[name].get("simulate"), f"echte Config darf {name} nicht simulieren")
        # Bronkhorst "2" von Messstand I, am 25.11.2026 am Pi 2 lesend bestaetigt (M18212352C, 50 mln/min, Knoten 03)
        mfc = devices["mfc2"]
        self.assertEqual(mfc["address"], "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BG01B1W6-if00-port0")
        self.assertEqual((mfc["node"], mfc["max_flow_ml_min"], mfc["serial_parameters"]["baudrate"]), ("03", 50.0, 38400))
        self.assertNotIn("enabled", mfc)
        self.assertNotIn("mfc1", devices)
        # microGC bleibt deaktiviert, bis eth0 am Pi 2 die Link-Local-Adresse hat
        self.assertIs(devices["microgc"].get("enabled"), False)
        self.assertEqual(devices["microgc"]["address"], "169.254.1.1")       # derselbe GC wie an Messstand I
        self.assertNotIn("streams", devices["microgc"])                       # ein Gasstrom, keine Zellenventile

    def test_config_messstand2_dummy_yml(self):
        config = _config("config.messstand2.dummy.yml")
        self._pruefe_relais(config)
        for name in RELAIS:
            self.assertTrue(config["devices"][name].get("simulate"), f"Dummy-Config braucht simulate: true ({name})")
        self._pruefe_routinen(config)
        for name in ("mfc2", "microgc"):
            self.assertTrue(config["devices"][name]["address"].startswith("127.0.0.1:"), name)
            self.assertNotIn("enabled", config["devices"][name])
        # Routinen in beiden Messstand-II-Configs identisch
        real = _config("config.messstand2.yml")["experiments"]
        for name in ROUTINEN:
            self.assertEqual(config["experiments"][name], real[name], name)

    def test_spuelung_haelt_spuelweg_und_pumpe_so_lange_wie_gespuelt_wird(self):
        # Das Routinenende stellt die Relais auf safe_state A. Damit Spuelweg und Pumpe waehrend der ganzen Spuelung
        # an bleiben, werden beide mit hold_position ueber `minutes` gehalten, nicht mit set_position.
        # Bronkhorst: Zaehler 0, Setpoint gasrate, messen - KEIN "Setpoint 0" am Ende mehr (Rafael 25.11.2026:
        # darf offen bleiben; das Routinenende oeffnet ihn ohnehin ganz). pump1 laeuft nicht mit, kein `rate`.
        spuelung = _config("config.messstand2.yml")["experiments"]["gas_spuelung"]
        self.assertEqual(set(spuelung["parameters"]), {"gasrate", "minutes"})
        self.assertEqual(spuelung["commands"], [
            ["gashandler", "hold_position", [], HALTEN],
            ["lowflow_pumpe", "hold_position", [], HALTEN],
            ["mfc2", "reset_counter", [], {}],
            ["mfc2", "set_setpoint", [], {"flow_ml_min": "{gasrate}"}],
            ["mfc2", "measure_for_minutes", [], {"minutes": "{minutes}"}],
        ])

    def test_messweg_oeffnet_mfc_und_stellt_auf_a(self):
        routine = _config("config.messstand2.yml")["experiments"]["gas_messweg"]
        self.assertFalse(routine.get("parameters"))
        self.assertEqual(routine["commands"], [
            ["gashandler", "set_position", [], {"position": "A"}],
            ["mfc2", "reset_counter", [], {}],
            ["mfc2", "open_valve", [], {}],
            ["mfc2", "read_setpoint", [], {}],
        ])

    def test_gc_messung(self):
        routine = _config("config.messstand2.yml")["experiments"]["gc_messung"]
        self.assertEqual(set(routine["parameters"]), {"method", "name", "tags"})
        self.assertEqual([c[:2] for c in routine["commands"]],
                         [["microgc", "load_method"], ["microgc", "run_method_named"], ["microgc", "get_last_run_data"]])

    def test_simulierte_relais_ohne_release(self):
        # Neue Platine: Relaismodule "aus" = Pin High (Ausgang), "an" = Pin Low; Low-Flow-Pumpe umgekehrt
        # (aus = Low, an = High). Kein Loslassen des Pins. Im sicheren Zustand A ist alles aus.
        for name, pin_nr in RELAIS.items():
            inverted = INVERTED[name]
            aus, an = (1, 0) if inverted else (0, 1)
            pin = build_output_pin(pin_nr, inverted=inverted, initial_position="A", simulate=True, release_when_off=False)
            self.addCleanup(pin.close)
            self.assertEqual(pin.pin.function, "output", name)
            self.assertEqual(pin.pin.state, aus, f"{name}: A = aus")
            pin.on()
            self.assertEqual(pin.pin.state, an, f"{name}: B = an")
            pin.off()
            self.assertEqual(pin.pin.state, aus, name)

    def test_messstand_i_ohne_gashandling_mfc2_deaktiviert(self):
        # 25.11.2026 (Rafael): Gashandling komplett aus Messstand I raus; mfc2 (Bronkhorst 2) haengt jetzt am Pi 2 und
        # bleibt in config.yml nur deaktiviert stehen. Die Dummy-Config behaelt mfc2 aktiv (Entwicklung ohne Geraete).
        for path in ("config.yml", "config.dummy.yml"):
            config = _config(path)
            self.assertNotIn("gashandler", config["devices"], path)
            for name in ("gas_spuelung", "gas_messweg"):
                self.assertNotIn(name, config["experiments"], path)
        self.assertIs(_config("config.yml")["devices"]["mfc2"].get("enabled"), False)
