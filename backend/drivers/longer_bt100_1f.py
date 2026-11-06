# Treiber fuer die Longer BT100-1F-Schlauchpumpe (Messstand II), angebunden ueber RS485
# (Klemmenmodul "RS485 A B GND" an der Rueckseite, FTDI-USB-Adapter), LONGER-eigenes Binaerprotokoll.
#
# QUELLE: docs/BT100-1F-RS485-Protocol.pdf ("LONGER RS485 Protocol for BT100-1F", Herstellerdokument,
# ueber Drifton/Longer am 04.11.2026 erhalten), Kurzfassung in docs/protokoll_bt100_1f.md.
# Alle Beispiel-Frames aus Anhang 7 des Dokuments sind in backend/test/test_longer_bt100_1f.py als
# Pruefvektoren hinterlegt (Frameaufbau, XOR-Pruefsumme, Byte-Stuffing, Parser).
#
# AM GERAET VERIFIZIERT 04.11.2026 (Messstand II, Kopf DG 6 Rollen, Schlauch Nr. 5 = 1,65 mm):
#   - RID/RT/RF/RD/RSD/RB werden beantwortet (tools/lese_bt100_1f.py), 1200 Baud 8E1, Adresse 1.
#   - Routine test_pump1_flow mit 5 mL/min, 0,5 min: WF-Start bestaetigt, 26 RF-Abfragen "laeuft, cw,
#     5,0 mL/min", nach 30 s WF-Stopp bestaetigt, Experiment Finished. Antwortzeit RF ~170 ms.
#   - Die Pumpe uebernimmt die Flussrate in nL/min direkt (WF-Antwort echot den Wert).
# Erstes Lesen am 02.11.2026: nur RID beantwortet, weil damals WJ/RJ/XL (andere Longer-Modelle) probiert wurden.
#
# Unterschiede zur WT600-2J (backend/drivers/longer_wt600.py), von der Frame/XOR/_RawFrame
# importiert werden:
#   - Die BT100-1F kennt WJ/RJ NICHT (darum am 02.11. keine Antwort darauf). Ihre Befehle sind
#     WF/RF (Flussrate-Modus), WD/RD + WSD/RSD (Dosier-Modus), WT/RT (Kopf/Schlauch), WB/RB
#     (Ruecksaugzeit), WID/RID (Adresse).
#   - Sollwert ist eine FLUSSRATE in nL/min (4 Byte, big-endian), keine Drehzahl. Die Umrechnung
#     in mL/min macht die Pumpe selbst anhand des eingestellten Kopfs/Schlauchs - eine
#     tubing_table wie bei der WT600 ist nicht noetig.
#   - BYTE-STUFFING: Ausser dem Start-Flag darf kein E9 im Frame vorkommen. Beim Senden wird
#     E8 -> E8 00 und E9 -> E8 01 ersetzt, beim Empfang zurueckgewandelt. Das Laengenbyte zaehlt
#     die PDU-Bytes VOR dem Stuffing, die Pruefsumme wird ueber die ungestuffte Folge gebildet
#     (Beispiel a im Dokument: Laenge 0E, auf dem Draht aber 15 PDU-Bytes wegen "03 E8" -> "03 E8 00").
#
# Frameformat (beide Richtungen):
#   E9 ADRESSE(1-30, 31=Broadcast ohne Antwort) LAENGE(PDU-Bytes) PDU FCS(XOR ueber ADRESSE+LAENGE+PDU)
# PDU "WF" + Fluss(4 Byte nL/min) + State1(1 Byte)      Antwort: "WF" + Fluss(4 Byte)
# PDU "RF"                                              Antwort: "RF" + Fluss(4 Byte) + State1(1 Byte)
# PDU "RT"                                              Antwort: "RT" + Kopf-Nr(1) + Schlauch-Nr(1)
# PDU "RID"                                             Antwort: "RID"
# State1: Bit0 Start(1)/Stop(0), Bit1 cw(1)/ccw(0), Bit2 Prime (100 rpm, hier nicht verwendet)
#
# Architektur-Sonderfall wie bei der WT600 (dort im Dateikopf ausfuehrlich begruendet): binaeres
# Protokoll ohne Zeilenende -> eigene Protocol-Klasse mit laengenbasiertem Framer, Rohbytes ueber
# _RawFrame am Text-Unterbau vorbei; reply.line traegt nur die Hex-Anzeige, reply.raw die Bytes.

