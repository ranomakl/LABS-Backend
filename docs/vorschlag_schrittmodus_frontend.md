# Vorschlag: Schrittmodus - ein Klick pro Versuchsschritt im Frontend (13.10.2026)

Wunsch (Rafael, 13.10.): Alle Schritte eines Versuchs (z.B. Pumpe, Spuelung, Elektrolyse, Gas zaehlen)
mit allen Werten im Frontend vorladen und senden. Danach soll JEDER Schritt erst starten, wenn jemand
im Frontend einen Knopf drueckt. Kein Terminal.

Status 13.10.2026 nachmittags: **GEBAUT, aber im Labor NICHT eingeschaltet** (Entscheidung Rafael: fuer den
Versuch morgen noch nicht benutzen). Schalter `step_mode` in config.yml, dort auf `false` -> Verhalten
wie bisher. Einschalten = `step_mode: true` setzen und das Backend neu starten (nicht waehrend eines Laufs).
Getestet: 6 Unit-Tests (backend/test/test_schrittmodus.py) und der Durchstich an den Dummys (zweites
Backend, config.dummy.yml hat step_mode: true): Senden startet nichts, Start = genau ein Schritt, danach
Paused mit finished_runs/next_experiment_name, Start bei leerer Schlange bleibt Paused, Senden im
Paused-Zustand startet nichts. Frontend zeigt im Schrittmodus "Paused - step N of M done, next: X - press
Start Experiments" (LABS-User-Interface app/monitoring/views.py). Nebenbei behoben: ein unbekannter
Experimenttyp hinterliess eine ID ohne Experiment in der Schlange (jeder spaetere Start scheiterte).

## Wie es heute laeuft

- "Start Experiments" im Frontend ruft `/api/start` auf. `Setup.start()` setzt den Zustand von
  Paused (oder Stopped) auf Ready. `Ready.enter()` (backend/setup/setupstates.py) nimmt das naechste
  Experiment aus der Warteschlange und startet es, Zustand Busy.
- Ist ein Experiment fertig, setzt `Setup.execute_experiment()` (backend/setup/setup.py) den Zustand
  wieder auf Ready -> das naechste Experiment startet SOFORT, ohne Knopf. Alle gesendeten Schritte
  laufen deshalb in einem Rutsch durch.
- Falle: Steht das Backend auf Ready mit leerer Warteschlange (letzter Schritt fertig), startet ein
  neu gesendeter Schritt SOFORT beim Senden (`Ready.insert_experiment_after()` ruft `enter()`).
  Wer nach dem Spuelen die Elektrolyse sendet, hat sie damit schon gestartet.

## Vorschlag: Schrittmodus

Nach dem Ende eines Experiments geht das Backend auf **Paused statt Ready**. Das naechste Experiment
wartet in der Schlange, bis "Start Experiments" gedrueckt wird. Im Leerlauf steht das Backend damit
immer auf Paused -> Senden startet nie etwas, nur der Knopf.

### Backend (ca. 10-20 Zeilen)

1. config.yml, oben bei `listen port` / `log_level`:

       step_mode: true     # true = nach jedem Experiment anhalten, "Start Experiments" startet das naechste

2. `Setup.execute_experiment()`: statt fest `Ready` -> `Paused`, wenn `step_mode` gesetzt ist.
3. `Paused` erbt heute von `Busy` und meldet in `station_overview` das zuletzt gelaufene Experiment als
   "running". Anpassen: im Paused-Zustand kein laufendes Experiment melden, dafuer das naechste
   anstehende (neues Feld `next_experiment_name`), damit das Frontend "Naechster Schritt: ..." zeigen kann.
4. Unveraendert: Stop/Failed -> Backend neu starten (bekannte Einschraenkung).

### Frontend (optional, ca. 30 min)

- Ueber den Knoepfen eine Zeile: "Schritt 2 von 4 fertig. Naechster Schritt: Elektrolyse_26175 -
  Start Experiments druecken." (aus `station_overview`: status, current_run_number,
  total_experiments_queued, next_experiment_name).
- Die Warteschlangen-Tabelle oben gibt es schon; evtl. den naechsten Schritt hervorheben.

### Test

- Dummys am PC: vier Experimente senden, pruefen: nach jedem Finished Zustand Paused, naechstes erst
  nach `/api/start`; Senden im Paused-Zustand startet nichts; Stop/Failed wie bisher.
- Dann am Pi: `git pull`, config.yml `step_mode: true`, Backend neu starten (NICHT waehrend eines Laufs).

### Aufwand

Backend + Dummy-Test ca. 1 h, Frontend-Hinweis ca. 0,5 h.

