# -*- test-case-name: backend.test.test_gashandling -*-
"""Gashandling (19.11.2026, docs/gashandling_19-11-2026.txt): Geraet `gashandler` und die Routinen
gas_spuelung / gas_messweg in config.yml und config.dummy.yml (Messstand I) sowie - seit dem Umzug am 25.11.2026 -
in config.messstand2.yml und config.messstand2.dummy.yml (Messstand II, dort zusaetzlich gc_messung). Prueft ohne Geraete:
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
ROUTINEN_M2 = ROUTINEN + ("gc_messung",)


def _config(name):
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


class GashandlingConfigTests(unittest.TestCase):
    def _pruefe_routinen(self, config, routinen=ROUTINEN):
        devices, experiments = config["devices"], config["experiments"]
        for name in routinen:
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

    def _pruefe_gashandler(self, config, release_when_off=True):
        devices = config["devices"]
        g = devices["gashandler"]
        self.assertEqual(g["driver"], "raspi_gpio_relay_valve")
        self.assertTrue(g["inverted"])
        # Messstand I: alte Platine mit 5-V-Steuerseite -> release_when_off. Messstand II (25.11.2026): neue Platine
        # ohne dieses Problem -> kein release_when_off (Rafael).
        self.assertEqual(bool(g.get("release_when_off", False)), release_when_off)
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

    # ---- Messstand II (Umzug 25.11.2026) -------------------------------------------------------------------------

    RELAIS_M2 = {"gashandler": 27, "lowflow_pumpe": 17, "ventil_waste": 22}   # Pinbelegung Messstand II 25.11.2026
    # Relaismodule sind Low-Active (Pin Low = an). Die Low-Flow-Pumpe nicht: ihr Pin las am 25.11. Low bei
    # ausgeschalteter Pumpe -> inverted: false, sonst liefe sie ab Backend-Start (safe_state A = Pin High).
    INVERTED_M2 = {"gashandler": True, "lowflow_pumpe": False, "ventil_waste": True}

    def _pruefe_relais_messstand2(self, config):
        devices = config["devices"]
        for name, pin in self.RELAIS_M2.items():
            d = devices[name]
            self.assertEqual(d["driver"], "raspi_gpio_relay_valve", name)
            self.assertEqual(d["pin"], pin, name)
            self.assertEqual(d["address"], f"GPIO{pin}", name)
            self.assertIs(d["inverted"], self.INVERTED_M2[name], name)
            self.assertNotIn("release_when_off", d, f"{name}: neue Platine ohne 5-V-Problem")
            self.assertEqual(d["safe_state"], "A", name)                       # A = Relais aus = spannungslos

    def test_config_messstand2_yml(self):
        config = _config("config.messstand2.yml")
        self._pruefe_gashandler(config, release_when_off=False)
        self._pruefe_relais_messstand2(config)
        self._pruefe_routinen(config, ROUTINEN_M2)
        devices = config["devices"]
        for name in self.RELAIS_M2:
            self.assertFalse(devices[name].get("simulate"), f"echte Config darf {name} nicht simulieren")
        # Bronkhorst "2" von Messstand I, am 25.11.2026 am Pi 2 lesend bestaetigt (M18212352C, 50 mln/min, Knoten 03)
        mfc = devices["mfc2"]
        self.assertEqual(mfc["address"], "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BG01B1W6-if00-port0")
        self.assertEqual(mfc["address"], _config("config.yml")["devices"]["mfc2"]["address"])
        self.assertEqual((mfc["node"], mfc["max_flow_ml_min"], mfc["serial_parameters"]["baudrate"]), ("03", 50.0, 38400))
        self.assertNotIn("enabled", mfc)
        self.assertNotIn("mfc1", devices)
        # microGC bleibt deaktiviert, bis eth0 am Pi 2 die Link-Local-Adresse hat
        self.assertIs(devices["microgc"].get("enabled"), False)
        self.assertEqual(devices["microgc"]["address"], "169.254.1.1")       # derselbe GC wie an Messstand I
        self.assertNotIn("streams", devices["microgc"])                       # ein Gasstrom, keine Zellenventile

    def test_config_messstand2_dummy_yml(self):
        config = _config("config.messstand2.dummy.yml")
        self._pruefe_gashandler(config, release_when_off=False)
        self._pruefe_relais_messstand2(config)
        for name in self.RELAIS_M2:
            self.assertTrue(config["devices"][name].get("simulate"), f"Dummy-Config braucht simulate: true ({name})")
        self._pruefe_routinen(config, ROUTINEN_M2)
        for name in ("mfc2", "microgc"):
            self.assertTrue(config["devices"][name]["address"].startswith("127.0.0.1:"), name)
            self.assertNotIn("enabled", config["devices"][name])
        # Routinen in beiden Messstand-II-Configs identisch
        real = _config("config.messstand2.yml")["experiments"]
        for name in ROUTINEN_M2:
            self.assertEqual(config["experiments"][name], real[name], name)

    def test_messstand2_spuelung_mit_lowflow_pumpe_sonst_wie_messstand_i(self):
        # "Waehrenddessen Pumpe an" = Low-Flow-Pumpe am Relais GPIO 17 (Pinbelegung 25.11.2026), gehalten ueber
        # dieselben Minuten wie der Gashandler. pump1 (Dosierpumpe hinter dem 16-Wege-Ventil) laeuft nicht mit.
        config = _config("config.messstand2.yml")
        spuelung = config["experiments"]["gas_spuelung"]
        self.assertEqual({c[0] for c in spuelung["commands"]}, {"gashandler", "lowflow_pumpe", "mfc2"})
        self.assertNotIn("rate", spuelung["parameters"])
        halten = {"position": "B", "minutes": "{minutes}"}
        self.assertEqual([c for c in spuelung["commands"] if c[0] == "gashandler"], [["gashandler", "hold_position", [], halten]])
        self.assertEqual([c for c in spuelung["commands"] if c[0] == "lowflow_pumpe"], [["lowflow_pumpe", "hold_position", [], halten]])
        # Die Bronkhorst-Befehle sind wie an Messstand I (dort mfc1), nur ohne das abschliessende "Setpoint 0":
        # der Bronkhorst darf offen bleiben (Rafael 25.11.2026), das Routinenende oeffnet ihn sowieso wieder ganz.
        def ohne_geraet(commands, device):
            return [c[1:] for c in commands if c[0] == device]
        m1 = _config("config.yml")["experiments"]
        erwartet = [c for c in ohne_geraet(m1["gas_spuelung"]["commands"], "mfc1") if c != ["set_setpoint", [], {"flow_ml_min": 0}]]
        self.assertEqual(len(erwartet), 3)
        self.assertEqual(ohne_geraet(spuelung["commands"], "mfc2"), erwartet)
        self.assertNotIn(["mfc2", "set_setpoint", [], {"flow_ml_min": 0}], spuelung["commands"])
        messweg = config["experiments"]["gas_messweg"]["commands"]
        self.assertEqual([[("mfc2" if c[0] == "mfc1" else c[0])] + c[1:] for c in m1["gas_messweg"]["commands"]], messweg)
        self.assertEqual(config["experiments"]["gc_messung"]["commands"], m1["kolbe_gc_messung"]["commands"])

    def test_simulierte_relais_messstand2_ohne_release(self):
        # Neue Platine: Relaismodule "aus" = Pin High (Ausgang), "an" = Pin Low; Low-Flow-Pumpe umgekehrt
        # (aus = Low, an = High). Kein Loslassen des Pins. Im sicheren Zustand A ist alles aus.
        for name, pin_nr in self.RELAIS_M2.items():
            inverted = self.INVERTED_M2[name]
            aus, an = (1, 0) if inverted else (0, 1)
            pin = build_output_pin(pin_nr, inverted=inverted, initial_position="A", simulate=True, release_when_off=False)
            self.addCleanup(pin.close)
            self.assertEqual(pin.pin.function, "output", name)
            self.assertEqual(pin.pin.state, aus, f"{name}: A = aus")
            pin.on()
            self.assertEqual(pin.pin.state, an, f"{name}: B = an")
            pin.off()
            self.assertEqual(pin.pin.state, aus, name)

    # ---- Messstand I ----------------------------------------------------------------------------------------------

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
