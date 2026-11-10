# -*- test-case-name: backend.test.test_valve_dosing -*-
"""Zugabe ueber ein Auswahlventil (Messstand II, 06.11.2026): Vorratsgefaesse an den Ports eines
Mehrwegeventils, EINE Pumpe zwischen Ventil und Reaktor.

Aufbau:
    Port 1 Wasser, Port 2..n Reagenzien -> Ventil -> Schlauch (Totvolumen) -> Pumpe -> Reaktor

Eine Zugabe aus Port P ist immer:
    1. Pumpe steht, Ventil auf P, Position zuruecklesen
    2. Pumpe foerdert das Volumen V            (vorne laeuft dabei Wasser aus dem Schlauch in den Reaktor)
    3. Pumpe steht, Ventil auf den Wasser-Port
    4. Pumpe foerdert die Spuelmenge           (schiebt das Reagenz in den Reaktor, Schlauch wieder Wasser)
In den Reaktor gelangen also V + Spuelmenge; davon V Reagenz. Die Spuelmenge ist
flush_factor * dead_volume_ml. Aus dem Wasser-Port selbst wird ohne Spuelschritt gefoerdert.

Warum ein MixIn im Pumpentreiber und kein eigenes Geraet: Jedes Geraet im Backend braucht eine
Verbindung, und ein Experiment schickt seine Befehle an alle Geraete gleichzeitig los - die Reihenfolge
"erst Ventil, dann Pumpe, dann wieder Ventil" laesst sich in config.yml nicht ausdruecken. Vorbild ist
der microGC, der die Ventile seiner Gasstroeme selbst stellt (link_devices, inficon_microgc_fusion.py):
die Pumpe bleibt fuer die ganze Zugabe Busy und stellt das Ventil selbst. Der Kern (Setup, Experiment)
bleibt unveraendert.

Der Wirts-Treiber (z.B. longer_bt100_1f.Device) muss liefern:
    _dosing_pump_start(rate_ml_min) -> Befehl (.deferred_result feuert bei der Bestaetigung, .time ist der
                                       Zeitpunkt des Sendens); muss auch im Busy-Zustand rausgehen
    _dosing_pump_stop()             -> Befehl, ebenso
und in __init__ self._init_dosing(dosing) aufrufen (dosing = Abschnitt `dosing:` des Geraets in der
Konfiguration, None = Funktion nicht eingerichtet).

Zeitsteuerung: Die Laufzeit zaehlt vom SENDEN des Startbefehls bis zum SENDEN des Stoppbefehls. Beide
Frames sind gleich lang, die Uebertragungszeit (bei 1200 Baud ~90 ms) hebt sich damit auf. Waehrend
einer Zugabe wird die Pumpe NICHT periodisch abgefragt, damit der Stopp nie hinter einer Abfrage wartet.

Rezept (10.11.2026): add_recipe faehrt mehrere Zugaben nacheinander ab (Leitsalz, Wasser, Saeuren, NaOH, ...)
und fuellt am Ende mit Wasser auf ein Zielvolumen auf. Die Volumina werden direkt eingegeben (mL); die
Umrechnung aus Konzentrationen (Blatt 2 der Exceltabelle) ist noch offen und kommt davor, nicht hierher.
Vor dem ersten Ventilschritt wird das Volumenbudget geprueft: passt Rezept + Spuelwasser nicht ins
Zielvolumen, laeuft nichts an und der Lauf endet als Failed.

Nicht in diesem Modul: die pH-Schleife. Sie baut auf den Schritten hier auf (plan_addition/plan_recipe
liefern eine Schrittliste, _dosing_request faehrt sie ab).
"""

import time

from twisted.internet import defer

from backend.conditions.conditions import ObservableEqualsValueCondition
from backend.devices import devicestate

DOSING_OBSERVABLE = "dosing"          # "running" / "finished" / "failed" / "cancelled"

# Pflichtangaben unter `dosing:` - bewusst OHNE Default (Kalibrier- und Aufbauwerte: ein plausibler
# Fehlwert wuerde still falsche Konzentrationen ansetzen; ein Startabbruch ist billiger).
REQUIRED_KEYS = ("valve", "water_port", "dead_volume_ml", "flush_factor",
                 "min_rate_ml_min", "max_rate_ml_min", "min_dose_seconds")
