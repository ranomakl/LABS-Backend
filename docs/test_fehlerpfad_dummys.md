# Test des Fehlerpfads mit den Dummys (nach Vorfall 08.10.2026)

Prueft die vier Korrekturen aus Commit f9f7c43 (siehe docs/vorfall_08-10-2026_netzteil_blieb_an.txt):

1. Ein einzelner Timeout fuehrt NICHT zu Error (Retry, bis zu 3 Wiederholungen).
2. Nach endgueltigem Fehler werden die Abschaltbefehle (final_commands) TROTZDEM gesendet,
   auch an das Geraet im Error-Zustand.
3. Messwerte (values.json, lauf.json) und Bericht werden beim Abbruch IMMER geschrieben.
4. Nach einem Fehler sind Stop und Shutdown am Backend moeglich.

Laeuft komplett ohne Laborgeraete am Laptop (Windows oder Linux). Dauer ca. 20 min.

## Vorbereitung (einmalig)

    cd LABS-DeviceDummys && git pull        # STUMM-Schalter + neue Bronkhorst-Befehle (Commit 9793d0d)
    cd ../LABS-Backend     && git pull        # Korrekturen + diese Anleitung
    copy config.dummy.yml config.yml          # Windows   (Linux: cp) - NICHT committen

Drei Fenster:

| Fenster | Befehl | Zweck |
|---|---|---|
| A | `cd LABS-DeviceDummys` dann `python main.py` | Dummys, loggt jede Anfrage/Antwort |
| B | `cd LABS-Backend` dann `python main.py` | Backend, loggt Zustaende |
| C | `cd LABS-Backend` | Befehle per curl (unten) und STUMM-Datei anlegen/loeschen |

Frontend ist fuer den Test nicht noetig; alles geht ueber die HTTP-API des Backends mit curl
(Windows: curl ist in PowerShell vorhanden; Anfuehrungszeichen wie angegeben).

Der STUMM-Schalter: Liegt im Ordner LABS-DeviceDummys eine Datei namens `STUMM` (Inhalt egal),
antworten die Dummys nicht mehr, nehmen aber weiter Befehle an (= haengendes Geraet, Verbindung
bleibt). Datei loeschen = Geraet antwortet wieder. `STUMM_bronkhorst_mfc` stummt nur den MFC-Dummy.

    Windows (PowerShell):  New-Item -Path ..\LABS-DeviceDummys\STUMM_bronkhorst_mfc -ItemType File
                           Remove-Item ..\LABS-DeviceDummys\STUMM_bronkhorst_mfc
    Linux:                 touch ../LABS-DeviceDummys/STUMM_bronkhorst_mfc
                           rm ../LABS-DeviceDummys/STUMM_bronkhorst_mfc

## Test 1: Einzelner Timeout -> Retry, KEIN Fehler

Ziel: Korrektur 1. Ein kurz stummes Geraet wirft das Experiment nicht raus.

1. Fenster B: Backend starten, warten bis `State of Device changed to: Ready` fuer mfc (und die
   anderen Dummys) und `changed to: Paused`.
2. Fenster C:
       curl "http://127.0.0.1:11123/api/add_experiment?experiment_id=t1&experiment_type=test_fehlerpfad_mfc&minutes=2"
       curl "http://127.0.0.1:11123/api/start"
   Fenster B zeigt jetzt jede Sekunde READ_MEASURE/READ_COUNTER an den MFC.
3. Nach ca. 20 s: STUMM_bronkhorst_mfc anlegen, **4 Sekunden warten** (ein Timeout = 2,5 s,
   die Datei darf nur EINEN Timeout lang liegen), dann Datei loeschen.
4. Erwartung in Fenster B:
   - genau eine Zeile `changed to: Retry` fuer einen READ-Befehl (Retry = Korrektur 1 greift),
     danach `Success` - KEIN `changed to: Error`, KEIN `Experiment ... changed to: Failed`.
   - Das Polling laeuft weiter, nach 2 min endet das Experiment normal (`Finished`),
     im Ordner logs/<J>/<M>/<T>/t1/ liegen values.json, lauf.json, bericht.html.
   - lauf.json: `"final_state": "Finished"`.
5. FALLS stattdessen `Error`/`Failed` kommt: Datei lag laenger als 3 Timeouts (10 s) - Test
   wiederholen (experiment_id t1b), schneller loeschen. Kommt Error schon beim ERSTEN Timeout:
   Korrektur 1 greift nicht -> Fehler in backend/commands/commands.py (on_timeout) melden.

## Test 2: Geraet bleibt stumm -> Error, Abschaltbefehl wird trotzdem gesendet, Daten gerettet

Ziel: Korrekturen 2, 3, 4. Das ist der Vorfall von 13:58 nachgestellt.