import re

from backend.commands import commandstate
from backend.commands.parser import BaseParser, ParserParameterFactory
from backend.commands.results import Result
from backend.conditions.conditions import TimeCondition
from backend.devices.base import BaseDeviceProtocol, BaseDeviceProtocolFactory
from .longer_wt600 import FLAG, _xor, _build_frame, _RawFrame
from .pump_base import BaseDevice, SinglechannelBaseDevice, CommandParameterFactory
from .valve_dosing import ValveDosingMixIn


ESCAPE = 0xE8
BROADCAST = 31

CMD_WRITE_FLOW = "WF"   # 57 46 - Flussrate + Start/Stop/Richtung (Flussrate-Modus)
CMD_READ_FLOW = "RF"    # 52 46 - Flussrate + Zustand lesen
CMD_READ_TUBING = "RT"  # 52 54 - Pumpenkopf/Schlauch lesen
CMD_READ_ID = "RID"     # 52 49 44 - Adresse lesen (reiner Verbindungstest)

NL_PER_ML = 1_000_000
MIN_FLOW_NL_MIN = 1                 # Protokoll: "Disp Flow range: 1-1000000000"
MAX_FLOW_NL_MIN = 1_000_000_000     # = 1000 mL/min (Pumpe selbst: max. 500 mL/min laut Datenblatt)
DEFAULT_FLOW_NL_MIN = 1 * NL_PER_ML  # 1 mL/min, falls vor dem ersten Stopp noch kein RF gelesen wurde

PUMP_HEADS = {1: "YZ2515", 2: "YZ1515", 3: "DG-6", 4: "DG-10"}  # Anhang 5 des Protokolls


def stuff(data: bytes) -> bytes:
    """Byte-Stuffing nach dem Flag: E8 -> E8 00, E9 -> E8 01."""
    out = bytearray()
    for byte in data:
        if byte == ESCAPE:
            out += bytes([ESCAPE, 0x00])
        elif byte == FLAG:
            out += bytes([ESCAPE, 0x01])
        else:
            out.append(byte)
    return bytes(out)


def unstuff(data: bytes) -> bytes:
    """Umkehrung von stuff(). Ein E8 am Ende ohne Folgebyte wird unveraendert durchgereicht
    (nur fuer vollstaendige Frames gedacht; der Framer unten wartet auf das Folgebyte)."""
    out = bytearray()
    i = 0
    while i < len(data):
        byte = data[i]
        if byte == ESCAPE and i + 1 < len(data) and data[i + 1] in (0x00, 0x01):
            out.append(ESCAPE if data[i + 1] == 0x00 else FLAG)
            i += 2
        else:
            out.append(byte)
            i += 1
    return bytes(out)


def build_wire_frame(address: int, pdu: bytes) -> bytes:
    """Fertiger Draht-Frame: Flag + gestuffte(Adresse + Laenge + PDU + FCS)."""
    plain = _build_frame(address, pdu)
    return bytes([FLAG]) + stuff(plain[1:])


def _state1(running: bool, clockwise: bool, prime: bool = False) -> int:
    return (1 if running else 0) | ((1 if clockwise else 0) << 1) | ((1 if prime else 0) << 2)


def _clamp_flow_nl_min(flow_nl_min) -> int:
    return max(MIN_FLOW_NL_MIN, min(MAX_FLOW_NL_MIN, int(round(float(flow_nl_min)))))


def _u32(data: bytes) -> int:
    return (data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]


