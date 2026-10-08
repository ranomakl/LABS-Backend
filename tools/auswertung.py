#!/usr/bin/env python3
"""Auswertung der Versuchslogs im Nachhinein - liest logs/<Jahr>/<Monat>/<Tag>/<Experiment-ID>/
(values.json mit allen Messwerten, lauf.json mit Typ/Parametern/Einheiten, falls vorhanden).

Nur Standardbibliothek (kein pandas/matplotlib im venv noetig). Greift NICHT auf Geraete zu.

Aufruf aus der Repo-Wurzel:
    python tools/auswertung.py --liste                   # alle Laeufe mit Datum, Dauer, Observablen
    python tools/auswertung.py                           # neuester Lauf: Uebersicht + Tabelle (alle 10 s) im Terminal
    python tools/auswertung.py "<Experiment-ID>"         # bestimmter Lauf
    python tools/auswertung.py --html                    # BERICHT: logs/.../<ID>/bericht.html (Kurven + alle Messwerte)
    python tools/auswertung.py --html --tag 2026-10-08   # Tagesbericht mit allen Laeufen des Tages in einer Datei
    python tools/auswertung.py --html bericht.html       # Bericht an eigenen Pfad
    python tools/auswertung.py --takt 600                # Tabelle alle 10 Minuten (Frage 15 im Versuchsdokument)
    python tools/auswertung.py --takt 0                  # jeden einzelnen Messwert, kein Raster
    python tools/auswertung.py --csv werte.csv           # Tabelle als CSV (Excel-tauglich, Semikolon)
    python tools/auswertung.py --roh                     # Rohwerte je Observable untereinander (Zeit;Wert)

Der HTML-Bericht ist eine einzelne Datei ohne Internet-Abhaengigkeiten: Kopf (Typ, Parameter, Start,
Ende, Dauer), Kennzahlen je Observable, eine Kurve je Observable (mit Fadenkreuz beim Ueberfahren),
die Messwerttabelle im Raster --takt (Standard 10 s) und ein Knopf, der ALLE Rohwerte als CSV
herunterlaedt. Im Browser oeffnen, drucken oder per Mail verschicken.

Raster: pro Zeile steht der jeweils LETZTE Wert vor dem Rasterzeitpunkt (wie im Frontend);
"-" = noch kein Wert bis dahin. Geraetezustaende ("state") sind keine Spalte, nur eine Zaehlung.
"""
import argparse
import base64
import csv
import datetime as dt
import html
import io
import json
import math
import os
import sys

_HIER = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(os.path.dirname(_HIER), "logs")


# ----------------------------------------------------------------------------- Daten lesen

def _lokal(ts: float, mit_datum: bool = False) -> str:
    fmt = "%Y-%m-%d %H:%M:%S" if mit_datum else "%H:%M:%S"
    return dt.datetime.fromtimestamp(ts).strftime(fmt)


class Lauf:
    def __init__(self, pfad, daten, info):
        self.pfad = pfad                       # Verzeichnis des Laufs
        self.id = os.path.basename(pfad)
        self.daten = daten                     # values.json
        self.info = info or {}                 # lauf.json (kann fehlen)
        self.reihen = _reihen(daten)
        zeiten = _messzeiten(daten)
        self.start = self.info.get("starting_time") or (min(zeiten) if zeiten else os.path.getmtime(os.path.join(pfad, "values.json")))
        self.ende = self.info.get("finishing_time") or (max(zeiten) if zeiten else self.start)
        self.einheiten = {f"{o[0]}.{o[1]}": (o[3] if len(o) > 3 else "") for o in self.info.get("observables", [])}

    @property
    def typ(self):
        return self.info.get("experiment_type") or "?"

    @property
    def dauer(self):
        return self.ende - self.start

    def einheit(self, name):
        return self.einheiten.get(name, "")


def alle_laeufe():
    laeufe = []
    for wurzel, _dirs, dateien in os.walk(LOGS):
        if "values.json" not in dateien:
            continue
        try:
            daten = json.load(open(os.path.join(wurzel, "values.json")))
        except (json.JSONDecodeError, OSError):
            continue
        info = None
        if "lauf.json" in dateien:
            try:
                info = json.load(open(os.path.join(wurzel, "lauf.json")))
            except (json.JSONDecodeError, OSError):
                info = None
        laeufe.append(Lauf(wurzel, daten, info))
    laeufe.sort(key=lambda l: l.start)
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


