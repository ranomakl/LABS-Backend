"""Erster ECHTER Lauf am Inficon Micro GC Fusion - STEUERT DAS GERAET.

Im Gegensatz zu tools/lese_microgc.py sendet dieses Skript die Steuerbefehle, die auch der Treiber
backend/drivers/inficon_microgc_fusion.py benutzt (dieselben Pfade, dieselben Parameter):
  1. Methode laden   GET /v1/scm/sessions/system-manager!cmd.loadMethod?methodLocation=/v1/methods/userMethods/<name>
  2. Lauf starten    GET /v1/scm/sessions/system-manager!cmd.run?runWhenReady=true
  3. Status pollen, jeden Wechsel mit Zeitstempel protokollieren, bis der Lauf vorbei ist
  4. /v1/lastRun pruefen (neue UUID?) und die Laufdaten als CSV ausgeben/speichern

Zweck: am Geraet klaeren, (a) ob loadMethod/run so funktionieren, (b) in welchen Zustand das Geraet
nach dem Lauf zurueckkehrt ("public:ready" oder "public:standby" - der Treiber wartet auf ready),
(c) wie lange ein Lauf dauert. Verbraucht Traegergas und Probe - nur nach Freigabe des Labors.
BakeOut wird NICHT ausgeloest (--bakeout <min> ist bewusst nicht vorgesehen).

Aufruf aus der Repo-Wurzel:
    .venv/bin/python tools/starte_microgc_lauf.py --ja
    .venv/bin/python tools/starte_microgc_lauf.py --ja --methode microGC_Standard_Method_calibrated_0726
Ohne --ja wird nur gezeigt, was gesendet wuerde.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.drivers.inficon_microgc_fusion import (  # noqa: E402
    PATH_LAST_RUN_LOCATION, PATH_LOAD_METHOD, PATH_RUN, PATH_STATUS, READY_STATE,
    run_data_path, run_data_to_csv,
)
from urllib.parse import quote  # noqa: E402

RUHEZUSTAENDE = {"public:ready", "public:standby"}
AKTIV = {"public:loading-method", "public:preparing", "public:method-running", "public:waiting-for-modules"}


def stamp():
    return datetime.now().strftime("%H:%M:%S")


def get(host, path, timeout):
    url = f"http://{host}{path}"
    with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout) as r:
        body = r.read()
        try:
            return r.status, json.loads(body.decode("utf-8")) if body else None
        except ValueError:
            return r.status, body.decode("utf-8", "replace")[:300]


def status(host, timeout):
    _, data = get(host, PATH_STATUS, timeout)
    return data[0], data[1]


def poll_until(host, timeout, stop_when, max_seconds, interval, label):
    """Pollt den Status, protokolliert Wechsel, endet wenn stop_when(seq, sys, history) wahr."""
    t0 = time.time(); last = None; history = []
    while time.time() - t0 < max_seconds:
        seq, sysstate = status(host, timeout)
        if (seq, sysstate) != last:
            print(f"{stamp()}  [{label}] {time.time()-t0:7.1f}s  system={sysstate!r}  sequence={seq!r}", flush=True)
            last = (seq, sysstate); history.append(sysstate)
        if stop_when(seq, sysstate, history):
            return sysstate, history
        time.sleep(interval)
    print(f"{stamp()}  [{label}] ZEITUEBERSCHREITUNG nach {max_seconds}s, letzter Status {last}", flush=True)
    return last[1] if last else None, history


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="169.254.1.1")
    ap.add_argument("--methode", default="microGC_Standard_Method_calibrated_0726")
    ap.add_argument("--timeout", type=float, default=10.0, help="HTTP-Timeout je Anfrage in s")
    ap.add_argument("--max-lauf", type=float, default=1200, help="max. Wartezeit auf das Laufende in s")
    ap.add_argument("--ausgabe", default="logs/microgc_test", help="Ordner fuer JSON/CSV des Laufs")
    ap.add_argument("--ja", action="store_true", help="wirklich senden (sonst nur anzeigen)")
    args = ap.parse_args()

    load_path = f"{PATH_LOAD_METHOD}?methodLocation=/v1/methods/userMethods/{quote(args.methode, safe='')}"
    run_path = f"{PATH_RUN}?runWhenReady=true"
    print(f"Geraet: http://{args.host}")
    print(f"Wuerde senden: GET {load_path}")
    print(f"               GET {run_path}")
    if not args.ja:
        print("Nur Anzeige. Mit --ja wird wirklich gesendet.")
        return 0

    try:
        seq, sysstate = status(args.host, args.timeout)
        print(f"{stamp()}  Vorher: system={sysstate!r} sequence={seq!r}")
        _, before = get(args.host, PATH_LAST_RUN_LOCATION, args.timeout)
        print(f"{stamp()}  Letzter Lauf vorher: {before['dataLocation']}")

        code, body = get(args.host, load_path, args.timeout)
        print(f"{stamp()}  loadMethod -> HTTP {code} {json.dumps(body)[:300] if body is not None else '(leer)'}")
        final, hist = poll_until(args.host, args.timeout,
                                 lambda s, y, h: y != "public:loading-method", 120, 1, "laden")
        if final and final.startswith("public:error"):
            print("Methode laden fehlgeschlagen - Abbruch, kein Lauf gestartet."); return 2
        time.sleep(2)
        seq, sysstate = status(args.host, args.timeout)
        print(f"{stamp()}  Nach Laden: system={sysstate!r} sequence={seq!r}")

        code, body = get(args.host, run_path, args.timeout)
        print(f"{stamp()}  run -> HTTP {code} {json.dumps(body)[:300] if body is not None else '(leer)'}")
        t_start = time.time()

        def lauf_vorbei(s, y, h):
            war_aktiv = any(x in AKTIV and x != "public:loading-method" for x in h)
            return (war_aktiv and y in RUHEZUSTAENDE) or y.startswith("public:error")
        final, hist = poll_until(args.host, args.timeout, lauf_vorbei, args.max_lauf, 3, "lauf")
        print(f"{stamp()}  Lauf-Dauer gesamt: {time.time()-t_start:.0f}s, Statusfolge: {hist}")
        print(f"ERGEBNIS Rueckkehrzustand: {final!r}  (Treiber wartet auf {READY_STATE!r} -> "
              f"{'passt' if final == READY_STATE else 'READY_STATE im Treiber anpassen!'})")

        _, after = get(args.host, PATH_LAST_RUN_LOCATION, args.timeout)
        print(f"{stamp()}  Letzter Lauf nachher: {after['dataLocation']} "
              f"({'NEU' if after['dataLocation'] != before['dataLocation'] else 'UNVERAENDERT - kein neuer Lauf?'})")
        _, run_data = get(args.host, run_data_path(after["dataLocation"]), 60)
        out = Path(args.ausgabe); out.mkdir(parents=True, exist_ok=True)
        name = datetime.now().strftime("%Y%m%d_%H%M%S_lauf")
        (out / f"{name}.json").write_text(json.dumps(run_data, indent=1), encoding="utf-8")
        csv_text = run_data_to_csv(run_data)
        (out / f"{name}.csv").write_text(csv_text, encoding="utf-8")
        print(f"Methode {run_data.get('methodName')!r}, Zeitstempel {run_data.get('runTimeStamp')!r}, "
              f"gespeichert unter {out}/{name}.json|.csv")
        print(csv_text)
    except urllib.error.HTTPError as e:
        print(f"{stamp()}  HTTP-Fehler {e.code} bei {e.url}: {e.read()[:300]!r}", file=sys.stderr); return 1
    except urllib.error.URLError as e:
        print(f"{stamp()}  Keine Verbindung zu {args.host}: {e.reason}", file=sys.stderr); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