def _be32(value: int) -> bytes:
    return bytes([(value >> 24) & 0xFF, (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF])


class BT100Parser(BaseParser):
    """Prueft Flag/Laenge/XOR/Befehlsecho eines (bereits entstufften) Antwortframes und extrahiert
    die Nutzdaten je nach Befehl. Liest reply.raw (vom Framer gesetzt), nicht reply.line."""

    def __init__(self, command, expect_command: bytes, **kwargs):
        super().__init__(command)
        self.expect_command = expect_command

    def __call__(self, reply: Result):
        try:
            frame = reply.raw
        except AttributeError:
            return (commandstate.CommandResponseError(reply=reply, msg=f"Reply has no raw frame bytes: {reply.line!r}."),
                    commandstate.Retry)

        if len(frame) < 4 or frame[0] != FLAG:
            return (commandstate.CommandResponseError(reply=reply, msg=f"Missing/invalid start flag in {frame!r}."),
                    commandstate.Retry)

        address, pdu_length = frame[1], frame[2]
        if len(frame) != pdu_length + 4:
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"Frame length {len(frame)} does not match length byte "
                                          f"{pdu_length} (+4) in {frame!r}."),
                    commandstate.Retry)

        pdu, fcs = frame[3:3 + pdu_length], frame[-1]
        expected_fcs = _xor(frame[1:-1])
        if expected_fcs != fcs:
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"Checksum mismatch in {frame!r}: got {fcs:02X}, "
                                          f"expected {expected_fcs:02X}."),
                    commandstate.Retry)

        if not pdu.startswith(self.expect_command):
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"Unexpected command echo in {frame!r}: expected "
                                          f"{self.expect_command!r}."),
                    commandstate.Retry)

        payload = pdu[len(self.expect_command):]
        parameters = {"pump_address": str(address)}
        code = self.expect_command.decode("ascii")
        if code in (CMD_WRITE_FLOW, CMD_READ_FLOW) and len(payload) >= 4:
            parameters["flow_nl_min"] = str(_u32(payload[:4]))
            if len(payload) >= 5:  # RF liefert State1, WF nur den Fluss
                parameters["running"] = str(payload[4] & 0x01)
                parameters["clockwise"] = str((payload[4] >> 1) & 0x01)
        elif code == CMD_READ_TUBING and len(payload) >= 2:
            parameters["pump_head"] = str(payload[0])
            parameters["tubing"] = str(payload[1])
        reply.parameters = parameters
        return reply, commandstate.Success


class BT100Protocol(BaseDeviceProtocol):
    """Laengenbasierter Framer mit Byte-Stuffing: Nach dem Flag werden die Bytes entstufft, bis
    Adresse + Laengenbyte + Laenge PDU-Bytes + FCS beisammen sind. Ein weiteres E9 im Strom
    (darf laut Protokoll nicht vorkommen) gilt als neuer Frameanfang (Resynchronisation)."""

    def __init__(self):
        super().__init__()
        self._buffer = bytearray()

    def dataReceived(self, data):
        self._buffer.extend(data)
        while True:
            while self._buffer and self._buffer[0] != FLAG:
                del self._buffer[0]  # Rauschen bis zum naechsten Flag verwerfen
            if not self._buffer:
                return
            decoded = bytearray()
            i = 1  # hinter dem Flag
            complete = False
            while i < len(self._buffer):
                byte = self._buffer[i]
                if byte == FLAG:
                    break  # neuer Frameanfang mitten im Frame -> alten verwerfen
                if byte == ESCAPE:
                    if i + 1 >= len(self._buffer):
                        return  # Escape ohne Folgebyte: auf mehr Daten warten
                    nxt = self._buffer[i + 1]
                    decoded.append(ESCAPE if nxt == 0x00 else FLAG if nxt == 0x01 else nxt)
                    i += 2
                else:
                    decoded.append(byte)
                    i += 1
                if len(decoded) >= 2 and len(decoded) == 2 + decoded[1] + 1:
                    complete = True
                    break
            if complete:
                frame = bytes([FLAG]) + bytes(decoded)
                del self._buffer[:i]
                self.frameReceived(frame)
            elif i < len(self._buffer) and self._buffer[i] == FLAG:
                del self._buffer[:i]  # unvollstaendigen Frame vor dem neuen Flag verwerfen
            else:
                return

    def rawDataReceived(self, data):
        pass

    def frameReceived(self, frame: bytes):
        result = Result(frame.hex(" ").upper())
        result.raw = frame
        self.device.receive(result)

    def write_command(self, command_object):
        self.transport.write(command_object.bytestring)
        self.device.log.info(f"Wrote {command_object.parameters.commandstring} to device.")


