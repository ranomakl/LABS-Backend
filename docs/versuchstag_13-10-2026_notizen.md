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
- Vorschlag, damit es nicht wieder passieren kann: run_schedule_named soll eine EINZELNE Zahl als
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
