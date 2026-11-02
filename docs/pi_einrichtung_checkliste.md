# Neuen Pi / neuen Messstand mit LABS einrichten (Checkliste, Stand 02.11.2026)

Fuer den zweiten Messstand mit eigenem Raspberry Pi. Ziel: derselbe Code wie am Messstand I
(alle drei Repos), aber eine eigene Konfiguration. Was hier steht, ist am Messstand I (Pi 5,
Linux 6.12, Python 3.13) so gemacht und erprobt worden; Pfade beziehen sich auf
/home/<benutzer>/LABS/.

Grundsatz: **Code ist stationsunabhaengig, config.yml ist stationsspezifisch.** Fixes, Treiber,
Schrittmodus, Fehlerpfad, Frontend-Monitoring gelten fuer alle Messstaende. Pro Messstand gibt es
nur eine eigene Konfigdatei und eigene Routinen darin. Kein Fork, keine zweite Codebasis.

## 1. Pi vorbereiten

1. Raspberry Pi OS (64 bit, Desktop) installieren, Benutzer anlegen, LAN/WLAN einrichten.
2. Benutzer in die Gruppen fuer serielle Adapter und GPIO:
   `sudo usermod -aG dialout,gpio,i2c,spi <benutzer>` (danach ab- und anmelden).
3. Pakete: `sudo apt install git python3-venv python3-lgpio lxterminal curl`.
   python3-lgpio nur, wenn Relais/GPIO-Ventile gebraucht werden (Pi 5 braucht lgpio als Pin-Factory
   fuer gpiozero; pip-Build braucht swig, deshalb das Systempaket).
4. Browser: Chromium haengt auf dem Pi von Messstand I bei jeder http-Seite ("Loading"). Firefox
   installieren und benutzen (`sudo apt install firefox`), tools/labs_start.sh entsprechend anpassen.

## 2. Repos klonen (GitHub-Nutzer ranomakl)

```
mkdir -p ~/LABS && cd ~/LABS
git clone https://github.com/ranomakl/LABS-Backend.git
git clone https://github.com/ranomakl/LABS-User-Interface.git
git clone https://github.com/ranomakl/LABS-DeviceDummys.git
```

Fuer Push braucht der Pi einen GitHub-Zugang (SSH-Key oder Token). Ohne reicht Pull.

## 3. Backend einrichten

