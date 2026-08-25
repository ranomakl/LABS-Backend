# Treiber fuer die Longer WT600-2J(1J)(3J)-Schlauchpumpe, angebunden ueber RS485 (DB15-Adapter),
# LONGER-eigenes Binaerprotokoll.
#
# QUELLENLAGE - WICHTIG: Quelle ist docs/protokoll_pumpe.md, ein BLOGPOST ("How to Control the
# Longer WT600-2J(1J)(3J) Pump via Matlab?"), KEIN Herstellerhandbuch. Der Blogpost liefert drei
# vollstaendige Beispiel-Frames (inkl. Pruefsumme) sowie eine Tabelle fuer die Lese-Antwort
# ("Read running parameter"), aber KEIN Beispiel fuer die Antwort auf einen Schreibbefehl
# ("Set running parameter"/WJ). Vor Produktiveinsatz gegen echte Hardware bzw. ein
# Herstellerhandbuch verifizieren, falls verfuegbar!
#
# VERIFIZIERT byte-genau (siehe docs/protokoll_pumpe.md, Abschnitt "Examples of control command
# strings" + Matlab-Codebeispiele) - alle drei dort vorkommenden Frames inkl. XOR-Pruefsumme:
#   150 rpm, cw, start, Adresse 1:  E9 01 06 57 4A 00 96 01 01 8C
#   Adresse 1 -> 7 aendern:         E9 01 04 57 49 44 07 58            (WID, hier NICHT implementiert)
#   320 rpm, cw, start, Adresse 4:  E9 04 06 57 4A 01 40 01 01 5E
#   50 rpm, ccw, start, Adresse 4:  E9 04 06 57 4A 00 32 01 00 2C
#   50 rpm, ccw, stop, Adresse 4:   E9 04 06 57 4A 00 32 00 00 2D
# Alle fuenf Frames wurden gegen _build_frame() (s.u.) nachgerechnet: Flag, Adresse, PDU-Laenge,
# PDU-Inhalt und XOR-Pruefsumme stimmen jeweils byte-genau ueberein.
#
# UNVERIFIZIERTE ANNAHME (weil der Blogpost dafuer kein Beispiel zeigt): Die Antwort auf einen
# WJ-Schreibbefehl hat dieselbe PDU-Struktur wie die dokumentierte RJ-Leseantwort (WJ/RJ + Drehzahl
# + State1 + State2, 6 Byte PDU) - der Blogtext sagt nur "the pump will respond with WJ", ohne die
# volle Antwortstruktur zu zeigen. Der Parser (WT600Parser, s.u.) verlangt diese 6 Byte deshalb
# NICHT zwingend: er prueft Flag/Adresse/Pruefsumme/Befehlsecho anhand der tatsaechlich
# empfangenen, selbstbeschreibenden PDU-Laenge (Laengenbyte im Frame) und wertet Drehzahl/State nur
# aus, wenn tatsaechlich >= 6 Byte PDU zurueckkommen. Damit funktioniert er unabhaengig davon, ob
# die Pumpe nur "WJ" oder die volle Struktur zurueckschickt.
#
# Frameformat (fuer beide Richtungen, Anfrage wie Antwort):
#   E9(Flag, 1 Byte) ADRESSE(1 Byte, 1-30 oder 31=Broadcast) LAENGE(1 Byte, Anzahl PDU-Bytes)
#   PDU(LAENGE Byte) FCS(1 Byte, XOR ueber ADRESSE+LAENGE+PDU)
# "Set running parameter" (WJ, schreibend): PDU = "WJ" + Drehzahl(2 Byte, big-endian, 0-600) +
#   State1(1 Byte: bit0 Start/Stop, bit1 Prime - hier nicht verwendet) + State2(1 Byte: bit0
#   Drehrichtung, 1=cw/0=ccw)
# "Read running parameter" (RJ, lesend): Anfrage-PDU = "RJ" (2 Byte); Antwort-PDU = "RJ" +
#   Drehzahl(2 Byte) + State1(1 Byte) + State2(1 Byte), s.o.
#
# ACHTUNG - Architektur-Sonderfall dieses Treibers (anders als alle anderen Treiber in diesem
# Repo): Das WT600-Protokoll ist binaer (rohe Bytes 0x00-0xFF), nicht ASCII-Text mit Zeilenende.
# Der gemeinsame Unterbau (backend/devices/base.py, backend/commands/commands.py) geht aber von
# einem zeilenbasierten Text-Protokoll aus:
#   - Command.__init__ baut den Draht-Bytestring immer per commandstring.encode() (UTF-8) -
#     fuer Zeichen >= 0x80 (die in Adresse/Drehzahl/Pruefsumme dieses Protokolls staendig
#     vorkommen) waere das NICHT byte-treu. Loesung: _RawFrame (str-Subklasse unten), deren
#     .encode() unabhaengig von Encoding-Argumenten immer die exakten Rohbytes zurueckgibt; als
#     "Text" traegt sie zu Log-/Debugzwecken die Hex-Darstellung des Frames.
#   - BaseDeviceProtocol (LineReceiver) erkennt Nachrichtenenden ueber ein Text-Trennzeichen -
#     das WT600-Protokoll hat keines, Frames sind stattdessen selbstbeschreibend ueber das
#     Laengenbyte. Loesung: WT600Protocol (unten) ueberschreibt dataReceived() komplett mit einer
#     laengenbasierten Framer-Logik und write_command() so, dass Rohbytes ohne angehaengtes
#     Trennzeichen gesendet werden.
# Beides bleibt vollstaendig in diesem Treibermodul gekapselt, backend/devices/base.py und
# backend/commands/commands.py werden nicht veraendert.

