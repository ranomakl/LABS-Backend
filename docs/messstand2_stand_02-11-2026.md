# Messstand II - Stand 02.11.2026 (Einrichtung neuer Pi, Ventil, Pumpe)

Ergaenzung zu docs/pi_einrichtung_checkliste.md und docs/neuer_pi_tipps_02-11-2026.txt.
Pi: Raspberry-PI-MP-001, Benutzer pohlma, Debian 13 (trixie), Python 3.13.5.

## 1. Pi-Einrichtung (erledigt)

- Gruppen dialout/gpio/i2c/spi, Pakete (git, python3-venv, python3-lgpio, lxterminal, curl, firefox): vorhanden.
- GitHub: gh-CLI ohne sudo nach ~/.local/bin/gh (Release-Tarball, Pruefsumme geprueft), `gh auth login`
  als ranomakl, `gh auth setup-git` (git nutzt den gh-Login, kein Token in Dateien).
  Git-Identitaet: ranomakl / 320973586+ranomakl@users.noreply.github.com.
  Falle: `gh` war im bereits offenen Terminal nicht im PATH, weil ~/.local/bin beim Login noch nicht
  existierte (~/.profile nimmt es nur auf, wenn es existiert) -> voller Pfad oder neu anmelden.
- Backend-venv: 102 Tests gruen (101 ok, 1 skip). Unter Python 3.13 fehlten zwei Pakete, beide jetzt in
  requirements.txt: legacy-cgi (Twisted 22.10 importiert cgi) und setuptools<81 (pkg_resources fuer
  `python -m twisted.trial`).
- Frontend-venv: `pip install -r requirements.txt` (requirements.txt ist UTF-16, pip kommt damit klar;
  torch/botorch sind gross). Erster Versuch brach mit Netzwerkfehler ab, zweiter mit
  `--resume-retries 20 --timeout 60` lief durch. `flask db upgrade` -> database-devel.sqlite3 (gitignored).
  Admin-Konto wird beim ersten App-Start angelegt (Passwort einmalig auf der Konsole). Passwort vergessen:
  Passwort per Python im App-Kontext neu setzen (User.query.filter_by(username="admin"), u.password = ...,
  db.session.commit()). `flask shell -c` gibt es NICHT.
- Station im Frontend: Name frei, Adresse 127.0.0.1:11123, Location frei, API-Key beliebig (Backend prueft
  ihn nicht).
- Konfig pro Pi: station.conf im Backend-Ordner (gitignored) mit `CONFIG=config.messstand2.yml`;
  tools/labs_start.sh liest sie. Ohne station.conf laedt es config.yml (Messstand I unveraendert).
- labs_start.sh oeffnet Firefox, falls installiert, sonst Chromium.
- Desktop-Symbole "LABS starten"/"LABS beenden" nach ~/Desktop kopiert, ausfuehrbar, gio trusted.

## 2. Netzwerk fuer das Ventil (eth0)

- Ventil haengt per LAN direkt an eth0. Ohne DHCP-Server bekam weder Pi noch Ventil eine IPv4-Adresse.
- Loesung: `nmcli con mod "Wired connection 1" ipv4.method shared` -> Pi hat 10.42.0.1/24 auf eth0 und
  verteilt per DHCP. Ventil bekam 10.42.0.103 (MAC 00:15:e2:00:78:e2, Knauer). WLAN unberuehrt.
  Zuruecksetzen: `nmcli con mod "Wired connection 1" ipv4.method auto`.
- Falle: Direkt nach dem Einschalten hat das Ventil noch keinen Port offen (Ping geht schon). Einige
  Minuten warten. Ein Scan ueber das ganze 169.254.0.0/16 erzeugt im Kernel-Log "neighbor table
  overflow" (harmlos).

## 3. Ventil Knauer AZURA VU 4.1 (valve1) - funktioniert

- IDENTIFY: `7,Knauer,VU4.1,FVH263200018,6.26.000.0000,16,16`
- VALVE: Kopf SN FWM263200013, Typ EVS63CE, 16 Positionen, 16 Ports.
- Adresse 10.42.0.103:10001 (Port 10001 = Knauer-Werkseinstellung; die alten Ventile liefen auf 10123).
- Treiber knauer_azura_vu_4_1 passt unveraendert. Getestet direkt (POSITION:2, zurueck auf 1) und ueber
  LABS (Routine test_valve1_position, Position 3 angefahren und bestaetigt).
- Verhalten des Treibers: faehrt beim Backend-Start UND am Ende jedes Experiments auf Position 1
  (initial_commands/final_commands). Soll das Ventil zwischen Schritten stehen bleiben, muss das angepasst
  werden - offen, haengt vom Versuchsablauf ab.

## 4. Pumpe Longer BT100-1F (Haendler Drifton) - Verbindung steht, Protokoll noch offen

- Typenschild: Baoding Longer Precision Pump, Model BT100-1F(-B), SN 202606090001. Fotos:
  docs/photo_2026-11-02_14-39-*.jpg.
- Rueckseite: RS485-Modul (Klemme "RS485 A B GND", Draehte gelb/rot/gruen), daneben DB9 (nicht benutzt).
- Adapter: FTDI FT232R, SN BG01X3TF, ueber LogiLink-Hub:
  `/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BG01X3TF-if00-port0`
- Am Geraet: Menue ueber Druck auf den Drehknopf. Pfad laut Handbuch:
  System Setting -> Control Mode -> Ext Cont. ON -> Address. Am 02.11. auf ON gestellt, Adresse 1.
- Falle: Die Klemmen am RS485-Modul waren locker (GND fiel fast heraus). Erst nach Festziehen kam eine
  Antwort.
- Ergebnisse (1200 Baud, 8E1, Adresse 1, Longer-Frame E9 adr len PDU xor):
  - `RID` -> Antwort `E9 01 03 52 49 44 5D` (zuverlaessig, auch schon vor Ext Cont. ON).
  - `RJ` (WT600-Lesen), `DL`/`RL` (BT100-1L-Lesen): keine Antwort.
  - Stopp-Befehle `XL` (BT100-1L, Drehzahl 0, Stop: E9 01 06 58 4C 00 00 00 01 12) und `WJ` (WT600,
    E9 01 06 57 4A 00 00 00 01 1B): keine Antwort. Pumpe blieb aus.
  - Modbus RTU (fc 3/4, Adresse 1-16, 1200-115200 Baud, N/E): keine Antwort.
- Schluss: Physik und Frameformat stimmen (RID wird beantwortet), die Betriebsbefehle der BT100-1F sind
  andere oder brauchen eine weitere Einstellung. Das Handbuch nennt das Protokoll nicht und verweist an
  Longer (longer@longerpump.com) - beim Haendler Drifton/Longer das RS485-Protokoll der BT100-1F anfragen.
- Quellen: BT100-1F-Handbuch (manualshive.com, manuals.online), Darwin Microfluidics: RS485-Protokoll
  BT100-2J(3J) (PDF) und Blog "How to control the Longer BT100-1L pump via Python" (XL/DL/WL/RL/CL).
- Noch kein Treiber und kein Eintrag in config.messstand2.yml.

## 5. Naechste Schritte

1. BT100-1F-Protokoll von Longer/Drifton besorgen, nach docs/ legen. Dann Treiber (Vorbild longer_wt600.py,
   Frame-Funktionen wiederverwenden) + Leseskript unter tools/ + Test mit Pruefvektoren.
2. Klaeren, ob valve1 zwischen Versuchsschritten seine Position halten soll (Treiber faehrt sonst auf 1).
3. Weitere Geraete von Messstand II in config.messstand2.yml eintragen.