```
cd ~/LABS/LABS-Backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Nur bei GPIO-Relais (Pi 5): lgpio aus dem Systempaket ins venv holen, wie am 27.10.2026:

```
ln -s /usr/lib/python3/dist-packages/lgpio.py .venv/lib/python3.*/site-packages/
ln -s /usr/lib/python3/dist-packages/_lgpio*.so .venv/lib/python3.*/site-packages/
```

Tests laufen ohne Hardware und muessen gruen sein (Stand 02.11.: 102 Tests):

```
.venv/bin/python -m twisted.trial backend.test
```

## 4. Konfiguration fuer den neuen Messstand

main.py laedt ohne Argument config.yml, mit Argument eine beliebige Datei
(`python main.py config.messstand2.yml`). Empfehlung: eigene Datei `config.messstand2.yml`
anlegen und in tools/labs_start.sh eintragen, damit config.yml von Messstand I unangetastet bleibt
und beide Konfigurationen im selben Repo liegen.

Aufbau der Datei (siehe CLAUDE.md und config.yml als Vorlage):

- Kopf: `listen port: 11123`, `destination port`, `log_level`, `step_mode: true` (Schrittmodus,
  nach jedem Schritt anhalten; am Messstand I seit 16.10.2026 an).
- `devices:` pro Geraet `driver` (Modulname unter backend/drivers/), `address`, Treiber-Parameter.
  `enabled: false` schaltet ein Geraet ab, ohne es zu loeschen; Routinen, die es brauchen, werden
  beim Start mit Warnung uebersprungen.
- `experiments:` erst die Geraetetests (test_...), dann die Versuchsschritte. Routinen aus
  config.yml, die auf gleichen Geraetetypen beruhen, koennen kopiert werden (Uebersicht:
  docs/routinen_uebersicht.md). Die kolbe_-Routinen sind auf Messstand I zugeschnitten und werden
  fuer den neuen Aufbau neu zusammengestellt.

Wichtig fuer das Frontend: eine einmal geladene Routine wird nicht aktualisiert. Geaenderte
Routinen bekommen deshalb einen neuen Namen (Beispiel _gc, _2k, _3x).

### Serielle Adapter adressieren

- FTDI-Adapter haben eine Seriennummer und werden ueber `/dev/serial/by-id/usb-FTDI_..._<SN>-if00-port0`
  angesprochen. Sie duerfen den USB-Steckplatz wechseln. Auslesen mit `ls -l /dev/serial/by-id/`.
- Adapter OHNE eindeutige Seriennummer (z.B. die Joy-IT-Netzteile, CH340 "1a86_USB_Serial") sind
  per by-id mehrdeutig und werden ueber den USB-Steckplatz angesprochen:
  `/dev/serial/by-path/platform-xhci-hcd.1-usb-0:<buchse>:1.0-port0`. Diese Geraete muessen immer
  in derselben Buchse stecken; Buchse am Hub beschriften. Pfad auslesen mit `ls -l /dev/serial/by-path/`.
- Wer welches Geraet ist: ein Adapter nach dem anderen stecken und schauen, welcher Eintrag
  dazukommt. Danach in der Konfig als Kommentar notieren (Seriennummer, Etikett, Geraet).
- Baudraten am Messstand I: Bronkhorst 38400 (nicht 187500), Liquiline Modbus RTU 19200/E/1,
  Busadresse 247. Neue Geraete: Handbuch, dann mit den Skripten unter tools/ probieren.

### GPIO-Relais (nur falls gebraucht)

Treiber raspi_gpio_relay_valve, `address: "GPIO17"` usw., `release_when_off: true` (Pin loslassen
= Relais aus). Relaisplatine an ihre eigenen 5 V, NICHT an die 3,3 V des Pi (Pi-5-Absturz am
28.10.2026). Am Header nur stromlos stecken. Hintergrund:
docs/relaisplatine_absturz_und_softwareloesung_28-10-2026.txt.

## 5. Neue Geraete (Treiber schreiben)

Fuer Geraete, die es am Messstand I nicht gibt:

1. Erst mit einem eigenstaendigen Skript unter tools/ (ohne Twisted) sprechen lernen: Adresse,
   Baudrate, Frame-Format, ein Lesebefehl. Vorbild: tools/scan_pumpe.py (nur lesend, mit Sperren),
   tools/lese_netzteil.py, tools/dauertest_liquiline.py. Beschreibung in tools/README.md.
2. Treiber unter backend/drivers/<hersteller_modell>.py auf der passenden Basisklasse:
   psu_base, mfc_base, pump_base, transmitter_base (Messwertgeber wie Liquiline), gc_base,
   two_way_valve_base / multipos_valve_base, thermostat_base. Vorbilder nach Schnittstelle:
   - serielles ASCII-Protokoll: joyit_dpm86.py, longer_wt600.py
   - Modbus RTU: endress_hauser_liquiline.py (CRC, Frame-Laenge, Parser mit Pruefvektoren)
   - Bronkhorst Propar: bronkhorst_mfc.py
   - HTTP/REST ueber LAN: inficon_microgc_fusion.py
3. Dummy unter LABS-DeviceDummys/<gleicher_name>.py auf base.py, eigener TCP-Port, in main.py
   eintragen. Damit laeuft die Routine am Laptop ohne Geraet (docs/daheim_entwickeln_ohne_pi.md).
4. Test unter backend/test/test_<geraet>.py mit Pruefvektoren vom echten Geraet (Vorbild:
   test_liquiline_rtu.py). Aufruf: `.venv/bin/python -m twisted.trial backend.test`.
5. Fehlerpfad beachten: Geraete, die etwas einschalten (Netzteil, Pumpe, Ventil), muessen beim
   Verbindungsverlust und beim Experimentende sicher ausschalten (docs/fehlerpfad_nachbesserung_12-10-2026.md,
   docs/test_fehlerpfad_dummys.md).

## 6. Frontend einrichten

```
cd ~/LABS/LABS-User-Interface
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/flask db upgrade
.venv/bin/flask run --host=0.0.0.0
```

Beim ersten Start wird ein Admin-Konto angelegt, Zugangsdaten stehen in der Konsole. Dann im Frontend
unter Administration eine Station mit Adresse `127.0.0.1:11123` anlegen und unter Routines
"Download Experiments from Station" klicken. Designs sind pro Benutzer.

## 7. Starten, Stoppen, Desktop-Symbole

- tools/labs_start.sh: git pull, Backend (Log logs/backend_stdout.log), Frontend (Port 5000),
  Geraetestatus-Fenster (tools/geraete_fenster.py), Browser. Pfade (BACKEND, FRONTEND), die
  Konfigdatei und den Browser fuer den neuen Pi anpassen.
- tools/labs_stop.sh: /api/shutdown (Netzteile aus, Ventile in Ruhelage), dann Prozesse ueber ihre
  Ports beenden. Warnt, wenn ein Experiment laeuft.
- Desktop-Symbole: tools/"LABS starten.desktop" und "LABS beenden.desktop" nach ~/Desktop kopieren,
  Pfad in `Exec=` anpassen, ausfuehrbar machen.
- Pruefen, ob alles laeuft: `curl -s http://127.0.0.1:11123/api/station_overview` und
  `curl -s -o /dev/null -w '%{http_code}' http://localhost:5000`.