OPTIONAL_KEYS = {"valve_timeout_s": 20.0,    # so lange darf das Ventil brauchen, bis es die Position meldet
                 "settle_s": 0.5}            # Pause zwischen Ventil-Bestaetigung und Pumpenstart


class DosingSettings:
    """Geprueft eingelesener Abschnitt `dosing:` eines Pumpengeraets."""

    def __init__(self, config: dict):
        if not isinstance(config, dict):
            raise ValueError(f"dosing: muss ein Abschnitt mit Schluesseln sein, nicht {config!r}")
        missing = [key for key in REQUIRED_KEYS if key not in config]
        if missing:
            raise ValueError(f"dosing: Pflichtangaben fehlen: {missing} (kein Default - Aufbau-/Kalibrierwerte)")
        unknown = [key for key in config if key not in REQUIRED_KEYS and key not in OPTIONAL_KEYS]
        if unknown:
            raise ValueError(f"dosing: unbekannte Schluessel {unknown}; erlaubt sind "
                             f"{list(REQUIRED_KEYS) + list(OPTIONAL_KEYS)}")
        self.valve = str(config["valve"])
        self.water_port = int(config["water_port"])
        self.dead_volume_ml = float(config["dead_volume_ml"])
        self.flush_factor = float(config["flush_factor"])
        self.min_rate_ml_min = float(config["min_rate_ml_min"])
        self.max_rate_ml_min = float(config["max_rate_ml_min"])
        self.min_dose_seconds = float(config["min_dose_seconds"])
        self.valve_timeout_s = float(config.get("valve_timeout_s", OPTIONAL_KEYS["valve_timeout_s"]))
        self.settle_s = float(config.get("settle_s", OPTIONAL_KEYS["settle_s"]))
        if self.water_port < 1:
            raise ValueError(f"dosing: water_port {self.water_port} muss >= 1 sein")
        if self.dead_volume_ml <= 0:
            raise ValueError(f"dosing: dead_volume_ml {self.dead_volume_ml} muss > 0 sein")
        if self.flush_factor < 1:
            raise ValueError(f"dosing: flush_factor {self.flush_factor} muss >= 1 sein "
                             f"(sonst bleibt Reagenz im Schlauch)")
        if not 0 < self.min_rate_ml_min <= self.max_rate_ml_min:
            raise ValueError(f"dosing: 0 < min_rate_ml_min ({self.min_rate_ml_min}) <= max_rate_ml_min "
                             f"({self.max_rate_ml_min}) verletzt")
        if self.min_dose_seconds <= 0:
            raise ValueError(f"dosing: min_dose_seconds {self.min_dose_seconds} muss > 0 sein")
        if self.valve_timeout_s <= 0 or self.settle_s < 0:
            raise ValueError("dosing: valve_timeout_s muss > 0 und settle_s >= 0 sein")

    @property
    def flush_volume_ml(self) -> float:
        return self.dead_volume_ml * self.flush_factor


def choose_rate(volume_ml: float, settings: DosingSettings, rate=None) -> float:
    """Flussrate (mL/min) fuer ein Volumen. Ohne Vorgabe so, dass die Pumpe mindestens
    min_dose_seconds laeuft (kleine Volumen langsam = Start/Stopp faellt weniger ins Gewicht),
    begrenzt auf [min_rate, max_rate]. Eine vorgegebene Rate ausserhalb der Grenzen ist ein Fehler."""
    volume_ml = float(volume_ml)
    if volume_ml <= 0:
        raise ValueError(f"Volumen {volume_ml} mL muss > 0 sein")
    if rate is not None and str(rate).strip() != "" and float(rate) != 0:
        rate = float(rate)
        if not settings.min_rate_ml_min <= rate <= settings.max_rate_ml_min:
            raise ValueError(f"Flussrate {rate} mL/min ausserhalb {settings.min_rate_ml_min}-"
                             f"{settings.max_rate_ml_min} mL/min (dosing: min/max_rate_ml_min)")
        return rate
    wanted = volume_ml / (settings.min_dose_seconds / 60.0)
    return max(settings.min_rate_ml_min, min(settings.max_rate_ml_min, wanted))


