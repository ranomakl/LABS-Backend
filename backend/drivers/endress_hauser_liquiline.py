# Treiber fuer den Endress+Hauser Liquiline CM442/CM448 Multiparameter-Messumformer, angebunden
# ueber Modbus RTU auf RS485 (Modul 485MB). Quelle: docs/handbuch_liquiline_modbus.pdf (Endress+Hauser
# SD01189C/07/EN/06.20, "Data transmission via Modbus").
#
# TRANSMISSION MODE = RTU (seit 12.10.2026). Vorgeschichte: Der Treiber sprach zunaechst Modbus ASCII
# (Begruendung damals: textdelimitierte Frames passen in den LineReceiver des Backends). Das Geraet
# hat im Labor vom 30.09. bis 12.10.2026 auf KEINE ASCII-Anfrage reagiert - bei allen Baudraten,
# Paritaeten, Adressen, zwei Adaptern, beiden Polungen, mit/ohne GND und Terminierung. Nach dem
# Umstellen des Geraets auf RTU (Menue Setup/General settings/Extended setup/Modbus) kamen am
# 12.10.2026 sofort gueltige Antworten (63 FC03-Antworten in 20 s bei 19200 8E1, Adresse 247,
# Adapter BG01XFU4). Der ASCII-Modus dieses Geraets funktioniert offenbar nicht; E+H selbst hat nur
# RTU getestet (Case 01976469). Deshalb RTU, mit binaerem Framer nach dem Muster von longer_wt600.py.
#
# RTU-Rahmen (Abschnitt 3.2.2): ADRESSE(1) FUNKTION(1) DATEN(N) CRC16(2, Low-Byte zuerst).
#   Anfrage FC03:  addr 03 start_hi start_lo count_hi count_lo crc_lo crc_hi            (8 Byte)
#   Antwort FC03:  addr 03 bytecount daten[bytecount] crc_lo crc_hi                      (5+bytecount)
#   Exception:     addr 83 code crc_lo crc_hi                                            (5 Byte)
# Rahmengrenzen definiert RTU ueber Sendepausen (3,5 Zeichen); hier wird stattdessen laengenbasiert
# geframed (Antwortlaenge ist aus Funktionscode und Bytecount bekannt), was bei einem einzigen Master
# und Anfrage/Antwort-Betrieb gleichwertig ist. CRC16: Polynom 0xA001 (reflektiert 0x8005), Start 0xFFFF
# - verifiziert gegen die am Geraet gemessene Antwort F7 03 02 00 00 70 51 (CRC 0x5170) und das
# kanonische Spezifikationsbeispiel (s. backend/test/test_liquiline_rtu.py).
#
# Rohbytes im Backend: Command.__init__ (backend/commands/commands.py) ruft commandstring.encode()
# (UTF-8) auf, was fuer Bytes >= 0x80 nicht byte-treu waere -> _RawFrame (str-Subklasse, .encode()
# liefert die Rohbytes; Text ist die Hex-Anzeige fuer Logs). Antworten tragen die Rohbytes in
# reply.raw, reply.line ist nur die Hex-Anzeige (Konsolen-Logs vertragen keine Steuerzeichen, s.
# longer_wt600.py).
#
# AM GERAET VERIFIZIERT 12.10.2026 (Modbus RTU, Firmware-Stand des Laborgeraets):
#   - Registerzaehlung 0-basiert, FC03 ab Register 0 liefert AI1 (Value/Status/Unit = 4 Register).
#   - AI-Block: Register 0-1 Value (FLOAT), 2 Status (UNSIGNED8, Low-Byte), 3 Unit (UNSIGNED8,
#     Low-Byte). Gemessen: [0, 0, 2, 53] = Wert 0.0, Status 2 "Bad", Einheit 53 "pH".
#   - Byte order "1-0-3-2" (Werkseinstellung) bestaetigt ueber Register 506/507 MODBUS_WATCHDOG:
#     Drahtbytes 00 00 40 A0 -> 5.0 s (Geraetemenue: Watchdog 5 s). _decode_float(0, 16544, "1-0-3-2") == 5.0.
#   - Status-Codes (Abschnitt 3.7): 0 Good, 1 Uncertain, 2 Bad, 3 Not assigned (= keine Datenquelle
#     unter Setup/Outputs/Modbus/AI n gewaehlt). Ohne Mapping liefert jedes AI Status 3, Wert 0.
#   - Konfigurationsregister (Tabelle 7.3.x): 501 RS485_BAUDRATE = 4 (19200), 503 RS485_PARITY = 0
#     (Even), 504 RS485_ENABLE = 1, 505 MODBUS_MODE = 0 (RTU), 509 ETHERNET_ENABLE = 1,
#     510/511 IP = 169.254.233.247 (Link-Local), 512/513 Netzmaske 255.255.255.0.
#   - Unit-Codes (Abschnitt 7.1): vollstaendige Tabelle 0-177 sowie 254 uebernommen (UNIT_CODES).
#
# ANNAHME (unveraendert): UNSIGNED8-Werte (Status, Unit) belegen ein volles 16-Bit-Register; gelesen
# wird das Byte, das ungleich 0 ist (am Geraet: Low-Byte). Status (0-3) und Unit-Code (0-254) sind
# immer < 256, beide Bytes koennen also nie gleichzeitig sinnvoll belegt sein.