def _ist_zahl(w):
    return isinstance(w, (int, float)) and not isinstance(w, bool)


def _fmt(w):
    if w is None:
        return "-"
    if isinstance(w, bool):
        return "ja" if w else "nein"
    if isinstance(w, float):
        return f"{w:.4g}" if abs(w) < 1e4 else f"{w:.6g}"
    return str(w)


def _kennzahlen(reihe):
    werte = [w for _, w in reihe]
    zahlen = [w for w in werte if _ist_zahl(w)]
    k = {"n": len(reihe), "erster": werte[0], "letzter": werte[-1], "min": None, "max": None, "mittel": None, "takt": None}
    if zahlen:
        k.update(min=min(zahlen), max=max(zahlen), mittel=sum(zahlen) / len(zahlen))
    dauer = reihe[-1][0] - reihe[0][0]
    if len(reihe) > 1 and dauer > 0:
        k["takt"] = dauer / (len(reihe) - 1)
    return k


def tabelle(lauf, takt):
    """([spalten], [(uhrzeit, versuchszeit_s, {name: wert})]) - Raster 'letzter Wert bis dahin' oder alle Punkte."""
    reihen = lauf.reihen
    zeiten = _messzeiten(lauf.daten)
    if not zeiten:
        return [], []
    t0, t1 = min(zeiten), max(zeiten)
    if takt > 0:
        raster = [t0 + i * takt for i in range(int((t1 - t0) // takt) + 1)]
        if raster[-1] < t1:
            raster.append(t1)
    else:
        raster = sorted(set(zeiten))
    zeilen, idx, letzter = [], {n: 0 for n in reihen}, {n: None for n in reihen}
    for t in raster:
        for name, reihe in reihen.items():
            i = idx[name]
            while i < len(reihe) and reihe[i][0] <= t + 1e-6:
                letzter[name] = reihe[i][1]
                i += 1
            idx[name] = i
        zeilen.append((t, t - t0, dict(letzter)))
    return list(reihen), zeilen


# ----------------------------------------------------------------------------- Terminal

def uebersicht(lauf):
    print(f"Lauf:        {lauf.id}")
    print(f"Typ:         {lauf.typ}")
    if lauf.info.get("parameters"):
        print("Parameter:   " + ", ".join(f"{k} = {v['value']} {v['unit'] or ''}".strip() for k, v in lauf.info["parameters"].items()))
    if not lauf.reihen:
        print("  (keine Messwerte, nur Geraetezustaende)")
        return
    print(f"Start:       {_lokal(lauf.start, True)}")
    print(f"Ende:        {_lokal(lauf.ende, True)}   Dauer {lauf.dauer:.0f} s")
    print(f"Geraete:     {', '.join(lauf.daten)}")
    print("Observablen:")
    for name, reihe in lauf.reihen.items():
        k = _kennzahlen(reihe)
        if k["min"] is not None:
            stat = f"min {_fmt(k['min'])}  max {_fmt(k['max'])}  mittel {_fmt(k['mittel'])}"
        else:
            stat = f"werte {sorted(set(_fmt(w) for _, w in reihe))}"
        takt = f", ~{k['takt']:.2f} s Takt" if k["takt"] else ""
        einheit = f" [{lauf.einheit(name)}]" if lauf.einheit(name) else ""
        print(f"  {name + einheit:<30} n={k['n']:<5} {stat}  (erster {_fmt(k['erster'])}, letzter {_fmt(k['letzter'])}{takt})")
    print(f"Zustandswechsel (nicht in Tabelle): { {g: len(o.get('state', [])) for g, o in lauf.daten.items()} }")
    print()


def drucke_tabelle(spalten, zeilen):
    kopf = ["Uhrzeit", "t/s"] + spalten
    rows = [[_lokal(t), f"{s:.0f}"] + [_fmt(w.get(c)) for c in spalten] for t, s, w in zeilen]
    breiten = [max(len(str(z[i])) for z in [kopf] + rows) for i in range(len(kopf))]
    for z in [kopf] + rows:
        print("  ".join(str(v).rjust(b) for v, b in zip(z, breiten)))


def csv_text(lauf, spalten, zeilen):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(["experiment", "datum_uhrzeit", "t_s"] + spalten)
    for t, s, werte in zeilen:
        w.writerow([lauf.id, _lokal(t, True), f"{s:.1f}"] + ["" if werte.get(c) is None else werte[c] for c in spalten])
    return buf.getvalue()


def drucke_roh(lauf):
    for name, reihe in lauf.reihen.items():
        print(f"## {name}  (n={len(reihe)})")
        for t, w in reihe:
            print(f"{_lokal(t, True)};{t:.3f};{_fmt(w)}")
        print()


# ----------------------------------------------------------------------------- HTML-Bericht

def _nice_ticks(lo, hi, n=4):
    if hi <= lo:
        pad = abs(lo) * 0.05 or 1.0
        lo, hi = lo - pad, hi + pad
    roh = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(roh))
    for f in (1, 2, 2.5, 5, 10):
        schritt = f * mag
        if roh <= schritt:
            break
    start = math.floor(lo / schritt) * schritt
    ticks = []
    t = start
    while t <= hi + schritt * 1e-6:
        ticks.append(round(t, 10))
        t += schritt
    return ticks[0], ticks[-1], ticks


def _zeit_ticks(dauer):
    for schritt in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200):
        if dauer / schritt <= 8:
            break
    n = int(dauer // schritt) + 1
    return [i * schritt for i in range(n)], schritt


def _fmt_zeit(s):
    s = int(round(s))
    if s >= 3600:
        return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    return f"{s // 60}:{s % 60:02d}"


def _svg_kurve(lauf, name, reihe, idx):
    """Eine Kurve (kleines Vielfaches) als SVG-String; Punkte fuer das Fadenkreuz stehen in data-pts."""
    W, H, L, R, T, B = 760, 190, 64, 72, 14, 30
    t0 = lauf.start
    boolean = all(isinstance(w, bool) for _, w in reihe)
    if boolean:
        pts = [(t - t0, 1 if w else 0) for t, w in reihe]
        ylo, yhi, yticks = -0.1, 1.1, [0, 1]
    else:
        pts = [(t - t0, w) for t, w in reihe if _ist_zahl(w)]
        if not pts:
            return ""
        ylo, yhi, yticks = _nice_ticks(min(p[1] for p in pts), max(p[1] for p in pts))
    xmax = max(lauf.dauer, pts[-1][0], 1.0)
    xticks, _ = _zeit_ticks(xmax)
    sx = lambda x: L + (W - L - R) * x / xmax
    sy = lambda y: T + (H - T - B) * (1 - (y - ylo) / (yhi - ylo))
    g = []
    for y in yticks:
        lab = ("ja" if y == 1 else "nein") if boolean else _fmt(float(y))
        g.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{sy(y):.1f}" y2="{sy(y):.1f}"/>'
                 f'<text class="tick" x="{L - 8}" y="{sy(y) + 4:.1f}" text-anchor="end">{html.escape(lab)}</text>')
    for x in xticks:
        g.append(f'<text class="tick" x="{sx(x):.1f}" y="{H - 10}" text-anchor="middle">{_fmt_zeit(x)}</text>')
    g.append(f'<line class="axis" x1="{L}" x2="{W - R}" y1="{sy(ylo):.1f}" y2="{sy(ylo):.1f}"/>')
    if boolean:
        # Stufenlinie: Zustand gilt bis zum naechsten Messpunkt
        d = []
        for i, (x, y) in enumerate(pts):
            d.append(f"{'M' if i == 0 else 'L'}{sx(x):.1f},{sy(y):.1f}")
            if i + 1 < len(pts):
                d.append(f"L{sx(pts[i + 1][0]):.1f},{sy(y):.1f}")
        pfad = " ".join(d)
    else:
        pfad = " ".join(f"{'M' if i == 0 else 'L'}{sx(x):.1f},{sy(y):.1f}" for i, (x, y) in enumerate(pts))
    g.append(f'<path class="line" d="{pfad}"/>')
    if len(pts) <= 40:
        g.extend(f'<circle class="dot" cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="4"/>' for x, y in pts)
    letzter = pts[-1]
    lab = ("ja" if letzter[1] else "nein") if boolean else _fmt(float(letzter[1]))
    g.append(f'<text class="label" x="{sx(letzter[0]) + 8:.1f}" y="{sy(letzter[1]) + 4:.1f}">{html.escape(lab)}</text>')
    # Fadenkreuz-Elemente (per JS gesteuert)
    g.append(f'<line class="cross" x1="0" x2="0" y1="{T}" y2="{H - B}" visibility="hidden"/>'
             f'<circle class="crossdot" cx="0" cy="0" r="5" visibility="hidden"/>'
             f'<rect class="hit" x="{L}" y="{T}" width="{W - L - R}" height="{H - T - B}" fill="transparent"/>')
    daten = json.dumps([[round(x, 3), (1 if y else 0) if boolean else y] for x, y in pts])
    einheit = lauf.einheit(name)
    titel = f"{name}" + (f" [{einheit}]" if einheit else "")
    return (f'<figure class="chart" id="c{idx}">'
            f'<figcaption>{html.escape(titel)} <span class="muted">n = {len(reihe)}</span></figcaption>'
            f'<div class="chartwrap"><svg viewBox="0 0 {W} {H}" data-pts=\'{daten}\' data-bool="{int(boolean)}" '
            f'data-unit="{html.escape(einheit)}" data-x0="{L}" data-x1="{W - R}" data-xmax="{xmax:.3f}" '
            f'data-y0="{T}" data-y1="{H - B}" data-ylo="{ylo}" data-yhi="{yhi}">{"".join(g)}</svg>'
            f'<div class="tip" hidden></div></div></figure>')


def _abschnitt(lauf, takt, nr):
    p = lauf.info.get("parameters") or {}
    param_html = ("<dl class='params'>" + "".join(
        f"<dt>{html.escape(k)}</dt><dd>{html.escape(str(v['value']))} {html.escape(v['unit'] or '')}</dd>" for k, v in p.items()
    ) + "</dl>") if p else "<p class='muted'>Parameter nicht aufgezeichnet (Lauf vor Einfuehrung von lauf.json).</p>"
    kopf = (f"<table class='meta'><tr><th>Typ</th><td>{html.escape(lauf.typ)}</td>"
            f"<th>Start</th><td>{_lokal(lauf.start, True)}</td></tr>"
            f"<tr><th>Geraete</th><td>{html.escape(', '.join(lauf.daten))}</td>"
            f"<th>Ende</th><td>{_lokal(lauf.ende, True)}</td></tr>"
            f"<tr><th>Endzustand</th><td>{html.escape(str(lauf.info.get('final_state') or '?'))}</td>"
            f"<th>Dauer</th><td>{_fmt_zeit(lauf.dauer)} min:s ({lauf.dauer:.0f} s)</td></tr></table>")
    if not lauf.reihen:
        return f"<section id='l{nr}'><h2>{html.escape(lauf.id)}</h2>{kopf}{param_html}<p>Keine Messwerte.</p></section>"
    kz = ["<table class='kenn'><thead><tr><th>Observable</th><th>Einheit</th><th>n</th><th>Takt</th><th>min</th><th>max</th><th>Mittel</th><th>erster</th><th>letzter</th></tr></thead><tbody>"]
    for name, reihe in lauf.reihen.items():
        k = _kennzahlen(reihe)
        kz.append(f"<tr><td>{html.escape(name)}</td><td>{html.escape(lauf.einheit(name))}</td><td>{k['n']}</td>"
                  f"<td>{(f'{k[chr(116)+chr(97)+chr(107)+chr(116)]:.2f} s' if k['takt'] else '-')}</td>"
                  f"<td>{_fmt(k['min'])}</td><td>{_fmt(k['max'])}</td><td>{_fmt(k['mittel'])}</td>"
                  f"<td>{_fmt(k['erster'])}</td><td>{_fmt(k['letzter'])}</td></tr>")
    kz.append("</tbody></table>")
    kurven = "".join(_svg_kurve(lauf, name, reihe, f"{nr}_{i}") for i, (name, reihe) in enumerate(lauf.reihen.items()))
    spalten, zeilen = tabelle(lauf, takt)
    tab = ["<table class='werte'><thead><tr><th>Uhrzeit</th><th>t</th>"]
    tab.extend(f"<th>{html.escape(c)}<br><span class='muted'>{html.escape(lauf.einheit(c))}</span></th>" for c in spalten)
    tab.append("</tr></thead><tbody>")
    for t, s, w in zeilen:
        tab.append(f"<tr><td>{_lokal(t)}</td><td>{_fmt_zeit(s)}</td>" + "".join(f"<td>{_fmt(w.get(c))}</td>" for c in spalten) + "</tr>")
    tab.append("</tbody></table>")
    _, alle = tabelle(lauf, 0)
    roh_csv = base64.b64encode(csv_text(lauf, spalten, alle).encode("utf-8")).decode("ascii")
    raster_csv = base64.b64encode(csv_text(lauf, spalten, zeilen).encode("utf-8")).decode("ascii")
    sicher = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in lauf.id)
    takt_txt = f"alle {takt:g} s" if takt > 0 else "jeder Messwert"
    return (f"<section id='l{nr}'><h2>{html.escape(lauf.id)}</h2>{kopf}<h3>Parameter</h3>{param_html}"
            f"<h3>Kennzahlen</h3>{''.join(kz)}<h3>Verlauf</h3><div class='charts'>{kurven}</div>"
            f"<h3>Messwerte ({takt_txt}, {len(zeilen)} Zeilen)</h3>"
            f"<p class='dl'><a download='{sicher}_rohwerte.csv' href='data:text/csv;base64,{roh_csv}'>Alle Rohwerte als CSV ({len(alle)} Zeilen)</a> "
            f"<a download='{sicher}_tabelle.csv' href='data:text/csv;base64,{raster_csv}'>Diese Tabelle als CSV</a></p>"
            f"<div class='scroll'>{''.join(tab)}</div></section>")