class Step:
    """Ein Schritt einer Zugabe. kind: 'valve' (port), 'pump' (volume_ml, rate_ml_min, role), 'pause' (seconds).
    role: 'reagent' (zaehlt als zugegebenes Reagenz) oder 'water' (Spuel-/Fuellwasser)."""

    def __init__(self, kind, port=None, volume_ml=None, rate_ml_min=None, role=None, seconds=None, label=None):
        self.kind, self.port, self.volume_ml = kind, port, volume_ml
        self.rate_ml_min, self.role, self.seconds = rate_ml_min, role, seconds
        self.label = label        # Name der Zugabe im Rezept (z.B. "Leitsalz"), None bei Einzelzugaben

    @property
    def duration_s(self) -> float:
        if self.kind == "pump":
            return 60.0 * self.volume_ml / self.rate_ml_min
        if self.kind == "pause":
            return self.seconds
        return 0.0

    def __repr__(self):
        if self.kind == "valve":
            return f"Ventil->Port {self.port}"
        if self.kind == "pump":
            return f"{self.role} {self.volume_ml * 1000:g} uL @ {self.rate_ml_min:g} mL/min"
        return f"Pause {self.seconds:g} s"

    def __eq__(self, other):
        return isinstance(other, Step) and repr(self) == repr(other)

    __hash__ = None


def plan_addition(port, volume_ml, settings: DosingSettings, rate=None, repeats=1, pause_s=0.0,
                  positions=None) -> list:
    """Schrittliste fuer `repeats` Zugaben von je volume_ml aus `port`.
    Reagenz-Port: Ventil, Dosis, Ventil auf Wasser, Spuelen. Wasser-Port: Ventil, Volumen (kein Spuelen).
    positions: Anzahl Ventilpositionen (None = unbekannt, dann keine Obergrenze pruefbar)."""
    port_f = float(port)
    if port_f != int(port_f):
        raise ValueError(f"Port {port!r} ist keine ganze Zahl")
    port = int(port_f)
    if port < 1 or (positions is not None and port > int(positions)):
        raise ValueError(f"Port {port} gibt es nicht (Ventil hat "
                         f"{positions if positions is not None else '?'} Positionen)")
    repeats_f = float(repeats)
    if repeats_f != int(repeats_f) or repeats_f < 1:
        raise ValueError(f"Wiederholungen {repeats!r} muessen eine ganze Zahl >= 1 sein")
    pause_s = float(pause_s or 0.0)
    if pause_s < 0:
        raise ValueError(f"Pause {pause_s} s darf nicht negativ sein")
    volume_ml = float(volume_ml)
    dose_rate = choose_rate(volume_ml, settings, rate)
    steps = []
    for index in range(int(repeats_f)):
        if index and pause_s:
            steps.append(Step("pause", seconds=pause_s))
        if port == settings.water_port:
            if not index:
                steps.append(Step("valve", port=port))
            steps.append(Step("pump", volume_ml=volume_ml, rate_ml_min=dose_rate, role="water"))
        else:
            flush = settings.flush_volume_ml
            steps.append(Step("valve", port=port))
            steps.append(Step("pump", volume_ml=volume_ml, rate_ml_min=dose_rate, role="reagent"))
            steps.append(Step("valve", port=settings.water_port))
            steps.append(Step("pump", volume_ml=flush, rate_ml_min=choose_rate(flush, settings, rate),
                              role="water"))
    return steps


def parse_additions(text) -> list:
    """Rezeptzeile -> Liste (label, port, volume_ml). Eintraege mit ';' getrennt, je Eintrag
    'Name=port:volumen' oder 'Name=volumen' (ohne Port = Wasser-Port) oder ohne Name 'port:volumen'.
    Volumen 0 oder leer = Eintrag entfaellt (so lassen sich Zugaben im Frontend "ausschalten");
    Port 0 ebenso (Routinen mit EINEM Volumen fuer mehrere Ports, z.B. vorfuellen: nicht genutzte Ports = 0).
    Beispiel: 'Leitsalz=3:5;Wasser=20;Saeure=4:1.2;NaOH=5:0' -> drei Zugaben, NaOH entfaellt."""
    additions = []
    if text is None:
        return additions
    for raw in str(text).split(";"):
        entry = raw.strip()
        if not entry:
            continue
        label, _, spec = entry.rpartition("=")
        label, spec = label.strip(), spec.strip()
        if ":" in spec:
            port_text, _, volume_text = spec.partition(":")
            port_text = port_text.strip()
        else:
            port_text, volume_text = "", spec
        volume_text = volume_text.strip()
        if volume_text in ("", "None"):
            continue
        try:
            volume_ml = float(volume_text)
        except ValueError:
            raise ValueError(f"Rezept: Volumen {volume_text!r} in {entry!r} ist keine Zahl")
        if volume_ml < 0:
            raise ValueError(f"Rezept: Volumen {volume_ml} mL in {entry!r} darf nicht negativ sein")
        if volume_ml == 0:
            continue
        if port_text in ("", "None"):
            port = None
        else:
            try:
                port_f = float(port_text)
            except ValueError:
                raise ValueError(f"Rezept: Port {port_text!r} in {entry!r} ist keine Zahl")
            if port_f != int(port_f):
                raise ValueError(f"Rezept: Port {port_text!r} in {entry!r} ist keine ganze Zahl")
            port = int(port_f)
            if port == 0:
                continue
        additions.append((label or (f"Port {port}" if port is not None else "Wasser"), port, volume_ml))
    return additions


