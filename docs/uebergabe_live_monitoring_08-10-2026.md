# Uebergabe: Live-Werte im Monitoring (Stand 08.10.2026 frueh, vom Windows-PC)

Gebaut in der Nacht vor dem Versuch, am PC gegen LABS-DeviceDummys getestet - NICHT am
echten Geraet. Dieses Dokument ist die Arbeitsgrundlage, um am Pi weiterzumachen.

## Was gebaut wurde

### LABS-Backend, Commit 300542f (Treiber)

Vorlage war in beiden Faellen das Netzteil (joyit_dpm86.py): repeated_query + zentrale
Uebersetzung der Parser-Rohgruppen in update_observables(). Der gemeinsame Unterbau
(backend/devices/base.py, receive_reply) reicht jede geparste Antwort generisch an
update_observables() durch - deshalb braucht repeated_query keine Callbacks am Einzelbefehl.

- backend/drivers/bronkhorst_mfc.py:
  - Regex-Gruppen umbenannt (value -> measure_raw bzw. counter_raw), damit
    update_observables() die Antworten unterscheiden kann.
  - update_observables() uebersetzt zentral: measure_raw -> 'flow' (mL/min),
    counter_raw -> 'counter' (float). Statusmeldungen/Rohgruppen (len, node, status,
    statusindex) erzeugen keine Observables.
  - start_measuring(interval=1.0) / stop_measuring(): flow+counter periodisch.
    Automatisch: set_setpoint(>0) startet, stop_flow stoppt. Auch als Experimentbefehl
    aufrufbar (z.B. Basislinie ohne Setpoint).
  - measure_flow()/read_counter() sind jetzt einfache Queries (Umrechnung zentral).
- backend/drivers/longer_wt600.py:
  - dito: update_observables() uebersetzt speed/running/clockwise (Strings vom
    WT600Parser) in 'speed_rpm'/'running'/'clockwise'/'flow_ml_min'; WJ-Acks erzeugen
    keine Observables. Ohne Schlauchkalibrierung kommt die Drehzahl trotzdem.
  - start_measuring(interval=1.0) / stop_measuring(): RJ-Polling. Automatisch:
    start_pumping startet, stop_pumping stoppt.
  - ACHTUNG Intervall: bei 1200 Baud dauert ein RJ-Paar ~150 ms. Nicht unter 0,5 s gehen.
- config.dummy.yml: dosing_pump-Dummy (Port 12352), counter-Observable bei
  test_mfc_setpoint, test_wt600_speed/stop_wt600, demo_live_monitoring (laeuft
  volume/rate Minuten, fuer die Monitoring-Demo am PC).

### LABS-User-Interface, Commit 738bdca (Frontend)

- app/static/live_values.js (NEU): Tabelle "Current values" auf der Monitoring-
  Detailseite (/station/<id>), ueber den Kurven. Pro Observable des laufenden
  Experiments: letzter Wert als Zahl + Empfangsuhrzeit. Daneben die Versuchszeit
  ("running for mm:ss"), tickt sekuendlich.
- app/static/plots.js: feuert nach jedem SSE-Update ein "monitoring-update"-CustomEvent;
  die Tabelle hoert denselben Datenstrom mit. KEINE zweite EventSource - das Backend
  wird weiterhin nur 1x/s abgefragt.
- app/templates/monitoring/detail.html: Anker-Div + Einbindung.
- Verhalten: Tabelle leert sich beim Experimentwechsel; bleibt ein Wert aus, steht der
  letzte weiter da (Uhrzeit daneben altert sichtbar).

## Was am PC verifiziert wurde (Dummys)

Kompletter Durchstich: DeviceDummys + Backend (config.dummy.yml) + Frontend. Experiment
demo_live_monitoring (MFC 25 mL/min, Pumpe 100 mL/min): alle vier Observables im
Sekundentakt in Tabelle und Kurven, flow korrekt 25.0, counter akkumulierend, Pumpe
113 rpm / 100,38 mL/min. Treiberlogik zusaetzlich mit Einzeltests gegen Handbuch-Frames
geprueft (7D00 -> 50.0 mL/min, Counter-Float, WJ-Ack/Statusmeldung -> keine Observables).

## Offene Pruefpunkte fuer den Pi / Versuch

1. AM GERAET VERIFIZIEREN (vor dem Versuch, je ~1 min): test_mfc_setpoint und
   test_wt600_speed einmal ueber das Backend fahren und pruefen, dass beide Geraete das
   1-s-Polling sauber beantworten (Log: 1x/s READ_MEASURE/READ_COUNTER bzw. RJ).
2. Labor-config.yml: bei test_mfc_setpoint fehlt '- [mfc, counter, float, ""]' unter
   observables - ergaenzen, wenn der Zaehler live sichtbar sein soll. Generell: die
   Tabelle zeigt NUR, was das laufende Experiment unter observables: deklariert.
   Das gilt besonders fuer das Elektrolyse-Schritt-Experiment (Schritt 5).
3. Frontend am Pi: git pull in LABS-User-Interface, flask run, Browser Strg+F5
   (sonst altes JavaScript aus dem Cache).

## Bekannte Kanten (bewusst nicht behoben)