_CSS = """
:root{color-scheme:light;--bg:#fcfcfb;--surface:#ffffff;--text:#0b0b0b;--text-2:#52514e;--muted:#7a7974;--border:#e3e2dd;
--grid:#ececea;--axis:#c9c8c2;--series:#2a78d6;--link:#1c5cab;--tip-bg:#0b0b0b;--tip-text:#ffffff}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;--bg:#1a1a19;--surface:#222221;--text:#ffffff;
--text-2:#c3c2b7;--muted:#9a998f;--border:#3a3a37;--grid:#2c2c2a;--axis:#4a4a46;--series:#3987e5;--link:#86b6ef;--tip-bg:#f0efec;--tip-text:#0b0b0b}}
:root[data-theme=dark]{color-scheme:dark;--bg:#1a1a19;--surface:#222221;--text:#ffffff;--text-2:#c3c2b7;--muted:#9a998f;--border:#3a3a37;
--grid:#2c2c2a;--axis:#4a4a46;--series:#3987e5;--link:#86b6ef;--tip-bg:#f0efec;--tip-text:#0b0b0b}
*{box-sizing:border-box}body{margin:0;padding:20px 16px 48px;background:var(--bg);color:var(--text);
font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}main{max-width:1000px;margin:0 auto}
h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.2rem;margin:36px 0 10px;padding-top:16px;border-top:1px solid var(--border)}
h3{font-size:1rem;margin:22px 0 8px;color:var(--text-2)}.muted{color:var(--muted);font-weight:normal}a{color:var(--link)}
table{border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{padding:4px 10px;text-align:right;border-bottom:1px solid var(--border)}
th:first-child,td:first-child{text-align:left}thead th{color:var(--text-2);font-weight:600;position:sticky;top:0;background:var(--bg)}
table.meta th{text-align:left;color:var(--text-2);font-weight:600;padding-right:6px}table.meta td{text-align:left;padding-right:28px}
dl.params{display:grid;grid-template-columns:max-content 1fr;gap:2px 14px;margin:0}dl.params dt{color:var(--text-2)}dl.params dd{margin:0}
.charts{display:grid;gap:14px}figure.chart{margin:0;padding:10px 12px 6px;background:var(--surface);border:1px solid var(--border);border-radius:8px}
figcaption{font-weight:600;margin-bottom:4px}.chartwrap{position:relative}svg{width:100%;height:auto;display:block}
.grid{stroke:var(--grid);stroke-width:1}.axis{stroke:var(--axis);stroke-width:1}.tick,.label{fill:var(--text-2);font-size:12px}
.label{font-weight:600}.line{fill:none;stroke:var(--series);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.dot{fill:var(--series);stroke:var(--surface);stroke-width:2}.cross{stroke:var(--axis);stroke-width:1;stroke-dasharray:3 3}
.crossdot{fill:var(--series);stroke:var(--surface);stroke-width:2}.hit{cursor:crosshair}
.tip{position:absolute;pointer-events:none;background:var(--tip-bg);color:var(--tip-text);padding:4px 8px;border-radius:6px;font-size:12px;white-space:nowrap}
.scroll{overflow:auto;max-height:70vh;border:1px solid var(--border);border-radius:8px}.scroll table{width:100%}
p.dl a{display:inline-block;margin:0 10px 6px 0;padding:6px 12px;border:1px solid var(--border);border-radius:6px;text-decoration:none;background:var(--surface)}
nav ol{columns:2;padding-left:20px}@media print{.scroll{max-height:none;overflow:visible}p.dl,.tip{display:none}}
"""

