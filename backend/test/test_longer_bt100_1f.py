# Tests fuer den Longer-BT100-1F-Treiber (backend/drivers/longer_bt100_1f.py), Stand 04.11.2026.
# Pruefvektoren: Anhang 7 von docs/BT100-1F-RS485-Protocol.pdf (Herstellerbeispiele a/b/c) und die
# am 02.11.2026 am Geraet gemessene RID-Antwort. Laeuft ohne Hardware.
# Aufruf: .venv/bin/python -m twisted.trial backend.test.test_longer_bt100_1f
from twisted.trial import unittest

from backend.commands import commandstate
from backend.commands.results import Result
from backend.drivers.longer_bt100_1f import (stuff, unstuff, build_wire_frame, BT100Parser, BT100Protocol,
                                             Device, _RawFrame, _state1, _clamp_flow_nl_min,
                                             CMD_WRITE_FLOW, CMD_READ_FLOW, CMD_READ_ID, CMD_READ_TUBING)
from backend.drivers.longer_wt600 import _build_frame


def h(hexstring: str) -> bytes:
    return bytes.fromhex(hexstring)


class FrameTest(unittest.TestCase):
    def test_beispiel_a_write_dispensing_mit_stuffing(self):
        # Protokoll Anhang 7a: Disp Vol 10.0 mL (03E8 -> 03 E8 00 auf dem Draht), 200 Kopien,
        # 100.0 mL/min, Pause 1.0 s. Laengenbyte 0E zaehlt VOR dem Stuffing, FCS 24.
        pdu = b"WD" + h("000003E8") + h("00C8") + h("05F5E100") + h("000A")
        self.assertEqual(build_wire_frame(1, pdu), h("E9 01 0E 57 44 00 00 03 E8 00 00 C8 05 F5 E1 00 00 0A 24"))

    def test_beispiel_b_read_flow_anfrage(self):
        self.assertEqual(build_wire_frame(1, b"RF"), h("E9 01 02 52 46 17"))

    def test_beispiel_c_write_tubing(self):
        self.assertEqual(build_wire_frame(1, b"WT" + h("0202")), h("E9 01 04 57 54 02 02 06"))

    def test_rid_anfrage_und_antwort_vom_geraet_02_11_2026(self):
        self.assertEqual(build_wire_frame(1, b"RID"), h("E9 01 03 52 49 44 5D"))
        # Die Pumpe antwortete am 02.11.2026 mit genau demselben Frame (Echo).
        self.assertEqual(_build_frame(1, b"RID"), h("E9 01 03 52 49 44 5D"))

    def test_stuffing_roundtrip(self):
        plain = h("01 05 E8 E9 00 E8 E9")
        self.assertEqual(stuff(plain), h("01 05 E8 00 E8 01 00 E8 00 E8 01"))
        self.assertEqual(unstuff(stuff(plain)), plain)

    def test_rawframe_bytetreu(self):
        raw = build_wire_frame(1, b"RF")
        self.assertEqual(_RawFrame(raw).encode(), raw)
        self.assertEqual(str(_RawFrame(raw)), "E9 01 02 52 46 17")

    def test_state1(self):
        self.assertEqual(_state1(running=False, clockwise=True), 0x02)   # Beispiel b: "stop state, run in cw"
        self.assertEqual(_state1(running=True, clockwise=True), 0x03)
        self.assertEqual(_state1(running=True, clockwise=False), 0x01)
        self.assertEqual(_state1(running=True, clockwise=True, prime=True), 0x07)

    def test_clamp(self):
        self.assertEqual(_clamp_flow_nl_min(0), 1)
        self.assertEqual(_clamp_flow_nl_min(2.5e9), 1_000_000_000)
        self.assertEqual(_clamp_flow_nl_min(250_000_000.4), 250_000_000)


class FakeCommand:
    class device:
        log = type("L", (), {"info": staticmethod(lambda *a, **k: None)})()

    def __init__(self, code):
        self.parameters = type("P", (), {"commandstring": code, "command_values": {}})()


def parse(frame: bytes, code: str):
    parser = BT100Parser(FakeCommand(code), expect_command=code.encode("ascii"))
    reply = Result(frame.hex(" ").upper()); reply.raw = frame
    return parser(reply)