def _number_or_zero(value) -> float:
    if value is None or str(value).strip() in ("", "None"):
        return 0.0
    return float(value)


def plan_recipe(additions, settings: DosingSettings, target_volume_ml=None, pause_s=0.0,
                start_volume_ml=0.0, positions=None) -> list:
    """Schrittliste fuer ein Rezept: die Zugaben aus `additions` (Liste (label, port, volume_ml), port None =
    Wasser-Port) der Reihe nach, jede Reagenz-Zugabe mit Spuelen, dazwischen `pause_s` Sekunden Ruehrzeit.
    target_volume_ml > 0: am Ende mit Wasser auffuellen, bis start_volume_ml + alles Gefoerderte das
    Zielvolumen erreicht. Passt das Rezept samt Spuelwasser nicht hinein -> ValueError, nichts laeuft an."""
    target_volume_ml = _number_or_zero(target_volume_ml)
    start_volume_ml = _number_or_zero(start_volume_ml)
    pause_s = _number_or_zero(pause_s)
    if target_volume_ml < 0 or start_volume_ml < 0:
        raise ValueError("Rezept: Zielvolumen und Startvolumen duerfen nicht negativ sein")
    if pause_s < 0:
        raise ValueError(f"Rezept: Pause {pause_s} s darf nicht negativ sein")
    if not additions and target_volume_ml <= 0:
        raise ValueError("Rezept: keine Zugabe mit Volumen > 0 und kein Zielvolumen - nichts zu tun")
    steps = []
    last_port = None

    def append(label, port, volume_ml):
        nonlocal last_port
        if steps and pause_s:
            steps.append(Step("pause", seconds=pause_s, label=label))
        for step in plan_addition(port, volume_ml, settings, positions=positions):
            if step.kind == "valve" and step.port == last_port:
                continue                              # Ventil steht schon dort
            step.label = label
            steps.append(step)
            if step.kind == "valve":
                last_port = step.port

    for label, port, volume_ml in additions:
        append(label, settings.water_port if port is None else port, volume_ml)
    delivered = start_volume_ml + plan_totals(steps)["total_ml"]
    if target_volume_ml > 0:
        fill_ml = target_volume_ml - delivered
        if fill_ml < -1e-9:
            raise ValueError(f"Rezept ergibt {delivered:.3f} mL (Zugaben + Spuelwasser + Startvolumen), "
                             f"mehr als das Zielvolumen {target_volume_ml:.3f} mL - Zielvolumen erhoehen oder "
                             f"Zugaben verkleinern")
        if fill_ml > 1e-9:
            append(f"Auffuellen auf {target_volume_ml:g} mL", settings.water_port, fill_ml)
    return steps


def plan_totals(steps) -> dict:
    """Summe der Schrittliste: Reagenz, Wasser, Gesamtvolumen in den Reaktor (mL) und Dauer (s, ohne Ventil)."""
    reagent = sum(s.volume_ml for s in steps if s.kind == "pump" and s.role == "reagent")
    water = sum(s.volume_ml for s in steps if s.kind == "pump" and s.role == "water")
    return {"reagent_ml": reagent, "water_ml": water, "total_ml": reagent + water,
            "duration_s": sum(s.duration_s for s in steps)}


