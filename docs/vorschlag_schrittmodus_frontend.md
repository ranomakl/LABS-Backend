# Vorschlag: Schrittmodus - ein Klick pro Versuchsschritt im Frontend (13.10.2026)

Wunsch (Rafael, 13.10.): Alle Schritte eines Versuchs (z.B. Pumpe, Spuelung, Elektrolyse, Gas zaehlen)
mit allen Werten im Frontend vorladen und senden. Danach soll JEDER Schritt erst starten, wenn jemand
im Frontend einen Knopf drueckt. Kein Terminal.

Status: Vorschlag, nicht umgesetzt. Entscheidung offen (siehe unten).

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

## Entscheidung (offen)

a) `step_mode` fest in config.yml - im Labor immer ein Klick pro Schritt. Einfachste, sicherste Variante.
b) Zusaetzlich ein Umschalter im Frontend (Auto / Schritt fuer Schritt), falls z.B. nachts alles
   durchlaufen soll. Kann spaeter auf a) aufgesetzt werden (API `set_step_mode`).

Empfehlung: mit a) anfangen.

Siehe auch docs/ablauf_versuch_im_labor.md (Bedienung fuer den Anwender).