import re

from backend.commands import commandstate
from backend.commands.parser import BaseParser, ParserParameterFactory
from backend.commands.results import Result
from backend.conditions.conditions import TimeCondition
from backend.devices.base import BaseDeviceProtocol, BaseDeviceProtocolFactory
from .pump_base import BaseDevice, SinglechannelBaseDevice, CommandParameterFactory


FLAG = 0xE9
MAX_RPM = 600  # Herstellerangabe im Blogpost: "a maximum speed of 600 rpm"

CMD_SET = "WJ"   # 57 4A - "Set running parameter" (Drehzahl/Start/Stop/Richtung in einem Frame)
CMD_READ = "RJ"  # 52 4A - "Read running parameter"


def _xor(data) -> int:
    checksum = 0
    for byte in data:
        checksum ^= byte
    return checksum


def _build_frame(address: int, pdu: bytes) -> bytes:
    """E9 + Adresse + Laenge + PDU + FCS(XOR ueber Adresse+Laenge+PDU). Generisch fuer beide
    Richtungen und alle PDU-Typen (auch WID/RID, hier nicht genutzt) - siehe Verifikation oben."""
    body = bytes([address & 0xFF, len(pdu)]) + pdu
    return bytes([FLAG]) + body + bytes([_xor(body)])


def _state1(running: bool, prime: bool = False) -> int:
    return (1 if running else 0) | ((1 if prime else 0) << 1)


def _state2(clockwise: bool) -> int:
    return 1 if clockwise else 0


def _clamp_rpm(rpm) -> int:
    return max(0, min(MAX_RPM, int(round(float(rpm)))))


class _RawFrame(str):
    """str-Subklasse, die als Text ihre eigene Hex-Darstellung traegt (fuer Logs/Reprs im
    gemeinsamen Unterbau, der commandstring wie einen String behandelt), deren .encode() aber -
    unabhaengig von Encoding/Errors-Argumenten - immer die tatsaechlichen Rohbytes liefert. Noetig,
    weil Command.__init__ (backend/commands/commands.py) unbedingt commandstring.encode() (UTF-8)
    aufruft; siehe Kommentar am Dateianfang."""

    def __new__(cls, raw: bytes):
        obj = super().__new__(cls, raw.hex(" ").upper())
        obj._raw = bytes(raw)
        return obj

    def encode(self, *args, **kwargs):
        return self._raw


class WT600Parser(BaseParser):
    """Prueft Flag/Adresse/XOR-Pruefsumme/Befehlsecho eines WT600-Antwortframes und extrahiert
    Drehzahl/Status, falls vorhanden (siehe UNVERIFIZIERTE ANNAHME oben - die Laenge der PDU wird
    aus dem tatsaechlich empfangenen Laengenbyte gelesen, nicht angenommen).

    Liest die Rohbytes aus reply.raw (von WT600Protocol.frameReceived gesetzt), NICHT aus
    reply.line: reply.line ist bewusst nur die Hex-Anzeige des Frames (siehe _RawFrame-Kommentar
    oben) - der gemeinsame Unterbau (backend/devices/base.py) loggt reply.line unveraendert
    (u.a. "self.log.info(f'Received {reply}')"), und rohe Steuerzeichen dort brachten den
    Windows-Konsolen-Log-Observer per UnicodeEncodeError zum Absturz (mit echter Hardware
    live nachvollzogen)."""

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

        if pdu[:2] != self.expect_command:
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"Unexpected command echo in {frame!r}: expected "
                                          f"{self.expect_command!r}."),
                    commandstate.Retry)

        parameters = {"pump_address": str(address)}
        if len(pdu) >= 6:
            speed = (pdu[2] << 8) | pdu[3]
            parameters.update({
                "speed": str(speed),
                "running": str(pdu[4] & 0x01),
                "clockwise": str(pdu[5] & 0x01),
            })
        reply.parameters = parameters
        return reply, commandstate.Success