_JS = """
document.querySelectorAll('figure.chart svg').forEach(function(svg){
  var pts=JSON.parse(svg.dataset.pts), bool=svg.dataset.bool==='1', unit=svg.dataset.unit;
  var x0=+svg.dataset.x0, x1=+svg.dataset.x1, xmax=+svg.dataset.xmax, y0=+svg.dataset.y0, y1=+svg.dataset.y1, ylo=+svg.dataset.ylo, yhi=+svg.dataset.yhi;
  var cross=svg.querySelector('.cross'), dot=svg.querySelector('.crossdot'), hit=svg.querySelector('.hit'), tip=svg.parentNode.querySelector('.tip');
  var vb=svg.viewBox.baseVal;
  function fmtT(s){s=Math.round(s);var h=Math.floor(s/3600),m=Math.floor(s%3600/60),r=s%60;return (h?h+':'+String(m).padStart(2,'0'):m)+':'+String(r).padStart(2,'0');}
  function fmtV(v){return bool?(v?'ja':'nein'):(Math.abs(v)<1e4?+v.toPrecision(4):+v.toPrecision(6));}
  hit.addEventListener('mousemove',function(e){
    var r=svg.getBoundingClientRect(), px=(e.clientX-r.left)*vb.width/r.width, xs=(px-x0)/(x1-x0)*xmax;
    var lo=0,hi=pts.length-1; while(lo<hi){var mid=(lo+hi)>>1; if(pts[mid][0]<xs) lo=mid+1; else hi=mid;}
    if(lo>0 && Math.abs(pts[lo-1][0]-xs)<Math.abs(pts[lo][0]-xs)) lo--;
    var p=pts[lo], sx=x0+(x1-x0)*p[0]/xmax, sy=y0+(y1-y0)*(1-(p[1]-ylo)/(yhi-ylo));
    cross.setAttribute('x1',sx);cross.setAttribute('x2',sx);cross.setAttribute('visibility','visible');
    dot.setAttribute('cx',sx);dot.setAttribute('cy',sy);dot.setAttribute('visibility','visible');
    tip.hidden=false; tip.textContent='t = '+fmtT(p[0])+'   '+fmtV(p[1])+(unit?' '+unit:'');
    var left=sx*r.width/vb.width, top=sy*r.height/vb.height;
    tip.style.left=Math.min(left+12, r.width-tip.offsetWidth-4)+'px'; tip.style.top=Math.max(top-34,0)+'px';
  });
  hit.addEventListener('mouseleave',function(){cross.setAttribute('visibility','hidden');dot.setAttribute('visibility','hidden');tip.hidden=true;});
});
"""


