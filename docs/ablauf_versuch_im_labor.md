# Versuch im Labor durchfuehren - Ablauf fuer den Anwender (Stand 13.10.2026)

Kurzanleitung fuer die Kolbe-Elektrolyse mit Live-Monitoring. Keine Programmierkenntnisse noetig,
nur zwei Terminal-Befehle am Pi und danach alles im Browser.

Begriffe: **Backend** = das Programm am Pi, das die Geraete steuert. **Frontend** = die Webseite
(Nutzeroberflaeche) im Browser. **Routine** = ein fertiges Rezept aus config.yml (z.B.
`kolbe_elektrolyse_gc`). **Design / Stage / Run** = so heisst im Frontend die Planung: ein Design ist
der Versuch, eine Stage ist ein Schritt (eine Routine), ein Run ist ein Parametersatz dieses Schritts.

## 1. Geraete einschalten (VOR dem Backend!)

Alle Geraete einschalten und warten, bis sie betriebsbereit sind:

- Netzteil (grauer Kasten "DC SOURCE 48V"), Ausgang bleibt aus
- Massendurchflussregler Bronkhorst (MFC) und N2-Versorgung
- Schlauchpumpe Longer WT600
- Liquiline (pH / Leitfaehigkeit / Temperatur) - Display muss fuer CH1 einen pH-Wert zeigen,
  nicht "X --- ---"
- microGC Fusion (am LAN), Status am Geraet "ready" (kein BakeOut, keine laufende Messung)

Regel: Ein Geraet, das beim Start des Backends aus ist, wird uebersprungen. Alle Routinen, die dieses
Geraet brauchen, fehlen dann bis zum naechsten Backend-Start. Spaeter eingeschaltet = Backend neu starten.

## 2. Pi: Backend und Frontend starten

Am Pi zwei Terminalfenster oeffnen (oder zwei SSH-Verbindungen).

Fenster 1, Backend:

    cd ~/LABS/LABS-Backend
    .venv/bin/python main.py

Im Log muss fuer JEDES Geraet eine Zeile `State of Device changed to: Ready` kommen und am Ende
`changed to: Paused`. Steht bei einem Geraet `Error` oder fehlt es: Geraet pruefen, Strg+C, neu starten.

Fenster 2, Frontend:

    cd ~/LABS/LABS-User-Interface
    .venv/bin/flask run --host=0.0.0.0

`--host=0.0.0.0` ist noetig, damit andere Rechner im Labornetz die Seite sehen. Beide Fenster
offen lassen, solange der Versuch laeuft. Beenden jeweils mit Strg+C (erst nach dem Versuch!).

## 3. Im Browser anmelden

Beliebiger Rechner im selben Netz: `http://<IP-des-Pi>:5000` (am Pi selbst: `http://localhost:5000`).
Oben rechts **Login**. Wer noch kein Konto hat: **Register**, dann dem Admin Bescheid geben.
Designs sind pro Benutzer: jeder sieht nur seine eigenen und die, die ihm geteilt wurden.

## 4. Routinen pruefen (einmalig, nur Admin)

Administration -> Routines -> **Download Experiments from Station**. Danach muessen in der Liste u.a.
stehen: `kolbe_pumpe_zeit`, `kolbe_gas_zaehlen`, `kolbe_elektrolyse_gc`, `kolbe_gc_messung`.
Fehlt eine Routine, war beim Backend-Start ein Geraet aus (siehe 1).

## 5. Versuch planen (Design anlegen)

1. **Experiments** -> **Add a new experimental Design**: Name = Versuchsnummer (z.B. `26175`),
   Station auswaehlen -> Create.
2. Im Design **Create Stage**: Name des Schritts, Routine auswaehlen. Fuer jeden Schritt des Versuchs
   eine Stage, in der Reihenfolge, in der sie laufen sollen (Vorschlag unten).
3. Stage oeffnen (**Edit**): die Parameter der Routine eintragen und **Add** druecken -> ein Run.
   Dezimalzahlen mit Punkt (`0.5`), Kommas werden automatisch zu Punkten.
4. Zurueck im Design: die Stages anhaken und **Send** -> die Runs stehen jetzt in der Warteschlange
   des Backends, in der angehakten Reihenfolge.

Schrittfolge Kolbe-Elektrolyse (Nummern wie im Laborplan):

| Schritt | Routine | Parameter | Hinweis |
|---|---|---|---|
| 3 Befuellen / Dichtheit | `kolbe_pumpe_zeit` | rate (mL/min), minutes | Gaszaehler liest mit |
| 4 N2-Spuelung | `kolbe_pumpe_zeit` oder `kolbe_gas_zaehlen` | rate, minutes | Zaehler auf 0 |
| 5 Elektrolyse + GC | `kolbe_elektrolyse_gc` | versuch, gc_minutes, current (A), max_voltage (V), minutes, rate | siehe unten |
| 8 Gas zaehlen | `kolbe_gas_zaehlen` | minutes | bis ~150 mLn, frueher Ende mit Stop |
| 6/11 GC-Einzelmessung | `kolbe_gc_messung` | method, name, tags | Gasbeutel; nur wenn nichts anderes laeuft |
| 10 Nachspuelen | `kolbe_pumpe_zeit` | rate, minutes (10) | |

Parameter von `kolbe_elektrolyse_gc`:

