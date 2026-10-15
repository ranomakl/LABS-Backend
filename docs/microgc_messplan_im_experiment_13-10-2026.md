# microGC-Messplan im Elektrolyse-Experiment (13.10.2026)

Umsetzung von `docs/aufgabe_microgc_im_experiment.txt`: der microGC misst jetzt INNERHALB von
`kolbe_elektrolyse_gc` zu den Zeitpunkten des Versuchsplans, die Konzentrationen erscheinen live im
Monitoring (Kurven + "Current values"), in values.json und damit im Bericht. Das zweite Terminal mit
`tools/kolbe_gc_messplan.py` entfaellt (bleibt als Fallback).

## Bedienung (Frontend)

1. Routinen neu laden, damit `kolbe_elektrolyse_gc` und `test_microgc_plan` erscheinen.
2. `kolbe_elektrolyse_gc` starten, Parameter wie `kolbe_elektrolyse_ph` plus:
   - `versuch`: Versuchsnummer, z.B. `26175` (Laufname am Geraet wird `26175_10 min`)
   - `gc_minutes`, drei Moeglichkeiten (seit 13.10. mittags, nach dem Vorfall "7.5" bei Versuch 26175):
     - `0` = **Dauermessung**: der naechste Lauf startet, sobald das Geraet fertig ist (~alle 8 min),
       bis die Elektrolysezeit `minutes` um ist. Laufname = verstrichene Minute, z.B. `26175_15.3 min`.
     - eine Zahl, z.B. `10` = alle 10 Minuten von 0 bis `minutes`.
     - Liste mit **Semikolon** (das Frontend macht aus Kommas Punkte) = feste Zeitpunkte, Versuchsplan:
       `0;10;20;30;40;50;60;80;100;120;140;160;180;200;219`
     Eine einzelne Zahl ist also NICHT mehr ein einzelner Zeitpunkt (so kam es am 13.10. zu genau
     einem Lauf bei 7,5 min). `test_microgc_plan` hat dafuer einen eigenen Parameter `minutes`.
3. Das Experiment endet erst, wenn der LETZTE GC-Lauf abgeholt ist (letzter Zeitpunkt + ca. 8 min).
   Netzteil und Pumpe schalten unabhaengig davon nach `minutes` ab. Die Anzeige "ends ~HH:MM" kennt
   nur `minutes`, nicht die GC-Nachlaufzeit.
   **Abschlussmessung (seit 16.10.2026, Wunsch Rafael):** `kolbe_elektrolyse_gc` hat in config.yml
   `final_run: true`. Damit misst der GC nach dem Ende der Elektrolyse (`minutes` um, Netzteil aus)
   noch EINMAL: er wartet, bis der letzte planmaessige Lauf fertig und das Geraet wieder im Leerlauf
   ist, startet dann den Lauf `<versuch>_Ende <t> min` (t = verstrichene Minute, z.B. `26175_Ende
   221.3 min`), holt die Werte ab, und erst danach endet das Experiment. Das gilt fuer alle drei
   `gc_minutes`-Modi. Liegt ein planmaessiger Zeitpunkt ohnehin bei oder nach `minutes` (z.B. Liste
   mit 219 bei 219 min Elektrolyse), gibt es KEINE zusaetzliche Abschlussmessung - der letzte
   planmaessige Lauf misst dann schon nach dem Ende. `gc_runs_planned` zaehlt die Abschlussmessung
   mit. "Stop Experiments" bricht auch die Abschlussmessung ab. Tests:
   backend/test/test_microgc_abschlussmessung.py.
   **Warum das Experiment nach dem Ende bis zu ~16 min weiterlaeuft (Entscheidung Rafael 16.10.: so
   lassen):** Ein GC-Lauf dauert ~7,6 min, die Gasprobe wird am ANFANG des Laufs gezogen, und ein
   laufender GC-Lauf wird nie abgebrochen. Startet ein planmaessiger Lauf kurz vor dem Ende, laeuft er
   ueber das Ende hinaus; seine Probe stammt von VOR dem Ende und ersetzt die Abschlussmessung nicht.
   Die Abschlussmessung wartet deshalb, bis er fertig ist. Beispiel Elektrolyse 219 min, Zeitpunkt 215:

   | Zeit | Was passiert |
   |---|---|
   | 215 min | planmaessiger Lauf startet (Probe von 215 min) |
   | 219 min | Netzteil aus, Pumpe stopp; Lauf laeuft noch |
   | ~222,6 min | Lauf fertig, Geraet bereit -> Abschlussmessung startet (Probe NACH dem Ende) |
   | ~230 min | Abschlussmessung abgeholt, Experiment Finished |

   Normalfall mit "alle 10 min" bei 219 min: letzter Zeitpunkt 210, fertig ~217,6, Abschlussmessung ab
   219, Finished ~226,6 - also nur EIN Lauf nach dem Ende. Bei Dauermessung (gc_minutes 0) ist am Ende
   fast immer ein Lauf offen, dann ~15 min. Es gibt in jedem Fall genau EINE Abschlussmessung.
