# Treiber fuer den Inficon Micro GC Fusion, angebunden ueber Ethernet (feste IP), REST/HTTP+JSON -
# keine serielle Verbindung, keine Frames.
#
# ABHAENGIGKEITS-ENTSCHEIDUNG (wie angefragt, vor der Implementierung begruendet):
# Es gibt ein Community-Modul "MicroGCFusionAPI" (PyPI, nicht von INFICON), das genau diese
# REST-API kapselt. Dieser Treiber bindet es NICHT als Abhaengigkeit ein, sondern baut die
# benoetigten HTTP-Aufrufe direkt mit Twisteds eigenen Mitteln nach (twisted.web.client.Agent).
# Begruendung:
#   1. MicroGCFusionAPI ist BLOCKIEREND: es nutzt `requests.Session` fuer jeden Aufruf. Diese
#      gesamte Codebase ist Twisted/Deferred-basiert und laeuft in EINEM Reactor-Thread (s.
#      CLAUDE.md: "Everything is asynchronous"); ein blockierender requests.get()-Aufruf im
#      Reactor-Thread wuerde fuer die Dauer jeder GC-Anfrage ALLE anderen Geraete, Experimente und
#      das Frontend-HTTP-API einfrieren. Das ist kein Stilproblem, sondern ein harter
#      Architektur-Konflikt.
#   2. Nicht herstellerseitig gepflegt: Community-Modul, Version 0.0.8, sichtbare Qualitaetsmaengel
#      im Quellcode selbst (z.B. Databrowser.queryText() greift auf die undefinierte Variable
#      `runs` statt `response['runs']` zu - ein echter NameError-Bug in der veroeffentlichten
#      Version). Fuer 5 einfache REST-Aufrufe eine ungeprüfte Fremdabhaengigkeit (mitsamt deren
#      TRANSITIVEN Abhaengigkeiten `requests` UND `numpy`, obwohl wir weder Threads noch
#      Array-Mittelung brauchen) ins requirements.txt aufzunehmen, ist unverhaeltnismaessig.
#   3. Alternative "in einem Thread ausfuehren" (deferToThread) wuerde Thread-Sicherheit und eine
#      zusaetzliche Bruecke in die Command-Zustandsmaschine noetig machen, ohne die
#      Abhaengigkeits-/Bug-Risiken aus Punkt 2 zu beseitigen.
#   4. twisted.web.client.Agent ist Teil von Twisted selbst (bereits harte Abhaengigkeit dieses
#      Projekts, s. requirements.txt) - KEINE neue Abhaengigkeit noetig. treq (ein komfortablerer
#      Agent-Wrapper) waere ebenfalls asynchron und legitim gewesen, wurde hier aber bewusst NICHT
#      gewaehlt, um requirements.txt nicht um ein weiteres Paket zu erweitern, wo Agent + readBody
#      fuer die paar benoetigten GET-Aufrufe (keiner davon mit Request-Body) bereits ausreicht.
#
# QUELLENLAGE - WICHTIG: docs/microgc_api.md dokumentiert NUR die OEFFENTLICHE METHODENSCHNITTSTELLE
# des Python-Wrapper-Moduls (f.control.bakeout(), f.control.run(), ...), NICHT die tatsaechlichen
# HTTP-Endpunkte/Pfade/Query-Parameter dahinter - die stehen in dieser Doku schlicht nicht drin.
# Um den Wrapper NICHT einzubinden (s.o.) aber trotzdem byte-genau dieselben, tatsaechlich vom
# Geraet unterstuetzten Endpunkte zu treffen, wurde stattdessen der QUELLCODE von MicroGCFusionAPI
# (PyPI-Paket, Version 0.0.8, Datei MicroGCFusionAPI/fusion.py) gelesen - nur gelesen, nicht als
# Abhaengigkeit eingebunden (s.o.) - und die dort verwendeten Endpunkte 1:1 uebernommen:
#   - Ready-Status:      GET /v1/scm/sessions/system-manager/publicConfiguration
#                         -> JSON-Array [sequenceStatus, systemStatus] (Fusion.status())
#   - BakeOut starten:    GET /v1/scm/sessions/system-manager!cmd.bakeout?duration={min*60}s
#                         (Fusion.control.bakeout())
#   - Methode laden:      GET /v1/scm/sessions/system-manager!cmd.loadMethod?methodLocation=
#                         /v1/methods/userMethods/{methodName} (Fusion.control.loadMethod())
#   - Methode ausfuehren: GET /v1/scm/sessions/system-manager!cmd.run?runWhenReady=true
#                         (Fusion.control.run(), die parameterlose Variante - NICHT runWithName())
#   - Letzter Lauf:       GET /v1/lastRun -> {'dataLocation': ...}, danach
#                         GET /runData/{dataLocation} -> vollstaendiges Laufdatenfile
#                         (Fusion.data.lastRun(), zwei Anfragen nacheinander)
# Diese sechs Endpunkte/Pfade sind damit VERIFIZIERT gegen eine tatsaechliche, oeffentlich
# einsehbare Referenzimplementierung - NICHT gegen docs/microgc_api.md selbst (das nur die
# Python-Methodennamen zeigt) und NICHT gegen ein offizielles INFICON-API-Dokument (liegt hier
# nicht vor). Das "!" im Pfad ist Teil des echten Pfads (Sling-Servlet-Aufrufkonvention des
# Geraets), kein Tippfehler, und wird nicht URL-kodiert (in Pfadsegmenten laut RFC 3986 zulaessig).
#
# ANNAHME (nicht aus Doku oder Referenzcode ableitbar, s.u. run_data_to_csv): die JSON-Struktur
# der Laufdaten (data['detectors'][name]['analysis']['peaks'][...]) ist aus
# Fusion.data.compoundResults() im selben Referenzquellcode uebernommen, aber dort nur informell,
# nicht durch ein Schema abgesichert.
#
# LANG LAUFENDE VORGAENGE (BakeOut, Methodenlauf - Minuten bis Stunden): werden NICHT durch
# blockierendes Warten abgebildet, sondern wie beim Netzteil (tdk_lambda_zplus.py,
# output_constant_current/start_measuring_output) durch die bestehende Busy-Zustandsmaschine
# (self.busy(condition), backend/devices/devicestate.py) kombiniert mit einem RepeatedCommand
# (self.repeated_query("STATUS", ...)), das den Systemstatus periodisch abfragt und automatisch
# stoppt, sobald die Bedingung (Systemstatus == "public:ready") erfuellt ist - siehe
# _wait_until_ready(). ANNAHME/bekannte Einschraenkung: es wird nicht zweiphasig geprueft, dass der
# Systemstatus zwischenzeitlich tatsaechlich den aktiven Zustand (public:bakeout/
# public:method-running) angenommen hat, bevor auf "public:ready" gewartet wird - bei einer
# Race Condition (Status bereits "public:ready" beim allerersten Poll) wuerde busy() sofort
# zurueckkehren. Fuer die hier verlangte Funktionalitaet (Zustandsautomat + Repeated Commands statt
# blockierendem Warten) ausreichend; fuer eine harte Absicherung gegen diese Race waere ein
# zusaetzlicher lokaler "started"-Zwischenzustand noetig.

