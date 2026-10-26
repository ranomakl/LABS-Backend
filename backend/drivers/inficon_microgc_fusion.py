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
#   - Letzter Lauf:       GET /v1/lastRun -> {'dataLocation': '/runData/<uuid>'}, danach
#                         GET {dataLocation} -> vollstaendiges Laufdatenfile
#                         (Fusion.data.lastRun(), zwei Anfragen nacheinander). dataLocation ist
#                         bereits ein vollstaendiger Pfad inkl. "/runData/" - am Geraet geprueft
#                         06.10.2026; bis dahin wurde hier faelschlich nochmal "/runData/"
#                         vorangestellt, was das Geraet zwar tolerierte, aber nicht korrekt war.
# Diese sechs Endpunkte/Pfade sind damit VERIFIZIERT gegen eine tatsaechliche, oeffentlich
# einsehbare Referenzimplementierung - NICHT gegen docs/microgc_api.md selbst (das nur die
# Python-Methodennamen zeigt) und NICHT gegen ein offizielles INFICON-API-Dokument (liegt hier
# nicht vor). Das "!" im Pfad ist Teil des echten Pfads (Sling-Servlet-Aufrufkonvention des
# Geraets), kein Tippfehler, und wird nicht URL-kodiert (in Pfadsegmenten laut RFC 3986 zulaessig).
#
# JSON-Struktur der Laufdaten (data['detectors'][name]['analysis']['peaks'][...]): urspruenglich
# aus Fusion.data.compoundResults() im Referenzquellcode uebernommen; am 06.10.2026 gegen die
# Beispieldatei testdata_microgc(1).fusion-data UND gegen den letzten Lauf am echten Geraet geprueft -
# stimmt (s. run_data_to_csv, tools/lese_microgc.py).
#
# AM GERAET GEPRUEFT (06.10.2026, Pi per LAN direkt am microGC, Geraet unter 169.254.1.1): alle
# oben genannten Lese-Endpunkte (STATUS, /v1/lastRun, Laufdaten, /v1/methods/userMethods) antworten
# mit HTTP 200 und dem erwarteten JSON. loadMethod und run ebenfalls am Geraet ausgefuehrt
# (HTTP 200, Lauf durchgefuehrt, neue Laufdaten abgeholt, s. READY_STATE). BakeOut nicht ausgeloest.
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
import os
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

from twisted.internet import defer, reactor
from twisted.python import failure
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers
from twisted.web.iweb import IBodyProducer
from zope.interface import implementer

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
# AM GERAET BESTAETIGT (echter Lauf 06.10.2026, tools/starte_microgc_lauf.py): Statusfolge nach
# loadMethod + run war preparing (27 s) -> method-running (~5 min) -> loading-method -> preparing
# (~2 min) -> ready, insgesamt 454 s. Das Geraet kehrt also nach "public:ready" zurueck, auf das
# _wait_until_ready() wartet. Im Leerlauf vor dem ersten Laden stand es auf "public:standby" -
# das betrifft nur den Ausgangszustand, nicht das Warten. BakeOut noch nicht ausgeloest.


def _extract_status(data) -> dict:
    """[sequenceStatus, systemStatus] -> {"sequence": ..., "system": ...}, verifiziert gegen
    Fusion.status() im Referenzquellcode (s. Dateikopf)."""
    return {"sequence": data[0], "system": data[1]}


def _extract_last_run_location(data) -> dict:
    return {"last_run_location": data["dataLocation"]}


def run_data_path(location: str) -> str:
    """Pfad zum Laufdatenfile aus dem 'dataLocation'-Wert von /v1/lastRun. Das Geraet liefert
    ihn bereits vollstaendig ("/runData/<uuid>", am Geraet geprueft 06.10.2026); nur eine nackte
    UUID wird noch mit dem Prefix versehen."""
    if location.startswith(PATH_RUN_DATA_PREFIX):
        return PATH_RUN_DATA_PREFIX + quote(location[len(PATH_RUN_DATA_PREFIX):], safe="")
    return PATH_RUN_DATA_PREFIX + quote(location.lstrip("/"), safe="")