import re
import struct

from backend.commands import commandstate
from backend.commands.parser import BaseParser, ParserParameterFactory
from backend.commands.results import Result
from .transmitter_base import (BaseDevice, SinglechannelBaseDevice, CommandParameterFactory,
                               BaseDeviceProtocol, BaseDeviceProtocolFactory)


FC_READ_HOLDING_REGISTERS = 0x03

# Unit-Codes aus Abschnitt 7.1 "Unit codes" des Handbuchs, vollstaendig uebernommen (0-177, 254;
# Luecken 178-253 sind im Handbuch nicht belegt).
UNIT_CODES = {
    0: "None", 1: "1/K", 2: "nAs", 3: "uAs", 4: "As", 5: "ppb", 6: "ppm", 7: "%", 8: "%SAT",
    9: "1/mm", 10: "1/cm", 11: "1/m", 12: "g/kg", 13: "ppmVol", 14: "%Vol", 15: "%/K",
    16: "%/uV", 17: "%/mV", 18: "%/V", 19: "uS", 20: "mS", 21: "S", 22: "pA", 23: "nA",
    24: "uA", 25: "mA", 26: "A", 27: "nA/(mg/l)", 28: "A/(kg/m3)", 29: "A/Pa",
    30: "pA/hPa", 31: "A/hPa", 32: "deg", 33: "FNU", 34: "NTU", 35: "Hz", 36: "1/min", 37: "1/h",
    38: "1/d", 39: "KByte", 40: "mm", 41: "cm", 42: "dm", 43: "m", 44: "km", 45: "g/ml",
    46: "ug/l", 47: "mg/l", 48: "g/l", 49: "kg/l", 50: "kg/m3", 51: "ppb", 52: "ppm",
    53: "pH", 54: "mm/s", 55: "mm/min", 56: "mm/h", 57: "mm/d", 58: "Pa", 59: "hPa", 60: "mbar",
    61: "Pa/A", 62: "PSU", 63: "mOhm", 64: "Ohm", 65: "kOhm", 66: "MOhm", 67: "GOhm",
    68: "rH", 69: "uS/mm", 70: "nS/cm", 71: "uS/cm", 72: "mS/cm", 73: "S/cm",
    74: "uS/m", 75: "mS/m", 76: "S/m", 77: "kS/m", 78: "MS/m", 79: "nOhm*m",
    80: "uOhm*m", 81: "mOhm*m", 82: "Ohm*m", 83: "kOhm*m", 84: "MOhm*m",
    85: "GOhm*m", 86: "Ohm*cm", 87: "kOhm*cm", 88: "MOhm*cm", 89: "degC", 90: "K",
    91: "degC (delta)", 92: "K (delta)", 93: "us", 94: "ms", 95: "s", 96: "min", 97: "h", 98: "d",
    99: "week(s)", 100: "month(s)", 101: "l/s", 102: "m3/s", 103: "l/min", 104: "m3/min",
    105: "l/h", 106: "m3/h", 107: "l/d", 108: "m3/d", 109: "uV", 110: "mV",
    111: "V", 112: "mV/%", 113: "V/%", 114: "mV/pH", 115: "V/pH", 116: "ml", 117: "l",
    118: "m3", 119: "inch", 120: "ft", 121: "yd", 122: "mi", 123: "in/s", 124: "inch/min",
    125: "inch/h", 126: "inch/d", 127: "degF", 128: "degF (delta)", 129: "gps", 130: "cfs",
    131: "mgs", 132: "gpm", 133: "cfm", 134: "mgm", 135: "gph", 136: "cfh", 137: "mgh", 138: "gpd",
    139: "cfd", 140: "mgd", 141: "gal", 142: "cf", 143: "mol/m3", 144: "mol/l", 145: "%TS",
    146: "bar", 147: "nm", 148: "m/s", 149: "ft/s", 150: "MByte", 151: "Byte", 152: "GByte",
    153: "pA/(mg/l)", 154: "kg/mol", 155: "g/mol", 156: "FTU", 157: "TE/F", 158: "ASBC",
    159: "EBC", 160: "deg", 161: "mg/l %", 162: "AU", 163: "%T", 164: "OD", 165: "ml/min",
    166: "eq", 167: "eq/m3", 168: "eq/l", 169: "eq/gal", 170: "degC/s", 171: "degC/min",
    172: "FAU", 173: "Ah", 174: "m/h", 175: "1/Pa", 176: "1/hPa", 177: "1/MPa",
    254: "user defined textual unit",
}