class WT600Protocol(BaseDeviceProtocol):
    """Ersetzt die zeilenbasierte Framer-Logik von BaseDeviceProtocol (LineReceiver) durch eine
    laengenbasierte: ein Frame ist vollstaendig, sobald FLAG+Adresse+Laengenbyte (3 Byte) plus
    "Laengenbyte" weitere PDU-Bytes plus 1 FCS-Byte im Puffer stehen. dataReceived() wird dazu
    komplett ueberschrieben (LineReceiver.dataReceived wird nie aufgerufen)."""

    def __init__(self):
        super().__init__()
        self._buffer = bytearray()

    def dataReceived(self, data):
        self._buffer.extend(data)
        while True:
            while self._buffer and self._buffer[0] != FLAG:
                # Rauschen/Fehlsynchronisation: bis zum naechsten moeglichen Frameanfang verwerfen.
                del self._buffer[0]
            if len(self._buffer) < 3:
                return
            frame_length = 3 + self._buffer[2] + 1  # Flag+Adresse+Laengenbyte + PDU + FCS
            if len(self._buffer) < frame_length:
                return
            frame = bytes(self._buffer[:frame_length])
            del self._buffer[:frame_length]
            self.frameReceived(frame)

    def rawDataReceived(self, data):
        pass  # ungenutzt: dataReceived() oben wird nie in den LineReceiver-Rawmode delegiert.

    def frameReceived(self, frame: bytes):
        # reply.line traegt bewusst nur die Hex-Anzeige (druckbar, log-sicher) - die tatsaechlichen
        # Rohbytes haengen als reply.raw dran, gelesen von WT600Parser. Siehe Kommentar dort:
        # rohe Steuerzeichen in reply.line liessen den Konsolen-Log-Observer abstuerzen
        # (UnicodeEncodeError beim Rendern von "self.log.info(f'Received {reply}')" in base.py).
        result = Result(frame.hex(" ").upper())
        result.raw = frame
        self.device.receive(result)

    def write_command(self, command_object):
        # kein sendLine(): der Frame ist bereits vollstaendig (inkl. FCS als letztem Byte), ein
        # zusaetzliches Trennzeichen wuerde ihn verfaelschen.
        self.transport.write(command_object.bytestring)
        self.device.log.info(f"Wrote {command_object.parameters.commandstring} to device.")


class WT600ProtocolFactory(BaseDeviceProtocolFactory):
    protocol = WT600Protocol


