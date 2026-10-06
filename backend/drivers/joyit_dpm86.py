# Treiber fuer Joy-IT JT-DPM86xx Spannungsquellen (DPM8605/8624/8650), angebunden ueber RS485/USB-Seriell,
# "simple communication protocol" (ASCII, Werkseinstellung des Geraets).
#
# Quelle: Programm von Matthias Schmidt (PowerBison, PowerSupplyWrapper_JoyItDPM86.py, Stand 28.04.2026),
# das seinerseits auf https://github.com/aloishockenschlohe/dpm86_power_supply beruht. Uebernommen ist nur
# das Protokoll; tkinter-Portauswahl, Threads/Mutex und GUI-Anbindung entfallen, die Serialisierung der
# Befehle uebernimmt die Command-Warteschlange des Backends.
#
# Schnittstelle: 9600 Baud, 8N1, Geraeteadresse "01" (Werkseinstellung).
# Frames (Matthias' Code byte-genau, inkl. doppeltem Komma und reinem LF als Abschluss):
#   Lesen:     ":01r30=0,,\n"      Antwort: ":01r30=1234.\r\n"  (Wert als Ganzzahl)
#   Schreiben: ":01w10=1250,,\n"   Antwort: ":01ok\r\n"
# Skalierung: Spannung in 0,01 V, Strom in 0,001 A.
#
# Hinweise aus Matthias' Code (Kommentar des Originalautors):
# - Spannungsquelle und RS485-Adapter muessen auf GEMEINSAMER MASSE liegen, sonst gibt es Zeichenmuell
#   oder gar keine Uebertragung.
# - Das Geraet muss auf "simple protocol" stehen (Werkseinstellung).
#
# NOCH NICHT AM GERAET VERIFIZIERT (Stand 06.10.2026). Am 05.10. hat das Geraet auf nichts geantwortet -
# damals vermutlich ohne Leistungsversorgung und mit falschem Frame (":01r00=0," mit nur einem Komma).
# Erster Test mit tools/lese_netzteil.py (sendet nur Lesebefehle).

from .psu_base import BaseDevice, SinglechannelBaseDevice, CommandParameterFactory
from backend.commands.parser import ParserParameterFactory, REParser
from backend.conditions import ObservableGreaterOrEqualValueCondition
from backend.combined_observables import TimeIntegral

import re

from twisted.internet import defer


READ = "r"
WRITE = "w"

# Funktionsnummern laut Protokoll: (Observable-Name, Faktor Rohwert -> physikalischer Wert)
FUNCTIONS = {
    "00": ("max_voltage", 0.01),        # R: maximale Ausgangsspannung des Geraets
    "01": ("max_current", 0.001),       # R: maximaler Ausgangsstrom des Geraets
    "10": ("voltage_setpoint", 0.01),   # R/W: Sollspannung
    "11": ("current_setpoint", 0.001),  # R/W: Sollstrom
    "12": ("output", 1),                # R/W: Ausgang 0 = aus, 1 = an
    "30": ("voltage", 0.01),            # R: gemessene Ausgangsspannung
    "31": ("current", 0.001),           # R: gemessener Ausgangsstrom
    "32": ("mode", 1),                  # R: 0 = Konstantspannung, 1 = Konstantstrom
    "33": ("temperature", 1),           # R: Temperatur
}

READ_PATTERN = r":(?P<dpm_address>\d{2})r(?P<function>\d{2})=(?P<value>\d+)"
WRITE_PATTERN = r":(?P<dpm_address>\d{2})(?P<reply>ok)"


def frame(dpm_address: str, rw: str, function: str, value: int = 0) -> str:
    """Ein Befehlsframe ohne Zeilenende, z.B. frame("01", "r", "30") -> ":01r30=0,,".
    Wird auch von tools/lese_netzteil.py benutzt, damit das Werkzeug genau das sendet, was der Treiber sendet."""
    return f":{dpm_address}{rw}{function}={value},,"


def _read_command(function):
    return [f"{READ}{function}", READ_PATTERN]


def _write_command(function):
    return [f"{WRITE}{function}",
            ParserParameterFactory(parserclass=REParser, pattern=WRITE_PATTERN, expected_values={"reply": "ok"})]