- RACE: stop_measuring() direkt nach start_measuring() im selben Experiment (z.B.
  stop_flow als naechster Befehl nach set_setpoint) kann das Polling verfehlen, wenn die
  RepeatedCommands noch in der Geraetequeue stehen - stop_running() setzt ein Flag, das
  execute() danach wieder ueberschreibt. Gleiche Race steckt im Netzteil-Muster. Im
  normalen Ablauf (Stopp am Ende eines langen Laufs) tritt sie nicht auf; das
  Experimentende raeumt zusaetzlich selbst auf (beobachtet: WJ-Stopp + Setpoint 0).
- dispense() der Pumpe blockiert nur das GERAET (busy/TimeCondition), nicht die
  Befehlsliste des Experiments - ein Befehl NACH dispense laeuft sofort los. Deshalb hat
  demo_live_monitoring keinen stop_flow am Ende (Kommentar in config.dummy.yml).
- Versuchszeit im Frontend rechnet Browser-Uhr gegen Backend-Zeitstempel - bei
  Uhrenversatz zwischen Pi und Browser-PC stimmt sie nicht exakt.
- "Last update" in der Tabelle ist eine UHRZEIT (HH:MM:SS) - kurz nach Mitternacht
  sieht sie wie eine Stoppuhr aus.
- LABS-User-Interface: migrations/ ist untracked (nicht auf GitHub). Auf dem Pi existiert
  das Frontend schon samt DB - nur bei einem frischen Clone wuerde flask db upgrade
  stolpern.

## Lokaler Zustand des Windows-PCs (nicht auf GitHub)

- Frontend-Dev-DB: Admin-Passwort auf admin/labs2026 zurueckgesetzt (nur die lokale
  database-devel.sqlite3 - die Pi-DB ist NICHT betroffen). Station "Lokales Testsystem"
  127.0.0.1:11123 war schon eingetragen.
- LABS-Backend: config.yml.labor-backup-2026-10-07 liegt untracked herum (redundant,
  Inhalt = committete config.yml), kann geloescht werden.
- Zum Dummy-Testen am PC: DeviceDummys main.py starten, config.dummy.yml nach config.yml
  kopieren (NICHT committen), Backend starten, flask run - siehe
  docs/daheim_entwickeln_ohne_pi.md. Dort steht noch "fuer Bronkhorst/Pumpe gibt es
  keinen Dummy" - das ist UEBERHOLT, beide Dummys existieren seit 25.08. (Ports
  12351/12352) und sprechen das aktuelle Protokoll.

## Ergebnis am Pi (08.10.2026, 09:30, echte Geraete)

- Pruefpunkt 1 ERLEDIGT: Polling am echten Bronkhorst und an der echten Longer-Pumpe laeuft.
  Testlauf `test_live_polling` (neu in config.yml, rate 100 mL/min, volume 50 mL = 30 s):
  MFC 2 Anfragen/s (READ_MEASURE + READ_COUNTER, 31 Werte in 30,7 s), Pumpe RJ ~1/s
  (26 Werte in 29,2 s; bei 1200 Baud faellt etwa jede 7. Sekunde aus, weil ein RJ-Paar ~150 ms
  braucht - erwartet, kein Fehler). Werte: flow 0,0 (kein Gas, Ventil zu), counter 793,21 konstant,
  Pumpe 113 rpm / 100,38 mL/min, running/clockwise true. Keine Fehler/Retries im Log.
- Aufraeumen am Experimentende verifiziert: Pumpe WJ-Stopp (Status 1E), MFC Setpoint 0 (Status 00),
  Polling endet.
- `test_live_polling` greift NICHT in den Gasweg ein: MFC nur `start_measuring` ohne Setpoint
  (Sicherheitsfrage 1 bleibt unberuehrt). Die Pumpe haelt per `dispense` das Experiment am Laufen.
- Pruefpunkt 2 ERLEDIGT: counter-Observable bei `test_mfc_setpoint` ergaenzt.
- Netzteil-Pfad in config.yml korrigiert: Hub-Buchse 2.4.2 haengt an Controller `xhci-hcd.1`, nicht
  `hcd.0` (so meldet es der Pi heute; Geraet antwortet, 60 V / 5 A).
- microGC: eth0 hatte um 09:26 keinen Link (carrier 0) - Geraet aus oder Kabel nicht gesteckt.
  Backend ueberspringt ihn mit Warnung, die microgc-Experimente fehlen dann in der Auswahl.

## Nachtrag 08.10. 10:10: Auswertung im Nachhinein

- Backend schreibt jetzt pro Lauf `lauf.json` neben `values.json` (Experimenttyp, Parameter mit Einheit,
  deklarierte Observablen mit Einheit, Start/Ende, Endzustand) - beim Start und am Ende, damit auch ein
  abgebrochener Lauf Typ und Parameter hinterlaesst. Am Geraet geprueft (Lauf lauf_json_test).
- `tools/auswertung.py --html` erzeugt einen Versuchsbericht als einzelne HTML-Datei (Kurven + alle
  Messwerte + CSV-Download), `--html --tag JJJJ-MM-TT` einen Tagesbericht. Beschreibung in tools/README.md.
