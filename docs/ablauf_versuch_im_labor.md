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

Am Pi (Raspberry-PI-MP-002, Benutzer pohlma, Bildschirm/Tastatur im Labor) zwei Terminalfenster
oeffnen: Terminal-Symbol in der Leiste oben, oder Strg+Alt+T; fuer das zweite Fenster nochmal.
(Alternativ zwei SSH-Verbindungen vom Laptop: `ssh pohlma@141.65.150.197`.)

Fenster 1, Backend:

    cd ~/LABS/LABS-Backend
    git pull
    .venv/bin/python main.py

(`git pull` holt den neuesten Stand von GitHub; ohne Internet einfach weglassen.)

Im Log muss fuer JEDES Geraet eine Zeile `State of Device changed to: Ready` kommen und am Ende
`changed to: Paused`. Steht bei einem Geraet `Error` oder fehlt es: Geraet pruefen, Strg+C, neu starten.

Fenster 2, Frontend:

    cd ~/LABS/LABS-User-Interface
    git pull
    .venv/bin/flask run --host=0.0.0.0

Richtig ist die Zeile `Running on http://0.0.0.0:5000`.

`--host=0.0.0.0` ist noetig, damit andere Rechner im Labornetz die Seite sehen. Beide Fenster
offen lassen, solange der Versuch laeuft. Beenden jeweils mit Strg+C (erst nach dem Versuch!).

## 3. Im Browser anmelden

Am Pi selbst: Chromium oeffnen (Weltkugel-Symbol in der Leiste), Adresse `http://localhost:5000`.
Vom Laptop im WLAN "ufz-m2m": `http://141.65.150.197:5000` (WLAN-Adresse des Pi, Stand 13.10.2026;
sie kommt per DHCP und kann sich irgendwann aendern - dann am Pi im Terminal `hostname -I` eingeben,
die Adresse der Form 141.65.x.x nehmen. Die zweite Adresse 169.254.x.x ist das Kabel zum microGC.)

Zugangsdaten fuer LABS: ______________________________ (hier eintragen oder beim Admin erfragen).
Oben rechts **Login**. Wer noch kein Konto hat: **Register**, dann dem Admin Bescheid geben.
Designs sind pro Benutzer: jeder sieht nur seine eigenen und die, die ihm geteilt wurden.

## 4. Routinen pruefen (einmalig, nur Admin)

Administration -> Routines -> **Download Experiments from Station**. Danach muessen in der Liste u.a.
stehen: `kolbe_pumpe_zeit`, `kolbe_gas_zaehlen`, `kolbe_gas_zaehlen_pumpe`, `kolbe_elektrolyse_gc`, `kolbe_gc_messung`.
Fehlt eine Routine, war beim Backend-Start ein Geraet aus (siehe 1).

## 5. Versuch planen (Design anlegen)

1. **Experiments** -> **Add a new experimental Design**: Name = Versuchsnummer (z.B. `26175`),
   Station auswaehlen -> Create.
2. Im Design **Create Stage**: Name des Schritts (freier Text, z.B. `Spuelung_26175` - erscheint
   in der Warteschlange und im Log-Ordner) und Routine auswaehlen. Fuer jeden Schritt des Versuchs
   eine Stage. Eine Reihenfolge wird NICHT eingetragen: die Stages stehen im Design in der
   Reihenfolge, in der sie angelegt wurden (aelteste oben), und genau so werden sie gesendet.
   Also in der Ablaufreihenfolge anlegen (Vorschlag unten); umsortieren geht nur durch Loeschen
   und Neuanlegen.
3. Stage oeffnen (**Edit**): die Parameter der Routine eintragen und **Add** druecken -> ein Run.
   Dezimalzahlen mit Punkt (`0.5`), Kommas werden automatisch zu Punkten.
4. Zurueck im Design: die Stages anhaken und **Send** -> die Runs stehen jetzt in der Warteschlange
   des Backends, in der Listenreihenfolge. Entweder alle Schritte auf einmal senden, oder - wenn
   zwischen den Schritten am Aufbau etwas zu tun ist - immer nur den naechsten anhaken und senden.

Schrittfolge Kolbe-Elektrolyse (Nummern wie im Laborplan):