class BT100ProtocolFactory(BaseDeviceProtocolFactory):
    protocol = BT100Protocol


def _parser(code: str):
    return ParserParameterFactory(parserclass=BT100Parser, expect_command=code.encode("ascii"))


class Device(ValveDosingMixIn, BaseDevice, SinglechannelBaseDevice):
    protocol_factory_class = BT100ProtocolFactory
    serial_parameters = {"baudrate": 1200, "bytesize": 8, "parity": "E", "stopbits": 1}
    command_parameter_factory = CommandParameterFactory(command_execution_time=.1)
    replies_commands = True
    log_name = "Longer BT100-1F"

    commands = {
        "WRITE_FLOW": [CMD_WRITE_FLOW, _parser(CMD_WRITE_FLOW)],
        "READ_FLOW": [CMD_READ_FLOW, _parser(CMD_READ_FLOW)],
        "READ_TUBING": [CMD_READ_TUBING, _parser(CMD_READ_TUBING)],
        "READ_ID": [CMD_READ_ID, _parser(CMD_READ_ID)],
    }

    def __init__(self, address, *args, pump_address: int = 1, dosing: dict = None, **kwargs):
        """
        :param pump_address: Protokolladresse der Pumpe (1-30, ab Werk 1; am Geraet unter
                             System Setting -> Address; dort muss auch "Ext Cont." auf ON stehen).
                             Nicht zu verwechseln mit `address` (serielle Schnittstelle).
        :param dosing: optionaler Abschnitt fuer Zugaben ueber ein Auswahlventil (valve, water_port,
                       dead_volume_ml, flush_factor, min/max_rate_ml_min, min_dose_seconds - alles Pflicht,
                       siehe valve_dosing.py). Ohne den Abschnitt verhaelt sich die Pumpe wie bisher.
        """
        self.pump_address = int(pump_address)
        if not 1 <= self.pump_address <= 30:
            raise ValueError(f"pump_address {pump_address} ausserhalb 1-30 (31 = Broadcast ist nicht erlaubt).")
        self._init_dosing(dosing)
        self._flow_nl_min = DEFAULT_FLOW_NL_MIN
        self._flow_known = False   # True, sobald ein RF/WF die eingestellte Flussrate geliefert hat
        self._running = False
        self._clockwise = True
        super().__init__(address, *args, **kwargs)
        self._flow_measuring = None

    def cmd_string(self, command_parameters: CommandParameterFactory) -> str:
        code = command_parameters.commandstring
        if code == CMD_WRITE_FLOW:
            flow_nl_min, running, clockwise = command_parameters.command_values["value"]
            pdu = CMD_WRITE_FLOW.encode("ascii") + _be32(flow_nl_min) + bytes([_state1(running, clockwise)])
        elif code in (CMD_READ_FLOW, CMD_READ_TUBING, CMD_READ_ID):
            pdu = code.encode("ascii")
        else:
            raise ValueError(f"Unknown BT100-1F command code {code!r}.")
        return _RawFrame(build_wire_frame(self.pump_address, pdu))

    def initial_commands(self):
        # Erst lesen (Adresse, Kopf/Schlauch, eingestellte Flussrate), dann sicherheitshalber stoppen.
        # Der Stopp-Frame wird erst NACH der RF-Antwort gebaut, damit er die am Geraet eingestellte
        # Flussrate zurueckschreibt statt DEFAULT_FLOW_NL_MIN (cmd_string() laeuft beim Einreihen).
        self.query("READ_ID", inter_command_time=0)
        self.query("READ_TUBING", inter_command_time=0)
        self.query("READ_FLOW").deferred_result.addBoth(self._adopt_device_flow_and_stop)

    def _adopt_device_flow_and_stop(self, result):
        """Callback der RF-Antwort beim Verbinden. Liest die Flussrate direkt aus result.parameters:
        der Callback feuert, BEVOR der Unterbau update_observables() aufruft (base.py receive():
        erst Zustand setzen, dann Observablen) - am Geraet am 04.11.2026 gesehen (Stopp ging mit
        1,0 mL/min statt der gelesenen 0,018 mL/min raus). Bei Fehler (Failure) trotzdem stoppen."""
        try:
            flow_nl_min = int(result.parameters["flow_nl_min"])
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        else:
            if not self._flow_known and flow_nl_min >= MIN_FLOW_NL_MIN:
                self._flow_nl_min = flow_nl_min
                self._flow_known = True
        self.stop_pumping()
        return result

    def final_commands(self):
        self.stop_pumping()

    def handle_event(self, match: re.Match) -> None:
        pass

    # Rohschluessel aus BT100Parser - werden hier in typisierte Observablen uebersetzt. ALLE anderen
    # Schluessel (vor allem "state" vom Unterbau bei jedem Zustandswechsel, "errorcode") muessen
    # unveraendert durchgereicht werden: die Endbedingung eines Experiments (DevicesWaitingCondition)
    # feuert nur auf die "state"-Meldung "Waiting". Am 04.11.2026 blieb test_pump1_read deshalb ewig
    # in Running, weil diese Methode "state" verschluckt hat.
    _RAW_KEYS = ("pump_address", "flow_nl_min", "running", "clockwise", "pump_head", "tubing")

    def update_observables(self, observables: dict, timestamp: float = None):
        converted = {key: value for key, value in observables.items() if key not in self._RAW_KEYS}
        if "flow_nl_min" in observables:
            flow_nl_min = int(observables["flow_nl_min"])
            if not self._flow_known and flow_nl_min >= MIN_FLOW_NL_MIN:
                self._flow_nl_min = flow_nl_min  # Geraeteeinstellung uebernehmen (siehe initial_commands)
            self._flow_known = True
            converted["set_flow_ml_min"] = flow_nl_min / NL_PER_ML
            if "running" in observables:
                converted["running"] = bool(int(observables["running"]))
                converted["clockwise"] = bool(int(observables["clockwise"]))
                # Fluss nur bei laufender Pumpe, sonst 0 (die Pumpe meldet den Sollwert auch im Stand)
                converted["flow_ml_min"] = converted["set_flow_ml_min"] if converted["running"] else 0.0
        if "pump_head" in observables:
            head = int(observables["pump_head"])
            converted["pump_head"] = PUMP_HEADS.get(head, str(head))
            converted["tubing_no"] = int(observables["tubing"])
        if converted:
            if timestamp is None:
                super().update_observables(converted)
            else:
                super().update_observables(converted, timestamp)

    def start_measuring(self, interval: float = 1.0, condition=None):
        """Flussrate/Zustand periodisch abfragen (Live-Werte im Monitoring). Bei 1200 Baud dauert
        ein RF-Paar ~170 ms, Intervalle unter 0,5 s verstopfen die Leitung."""
        self._flow_measuring = self.repeated_query("READ_FLOW", interval, condition, inter_command_time=.001)

    def stop_measuring(self):
        try:
            self._flow_measuring.stop_running()
        except AttributeError:
            pass
        else:
            self._flow_measuring = None

    def _send_state(self, **kwargs):
        """Ein WF-Frame traegt immer Flussrate UND Start/Stop UND Richtung."""
        return self.write("WRITE_FLOW", command_values={
            "value": (self._flow_nl_min, self._running, self._clockwise)}, **kwargs)

    def set_flow(self, rate, clockwise: bool = True, **kwargs):
        """Flussrate in mL/min setzen, Start/Stop-Zustand bleibt wie er ist."""
        self._flow_nl_min = _clamp_flow_nl_min(float(rate) * NL_PER_ML)
        self._flow_known = True
        self._clockwise = bool(clockwise)
        return self._send_state(**kwargs)

    def start_pumping(self, **kwargs):
        """Start mit der zuletzt gesetzten Flussrate; startet das periodische Auslesen."""
        self._running = True
        cmd = self._send_state(**kwargs)
        self.start_measuring()
        return cmd

    def read_flow(self, **kwargs):
        """Flussrate und Zustand lesen -> Observablen set_flow_ml_min, flow_ml_min, running, clockwise."""
        return self.query("READ_FLOW")

    def read_tubing(self, **kwargs):
        """Pumpenkopf und Schlauchnummer lesen -> Observablen pump_head, tubing_no."""
        return self.query("READ_TUBING")

    def continuous_flow(self, rate, **kwargs):
        """rate in mL/min; negatives Vorzeichen = gegen den Uhrzeigersinn."""
        rate = float(rate)
        self.set_flow(abs(rate), clockwise=rate >= 0, **kwargs)
        self.start_pumping(**kwargs)

    def dispense(self, rate, volume, **kwargs):
        """Volumen (mL) mit rate (mL/min) ueber die Laufzeit foerdern, dann Stopp. Zeitgesteuert wie
        bei der WT600; der geraeteeigene Dosier-Modus (WD/WSD) wird nicht benutzt, weil er am Geraet
        den Control Mode "Dispensing" voraussetzt."""
        if float(volume) == 0:
            return
        self.continuous_flow(rate, **kwargs)
        time_to_pump = 60 * abs(float(volume)) / abs(float(rate))

        def stop(result):
            self.stop_pumping(urgent=True)
            return result
        self.busy(TimeCondition("dispense finished", time_to_pump)).deferred_result.addBoth(stop)

    def run_for_minutes(self, rate, minutes, **kwargs):
        """'minutes' Minuten mit 'rate' mL/min laufen, dann Stopp. Geraet ist solange Busy."""
        return self.dispense(rate, float(rate) * float(minutes), **kwargs)

    # -- Zugabe ueber das Auswahlventil (valve_dosing.ValveDosingMixIn) --------------------------------
    # Beide Befehle gehen als dringend raus, weil die Pumpe waehrend der ganzen Zugabe Busy ist. Kein
    # periodisches RF dabei: der Stopp soll nie hinter einer Abfrage warten (Dosiergenauigkeit).

    def _dosing_pump_start(self, rate_ml_min):
        """Ein WF-Frame: Flussrate setzen UND starten (im Uhrzeigersinn). Rueckgabe: der Befehl."""
        self.stop_measuring()
        self._flow_nl_min = _clamp_flow_nl_min(float(rate_ml_min) * NL_PER_ML)
        self._flow_known = True
        self._clockwise = True
        self._running = True
        return self._send_state(urgent=True, run_while_device_busy=True)

    def _dosing_pump_stop(self):
        """Stopp; danach einmal RF, damit die Observablen running/flow_ml_min stimmen. Rueckgabe: der
        Stopp-Befehl (WF)."""
        self._running = False
        command = self._send_state(urgent=True, run_while_device_busy=True)
        self.query("READ_FLOW", urgent=True, run_while_device_busy=True)
        return command

    def stop_pumping(self, **kwargs):
        """Stop (Start/Stop-Bit 0, Flussrate bleibt). Beendet auch das periodische Auslesen und liest
        den Zustand einmal zurueck, damit die Observablen mit running=False / flow_ml_min=0 enden
        (die WF-Bestaetigung traegt nur die Flussrate, keinen Zustand)."""
        self.stop_measuring()
        self._running = False
        cmd = self._send_state(**kwargs)
        self.query("READ_FLOW", **kwargs)
        return cmd