class _Run:
    def __init__(self, steps, title):
        self.steps = list(steps)
        self.title = title
        self.index = 0
        self.open = True          # False nach finished/failed/cancelled
        self.timer = None         # laufender IDelayedCall (Dosierzeit, Pause, Ventil-Nachfrage)
        self.watchdog = None
        self.pump_running = False
        self.reagent_port = None  # Port, dessen Reagenz evtl. noch im Schlauch steht
        self.label = None         # Zugabe des Rezepts, die gerade laeuft (Observable dosing_addition)
        self.dosed_ml = 0.0
        self.flushed_ml = 0.0


class ValveDosingMixIn:
    """Siehe Modulkopf. Oeffentliche Methoden (aus der Konfiguration: [pump1, add_from_port, [], {...}]):
    add_from_port, pump_water, add_recipe."""

    _dosing_settings = None
    _dosing_valve = None
    _dosing = None                         # aktueller/letzter _Run
    _dosing_now = staticmethod(time.time)  # Tests setzen eine task.Clock ein
    WATCHDOG_MARGIN_S = 15.0               # so viel laenger als geplant darf ein Schritt dauern

    def _init_dosing(self, dosing):
        self._dosing_settings = None if dosing is None else DosingSettings(dosing)
        self._dosing_valve = None
        self._dosing = None

    def link_devices(self, devices_and_channels):
        """Von Setup nach dem Verbinden aller Geraete aufgerufen: das Ventil aufloesen."""
        if self._dosing_settings is None:
            return
        try:
            self._dosing_valve = devices_and_channels[self._dosing_settings.valve]
        except KeyError:
            self.log.error("dosing: Ventil {valve} ist kein verbundenes Geraet - Zugaben scheitern, bis es in der "
                           "Konfiguration eingetragen und erreichbar ist.", valve=self._dosing_settings.valve)

    # -- oeffentliche Befehle ------------------------------------------------------------------------

    def add_from_port(self, port, volume, rate=None, repeats=1, pause_s=0.0, **kwargs):
        """`repeats` Zugaben von je `volume` mL aus Ventil-Port `port`, jede gefolgt von der Spuelmenge
        Wasser. rate (mL/min) leer/0 = automatisch. Die Pumpe ist bis zum Ende Busy.
        Aus dem Wasser-Port: nur das Volumen, kein Spuelschritt."""
        return self._dosing_request(
            f"Zugabe Port {port}",
            lambda settings, positions: plan_addition(port, volume, settings, rate, repeats, pause_s,
                                                      positions=positions))

    def pump_water(self, volume, rate=None, repeats=1, pause_s=0.0, **kwargs):
        """`repeats` mal `volume` mL Wasser (Wasser-Port) foerdern: Spuelen, Schlauch fuellen, Auffuellen
        und Auswiegen der Dosiergenauigkeit."""
        return self._dosing_request(
            "Wasser",
            lambda settings, positions: plan_addition(settings.water_port, volume, settings, rate, repeats,
                                                      pause_s, positions=positions))

    def add_recipe(self, additions, target_volume=None, pause_s=0.0, start_volume=0.0, title="Ansatz", **kwargs):
        """Rezept: mehrere Zugaben nacheinander, dann mit Wasser auf `target_volume` mL auffuellen.
        additions: Rezeptzeile 'Name=port:volumen;Name=volumen;...' (siehe parse_additions; Volumen 0 =
        Eintrag entfaellt, ohne Port = Wasser). pause_s: Ruehrzeit zwischen den Zugaben. start_volume:
        was schon im Reaktor ist (zaehlt zum Zielvolumen). Die Pumpe ist bis zum Ende Busy.
        Passt das Rezept nicht ins Zielvolumen, bewegt sich nichts und der Lauf endet als Failed.
        title: Name im Log und in den Meldungen (vorfuellen nutzt denselben Baustein)."""
        return self._dosing_request(
            str(title),
            lambda settings, positions: plan_recipe(parse_additions(additions), settings, target_volume,
                                                    pause_s, start_volume, positions=positions))

    # -- Ablauf ----------------------------------------------------------------------------------------

    def _dosing_emit(self, values: dict):
        self.update_observables(values, self._dosing_now())

    def _dosing_request(self, title, plan):
        """plan(settings, positions) -> Schrittliste; darf ValueError/TypeError werfen (-> Failed ohne Bewegung)."""
        error, steps = None, []
        try:
            if self._dosing_settings is None:
                raise ValueError("Geraet hat keinen Abschnitt dosing: in der Konfiguration")
            if self._dosing_valve is None:
                raise ValueError(f"Ventil {self._dosing_settings.valve} ist nicht verbunden")
            if self._dosing is not None and self._dosing.open:
                raise ValueError(f"es laeuft noch '{self._dosing.title}'")
            steps = plan(self._dosing_settings, getattr(self._dosing_valve, "positions", None))
        except (ValueError, TypeError) as exc:
            error = exc
        run = _Run(steps, title)
        if error is None:
            self._dosing = run
        # Auch ein Eingabefehler laeuft ueber Busy + Fehlerpfad: so endet das Experiment sauber als
        # Failed, statt dass eine Ausnahme mitten im Experimentstart das Setup haengen laesst.
        condition = ObservableEqualsValueCondition(f"{title} beendet", self, DOSING_OBSERVABLE, "finished")
        wait_command = self.busy(condition)
        totals = plan_totals(steps)
        self._dosing_emit({DOSING_OBSERVABLE: "running", "dosing_step": "Start", "dosing_addition": "",
                           "dosed_ml": 0.0, "flushed_ml": 0.0, "delivered_ml": 0.0, "dosing_flow_ml_min": 0.0})
        if error is None:
            self.log.info("{title}: {n} Schritte, {reagent:.3f} mL Reagenz + {water:.3f} mL Wasser = {total:.3f} mL "
                          "in den Reaktor, ca. {seconds:.0f} s. Schritte: {steps}", title=title, n=len(steps),
                          reagent=totals["reagent_ml"], water=totals["water_ml"], total=totals["total_ml"],
                          seconds=totals["duration_s"], steps=str(steps))
            wait_command.deferred_execution.addCallback(
                lambda _: self.callLater(0, self._dosing_next, run))
        else:
            wait_command.deferred_execution.addCallback(
                lambda _: self.callLater(0, self._dosing_fail, run, error))
        return wait_command.deferred_result

    def _dosing_next(self, run):
        if not run.open:
            return
        if run.index >= len(run.steps):
            self._dosing_finish(run)
            return
        step = run.steps[run.index]
        run.index += 1
        if step.label is not None and step.label != run.label:
            run.label = step.label
            labels = []
            for other in run.steps:
                if other.label is not None and other.label not in labels:
                    labels.append(other.label)
            number = labels.index(step.label) + 1
            self._dosing_emit({"dosing_addition": f"{number}/{len(labels)}: {step.label}"})
            self.log.info("{title}: Zugabe {n}/{total} '{label}'", title=run.title, n=number,
                          total=len(labels), label=step.label)
        if step.kind == "valve":
            deferred, limit = self._dosing_valve_step(run, step), self._dosing_settings.valve_timeout_s
        elif step.kind == "pump":
            deferred, limit = self._dosing_pump_step(run, step), step.duration_s
        else:
            deferred, limit = self._dosing_pause_step(run, step), step.duration_s

        def expired():
            run.watchdog = None
            self._dosing_fail(run, RuntimeError(f"Schritt '{step}' nicht innerhalb von "
                                                f"{limit + self.WATCHDOG_MARGIN_S:.0f} s abgeschlossen"))
        if run.open:
            run.watchdog = self.callLater(limit + self.WATCHDOG_MARGIN_S, expired)

        def done(_):
            self._dosing_cancel_call(run, "watchdog")
            self._dosing_next(run)

        def failed(failure):
            self._dosing_cancel_call(run, "watchdog")
            self._dosing_fail(run, failure)
        deferred.addCallbacks(done, failed)

    @staticmethod
    def _dosing_cancel_call(run, name):
        call = getattr(run, name)
        setattr(run, name, None)
        try:
            if call is not None and call.active():
                call.cancel()
        except Exception:  # noqa: BLE001
            pass

    def _dosing_valve_step(self, run, step):
        """Ventil stellen und Position zuruecklesen, bis sie stimmt (oder valve_timeout_s um sind).
        Ventile ohne GET_POS-Befehl: die Bestaetigung des Stellbefehls genuegt."""
        valve, settings, port = self._dosing_valve, self._dosing_settings, step.port
        result = defer.Deferred()
        deadline = self._dosing_now() + settings.valve_timeout_s
        can_read = "GET_POS" in getattr(valve, "commands", {})
        self._dosing_emit({"dosing_step": f"Ventil auf Port {port}"})

        def settled():
            run.timer = None
            if run.open:
                if port != settings.water_port:
                    run.reagent_port = port
                self._dosing_emit({"dosing_port": port})
                result.callback(port)

        def confirmed(_=None):
            if run.open:
                run.timer = self.callLater(settings.settle_s, settled)

        def ask(_=None):
            run.timer = None
            if not run.open:
                return
            if not can_read:
                confirmed()
                return
            valve.query("GET_POS").deferred_result.addCallbacks(check, result.errback)

        def check(reply):
            try:
                position = int(float(reply.parameters["position"]))
            except (AttributeError, KeyError, TypeError, ValueError):
                position = None
            if position == port:
                confirmed()
            elif self._dosing_now() >= deadline:
                result.errback(RuntimeError(f"Ventil meldet Position {position} statt {port} "
                                            f"(nach {settings.valve_timeout_s:g} s)"))
            elif run.open:
                run.timer = self.callLater(0.5, ask)
            return None

        if run.pump_running:
            return defer.fail(RuntimeError("Ventil darf nur bei stehender Pumpe schalten"))
        valve_state = getattr(valve, "state", None)
        if valve_state in (devicestate.Stopped, devicestate.Shutdown, devicestate.Error):
            return defer.fail(RuntimeError(f"Ventil ist im Zustand {getattr(valve_state, '__name__', valve_state)} "
                                           f"und nimmt keine Befehle an"))
        try:
            command = valve.set_position(port)
        except Exception as exc:  # noqa: BLE001
            return defer.fail(exc)
        command.deferred_result.addCallbacks(ask, result.errback)
        return result

    def _dosing_pump_step(self, run, step):
        """Pumpe step.duration_s laufen lassen. Die Zeit zaehlt vom Senden des Start- bis zum Senden
        des Stoppbefehls (gleiche Framelaenge, Uebertragungszeit hebt sich auf)."""
        result = defer.Deferred()
        seconds = step.duration_s
        commands = {}
        what = "Reagenz" if step.role == "reagent" else "Wasser"
        self._dosing_emit({"dosing_step": f"{what} {step.volume_ml * 1000:g} uL bei {step.rate_ml_min:g} mL/min"})

        def sent_at(key):
            # Command.time = Zeitpunkt des (letzten) Sendens, gesetzt in commandstate.Sent.enter. Achtung:
            # deferred_execution taugt dafuer nicht - ein sofort gesendeter Befehl hat es schon gefeuert
            # und durch ein neues ersetzt, bevor man hier einen Callback anhaengen kann (Dummy-Lauf
            # 06.11.2026: 10,13 s statt 10,00 s, weil ab der Bestaetigung gezaehlt wurde).
            sent = getattr(commands.get(key), "time", None)
            return self._dosing_now() if sent is None else sent

        def stop():
            run.timer = None
            if not run.open:
                return
            commands["stop"] = self._dosing_pump_stop()
            commands["stop"].deferred_result.addCallbacks(stopped, result.errback)

        def started(_):
            if not run.open:
                return
            now = self._dosing_now()
            # dosing_flow_ml_min: Rate, solange die Pumpe foerdert, sonst 0 - im Monitoring ein Rechteck je Schritt
            self._dosing_emit({"dosing_flow_ml_min": round(step.rate_ml_min, 6)})
            if now - requested > 1.0:
                self.log.warn("{title}: Start der Pumpe erst nach {waited:.1f} s bestaetigt (Wiederholung?) - "
                              "dieses Volumen ist ungenau.", title=run.title, waited=now - requested)
            run.timer = self.callLater(max(0.0, seconds - (now - sent_at("start"))), stop)

        def stopped(_):
            run.pump_running = False
            actual = sent_at("stop") - sent_at("start")
            if step.role == "reagent":
                run.dosed_ml += step.volume_ml
            else:
                run.flushed_ml += step.volume_ml
                if step.volume_ml >= self._dosing_settings.dead_volume_ml:
                    run.reagent_port = None       # Schlauch ist wieder mit Wasser gefuellt
            self.log.info("{title}: {what} {volume:.3f} mL, Laufzeit Soll {soll:.2f} s / Ist {ist:.2f} s",
                          title=run.title, what=what, volume=step.volume_ml, soll=seconds, ist=actual)
            self._dosing_emit({"dosing_flow_ml_min": 0.0, "dosed_ml": round(run.dosed_ml, 6),
                               "flushed_ml": round(run.flushed_ml, 6),
                               "delivered_ml": round(run.dosed_ml + run.flushed_ml, 6)})
            if run.open:
                result.callback(None)

        run.pump_running = True
        requested = self._dosing_now()
        commands["start"] = self._dosing_pump_start(step.rate_ml_min)
        commands["start"].deferred_result.addCallbacks(started, result.errback)
        return result

    def _dosing_pause_step(self, run, step):
        result = defer.Deferred()
        self._dosing_emit({"dosing_step": f"Pause {step.seconds:g} s"})

        def done():
            run.timer = None
            if run.open:
                result.callback(None)
        run.timer = self.callLater(step.seconds, done)
        return result

    def _dosing_finish(self, run):
        run.open = False
        self.log.info("{title} fertig: {reagent:.3f} mL Reagenz + {water:.3f} mL Wasser in den Reaktor.",
                      title=run.title, reagent=run.dosed_ml, water=run.flushed_ml)
        self._dosing_emit({"dosing_step": "fertig", "dosing_addition": "fertig", DOSING_OBSERVABLE: "finished"})

    def _dosing_close(self, run, outcome, message):
        """Gemeinsames Ende fuer Fehler und Abbruch: Timer weg, Warnung zum Schlauchinhalt.
        Die Pumpe wird hier bewusst NICHT selbst gestoppt: das macht der Abschaltpfad des Geraets
        (stop() -> final_commands, dringend, mit Wiederholung bis zur Bestaetigung). Ein eigener
        Stoppbefehl unmittelbar davor liegt noch unbeantwortet auf der Leitung, wenn die Abschaltserie
        rausgeht - die Antworten werden dann vertauscht zugeordnet (Dummy-Lauf 06.11.2026:
        AlreadyCalledError im Protokoll, Verbindung zur Pumpe weg).
          - Abbruch: stop() ruft direkt danach super().stop().
          - Fehler:  der Error-Zustand laesst das Experiment scheitern, das ruft stop() aller Geraete
                     im selben Reaktor-Durchlauf (Experiment.update -> Failed.enter)."""
        run.open = False
        self._dosing_cancel_call(run, "timer")
        self._dosing_cancel_call(run, "watchdog")
        if run.pump_running:
            self.log.warn("{title}: Pumpe laeuft noch - der Abschaltpfad stoppt sie.", title=run.title)
            run.pump_running = False
        if run.reagent_port is not None:
            self.log.error("{title}: im Schlauch steht noch Reagenz von Port {port} - vor dem naechsten Ansatz "
                           "spuelen (Routine spuelen).", title=run.title, port=run.reagent_port)
        self._dosing_emit({"dosing_step": message, "dosing_flow_ml_min": 0.0, DOSING_OBSERVABLE: outcome})

    def _dosing_fail(self, run, reason):
        if not run.open:
            return
        message = reason.getErrorMessage() if hasattr(reason, "getErrorMessage") else str(reason)
        self.log.error("{title} FEHLGESCHLAGEN nach {reagent:.3f} mL Reagenz + {water:.3f} mL Wasser: {err}",
                       title=run.title, reagent=run.dosed_ml, water=run.flushed_ml, err=message)
        self._dosing_close(run, "failed", f"FEHLER: {message}")
        # Error-Zustand -> das Experiment geht nach Failed und schaltet alle Geraete ab (Experiment.update).
        self.state = devicestate.Error

    def _dosing_cancel(self, reason):
        run = self._dosing
        if run is None or not run.open:
            return
        self.log.warn("{title} abgebrochen ({reason}) nach {reagent:.3f} mL Reagenz + {water:.3f} mL Wasser.",
                      title=run.title, reason=reason, reagent=run.dosed_ml, water=run.flushed_ml)
        self._dosing_close(run, "cancelled", f"abgebrochen ({reason})")

    def stop(self):
        # Experimentende / "Stop Experiments": eine laufende Zugabe abbrechen, dann der normale
        # Abschaltpfad des Pumpentreibers (final_commands = Pumpe stopp).
        self._dosing_cancel("stop")
        return super().stop()
