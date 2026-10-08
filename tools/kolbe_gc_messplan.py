"""microGC-Messplan fuer die Kolbe-Elektrolyse - STEUERT DAS GERAET, laeuft UNABHAENGIG vom Backend.

Warum ein eigenes Werkzeug: Das Backend fuehrt immer nur EIN Experiment gleichzeitig aus. Waehrend
kolbe_elektrolyse (219 min) laeuft, kann es keine microGC-Messung als zweites Experiment starten.
Dieses Skript laeuft deshalb in einem ZWEITEN Terminal parallel zum Backend und spricht den microGC
direkt per HTTP an (stateless, stoert das Backend nicht).

Was es tut (Versuchsplan 26174-26177, Blatt Exp_protocol):
  - wartet, bis das Geraet bereit ist (kein BakeOut/kein Lauf),
  - laedt die Methode einmal,
  - wartet auf ENTER (= Start der Elektrolyse, t = 0),
  - startet zu jedem Zeitpunkt des Plans einen BENANNTEN Lauf "<Versuch>_<t> min" mit Tags
    (POST cmd.run mit annotations, wie MicroGCFusionAPI.control.runWithName),
  - wartet jeweils das Laufende ab und speichert die Laufdaten als JSON + CSV unter
    logs/<Jahr>/<Monat>/<Tag>/microgc/<Name>.json|.csv.

Aufruf aus der Repo-Wurzel (zweites Terminal):
    .venv/bin/python tools/kolbe_gc_messplan.py --versuch 26174 --ja
    .venv/bin/python tools/kolbe_gc_messplan.py --versuch 26174 --einzel rep1 --ja      # Offline-Gasbeutel: "26174_rep1"
    .venv/bin/python tools/kolbe_gc_messplan.py --versuch 26174 --zeiten 0,10,20 --ja   # eigener Plan
Ohne --ja nur Anzeige. Abbruch jederzeit mit Strg+C (ein laufender GC-Lauf wird dadurch NICHT
abgebrochen, er laeuft am Geraet zu Ende).
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

_HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(_HIER))             # Nachbarskript starte_microgc_lauf (get/status/poll_until)
sys.path.insert(0, str(_HIER.parent))      # Repo-Wurzel fuer backend.*
from starte_microgc_lauf import AKTIV, RUHEZUSTAENDE, get, poll_until, stamp, status  # noqa: E402
from backend.drivers.inficon_microgc_fusion import (  # noqa: E402
    PATH_LAST_RUN_LOCATION, PATH_LOAD_METHOD, PATH_RUN, run_data_path, run_data_to_csv,
)
from urllib.parse import quote  # noqa: E402

PLAN_STANDARD = "0,10,20,30,40,50,60,80,100,120,140,160,180,200,219"   # Exp_protocol, Spalte A


def post_json(host, path, body, timeout):
    url = f"http://{host}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        try:
            return r.status, json.loads(raw.decode("utf-8")) if raw else None
        except ValueError:
            return r.status, raw.decode("utf-8", "replace")[:300]


def warte_bis_bereit(host, timeout):
    seq, sysstate = status(host, timeout)
    if sysstate in RUHEZUSTAENDE:
        return sysstate
    print(f"{stamp()}  Geraet ist '{sysstate}' - warte, bis es bereit ist (BakeOut/Lauf zu Ende) ...", flush=True)
    final, _ = poll_until(host, timeout, lambda s, y, h: y in RUHEZUSTAENDE or y.startswith("public:error"),
                          3 * 3600, 10, "warten")
    return final


def lauf(host, timeout, name, tags, max_lauf, ausgabe):
    """Einen benannten Lauf starten, Ende abwarten, Daten speichern. Gibt den CSV-Text zurueck."""
    _, before = get(host, PATH_LAST_RUN_LOCATION, timeout)
    body = {"runWhenReady": True, "annotations": {"name": name, "tags": tags}}
    code, antwort = post_json(host, PATH_RUN, body, timeout)
    print(f"{stamp()}  run '{name}' -> HTTP {code} {json.dumps(antwort)[:200] if antwort is not None else '(leer)'}", flush=True)
    t_start = time.time()

    def lauf_vorbei(s, y, h):
        war_aktiv = any(x in AKTIV and x != "public:loading-method" for x in h)
        return (war_aktiv and y in RUHEZUSTAENDE) or y.startswith("public:error")
    final, hist = poll_until(host, timeout, lauf_vorbei, max_lauf, 3, name)
    dauer = time.time() - t_start
    print(f"{stamp()}  '{name}' fertig nach {dauer / 60:.1f} min, Endzustand {final!r}", flush=True)
    _, after = get(host, PATH_LAST_RUN_LOCATION, timeout)
    if after["dataLocation"] == before["dataLocation"]:
        print(f"{stamp()}  WARNUNG: /v1/lastRun unveraendert - kein neuer Lauf am Geraet?", flush=True)
        return None
    _, run_data = get(host, run_data_path(after["dataLocation"]), 60)
    ausgabe.mkdir(parents=True, exist_ok=True)
    sicher = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
    (ausgabe / f"{sicher}.json").write_text(json.dumps(run_data, indent=1), encoding="utf-8")
    csv_text = run_data_to_csv(run_data)
    (ausgabe / f"{sicher}.csv").write_text(csv_text, encoding="utf-8")
    print(f"{stamp()}  gespeichert: {ausgabe}/{sicher}.json|.csv  (Geraet: Methode {run_data.get('methodName')!r}, "
          f"Zeitstempel {run_data.get('runTimeStamp')!r})", flush=True)
    return csv_text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--versuch", required=True, help="Versuchsnummer, z.B. 26174 (wird Namenspraefix)")
    ap.add_argument("--host", default="169.254.1.1")
    ap.add_argument("--methode", default="microGC_Standard_Method_calibrated_0726")
    ap.add_argument("--zeiten", default=PLAN_STANDARD, help="Messzeitpunkte in min, kommagetrennt")
    ap.add_argument("--einzel", metavar="SUFFIX", help="statt Plan: EIN Lauf mit Namen <versuch>_<SUFFIX> (z.B. rep1)")
    ap.add_argument("--tags", default="Kolbe;MP", help="Tags, mit Semikolon getrennt")
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--max-lauf", type=float, default=1200, help="max. Wartezeit je Lauf in s")
    ap.add_argument("--ausgabe", help="Zielordner; Standard logs/<J>/<M>/<T>/microgc")
    ap.add_argument("--ja", action="store_true", help="wirklich senden (sonst nur anzeigen)")
    args = ap.parse_args()

    tags = [t.strip() for t in args.tags.split(";") if t.strip()]
    heute = date.today()
    ausgabe = Path(args.ausgabe) if args.ausgabe else Path(f"logs/{heute.year}/{heute.month}/{heute.day}/microgc")
    load_path = f"{PATH_LOAD_METHOD}?methodLocation=/v1/methods/userMethods/{quote(args.methode, safe='')}"

    if args.einzel:
        plan = [(None, f"{args.versuch}_{args.einzel}")]
    else:
        plan = [(float(t), f"{args.versuch}_{int(float(t))} min") for t in args.zeiten.split(",") if t.strip()]
    print(f"Geraet: http://{args.host}   Methode: {args.methode}   Tags: {tags}   Ausgabe: {ausgabe}")
    print("Plan:", ", ".join(f"{n}" + (f" @ {t:g} min" if t is not None else "") for t, n in plan))
    print(f"Wuerde senden: GET {load_path}")
    print(f"               POST {PATH_RUN}  {{runWhenReady: true, annotations: {{name, tags}}}}")
    if not args.ja:
        print("Nur Anzeige. Mit --ja wird wirklich gesendet.")
        return 0

    try:
        final = warte_bis_bereit(args.host, args.timeout)
        if final is None or final.startswith("public:error"):
            print("Geraet im Fehlerzustand - Abbruch.", file=sys.stderr)
            return 2
        code, body = get(args.host, load_path, args.timeout)
        print(f"{stamp()}  loadMethod -> HTTP {code}", flush=True)
        final, _ = poll_until(args.host, args.timeout, lambda s, y, h: y != "public:loading-method", 120, 1, "laden")
        if final and final.startswith("public:error"):
            print("Methode laden fehlgeschlagen - Abbruch.", file=sys.stderr)
            return 2

        if args.einzel:
            lauf(args.host, args.timeout, plan[0][1], tags, args.max_lauf, ausgabe)
            return 0

        input(f"\n{stamp()}  Bereit. ENTER druecken, sobald die Elektrolyse im Frontend gestartet ist (t = 0) ... ")
        t0 = time.time()
        print(f"{stamp()}  t = 0 gesetzt. Plan laeuft; Abbruch mit Strg+C.", flush=True)
        for t_min, name in plan:
            soll = t0 + 60 * t_min
            rest = soll - time.time()
            if rest > 0:
                print(f"{stamp()}  naechster Lauf '{name}' in {rest / 60:.1f} min", flush=True)
                time.sleep(rest)
            else:
                print(f"{stamp()}  '{name}' ist {-rest / 60:.1f} min ueberfaellig (voriger Lauf dauerte laenger) - starte sofort", flush=True)
            lauf(args.host, args.timeout, name, tags, args.max_lauf, ausgabe)
        print(f"{stamp()}  Messplan abgeschlossen ({len(plan)} Laeufe).")
    except KeyboardInterrupt:
        print(f"\n{stamp()}  Abgebrochen. Ein laufender GC-Lauf laeuft am Geraet zu Ende.")
        return 130
    except urllib.error.HTTPError as e:
        print(f"{stamp()}  HTTP-Fehler {e.code} bei {e.url}: {e.read()[:300]!r}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"{stamp()}  Keine Verbindung zu {args.host}: {e.reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