## Ergaenzungen nach Durchsicht des Codes (13.10. nachmittags)

Drei Punkte, die im Vorschlag oben fehlen; ohne 1. ist der Schrittmodus nicht sicher.

1. **Die Falle kommt durch die Hintertuer zurueck.** `Setup.start()` setzt Ready; `Ready.enter()` faengt
   bei leerer Warteschlange den IndexError und laesst den Zustand auf Ready stehen. Drueckt jemand
   "Start Experiments" ohne wartenden Schritt, startet das naechste GESENDETE Experiment sofort beim
   Senden (`Ready.insert_experiment_after()` ruft `enter()`). Noetig im Schrittmodus:
   - `Ready.enter()`: bei leerer Schlange zurueck auf Paused (statt Ready bleiben);
   - `Ready.insert_experiment_after()`: im Schrittmodus NICHT `enter()` aufrufen, nur einreihen.
   Regel danach: Es gibt genau einen Weg, ein Experiment zu starten - den Knopf.
2. **Paused meldet das alte Experiment als laufend.** `Paused` erbt von `Busy`, `get_current_experiment()`
   liefert das Experiment am aktuellen Index = das gerade beendete. `station_overview` meldet es als
   `running_experiment_name`, `get_updates` liefert `experiment_started`/`experiment_planned_end` des
   alten Laufs, und `live_values.js` laesst die Laufzeit weiterticken. Noetig:
   - `station_overview` im Paused-Zustand: `running_experiment_name` leer, neues Feld
     `next_experiment_name` (naechster in `experiment_id_order` nach dem aktuellen Index, oder leer),
     `current_run_number` = Zahl der fertigen Schritte;
   - `get_updates` im Paused-Zustand: `current_experiment` leer, `experiment_started` leer. Die
     Observablen des letzten Schritts duerfen weiter geliefert werden (Werte bleiben sichtbar);
   - Frontend `monitoring/views.py` (Zeile ~112 "Paused - Not started"): wenn `current_run_number` > 0,
     Text "Paused - Schritt N von M fertig, naechster: <next_experiment_name>, Start Experiments
     druecken".
3. **Stop und Failed unveraendert:** danach Backend neu starten (wie heute). Nicht Teil dieser Aenderung.

Weitere Hinweise:
- `step_mode` in config.yml UND config.dummy.yml auf true, damit der Dummy-Test dasselbe Verhalten
  prueft. Standard, wenn der Schluessel fehlt: false (Verhalten wie heute), damit alte Configs weiterlaufen.
- Test an den Dummys (zweites Backend auf dem Pi, Port 11124, wie beim microGC-Messplan): vier
  Experimente senden -> nach jedem Finished Paused, naechstes nur per /api/start; /api/start bei leerer
  Schlange -> Paused; Senden im Paused-Zustand startet nichts; Stop -> Stopped wie bisher.
- Aktiv erst beim naechsten Backend-Start (NICHT waehrend eines Laufs). Vorher
  docs/ablauf_versuch_im_labor.md Abschnitt 6 anpassen: nach jedem Schritt "Start Experiments" druecken.

### Heutiges Verhalten, zur Einordnung (Frage 13.10.: "Submit Stage startet das Experiment sofort?")

Ja, und zwar immer dann, wenn das Backend auf **Ready mit leerer Warteschlange** steht - das ist der
Zustand nach dem letzten fertigen Experiment ("Ready - Queue finished"). Waehrend ein Experiment laeuft
(Busy) wird ein gesendeter Schritt nur eingereiht und startet, sobald der laufende fertig ist. Nach
dem Backend-Start (Paused) wird nur eingereiht, bis "Start Experiments" gedrueckt wird. Das ist das
urspruengliche LABS-Verhalten (Warteschlange laeuft von selbst durch), nicht fuer den Laborbetrieb
gedacht. Fuer HEUTE heisst das: Nach dem Ende der Elektrolyse (~14:37) steht das Backend auf Ready;
der naechste gesendete Schritt (Gas zaehlen, Nachspuelen) startet SOFORT beim Senden - also erst
senden, wenn der Aufbau dafuer steht.

## Entscheidung (offen)

a) `step_mode` fest in config.yml - im Labor immer ein Klick pro Schritt. Einfachste, sicherste Variante.
b) Zusaetzlich ein Umschalter im Frontend (Auto / Schritt fuer Schritt), falls z.B. nachts alles
   durchlaufen soll. Kann spaeter auf a) aufgesetzt werden (API `set_step_mode`).

Empfehlung: mit a) anfangen.

Siehe auch docs/ablauf_versuch_im_labor.md (Bedienung fuer den Anwender).
