#!/usr/bin/env python3
"""Statusfenster "LABS Geraete" (27.10.2026): zeigt nach dem Start fuer jedes Geraet aus config.yml einen
gruenen Haken (verbunden, benutzbar) oder ein rotes Kreuz (ausgeschaltet / nicht verbunden / Fehler).
Deaktivierte Geraete (enabled: false) erscheinen grau. Wird von tools/labs_start.sh geoeffnet, kann aber
jederzeit von Hand gestartet werden:
    .venv/bin/python tools/geraete_fenster.py            (Backend muss laufen, Port 11123)
Liest nur /api/device_states - aendert nichts am Backend. "Neu pruefen" fragt den Zustand erneut ab
(z.B. nachdem ein Netzteil eingeschaltet wurde; ein nicht verbundenes Geraet wird erst nach einem
Neustart des Backends wieder verbunden, siehe Hinweis im Fenster)."""
import json
import sys
import tkinter as tk
import tkinter.font as tkfont
import urllib.error
import urllib.request

import os
URL = os.environ.get("LABS_DEVICE_STATES_URL", "http://127.0.0.1:11123/api/device_states")

# Klartext je Geraetename (config.yml). Unbekannte Namen werden mit Treibernamen angezeigt.
BESCHREIBUNG = {
    "psu1": "Netzteil Zelle 1 (Joy-IT, grauer Kasten, Hub 2.4.2)",
    "psu2": "Netzteil Zelle 2 (Joy-IT, grauer Kasten, Hub 2.1)",
    "psu3": "Netzteil Zelle 3 (Joy-IT, grauer Kasten, Hub 2.2.1)",
    "mfc1": "Massenflussregler Zelle 1 (Bronkhorst 50 ml/min)",
    "mfc2": "Massenflussregler Zelle 2 (Bronkhorst 50 ml/min)",
    "mfc3": "Massenflussregler Zelle 3 (Bronkhorst 20 ml/min)",
    "dosing_pump": "Schlauchpumpe (Longer WT600-2J)",
    "liquiline": "pH-Messung (Endress+Hauser Liquiline)",
    "microgc": "Gaschromatograph (Inficon Micro GC Fusion)",
    "ventil_z1": "GC-Ventil Zelle 1 (Relais)",
    "ventil_z2": "GC-Ventil Zelle 2 (Relais)",
    "ventil_z3": "GC-Ventil Zelle 3 (Relais)",
}
GRUEN, ROT, GRAU = "#1a8f2e", "#c62828", "#8a8a8a"


def lade_zustaende():
    """Liste von /api/device_states oder None, wenn das Backend nicht antwortet."""
    try:
        with urllib.request.urlopen(URL, timeout=3) as antwort:
            return json.loads(antwort.read().decode())
    except (urllib.error.URLError, OSError, ValueError):
        return None


class Fenster(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LABS Geraete")
        self.configure(bg="white", padx=18, pady=14)
        self.resizable(False, False)
        self.gross = tkfont.Font(family="DejaVu Sans", size=14, weight="bold")
        self.normal = tkfont.Font(family="DejaVu Sans", size=11)
        self.klein = tkfont.Font(family="DejaVu Sans", size=9)
        self.symbol = tkfont.Font(family="DejaVu Sans", size=22, weight="bold")
        self.kopf = tk.Label(self, font=self.gross, bg="white", anchor="w", justify="left")
        self.kopf.pack(fill="x", pady=(0, 10))
        self.liste = tk.Frame(self, bg="white")
        self.liste.pack(fill="x")
        self.hinweis = tk.Label(self, font=self.klein, bg="white", fg="#444", justify="left", anchor="w",
                                wraplength=560)
        self.hinweis.pack(fill="x", pady=(12, 8))
        knoepfe = tk.Frame(self, bg="white")
        knoepfe.pack(fill="x")
        tk.Button(knoepfe, text="Neu pruefen", font=self.normal, command=self.aktualisieren, width=14).pack(side="left")
        tk.Button(knoepfe, text="Schliessen", font=self.normal, command=self.destroy, width=14).pack(side="right")
        self.aktualisieren()
        self.lift()
        self.attributes("-topmost", True)          # wie ein Warnfenster: oben auf, ...
        self.after(1500, lambda: self.attributes("-topmost", False))   # ... aber nicht dauerhaft im Weg

    def aktualisieren(self):
        for kind in self.liste.winfo_children():
            kind.destroy()
        zustaende = lade_zustaende()
        if zustaende is None:
            self.kopf.config(text="⚠  Backend antwortet nicht (Port 11123)", fg=ROT)
            self.hinweis.config(text="Ist LABS gestartet? Log: LABS-Backend/logs/backend_stdout.log")
            return
        aus = [z for z in zustaende if not z["ok"] and z["state"] != "deaktiviert"]
        an = [z for z in zustaende if z["ok"]]
        if aus:
            self.kopf.config(text=f"⚠  {len(aus)} Geraet(e) AUS oder nicht erreichbar, {len(an)} an", fg=ROT)
        else:
            self.kopf.config(text=f"✔  Alle {len(an)} Geraete an und verbunden", fg=GRUEN)
        for zeile, z in enumerate(zustaende):
            if z["ok"]:
                zeichen, farbe, text = "✔", GRUEN, "an"
            elif z["state"] == "deaktiviert":
                zeichen, farbe, text = "–", GRAU, "deaktiviert (config.yml)"
            else:
                zeichen, farbe, text = "✘", ROT, z["state"]
            name = f'{z["name"]}  –  {BESCHREIBUNG.get(z["name"], z["driver"])}'
            tk.Label(self.liste, text=zeichen, font=self.symbol, fg=farbe, bg="white", width=2)\
                .grid(row=zeile, column=0, sticky="w")
            tk.Label(self.liste, text=name, font=self.normal, fg="black" if z["ok"] else farbe, bg="white",
                     anchor="w").grid(row=zeile, column=1, sticky="w", padx=(4, 16))
            tk.Label(self.liste, text=text, font=self.normal, fg=farbe, bg="white", anchor="w")\
                .grid(row=zeile, column=2, sticky="w")
        if aus:
            self.hinweis.config(
                text="Rotes Kreuz: Geraet einschalten bzw. Kabel pruefen. Ein Netzteil, dessen Wandler am Pi "
                     "auftaucht, aber nicht antwortet, ist AUSGESCHALTET. Danach LABS beenden und neu starten, "
                     "damit das Backend die Geraete neu verbindet. Experimente mit diesen Geraeten wurden "
                     "uebersprungen.")
        else:
            self.hinweis.config(text="Alle Experimente aus config.yml sind verfuegbar.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--text":     # ohne Grafik, z.B. per SSH
        for z in lade_zustaende() or []:
            print(("OK   " if z["ok"] else "AUS  "), z["name"], z["state"], z["reason"])
        sys.exit(0)
    Fenster().mainloop()