class Device(BaseDevice, SinglechannelBaseDevice):
    delimiter = "\n"  # gesendet wird reines LF wie in Matthias' Code; Antworten enden auf \r\n, das \r stoert die Regexes nicht
    serial_parameters = {"baudrate": 9600}  # 8N1 ist Default von SerialPort
    command_parameter_factory = CommandParameterFactory(command_execution_time=.1)
    replies_commands = True
    log_name = "Joy-IT DPM86xx"

    commands = {
        "GET_MAX_VOLTAGE": _read_command("00"),
        "GET_MAX_CURRENT": _read_command("01"),
        "GET_VOLTAGE_SETPOINT": _read_command("10"),
        "GET_CURRENT_SETPOINT": _read_command("11"),
        "GET_OUTPUT": _read_command("12"),
        "GET_MEASURE_VOLTAGE": _read_command("30"),
        "GET_MEASURE_CURRENT": _read_command("31"),
        "GET_MODE": _read_command("32"),
        "GET_TEMPERATURE": _read_command("33"),
        "SET_VOLTAGE": _write_command("10"),
        "SET_CURRENT": _write_command("11"),
        "SET_OUTPUT": _write_command("12"),
    }

    def __init__(self, address, *args, dpm_address: str = "01", voltage_limit: float = 60.0,
                 current_limit: float = 50.0, **kwargs):
        """
        :param dpm_address: Geraeteadresse im Protokoll, zwei Ziffern (Werkseinstellung "01")
        :param voltage_limit: Obergrenze in V fuer jeden Spannungssollwert (aus config.yml). Hoehere Werte
                              werden abgelehnt, ohne dass etwas gesendet wird.
        :param current_limit: Obergrenze in A fuer jeden Stromsollwert, analog.
        """
        self.dpm_address = dpm_address
        self.voltage_limit = float(voltage_limit)
        self.current_limit = float(current_limit)
        super().__init__(address, *args, **kwargs)
        self._aoc = None
        self._current_measuring = None
        self._voltage_measuring = None

    def cmd_string(self, command_parameters: CommandParameterFactory) -> str:
        rw, function = command_parameters.commandstring[0], command_parameters.commandstring[1:]
        value = command_parameters.command_values.get("value", 0)
        return frame(self.dpm_address, rw, function, value)

    def initial_commands(self):
        # Ausgang beim Verbindungsaufbau abschalten - aus demselben Grund wie beim MFC: der letzte Zustand
        # ueberlebt einen Absturz des Backends, final_commands() greift nur beim sauberen Beenden.
        self.stop_current()
        self.query("GET_MAX_VOLTAGE")
        self.query("GET_MAX_CURRENT")

    def final_commands(self):
        self.stop_current()

    def handle_event(self, match: re.Match) -> None:
        pass

    def update_observables(self, observables: dict, timestamp: float = None):
        # Der Parser liefert die Rohgruppen der Regex (dpm_address, function, value, reply). Daraus werden
        # die physikalischen Observables (voltage in V, current in A, ...); die Rohgruppen selbst entfallen.
        if "function" in observables and "value" in observables:
            name, factor = FUNCTIONS[observables["function"]]
            observables = {name: round(int(observables["value"]) * factor, 3)}
        else:
            observables = {k: v for k, v in observables.items() if k not in ("dpm_address", "reply")}
        if observables:
            if timestamp is None:
                super().update_observables(observables)
            else:
                super().update_observables(observables, timestamp)

    def _check_limit(self, value, limit, unit):
        value = float(value)  # config.yml uebergibt Parameter als String ("{current}"-Substitution)
        if not 0 <= value <= limit:
            raise ValueError(f"{value} {unit} liegt ausserhalb 0...{limit} {unit} (Grenze aus config.yml)")
        return value

    def set_voltage(self, voltage):
        voltage = self._check_limit(voltage, self.voltage_limit, "V")
        return self.write("SET_VOLTAGE", command_values={"value": round(voltage * 100)})

    def set_current(self, current):
        current = self._check_limit(current, self.current_limit, "A")
        return self.write("SET_CURRENT", command_values={"value": round(current * 1000)})

    def set_output(self, on):
        on = on not in (False, 0, "0", "false", "False", "off")
        return self.write("SET_OUTPUT", command_values={"value": 1 if on else 0})

    def measure_output(self):
        with self.commandseries as series:
            self.query("GET_MEASURE_VOLTAGE")
            self.query("GET_MEASURE_CURRENT")
        return series

    def _start_aoc(self):
        self._stop_aoc()
        self._aoc = TimeIntegral(self, "amount_of_charge", "current")
        self._aoc.start()

    def _stop_aoc(self):
        try:
            self._aoc.stop()
        except AttributeError:
            pass

    def start_measuring_output(self, interval=.5, condition=None):
        def start_aoc(result):
            self._start_aoc()
            return result

        self._current_measuring = self.repeated_query("GET_MEASURE_CURRENT", interval, condition, inter_command_time=.001)
        self._voltage_measuring = self.repeated_query("GET_MEASURE_VOLTAGE", interval, condition, inter_command_time=.001)
        self._current_measuring.deferred_result.addCallback(start_aoc)

    def _stop_measuring_output(self):
        self._stop_aoc()
        try:
            self._current_measuring.stop_running()
            self._voltage_measuring.stop_running()
        except AttributeError:
            pass
        else:
            self._current_measuring = None
            self._voltage_measuring = None

    def output_constant_current(self, current, max_voltage=None, amount_of_charge=None):
        # Wie TDK-Treiber: Strom und Spannungsbegrenzung setzen, Ausgang an. Ob das Geraet dann im
        # Konstantstrom- oder Konstantspannungsbetrieb laeuft, entscheidet es selbst (Observable "mode").
        if max_voltage is None:
            max_voltage = self.voltage_limit
        self.set_current(current)
        self.set_voltage(max_voltage)
        deferred_result = self.set_output(True).deferred_result

        if amount_of_charge:
            def get_time_passed(results):
                try:
                    time_passed = results[1][1].time - results[0][1].time
                except AttributeError:
                    self.log.error(f"Constant current output failed with: {results}")
                    for (success, result) in results:
                        if not success:
                            raise result
                else:
                    self.log.info(f"Amount of charge reached after {time_passed} s.")
                    return results

            condition = ObservableGreaterOrEqualValueCondition("amount of charge reached", self, "amount_of_charge", str(amount_of_charge))
            defer.DeferredList([deferred_result, self.busy(condition).deferred_result]).addCallback(get_time_passed)
            self.start_measuring_output()
            self.stop_current()
        else:
            self.start_measuring_output()

        return deferred_result

    def output_constant_voltage(self, voltage, max_current=None, amount_of_charge=None):
        if max_current is None:
            max_current = self.current_limit
        return self.output_constant_current(max_current, voltage, amount_of_charge)

    def stop_current(self):
        def stop_measuring(result):
            self._stop_measuring_output()
            return result
        cmd = self.write("SET_OUTPUT", command_values={"value": 0})
        cmd.deferred_execution.addCallback(stop_measuring)
        return cmd