import json
from urllib.parse import quote

from twisted.internet import defer, reactor
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers

from backend.commands import commandstate
from backend.commands.parser import BaseParser, ParserParameterFactory
from backend.commands.results import Result
from backend.conditions.conditions import ObservableEqualsValueCondition
from .gc_base import BaseDevice, SinglechannelBaseDevice, CommandParameterFactory


PATH_STATUS = "/v1/scm/sessions/system-manager/publicConfiguration"
PATH_BAKEOUT = "/v1/scm/sessions/system-manager!cmd.bakeout"
PATH_LOAD_METHOD = "/v1/scm/sessions/system-manager!cmd.loadMethod"
PATH_RUN = "/v1/scm/sessions/system-manager!cmd.run"
PATH_LAST_RUN_LOCATION = "/v1/lastRun"
PATH_RUN_DATA_PREFIX = "/runData/"

READY_STATE = "public:ready"


def _extract_status(data) -> dict:
    """[sequenceStatus, systemStatus] -> {"sequence": ..., "system": ...}, verifiziert gegen
    Fusion.status() im Referenzquellcode (s. Dateikopf)."""
    return {"sequence": data[0], "system": data[1]}


def _extract_last_run_location(data) -> dict:
    return {"last_run_location": data["dataLocation"]}


