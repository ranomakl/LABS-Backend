# Treiber fuer Bronkhorst EL-FLOW Prestige FG-201CV (Massenflussmessgeraet/-regler),
# angebunden ueber RS485/USB-Seriell, Protokoll FLOW-BUS/ProPar ASCII.
# Quelle: docs/handbuch_bronkhorst.pdf, Abschnitte 3.3-3.9 (3.9.1-3.9.4 enthalten die
# vollstaendigen, byte-genauen Beispiel-Frames, gegen die dieser Treiber verifiziert ist).
# HINWEIS: Abschnitt 3.10 ("Beispiele - ProPar verbessertes Binaerprotokoll") behandelt ein
# ANDERES, binaeres Protokoll und ist fuer diesen Treiber NICHT relevant.
#
# AENDERUNGSHISTORIE (grob):
# 1. Platzhalter-Frames mit NotImplementedError-Sperre.
# 2. Frame = Knoten+Befehl+Prozess(plain)+Parameter(plain)+Daten angenommen - falsch, siehe 3.
# 3. Nutzer-Handbuchzeile (Setpoint) zeigte: Parameterbyte ist (Typ<<5)|Parameternummer, nicht
#    die reine Parameternummer -> korrigiert, Setpoint-Schreiben danach byte-exakt bestaetigt.
# 4. DIESE Fassung, nach Lesen von Abschnitt 3.7-3.9 des Handbuchs: zwei weitere, bis dahin
#    unentdeckte Fehler behoben:
#    a) Lesebefehle (Befehl 04) brauchen ZWEI Prozess/Parameter-Byte-Paare: ein "Echo/Index"-Paar
#       (wird vom Geraet unveraendert in die Antwort kopiert, zur Korrelation bei mehreren
#       gleichzeitigen Anfragen) UND das eigentliche Prozess/Parameter-Paar. Alle drei
#       Handbuchbeispiele (Setpoint/Messwert/Zaehler lesen) nutzen durchgaengig einen FESTEN
#       Echo-Index von 1, unabhaengig von der tatsaechlichen Parameternummer (bei "Messwert",
#       FBnr=0, wird trotzdem Index=1 verwendet) - siehe READ_ECHO_INDEX unten.
#    b) Die Antwort auf einen Lesebefehl beginnt NICHT direkt mit dem Wert nach der Node-Adresse,
#       sondern: Node + Befehl(02) + geechotes Prozess/Parameter-Paar + erst dann der Wert.
#       c) Die Antwort auf einen Schreibbefehl (Setpoint) ist keine "stille" Bestaetigung, sondern
#       eine echte Statusmeldung (Node + 00 + Status + Index). Bisher wurde das mit einem
#       SuccessParser/replies_commands=False vorgetaeuscht ("NO RESULT") - jetzt wird die
#       Statusmeldung real geparst und bei Status != 0 als Fehler behandelt.
#    Der Float-Typ-Code fuer den Counter ist jetzt durch Abschnitt 3.4.2 (Parametertypen-Tabelle)
#    UND das Zaehlerwert-Beispiel (3.9.4) bestaetigt: TYPE_FLOAT = 2 (Byte 0x40), Big-Endian.
#    read_counter() ist deshalb nicht mehr gesperrt.
#
# Frameformat WRITE (Befehl 01, Abschnitt 3.7):
#   ":" LEN NODE "01" PROZESS PARAMETER WERT "\r\n"
# Frameformat READ-Anfrage (Befehl 04, Abschnitt 3.8):
#   ":" LEN NODE "04" ECHO_PROZESS ECHO_PARAMETER PROZESS PARAMETER "\r\n"
# Frameformat READ-Antwort (Abschnitt 3.8, wird als Befehl "02" gesendet):
#   ":" LEN NODE "02" ECHO_PROZESS ECHO_PARAMETER WERT "\r\n"
# Frameformat WRITE-Antwort/Statusmeldung (Abschnitt 3.6):
#   ":" "04" NODE "00" STATUS INDEX "\r\n"    (STATUS=00 -> kein Fehler)
# Alle Bytes als 2 Hex-Zeichen. LEN = Byte-Anzahl NACH dem Laengenbyte selbst.
# Prozessbyte = c ppppppp (c=Verkettungsbit, hier immer 0, p=Prozessnummer, 7 Bit)
# Parameterbyte = c tt ppppp (c=Verkettungsbit, tt=Typ (2 Bit), p=Parameternummer, 5 Bit)
#
# VERIFIZIERT byte-genau gegen docs/handbuch_bronkhorst.pdf, Abschnitte 3.9.1-3.9.4:
#   Setpoint schreiben (50%): :06030101213E80  (3.9.1)
#   Setpoint lesen (Anfrage): :06030401210121  (3.9.2)
#   Messwert lesen (Anfrage): :06030401210120  (3.9.3)
#   Zaehler lesen (Anfrage):  :06030468416841  (3.9.4)

