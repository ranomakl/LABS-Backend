#!/usr/bin/env python3
"""Auswertung der Versuchslogs im Nachhinein - liest logs/<Jahr>/<Monat>/<Tag>/<Experiment-ID>/values.json.

Nur Standardbibliothek (kein pandas/matplotlib im venv noetig). Greift NICHT auf Geraete zu.

Aufruf aus der Repo-Wurzel:
    python tools/auswertung.py                       # neuester Lauf: Uebersicht + Tabelle (alle 10 s)
    python tools/auswertung.py --liste               # alle Laeufe mit Datum, Dauer, Observablen
    python tools/auswertung.py --liste --tag 2026-10-08
    python tools/auswertung.py "test_0810-Polling test-3"       # bestimmter Lauf (Experiment-ID)
    python tools/auswertung.py --takt 600            # Tabelle alle 10 Minuten (Frage 15 im Versuchsdokument)
    python tools/auswertung.py --takt 0              # jeden einzelnen Messwert, kein Raster
    python tools/auswertung.py --csv werte.csv       # Tabelle zusaetzlich als CSV (Excel-tauglich, Semikolon)
    python tools/auswertung.py --roh                 # Rohwerte je Observable untereinander (Zeit;Wert)

Spalten der Tabelle: Uhrzeit, Versuchszeit in s, dann je Observable "geraet.observable". Im Raster
(--takt > 0) steht pro Zeile der jeweils LETZTE Wert vor dem Rasterzeitpunkt (so, wie ihn das
Frontend auch anzeigt); "-" = noch kein Wert bis dahin. Die Geraetezustaende ("state") werden nicht
als Spalte gefuehrt, sondern nur in der Uebersicht gezaehlt.
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys

_HIER = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(os.path.dirname(_HIER), "logs")


def _lokal(ts: float, mit_datum: bool = False) -> str:
    fmt = "%Y-%m-%d %H:%M:%S" if mit_datum else "%H:%M:%S"
    return dt.datetime.fromtimestamp(ts).strftime(fmt)


def alle_laeufe():
    """[(startzeit, pfad, experiment_id)] - sortiert nach Startzeit (= erster Messwert, nicht Verzeichnis)."""
    laeufe = []
    for wurzel, _dirs, dateien in os.walk(LOGS):
        if "values.json" in dateien:
            pfad = os.path.join(wurzel, "values.json")
            try:
                daten = json.load(open(pfad))
            except (json.JSONDecodeError, OSError):
                continue
            zeiten = _messzeiten(daten)
            start = min(zeiten) if zeiten else os.path.getmtime(pfad)
            laeufe.append((start, wurzel, os.path.basename(wurzel), daten))
    laeufe.sort()
    return laeufe


def _messzeiten(daten):
    return [p[0] for obs in daten.values() for name, reihe in obs.items() if name != "state" for p in reihe]


def _reihen(daten):
    """{'geraet.observable': [(t, wert), ...]} ohne 'state', zeitlich sortiert."""
    out = {}
    for geraet, obs in daten.items():
        for name, reihe in obs.items():
            if name == "state" or not reihe:
                continue
            out[f"{geraet}.{name}"] = sorted((float(t), w) for t, w in reihe)
    return out


def _fmt(w):
    if isinstance(w, bool):
        return "ja" if w else "nein"
    if isinstance(w, float):
        return f"{w:.4g}" if abs(w) < 1e4 else f"{w:.6g}"
    return str(w)


def uebersicht(exp_id, daten):
    reihen = _reihen(daten)
    zeiten = _messzeiten(daten)
    print(f"Lauf:        {exp_id}")
    if not zeiten:
        print("  (keine Messwerte, nur Geraetezustaende)")
        return
    t0, t1 = min(zeiten), max(zeiten)
    print(f"Start:       {_lokal(t0, True)}")
    print(f"Ende:        {_lokal(t1, True)}   Dauer {t1 - t0:.0f} s")
    print(f"Geraete:     {', '.join(daten)}")
    print("Observablen:")
    for name, reihe in reihen.items():
        werte = [w for _, w in reihe]
        zahlen = [w for w in werte if isinstance(w, (int, float)) and not isinstance(w, bool)]
        if zahlen:
            stat = f"min {_fmt(min(zahlen))}  max {_fmt(max(zahlen))}  mittel {_fmt(sum(zahlen) / len(zahlen))}"
        else:
            stat = f"werte {sorted(set(map(str, werte)))}"
        dauer = reihe[-1][0] - reihe[0][0]
        takt = f", ~{dauer / (len(reihe) - 1):.2f} s Takt" if len(reihe) > 1 and dauer > 0 else ""
        print(f"  {name:<26} n={len(reihe):<5} {stat}  (erster {_fmt(werte[0])}, letzter {_fmt(werte[-1])}{takt})")
    zustaende = {g: len(o.get("state", [])) for g, o in daten.items()}
    print(f"Zustandswechsel (nicht in Tabelle): {zustaende}")
    print()


def tabelle(daten, takt):
    """Zeilen [(uhrzeit, versuchszeit_s, {name: wert})] - Raster mit 'letzter Wert bis dahin' oder alle Punkte."""
    reihen = _reihen(daten)
    zeiten = _messzeiten(daten)
    if not zeiten:
        return [], []
    t0, t1 = min(zeiten), max(zeiten)
    if takt > 0:
        n = int((t1 - t0) // takt) + 1
        raster = [t0 + i * takt for i in range(n)]
        if raster[-1] < t1:
            raster.append(t1)
    else:
        raster = sorted(set(zeiten))
    zeilen = []
    idx = {name: 0 for name in reihen}
    letzter = {name: None for name in reihen}
    for t in raster:
        for name, reihe in reihen.items():
            i = idx[name]
            while i < len(reihe) and reihe[i][0] <= t + 1e-6:
                letzter[name] = reihe[i][1]
                i += 1
            idx[name] = i
        zeilen.append((t, t - t0, dict(letzter)))
    return list(reihen), zeilen


def drucke_tabelle(spalten, zeilen):
    kopf = ["Uhrzeit", "t/s"] + spalten
    rows = [[_lokal(t), f"{dt_s:.0f}"] + ["-" if w.get(s) is None else _fmt(w[s]) for s in spalten] for t, dt_s, w in zeilen]
    breiten = [max(len(str(z[i])) for z in [kopf] + rows) for i in range(len(kopf))]
    for z in [kopf] + rows:
        print("  ".join(str(v).rjust(b) for v, b in zip(z, breiten)))


def schreibe_csv(pfad, spalten, zeilen, exp_id):
    with open(pfad, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["experiment", "datum_uhrzeit", "t_s"] + spalten)
        for t, dt_s, werte in zeilen:
            w.writerow([exp_id, _lokal(t, True), f"{dt_s:.1f}"] + ["" if werte.get(s) is None else werte[s] for s in spalten])
    print(f"CSV geschrieben: {pfad} ({len(zeilen)} Zeilen)")


def drucke_roh(daten):
    for name, reihe in _reihen(daten).items():
        print(f"## {name}  (n={len(reihe)})")
        for t, w in reihe:
            print(f"{_lokal(t, True)};{t:.3f};{_fmt(w)}")
        print()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("experiment", nargs="?", help="Experiment-ID (Verzeichnisname); Standard: neuester Lauf")
    ap.add_argument("--liste", action="store_true", help="alle Laeufe auflisten und beenden")
    ap.add_argument("--tag", help="nur Laeufe dieses Datums (JJJJ-MM-TT), fuer --liste")
    ap.add_argument("--takt", type=float, default=10.0, help="Rasterbreite der Tabelle in s (0 = jeder Messwert); Standard 10")
    ap.add_argument("--csv", metavar="DATEI", help="Tabelle zusaetzlich als CSV schreiben")
    ap.add_argument("--roh", action="store_true", help="statt Tabelle: Rohwerte je Observable")
    ap.add_argument("--keine-tabelle", action="store_true", help="nur die Uebersicht ausgeben")
    args = ap.parse_args()

    laeufe = alle_laeufe()
    if not laeufe:
        sys.exit(f"Keine values.json unter {LOGS} gefunden.")

    if args.liste:
        for start, pfad, exp_id, daten in laeufe:
            if args.tag and _lokal(start, True)[:10] != args.tag:
                continue
            zeiten = _messzeiten(daten)
            dauer = f"{max(zeiten) - min(zeiten):4.0f} s" if zeiten else "  -   "
            obs = ", ".join(_reihen(daten)) or "(nur Zustaende)"
            print(f"{_lokal(start, True)}  {dauer}  {exp_id:<32} {obs}")
        return

    if args.experiment:
        treffer = [l for l in laeufe if l[2] == args.experiment]
        if not treffer:
            sys.exit(f"Lauf '{args.experiment}' nicht gefunden. Vorhandene Laeufe: --liste")
        _start, _pfad, exp_id, daten = treffer[-1]
    else:
        _start, _pfad, exp_id, daten = laeufe[-1]

    uebersicht(exp_id, daten)
    if args.roh:
        drucke_roh(daten)
        return
    spalten, zeilen = tabelle(daten, args.takt)
    if not args.keine_tabelle and zeilen:
        drucke_tabelle(spalten, zeilen)
    if args.csv and zeilen:
        schreibe_csv(args.csv, spalten, zeilen, exp_id)


if __name__ == "__main__":
    main()