| Schritt | Routine | Parameter | Hinweis |
|---|---|---|---|
| 3 Befuellen / Dichtheit | `kolbe_pumpe_zeit` | rate (mL/min), minutes | Gaszaehler liest mit |
| 4 N2-Spuelung | `kolbe_pumpe_zeit` oder `kolbe_gas_zaehlen` | rate, minutes | Zaehler auf 0 |
| 5 Elektrolyse + GC | `kolbe_elektrolyse_gc` | versuch, gc_minutes, current (A), max_voltage (V), minutes, rate | siehe unten |
| 8 Gas zaehlen | `kolbe_gas_zaehlen_pumpe` (Pumpe waelzt um) oder `kolbe_gas_zaehlen` (ohne Pumpe) | minutes, rate | bis ~150 mLn, frueher Ende mit Stop; `_pumpe` ab Backend-Stand 13.10. abends |
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
   auf diesen Knopf. **Schrittmodus (seit 16.10.2026 eingeschaltet, `step_mode: true` in config.yml):**
   jeder Klick startet genau EINEN Schritt der Warteschlange. Ist er fertig, haelt das Backend an
   (Netzteil aus, Pumpe stopp, MFC-Ventil auf) und wartet auf den naechsten Klick. Senden aus dem
   Frontend startet nie etwas, nur dieser Knopf. Die Statuszeile ueber den Knoepfen zeigt, was dran ist:
   - gruen, Start-Knopf pulsiert: "Paused - step N of M done, next: <Name> - press Start Experiments"
     (oder vor dem ersten Schritt "Paused - not started, N step(s) queued") -> **Start Experiments**;
   - blau: "Running - step N of M: <Name>" -> laufen lassen;
   - grau: "Paused - all N steps done" -> naechsten Schritt senden, dann Start;
   - rot: Stopped/Failed/offline -> Abschnitt 7.
3. Waehrend ein Run laeuft:
   - "Current experiment" mit Laufzeit und **voraussichtlichem Ende** (`ends ~HH:MM`). Bei
     `kolbe_elektrolyse_gc` kennt die Anzeige nur `minutes`, nicht den GC-Nachlauf: nach dem Ende der
     Elektrolyse (Netzteil aus) misst der GC noch EINMAL (Abschlussmessung `<versuch>_Ende <t> min`,
     seit 16.10.2026), vorher wartet er ggf. einen noch laufenden Lauf ab. Das Experiment ist also
     erst ~8 bis ~16 min nach `ends` fertig - das ist gewollt, nicht haengen geblieben. Details:
     docs/microgc_messplan_im_experiment_13-10-2026.md, Bedienung Punkt 3.
   - Tabelle **Current values**: alle Messwerte mit Alter der letzten Aktualisierung.
   - Kurven darunter, X-Achse = Uhrzeit. Knoepfe **last 10 min / last hour / whole run** fuer den
     Zeitausschnitt.
   - GC: `gc_runs_done` zaehlt die fertigen Laeufe, `gc_run_name` zeigt den letzten, die
     Konzentrationen (gc_H2, gc_CO2, ...) springen nach jedem Lauf auf den neuen Wert.
4. Seite neu laden ist jederzeit erlaubt (F5), die Kurven bauen sich wieder auf.

Schrittmodus ausschalten (`step_mode: false`, Backend neu starten): dann laufen alle gesendeten Schritte
in einem Rutsch durch, und ein Schritt, der bei leerer Schlange gesendet wird, startet SOFORT beim Senden.
Im Labor nicht empfohlen.

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

- Bericht und Tabellen im Terminal erzeugen (Backend darf dabei laufen):

      cd ~/LABS/LABS-Backend
      .venv/bin/python tools/auswertung.py --liste                            # alle Laeufe mit Datum
      .venv/bin/python tools/auswertung.py --html --tag 2026-10-14             # Tagesbericht (Datum anpassen)
      .venv/bin/python tools/auswertung.py "<Run-ID>" --csv werte.csv --takt 600   # Tabelle alle 10 min, Excel

  Die Run-ID ist der Ordnername unter logs (steht in `--liste`). Der HTML-Bericht ist eine einzelne
  Datei: Kurven, Kennzahlen, 10-Minuten-Tabelle, GC-Tabelle, Knopf fuer alle Rohwerte als CSV.
  Bei langen Laeufen (ueber 2 MB Rohwerte) liegt die Rohwerte-CSV als `<Run-ID>_rohwerte.csv` NEBEN
  dem Bericht - beim Kopieren/Verschicken beide Dateien mitnehmen.
- Daten liegen am Pi unter `~/LABS/LABS-Backend/logs/<Jahr>/<Monat>/<Tag>/<Run-ID>/`:
  `values.json` (alle Messwerte), `lauf.json` (Parameter, Start/Ende, Endzustand),
  `bericht.html` (automatischer Bericht mit Kurven), `log.txt`.