# ---------------------------------------------------------------------------------------------
# GC-MESSPLAN INNERHALB EINES EXPERIMENTS (13.10.2026, docs/aufgabe_microgc_im_experiment.txt)
# Zustaende des Geraets, wie am 06./08./13.10.2026 beobachtet (tools/starte_microgc_lauf.py):
#   Leerlauf: public:ready, public:standby (vor dem ersten Laden nach dem Einschalten)
#   Laden:    public:loading-method (nach cmd.loadMethod, einige Sekunden; ein cmd.run in dieser
#             Phase startet den Lauf zwar, verliert aber Name/Tags - am 13.10. so gesehen)
#   Aktiv:    public:preparing -> public:method-running -> (loading-method/preparing) -> ready
# ---------------------------------------------------------------------------------------------
IDLE_STATES = {"public:ready", "public:standby"}
LOADING_STATE = "public:loading-method"
ACTIVE_STATES = {"public:preparing", "public:method-running", "public:waiting-for-modules"}
ERROR_PREFIX = "public:error"
SCHEDULE_OBSERVABLE = "gc_schedule"          # "running" / "finished" / "cancelled"
MAX_RUN_S = 30 * 60                          # ein Methodenlauf dauert ~7,6 min; danach gilt er als haengend
MAX_LOAD_S = 5 * 60


def observable_key(label: str) -> str:
    """Peak-Label vom Geraet -> Observablenname: alles ausser Buchstaben/Ziffern wird zu '_',
    z.B. 'H2' -> gc_H2, 'n Hexane' -> gc_n_Hexane, '1,3 Butadien' -> gc_1_3_Butadien,
    'trans + cis 2 Buten' -> gc_trans_cis_2_Buten."""
    return "gc_" + re.sub(r"[^0-9A-Za-z]+", "_", str(label)).strip("_")


def concentrations_from_run_data(run_data: dict) -> dict:
    """Benannte Peaks aller Detektoren -> {gc_<Label>: concentration, gc_<Label>_norm:
    normalizedConcentration} (Einheit %, wie das Geraet sie liefert). Peaks ohne Label oder ohne
    Zahl werden ausgelassen. Struktur s. run_data_to_csv()."""
    values = {}
    for detector_data in (run_data.get("detectors") or {}).values():
        for peak in ((detector_data or {}).get("analysis") or {}).get("peaks") or []:
            if "label" not in peak:
                continue
            key = observable_key(peak["label"])
            for suffix, field in (("", "concentration"), ("_norm", "normalizedConcentration")):
                try:
                    values[key + suffix] = float(peak[field])
                except (KeyError, TypeError, ValueError):
                    continue
    return values


def parse_minutes(text) -> list:
    """'0;10;20' (auch Komma/Leerzeichen als Trenner) -> [0.0, 10.0, 20.0], sortiert, ohne
    Doppelte. Im Frontend Semikolons benutzen: es macht aus Kommas in Parametern Punkte."""
    if isinstance(text, (list, tuple)):
        parts = [str(t) for t in text]
    else:
        parts = re.split(r"[;,\s]+", str(text).strip())
    return sorted({float(part) for part in parts if part})


def _truthy(value) -> bool:
    """config.yml-Schalter: True/'true'/'ja'/'1' -> True; False/''/'false'/'nein'/'0'/None -> False."""
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "ja", "on")
    return bool(value)


def _stream_prefix(prefix, stream) -> str:
    return f"{prefix}_{stream}" if stream is not None else str(prefix)


def run_name(prefix, minute: float) -> str:
    """Laufname wie in tools/kolbe_gc_messplan.py: '<Versuch>_<t> min', t ohne Nachkommastellen,
    wenn ganzzahlig."""
    return f"{prefix}_{minute:g} min"


def safe_filename(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(name))


def default_save_dir() -> Path:
    """Gleicher Ordner wie tools/kolbe_gc_messplan.py, damit tools/auswertung.py die Laeufe findet."""
    today = date.today()
    return Path("logs") / str(today.year) / str(today.month) / str(today.day) / "microgc"


