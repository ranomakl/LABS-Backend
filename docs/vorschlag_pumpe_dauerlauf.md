# Vorschlag: Pumpe laeuft durchgehend (Fluessigkeit umwaelzen) - 13.10.2026

Status: **Teil 1 GEBAUT (nur Gas zaehlen), Teil 2 VORSCHLAG, nicht gebaut.**

Wunsch vom 13.10. nachmittags: "Pumpe soll durchgehend Fluessigkeit umwaelzen", zunaechst nur beim
Gas zaehlen ("einfach ein bisschen umwaelzen").

## Teil 1 (gebaut): `kolbe_gas_zaehlen_pumpe`

Neuer Schritt in config.yml (und config.dummy.yml), aktiv nach dem naechsten Backend-Start und
"Download Experiments from Station" im Frontend:

| Parameter | Bedeutung |
|---|---|
| `minutes` | Dauer des Zaehlens in Minuten |
| `rate` | Pumpenrate in mL/min (bisher immer 100) |

Ablauf: Zaehler auf 0 -> Fluss und Zaehler jede Sekunde lesen -> Pumpe laeuft `minutes` Minuten mit
`rate` -> Pumpe stoppt, Schritt ist Finished. Live im Monitoring: mfc.flow, mfc.counter,
dosing_pump.speed_rpm, dosing_pump.flow_ml_min, dosing_pump.running. Frueher beenden: "Stop
Experiments" (Pumpe stoppt, MFC-Ventil bleibt auf).

`kolbe_gas_zaehlen` (ohne Pumpe) bleibt unveraendert bestehen. Technisch ist der neue Schritt dasselbe
wie `kolbe_n2_spuelung`; der eigene Name macht ihn im Laborplan (Schritt 8) eindeutig.

Dummy-Test 13.10. (Test-Backend Port 11124): Schritt mit minutes 0.5, rate 50 bis Finished gelaufen,
Zaehler zaehlt hoch, dosing_pump.running ist waehrend der 30 s True (60 rpm, 53 mL/min) und danach False.

## Teil 2 (Vorschlag): Pumpe ueber MEHRERE Schritte durchlaufen lassen

Heute stoppt JEDER Schritt am Ende alle beteiligten Geraete (`Experiment._stop_devices` ->
`device.stop()` -> `final_commands()`), beim Pumpentreiber heisst das `stop_pumping()`. Die Pumpe
kann deshalb nicht ueber eine Schrittgrenze hinweg laufen. Dafuer waere noetig:

1. **Treiber `longer_wt600`: Dauerlauf-Merker.**
   - `run_continuously(rate)`: setzt `_keep_running = True`, Drehzahl, Start, Live-Abfrage.
   - `stop_continuous()`: Merker loeschen, Stopp.
   - `final_commands()`: wenn der Merker gesetzt ist, KEIN Stopp, stattdessen nur ein Lesebefehl
     (die Abschaltserie braucht einen Befehl, damit der Zustand Stopped erreicht wird).
   - `run_for_minutes()` am Ende: wenn der Merker gesetzt ist, zurueck auf die Dauerlauf-Rate statt
     Stopp (sonst wuerde die N2-Spuelung oder die Elektrolyse die Pumpe anhalten).
   - `shutdown()` (Backend-Ende mit Strg+C): Merker loeschen, Pumpe stoppt. `initial_commands()`
     stoppt die Pumpe beim Verbinden wie bisher, ein Backend-Neustart haelt sie also an.
2. **Zwei neue Schritte:** `kolbe_pumpe_dauer_start` (rate) und `kolbe_pumpe_dauer_stop`. Beide sind
   sofort Finished, die Pumpe laeuft bzw. steht danach.
3. **Schritte ohne Pumpenbefehl** (`kolbe_gas_zaehlen`, GC-Einzelmessung): bekommen
   `dosing_pump.start_measuring` plus die Pumpen-Observablen, damit die laufende Pumpe im Monitoring
   sichtbar bleibt. Zwischen zwei Schritten (Ready/Paused) fragt niemand die Pumpe ab - sie laeuft,
   aber es gibt keine Werte.
4. **"Stop Experiments"**: heute "alles aus". Vorschlag: auch im Dauerlauf stoppt Stop Experiments
   die Pumpe (Setup.remote_stop loescht den Merker bei allen Geraeten, die einen haben). Alternative:
   Pumpe laeuft weiter, nur `kolbe_pumpe_dauer_stop` haelt sie an - dann muss die Anleitung das
   deutlich sagen.
5. **Fehlerfall Pumpe** (keine Antwort, Verbindung weg): der Error-Zustand wiederholt `device.stop()`;
   mit gesetztem Merker ist das nur ein Lesebefehl. Die Pumpe laeuft physisch weiter, bis sie wieder
   antwortet oder jemand sie am Geraet stoppt. Fuer eine Umwaelzpumpe vertretbar, fuer das Netzteil
   waere das undenkbar - deshalb der Merker NUR im Pumpentreiber.

Aufwand: Treiber ~40 Zeilen, config ~25 Zeilen, Unit-Test fuer final_commands/run_for_minutes mit
Merker, Dummy-Durchstich (Start -> Spuelung -> Gas zaehlen -> Stop, Pumpe laeuft durch).
Risiko: gering, solange `step_mode` aus ist und die Schritte wie heute einzeln gesendet werden.

Entscheidung offen: Teil 2 bauen? Wenn ja: Verhalten von "Stop Experiments" (Punkt 4) festlegen.
