# Tests fuer den Modbus-RTU-Treiber des Endress+Hauser Liquiline (backend/drivers/endress_hauser_liquiline.py),
# Stand 12.10.2026. Pruefvektoren stammen vom echten Geraet (Labor 12.10.2026) und aus der Modbus-Spezifikation.
# Aufruf: .venv/bin/python -m twisted.trial backend.test.test_liquiline_rtu
from twisted.trial import unittest

from backend.commands import commandstate
from backend.commands.results import Result
from backend.drivers.endress_hauser_liquiline import (_crc16, _build_request, expected_frame_length, _decode_float,
                                                      LiquilineParser, LiquilineProtocol, Device, _RawFrame)


def frame_with_crc(body_hex: str) -> bytes:
    body = bytes.fromhex(body_hex)
    return body + _crc16(body)


class CRCTest(unittest.TestCase):
    def test_geraeteantwort_12_10_2026(self):
        # dauertest_liquiline.py, RTU 19200/E/247: Antwort F7 03 02 00 00 70 51
        self.assertEqual(_crc16(bytes.fromhex("F703020000")), bytes.fromhex("7051"))

    def test_spezifikationsbeispiel(self):
        # Kanonisches Modbus-Beispiel: 11 03 00 6B 00 03 -> CRC 76 87
        self.assertEqual(_crc16(bytes.fromhex("1103006B0003")), bytes.fromhex("7687"))

    def test_anfrage_ai1(self):
        self.assertEqual(_build_request(247, 3, 0, 4), bytes.fromhex("F7 03 00 00 00 04 50 9F"))

    def test_rawframe_encode_bytetreu(self):
        raw = _build_request(247, 3, 0, 4)
        self.assertEqual(_RawFrame(raw).encode(), raw)          # 0xF7 >= 0x80 darf nicht UTF-8-kodiert werden
        self.assertEqual(str(_RawFrame(raw)), "F7 03 00 00 00 04 50 9F")


class FloatTest(unittest.TestCase):
    def test_watchdog_register_506(self):
        # Am Geraet gelesen: Register 506/507 = [0, 16544] -> Watchdog 5.0 s (Menue), Byte order 1-0-3-2
        self.assertEqual(_decode_float(0, 16544, "1-0-3-2"), 5.0)


class FakeCommand:
    class device:
        log = type("L", (), {"info": staticmethod(lambda *a, **k: None)})()
    parameters = type("P", (), {"commandstring": "03"})()


def parse(frame: bytes, byte_order="1-0-3-2", address=247):
    parser = LiquilineParser(FakeCommand(), expect_bus_address=address, expect_function=3, byte_order=byte_order)
    reply = Result(frame.hex(" ").upper()); reply.raw = frame
    return parser(reply)


class ParserTest(unittest.TestCase):
    def test_ai_block_vom_geraet(self):
        # AI1 am 12.10.2026: Register [0, 0, 2, 53] = Wert 0.0, Status 2 Bad, Einheit 53 pH
        result, state = parse(frame_with_crc("F7 03 08 0000 0000 0002 0035"))
        self.assertIs(state, commandstate.Success)
        self.assertEqual(result.parameters, {"value": "0.0", "status": "2", "unit": "53"})

    def test_ai_block_mit_messwert(self):
        # pH 7.25 als Float 40E80000, Drahtfolge 1-0-3-2: Byte1 Byte0 Byte3 Byte2 = 00 00 40 E8; Status 0 Good
        result, state = parse(frame_with_crc("F7 03 08 0000 40E8 0000 0035"))
        self.assertIs(state, commandstate.Success)
        self.assertEqual(result.parameters, {"value": "7.25", "status": "0", "unit": "53"})

    def test_crc_falsch(self):
        frame = bytearray(frame_with_crc("F7 03 08 0000 0000 0002 0035")); frame[-1] ^= 0xFF
        _, state = parse(bytes(frame))
        self.assertIs(state, commandstate.Retry)

    def test_exception(self):
        result, state = parse(frame_with_crc("F7 83 02"))
        self.assertIs(state, commandstate.Fail)
        self.assertIn("ILLEGAL_DATA_ADDRESS", result.line)

    def test_falsche_adresse(self):
        _, state = parse(frame_with_crc("01 03 08 0000 0000 0002 0035"))
        self.assertIs(state, commandstate.Retry)


class FramingTest(unittest.TestCase):
    """LiquilineProtocol.dataReceived: laengenbasiertes Framing, auch bei stueckweisem Empfang und Rauschen."""
    def setUp(self):
        self.frames = []
        self.protocol = LiquilineProtocol()
        self.protocol.device = type("D", (), {"bus_address": 247, "receive": lambda s, r: self.frames.append(r.raw)})()

    def test_rahmenlaengen(self):
        self.assertIsNone(expected_frame_length(b"\xf7"))
        self.assertEqual(expected_frame_length(b"\xf7\x83"), 5)
        self.assertIsNone(expected_frame_length(b"\xf7\x03"))
        self.assertEqual(expected_frame_length(b"\xf7\x03\x08"), 13)

    def test_stueckweise(self):
        frame = frame_with_crc("F7 03 08 0000 0000 0002 0035")
        for i in range(len(frame)):
            self.protocol.dataReceived(frame[i:i + 1])
        self.assertEqual(self.frames, [frame])

    def test_zwei_rahmen_in_einem_stueck_und_rauschen_davor(self):
        f1 = frame_with_crc("F7 03 08 0000 0000 0002 0035")
        f2 = frame_with_crc("F7 83 02")
        self.protocol.dataReceived(b"\x00\x00" + f1 + f2)
        self.assertEqual(self.frames, [f1, f2])


class DeviceTest(unittest.TestCase):
    def test_cmd_string_ist_rtu_anfrage(self):
        dev = Device("127.0.0.1:1", bus_address=247, channels={"ph_ch1": 0})
        cmd = dev.get_cmd("READ_AI_BLOCK", command_values={"value": (0, 4)}, expect_bus_address=247, byte_order="1-0-3-2")
        self.assertEqual(cmd.bytestring, bytes.fromhex("F7 03 00 00 00 04 50 9F"))
        self.assertEqual(dev.serial_parameters, {"baudrate": 19200, "bytesize": 8, "parity": "E", "stopbits": 1})

    def test_observablen_ohne_rohgruppen(self):
        dev = Device("127.0.0.1:1", bus_address=247, channels={"ph_ch1": 0})
        dev.update_observables({"value": "0.0", "status": "2", "unit": "53"})
        self.assertNotIn("value", dev.observables)
        dev.update_observables({"ph_ch1_value": 0.0})
        self.assertIn("ph_ch1_value", dev.observables)