def plan_times(minutes, until_minutes=None):
    """Eingabe gc_minutes -> (Zeitpunkte in min, continuous). Liste '0;10;20' = feste Zeitpunkte;
    EINE Zahl N > 0 = alle N Minuten von 0 bis until_minutes; 0 = Dauermessung (continuous: naechster
    Lauf sofort, wenn der vorige fertig ist, bis until_minutes). Ohne until_minutes gilt eine
    einzelne Zahl als einzelner Zeitpunkt (Verhalten bis 13.10.2026 - fuehrte zu einem einzigen Lauf)."""
    times = parse_minutes(minutes)
    until = None
    if until_minutes not in (None, ""):
        until = float(until_minutes)
    if len(times) != 1 or until is None or until <= 0:
        return times, False
    single = times[0]
    if single <= 0:
        return [], True
    n = int(until // single) + 1
    return [round(k * single, 6) for k in range(n)], False


class _Schedule:
    """Zustand eines laufenden GC-Messplans (ein Plan je Geraet)."""
    def __init__(self, prefix, tags, minutes, poll_interval, save_dir, continuous=False, until_minutes=None,
                 final_run=False, streams=None):
        self.prefix = prefix
        # 26.10.2026 Drei Zellen an einem GC (docs/gc_rundlauf_3_zellen_26-10-2026.md): `streams` = Namen
        # der Gasstroeme (z.B. Z1;Z2;Z3), die im Kreis gemessen werden - jeder faellige Lauf misst den
        # NAECHSTEN Strom; die Abschlussmessung laeuft einmal je Strom. Leer = ein Strom, wie bisher.
        self.streams = [str(x) for x in (streams or [])]
        self.stream_index = 0
        self.last_stream = None      # zuletzt gemessener Strom (Ventile stehen noch so)
        self.final_streams = []      # Abschlussmessungen, die noch anstehen (Stromnamen oder [None])
        self.tags = tags
        self.minutes = list(minutes)
        self.continuous = continuous
        self.until_s = 60.0 * float(until_minutes) if until_minutes not in (None, "") else None
        self.poll_interval = float(poll_interval)
        self.save_dir = Path(save_dir) if save_dir else default_save_dir()
        self.t0 = time.time()
        self.timers = []
        self.due = []            # faellige, noch nicht gestartete Zeitpunkte (min)
        self.active = None       # Zeitpunkt des gerade laufenden Laufs
        self.remaining = len(self.minutes)   # im Dauermodus: offen (wird bei jedem Start erhoeht)
        self.done = 0
        self.failed = 0
        self.cancelled = False
        self.loaded = False      # Methode geladen und Geraet wieder im Leerlauf
        # 16.10.2026 Abschlussmessung (Wunsch Rafael): nach dem Ende der Elektrolyse (until_minutes) und
        # nach dem letzten planmaessigen Lauf noch EIN Lauf "<prefix>_Ende <t> min". Nur mit until_minutes.
        # Entfaellt, wenn ein planmaessiger Zeitpunkt ohnehin >= until_minutes liegt (der misst schon
        # nach dem Ende). final_due: until_minutes sind um (Timer); final_pending: Lauf steht an
        # (verstrichene Minute); final_done: gelaufen, uebersprungen oder nicht gewuenscht.
        self.final_run = bool(final_run) and self.until_s is not None
        if self.final_run and not continuous and any(60.0 * m >= self.until_s for m in self.minutes):
            self.final_run = False
        self.final_due = False
        self.final_pending = None
        self.final_done = not self.final_run

    def is_open(self) -> bool:
        """Noch nicht regulaer beendet: Laeufe offen, einer aktiv, oder die Abschlussmessung steht aus."""
        return bool(self.remaining or self.due or self.active is not None or not self.final_done
                    or self.final_streams)

    def next_stream(self):
        """Naechster Strom im Kreis (None ohne Streams)."""
        if not self.streams:
            return None
        stream = self.streams[self.stream_index % len(self.streams)]
        self.stream_index += 1
        return stream


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


@implementer(IBodyProducer)
class _BytesProducer:
    """Minimaler IBodyProducer fuer einen fertigen Byte-Koerper (twisted.web.client.Agent)."""
    def __init__(self, body: bytes):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)

    def pauseProducing(self):
        pass

    def resumeProducing(self):
        pass

    def stopProducing(self):
        pass


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

    def post_json(self, url: str, body: dict) -> defer.Deferred:
        data = json.dumps(body).encode("utf-8")
        headers = Headers({b"Content-Type": [b"application/json"]})
        d = self.agent.request(b"POST", url.encode("ascii"), headers, _BytesProducer(data))

        def read_body(response):
            body_deferred = readBody(response)
            body_deferred.addCallback(lambda raw: (response.code, raw))
            return body_deferred

        d.addCallback(read_body)
        return d

    def write_command(self, command_object) -> None:
        url = self.device.base_url() + command_object.parameters.commandstring
        json_body = command_object.parameters.command_values.get("json_body")
        if json_body is not None:
            # Benannter Lauf (runWithName in MicroGCFusionAPI): POST mit JSON-Koerper statt GET.
            d = self.post_json(url, json_body)
            self.device.log.info("Wrote POST {url} {body} to device.", url=url, body=json.dumps(json_body))
        else:
            d = self.get(url)
            self.device.log.info(f"Wrote GET {url} to device.")
        d.addCallback(self._build_result, url)
        d.addErrback(self._request_failed, url)

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

    def __init__(self, address, *args, connect_timeout: float = 5.0, streams=None, flush_s: float = 0.0,
                 **kwargs):
        """
        :param address: feste IP (oder IP:Port, z.B. fuer die Dummy-Umgebung) des Geraets im
                         Netzwerk - kein serieller Port.
        :param streams: (26.10.2026, drei Zellen an einem GC) Gasstroeme, die der Messplan im Kreis
                         messen kann: Liste von {name: Z1, valves: {ventilname: A|B, ...}} aus config.yml.
                         Die Ventile sind eigene Geraete (z.B. raspi_gpio_relay_valve); Setup reicht sie
                         nach dem Verbinden ueber link_devices() herein.
        :param flush_s: Spuelzeit in Sekunden nach dem Umschalten der Ventile, bevor der Lauf startet.
        :param connect_timeout: TCP-Verbindungsaufbau-Timeout in Sekunden (aus config.yml).
                                 Das Antwort-Timeout pro Anfrage kommt ueber den bestehenden,
                                 generischen Mechanismus aus config.yml: `command_parameters:
                                 {timeout: <Sekunden>}` auf diesem Geraet (s. CommandParameterFactory).
        """
        self.connect_timeout = float(connect_timeout)
        self._schedule = None
        self.streams = {}            # Stromname -> {Ventilname: Position}
        for entry in streams or []:
            try:
                self.streams[str(entry["name"])] = {str(k): str(v) for k, v in dict(entry["valves"]).items()}
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"microgc streams: Eintrag {entry!r} braucht 'name' und 'valves'") from error
        self.flush_s = float(flush_s)
        self._valves = {}            # Ventilname -> Geraet (nach link_devices)
        super().__init__(address, *args, **kwargs)

    def link_devices(self, devices_and_channels):
        """Von Setup nach dem Verbinden aller Geraete aufgerufen: Ventile der Gasstroeme aufloesen.
        Fehlende Ventile werden protokolliert; ein Messplan mit diesem Strom scheitert dann beim Start."""
        wanted = {valve for positions in self.streams.values() for valve in positions}
        for valve in sorted(wanted):
            try:
                self._valves[valve] = devices_and_channels[valve]
            except KeyError:
                self.log.error("Gasstrom-Ventil {valve} ist kein verbundenes Geraet - Messplaene mit Stroemen "
                               "scheitern, bis es in config.yml eingetragen und erreichbar ist.", valve=valve)

    def _stream_names(self, streams) -> list:
        """'Z1;Z2' -> ['Z1', 'Z2']; 'alle'/'all' -> alle konfigurierten; ''/None -> [] (ein Strom, wie bisher).
        Unbekannte Stroeme oder nicht verbundene Ventile sind ein Fehler (das Experiment scheitert sofort,
        statt stundenlang die falsche Zelle zu messen)."""
        text = str(streams or "").strip()
        if not text:
            return []
        if text.lower() in ("alle", "all", "*"):
            names = list(self.streams)
        else:
            names = [x.strip() for x in text.split(";") if x.strip()]
        unknown = [x for x in names if x not in self.streams]
        if unknown:
            raise ValueError(f"GC-Messplan: unbekannte Gasstroeme {unknown}; konfiguriert sind {list(self.streams)}")
        missing = sorted({valve for x in names for valve in self.streams[x] if valve not in self._valves})
        if missing:
            raise ValueError(f"GC-Messplan: Ventile {missing} sind nicht verbunden")
        return names

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
            if "json_body" in values:
                return path  # runWhenReady steht im JSON-Koerper (s. HTTPCommandTransport.write_command)
            return f"{path}?runWhenReady=true"
        if path == PATH_RUN_DATA_PREFIX:
            return run_data_path(str(values["location"]))
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

    def run_method_named(self, name, tags="", poll_interval=5, **kwargs):
        """Die geladene Methode mit LAUFNAMEN und Tags ausfuehren (POST cmd.run mit
        {"runWhenReady": true, "annotations": {"name": ..., "tags": [...]}} - exakt wie
        MicroGCFusionAPI.control.runWithName(), Quelltext 0.0.8 gelesen 08.10.2026). Tags als
        Semikolon-Liste ("Kolbe;MP"), weil das Frontend Kommas in Parameterwerten zu Punkten macht.
        NOCH NICHT am Geraet getestet (08.10.: Geraet war im BakeOut); Fallback ist run_method()."""
        tag_list = [t.strip() for t in str(tags).split(";") if t.strip()]
        body = {"runWhenReady": True, "annotations": {"name": str(name), "tags": tag_list}}
        self.write("RUN", command_values={"json_body": body}, **kwargs)
        return self._wait_until_ready(poll_interval)

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
                # 13.10.2026: zusaetzlich die Konzentrationen als einzelne Observablen (gc_H2, ...),
                # und mit echtem Zeitstempel (der Default-Parameter von update_observables wird nur
                # einmal beim Import ausgewertet und waere sonst Stunden alt).
                values = concentrations_from_run_data(run_data_result.json or {})
                values["last_run_data"] = run_data_result.json
                self.update_observables(values, time.time())
                return run_data_result
            run_data_cmd.deferred_result.addCallback(store)
            return run_data_cmd.deferred_result

        d = self.query("LAST_RUN_LOCATION", **kwargs).deferred_result
        d.addCallback(fetch_run_data)
        return d


    # -----------------------------------------------------------------------------------------
    # GC-Messplan innerhalb eines Experiments (13.10.2026). Ablauf:
    #   run_schedule_named() laedt die Methode EINMAL, haelt das Geraet mit busy() bis zum Ende des
    #   Plans im Busy-Zustand (damit das Experiment erst nach dem letzten Lauf endet) und stellt je
    #   Zeitpunkt einen Timer. Faellige Laeufe werden NACHEINANDER abgearbeitet (ist der vorige noch
    #   nicht fertig, startet der naechste sofort danach - "ueberfaellig"). Je Lauf: warten bis das
    #   Geraet im Leerlauf ist, dataLocation merken, POST cmd.run mit Name/Tags, Status pollen bis der
    #   Lauf aktiv war und wieder im Leerlauf ist, neue dataLocation holen, Laufdaten laden,
    #   Konzentrationen als Observablen melden (gc_<Label>) und JSON+CSV wie das Skript ablegen.
    #   Alle Befehle laufen mit urgent=True: sie werden VOR dem Wartebefehl des Experimentendes in die
    #   Warteschlange gestellt und auch im Busy-Zustand ausgefuehrt (devicestate.Busy, wie das
    #   Netzteil-Polling). stop() bricht den Plan ab (Timer weg, kein neuer Befehl mehr); ein am
    #   Geraet laufender Lauf laeuft dort zu Ende (cmd.abort bewusst nicht benutzt).
    # -----------------------------------------------------------------------------------------

    def run_schedule_named(self, method_name, prefix, minutes="0;10;20", tags="", poll_interval=5,
                           save_dir="", until_minutes=None, final_run=False, streams="", **kwargs):
        """Messplan: zu jedem Zeitpunkt in `minutes` (Minuten ab jetzt, Trenner ';') einen benannten
        Lauf '<prefix>_<t> min' mit `tags` (Trenner ';') starten. Rueckgabe: Deferred, das feuert,
        wenn der letzte Lauf abgeholt ist (Geraet war bis dahin Busy).
        final_run=True (16.10.2026): nach Ablauf von `until_minutes` (= Elektrolyseende) und nach dem
        letzten planmaessigen Lauf noch eine Abschlussmessung '<prefix>_Ende <t> min'; das Experiment
        endet erst danach. Entfaellt, wenn ein planmaessiger Zeitpunkt schon >= until_minutes liegt.
        config.yml: [microgc, run_schedule_named, [], {method_name: "...", prefix: "{versuch}",
                     minutes: "{gc_minutes}", until_minutes: "{minutes}", tags: "Kolbe;MP", final_run: true}]
        streams="Z1;Z2;Z3" (26.10.2026): die Gasstroeme aus `streams:` des Geraets werden im Kreis gemessen
        (jeder faellige Lauf = naechster Strom, Name '<prefix>_<Strom> <t> min', Tag <Strom>, Konzentrationen
        als gc_<Strom>_<Label>); vor jedem Lauf werden die Ventile des Stroms gestellt und flush_s gewartet.
        "alle" = alle konfigurierten Stroeme in Reihenfolge."""
        times, continuous = plan_times(minutes, until_minutes)
        stream_names = self._stream_names(streams)
        if not times and not continuous:
            raise ValueError(f"GC-Messplan ohne Zeitpunkte: {minutes!r}")
        if self._schedule is not None and not self._schedule.cancelled and self._schedule.is_open():
            self.log.warn("GC-Messplan laeuft bereits - der alte wird abgebrochen.")
            self._cancel_schedule("replaced")
        tag_list = [t.strip() for t in str(tags).split(";") if t.strip()]
        schedule = self._schedule = _Schedule(prefix, tag_list, times, poll_interval, save_dir,
                                              continuous=continuous, until_minutes=until_minutes,
                                              final_run=_truthy(final_run), streams=stream_names)
        if stream_names:
            self.log.info("GC-Messplan '{prefix}': {n} Gasstroeme im Kreis: {streams} (Spuelzeit {flush:g} s)",
                          prefix=prefix, n=len(stream_names), streams=stream_names, flush=self.flush_s)
        if continuous:
            self.log.info("GC-Messplan '{prefix}': DAUERMESSUNG, naechster Lauf sobald das Geraet fertig ist, "
                          "bis {until} min; Methode {method}, Tags {tags}",
                          prefix=prefix, until=until_minutes, method=method_name, tags=tag_list)
        else:
            self.log.info("GC-Messplan '{prefix}': {n} Laeufe bei {times} min, Methode {method}, Tags {tags}",
                          prefix=prefix, n=len(times), times=times, method=method_name, tags=tag_list)
        if schedule.final_run:
            self.log.info("GC-Messplan '{prefix}': dazu eine Abschlussmessung nach {until} min, sobald der "
                          "letzte planmaessige Lauf fertig ist.", prefix=prefix, until=until_minutes)
        elif _truthy(final_run):
            self.log.info("GC-Messplan '{prefix}': keine gesonderte Abschlussmessung - "
                          "{reason}.", prefix=prefix,
                          reason="until_minutes fehlt" if schedule.until_s is None
                          else "ein planmaessiger Lauf liegt schon am Ende")

        self.load_method(method_name, **kwargs)
        condition = ObservableEqualsValueCondition(
            f"GC-Messplan '{prefix}' beendet", self, SCHEDULE_OBSERVABLE, "finished")
        wait_command = self.busy(condition)
        planned = -1 if continuous else len(times) + (max(1, len(stream_names)) if schedule.final_run else 0)
        self.update_observables({SCHEDULE_OBSERVABLE: "running", "gc_runs_done": 0,
                                 "gc_runs_planned": planned}, time.time())
        if continuous:
            schedule.timers.append(self.callLater(0.0, self._schedule_next, schedule))
        for minute in times:
            schedule.timers.append(self.callLater(max(0.0, 60.0 * minute), self._schedule_due, schedule, minute))
        if schedule.final_run:
            schedule.timers.append(self.callLater(schedule.until_s, self._schedule_final_due, schedule))
        return wait_command.deferred_result

    def _schedule_due(self, schedule, minute):
        if schedule.cancelled or schedule is not self._schedule:
            return
        schedule.due.append(minute)
        self._schedule_next(schedule)

    def _schedule_final_due(self, schedule):
        # until_minutes sind um (Elektrolyse zu Ende): die Abschlussmessung ist faellig. Sie startet,
        # sobald kein planmaessiger Lauf mehr offen ist (_schedule_next).
        if schedule.cancelled or schedule is not self._schedule:
            return
        schedule.final_due = True
        self.log.info("GC-Messplan '{prefix}': Elektrolyse zu Ende, Abschlussmessung folgt{wait}.",
                      prefix=schedule.prefix,
                      wait=" nach dem laufenden Lauf" if schedule.active is not None or schedule.due else "")
        self._schedule_next(schedule)

    def _queue_final_run(self, schedule):
        """Abschlussmessung einreihen, wenn sie faellig ist und alle planmaessigen Laeufe durch sind."""
        if schedule.final_done or schedule.final_pending is not None or not schedule.final_due:
            return False
        schedule.final_pending = round((time.time() - schedule.t0) / 60.0, 1)
        schedule.final_streams = list(schedule.streams) or [None]
        schedule.remaining += len(schedule.final_streams)
        return True

    def _schedule_next(self, schedule):
        if schedule.cancelled or schedule.active is not None:
            return
        if not schedule.due and schedule.final_pending is None:
            if schedule.continuous:
                elapsed = time.time() - schedule.t0
                if elapsed < schedule.until_s:
                    # Dauermessung: naechster Lauf sofort, benannt nach der verstrichenen Minute
                    schedule.due.append(round(elapsed / 60.0, 1))
                    schedule.remaining += 1
                elif not schedule.final_done:
                    # Dauermessung vorbei; die Abschlussmessung ist ab until_s faellig (Timer kann noch
                    # ausstehen, wenn der letzte Lauf genau am Ende fertig wurde) -> hier direkt faellig.
                    schedule.final_due = True
                    if not self._queue_final_run(schedule):
                        return
                else:
                    schedule.remaining = 0
                    self._schedule_finished(schedule)
                    return
                return self._schedule_next(schedule)
            if schedule.remaining == 0:
                if not schedule.final_done:
                    if self._queue_final_run(schedule):
                        return self._schedule_next(schedule)
                    return   # Abschlussmessung noch nicht faellig: Timer _schedule_final_due wartet
                self._schedule_finished(schedule)
            return
        if schedule.due:
            minute = schedule.due.pop(0)
            stream = schedule.next_stream()
            name = run_name(_stream_prefix(schedule.prefix, stream), minute)
            late = time.time() - schedule.t0 - 60.0 * minute
            if late > 30 and not schedule.continuous:
                self.log.warn("GC-Lauf '{name}' startet {late:.0f} s verspaetet (voriger Lauf noch nicht fertig).",
                              name=name, late=late)
        else:
            minute = schedule.final_pending
            stream = schedule.final_streams.pop(0) if schedule.final_streams else None
            if not schedule.final_streams:
                schedule.final_pending = None
                schedule.final_done = True
            name = f"{_stream_prefix(schedule.prefix, stream)}_Ende {minute:g} min"
            self.log.info("GC-Abschlussmessung '{name}' nach dem Ende der Elektrolyse.", name=name)
        schedule.active = minute
        d = self._schedule_run(schedule, name, minute, stream=stream)
        d.addBoth(self._schedule_run_done, schedule, minute, name)

    def _schedule_run_done(self, result, schedule, minute, name):
        schedule.active = None
        schedule.remaining -= 1
        if isinstance(result, failure.Failure):
            schedule.failed += 1
            self.log.error("GC-Lauf '{name}' ({minute:g} min) fehlgeschlagen: {err}",
                           name=name, minute=minute, err=result.getErrorMessage())
        else:
            schedule.done += 1
        if not schedule.cancelled:
            self.update_observables({"gc_runs_done": schedule.done}, time.time())
            self._schedule_next(schedule)
        return None

    def _schedule_finished(self, schedule):
        self.log.info("GC-Messplan '{prefix}' beendet: {done} Laeufe, {failed} fehlgeschlagen.",
                      prefix=schedule.prefix, done=schedule.done, failed=schedule.failed)
        self.update_observables({SCHEDULE_OBSERVABLE: "finished"}, time.time())

    def _cancel_schedule(self, reason):
        schedule = self._schedule
        if schedule is None or schedule.cancelled:
            return
        if not schedule.is_open():
            return  # regulaer beendet, nichts abzubrechen
        schedule.cancelled = True
        for timer in schedule.timers:
            try:
                if timer.active():
                    timer.cancel()
            except Exception:  # noqa: BLE001
                pass
        schedule.timers = []
        schedule.due = []
        self.log.info("GC-Messplan '{prefix}' abgebrochen ({reason}): {done} von {n} Laeufen fertig.",
                      prefix=schedule.prefix, reason=reason, done=schedule.done, n=len(schedule.minutes))
        self.update_observables({SCHEDULE_OBSERVABLE: "cancelled"}, time.time())

    def stop(self):
        # Experimentende/"Stop Experiments": Plan abbrechen, dann der normale Abschaltpfad (final_commands).
        self._cancel_schedule("stop")
        return super().stop()

    # -- ein einzelner Lauf des Plans (Deferred-Kette, Befehle als urgent) --

    def _urgent_query(self, command_name, **kwargs):
        return self.query(command_name, urgent=True, run_while_device_busy=True, **kwargs).deferred_result

    def _poll_status(self, schedule, is_done, max_seconds, what):
        """Status alle poll_interval s abfragen, bis is_done(system, seen_states) wahr ist.
        Feuert mit dem letzten Systemstatus; Fehler bei Geraetefehler/Zeitueberschreitung/Abbruch."""
        result = defer.Deferred()
        seen = []
        started = time.time()

        def ask():
            if schedule.cancelled:
                result.errback(RuntimeError(f"abgebrochen beim Warten auf {what}"))
                return
            self._urgent_query("STATUS").addCallbacks(check, result.errback)

        def check(reply):
            system = str(reply.parameters.get("system", ""))
            seen.append(system)
            if system.startswith(ERROR_PREFIX):
                result.errback(RuntimeError(f"Geraetefehler beim Warten auf {what}: {system}"))
            elif is_done(system, seen):
                result.callback(system)
            elif time.time() - started > max_seconds:
                result.errback(RuntimeError(f"Zeitueberschreitung ({max_seconds:.0f} s) beim Warten auf {what}, "
                                            f"letzter Status {system}"))
            else:
                self.callLater(schedule.poll_interval, ask)
            return None

        ask()
        return result

    def _schedule_run(self, schedule, name, minute, stream=None):
        state = {}

        def switch_stream(_):
            # Ventile auf den Gasstrom der Zelle stellen, dann Spuelzeit abwarten. Stehen die Ventile
            # schon so (gleicher Strom wie beim vorigen Lauf), entfaellt beides.
            if stream is None or stream == schedule.last_stream:
                return None
            if schedule.cancelled:
                raise RuntimeError("abgebrochen vor dem Umschalten")
            positions = self.streams[stream]
            self.log.info("GC-Lauf '{name}': Gasstrom {stream}, Ventile {valves}, dann {flush:g} s spuelen.",
                          name=name, stream=stream, valves=positions, flush=self.flush_s)
            writes = [self._valves[valve].set_position(position).deferred_result
                      for valve, position in positions.items()]
            d = defer.gatherResults(writes, consumeErrors=True)
            d.addErrback(lambda f: failure.Failure(RuntimeError(
                f"Ventil fuer Gasstrom {stream} konnte nicht gestellt werden: {f.value.subFailure.getErrorMessage()}")))

            def flushed(_):
                schedule.last_stream = stream
                self.update_observables({"gc_stream": stream}, time.time())
                if self.flush_s <= 0:
                    return None
                waited = defer.Deferred()
                self.callLater(self.flush_s, waited.callback, None)
                return waited
            d.addCallback(flushed)
            return d

        def wait_idle(_):
            # Nach loadMethod ist das Geraet einige Sekunden in loading-method; ein cmd.run in dieser
            # Phase startet zwar, verliert aber Name/Tags (13.10.2026). Also erst Leerlauf abwarten.
            return self._poll_status(schedule, lambda system, seen: system in IDLE_STATES, MAX_LOAD_S,
                                     f"Leerlauf vor '{name}'")

        def remember_location(_):
            return self._urgent_query("LAST_RUN_LOCATION").addCallback(
                lambda reply: state.__setitem__("before", reply.parameters.get("last_run_location")))

        def start_run(_):
            if schedule.cancelled:
                raise RuntimeError("abgebrochen vor dem Start")
            tags = list(schedule.tags) + ([str(stream)] if stream is not None else [])
            body = {"runWhenReady": True, "annotations": {"name": str(name), "tags": tags}}
            self.log.info("GC-Lauf '{name}' ({minute:g} min) wird gestartet.", name=name, minute=minute)
            return self.write("RUN", command_values={"json_body": body}, urgent=True,
                              run_while_device_busy=True).deferred_result

        def wait_finished(_):
            def done(system, seen):
                was_active = any(s in ACTIVE_STATES for s in seen)
                return was_active and system in IDLE_STATES
            return self._poll_status(schedule, done, MAX_RUN_S, f"Ende von '{name}'")

        def fetch_location(_):
            if schedule.cancelled:
                raise RuntimeError("abgebrochen nach dem Laufende, Laufdaten werden nicht abgeholt")
            return self._urgent_query("LAST_RUN_LOCATION").addCallback(
                lambda reply: reply.parameters.get("last_run_location"))

        def fetch_data(location):
            if not location or location == state.get("before"):
                self.log.warn("GC-Lauf '{name}': /v1/lastRun unveraendert - keine neuen Laufdaten am Geraet.",
                              name=name)
                return None
            return self._urgent_query("RUN_DATA", command_values={"location": location}, timeout=60.0
                                      ).addCallback(lambda reply: reply.json)

        def publish(run_data):
            if run_data is None:
                return None
            self._publish_run_data(schedule, run_data, name, minute, stream=stream)
            return run_data

        d = defer.succeed(None)
        d.addCallback(wait_idle)
        d.addCallback(switch_stream)
        d.addCallback(remember_location)
        d.addCallback(start_run)
        d.addCallback(wait_finished)
        d.addCallback(fetch_location)
        d.addCallback(fetch_data)
        d.addCallback(publish)
        return d

    def _publish_run_data(self, schedule, run_data, name, minute, stream=None):
        values = concentrations_from_run_data(run_data)
        if stream is not None:
            # je Zelle eigene Observablen (gc_Z1_H2, ...), damit das Monitoring die Zellen nebeneinander zeigt
            values = {f"gc_{stream}_{key[3:]}": value for key, value in values.items()}
            values["gc_stream"] = str(stream)
        values.update({"gc_run_name": name, "gc_run_minute": float(minute),
                       "gc_run_timestamp": str(run_data.get("runTimeStamp", ""))})
        now = time.time()
        self.update_observables(values, now)
        annotations = run_data.get("annotations") or {}
        if annotations.get("name") != name:
            self.log.warn("GC-Lauf '{name}': Geraet hat den Namen nicht uebernommen (annotations={ann}).",
                          name=name, ann=annotations)
        summary = ", ".join(f"{k[3:]}={v:.3g}" for k, v in values.items()
                            if k.startswith("gc_") and not k.endswith("_norm") and isinstance(v, float)
                            and k not in ("gc_run_minute",) and v)
        self.log.info("GC-Lauf '{name}' fertig: {summary}", name=name, summary=summary or "keine Peaks > 0")
        try:
            schedule.save_dir.mkdir(parents=True, exist_ok=True)
            stem = schedule.save_dir / safe_filename(name)
            stem.with_suffix(".json").write_text(json.dumps(run_data, indent=1), encoding="utf-8")
            stem.with_suffix(".csv").write_text(run_data_to_csv(run_data), encoding="utf-8")
        except OSError as error:
            self.log.error("GC-Lauf '{name}': Laufdaten konnten nicht gespeichert werden: {err}",
                           name=name, err=error)


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