- GC-Laufdaten zusaetzlich unter `logs/<Jahr>/<Monat>/<Tag>/microgc/<Name>.csv`.
- Tagesbericht (automatisch nach jedem Lauf): `logs/<Jahr>/<Monat>/<Tag>/versuchstag_<Datum>.html`.
- Backend (Fenster 1) und Frontend (Fenster 2) mit Strg+C beenden, Geraete ausschalten.

## Haeufige Stolpersteine

- **Lauf bleibt nach seiner Zeit auf "Running", obwohl Pumpe/Netzteil schon aus sind** (13.10. nach
  "Stop Experiments" gesehen): einmal Stop Experiments druecken, Messwerte sind gespeichert, dann Start
  fuer den naechsten Schritt. Mit dem Backend-Stand ab 13.10. abends behoben.

| Symptom | Ursache / Abhilfe |
|---|---|
| Routine fehlt in der Liste | Geraet war beim Backend-Start aus -> Geraet an, Backend neu starten, Routinen neu laden |
| "Status: Paused", nichts passiert | **Start Experiments** druecken |
| "Status: Stopped" / "Failed", Start geht nicht | Backend neu starten (Abschnitt 7) |
| Kurven leer, Tabelle leer | Kein Experiment laeuft (Warteschlange leer oder noch nicht gestartet) |
| Kollege sieht die Seite nicht | Frontend ohne `--host=0.0.0.0` gestartet, oder falsche IP; Login noetig |
| Liquiline-Werte 0.0, Status "Bad" | Sensor liefert nichts (Display "X --- ---"): Memosens-Stecker pruefen |
| GC-Lauf "verspaetet" im Log | Normal bei dicht gesetzten Zeitpunkten; der Lauf startet, sobald das Geraet frei ist |
| Browser: "Seite nicht erreichbar" | Frontend laeuft nicht (Fenster 2, Abschnitt 2) oder falsche Adresse (Abschnitt 3) |
| Frontend: Station antwortet nicht / Senden schlaegt fehl | Backend laeuft nicht (Fenster 1) |
| gc-Werte kommen nicht | Der erste Wert kommt erst nach einem ganzen GC-Lauf (~8 min). Im Fenster 1 nach "GC-Lauf" suchen |
| mfc.flow und mfc.counter bleiben bei 0, obwohl Strom fliesst | Gas kommt nicht am Zaehler an: Leck oder Hahn zwischen Zelle und MFC pruefen; LABS misst richtig (13.10. so gesehen) |
| Leitfaehigkeit zappelt, kurz 0 / "Uncertain" | Gasblasen an der Leitfaehigkeitszelle oder Sensor kurz ohne Medium; pH-Einbruch fuer Sekunden ebenso (13.10.) |
| Netzteil bleibt an | Strg+C in Fenster 1, dann Netzschalter am grauen Kasten |

Normale Werte waehrend der Elektrolyse (08.10./13.10.): psu.current 0.55 A, psu.voltage 4-6 V,
mfc.flow 1-3 mL/min und mfc.counter stetig steigend (Ende ~220 mLn), ph_ch1_value 6-9,
conductivity_value ~50 mS/cm, temperature_value steigend auf ~25 degC; Luft am GC = O2 21 %, N2 78 %.

## Drei Zellen parallel (ab 26.10.2026)

Fuer den Lauf mit drei Zellen gibt es eigene Routinen mit Endung `_3x`: `kolbe_pumpe_zeit_3x`
(Dichtheitstest), `kolbe_n2_spuelung_3x`, `kolbe_elektrolyse_3x` (Strom je Zelle: current_z1/z2/z3,
GC misst Z1, Z2, Z3 im Kreis und am Ende je Zelle einmal), `kolbe_gas_zaehlen_pumpe_3x`. Einmalig im
Frontend: Administration -> Routines -> "Download Experiments from Station", dann die Routinen anlegen.
Vor dem Start muessen alle drei Netzteile und alle drei Bronkhorst an sein (Steckplaetze nicht
umstecken!). Im Monitoring stehen die Zellen in der Tabelle "Cells" nebeneinander (Spalten Z1/Z2/Z3),
die Kurven zeigen je Observable drei Linien (rot Z1, blau Z2, gruen Z3).
Details, Geraetezuordnung und offene Punkte (Ventile!): docs/gc_rundlauf_3_zellen_26-10-2026.md
