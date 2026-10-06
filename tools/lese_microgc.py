"""Erster Test des Inficon Micro GC Fusion ueber LAN - REINES LESEWERKZEUG.

Sendet ausschliesslich HTTP-GET auf Lese-Endpunkte (Status, Methodenliste, letzter Lauf) und gibt
die Antworten aus. Die Start-Kommandos des Geraets (BakeOut, loadMethod, run - alles Pfade mit
"!cmd.") sind gesperrt: _guarded_get() prueft jede URL gegen eine Whitelist, bevor sie auf die
Leitung geht. Es wird also weder geheizt noch eine Methode geladen oder gestartet.

Benutzt dieselben Pfade und dieselbe JSON->CSV-Umwandlung wie der Treiber
backend/drivers/inficon_microgc_fusion.py, laeuft aber ohne Twisted und ohne Setup.

Aufruf aus der Repo-Wurzel:
    .venv/bin/python tools/lese_microgc.py                       # Status, Methoden, Peaks des letzten Laufs
    .venv/bin/python tools/lese_microgc.py --host 169.254.1.1
    .venv/bin/python tools/lese_microgc.py --csv letzter_lauf.csv --json letzter_lauf.json

Vorher pruefen: LAN-Kabel Pi <-> microGC steckt, eth0 hat eine 169.254.x.x-Adresse
(`ip -brief addr show eth0`; NetworkManager-Profil "Wired connection 1" auf link-local).
Die Adresse des Geraets steht an dessen Display/Weboberflaeche ("automatic IP address").
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.drivers.inficon_microgc_fusion import (  # noqa: E402
    PATH_LAST_RUN_LOCATION, PATH_RUN_DATA_PREFIX, PATH_STATUS, run_data_path, run_data_to_csv,
)

PATH_USER_METHODS = "/v1/methods/userMethods"

# Erlaubt sind nur diese Lesepfade. Alles mit "!cmd." ist ein Steuerbefehl und wird nie gesendet.
ALLOWED_PATHS = (PATH_STATUS, PATH_LAST_RUN_LOCATION, PATH_USER_METHODS)
ALLOWED_PREFIXES = (PATH_RUN_DATA_PREFIX,)


class SafetyViolation(Exception):
    pass


def _guarded_get(host: str, path: str, timeout: float):
    if "!" in path or "?" in path:
        raise SafetyViolation(f"Steuerbefehl oder Parameter in Pfad gesperrt: {path}")
    if path not in ALLOWED_PATHS and not any(path.startswith(p) for p in ALLOWED_PREFIXES):
        raise SafetyViolation(f"Pfad nicht in der Lese-Whitelist: {path}")
    url = f"http://{host}{path}"
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        return response.status, json.loads(body.decode("utf-8")) if body else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="169.254.1.1", help="IP des microGC (Standard: 169.254.1.1)")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP-Timeout in s je Anfrage")
    parser.add_argument("--csv", help="Peak-Tabelle des letzten Laufs in diese CSV-Datei schreiben")
    parser.add_argument("--json", help="Rohdaten des letzten Laufs in diese JSON-Datei schreiben")
    parser.add_argument("--ohne-lauf", action="store_true", help="letzten Lauf nicht abrufen (ca. 250 kB)")
    args = parser.parse_args()

    try:
        status, data = _guarded_get(args.host, PATH_STATUS, args.timeout)
        print(f"Status (HTTP {status}): sequence = {data[0]!r}, system = {data[1]!r}")
        if data[1] != "public:ready":
            print("  Hinweis: Treiber wartet nach BakeOut/Lauf auf 'public:ready' - s. OFFENE_FRAGEN.md.")

        status, methods = _guarded_get(args.host, PATH_USER_METHODS, args.timeout)
        print(f"Methoden auf dem Geraet (HTTP {status}, {len(methods)}):")
        for name in sorted(methods):
            print(f"  {name}")

        if args.ohne_lauf:
            return 0

        status, data = _guarded_get(args.host, PATH_LAST_RUN_LOCATION, args.timeout)
        location = data["dataLocation"]
        print(f"Letzter Lauf (HTTP {status}): dataLocation = {location!r}")
        status, run_data = _guarded_get(args.host, run_data_path(location), args.timeout)
        print(f"Laufdaten (HTTP {status}): Methode {run_data.get('methodName')!r}, "
              f"Zeitstempel {run_data.get('runTimeStamp')!r}, "
              f"Detektoren {list((run_data.get('detectors') or {}).keys())}")
        if args.json:
            Path(args.json).write_text(json.dumps(run_data, indent=1), encoding="utf-8")
            print(f"Rohdaten geschrieben: {args.json}")
        csv_text = run_data_to_csv(run_data)
        if args.csv:
            Path(args.csv).write_text(csv_text, encoding="utf-8")
            print(f"CSV geschrieben: {args.csv}")
        print("Peak-Tabelle (CSV):")
        print(csv_text)
    except urllib.error.URLError as error:
        print(f"Keine Verbindung zu {args.host}: {error.reason}", file=sys.stderr)
        print("Pruefen: LAN-Kabel, `ip -brief addr show eth0` (169.254.x.x?), Adresse am Geraetedisplay.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