class ParserTest(unittest.TestCase):
    def test_beispiel_b_read_flow_antwort(self):
        # 0E E6 B2 80 = 250000000 nL/min = 250.0 mL/min, State1 02 = gestoppt, cw
        result, state = parse(h("E9 01 07 52 46 0E E6 B2 80 02 CA"), CMD_READ_FLOW)
        self.assertIs(state, commandstate.Success)
        self.assertEqual(result.parameters, {"pump_address": "1", "flow_nl_min": "250000000",
                                             "running": "0", "clockwise": "1"})

    def test_write_flow_antwort_nur_fluss(self):
        frame = _build_frame(1, b"WF" + h("05F5E100"))
        result, state = parse(frame, CMD_WRITE_FLOW)
        self.assertIs(state, commandstate.Success)
        self.assertEqual(result.parameters, {"pump_address": "1", "flow_nl_min": "100000000"})

    def test_read_tubing_antwort(self):
        result, state = parse(_build_frame(1, b"RT" + h("0202")), CMD_READ_TUBING)
        self.assertIs(state, commandstate.Success)
        self.assertEqual(result.parameters, {"pump_address": "1", "pump_head": "2", "tubing": "2"})

    def test_rid_antwort(self):
        result, state = parse(h("E9 01 03 52 49 44 5D"), CMD_READ_ID)
        self.assertIs(state, commandstate.Success)
        self.assertEqual(result.parameters, {"pump_address": "1"})

    def test_pruefsumme_falsch(self):
        _, state = parse(h("E9 01 07 52 46 0E E6 B2 80 02 CB"), CMD_READ_FLOW)
        self.assertIs(state, commandstate.Retry)

    def test_falsches_echo(self):
        _, state = parse(h("E9 01 07 52 46 0E E6 B2 80 02 CA"), CMD_WRITE_FLOW)
        self.assertIs(state, commandstate.Retry)

    def test_laenge_passt_nicht(self):
        _, state = parse(h("E9 01 07 52 46 0E E6"), CMD_READ_FLOW)
        self.assertIs(state, commandstate.Retry)


class FakeDevice:
    def __init__(self):
        self.frames = []
        self.log = FakeCommand.device.log

    def receive(self, result):
        self.frames.append(result.raw)


def protocol_with_device():
    protocol = BT100Protocol()
    protocol.device = FakeDevice()
    return protocol


class FramerTest(unittest.TestCase):
    def test_antwort_am_stueck(self):
        p = protocol_with_device()
        p.dataReceived(h("E9 01 07 52 46 0E E6 B2 80 02 CA"))
        self.assertEqual(p.device.frames, [h("E9 01 07 52 46 0E E6 B2 80 02 CA")])

    def test_stuffing_wird_entfernt_auch_bei_bytweiser_ankunft(self):
        # Draht: E9 01 02 57 44 10 (Beispiel a) plus ein Frame, dessen Fluss ein E8 enthaelt:
        # Fluss 0x0E E8 B2 80 -> auf dem Draht 0E E8 00 B2 80; Laenge bleibt 07.
        plain = _build_frame(1, b"RF" + h("0EE8B280") + h("02"))
        wire = build_wire_frame(1, b"RF" + h("0EE8B280") + h("02"))
        self.assertIn(h("E8 00"), wire)
        p = protocol_with_device()
        for byte in h("E9 01 02 57 44 10") + wire:
            p.dataReceived(bytes([byte]))
        self.assertEqual(p.device.frames, [h("E9 01 02 57 44 10"), plain])

    def test_rauschen_vor_dem_flag_wird_verworfen(self):
        p = protocol_with_device()
        p.dataReceived(h("00 FF 13") + h("E9 01 02 52 46 17"))
        self.assertEqual(p.device.frames, [h("E9 01 02 52 46 17")])

    def test_neues_flag_mitten_im_frame_resynchronisiert(self):
        p = protocol_with_device()
        p.dataReceived(h("E9 01 07 52 46") + h("E9 01 02 52 46 17"))
        self.assertEqual(p.device.frames, [h("E9 01 02 52 46 17")])

    def test_unvollstaendig_wartet(self):
        p = protocol_with_device()
        p.dataReceived(h("E9 01 07 52 46 0E E6 B2"))
        self.assertEqual(p.device.frames, [])
        p.dataReceived(h("80 02 CA"))
        self.assertEqual(p.device.frames, [h("E9 01 07 52 46 0E E6 B2 80 02 CA")])