class Device(BaseDevice, SinglechannelBaseDevice):
    protocol_factory_class = WT600ProtocolFactory
    serial_parameters = {"baudrate": 1200, "bytesize": 8, "parity": "E", "stopbits": 1}
    command_parameter_factory = CommandParameterFactory(command_execution_time=.1)
    replies_commands = True
    log_name = "Longer WT600-2J"

    commands = {
        "SET": [CMD_SET, ParserParameterFactory(parserclass=WT600Parser, expect_command=CMD_SET.encode("ascii"))],
        "READ": [CMD_READ, ParserParameterFactory(parserclass=WT600Parser, expect_command=CMD_READ.encode("ascii"))],
    }

    def __init__(self, address, *args, pump_address: int = 1, tubing: str = None,
                 tubing_table: dict = None, **kwargs):
        """
        :param pump_address: Geraeteadresse im WT600-Protokoll (1-30, oder 31 fuer Broadcast; ab
                              Werk 1) - NICHT zu verwechseln mit `address` (serielle
                              Schnittstelle/TCP-Endpunkt der Dummy-Umgebung).
        :param tubing: Schluessel in tubing_table, waehlt den Umrechnungsfaktor RPM<->mL/min.
        :param tubing_table: {Schlauchbezeichnung: mL pro Umdrehung} - je nach montiertem
                              Schlauch/Pumpenkopf per Kalibrierung zu ermitteln, aus config.yml.
        """
        self.pump_address = int(pump_address)
        self.tubing = tubing
        self.tubing_table = {key: float(value) for key, value in (tubing_table or {}).items()}
        self._speed_rpm = 0
        self._running = False
        self._clockwise = True
        super().__init__(address, *args, **kwargs)

    def _ml_min_per_rpm(self) -> float:
        try:
            return self.tubing_table[self.tubing]
        except KeyError:
            raise ValueError(
                f"No calibration factor for tubing {self.tubing!r} in tubing_table "
                f"(configured keys: {list(self.tubing_table)}). Add it to this device's "
                f"tubing_table in config.yml.")

    def cmd_string(self, command_parameters: CommandParameterFactory) -> str:
        code = command_parameters.commandstring
        if code == CMD_SET:
            speed, running, clockwise = command_parameters.command_values["value"]
            pdu = (CMD_SET.encode("ascii")
                   + bytes([(speed >> 8) & 0xFF, speed & 0xFF, _state1(running), _state2(clockwise)]))
        elif code == CMD_READ:
            pdu = CMD_READ.encode("ascii")
        else:
            raise ValueError(f"Unknown WT600 command code {code!r}.")
        return _RawFrame(_build_frame(self.pump_address, pdu))

    def initial_commands(self):
        self.stop_pumping()

    def final_commands(self):
        self.stop_pumping()

    def handle_event(self, match: re.Match) -> None:
        pass

    def _send_state(self, **kwargs):
        """Sendet Drehzahl+Start/Stop+Richtung als ein WJ-Frame (das Protokoll erlaubt kein
        Aendern nur eines der drei Felder - jeder Frame traegt immer den vollstaendigen Zustand,
        siehe Beispiele in docs/protokoll_pumpe.md)."""
        return self.write("SET", command_values={
            "value": (self._speed_rpm, self._running, self._clockwise)}, **kwargs)

    def set_speed(self, rpm, clockwise: bool = True, **kwargs):
        """Drehzahl setzen (0-600 rpm, wird geclampt). Laesst Start/Stop-Zustand unveraendert:
        laeuft die Pumpe bereits, uebernimmt sie die neue Drehzahl sofort; steht sie, bleibt sie
        stehen, bis start_pumping() aufgerufen wird."""
        self._speed_rpm = _clamp_rpm(rpm)
        self._clockwise = bool(clockwise)
        return self._send_state(**kwargs)

    def start_pumping(self, **kwargs):
        """Start: laeuft mit der zuletzt per set_speed() gesetzten (oder Default-)Drehzahl."""
        self._running = True
        return self._send_state(**kwargs)

    def read_speed(self, **kwargs):
        """Drehzahl lesen: fragt die tatsaechlich laufende Drehzahl/Zustand ab und aktualisiert
        die Observablen 'speed_rpm', 'running', 'clockwise' (und 'flow_ml_min', falls tubing/
        tubing_table konfiguriert sind)."""
        def to_observables(result):
            speed = int(result.parameters["speed"])
            observables = {
                "speed_rpm": speed,
                "running": bool(int(result.parameters["running"])),
                "clockwise": bool(int(result.parameters["clockwise"])),
            }
            try:
                observables["flow_ml_min"] = speed * self._ml_min_per_rpm()
            except ValueError:
                pass  # keine Schlauchkalibrierung konfiguriert - Drehzahl-Observablen trotzdem melden.
            self.update_observables(observables)
            return result
        cmd = self.query("READ")
        cmd.deferred_result.addCallback(to_observables)
        return cmd

    def continuous_flow(self, rate, **kwargs):
        rate = float(rate)
        clockwise = rate >= 0
        self.set_speed(abs(rate) / self._ml_min_per_rpm(), clockwise=clockwise, **kwargs)
        self.start_pumping(**kwargs)

    def dispense(self, rate, volume, **kwargs):
        if float(volume) == 0:
            return
        self.continuous_flow(rate, **kwargs)
        time_to_pump = 60 * abs(float(volume)) / abs(float(rate))

        def stop(result):
            self.stop_pumping(urgent=True)
            return result
        self.busy(TimeCondition("dispense finished", time_to_pump)).deferred_result.addBoth(stop)

    def stop_pumping(self, **kwargs):
        """Stop."""
        self._running = False
        return self._send_state(**kwargs)
