# Anleitung Versuchstag: LABS am Pi starten und die Kolbe-Elektrolyse fahren

Fuer jemanden, der den Versuch allein fahren soll (Stand 13.10.2026). Rechner: Raspberry Pi
"Raspberry-PI-MP-002" im Labor, Benutzer pohlma. Alle Befehle werden in einem Terminal auf dem Pi
eingegeben (schwarzes Terminal-Symbol in der Leiste, oder Strg+Alt+T).

Die Schrittfolge des Versuchs selbst steht in `docs/versuch_08-10-2026_fragen_und_schritte.md`
(Tabelle "Einzelschritte"); hier geht es darum, LABS zum Laufen zu bringen und zu bedienen.

## 1. Geraete einschalten (ZUERST, vor dem Backend)

Einschalten und warten, bis die Displays etwas anzeigen:

- Netzteil (grauer Kasten "DC SOURCE 48V")
- Bronkhorst Gaszaehler (haengt am USB)
- Pumpe Longer WT600-2J
- Liquiline (pH/Leitfaehigkeit/Temperatur)
- microGC (Netzwerkkabel zum Pi muss stecken; nach dem Einschalten braucht er einige Minuten,
  Display zeigt am Ende "ready" oder "standby")

WICHTIG: Ein Geraet, das beim Start des Backends aus ist, wird uebersprungen, und alle Experimente
mit diesem Geraet fehlen bis zum naechsten Backend-Start. Spaeter eingeschaltet = Backend neu starten.

## 2. Backend starten (Terminal 1)

    cd ~/LABS/LABS-Backend
    git pull
    .venv/bin/python main.py

Im Terminal laufen viele Zeilen durch. Richtig ist, wenn fuer ALLE fuenf Geraete eine Zeile
"State of Device changed to: Ready" erscheint (Inficon Micro GC, Bronkhorst, Joy-IT DPM86xx,
Liquiline, Longer WT600) und danach "Experimental Setup ... changed to: Paused".
Kommt fuer ein Geraet stattdessen "Error" oder "CONNECTION LOST": Geraet pruefen (Strom? USB-Kabel?),
dann Backend mit Strg+C beenden und neu starten.

Das Terminal offen lassen. Strg+C beendet das Backend (und schaltet vorher Netzteil und Pumpe ab).

## 3. Frontend starten (Terminal 2, neues Terminalfenster)

    cd ~/LABS/LABS-User-Interface
    git pull
    .venv/bin/flask run --host=0.0.0.0

Richtig ist eine Zeile "Running on http://0.0.0.0:5000". Auch dieses Terminal offen lassen.

## 4. LABS im Browser oeffnen

- Auf dem Pi selbst: Chromium oeffnen, Adresse `http://localhost:5000`
- Vom Laptop (im selben WLAN "ufz-m2m"): `http://141.65.150.197:5000`
  (WLAN-Adresse des Pi; falls sie nicht geht, am Pi im Terminal `hostname -I` eingeben, die erste
  Adresse der Form 141.65.x.x nehmen)

Anmelden mit dem LABS-Konto (Zugangsdaten: _________________________ hier eintragen).

## 5. Einmal pro Tag: Routinen vom Backend holen

Menue **Experiments** -> **List Stations** -> bei der Station auf **Edit Routines** ->
**Download Experiments from Station**. Danach stehen alle Experimente aus der config.yml in der
Tabelle, u.a. kolbe_pumpe_zeit, kolbe_n2_spuelung, kolbe_elektrolyse_gc, kolbe_gas_zaehlen,
kolbe_gc_messung, test_microgc_plan.

Wenn sich ein Experiment geaendert hat (neue Parameter), erscheint das NICHT automatisch:
in der Tabelle die alte Zeile mit **Delete** loeschen und nochmal "Download Experiments from Station".

## 6. Ein Experiment starten

Menue **Experiments** -> Experimental Design -> Stage -> **Add run**: Experimenttyp waehlen,
Werte eintragen, abschicken, dann an die Station senden (Upload/Send). Das Backend startet es, sobald
es frei ist. Mehrere Experimente in der Warteschlange laufen OHNE Pause direkt hintereinander -
also einen Schritt erst dann einreihen, wenn der Aufbau dafuer fertig ist (z.B. nach dem Ansaeuern).

Zahlen mit Punkt eingeben (0.55, nicht 0,55).

### Werte fuer die Kolbe-Elektrolyse (Versuchsplan 26174-26177)

| Schritt | Experiment | Werte |
|---|---|---|
| Befuellen / Dichtheitstest | kolbe_pumpe_zeit | rate 100, minutes nach Bedarf (z.B. 1.5) |
| N2-Spuelung vor der Elektrolyse | kolbe_n2_spuelung | rate 100, minutes 10 |
| Elektrolyse MIT microGC | kolbe_elektrolyse_gc | versuch = Versuchsnummer (z.B. 26176), gc_minutes = **0**, current 0.55, max_voltage 48, minutes 219.28, rate 100 |
| Gas zaehlen nach dem Ansaeuern | kolbe_gas_zaehlen | minutes (z.B. 30; frueher beenden mit Stop) |
| Nachspuelen | kolbe_pumpe_zeit | rate 100, minutes 10 |
| Offline-Gasbeutel messen | test_microgc_plan | versuch z.B. 26176_rep1, gc_minutes 0, minutes 1 (= genau ein Lauf) |