1. Fenster C:
       curl "http://127.0.0.1:11123/api/add_experiment?experiment_id=t2&experiment_type=test_fehlerpfad_mfc_pumpe&minutes=3"
       curl "http://127.0.0.1:11123/api/start"
   Jetzt laufen MFC-Polling UND der Pumpen-Dummy (Drehzahl-Polling, RJ).
2. Nach ca. 30 s: STUMM_bronkhorst_mfc anlegen und LIEGEN LASSEN.
3. Erwartung in Fenster B innerhalb von ~15 s:
   - fuer einen READ-Befehl nacheinander `Retry`, `Retry`, `Retry`, dann `Fail`
     (3 Wiederholungen = 4 Versuche, ca. 10 s),
   - `[Bronkhorst ...] State of Device changed to: Error`,
   - `Experiment ... changed to: Failed`,
   - `[Longer WT600 ...] Wrote E9 01 06 57 4A 00 .. 00 01 ..` = Pumpen-STOPP wird gesendet und
     vom Pumpen-Dummy beantwortet (`Received E9 01 02 57 4A 1E`), Pumpe -> `Stopped`,
   - `[Bronkhorst ...] Error state: sending URGENT command anyway (shutdown path)` und danach
     `Wrote :06030101217D00` (= open_valve, Ventil auf) - DAS ist Korrektur 2. Der Befehl bekommt
     keine Antwort (Dummy stumm) und scheitert nach den Retries - das ist in Ordnung, er wurde
     gesendet.
   - KEINE Zeile `Cannot send commands in Error state!` (das war der Fehler von 13:58).
   - `Bericht wird erzeugt` und im Ordner logs/.../t2/ liegen values.json, lauf.json
     (`"final_state": "Failed"`), bericht.html - Korrektur 3.
   - Setup: `curl "http://127.0.0.1:11123/api/station_overview"` zeigt `"status": "Failed"`.
4. STUMM-Datei loeschen (Dummy antwortet wieder).
5. Fenster C:  curl "http://127.0.0.1:11123/api/stop"   -> Erwartung: HTTP 200, `null`,
   Fenster B: Setup `changed to: Stopped`, KEIN `SetupStateError: Setup is in failed state`
   - Korrektur 4. (Pumpe bekommt nochmal Stopp, MFC nochmal open_valve - jetzt beantwortet.)
6. Backend in Fenster B mit Strg+C beenden, neu starten (der MFC bleibt sonst im Error-Zustand).

## Test 3 (optional): Geraet antwortet WIEDER, waehrend es im Error-Zustand ist

Das war die genaue Situation am 08.10.: Netzteil hing kurz, war dann wieder da, der
Abschaltbefehl wurde trotzdem nie gesendet.

1. Wie Test 2, aber in Schritt 4 die STUMM-Datei bereits 1-2 s nach `changed to: Error`
   loeschen (also BEVOR die Retries des Abschaltbefehls aufgebraucht sind).
2. Erwartung: `Wrote :06030101217D00` (open_valve) wird nun beantwortet (`Received :0403000005`),
   `[Bronkhorst ...] State of Device changed to: Stopped`. Das Geraet wurde also trotz
   Fehlerzustand sauber abgeschaltet - das ist der Kern der Korrektur.

## Was melden

Bitte aus Fenster B die Zeilen ab dem Anlegen der STUMM-Datei kopieren (ca. 40 Zeilen) und
den Inhalt von logs/.../t2/lauf.json. Bei Abweichung von der Erwartung: welche Zeile fehlt
oder welche kommt zusaetzlich. Erst wenn Test 1 und 2 wie erwartet laufen, wird am Pi
neu gestartet und mit dem echten Netzteil (ohne Zelle, 2 V, Kabel kurz ziehen) wiederholt.

## Ergebnis 08.10.2026 (Windows-PC, Dummys)

| Test | Stand f9f7c43 | nach Nachkorrekturen e)-g) |
|---|---|---|
| 1 Einzel-Timeout | bestanden | bestanden |
| 2 Geraet stumm | NICHT bestanden: Serie leer, Pumpe lief weiter, Setup Busy | bestanden (alle Erwartungen inkl. Schritt 5) |
| 3 Geraet wieder da | - | bestanden (Ventil-auf beim 1. Retry beantwortet, MFC Stopped) |

Die drei Nachkorrekturen (CollectingCommands im Error-Zustand, Geraete einzeln stoppen, Failed
meldet sich beim Setup) sind in docs/vorfall_08-10-2026_netzteil_blieb_an.txt Abschnitt 6
beschrieben. Erwartung in Test 2 Schritt 3 ergaenzt: die URGENT-Zeile muss den Befehl enthalten
(`CommandSeries [Command :06030101217D00]`), nicht `CommandSeries []`.

Hinweis zum Ablauf: Nach Test 2 Schritt 5 zeigt station_overview `running_experiment_name: ""`,
der Stop geht deshalb ueber den Pfad "alle Geraete stoppen" - das ist in Ordnung.
