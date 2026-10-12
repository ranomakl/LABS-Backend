# Fehlerpfad-Nachbesserung 12.10.2026: Abschalten muss ankommen, Verbindungsverlust muss auffallen

Geschrieben 12.10.2026 von Claude (KI-Assistent) auf Bitte von Rafael Kleiner, nach dem Review der
Korrekturen zum Vorfall vom 08.10.2026 (Netzteil blieb nach Abbruch an, siehe
`docs/vorfall_08-10-2026_netzteil_blieb_an.txt`). Stand: Code geaendert, 16 automatische Tests gruen,
Dummy-Lauf am Pi bestanden (Protokoll unten). **Test am echten Netzteil steht noch aus** (Anleitung in
Abschnitt 8).

## 1. Kurzfassung

Die Korrekturen vom 08.10. schliessen das konkrete Loch (Abschaltbefehl wurde im Error-Zustand
verweigert). Beim Lesen des gesamten Fehlerpfads am 12.10. fielen zwei weitere Luecken im selben Pfad
auf, beide per Simulation gegen den echten Backend-Code bestaetigt:

| | Luecke | Folge vorher | Jetzt |
|---|---|---|---|
| 1 | Ein Timeout **innerhalb einer CommandSeries** erreichte die Serie nie. `device.stop()` schickt die Abschaltbefehle genau so. | AUS wurde 4x in 10 s geschrieben, dann **nie wieder**; die Serie blieb fuer immer "NotSent", niemand erfuhr vom Scheitern. Ein Geraet, das schon bei `initial_commands` schweigt, hing ewig in NotReady statt Error. | Timeout geht an die Serie; die Serie scheitert sichtbar (Logzeile `CommandSeries [...] failed.`), das Geraet geht nach Error. Im Error-Zustand wird `stop()` **alle 5 s wiederholt, bis das Geraet bestaetigt** (-> Stopped). |
| 2 | **Serieller Verbindungsverlust** (USB-Adapter weg) wurde nicht erkannt: nur `protocol = None`. | Geraet blieb Busy, Experiment lief weiter, Messung starb leise, Netzteil blieb an - und AUS haette nicht einmal gesendet werden koennen. | Geraet -> Error (Experiment -> Failed, uebrige Geraete werden gestoppt), Wiederverbindung alle 2 s; nach Erfolg schalten `initial_commands` (Ausgang aus, Ventil auf, Pumpe stopp) den sicheren Zustand. Experiment reagiert jetzt auch auf Geraetezustand "Shutdown". |

Nicht in dieser Nachbesserung enthalten (Abschnitt 9): Hardware-Interlock, Autostart (systemd),
Stopp-Reihenfolge, Frontend-Alarm, Plausibilitaetspruefung 48 V / 0 A.

## 2. Wie das Review gemacht wurde

- Alle Dateien des Fehlerpfads gelesen: `backend/commands/commands.py`, `commandstate.py`,
  `backend/devices/devicestate.py`, `base.py`, `backend/experiments/experiment.py`,
  `experimentstates.py`, `backend/setup/setup.py`, `setupstates.py`, `backend/drivers/joyit_dpm86.py`,
  dazu Vorfallbericht und Dummy-Testanleitung.
- Verdachtspunkte mit kleinen Skripten gegen den echten Code geprueft (Twisted `task.Clock` als
  simulierte Uhr, ein Fake-Protokoll, das nie antwortet). Das Ergebnis fuer Luecke 1, Stand a4cc998:

      gesendet: 4x ':01w12=0,,'          (innerhalb ~10 s)
      Zustand der Serie: NotSent | Zustand des inneren Befehls: Fail
      series.deferred_result gefeuert?: NEIN
      Geraetezustand danach: Error  (bzw. NotReady, wenn das Geraet vorher Ready war)

- Fuer Luecke 2 wurde zusaetzlich geprueft, dass Twisted bei einem seriellen Port das Verschwinden der
  Gegenseite ueberhaupt meldet (Pseudo-Terminal, Master geschlossen -> `connectionLost` kommt). Ja.

## 3. Luecke 1: Timeout in einer CommandSeries

### Mechanismus vorher