4. "Stop Experiments" bricht den Plan ab (keine weiteren Laeufe); ein am Geraet laufender Lauf laeuft
   dort zu Ende (cmd.abort wird bewusst nicht benutzt).

Observablen (alle in %, so wie das Geraet sie liefert): `gc_H2, gc_O2, gc_N2, gc_CO2, gc_Ethylene,
gc_Ethane, gc_1_Penten, gc_n_Pentan, gc_n_Hexane, gc_n_Heptane`, dazu `gc_run_name`, `gc_runs_done`,
`gc_schedule` (running/finished/cancelled). Der Treiber meldet ALLE benannten Peaks (auch `gc_CH4`,
`gc_CO`, `gc_Propane`, ... und jeweils `..._norm` = normalizedConcentration); in config.yml werden nur
die deklarierten angezeigt - weitere einfach unter `observables:` eintragen.
Laufdaten zusaetzlich als JSON+CSV unter `logs/<J>/<M>/<T>/microgc/<Name>.json|.csv` (gleicher Ort
wie beim Skript, `tools/auswertung.py` findet sie weiterhin).

## Wie es funktioniert (Treiber `inficon_microgc_fusion.py`, `run_schedule_named`)

- Methode wird EINMAL geladen; dann haelt `busy(gc_schedule == finished)` das Geraet bis zum Ende des
  Plans im Busy-Zustand (so wie das Netzteil bei `output_constant_current`).
- Je Zeitpunkt ein `reactor.callLater`-Timer. Faellige Laeufe werden NACHEINANDER abgearbeitet; ist
  der vorige noch nicht fertig, startet der naechste direkt danach (Warnung "verspaetet" im Log).
- Je Lauf: Status pollen bis Leerlauf (ready/standby) -> `/v1/lastRun` merken -> POST `cmd.run` mit
  `{"runWhenReady": true, "annotations": {"name", "tags"}}` -> Status pollen, bis der Lauf aktiv war
  (preparing/method-running) und wieder im Leerlauf ist -> neue dataLocation holen (muss sich geaendert
  haben, sonst Warnung) -> Laufdaten laden -> Konzentrationen melden, Dateien schreiben.
- Alle Befehle des Plans laufen mit `urgent=True, run_while_device_busy=True`: sie werden vor dem
  Wartebefehl des Experimentendes eingereiht und auch im Busy-Zustand ausgefuehrt (devicestate.Busy).
- `stop()` des Geraets bricht den Plan ab (Timer gecancelt, keine neuen Befehle), dann normaler
  Abschaltpfad.
- Zeitueberschreitung: 30 min je Lauf, 5 min fuer das Laden -> Lauf gilt als fehlgeschlagen, der Plan
  macht mit dem naechsten weiter; Geraetefehler (`public:error*`) ebenso.

## Warum erst Leerlauf abwarten (Befund 13.10.2026)

`kolbe_gc_messung` ueber das Backend (loadMethod, 3 s spaeter cmd.run mit Name) lieferte einen Lauf
OHNE annotations in den Laufdaten - das Geraet war beim cmd.run noch in `public:loading-method`. Das
Skript vom 08.10. wartete das Laden ab und die Namen kamen an. Der Messplan wartet deshalb vor jedem
Lauf auf ready/standby. (`kolbe_gc_messung` selbst ist unveraendert; fuer benannte Einzellaeufe lieber
`test_microgc_plan` mit `gc_minutes: 0` nehmen.)

## Getestet

- Dummy (LABS-DeviceDummys, erweitert um POST/annotations/realistische Peaks/Statusfolge), zweites
  Backend auf dem Pi (Port 11124): `test_microgc_plan` 3 Laeufe -> Finished, Namen/Werte/Dateien ok;
  Stop mitten im Plan -> abgebrochen, kein weiterer Lauf, Geraet Stopped; `kolbe_elektrolyse_gc` mit
  allen Dummys -> Finished, alle Observablen in values.json mit aktuellem Zeitstempel.
- `python -m twisted.trial backend.test`: 45 Tests gruen (neu: test_microgc_plan.py, inkl. echter
  Laufdaten vom 13.10.).
- Am echten Geraet (13.10. vormittags): `test_microgc_status` und `kolbe_gc_messung` ueber das
  Backend gelaufen (Luft: O2/N2 21/77 %).
- Am echten Geraet (13.10., 09:56-10:14): `test_microgc_plan` (Test_0 min) und `kolbe_elektrolyse_gc`
  als Probelauf (0.1 A, 2 V, 1 min, Pumpe 1 mL/min, GC bei 0 min) -> beide Finished, Name+Tags in den
  Laufdaten des Geraets, gc_*-Werte im Monitoring und in values.json, Dateien unter logs/.../microgc/.
  Liquiline-Kanaele meldeten "Bad"/0.0 (Sensoren noch nicht im Medium) - unabhaengig vom Ablauf.

## Nebenbei behoben

- `update_observables` ohne Zeitstempel benutzte den Import-Zeitpunkt (Default-Argument); der Treiber
  uebergibt jetzt `time.time()`. `get_last_run_data` meldet zusaetzlich die Konzentrationen.
- Logzeile "Wrote POST ..." brach die Twisted-Formatierung ("Unable to format event") - behoben.
