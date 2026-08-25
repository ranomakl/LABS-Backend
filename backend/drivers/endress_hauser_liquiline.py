# Treiber fuer den Endress+Hauser Liquiline CM442/CM448 Multiparameter-Messumformer, angebunden
# ueber Modbus RS485. Quelle: docs/handbuch_liquiline_modbus.pdf (Endress+Hauser SD01189C/07/EN/06.20,
# "Data transmission via Modbus") - ein echtes Herstellerhandbuch (anders als bei longer_wt600.py).
#
# TRANSMISSION-MODE-ENTSCHEIDUNG: Das Geraet unterstuetzt ueber RS485 sowohl Modbus RTU (binaer,
# CRC16, Abschnitt 3.2.2) als auch Modbus ASCII (druckbare Hex-Zeichen, LRC, Abschnitt 3.2.1). Dieser
# Treiber verwendet ASCII. Begruendung:
#   - Reiner Lesezugriff auf wenige Register (ein AI-Block = 4 Register = 8 Byte Nutzdaten) in
#     niedriger Frequenz (periodisches Pollen von Sensorwerten) - der ASCII-Overhead (ca. 2x mehr
#     Bytes auf der Leitung als RTU) ist bei den in diesem Handbuch vorgesehenen Baudraten
#     (1200-115200, Default 19200) fuer diesen Anwendungsfall irrelevant.
#   - ASCII-Frames sind durch ":" ... CRLF text-delimitiert (Abschnitt 3.2.1) und passen dadurch
#     vollstaendig in das bestehende BaseDeviceProtocol (LineReceiver mit delimiter="\r\n") - genau
#     das Muster, das bronkhorst_mfc.py schon nutzt. Es ist kein eigenes Protocol/Framer noetig (RTU
#     haette denselben Sonderaufwand wie longer_wt600.py gebraucht: eigener laengenbasierter Framer,
#     Rohbytes statt commandstring.encode()).
#   - ASCII-Frames sind reiner druckbarer ASCII-Text -> commandstring.encode() (UTF-8, siehe
#     backend/commands/commands.py) ist von Haus aus byte-treu, keine _RawFrame-Klasse noetig. Das
#     vermeidet genau den Fehler, der bei longer_wt600.py live auftrat: rohe Steuerzeichen in
#     Result.line liessen dort den Windows-Konsolen-Log-Observer mit UnicodeEncodeError abstuerzen
#     (siehe Kommentar in longer_wt600.py, WT600Parser). Bei ASCII kann das strukturell nicht
#     passieren.
#   - LRC ist algorithmisch einfacher als CRC16 (geringere Fehlererkennung, aber auf einem kurzen,
#     langsamen RS485-Sensor-Bus im Labor kein relevanter Nachteil gegenueber dem Robustheits- und
#     Einfachheitsgewinn).
# RTU waere die richtige Wahl, wenn hohe Durchsatzrate, viele Register oder viele Geraete am selben
# Bus gefragt waeren - hier nicht der Fall.
#
# QUELLENLAGE: Register-Adressen, Datentypen und Frame-Feldstruktur (Abschnitte 3.2.1, 3.5, 3.6,
# 3.8.1, 7.3.1, 7.3.2.2) sind direkt aus den Tabellen dieses Handbuchs uebernommen und daher
# byte-genau verifiziert (s.u.). Das Handbuch selbst enthaelt aber kein vollstaendiges, mit LRC/CRC16
# durchgerechnetes Beispiel-Frame (die FC08-Loopback-Beispielbytes in Abschnitt 3.8.3 haben keine
# Pruefsumme; LRC/CRC16 werden im Handbuch nur mit "see Modbus specification" referenziert, nicht
# selbst vorgerechnet). Die LRC-Implementierung ist deshalb stattdessen gegen die oeffentliche
# Modbus-Spezifikation verifiziert (s.u., Referenz-Testvektor) - nicht gegen ein Beispiel aus diesem
# Handbuch, das es fuer die Pruefsumme schlicht nicht gibt.
#
# VERIFIZIERT gegen die Tabellen dieses Handbuchs:
#   - ASCII-Rahmen: ":" ADRESSE(2 Zeichen) FUNKTION(2 Zeichen) DATEN(N Zeichen) LRC(2 Zeichen) CRLF
#     (Abschnitt 3.2.1)
#   - FC03 Read Holding Register: Request = Adresse+0x03+Startregister(2B)+Anzahl(2B);
#     Response = Adresse+0x03+ByteCount(1B)+Daten(ByteCount B) (Abschnitt 3.8.1)
#   - Registerzaehlung beginnt bei 0, keine +1-Verschiebung (Abschnitt 3.3/7.3.1) - so wie vom
#     Nutzer verlangt, exakt uebernommen: die in config.yml eingetragenen Registernummern werden
#     unveraendert als Modbus-Startadresse verwendet.
#   - AI-Geraetevariablen-Block (Value/Status/Unit), Abschnitt 3.7 (allgemeine Struktur) UND
#     Abschnitt 7.3.2.2 (konkrete Registernummern): MODBUS_AI_n: Value=FLOAT ab Register
#     (n-1)*4 (2 Register), Status=UNSIGNED8 auf Register (n-1)*4+2, Unit=UNSIGNED8 auf Register
#     (n-1)*4+3 - z.B. AI1: Register 0-3, AI2: Register 4-7, ... (Tabelle in 7.3.2.2 bis AI16
#     durchgerechnet und Formel bestaetigt).
#   - FLOAT = IEEE754, 4 Byte / 2 Register, Byte-Reihenfolge einstellbar ueber den Geraeteparameter
#     "Byte order" (Werkseinstellung "1-0-3-2", Abschnitt 3.5 + 4.1); der Optionsname selbst ist die
#     Uebertragungsreihenfolge der 4 Standard-IEEE754-Bytes (Byte3=MSB...Byte0=LSB) - z.B. "1-0-3-2"
#     heisst Byte1,Byte0,Byte3,Byte2 auf der Leitung, s. _decode_float() unten. Alle 4 Optionen aus
#     der Handbuchtabelle sind durch dieselbe generische Permutation abgedeckt und per Rundtrip-Test
#     gegen struct.pack('>f', ...) geprueft.
#   - UNSIGNED8-Werte (Status, Unit) belegen ein volles 16-Bit-Register; welches der beiden Bytes
#     (hoch/niedrig) den Wert traegt, ist im Handbuch fuer 1-Byte-Werte nicht explizit angegeben (die
#     Byte-Order-Tabelle in 3.5 behandelt nur FLOAT/INTEGER/STRING). ANNAHME (s. _decode_unsigned8):
#     genau eines der beiden Bytes ist 0, das andere traegt den Wert - das deckt beide moeglichen
#     Payload-Lagen robust ab, weil Status (0-3) und Unit-Code (0-254, s. Abschnitt 7.1) beide immer
#     kleiner als 256 sind und daher nie beide Registerbytes gleichzeitig sinnvoll belegen koennten.
#   - Unit-Codes (Abschnitt 7.1): vollstaendige Tabelle 0-177 sowie 254 uebernommen (UNIT_CODES).
#
# LRC verifiziert (oeffentliche Modbus-Spezifikation, nicht dieses Handbuch, s.o.):
#   - Kanonisches Modbus-ASCII-Beispiel "FC03, Slave 0x11, Start 0x006B, Anzahl 3" ergibt LRC=0x7E
#     (Summe 0x11+0x03+0x00+0x6B+0x00+0x03=0x82, LRC=(-0x82)&0xFF=0x7E) -> vollstaendiger Rahmen
#     ":1103006B00037E" byte-genau nachgerechnet und gegen die Treiberfunktion _lrc() verifiziert.