`device.stop()` (base.py) sammelt die `final_commands()` in einer `CommandSeries` und sendet sie als
EINEN dringenden Befehl. Antworten kommen ueber `device.receive()` und werden an
`device.current_command` (= die Serie) gegeben; die Serie reicht sie an den aktuellen inneren Befehl
weiter und zaehlt Retries (`CommandSeries.state`-Setter). Der **Timeout** aber haengt am inneren
`Command` (`commandstate.Sent.enter` startet den Timer auf `self._command`) und meldete sich nur dort:
innerer Befehl -> Retry -> Retry -> Retry -> Fail -> `deferred_result.errback` **ohne Abnehmer**
(innerhalb einer Serie bekommen innere Befehle keine Geraete-Callbacks, `CollectingCommands.add_command_callbacks`
ist leer). Die Serie merkte nichts.

### Aenderung

- `commands.py`: Jeder Befehl kennt jetzt die Serie, in der er laeuft (`parent_command_series`, gesetzt
  in `CommandSeries.execute`, vorher nur fuer verschachtelte Serien).
- `commandstate.py`, `Sent.enter.timedout`: Laeuft der Befehl in einer Serie und ist deren aktueller
  Befehl, geht der Timeout an die **Serie** (`series.temp_result = CommandTimeoutError; series.state = Retry`)
  - exakt der Weg, den `device.receive()` fuer Antworten nimmt. Die Serie wiederholt den inneren Befehl
  (bis `retries`), dann die ganze Serie (bis `retries` der Serie), dann `fail()` -> `deferred_result.errback`
  -> `handle_fail` des Geraetezustands -> Geraet Error.
- Einzelbefehle (kein Serienkontext) verhalten sich unveraendert (Test `test_einzelbefehl_timeout_unveraendert`).

Zahlen fuer `stop()`: innerer Befehl 4 Versuche x 2,5 s, Serie 4 Durchlaeufe -> **16 Sendungen in ~40 s**,
dann `failed.` (Parameter: `retries=3`, `timeout=2.5` aus `CommandParameterFactory`).

### Wiederholung im Error-Zustand (devicestate.py, Klasse `Error`)

- Neues Kennzeichen `shutdown_path=True` in `DeviceCommandParameterFactory`, gesetzt nur von
  `AbstractBaseDevice.stop()` und `MultichannelBaseDevice.stop()`. (`urgent` allein taugt nicht als
  Kennzeichen: `RepeatedCommand` setzt `urgent=True` fuer das Polling im Busy-Zustand - das fiel im
  ersten Dummy-Lauf auf, weil ein gescheitertes Polling eine Wiederholung ausloeste.)
- Scheitert ein Befehl mit `shutdown_path` (egal in welchem Zustand das Geraet den Fehler behandelt),
  plant der Error-Zustand `device.stop()` in `RETRY_INTERVAL = 5 s` neu. Das wiederholt sich, bis
  die Serie bestaetigt wird (-> `Stopped`, Timer wird gecancelt) oder das Geraet nach Shutdown/
  NotReady/Initializing wechselt.
- Dringende Befehle im Error-Zustand gehen jetzt **nacheinander** auf die Leitung (`_in_flight`,
  Warteschlange in `cmd_queue`). Vorher rief `Error.send_cmd` sofort `execute_cmd`, auch wenn schon
  ein Befehl lief - `current_command` waere ueberschrieben und die Antwort falsch zugeordnet worden.
- Ohne Verbindung (`device.protocol is None`) scheitert ein dringender Befehl sofort und sauber
  (`DeviceErrorError("NO CONNECTION ...")`), statt mit `AttributeError` aus `stop()` zu fliegen. Die
  Wiederholung laeuft trotzdem; das eigentliche Abschalten nach Wiederverbindung uebernehmen die
  `initial_commands` (Abschnitt 4).
- `Error.new_state` laesst zusaetzlich `Initializing` zu (einziger Weg dorthin: `connection_done()`
  nach Wiederverbindung).
- `Experiment._stop_devices` haengt an jede Abschaltserie einen Errback, der das Scheitern klar
  benennt (`Shutdown commands for psu NOT confirmed: ...`) statt irgendwann spaeter
  "Unhandled error in Deferred".

## 4. Luecke 2: Verbindungsverlust

### Mechanismus vorher