## 8. Inbetriebnahme-Reihenfolge am Geraet

Ein Geraet nach dem anderen, erst lesen, dann schalten:

1. Alle Geraete einschalten, DANN Backend starten (Geraete, die beim Start aus sind, fehlen samt
   ihren Routinen bis zum naechsten Backend-Start).
2. Backend-Log auf Warnungen pruefen: `grep -iE "nicht verfuegbar|uebersprungen|Could not|Error" logs/backend_stdout.log`.
3. Pro Geraet eine Leseroutine (Zaehler lesen, pH lesen, Status abfragen).
4. Pro Geraet eine Schaltroutine mit kurzer Laufzeit und Stop-Routine (test_psu_output /
   stop_psu_output, test_wt600_speed / stop_wt600, test_ventil_z1 mit minutes).
5. Zuordnung pruefen: welches Netzteil, welcher MFC, welche Pumpe gehoert zu welcher Zelle/Leitung
   (am Messstand I ueber N2-Fluss und Sollwert gemacht, docs/testplan_27-10-2026.txt).
6. Erst dann einen kompletten Versuchsschritt mit kleinen Werten (minutes 1).

## 9. Fallen, die am Messstand I Zeit gekostet haben

- `pkill -f`/`pgrep -f` mit einem Muster, das im eigenen Befehl vorkommt, beendet die eigene Shell
  (Exit 144). Stattdessen `ps aux | grep "[g]eraete_fenster.py"` oder Prozesse ueber Ports (labs_stop.sh).
- tools/labs_start.sh nie in eine Pipe haengen (Kindprozesse halten stdout). Start mit
  `setsid nohup bash tools/labs_start.sh &` und per curl pruefen.
- Ein laufendes Experiment nie ohne Auftrag stoppen oder starten. Lesen (API, Logs, Geraete) ist
  immer erlaubt.
- Beim Pull am Pi zuerst `git status` ansehen (lokale Aenderungen aus dem Labor), erst dann
  `git pull --ff-only`. Backend danach neu starten, sonst laeuft der alte Code.
- Nach jedem Backend-Neustart im Frontend "Download Experiments from Station", sonst fehlen neue
  Routinen und Parameter.
- Bronkhorst-Zaehler: Einheit am Geraet pruefen (20er-MFC meldet uln/min, docs/testplan_27-10-2026.txt).
- Screenshots auf Wayland mit grim, nicht mit scrot.

## 10. Wo was steht

- Geraete-Befunde Messstand I (Adressen, Adapter, was geprueft ist): OFFENE_FRAGEN.md
- Versuchsablauf im Labor fuer die Laboranten: docs/ablauf_versuch_im_labor.md
- Routinen-Uebersicht: docs/routinen_uebersicht.md
- Entwickeln ohne Pi: docs/daheim_entwickeln_ohne_pi.md
- Architektur fuer Claude/Entwickler: CLAUDE.md
- Werkzeuge: tools/README.md
