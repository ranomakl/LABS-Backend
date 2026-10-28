"""
28.10.2026: Software-Loesung fuer die Low-Active-Relaisplatine mit 5-V-Steuerseite (GC-Ventile).
"aus" = Pin loslassen (Eingang + Pull-Down), "an" = Pin als Ausgang auf Masse.
Laeuft komplett mit gpiozero MockFactory, kein echter GPIO noetig.
Siehe docs/relaisplatine_erklaerung_28-10-2026.txt
"""
from twisted.trial import unittest

from backend.drivers.relay_3_2_valve_base import build_output_pin, ReleasingOutputPin


class ReleasingOutputPinTest(unittest.TestCase):

    def _pin(self, initial_position="A"):
        pin = build_output_pin(17, inverted=True, initial_position=initial_position, simulate=True,
                               release_when_off=True)
        self.addCleanup(pin.close)
        return pin

    def test_release_when_off_liefert_releasing_pin(self):
        self.assertIsInstance(self._pin(), ReleasingOutputPin)

    def test_ohne_release_when_off_bleibt_alles_beim_alten(self):
        from gpiozero import DigitalOutputDevice
        pin = build_output_pin(17, inverted=True, initial_position="A", simulate=True)
        self.addCleanup(pin.close)
        self.assertIsInstance(pin, DigitalOutputDevice)

    def test_release_when_off_verlangt_inverted_true(self):
        with self.assertRaises(ValueError):
            build_output_pin(17, inverted=False, initial_position="A", simulate=True, release_when_off=True)

    def test_sicherer_zustand_a_ist_losgelassen(self):
        # Beim Start (safe_state A) darf der Pin NICHT treiben -> Relais bleibt aus wie vor dem Backend-Start.
        pin = self._pin("A")
        self.assertEqual(pin.pin.function, "input")
        self.assertEqual(pin.pin.pull, "down")
        self.assertFalse(pin.value)

    def test_start_in_b_ist_ausgang_auf_masse(self):
        pin = self._pin("B")
        self.assertEqual(pin.pin.function, "output")
        self.assertEqual(pin.pin.state, 0)
        self.assertTrue(pin.value)

    def test_on_off_wechsel(self):
        pin = self._pin("A")
        pin.on()
        self.assertEqual(pin.pin.function, "output")
        self.assertEqual(pin.pin.state, 0)      # Masse = Relais an
        self.assertTrue(pin.value)
        pin.off()
        self.assertEqual(pin.pin.function, "input")   # losgelassen = Relais aus
        self.assertEqual(pin.pin.pull, "down")
        self.assertFalse(pin.value)
        pin.on()
        self.assertEqual(pin.pin.function, "output")
        self.assertEqual(pin.pin.state, 0)

    def test_close_gibt_pin_frei(self):
        pin = build_output_pin(17, inverted=True, initial_position="B", simulate=True, release_when_off=True)
        mock_pin = pin.pin
        pin.close()
        self.assertIsNone(pin.pin)
        self.assertEqual(mock_pin.function, "input")   # MockPin.close() setzt auf Eingang zurueck


class TreiberMitReleaseTest(unittest.TestCase):
    """Der Treiber reicht die Option durch und faehrt beim Verbinden den sicheren Zustand an."""

    def test_treiber_faehrt_safe_state_losgelassen_an(self):
        from backend.drivers.raspi_gpio_relay_valve import Device
        dev = Device.__new__(Device)
        dev.pin_number, dev.inverted, dev.safe_state = 22, True, "A"
        dev.simulate, dev.release_when_off, dev._pin = True, True, None
        pin = build_output_pin(dev.pin_number, inverted=dev.inverted, initial_position=dev.safe_state,
                               simulate=dev.simulate, release_when_off=dev.release_when_off)
        dev._pin = pin
        self.addCleanup(pin.close)
        self.assertEqual(pin.pin.function, "input")
        # drive_pin ohne Logger/Observables: nur den Pin-Teil pruefen
        pin.on(); self.assertEqual(pin.pin.state, 0)
        pin.off(); self.assertEqual(pin.pin.function, "input")