`BaseDeviceProtocol.connectionLost` setzte nur `device.protocol = None`. `device.connection_lost()`
(-> Zustand Shutdown) wurde nur aus `BaseDeviceProtocolFactory.clientConnectionLost` gerufen, und die
gibt es nur bei TCP. Netzteil, MFC und Pumpe sind seriell. Folge: Zustand blieb Busy, der naechste
Schreibversuch warf im Hintergrund `AttributeError` (kein `Sent`, kein Timer, kein Retry, kein Error),
das Polling starb leise. `Experiment.update` reagierte ausserdem nur auf "Error", nicht auf "Shutdown"
- selbst bei TCP-Geraeten lief das Experiment also weiter.

### Aenderung (base.py, experiment.py)

- `BaseDeviceProtocol.connectionLost` ruft `device.connection_lost(reason)`. Die Methode ist idempotent
  (TCP meldet den Verlust ueber Protocol UND Factory).
- `connection_lost`: wenn nicht absichtlich Shutdown -> Logzeile `CONNECTION LOST to <Adresse> ...`,
  Observable `errorcode` (als **String** - vorher ein Failure-Objekt, das `json.dump` von values.json
  haette scheitern lassen), Zustand **Error**, Wiederverbindung planen.
- `_reconnect` alle `RECONNECT_INTERVAL = 2 s`: `connect()` neu aufrufen. Seriell wirft `SerialPort()`
  solange die Geraetedatei fehlt (USB nicht wieder eingesteckt) - wird gefangen und erneut geplant.
  `_new_protocol_deferred()` ersetzt das bereits gefeuerte `factory.d_protocol`. Logs: Versuch 1, 5 und
  jeder 30. auf Info, der Rest auf Debug; `RECONNECTED to ... after n attempt(s)` bei Erfolg.
- Nach Wiederverbindung laeuft wie beim Start `connection_done()` -> `Initializing` -> `initial_commands()`.
  Beim Joy-IT-Netzteil ist das `stop_current()` (Ausgang aus), beim MFC Ventil auf, bei der Pumpe Stopp.
  Danach `Ready`. Das Experiment ist zu dem Zeitpunkt laengst Failed, das Setup Failed - es laeuft
  **nichts automatisch weiter**.
- `Experiment.update`: Zustand "Error" **oder "Shutdown"** eines beteiligten Geraets -> Experiment Failed.

### Was bei einem Kabelbruch waehrend der Elektrolyse jetzt passiert (Soll)

1. `[Joy-IT DPM86xx ...] CONNECTION LOST to /dev/serial/by-path/...: ... - device -> Error, reconnecting every 2.0 s`
2. `Experiment ... changed to: Failed`, Pumpe Stopp, MFC Ventil auf (bestaetigt), Bericht, Setup Failed.
3. Netzteil: `NO CONNECTION, cannot send urgent command CommandSeries [...]`, dann alle 5 s
   `repeating device.stop()` (scheitert weiter, solange keine Verbindung).
4. Kabel wieder drin: `Reconnect attempt n`, `RECONNECTED`, `Wrote :01w12=0,,` (Ausgang aus),
   `changed to: Ready`. Der Ausgang ist aus, sobald der Pi das Geraet wieder sieht.
5. Kabel bleibt draussen: Ausgang bleibt an - **das kann keine Software aendern** (Abschnitt 9).

## 5. Geaenderte Dateien

| Datei | Aenderung |
|---|---|
| `backend/commands/commands.py` | `parent_command_series` fuer alle Befehle; Parameter `shutdown_path` |
| `backend/commands/commandstate.py` | `Sent.enter.timedout` leitet Timeout an die umgebende Serie |
| `backend/devices/devicestate.py` | `DeviceState.callLater`; `handle_fail` plant stop()-Wiederholung bei `shutdown_path`; Klasse `Error` neu (Warteschlange, Wiederholung, NO CONNECTION, Initializing erlaubt) |
| `backend/devices/base.py` | `connectionLost` -> `connection_lost`; `connection_lost` -> Error + Reconnect; `_reconnect`, `_schedule_reconnect`, `_new_protocol_deferred`; `stop()` setzt `shutdown_path=True` |
| `backend/experiments/experiment.py` | `update` reagiert auch auf "Shutdown"; `_stop_devices` loggt gescheiterte Abschaltserien |
| `backend/test/test_fehlerpfad_abschalten.py` | 6 Tests zu Luecke 1 (neu) |
| `backend/test/test_fehlerpfad_verbindungsverlust.py` | 9 Tests zu Luecke 2, davon einer mit echtem Twisted-SerialPort am Pseudo-Terminal und zwei mit echtem `Experiment` (neu) |