- `versuch`: Versuchsnummer ohne Leerzeichen, z.B. `26175`. Die GC-Laeufe heissen dann `26175_10 min`.
- `gc_minutes`, drei Moeglichkeiten (gilt ab Backend-Stand 8fb6847, 13.10. mittags):
  - `0` = **Dauermessung**: der naechste GC-Lauf startet, sobald das Geraet fertig ist (etwa alle
    8 min), bis die Elektrolysezeit `minutes` um ist. Laufname = verstrichene Minute (`26175_15.3 min`).
  - eine Zahl, z.B. `10` = alle 10 Minuten, von 0 bis `minutes`.
  - Liste **mit Semikolon**, Dezimalpunkt = feste Zeitpunkte, z.B. der Versuchsplan
    `0;10;20;30;40;50;60;80;100;120;140;160;180;200;219`
  Achtung: eine einzelne Zahl ist ein ABSTAND, kein Zeitpunkt. (`7.5` = alle 7,5 min.)
- `current`, `max_voltage`, `minutes`, `rate`: wie bisher aus dem Laborbuch.

Das Experiment endet erst, wenn der LETZTE GC-Lauf abgeholt ist (letzter Zeitpunkt + ca. 8 min).
Netzteil und Pumpe schalten unabhaengig davon nach `minutes` ab.

## 6. Starten und beobachten (Monitoring)

1. **Monitoring** -> Station -> **See Details**. Oben steht die Warteschlange (Name, Routine, Parameter).
2. **Start Experiments** druecken. Das Backend steht nach dem Start immer auf "Paused" und wartet
   auf diesen Knopf. Danach laufen alle gesendeten Runs nacheinander ab, ohne weiteres Zutun.
3. Waehrend ein Run laeuft:
   - "Current experiment" mit Laufzeit und **voraussichtlichem Ende** (`ends ~HH:MM`). Bei
     `kolbe_elektrolyse_gc` kennt die Anzeige nur `minutes`, nicht den GC-Nachlauf.
   - Tabelle **Current values**: alle Messwerte mit Alter der letzten Aktualisierung.
   - Kurven darunter, X-Achse = Uhrzeit. Knoepfe **last 10 min / last hour / whole run** fuer den
     Zeitausschnitt.
   - GC: `gc_runs_done` zaehlt die fertigen Laeufe, `gc_run_name` zeigt den letzten, die
     Konzentrationen (gc_H2, gc_CO2, ...) springen nach jedem Lauf auf den neuen Wert.
4. Seite neu laden ist jederzeit erlaubt (F5), die Kurven bauen sich wieder auf.

Was NICHT geht: ein zweites Experiment, waehrend eines laeuft (z.B. eine GC-Einzelmessung waehrend
der Elektrolyse). Alles wartet in der Reihenfolge der Warteschlange.

## 7. Abbrechen / Notfall

- **Stop Experiments** im Frontend: beendet den laufenden Run, Netzteil-Ausgang aus, Pumpe stopp,
  MFC-Ventil auf, GC-Plan abgebrochen (ein am Geraet laufender GC-Lauf laeuft zu Ende). Die bis dahin
  gemessenen Werte werden gespeichert.
- Echter Notfall: Netzschalter am grauen Kasten (Netzteil).
- Nach einem **Stop** oder einem Fehler (`Failed` in der Uebersicht) steht das Backend still. Fuer
  einen weiteren Versuch: Fenster 1 mit Strg+C beenden und das Backend neu starten (Abschnitt 2),
  dann die Warteschlange neu senden und **Start Experiments**.
- Zeigt ein Geraet im Backend-Log `Error`, schaltet das Backend von selbst alles ab und wiederholt
  den Abschaltbefehl, bis das Geraet bestaetigt. Trotzdem am Geraet pruefen: Netzteil-Ausgang AUS?

## 8. Nach dem Versuch

- Daten liegen am Pi unter `~/LABS/LABS-Backend/logs/<Jahr>/<Monat>/<Tag>/<Run-ID>/`:
  `values.json` (alle Messwerte), `lauf.json` (Parameter, Start/Ende, Endzustand),
  `bericht.html` (automatischer Bericht mit Kurven), `log.txt`.
- GC-Laufdaten zusaetzlich unter `logs/<Jahr>/<Monat>/<Tag>/microgc/<Name>.csv`.
- Tagesbericht: `logs/<Jahr>/<Monat>/<Tag>/bericht.html`.
- Backend (Fenster 1) und Frontend (Fenster 2) mit Strg+C beenden, Geraete ausschalten.

## Haeufige Stolpersteine

| Symptom | Ursache / Abhilfe |
|---|---|
| Routine fehlt in der Liste | Geraet war beim Backend-Start aus -> Geraet an, Backend neu starten, Routinen neu laden |
| "Status: Paused", nichts passiert | **Start Experiments** druecken |
| "Status: Stopped" / "Failed", Start geht nicht | Backend neu starten (Abschnitt 7) |
| Kurven leer, Tabelle leer | Kein Experiment laeuft (Warteschlange leer oder noch nicht gestartet) |
| Kollege sieht die Seite nicht | Frontend ohne `--host=0.0.0.0` gestartet, oder falsche IP; Login noetig |
| Liquiline-Werte 0.0, Status "Bad" | Sensor liefert nichts (Display "X --- ---"): Memosens-Stecker pruefen |
| GC-Lauf "verspaetet" im Log | Normal bei dicht gesetzten Zeitpunkten; der Lauf startet, sobald das Geraet frei ist |