gc_minutes bei kolbe_elektrolyse_gc:
- `0` = Dauermessung: der microGC misst immer wieder, sobald er fertig ist (etwa alle 8 Minuten),
  bis die Elektrolysezeit um ist. Das ist die Standardeinstellung.
- eine Zahl, z.B. `10` = alle 10 Minuten.
- Liste mit Semikolon, z.B. `0;10;20;30` = feste Zeitpunkte.
Die Laeufe heissen am microGC "<versuch>_<Minute> min", Tags Kolbe;MP.

Das Elektrolyse-Experiment endet erst, wenn der letzte GC-Lauf abgeholt ist (bis zu 8 Minuten nach
der Elektrolysezeit). Netzteil und Pumpe schalten schon nach `minutes` ab.

## 7. Zuschauen: Monitoring

Menue **Monitoring** -> Station anklicken. Oben die Tabelle "Current values" mit den aktuellen
Zahlen und der Versuchszeit ("running for ... ends ~..."), darunter die Kurven. Umschalter ueber den
Kurven: letzte 10 min / letzte Stunde / ganzer Lauf.

Was normal ist (Werte vom 08.10./13.10.):
- psu.current 0.55 A, psu.voltage 4-6 V (steigt langsam)
- mfc.flow etwa 1-3 mL/min, mfc.counter steigt stetig (am Ende ~220 mLn). Bleibt der Fluss bei 0
  und der Zaehler bei 0: Gasweg pruefen (Leck, Hahn), LABS kann daran nichts aendern.
- liquiline: ph_ch1_value pH 6-9, conductivity_value ~50 mS/cm, temperature_value steigt auf ~25 degC.
  Status "Bad" und Wert 0.0 = Sensor nicht im Medium / Stecker. Zappelnde Leitfaehigkeit = Gasblasen.
- microgc: gc_schedule "running", gc_runs_done zaehlt hoch, nach jedem Lauf neue Werte gc_H2, gc_CO2,
  gc_n_Hexane usw. in % (ein Punkt pro Lauf). Luft = O2 21 %, N2 78 %.

## 8. Stoppen (normal oder Notfall)

- Im Frontend "Stop Experiments" (oder im Terminal 1 Strg+C): Netzteil AUS, Pumpe AUS, microGC-Plan
  abgebrochen (ein laufender GC-Lauf laeuft am Geraet zu Ende, das ist harmlos).
- Notfall ohne Rechner: Netzschalter am grauen Kasten (Netzteil).
- Nach einem Stop steht das Backend auf "Stopped": fuer den naechsten Schritt Backend mit Strg+C
  beenden und neu starten (Schritt 2).

## 9. Nach dem Versuch: Auswertung

Alle Messwerte liegen unter `~/LABS/LABS-Backend/logs/<Jahr>/<Monat>/<Tag>/<Experimentname>/`
(values.json, lauf.json, log.txt, bericht.html). Die microGC-Laufdaten als JSON+CSV unter
`logs/<Jahr>/<Monat>/<Tag>/microgc/`.

Bericht erzeugen (Terminal, Backend darf dabei laufen):

    cd ~/LABS/LABS-Backend
    .venv/bin/python tools/auswertung.py --liste                      # alle Laeufe des Tages
    .venv/bin/python tools/auswertung.py --html --tag 2026-10-14       # Tagesbericht (Datum anpassen)
    .venv/bin/python tools/auswertung.py "<Experimentname>" --csv werte.csv --takt 600   # Tabelle alle 10 min

Der Bericht ist eine HTML-Datei (im Browser oeffnen, per Mail verschicken): Kurven, Kennzahlen,
10-Minuten-Tabelle, GC-Tabelle, Knopf fuer alle Rohwerte als CSV.

## 10. Feierabend

1. Im Frontend sicherstellen, dass kein Experiment mehr laeuft.
2. Terminal 1: Strg+C (Backend aus, schaltet Netzteil/Pumpe ab). Terminal 2: Strg+C (Frontend aus).
3. Geraete ausschalten. microGC laut Laborregel (BakeOut/Standby).

## Wenn etwas nicht geht

| Symptom | Was tun |
|---|---|
| Browser: Seite nicht erreichbar | Frontend laeuft nicht (Schritt 3) oder falsche Adresse (Schritt 4) |
| Frontend: Experiment laesst sich nicht senden / Station nicht erreichbar | Backend laeuft nicht (Schritt 2) |
| Ein Experiment fehlt in der Liste | Routinen neu holen (Schritt 5); fehlt es weiter: ein Geraet war beim Backend-Start aus -> Backend neu starten |
| Geraet "Error" im Terminal 1 | Geraet aus/Kabel ab: pruefen, Backend neu starten |
| Monitoring zeigt nichts | Es laeuft kein Experiment; Monitoring zeigt nur das laufende |
| microGC: gc-Werte kommen nicht | Erster Wert erst nach ~8 min (Laufdauer). Im Terminal 1 nach "GC-Lauf" suchen |
| Netzteil bleibt an | Strg+C im Terminal 1, dann Netzschalter am grauen Kasten |