Nicht geaendert: Treiber, config.yml, Frontend.

## 6. Automatische Tests

    cd ~/LABS/LABS-Backend
    .venv/bin/python -m twisted.trial backend.test        # 16 Tests, ca. 1,5 s

Alle Tests laufen ohne Hardware mit simulierter Uhr. Was sie absichern:

- Serie bei stummem Geraet scheitert sichtbar, Geraet -> Error; 16 Sendungen in 40 s.
- Wiederholung im Error-Zustand bis Bestaetigung; nach `Stopped` wird nichts mehr gesendet.
- Wiederholung auch, wenn das Geraet beim Abschalten noch gesund war (Fehler im NotReady-Zustand).
- `stop()` ohne Verbindung wirft nicht, scheitert sofort, sendet nach Rueckkehr der Verbindung.
- Zwei `stop()` hintereinander: nacheinander auf der Leitung.
- Einzelbefehl-Timeout unveraendert (4 Sendungen, Error).
- Verbindungsverlust -> Error (auch aus Busy), `errorcode` ist String, Reconnect alle 2 s, nach Erfolg
  `initial_commands` und Ready, danach kein weiterer Reconnect; Shutdown absichtlich -> kein Reconnect;
  TCP-Doppelmeldung -> ein Zyklus.
- Echter `SerialPort` am Pseudo-Terminal: Gegenseite schliessen -> Geraet Error, Reconnect geplant.
- Echtes `Experiment` mit zwei Geraeten: Verbindungsverlust des einen -> Failed, das andere wird
  gestoppt, values.json/lauf.json (`final_state: Failed`) geschrieben, Setup-Deferred errbackt,
  Wiederholung fuer das verlorene Geraet geplant. Gleiches fuer Zustand "Shutdown".

Hinweis: Trial meldet bei den Serien-Tests gelegentlich `Unhandled error in Deferred` fuer die
**inneren** Befehle einer gescheiterten Serie (`CommandRetryError`). Das ist bekannt und unschaedlich
(die Serie selbst meldet den Fehler); die Tests raeumen es in `tearDown` weg.

## 7. Dummy-Lauf am Pi (12.10.2026, LABS-DeviceDummys 9793d0d, config.dummy.yml)

Backend aus einem Scratch-Verzeichnis mit `config.dummy.yml` als `config.yml`, Experiment
`test_fehlerpfad_mfc_pumpe` (MFC-Polling + Pumpe), MFC per Datei `STUMM_bronkhorst_mfc` stummgeschaltet.

    11:00:46  MFC Error (3 Retries des Pollings, dann Fail) -> Experiment Failed -> Setup Failed
    11:00:46  MFC: sending URGENT command anyway (shutdown path): CommandSeries [Command :06030101217D00]
    11:00:46  Pumpe: Stopp gesendet und bestaetigt -> Stopped; Bericht erzeugt
    11:00:46 - 11:01:26  Ventil-auf 16x gesendet (Retry/Serien-Retry), keine Antwort
    11:01:26  MFC: CommandSeries [Command :06030101217D00] failed.                <- NEU (vorher stumm)
    11:01:26  MFC: shutdown command ... NOT confirmed - repeating device.stop() in 5.0 s   <- NEU
    11:01:31  MFC: repeating device.stop() (final commands) until the device confirms      <- NEU
    11:01:34  STUMM-Datei geloescht
    11:01:36  MFC: Ventil-auf bestaetigt -> State of Device changed to: Stopped

Danach Dummy-Prozess beendet (= TCP-Verbindungsabbruch aller acht Dummy-Geraete) und nach 7 s neu
gestartet:

    11:03:40  je Geraet: CONNECTION LOST to 127.0.0.1:123xx ... - device -> Error, reconnecting every 2.0 s
    11:03:42 / :44 / :46  Reconnect attempt 1 ... failed: Connection refused (Dummys noch aus)
    11:03:48  je Geraet: Initializing -> initial_commands -> Ready; "RECONNECTED ... after 4 attempt(s)"
              8 von 8 Geraeten wieder Ready, keine Fehler im Dummy-Log