import re
import struct

from backend.commands import commandstate
from backend.commands.parser import BaseParser, ParserParameterFactory
from backend.commands.results import Result
from .transmitter_base import BaseDevice, SinglechannelBaseDevice, CommandParameterFactory


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


def _lrc(data: bytes) -> int:
    """Modbus-ASCII Longitudinal Redundancy Check: Zweierkomplement der Bytesumme. Verifiziert
    gegen das kanonische Beispiel der Modbus-Spezifikation (s. Dateikopf): LRC("11 03 00 6B 00 03")
    ergibt 0x7E."""
    return (-sum(data)) & 0xFF


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
    """Prueft Adress-Echo, LRC und Modbus-Exceptions eines ASCII-Antwortrahmens und dekodiert einen
    AI-Geraetevariablen-Block (Value/Status/Unit, 4 Register/8 Byte, s. Dateikopf) daraus."""

    def __init__(self, command, expect_bus_address: int, expect_function: int, byte_order: str, **kwargs):
        super().__init__(command)
        self.expect_bus_address = expect_bus_address
        self.expect_function = expect_function
        self.byte_order = byte_order

    def __call__(self, reply: Result):
        line = reply.line
        if not line.startswith(":"):
            return (commandstate.CommandResponseError(reply=reply, msg=f"Missing ':' start in {line!r}."),
                    commandstate.Retry)

        try:
            raw = bytes.fromhex(line[1:])
        except ValueError:
            return (commandstate.CommandResponseError(reply=reply, msg=f"Non-hex payload in {line!r}."),
                    commandstate.Retry)

        if len(raw) < 4:
            return (commandstate.CommandResponseError(reply=reply, msg=f"Frame too short: {line!r}."),
                    commandstate.Retry)

        body, received_lrc = raw[:-1], raw[-1]
        expected_lrc = _lrc(body)
        if expected_lrc != received_lrc:
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"LRC mismatch in {line!r}: got {received_lrc:02X}, "
                                          f"expected {expected_lrc:02X}."),
                    commandstate.Retry)

        address, function = body[0], body[1]
        if address != self.expect_bus_address:
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"Unexpected bus address in {line!r}: expected "
                                          f"{self.expect_bus_address}, got {address}."),
                    commandstate.Retry)

        if function == (self.expect_function | 0x80):
            exception_code = body[2] if len(body) > 2 else None
            exception_name = EXCEPTION_CODES.get(exception_code, "unknown")
            return (commandstate.CommandErrorError(
                        reply=reply, msg=f"Modbus exception {exception_code!r} ({exception_name}) "
                                          f"in {line!r}."),
                    commandstate.Fail)

        if function != self.expect_function:
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"Unexpected function code in {line!r}: expected "
                                          f"{self.expect_function:#04x}, got {function:#04x}."),
                    commandstate.Retry)

        byte_count = body[2]
        payload = body[3:]
        if len(payload) != byte_count or byte_count != 8:
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"Unexpected byte count in {line!r}: expected 8 "
                                          f"(one AI block = 4 registers), got {byte_count} "
                                          f"({len(payload)} payload bytes)."),
                    commandstate.Retry)

        registers = [(payload[2 * i] << 8) | payload[2 * i + 1] for i in range(4)]
        value = _decode_float(registers[0], registers[1], self.byte_order)
        status = _decode_unsigned8(registers[2])
        unit = _decode_unsigned8(registers[3])
        reply.parameters = {"value": str(value), "status": str(status), "unit": str(unit)}
        return reply, commandstate.Success