class HTTPJSONParser(BaseParser):
    """Prueft, ob eine HTTP-Anfrage ueberhaupt eine Antwort mit 2xx-Status und gueltigem (oder
    leerem) JSON-Koerper bekommen hat, und extrahiert bei Bedarf einzelne Felder nach
    reply.parameters - genau der Mechanismus, ueber den AbstractBaseDevice.receive() (backend/
    devices/base.py) automatisch Observablen aktualisiert, wie bei den anderen Treibern auch."""

    def __init__(self, command, extract=None, **kwargs):
        super().__init__(command)
        self.extract = extract

    def __call__(self, reply: Result):
        status = getattr(reply, "http_status", None)
        if status is None:
            return (commandstate.CommandResponseError(reply=reply, msg=f"{reply.line}"),
                    commandstate.Retry)
        if not (200 <= status < 300):
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"Unexpected HTTP status in {reply.line}."),
                    commandstate.Retry)
        if getattr(reply, "json_error", False):
            return (commandstate.CommandResponseError(
                        reply=reply, msg=f"Invalid JSON body in {reply.line}."),
                    commandstate.Retry)
        if self.extract is not None:
            try:
                reply.parameters = self.extract(reply.json)
            except (KeyError, IndexError, TypeError) as error:
                return (commandstate.CommandResponseError(
                            reply=reply, msg=f"Unexpected JSON shape in {reply.line}: {error}"),
                        commandstate.Retry)
        return reply, commandstate.Success


class HTTPCommandTransport:
    """Ersetzt BaseDeviceProtocol (backend/devices/base.py) fuer dieses Geraet: keine persistente
    Byte-Stream-Verbindung, sondern ein einzelner HTTP-Request pro Command, ueber Twisteds eigenen
    Agent. Jede Antwort (oder jeder Fehlschlag) wird als genau ein Result an device.receive()
    gemeldet, damit die bestehende Command-Zustandsmaschine (Timeout/Retry/CommandSeries/
    RepeatedCommand) unveraendert weiterfunktioniert - siehe HTTPJSONParser fuer die
    Erfolgs-/Fehlerauswertung."""

    def __init__(self, device):
        self.device = device
        self.agent = Agent(reactor, connectTimeout=device.connect_timeout)

    def get(self, url: str) -> defer.Deferred:
        d = self.agent.request(b"GET", url.encode("ascii"), Headers())

        def read_body(response):
            body_deferred = readBody(response)
            body_deferred.addCallback(lambda body: (response.code, body))
            return body_deferred

        d.addCallback(read_body)
        return d

    def write_command(self, command_object) -> None:
        url = self.device.base_url() + command_object.parameters.commandstring
        d = self.get(url)
        d.addCallback(self._build_result, url)
        d.addErrback(self._request_failed, url)
        self.device.log.info(f"Wrote GET {url} to device.")

    def _build_result(self, code_and_body, url):
        code, body = code_and_body
        result = Result(f"HTTP {code} {url}")
        result.http_status = code
        result.json = None
        if body:
            try:
                result.json = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                result.json_error = True
        self.device.receive(result)

    def _request_failed(self, failure, url):
        result = Result(f"HTTP request to {url} failed: {failure.getErrorMessage()}")
        result.http_status = None
        result.json = None
        self.device.receive(result)

    def lose_connection(self):
        pass  # Agent verwaltet seine Verbindungen selbst; kein expliziter Verbindungsabbau noetig.