Beobachtet und bewusst so gelassen: bei TCP loggt die Factory bei jedem Reconnect-Versuch eine
`Failed connecting ...`-Zeile (alle 2 s); im Fehlerpfad wird der Pumpenstopp doppelt gesendet
(bekannt seit 08.10.); `Stopped` kann doppelt geloggt werden, wenn zwei Abschaltserien hintereinander
bestaetigt werden.

## 8. Noch zu testen am echten Netzteil (vor dem Testlauf 13.10.)

Backend auf dem Pi mit der echten `config.yml`, Netzteil ohne Zelle, Sollwert 2 V / 0,1 A.

1. **Geraet stumm** (Vorfall nachgestellt): kurzes Experiment mit `output_constant_current`
   (z.B. `kolbe_elektrolyse` mit `minutes: 3`, Pumpe/MFC duerfen trocken laufen oder man nimmt ein
   Testexperiment nur mit `psu`). Nach ~20 s das **Netzteil ausschalten** (Kippschalter; der CH340
   bleibt am USB, antwortet aber nicht - genau die Laborsituation). Erwartung im Log: `Retry` x3,
   `Error`, `Failed`, `sending URGENT command anyway ... [Command :01w12=0,,]`, 16x `Wrote :01w12=0,,`,
   `failed.`, `NOT confirmed - repeating device.stop() in 5.0 s`, alle 5 s `repeating ...`.
   Netzteil wieder einschalten -> beim naechsten Versuch `:01ok`, `changed to: Stopped`.
   **Am Geraet pruefen: Ausgang ist AUS** (`tools/lese_netzteil.py` oder Anzeige).
2. **Kabel ziehen**: gleiches Experiment, nach ~20 s **USB-Kabel des Kastens ziehen**. Erwartung:
   `CONNECTION LOST ... - device -> Error`, `Failed`, Pumpe/MFC abgeschaltet, `NO CONNECTION, cannot send`,
   `Reconnect attempt 1 ... failed` alle 2 s. Kabel wieder einstecken (gleiche Hub-Buchse! by-path):
   `RECONNECTED`, `Wrote :01w12=0,,`, `Ready`. **Am Geraet pruefen: Ausgang ist AUS.**
3. Danach Backend neu starten (Setup steht auf Failed).

Vorher pruefen: `ls -l /dev/serial/by-path/` muss den in `config.yml` eingetragenen Pfad
(`...usb-0:2.4.2:1.0-port0`) enthalten, sonst wird das Netzteil beim Start uebersprungen.

## 9. Was weiterhin offen ist (nicht Teil dieser Aenderung)

1. **Hardware-Interlock.** Friert der Pi ein, stuerzt das Backend ab oder bleibt das USB-Kabel draussen,
   bleibt das Netzteil im letzten Zustand (bis 48 V / 5 A), und keine Software kann das aendern. Fuer
   unbeaufsichtigte Elektrolysen (Wasserstoff!) ein Relais im Netzteil-Ausgang oder in der
   Netzzuleitung, das nur haelt, solange der Pi einen Herzschlag auf einem GPIO sendet
   (Watchdog-Monoflop). Die 16-Kanal-Relaisplatine ist schon da, ein Monoflop fehlt.
2. **Autostart/Neustart des Backends** (systemd, `Restart=always`). Ein Neustart schaltet ueber
   `initial_commands` das Netzteil aus - aber nur, wenn das Backend auch neu startet.
3. **Stopp-Reihenfolge**: `_stop_devices` stoppt in Reihenfolge der Experimentbefehle (MFC, Pumpe,
   Netzteil). Das gefaehrlichste Geraet zuerst.
4. **`finish_experiment` setzt alle Geraete sofort Ready**, waehrend ihre Abschaltserien noch laufen
   (daher der doppelte Pumpenstopp). Erst nach Bestaetigung Ready setzen.
5. **Frontend**: bei Failed deutlich warnen (rot, Geraetename, "AUS nicht bestaetigt").
6. **Plausibilitaet 48 V / 0 A**: Spannung an der Grenze und Strom ~0 ueber >30 s im Konstantstrom-
   betrieb = offener Stromkreis -> abschalten und melden (Vorfall 08.10., Ursache noch ungeklaert).
7. **Ein Geraet, das bei `initial_commands` nicht antwortet**, geht jetzt nach Error (vorher: haengt in
   NotReady). Experimente, die es benutzen, werden noch nicht uebersprungen (Setup prueft nur, ob das
   Geraet angelegt wurde, nicht seinen Zustand).