# Status-Codes aus Abschnitt 3.7 "Device variables with status" des Handbuchs.
STATUS_CODES = {0: "Good", 1: "Uncertain", 2: "Bad", 3: "Not assigned"}

# Modbus-Exception-Codes aus Abschnitt 3.3 des Handbuchs.
EXCEPTION_CODES = {
    0x01: "ILLEGAL_FUNCTION",
    0x02: "ILLEGAL_DATA_ADDRESS",
    0x03: "ILLEGAL_DATA_VALUE / SLAVE_DEVICE_FAILURE",
    0x04: "SLAVE_DEVICE_FAILURE",
}


def _crc16(data: bytes) -> bytes:
    """Modbus-RTU-CRC16 (Polynom 0xA001, Start 0xFFFF), Rueckgabe in Drahtreihenfolge (Low-Byte zuerst).
    Verifiziert gegen die Geraeteantwort F7 03 02 00 00 -> 70 51 (12.10.2026)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc.to_bytes(2, "little")


def _build_request(bus_address: int, function: int, start_register: int, quantity: int) -> bytes:
    pdu = bytes([bus_address, function,
                 (start_register >> 8) & 0xFF, start_register & 0xFF,
                 (quantity >> 8) & 0xFF, quantity & 0xFF])
    return pdu + _crc16(pdu)


def expected_frame_length(buffer: bytes) -> int | None:
    """Laenge des RTU-Antwortrahmens, der am Anfang von `buffer` steht, oder None, wenn dafuer noch
    Bytes fehlen. Exception-Antwort (Funktion | 0x80): 5 Byte. FC03: 3 + Bytecount + 2."""
    if len(buffer) < 2:
        return None
    if buffer[1] & 0x80:
        return 5
    if len(buffer) < 3:
        return None
    return 3 + buffer[2] + 2


class _RawFrame(str):
    """str-Subklasse: Text = Hex-Anzeige (fuer Logs), .encode() = die echten Rohbytes (s. Dateikopf)."""

    def __new__(cls, raw: bytes):
        obj = super().__new__(cls, raw.hex(" ").upper())
        obj._raw = bytes(raw)
        return obj

    def encode(self, *args, **kwargs):
        return self._raw


class LiquilineProtocol(BaseDeviceProtocol):
    """Laengenbasierter RTU-Framer statt LineReceiver. Bytes vor der erwarteten Busadresse werden als
    Rauschen verworfen (Resynchronisation nach Stoerung/Teilrahmen)."""

    def __init__(self):
        super().__init__()
        self._buffer = bytearray()

    def dataReceived(self, data):
        self._buffer.extend(data)
        while True:
            expected = self.device.bus_address
            while self._buffer and self._buffer[0] != expected:
                del self._buffer[0]
            length = expected_frame_length(self._buffer)
            if length is None or len(self._buffer) < length:
                return
            frame = bytes(self._buffer[:length])
            del self._buffer[:length]
            self.frameReceived(frame)

    def rawDataReceived(self, data):
        pass  # ungenutzt, dataReceived() oben delegiert nie in den LineReceiver

    def frameReceived(self, frame: bytes):
        result = Result(frame.hex(" ").upper())
        result.raw = frame
        self.device.receive(result)

    def write_command(self, command_object):
        self.transport.write(command_object.bytestring)   # kein sendLine: RTU hat kein Trennzeichen
        self.device.log.info(f"Wrote {command_object.parameters.commandstring} to device.")


class LiquilineProtocolFactory(BaseDeviceProtocolFactory):
    protocol = LiquilineProtocol


def _byte_order_permutation(byte_order: str) -> list:
    """"1-0-3-2" wird zu [1, 0, 3, 2]. Der Optionsname selbst listet, in Uebertragungsreihenfolge,
    welches Standard-IEEE754-Byte (3=MSB...0=LSB) an welcher Drahtposition steht - direkt aus der
    Tabelle in Abschnitt 3.5 abgelesen (s. Dateikopf-Kommentar)."""
    return [int(x) for x in byte_order.split("-")]


def _decode_float(register0: int, register1: int, byte_order: str) -> float:
    """Zwei aufeinanderfolgende Register (Value, Value+1) zu einem IEEE754-Float dekodieren, gemaess
    dem konfigurierten Byte-order-Geraeteparameter (Default "1-0-3-2"). Per Rundtrip-Test gegen
    struct.pack('>f', ...) fuer alle vier Handbuch-Optionen verifiziert."""
    wire_bytes = bytes([register0 >> 8, register0 & 0xFF, register1 >> 8, register1 & 0xFF])
    order = _byte_order_permutation(byte_order)
    byte_of = {}
    for wire_position, byte_index in enumerate(order):
        byte_of[byte_index] = wire_bytes[wire_position]
    standard_bytes = bytes([byte_of[3], byte_of[2], byte_of[1], byte_of[0]])
    return struct.unpack(">f", standard_bytes)[0]


def _decode_unsigned8(register: int) -> int:
    """Ein UNSIGNED8-Wert (Status, Unit) belegt ein volles 16-Bit-Register. Siehe ANNAHME im
    Dateikopf: genau eines der beiden Bytes traegt den Wert, das andere ist 0 - robust fuer den
    gesamten gueltigen Wertebereich (Status 0-3, Unit-Code 0-254, s. Abschnitt 7.1), unabhaengig
    davon, in welchem der beiden Bytes das Geraet den Wert tatsaechlich ablegt."""
    low, high = register & 0xFF, (register >> 8) & 0xFF
    return low if high == 0 else high


class LiquilineParser(BaseParser):
    """Prueft Adresse, CRC16 und Modbus-Exception eines RTU-Antwortrahmens (reply.raw, gesetzt von
    LiquilineProtocol.frameReceived) und dekodiert einen AI-Geraetevariablen-Block (Value/Status/Unit,
    4 Register/8 Byte, s. Dateikopf)."""

    def __init__(self, command, expect_bus_address: int, expect_function: int, byte_order: str,
                 channel_map: dict = None, **kwargs):
        """channel_map: {Startregister des AI-Blocks: Kanalname}. Ist es gesetzt, heissen die Parameter
        <kanal>_value/_status/_unit und die Antwort darf mehrere AI-Bloecke enthalten (eine Anfrage fuer
        alle Kanaele, s. Device.read_all_channels). Ohne channel_map: genau ein Block, Parameter
        value/status/unit."""
        super().__init__(command)
        self.expect_bus_address = expect_bus_address
        self.expect_function = expect_function
        self.byte_order = byte_order
        self.channel_map = {int(k): v for k, v in (channel_map or {}).items()}

    def __call__(self, reply: Result):
        try:
            frame = reply.raw
        except AttributeError:
            return (commandstate.CommandResponseError(reply=reply, msg=f"Reply has no raw frame bytes: {reply.line!r}."),
                    commandstate.Retry)
        shown = reply.line
        if len(frame) < 5:
            return (commandstate.CommandResponseError(reply=reply, msg=f"Frame too short: {shown!r}."),
                    commandstate.Retry)

        body, received_crc = frame[:-2], frame[-2:]
        expected_crc = _crc16(body)
        if expected_crc != received_crc:
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"CRC mismatch in {shown!r}: got {received_crc.hex()}, "
                                          f"expected {expected_crc.hex()}."),
                    commandstate.Retry)

        address, function = body[0], body[1]
        if address != self.expect_bus_address:
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"Unexpected bus address in {shown!r}: expected "
                                          f"{self.expect_bus_address}, got {address}."),
                    commandstate.Retry)

        if function == (self.expect_function | 0x80):
            exception_code = body[2] if len(body) > 2 else None
            exception_name = EXCEPTION_CODES.get(exception_code, "unknown")
            return (commandstate.CommandErrorError(
                        reply=reply, msg=f"Modbus exception {exception_code!r} ({exception_name}) "
                                          f"in {shown!r}."),
                    commandstate.Fail)

        if function != self.expect_function:
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"Unexpected function code in {shown!r}: expected "
                                          f"{self.expect_function:#04x}, got {function:#04x}."),
                    commandstate.Retry)

        byte_count = body[2]
        payload = body[3:]
        if len(payload) != byte_count or byte_count == 0 or byte_count % 8 != 0:
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"Unexpected byte count in {shown!r}: expected a multiple of 8 "
                                          f"(one AI block = 4 registers), got {byte_count} "
                                          f"({len(payload)} payload bytes)."),
                    commandstate.Retry)
        blocks = byte_count // 8
        if not self.channel_map and blocks != 1:
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"Expected exactly one AI block in {shown!r}, got {blocks}."),
                    commandstate.Retry)

        start_register = self.command.parameters.command_values["value"][0]
        parameters = {}
        for block in range(blocks):
            chunk = payload[8 * block: 8 * block + 8]
            registers = [(chunk[2 * i] << 8) | chunk[2 * i + 1] for i in range(4)]
            value = _decode_float(registers[0], registers[1], self.byte_order)
            status = _decode_unsigned8(registers[2])
            unit = _decode_unsigned8(registers[3])
            if self.channel_map:
                channel = self.channel_map.get(start_register + 4 * block)
                if channel is None:
                    continue   # Register ohne konfigurierten Kanal (Luecke zwischen zwei AI-Bloecken)
                prefix = f"{channel}_"
            else:
                prefix = ""
            parameters.update({f"{prefix}value": str(value), f"{prefix}status": str(status), f"{prefix}unit": str(unit)})
        reply.parameters = parameters
        return reply, commandstate.Success


class Device(BaseDevice, SinglechannelBaseDevice):
    protocol_factory_class = LiquilineProtocolFactory
    # Werkseinstellung des Geraets (Abschnitt 4.1) und am 12.10.2026 am Geraet bestaetigt; config.yml
    # kann einzelne Schluessel ueberschreiben (serial_parameters).
    serial_parameters = {"baudrate": 19200, "bytesize": 8, "parity": "E", "stopbits": 1}
    command_parameter_factory = CommandParameterFactory(command_execution_time=.1)
    replies_commands = True
    log_name = "Endress+Hauser Liquiline CM44x"

    commands = {
        "READ_AI_BLOCK": [
            f"{FC_READ_HOLDING_REGISTERS:02X}",
            ParserParameterFactory(parserclass=LiquilineParser, expect_function=FC_READ_HOLDING_REGISTERS),
        ],
    }

    def __init__(self, address, *args, bus_address: int = 247, byte_order: str = "1-0-3-2",
                 channels: dict = None, **kwargs):
        """
        :param bus_address: Modbus-Busadresse des Geraets (1-247; Werkseinstellung 247, s. Abschnitt
                             4.1) - NICHT zu verwechseln mit `address` (serielle Schnittstelle/
                             TCP-Endpunkt der Dummy-Umgebung).
        :param byte_order: Geraeteparameter "Byte order" (Menu: Setup/General settings/Extended
                            setup/Modbus/Settings, Abschnitt 4.1), muss mit der tatsaechlichen
                            Geraetekonfiguration uebereinstimmen. "1-0-3-2" (Werkseinstellung, am
                            Laborgeraet 12.10.2026 bestaetigt), "0-1-2-3", "2-3-0-1" oder "3-2-1-0".
        :param channels: {Kanalname: Register} - Register ist die 0-basierte Modbus-Startadresse des
                          zugehoerigen AI-Geraetevariablen-Blocks (Value/Status/Unit, s. Dateikopf),
                          wie sie am Geraet unter Setup/Outputs/Modbus/AI 1...AI 16 konfiguriert
                          wurde (welcher physische Sensorkanal/welche Messgroesse dahinter steckt,
                          wird am Geraetemenue eingestellt - beim Umstecken eines Sensors dort UND
                          in dieser config.yml anpassen, nicht im Treiber-Code).
        """
        self.bus_address = int(bus_address)
        self.byte_order = byte_order
        self.channels = {name: int(register) for name, register in (channels or {}).items()}
        self._last_status = {}
        self._measuring = None
        super().__init__(address, *args, **kwargs)

    def cmd_string(self, command_parameters: CommandParameterFactory) -> str:
        function = int(command_parameters.commandstring, 16)
        start_register, quantity = command_parameters.command_values["value"]
        return _RawFrame(_build_request(self.bus_address, function, start_register, quantity))

    def initial_commands(self):
        pass

    def final_commands(self):
        # Wird aus device.stop()/shutdown() gerufen (Experimentende, Abbruch, Fehlerpfad): Dauer-Messung
        # beenden. Sendet selbst nichts - das Geraet hat keinen Abschaltbefehl, es wird nur gelesen.
        self.stop_measuring()

    def handle_event(self, match: re.Match) -> None:
        pass

    def update_observables(self, observables: dict, timestamp: float = None):
        # base.receive() reicht die Parser-Parameter als Observablen durch. Kanalbezogene Werte
        # (<kanal>_value/_status/_unit) werden hier in float bzw. Klartext umgesetzt; die rohen,
        # kanallosen Schluessel (value/status/unit, nur ohne channel_map) werden verworfen.
        converted = {}
        for key, raw in observables.items():
            if key in ("value", "status", "unit"):
                continue
            if key.endswith("_value"):
                converted[key] = float(raw)
            elif key.endswith("_status"):
                code = int(raw)
                converted[key] = STATUS_CODES.get(code, f"unknown ({code})")
                channel = key[:-len("_status")]
                if converted[key] != self._last_status.get(channel):     # nur bei Aenderung loggen
                    self._last_status[channel] = converted[key]
                    (self.log.info if code == 0 else self.log.warn)(
                        "Channel {channel!r} status is now {status!r}", channel=channel, status=converted[key])
            elif key.endswith("_unit"):
                code = int(raw)
                converted[key] = UNIT_CODES.get(code, f"unknown ({code})")
            else:
                converted[key] = raw
        if not converted:
            return
        if timestamp is None:
            super().update_observables(converted)
        else:
            super().update_observables(converted, timestamp)

    def _block_request(self, channels: dict) -> tuple:
        """(Startregister, Anzahl Register, channel_map) fuer EINE FC03-Anfrage ueber alle `channels`
        (zusammenhaengend oder mit Luecken; max. 125 Register je Modbus-Anfrage)."""
        registers = sorted(channels.values())
        start, quantity = registers[0], registers[-1] + 4 - registers[0]
        if quantity > 125:
            raise ValueError(f"Channels span {quantity} registers, Modbus allows 125 per request: {channels}")
        return start, quantity, {register: name for name, register in channels.items()}

    def _query_blocks(self, channels: dict, write_function=None, **kwargs):
        start, quantity, channel_map = self._block_request(channels)
        return (write_function or self.query)("READ_AI_BLOCK", command_values={"value": (start, quantity)},
                                              expect_bus_address=self.bus_address, byte_order=self.byte_order,
                                              channel_map=channel_map, **kwargs)

    def read_channel(self, channel, **kwargs):
        """Einen konfigurierten Kanal (Name aus config.yml `channels`) einmal auslesen: ein AI-Block
        (4 Register, Value/Status/Unit) in einer Anfrage. Observablen '<channel>_value' (float),
        '<channel>_status' (Good/Uncertain/Bad/Not assigned), '<channel>_unit' (Text, Abschnitt 7.1)."""
        try:
            register = self.channels[channel]
        except KeyError:
            raise ValueError(f"No register configured for channel {channel!r} "
                              f"(configured channels: {list(self.channels)}). "
                              f"Add it to this device's `channels` in config.yml.")
        return self._query_blocks({channel: register}, **kwargs)

    def read_all_channels(self, **kwargs):
        """Alle konfigurierten Kanaele mit EINER Anfrage auslesen (z.B. Register 0-11 fuer AI1-AI3)."""
        return self._query_blocks(self.channels, **kwargs)

    def start_measuring(self, interval=2.0, condition=None, **kwargs):
        """Alle konfigurierten Kanaele fortlaufend lesen (alle `interval` Sekunden, eine Anfrage je
        Zyklus), bis stop_measuring() bzw. das Experimentende (final_commands) sie beendet. Laeuft wie
        das Netzteil-Polling als RepeatedCommand (dringend, auch im Busy/Waiting-Zustand des Geraets),
        sonst bliebe die Abfrage nach dem Ende der Befehlsliste in der Warteschlange haengen.
        config.yml: [liquiline, start_measuring, [], {interval: 2.0}]. Am Geraet dauert ein Zyklus ~0,1 s."""
        self.stop_measuring()
        interval = max(0.5, float(interval))
        start, quantity, channel_map = self._block_request(self.channels)
        self._measuring = self.repeated_query("READ_AI_BLOCK", interval, condition,
                                              command_values={"value": (start, quantity)},
                                              expect_bus_address=self.bus_address, byte_order=self.byte_order,
                                              channel_map=channel_map, inter_command_time=.001)
        return self._measuring

    def stop_measuring(self, **kwargs):
        measuring = getattr(self, "_measuring", None)
        if measuring is not None:
            measuring.stop_running()
            self._measuring = None