class Device(BaseDevice, SinglechannelBaseDevice):
    command_parameter_factory = CommandParameterFactory(timeout=10.0, command_execution_time=.2)
    replies_commands = True
    log_name = "Inficon Micro GC Fusion"

    commands = {
        "STATUS": [PATH_STATUS, ParserParameterFactory(parserclass=HTTPJSONParser, extract=_extract_status)],
        "BAKEOUT": [PATH_BAKEOUT, ParserParameterFactory(parserclass=HTTPJSONParser)],
        "LOAD_METHOD": [PATH_LOAD_METHOD, ParserParameterFactory(parserclass=HTTPJSONParser)],
        "RUN": [PATH_RUN, ParserParameterFactory(parserclass=HTTPJSONParser)],
        "LAST_RUN_LOCATION": [PATH_LAST_RUN_LOCATION,
                               ParserParameterFactory(parserclass=HTTPJSONParser, extract=_extract_last_run_location)],
        "RUN_DATA": [PATH_RUN_DATA_PREFIX, ParserParameterFactory(parserclass=HTTPJSONParser)],
    }

    def __init__(self, address, *args, connect_timeout: float = 5.0, **kwargs):
        """
        :param address: feste IP (oder IP:Port, z.B. fuer die Dummy-Umgebung) des Geraets im
                         Netzwerk - kein serieller Port.
        :param connect_timeout: TCP-Verbindungsaufbau-Timeout in Sekunden (aus config.yml).
                                 Das Antwort-Timeout pro Anfrage kommt ueber den bestehenden,
                                 generischen Mechanismus aus config.yml: `command_parameters:
                                 {timeout: <Sekunden>}` auf diesem Geraet (s. CommandParameterFactory).
        """
        self.connect_timeout = float(connect_timeout)
        super().__init__(address, *args, **kwargs)

    def base_url(self) -> str:
        if self.port is None:
            return f"http://{self.address}"
        return f"http://{self.address}:{self.port}"

    def get_connection_method(self):
        # AbstractBaseDevice.get_connection_method() waehlt sonst zwischen TCP- und
        # Seriell-Rohbytestream (_tcp/_serial) - fuer dieses Geraet ist beides falsch, jede
        # "Verbindung" ist hier nur eine Folge unabhaengiger HTTP-Requests. s. Dateikopf.
        return self._http

    def _http(self) -> defer.Deferred:
        transport = HTTPCommandTransport(self)

        def connected(_):
            return self.connection_done(transport)

        def failed(failure):
            self.log.error(f"Could not reach {self.log_name} at {self.base_url()}: "
                            f"{failure.getErrorMessage()}")
            return failure

        d = transport.get(self.base_url() + "/")
        d.addCallback(connected)
        d.addErrback(failed)
        return d

    def cmd_string(self, command_parameters: CommandParameterFactory) -> str:
        path = command_parameters.commandstring
        values = command_parameters.command_values
        if path == PATH_BAKEOUT:
            seconds = int(float(values["minutes"]) * 60)
            return f"{path}?duration={seconds}s"
        if path == PATH_LOAD_METHOD:
            method_name = quote(str(values["method_name"]), safe="")
            return f"{path}?methodLocation=/v1/methods/userMethods/{method_name}"
        if path == PATH_RUN:
            return f"{path}?runWhenReady=true"
        if path == PATH_RUN_DATA_PREFIX:
            return f"{path}{quote(str(values['location']), safe='')}"
        return path

    def initial_commands(self):
        self.get_status()

    def final_commands(self):
        pass  # kein Ausgang zum Abschalten - reiner Lesezugriff plus Start-Kommandos, s. Auftrag.

    def handle_event(self, match) -> None:
        pass

    def _wait_until_ready(self, poll_interval: float) -> defer.Deferred:
        """Bildet einen lang laufenden Vorgang (BakeOut/Methodenlauf) ueber die bestehende
        Busy-Zustandsmaschine + RepeatedCommand ab, statt blockierend zu warten - s. Dateikopf."""
        condition = ObservableEqualsValueCondition(
            f"{self.log_name} returned to {READY_STATE}", self, "system", READY_STATE)
        self.repeated_query("STATUS", poll_interval, condition, inter_command_time=.001)
        return self.busy(condition).deferred_result

    def start_bakeout(self, minutes=30, poll_interval=10, **kwargs):
        """BakeOut starten (Dauer in Minuten, Werkseinstellung des Geraets: 30). Der Ruecklaufwert
        wird erst erreicht (Deferred feuert), wenn der Systemstatus wieder public:ready meldet -
        das Aufrufen selbst blockiert nicht."""
        self.write("BAKEOUT", command_values={"minutes": minutes}, **kwargs)
        return self._wait_until_ready(poll_interval)

    def load_method(self, method_name, **kwargs):
        """Methode laden (Name der Methode auf dem Geraet)."""
        return self.write("LOAD_METHOD", command_values={"method_name": method_name}, **kwargs)

    def run_method(self, poll_interval=5, **kwargs):
        """Die aktuell geladene Methode ausfuehren. Wie start_bakeout(): nicht-blockierend, das
        Deferred feuert, sobald der Systemstatus wieder public:ready meldet."""
        self.write("RUN", **kwargs)
        return self._wait_until_ready(poll_interval)

    def get_status(self, **kwargs):
        """Ready-Status abfragen: aktualisiert die Observablen 'system' und 'sequence' (moegliche
        Werte s. docs/microgc_api.md, u.a. public:ready/public:standby/public:bakeout/
        public:method-running)."""
        return self.query("STATUS", **kwargs)

    def get_last_run_data(self, **kwargs):
        """Daten des letzten Laufs holen (volles JSON-Datenfile, unveraendert - s. Dateikopf:
        JSON->CSV ist bewusst NICHT hier, sondern in run_data_to_csv())."""
        def fetch_run_data(result):
            location = result.parameters["last_run_location"]
            run_data_cmd = self.query("RUN_DATA", command_values={"location": location}, **kwargs)

            def store(run_data_result):
                self.update_observables({"last_run_data": run_data_result.json})
                return run_data_result
            run_data_cmd.deferred_result.addCallback(store)
            return run_data_cmd.deferred_result

        d = self.query("LAST_RUN_LOCATION", **kwargs).deferred_result
        d.addCallback(fetch_run_data)
        return d