from .mfc_base import BaseDevice, SinglechannelBaseDevice, CommandParameterFactory
from backend.commands.parser import ParserParameterFactory, REParser
import re
import struct


CMD_WRITE = "01"
CMD_READ = "04"

TYPE_CHAR = 0     # 1 Byte, 0...255
TYPE_UINT16 = 1   # 2 Byte, 0...65535 ("integer" im Handbuch) - verifiziert (3.9.1-3.9.3)
TYPE_FLOAT = 2    # 4 Byte, IEEE754 Big-Endian - verifiziert (3.4.2 Parametertypen-Tabelle + 3.9.4)
TYPE_STRING = 3   # variable Laenge

READ_ECHO_INDEX = 1  # konstanter Korrelationsindex fuer Lesebefehle, siehe Kommentar oben


def _pack_parameter_byte(data_type: int, parameter: int) -> int:
    """FLOW-BUS-Parameterbyte: c(1 Bit, hier immer 0) + Typ(2 Bit) + Parameternummer(5 Bit).
    Generisch fuer weitere Parameter nutzbar - einfach mit neuem (type, parameter) aufrufen."""
    return ((data_type & 0x3) << 5) | (parameter & 0x1F)


def _rw_pair(process: int, data_type: int, parameter: int) -> str:
    """Ein Prozess/Parameter-Byte-Paar (4 Hex-Zeichen), Baustein fuer WRITE- und READ-Frames.
    Generisch fuer weitere Parameter nutzbar."""
    return f"{process & 0x7F:02X}{_pack_parameter_byte(data_type, parameter):02X}"


def _hex_to_int16(hexvalue: str) -> int:
    return int(hexvalue, 16)


def _hex_to_float32(hexvalue: str) -> float:
    return struct.unpack(">f", bytes.fromhex(hexvalue))[0]  # Big-Endian, verifiziert (3.9.4)