class DeviceCmdStringTest(unittest.TestCase):
    def setUp(self):
        self.device = Device("127.0.0.1:12399", pump_address=1)

    def _frame(self, code, value=None):
        params = type("P", (), {"commandstring": code, "command_values": {"value": value}})()
        return self.device.cmd_string(params).encode()

    def test_wf_100ml_min_start_cw(self):
        frame = self._frame(CMD_WRITE_FLOW, (100_000_000, True, True))
        self.assertEqual(frame, _build_frame(1, b"WF" + h("05F5E100") + h("03")))

    def test_wf_stop(self):
        frame = self._frame(CMD_WRITE_FLOW, (250_000_000, False, True))
        self.assertEqual(frame, h("E9 01 07 57 46 0E E6 B2 80 02") + bytes([0x01 ^ 0x07 ^ 0x57 ^ 0x46 ^ 0x0E ^ 0xE6 ^ 0xB2 ^ 0x80 ^ 0x02]))

    def test_wf_mit_stuffing_im_fluss(self):
        # 1000 mL/min = 0x3B9ACA00 kein E8; 0x0EE8B280 enthaelt E8 -> gestufft
        frame = self._frame(CMD_WRITE_FLOW, (0x0EE8B280, True, True))
        self.assertEqual(frame, build_wire_frame(1, b"WF" + h("0EE8B280") + h("03")))
        self.assertIn(h("E8 00"), frame)

    def test_lesebefehle(self):
        self.assertEqual(self._frame(CMD_READ_FLOW), h("E9 01 02 52 46 17"))
        self.assertEqual(self._frame(CMD_READ_ID), h("E9 01 03 52 49 44 5D"))
        self.assertEqual(self._frame(CMD_READ_TUBING), _build_frame(1, b"RT"))

    def test_broadcastadresse_abgelehnt(self):
        self.assertRaises(ValueError, Device, "127.0.0.1:12399", pump_address=31)


class DeviceObservablesTest(unittest.TestCase):
    def setUp(self):
        self.device = Device("127.0.0.1:12399", pump_address=1)
        self.seen = []
        self.device.subscribe = None
        # Beobachtungen abfangen, statt den Observer-Unterbau zu benutzen
        import backend.drivers.longer_bt100_1f as mod
        self._orig = mod.SinglechannelBaseDevice.update_observables
        mod.SinglechannelBaseDevice.update_observables = lambda dev, obs, ts=None: self.seen.append(obs)

    def tearDown(self):
        import backend.drivers.longer_bt100_1f as mod
        mod.SinglechannelBaseDevice.update_observables = self._orig

    def test_rf_antwort_wird_umgerechnet_und_fluss_uebernommen(self):
        self.device.update_observables({"pump_address": "1", "flow_nl_min": "250000000", "running": "0", "clockwise": "1"})
        self.assertEqual(self.seen, [{"set_flow_ml_min": 250.0, "running": False, "clockwise": True, "flow_ml_min": 0.0}])
        self.assertEqual(self.device._flow_nl_min, 250_000_000)  # Geraeteeinstellung uebernommen
        self.device.update_observables({"pump_address": "1", "flow_nl_min": "100000000", "running": "1", "clockwise": "0"})
        self.assertEqual(self.seen[-1], {"set_flow_ml_min": 100.0, "running": True, "clockwise": False, "flow_ml_min": 100.0})
        self.assertEqual(self.device._flow_nl_min, 250_000_000)  # nur die erste Meldung wird uebernommen

    def test_set_flow_hat_vorrang_vor_geraetewert(self):
        self.device._flow_nl_min = 5_000_000; self.device._flow_known = True
        self.device.update_observables({"pump_address": "1", "flow_nl_min": "250000000", "running": "0", "clockwise": "1"})
        self.assertEqual(self.device._flow_nl_min, 5_000_000)

    def test_rt_antwort(self):
        self.device.update_observables({"pump_address": "1", "pump_head": "2", "tubing": "2"})
        self.assertEqual(self.seen, [{"pump_head": "YZ1515", "tubing_no": 2}])

    def test_rid_antwort_ohne_observable(self):
        self.device.update_observables({"pump_address": "1"})
        self.assertEqual(self.seen, [])
