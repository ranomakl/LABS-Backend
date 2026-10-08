#!/usr/bin/env python3
"""Messwerte aus dem Roh-Log eines Laufs rekonstruieren, wenn values.json fehlt (z.B. Lauf im
Fehlerzustand abgebrochen, bevor das Backend die Werte geschrieben hat - so passiert 08.10.2026,
Versuch 26174, Netzteil-Timeout).

Liest logs/<J>/<M>/<T>/<Experiment-ID>/log.txt, erkennt die Geraeteantworten und schreibt
values.json im selben Format wie das Backend (Geraet -> Observable -> [[t, wert], ...]) sowie
lauf.json (finishing_time/final_state ergaenzt). Danach: tools/auswertung.py "<ID>" --html.

Erkannt werden:
  Joy-IT DPM86xx     :01r30=<V*100>.  -> psu.voltage ;  :01r31=<mA>.  -> psu.current
  Bronkhorst         measure_raw -> mfc.flow (mL/min, 32000 = max_flow) ; counter_raw -> mfc.counter
  Longer WT600       Received E9 01 06 52 4A 00 <rpm> <run> <cw> -> dosing_pump.speed_rpm/running/clockwise/flow_ml_min

Aufruf aus der Repo-Wurzel:
    .venv/bin/python tools/werte_aus_log.py "<Experiment-ID>"            # nur wenn values.json fehlt
    .venv/bin/python tools/werte_aus_log.py "<Experiment-ID>" --force    # vorhandene values.json ueberschreiben
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import struct
import sys

_HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(_HIER)

# Geraeteparameter aus config.yml (einfach gehalten: nur die zwei Zahlen, die die Umrechnung braucht)
def _config_zahlen():
    max_flow, ml_per_rev = 50.0, 0.8883
    try:
        import yaml
        c = yaml.safe_load(open(os.path.join(WURZEL, "config.yml")))
        mfc = c["devices"].get("mfc", {}); max_flow = float(mfc.get("max_flow_ml_min", max_flow))
        p = c["devices"].get("dosing_pump", {})
        ml_per_rev = float(p.get("tubing_table", {}).get(p.get("tubing", ""), ml_per_rev))
    except Exception:
        pass
    return max_flow, ml_per_rev


def _ts(line):
    # 2026-10-08T13:58:46+0200 ...  -> Epoch (lokale Zeit mit Offset)
    try:
        return dt.datetime.fromisoformat(line[:24]).timestamp()
    except ValueError:
        return None


def rekonstruiere(logpfad, max_flow, ml_per_rev):
    psu_v = re.compile(r"Received :01r30=(-?\d+)\.")
    psu_i = re.compile(r"Received :01r31=(-?\d+)\.")
    mfc_m = re.compile(r"'measure_raw': '([0-9A-F]{4})'")
    mfc_c = re.compile(r"'counter_raw': '([0-9A-F]{8})'")
    mfc_s = re.compile(r"'setpoint_raw': '([0-9A-F]{4})'")
    pump = re.compile(r"Received E9 01 06 52 4A 00 ([0-9A-F]{2}) 0([01]) 0([01])")
    out = {"psu": {}, "mfc": {}, "dosing_pump": {}}
    def add(dev, key, t, v): out[dev].setdefault(key, []).append([t, v])
    n = 0
    with open(logpfad, encoding="utf-8", errors="replace") as f:
        for line in f:
            if "Received" not in line and "_raw'" not in line:
                continue
            t = _ts(line)
            if t is None:
                continue
            n += 1
            if "Joy-IT" in line:
                m = psu_v.search(line)
                if m: add("psu", "voltage", t, int(m.group(1)) / 100); continue
                m = psu_i.search(line)
                if m: add("psu", "current", t, int(m.group(1)) / 1000); continue
            elif "Bronkhorst" in line:
                m = mfc_m.search(line)
                if m: add("mfc", "flow", t, int(m.group(1), 16) / 32000 * max_flow); continue
                m = mfc_c.search(line)
                if m: add("mfc", "counter", t, struct.unpack(">f", bytes.fromhex(m.group(1)))[0]); continue
                m = mfc_s.search(line)
                if m: add("mfc", "setpoint", t, int(m.group(1), 16) / 32000 * max_flow); continue
            elif "WT600" in line:
                m = pump.search(line)
                if m:
                    rpm, running, cw = int(m.group(1), 16), m.group(2) == "1", m.group(3) == "1"
                    add("dosing_pump", "speed_rpm", t, rpm); add("dosing_pump", "running", t, running)
                    add("dosing_pump", "clockwise", t, cw)
                    add("dosing_pump", "flow_ml_min", t, round(rpm * ml_per_rev, 4) if running else 0.0)
    # Ladungsmenge als Zeitintegral des Stroms nachrechnen (wie TimeIntegral im Backend, Trapez)
    cur = out["psu"].get("current")
    if cur:
        q = 0.0; aoc = [[cur[0][0], 0.0]]
        for (t0, i0), (t1, i1) in zip(cur, cur[1:]):
            q += (i0 + i1) / 2 * (t1 - t0); aoc.append([t1, round(q, 3)])
        out["psu"]["amount_of_charge"] = aoc
    return {d: o for d, o in out.items() if o}, n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("experiment")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    treffer = [d for d in glob.glob(os.path.join(WURZEL, "logs", "*", "*", "*", args.experiment)) if os.path.isdir(d)]
    if not treffer:
        sys.exit(f"Lauf '{args.experiment}' nicht gefunden.")
    ordner = sorted(treffer)[-1]
    vj = os.path.join(ordner, "values.json")
    if os.path.exists(vj) and not args.force:
        sys.exit(f"{vj} existiert schon - mit --force ueberschreiben.")
    max_flow, ml_per_rev = _config_zahlen()
    werte, n = rekonstruiere(os.path.join(ordner, "log.txt"), max_flow, ml_per_rev)
    if not werte:
        sys.exit("Keine Geraeteantworten im Log gefunden.")
    json.dump(werte, open(vj, "w"))
    zeiten = [p[0] for o in werte.values() for r in o.values() for p in r]
    print(f"values.json geschrieben: {vj}")
    for dev, obs in werte.items():
        print(f"  {dev}: " + ", ".join(f"{k} n={len(v)}" for k, v in obs.items()))
    lj = os.path.join(ordner, "lauf.json")
    info = json.load(open(lj)) if os.path.exists(lj) else {"experiment_id": args.experiment}
    if not info.get("finishing_time"):
        info["finishing_time"] = max(zeiten)
    if not info.get("final_state"):
        info["final_state"] = "Failed (values.json aus log.txt rekonstruiert, tools/werte_aus_log.py)"
    info.setdefault("starting_time", min(zeiten))
    json.dump(info, open(lj, "w"), indent=1)
    print(f"lauf.json ergaenzt: Start {dt.datetime.fromtimestamp(info['starting_time']):%H:%M:%S}, "
          f"Ende {dt.datetime.fromtimestamp(info['finishing_time']):%H:%M:%S}, {n} Antwortzeilen ausgewertet")


if __name__ == "__main__":
    main()