# ---------------------------------------------------------------------------------------------
# Datenaufbereitung - KEINE Geraetekommunikation, deshalb bewusst als eigenstaendige, reine
# Funktion ausserhalb der Device-Klasse (s. Auftrag). Nimmt das JSON, wie es get_last_run_data()
# liefert (bzw. dessen 'last_run_data'-Observable), und wandelt die Peak-Tabelle in CSV-Text um.
#
# ANNAHME: die Struktur data['detectors'][name]['analysis']['peaks'][...] mit den Feldern label/
# height/area/top/concentration/normalizedConcentration ist NICHT aus docs/microgc_api.md oder
# einem offiziellen Schema verifiziert (dort nicht dokumentiert), sondern aus der informellen
# Auswertung in Fusion.data.compoundResults() im MicroGCFusionAPI-Referenzquellcode (s. Dateikopf)
# uebernommen - selbst dort ohne Schema-Absicherung, mit try/except gegen fehlende Felder.
# ---------------------------------------------------------------------------------------------

import csv
import io


def run_data_to_csv(run_data: dict) -> str:
    """Peak-Tabelle eines Laufdatensatzes (Struktur s.o.) als CSV-Text. Eine Zeile pro erkanntem,
    benanntem Peak je Detektor; Peaks ohne 'label' (nicht durch den Nutzer benannt/nicht
    identifiziert) werden ausgelassen, wie auch in compoundResults()."""
    fieldnames = ["detector", "label", "height", "area", "retention_time",
                  "concentration", "normalized_concentration"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for detector_name, detector_data in (run_data.get("detectors") or {}).items():
        analysis = detector_data.get("analysis") or {}
        for peak in analysis.get("peaks") or []:
            if "label" not in peak:
                continue
            writer.writerow({
                "detector": detector_name,
                "label": peak.get("label"),
                "height": peak.get("height"),
                "area": peak.get("area"),
                "retention_time": peak.get("top"),
                "concentration": peak.get("concentration", ""),
                "normalized_concentration": peak.get("normalizedConcentration", ""),
            })
    return buffer.getvalue()
