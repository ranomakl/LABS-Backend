# microGC-Messplan im Elektrolyse-Experiment (13.10.2026)

Umsetzung von `docs/aufgabe_microgc_im_experiment.txt`: der microGC misst jetzt INNERHALB von
`kolbe_elektrolyse_gc` zu den Zeitpunkten des Versuchsplans, die Konzentrationen erscheinen live im
Monitoring (Kurven + "Current values"), in values.json und damit im Bericht. Das zweite Terminal mit
`tools/kolbe_gc_messplan.py` entfaellt (bleibt als Fallback).

## Bedienung (Frontend)

1. Routinen neu laden, damit `kolbe_elektrolyse_gc` und `test_microgc_plan` erscheinen.
2. `kolbe_elektrolyse_gc` starten, Parameter wie `kolbe_elektrolyse_ph` plus:
   - `versuch`: Versuchsnummer, z.B. `26175` (Laufname am Geraet wird `26175_10 min`)
   - `gc_minutes`: Messzeitpunkte in Minuten ab Start, **Trenner Semikolon** (das Frontend macht aus
     Kommas Punkte): `0;10;20;30;40;50;60;80;100;120;140;160;180;200;219`
3. Das Experiment endet erst, wenn der LETZTE GC-Lauf abgeholt ist (letzter Zeitpunkt + ca. 8 min).
   Netzteil und Pumpe schalten unabhaengig davon nach `minutes` ab. Die Anzeige "ends ~HH:MM" kennt
   nur `minutes`, nicht die GC-Nachlaufzeit.
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
  Backend gelaufen (Luft: O2/N2 21/77 %). `run_schedule_named` am Geraet: siehe OFFENE_FRAGEN.md.

## Nebenbei behoben

- `update_observables` ohne Zeitstempel benutzte den Import-Zeitpunkt (Default-Argument); der Treiber
  uebergibt jetzt `time.time()`. `get_last_run_data` meldet zusaetzlich die Konzentrationen.
- Logzeile "Wrote POST ..." brach die Twisted-Formatierung ("Unable to format event") - behoben.