def schreibe_html(laeufe, pfad, takt, titel):
    teile = []
    if len(laeufe) > 1:
        teile.append("<nav><h3>Laeufe</h3><ol>" + "".join(
            f"<li><a href='#l{i}'>{html.escape(l.id)}</a> <span class='muted'>{html.escape(l.typ)}, {_lokal(l.start)}, {_fmt_zeit(l.dauer)}</span></li>"
            for i, l in enumerate(laeufe)) + "</ol></nav>")
    teile.extend(_abschnitt(l, takt, i) for i, l in enumerate(laeufe))
    erzeugt = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    doc = (f"<!doctype html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>{html.escape(titel)}</title><style>{_CSS}</style></head><body><main>"
           f"<h1>{html.escape(titel)}</h1><p class='muted'>LABS-Versuchslog, erzeugt {erzeugt} mit tools/auswertung.py. "
           f"Kurven: Fadenkreuz beim Ueberfahren. Zeitachse = Versuchszeit ab Start (min:s).</p>"
           f"{''.join(teile)}</main><script>{_JS}</script></body></html>")
    os.makedirs(os.path.dirname(os.path.abspath(pfad)), exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"Bericht geschrieben: {pfad} ({os.path.getsize(pfad) / 1024:.0f} kB, {len(laeufe)} Lauf/Laeufe)")


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("experiment", nargs="?", help="Experiment-ID (Verzeichnisname); Standard: neuester Lauf")
    ap.add_argument("--liste", action="store_true", help="alle Laeufe auflisten und beenden")
    ap.add_argument("--tag", help="Datum JJJJ-MM-TT: fuer --liste als Filter, fuer --html ein Tagesbericht mit allen Laeufen")
    ap.add_argument("--html", nargs="?", const=True, metavar="DATEI", help="HTML-Bericht schreiben (Standardpfad im Log-Ordner)")
    ap.add_argument("--takt", type=float, default=10.0, help="Rasterbreite der Tabelle in s (0 = jeder Messwert); Standard 10")
    ap.add_argument("--csv", metavar="DATEI", help="Tabelle als CSV schreiben")
    ap.add_argument("--roh", action="store_true", help="statt Tabelle: Rohwerte je Observable")
    ap.add_argument("--keine-tabelle", action="store_true", help="nur die Uebersicht ausgeben")
    args = ap.parse_args()

    laeufe = alle_laeufe()
    if not laeufe:
        sys.exit(f"Keine values.json unter {LOGS} gefunden.")

    if args.liste:
        for l in laeufe:
            if args.tag and _lokal(l.start, True)[:10] != args.tag:
                continue
            obs = ", ".join(l.reihen) or "(nur Zustaende)"
            print(f"{_lokal(l.start, True)}  {l.dauer:5.0f} s  {l.typ:<20} {l.id:<32} {obs}")
        return

    if args.html and args.tag and not args.experiment:
        auswahl = [l for l in laeufe if _lokal(l.start, True)[:10] == args.tag]
        if not auswahl:
            sys.exit(f"Keine Laeufe am {args.tag}.")
        pfad = args.html if isinstance(args.html, str) else os.path.join(os.path.dirname(auswahl[0].pfad), f"versuchstag_{args.tag}.html")
        schreibe_html(auswahl, pfad, args.takt, f"Versuchstag {args.tag}")
        return

    if args.experiment:
        treffer = [l for l in laeufe if l.id == args.experiment]
        if not treffer:
            sys.exit(f"Lauf '{args.experiment}' nicht gefunden. Vorhandene Laeufe: --liste")
        lauf = treffer[-1]
    else:
        lauf = laeufe[-1]

    if args.html:
        pfad = args.html if isinstance(args.html, str) else os.path.join(lauf.pfad, "bericht.html")
        schreibe_html([lauf], pfad, args.takt, f"Versuchsbericht {lauf.id}")
        return

    uebersicht(lauf)
    if args.roh:
        drucke_roh(lauf)
        return
    spalten, zeilen = tabelle(lauf, args.takt)
    if not args.keine_tabelle and zeilen:
        drucke_tabelle(spalten, zeilen)
    if args.csv and zeilen:
        with open(args.csv, "w", encoding="utf-8", newline="") as f:
            f.write(csv_text(lauf, spalten, zeilen))
        print(f"CSV geschrieben: {args.csv} ({len(zeilen)} Zeilen)")


if __name__ == "__main__":
    main()