class Device(BaseDevice, SinglechannelBaseDevice):
    delimiter = "\r\n"
    serial_parameters = {"baudrate": 38400}  # am Geraet verifiziert (bei 187500 keine Antwort)
    command_parameter_factory = CommandParameterFactory(command_execution_time=.1)
    replies_commands = True  # alle Befehle bekommen jetzt eine echte Antwort (s. Historie oben)
    log_name = "Bronkhorst EL-FLOW Prestige FG-201CV"

    PROCESS_SETPOINT, PARAMETER_SETPOINT, TYPE_SETPOINT = 1, 1, TYPE_UINT16
    PROCESS_MEASURE, PARAMETER_MEASURE, TYPE_MEASURE = 1, 0, TYPE_UINT16
    PROCESS_COUNTER, PARAMETER_COUNTER, TYPE_COUNTER = 104, 1, TYPE_FLOAT

    commands = {
        "SET_SETPOINT": [
            f"{CMD_WRITE}{_rw_pair(PROCESS_SETPOINT, TYPE_SETPOINT, PARAMETER_SETPOINT)}",
            ParserParameterFactory(parserclass=REParser,
                                    pattern=r":(?P<len>[0-9A-F]{2})(?P<node>[0-9A-F]{2})00"
                                            r"(?P<status>[0-9A-F]{2})(?P<statusindex>[0-9A-F]{2})",
                                    expected_values={"status": "00"}),
        ],
        "READ_MEASURE": [
            f"{CMD_READ}{_rw_pair(PROCESS_MEASURE, TYPE_MEASURE, READ_ECHO_INDEX)}"
            f"{_rw_pair(PROCESS_MEASURE, TYPE_MEASURE, PARAMETER_MEASURE)}",
            r":(?P<len>[0-9A-F]{2})(?P<node>[0-9A-F]{2})02[0-9A-F]{4}(?P<value>[0-9A-F]{4})",
        ],
        "READ_COUNTER": [
            f"{CMD_READ}{_rw_pair(PROCESS_COUNTER, TYPE_COUNTER, READ_ECHO_INDEX)}"
            f"{_rw_pair(PROCESS_COUNTER, TYPE_COUNTER, PARAMETER_COUNTER)}",
            r":(?P<len>[0-9A-F]{2})(?P<node>[0-9A-F]{2})02[0-9A-F]{4}(?P<value>[0-9A-F]{8})",
        ],
    }

    def __init__(self, address, *args, node: str = "80", max_flow_ml_min: float = 100.0, **kwargs):
        """
        :param node: FLOW-BUS-Knotenadresse des Geraets (aus config.yml, 2 Hex-Zeichen, z.B. "03")
        :param max_flow_ml_min: Messbereichsendwert des Geraets in mL/min (aus config.yml, vom
                                 Typenschild/Kalibrierschein), fuer die Umrechnung
                                 Prozent <-> mL/min
        """
        self.node = node
        self.max_flow_ml_min = max_flow_ml_min
        super().__init__(address, *args, **kwargs)

    def cmd_string(self, command_parameters: CommandParameterFactory) -> str:
        data = ""
        if "value" in command_parameters.command_values:
            data = f"{command_parameters.command_values['value']:04X}"
        body = f"{self.node}{command_parameters.commandstring}{data}"
        length = f"{len(body) // 2:02X}"
        return f":{length}{body}"

    def initial_commands(self):
        pass

    def final_commands(self):
        self.stop_flow()

    def handle_event(self, match: re.Match) -> None:
        pass

    def _percent_to_ml_min(self, percent: float) -> float:
        return percent / 100 * self.max_flow_ml_min

    def _ml_min_to_raw(self, flow_ml_min: float) -> int:
        # float(): config.yml uebergibt Parameter als String ("{flow}"-Substitution), analog zu
        # allen anderen Treibern in diesem Repo (z.B. pump_base-Treiber via dispense(rate=...)).
        flow_ml_min = float(flow_ml_min)
        percent = max(0.0, min(100.0, flow_ml_min / self.max_flow_ml_min * 100))
        return round(percent / 100 * 32000)

    def set_setpoint(self, flow_ml_min: float):
        """Setpoint in mL/min setzen (wird intern in 0-32000 = 0-100% des Messbereichs umgerechnet).
        Die Geraeteantwort (Statusmeldung) wird geprueft; Status != 0 fuehrt zu einem Retry/Fehler."""
        raw_value = self._ml_min_to_raw(flow_ml_min)
        return self.write("SET_SETPOINT", command_values={"value": raw_value})

    def measure_flow(self):
        """Momentanen Messwert abfragen, Ergebnis in mL/min ueber die 'flow' Observable."""
        def to_ml_min(result):
            raw = _hex_to_int16(result.parameters["value"])
            flow = self._percent_to_ml_min(raw / 32000 * 100)
            self.update_observables({"flow": flow})
            return result
        cmd = self.query("READ_MEASURE")
        cmd.deferred_result.addCallback(to_ml_min)
        return cmd

    def read_counter(self):
        """Counter/Totalizer abfragen (IEEE754-Float, Big-Endian, Einheit laut Geraetekonfiguration)."""
        def to_float(result):
            value = _hex_to_float32(result.parameters["value"])
            self.update_observables({"counter": value})
            return result
        cmd = self.query("READ_COUNTER")
        cmd.deferred_result.addCallback(to_float)
        return cmd

    def stop_flow(self):
        return self.set_setpoint(0)