class Device(BaseDevice, SinglechannelBaseDevice):
    delimiter = "\r\n"
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
                            Geraetekonfiguration uebereinstimmen. "1-0-3-2" (Werkseinstellung),
                            "0-1-2-3", "2-3-0-1" oder "3-2-1-0".
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
        super().__init__(address, *args, **kwargs)

    def cmd_string(self, command_parameters: CommandParameterFactory) -> str:
        function = int(command_parameters.commandstring, 16)
        start_register, quantity = command_parameters.command_values["value"]
        pdu = bytes([self.bus_address, function,
                     (start_register >> 8) & 0xFF, start_register & 0xFF,
                     (quantity >> 8) & 0xFF, quantity & 0xFF])
        return f":{pdu.hex().upper()}{_lrc(pdu):02X}"

    def initial_commands(self):
        pass

    def final_commands(self):
        pass

    def handle_event(self, match: re.Match) -> None:
        pass

    def read_channel(self, channel, **kwargs):
        """Ein konfigurierter Kanal (Name aus config.yml `channels`) auslesen: liest den
        vollstaendigen AI-Block (4 Register) in einer Anfrage (s. Handbuch: Parameter muessen
        vollstaendig gelesen werden, sonst SLAVE_DEVICE_FAILURE) und aktualisiert die Observablen
        '<channel>_value', '<channel>_status' (0=Good...3=Not assigned, s. Abschnitt 3.7) und
        '<channel>_unit' (Text aus der Unit-Code-Tabelle, Abschnitt 7.1)."""
        try:
            start_register = self.channels[channel]
        except KeyError:
            raise ValueError(f"No register configured for channel {channel!r} "
                              f"(configured channels: {list(self.channels)}). "
                              f"Add it to this device's `channels` in config.yml.")

        def to_observables(result):
            status = int(result.parameters["status"])
            unit_code = int(result.parameters["unit"])
            observables = {
                f"{channel}_value": float(result.parameters["value"]),
                f"{channel}_status": STATUS_CODES.get(status, f"unknown ({status})"),
                f"{channel}_unit": UNIT_CODES.get(unit_code, f"unknown ({unit_code})"),
            }
            if status != 0:
                self.log.warn(f"Channel {channel!r} (register {start_register}) has status "
                              f"{observables[f'{channel}_status']!r}, value may not be usable.")
            self.update_observables(observables)
            return result

        cmd = self.query("READ_AI_BLOCK", command_values={"value": (start_register, 4)},
                         expect_bus_address=self.bus_address, byte_order=self.byte_order, **kwargs)
        cmd.deferred_result.addCallback(to_observables)
        return cmd

    def read_all_channels(self, **kwargs):
        """Alle in config.yml konfigurierten Kanaele nacheinander auslesen."""
        for channel in self.channels:
            self.read_channel(channel, **kwargs)
