# Versuchstag 13.10.2026 - Notizen waehrend des Laufs (Versuch 26175)

## Vormittag (vor dem Versuch)
- microGC-Messplan im Experiment gebaut und am Geraet verifiziert (docs/microgc_messplan_im_experiment_13-10-2026.md).
- Liquiline CH2 = Leitfaehigkeit (conductivity, mS/cm). Sensoren waren bis zum Versuchsstart nicht im Medium (Bad/0.0).
- Probelauf kolbe_elektrolyse_gc (0.1 A, 2 V, 1 min, GC bei 0 min): Finished, Netzteil nach 60 s aus.
- tools/auswertung.py laeuft mit dem neuen Experiment unveraendert (gc_*-Spalten, conductivity_value).

## Versuch 26175 (Start Elektrolyse 10:57:45)
Reihenfolge: Pumpe_26175 (kolbe_pumpe_zeit 100 mL/min, 1.5 min) -> Spuelung_26175 (kolbe_n2_spuelung 10 min)
-> Elektrolyse_26175 (kolbe_elektrolyse_gc, 0.55 A, 48 V, 219.28 min, 100 mL/min).

### NACHBESSERN: gc_minutes kam als 7.5 an statt als Liste
- Im Experiment steht `gc_minutes = 7.5` -> der Messplan hat genau EINEN GC-Lauf (bei 7,5 min, 11:05:15),
  danach keinen mehr. Entscheidung 11:00: Versuch laeuft weiter, die uebrigen GC-Messungen fehlen im
  Monitoring. Danach klaeren, was im Frontend-Feld eingetragen wurde (die Liste "0;10;20;..." muss als
  Text ankommen; das Frontend castet nach data_type, `str` ist erlaubt; die Zahl 7.5 spricht dafuer,
  dass eine einzelne Zahl eingegeben wurde).
- UMGESETZT 11:20 (Dummy-getestet, aktiv nach dem naechsten Backend-Neustart): gc_minutes 0 = Dauermessung,
  Zahl N = alle N Minuten, Liste = feste Zeitpunkte; Parameter until_minutes = `minutes`. Urspruenglicher Vorschlag: run_schedule_named soll eine EINZELNE Zahl als
  "alle N Minuten bis zum Ende von `minutes`" verstehen (N>0) und 0 als Standardplan
  0,10,...,60,80,...,200,219; zusaetzlich im Frontend-Feld einen Hinweistext/Standardwert.
- Zweitens: Das Experiment endet mit dem letzten GC-Lauf (~11:13), NICHT nach 219 min - weil der
  microGC dann fertig ist? NEIN: Netzteil und Pumpe bleiben bis 219 min Busy, das Experiment wartet auf
  alle Geraete. Ende also regulaer ~14:37.

### Bronkhorst MFC liefert kaum Fluss (11:03)
- Kommunikation ist in Ordnung: ein Wert je Sekunde, keine Fehler/Retries im Log.
- Fluss nach 6 min Elektrolyse bei 0.55 A: 0.0-0.23 mL/min, Zaehler 0.0 mLn.
  Am 08.10. (gleicher Strom): nach 40 s schon 0.74 mL/min, nach 1 min ~1 mL/min, Median 1.5 mL/min,
  Zaehler am Ende 220 mLn. Heute also etwa Faktor 5 weniger bei gleicher Gasproduktion.
- Das Backend misst richtig; Ursache im Gasweg (Undichtigkeit, Gas geht am MFC vorbei, Ventilstellung)
  oder Gas sammelt sich (Druckaufbau) - am Aufbau pruefen.

### Nachtrag 11:20: MFC-Fluss kam doch
- Ab 11:19:54 sprang der Fluss innerhalb von 10 s von ~0 auf 5 mL/min (Spitze 7.8, Median danach 6.7 mL/min).
  Gleichzeitig: pH-Einbruch auf 6.2 (11:19:16), Leitfaehigkeit 11:21:21-11:22:06 auf 0 / "Uncertain".
  Passt zu einem Eingriff am Aufbau um 11:19 (Ventil/Gasweg) - vorher ging das Gas am MFC vorbei.
- Zaehler am Ende 1250 mLn. Faraday-Kontrolle: 7236 C = 0.075 mol e- -> 840 mLn H2 + 420 mLn O2 =
  1260 mLn (bei reiner Wasserelektrolyse; Kolbe-Gase liegen in derselben Groessenordnung). Der Zaehler
  stimmt also mit der Ladung ueberein, obwohl die ersten 22 Minuten ohne Fluss waren.

## Ergebnis (Ende 14:37:04, Finished, Dauer 13158 s = 219.3 min)
- Netzteil: 0.55 A konstant, Spannung 4.0 -> 5.1 V (max) -> 5.0 V, Ladung 7236 C. Ausgang nach dem Ende aus.
- Liquiline: pH 9.28 -> 8.92 (Einbruch 6.2 um 11:19), Leitfaehigkeit 52.8 -> 38.2 mS/cm (max 76),
  Temperatur 21.0 -> 25.5 degC. Sensorstatus Good bis auf 22 Werte "Uncertain" um 11:21.
- Pumpe 100 mL/min (113 rpm) durchgehend.
- GC im Experiment: nur der eine Lauf "26175_7.5 min" (H2 2.69 %, CO2 0.41 %, N2 95.7 %, O2 0.90 %).
  Die weiteren Messungen kamen aus tools/kolbe_gc_messplan.py (Tippfehler: Versuch 21675 statt 26175):
  12 Laeufe 10..120 min ab Skriptstart 11:19:39 (Dateien logs/2026/10/13/microgc/21675_<N>_min.csv,
  letzte um 13:26). Von 13:26 bis 14:37 gibt es KEINE GC-Messung. Der Bericht ordnet alle 13 Laeufe
  ueber die Startzeit dem Experiment zu.
- Berichte: logs/2026/10/13/Elektrolyse_26175-kolbe_elektrolyse_26175-8/bericht.html (10-min-Tabelle),
  tabelle_10min.csv daneben, Tagesbericht logs/2026/10/13/versuchstag_2026-10-13.html.
- NACHGEBESSERT: Der automatisch erzeugte Bericht war 93 MB (Rohwerte-CSV als Base64 im HTML, 92828
  Zeilen x ~80 Spalten). tools/auswertung.py legt Rohwerte ueber 2 MB jetzt als `<ID>_rohwerte.csv`
  NEBEN den Bericht (62 MB); der Bericht selbst ist 6 MB, der Tagesbericht 9.6 MB.
- Backend steht seit 14:37 auf Ready mit leerer Schlange: der naechste gesendete Schritt startet sofort.
  Neuer Treiber-/Config-Stand (gc_minutes-Modi, conductivity, step_mode-Schalter) wird erst mit dem
  naechsten Backend-Start aktiv.
