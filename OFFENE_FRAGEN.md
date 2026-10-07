\# Am Geraet zu pruefen



\## Bronkhorst FG-201CV — ERLEDIGT, am Geraet geprueft

Reiner Lesetest (nur Befehl 04) ueber /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BG01B77U-if00-port0,
ohne angeschlossenes Gas. Geraet antwortet auf alle Abfragen.

\- Baudrate: 38400 — bestaetigt. Bei 187500 antwortet das Geraet nicht.
\- Knotenadresse: "03" — bestaetigt (nicht 128).
\- Maximalfluss: 50.0 mL/min — Typenschild sagt 50 mln/min N2, und das Geraet meldet selbst
  Capacity100% (1/13) = 50 bei Capacity unit (1/31) = "mln/min", Fluid name (1/17) = "N2".
\- Seriennummer laut Geraet: M18212352B
\- Treiber-Frames READ_MEASURE (:06030401210120) und READ_COUNTER (:06030468416841) wurden vom
  Geraet beantwortet, beide Antwort-Regexes greifen. Counter stand bei 793.212.

\### Schreibtest — ERLEDIGT, am Geraet geprueft (ohne Gas, Geraet nur unter Strom)

Erster Schreibzugriff (Befehl 01) auf das Geraet, gleichzeitig Entschaerfung des unten
beschriebenen Sicherheitsproblems.

\- Setpoint vorher gelesen: :06030201217D00 -> 32000 raw = 100 % = 50 mL/min (bestaetigt den
  gefaehrlichen Ausgangszustand).
\- Geschrieben: :06030101210000 (Treiber-Frame aus SET_SETPOINT + cmd_string(), Wert aus
  _ml_min_to_raw(0) = 0).
\- Geraeteantwort: :0403000005 — echte Statusmeldung, Status-Byte 00 = kein Fehler. Der
  SET_SETPOINT-Parser des Treibers (Statusframe-Regex + expected_values status=00) greift.
\- Rueckkontrolle: Setpoint jetzt :06030201210000 -> 0 raw = 0 mL/min. Messwert ebenfalls 0.

\- Der gespeicherte Setpoint des Geraets stand auf 32000 = 100 % (= 50 mL/min), die Ventiloeffnung
  entsprechend am Anschlag (61,67 %, laut Handbuch der typische Maximalwert). Solange kein Gas
  anliegt, passiert nichts — sobald Gas aufgedreht wird, faehrt das Geraet aber sofort auf Vollausschlag.
  ERLEDIGT: Setpoint am Geraet auf 0 geschrieben (s. oben).
\- initial_commands() im Treiber war leer, setzte den Setpoint beim Start also NICHT zurueck; nur
  final_commands() rief stop_flow(). ERLEDIGT: initial_commands() ruft jetzt ebenfalls stop_flow().
  Begruendung: final_commands() greift nur beim sauberen Beenden — nach Absturz, Stromausfall oder
  gezogenem Kabel bleibt der alte Setpoint im Geraet stehen.



\## Longer WT600-2J — ERLEDIGT 06.10.2026, am Geraet geprueft

Aufloesung: Die Pumpe beantwortet den Lesebefehl RID ("Read pump address") NICHT. Alle Scans seit
August haben ausschliesslich RID gesendet und deshalb nie eine Antwort gesehen. Verkabelung,
Adapter und Werkseinstellungen waren die ganze Zeit in Ordnung.

\- Bestaetigt: 1200 Baud, 8E1, Adresse 1 (Werkseinstellung). Adapter BG02Q0XU (FTDI).
\- WJ (Start/Stop/Drehzahl) wird mit `E9 01 02 57 4A 1E` bestaetigt (das "geratene" Ack-Frame ist
  damit real: Adresse + PDU "WJ" + XOR). RJ antwortet mit `E9 01 06 52 4A <speed:2> <state1> <state2> <fcs>`,
  genau wie der Treiber annimmt.
\- WJ-Frames mit Drehzahl 0 ignoriert die Pumpe VOLLSTAENDIG (keine Antwort). Bereich 60-600 rpm.
  Treiber angepasst: Drehzahl nie unter 60, Stoppen nur ueber das Start/Stop-Bit (MIN_RPM).
\- Treiber backend/drivers/longer_wt600.py am Geraet verifiziert: Init (Stopp), read_speed,
  set_speed(100) + start_pumping (Kopf dreht, RJ meldet laeuft/100 rpm), stop_pumping. Mit
  tubing 3,2x6,4 mm / 0,8883 mL/U meldet er flow_ml_min = 88,83 bei 100 rpm.
\- tools/scan_pumpe.py und alle abgeleiteten Werkzeuge senden jetzt RJ statt RID; der Scan findet
  die Pumpe sofort (1200/E, Adresse 1). `--port <pfad>` funktioniert jetzt wirklich.
\- Zweite WT600-2J (Adapter BG01W2OJ): hat bei 1200/E Adresse 1 EINMAL auf WJ geantwortet und den
  Kopf gedreht, danach keine Antworten mehr -> Befehle kommen an, Antworten gehen verloren.
  Verdacht GND nicht angeklemmt. Fuer Stufe I nicht gebraucht.
\- Drehrichtung: Treiber-Default clockwise=True (State2 = 1) dreht den Kopf laut Nutzer IM UHRZEIGERSINN
  (06.10.2026 beobachtet). Offen: ob das in der Anlage zur Zelle foerdert - haengt von der Schlauchfuehrung
  ab, bei Einbau pruefen; sonst in continuous_flow() das Vorzeichen drehen.

\### Alte Befunde (ueberholt, Ursache s.o.)

\## Longer WT600-2J — Adress-/Baudratensuche (Stand bis 04.09.2026, ueberholt)

Stand 31.08.2026. Ziel war, Pumpenadresse und Baudrate per RID ("Read pump address") zu
ermitteln, weil kein Display zugaenglich ist. Werkzeug: tools/scan_pumpe.py (reines Lesewerkzeug,
sendet nur RID — Sperre siehe tools/README.md).

\### Ergebnis: keine einzige Antwort, kein einziges empfangenes Byte

Ausgeschlossen wurde (Adapter BG01XVQG an /dev/ttyUSB3, Pumpe eingeschaltet, RS485-Modul im
DB15 gesteckt, A/B + GND am Adapter angeklemmt):

\- Baudraten 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200 — je Paritaet gerade und keine
\- Adressen 1-30 (Broadcast 31 bewusst nicht angefragt)
\- beide RTS-Zustaende (manche RS485-Adapter schalten die Senderichtung darueber)
\- Rohbytes ohne Echo-Filter: 0 Byte empfangen, auch kein eigenes Echo

Insgesamt ueber 480 Frames, die Empfangsleitung hat nie ein Bit gesehen.

\### Was bestaetigt ist

\- Die Frame-/XOR-Logik des Treibers stimmt: der Selbsttest in tools/scan_pumpe.py rechnet alle
  fuenf Beispielframes aus docs/protokoll_pumpe.md byte-genau nach (5/5).
\- Der Adapter sendet tatsaechlich: beim Dauersenden (tools/dauersenden.py) blinkt die TXD-LED.
  ACHTUNG — die LED haengt am UART-Signal, also vor der Leitung. Sie beweist nicht, dass das
  Signal an der Pumpe ankommt; ein Kabelbruch saehe genauso aus.

\### Nachtest 04.09.2026 - unveraendert, zwei weitere Ursachen ausgeschlossen

Adapter BG01XVQG haengt jetzt an /dev/ttyUSB0 (vorher ttyUSB3); der by-id-Pfad in
tools/scan_pumpe.py stimmt weiterhin. Am Aufbau wurde nichts geaendert.

- tools/schnelltest.py (1200/E und 9600/E, Adressen 1-30): 0 Reaktionen.
- tools/probe_rts_toggle.py (NEU): RTS pro Frame umgeschaltet - gesetzt vor dem Senden, geloest
  nach dem letzten Bit -, beide Polaritaeten, 1200/E und 9600/E: 0 Reaktionen. Damit ist auch
  eine RTS-gesteuerte Sendefreigabe ausgeschlossen; probe_rts.py hatte nur statische Pegel
  geprueft, was bei so einem Adapter grundsaetzlich nie funktionieren wuerde.

Die Parametersuche ist damit erschoepft: 8 Baudraten x 2 Paritaeten x 30 Adressen x 3 RTS-Varianten,
kein einziges empfangenes Byte. Weiteres Scannen bringt nichts - der Fehler ist elektrisch.

### Naechste Schritte am Geraet

\- ZUERST: tools/mitlauscher.py (NEU) mit dem zweiten Adapter (BG01X3TF) parallel an dieselben
  Klemmen. Sendet auf dem einen, hoert auf dem anderen mit, und trennt damit "Adapter sendet
  nicht" von "Pumpe antwortet nicht" - das ist die Weggabelung, an der alle weiteren Schritte
  haengen. Die TXD-LED kann das nicht: sie sitzt vor dem Treiberbaustein.
  Aufruf: .venv/bin/python tools/mitlauscher.py --rx /dev/serial/by-id/<zweiter Adapter>
- A/B tauschen. Wahrscheinlichste Ursache. Die A/B-Beschriftung ist herstelleruebergreifend
  uneinheitlich — beide Seiten koennen "richtig" verkabelt und trotzdem zueinander verpolt sein.
  Man sieht es der Verkabelung nicht an, deshalb ist Tauschen der Standardtest.
\- Durchgang beider Datenadern zwischen Adapterklemme und RS485-Modul messen (Kabelbruch).
\- Klaeren, ob die Pumpe am Bedienfeld erst von lokaler Steuerung auf Fernsteuerung umgestellt
  werden muss. Der Blogpost sagt dazu nichts — dafuer braeuchten wir ein Herstellerhandbuch.

Nach jeder Aenderung: .venv/bin/python tools/schnelltest.py (~40 s)

\### Weiterhin offen

\- Ack-Frame beim Schreiben: geraten, Blogquelle zeigt es nicht
-> über LABS Backend lösen?

\- Pumpenadresse: 1 als Werkseinstellung angenommen, am Geraet NICHT bestaetigt (s.o.)

\- Schlauchfaktoren mL/Umdrehung: echte Werte fehlen
welche Schläuche  tatsächlich verwenden? Für jeden einen Faktor, ab in die config.yml

\- Baudrate 1200 / gerade Paritaet aus Blogquelle, am Geraet NICHT bestaetigt (s.o.)

\## Drifton-Pumpe (zweites Geraet) — unidentifiziert

Stand 31.08.2026. Adapter BG01X3TF an /dev/ttyUSB0. Drifton ist der europaeische Vertrieb fuer
Longer-Pumpen, die Geraete sind oft baugleiche Longer unter anderem Label — deshalb wurde
derselbe RID-Scan gefahren. Ergebnis ebenfalls: keine Antwort auf allen Kombinationen.

Offen, bevor es weitergehen kann:

\- Modellbezeichnung vom Typenschild. Danach richtet sich, ob das LONGER-Binaerprotokoll ueberhaupt
  passt — kleinere Modelle sprechen teils Modbus RTU, dann braucht es einen anderen Scan.
\- War die Pumpe beim Scan eingeschaltet und ueber RS485 mit dem Adapter verbunden? Nicht geprueft.

\## Endress+Hauser Liquiline CM442/CM448 
- Treiber spricht ASCII. Geraet muss auf ASCII stehen! Menu/Setup/General settings/Extended setup/Modbus/Transmission Mode 
- KORREKTUR 30.09.2026: Laut Handbuch SD01189C (Register 504 RS485_ENABLE) ist Modbus RS485 ab
  Werk EINGESCHALTET (Default 1 = On). Im Menue Setup/General settings/Extended setup/Modbus/Settings
  gibt es keinen "Enable"-Punkt, nur Adresse/Mode/Baudrate/Paritaet/Byte order/Watchdog.
- Busadresse: per DIP-Schalter oder Software, pruefen 
im Modbus Menü?
- Registeradressen der tatsaechlich angeschlossenen Sensoren pruefen
welcher sensor an welchen gerät hängt und welches register dazu gehört. auf gerät sehen welcher sensor erkannt wird?
Zuordnung zu Registern steht SD01189C Tabelle
Notieren, welche Sensoren an welchen Kanälen hängen (pH auf Kanal 1, Leitfähigkeit auf Kanal 2 etc.).
Die Registerzuordnung zuhause anhand der Tabelle.

Scan 30.09.2026 (tools/scan_liquiline.py, nur FC03, Stufe 1 = Adressen 1 und 247, ASCII+RTU,
1200-115200 Baud, Paritaet E/N/O) - Liquiline NICHT gefunden:
- BG02Q3TM (ttyUSB5, heute 11:59 eingesteckt, alle anderen 09:42 - wahrscheinlichster Kandidat):
  keinerlei Reaktion.
- BG01W2OJ (ttyUSB0) und CH341-Adapter 1a86 (ttyUSB4): keinerlei Reaktion.
- BG01B1W6 (ttyUSB1) und BG01B8RX (ttyUSB3): bei 38400 8N1 Antwort ":0104\r\n", unabhaengig
  von der gefragten Adresse -> das ist kein Modbus, sondern eine Bronkhorst-ProPar-ASCII-
  Fehlermeldung (38400 8N1 = Bronkhorst-Werkseinstellung). Dort haengen vermutlich weitere
  Bronkhorst-Geraete, nicht der Liquiline. Zusaetzlich einmal Datenmuell bei 57600/E (Fehlrahmen).
- BG01B77U (MFC laut config.yml) wurde bewusst nicht gescannt.
- BESTAETIGT 30.09.2026 12:24 durch Abstecken: Der Liquiline haengt am Adapter BG02Q3TM
  (/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BG02Q3TM-if00-port0). Er antwortet dort nicht,
  also liegt das Problem am Geraet (Modbus aus?) oder an der Verkabelung, nicht am Anschluss.
- Danach am Geraet auf ASCII umgestellt, Adresse 247 abgelesen, Baudrate/Paritaet laut Nutzer
  passend -> erneuter Scan auf BG02Q3TM: weiterhin KEINE Reaktion. Verdacht: Verkabelung
  (Handbuch Abschn. 2.1: bei Problemen A/B tauschen, schadet nicht) - LEDs am Modul 485 pruefen.
- LEDs am Modul 485: nur EINE LED leuchtet, ROT (vom Nutzer als PWR abgelesen; laut Handbuch ist
  PWR nur gruen definiert, rot nur BF/SF), alle anderen aus, COM blinkt nicht. Messwerte am Display
  sind vorhanden -> Messung ok, Problem liegt bei Modul 485 / Kabel / Adapter.
- 12:40 A/B getauscht, erneuter Scan auf BG02Q3TM: weiterhin KEINE Reaktion.
- Hardware-Adressschalter am Modul 485 hat laut Handbuch Vorrang vor der Menue-Adresse. Deshalb
  ASCII 19200/E ueber ALLE Adressen 1-247 gescannt: keine Reaktion. Eine abweichende
  DIP-Adresse erklaert das Schweigen also nicht (sofern das Geraet wirklich auf 19200/E steht).
- ~12:50 Liquiline neu gestartet, erneuter Scan (Stufe 1, alle Modi/Baud/Paritaet): weiterhin
  KEINE Reaktion. Verdacht bleibt Modul 485 (rote LED) -> Diagnoseliste pruefen, ggf. E+H-Service.
- Diagnoseliste: nur F100 "Sensor Kommunikation CH2" (Memosens-Sensor an Kanal 2 antwortet nicht,
  eigenes Problem). KEIN S969 Modbus Watchdog, obwohl Watchdog = 5 s und Modbus aktiviert.
- Bestellcode CM448-AA36A11AABAA+AB (nicht dekodiert -> E+H Device Viewer/Service). Klemmen 95/96/99
  an Modul 485 und Menue (nur Modbus, kein PROFIBUS) laut Nutzer korrekt.
- ~13:20 Terminierung am Modul eingeschaltet, Adapter unveraendert BG02Q3TM: keine Reaktion.
  Adapter-LED TXD blinkt rot beim Scan -> Adapter sendet; RXD blinkt nicht -> nichts kommt zurueck.
  Offen: ob die Anfragen am Modul ankommen (COM-LED beobachten) und Adapter gegen einen
  nachweislich funktionierenden (BG01B1W6/BG01B8RX) tauschen.
- 13:26 Dauertest: 186 FC03-Anfragen (ASCII, 19200/E, Adresse 247) in 40 s, 0 Antworten.
  Nutzer beobachtet dabei: am Modul leuchtet GAR NICHTS (weder COM noch T, obwohl Terminierung an),
  nur TXD am Adapter blinkt. -> Modul 485 zeigt kein Lebenszeichen (nicht versorgt / nicht
  richtig gesteckt / defekt / Kabel an falschem Modul). Naechster Schritt: Modul pruefen, E+H-Service.
- Danach am Modul: PWR gruen, T gelb (Modul laeuft, Terminierung aktiv). Dauertests 13:28/13:30 und
  voller Stufe-1-Scan: 0 Antworten, COM blinkt NICHT.
- GND (Klemme C) war nicht angeschlossen -> angeklemmt, Neustart. Dauertests 13:33 und 13:35 (je
  278 Anfragen) + voller Scan: 0 Antworten. Am Modul jetzt SF (Systemfehler) rot.
- SF kam vom fehlenden Sensor an Kanal 2 (F100); nach Anschluss des Sensors SF aus, Modul PWR gruen,
  T gelb. 14:34 Dauertest + Scan auf BG02Q3TM: 0 Antworten.
- 14:38 RS485-Adapter getauscht gegen neuen BG01XFU4 (ttyUSB5). 14:39 Dauertest (186 Anfragen) +
  voller Stufe-1-Scan: 0 Antworten. Adapter BG02Q3TM als alleinige Ursache damit unwahrscheinlich.
- Modul laut Beschriftung "Modbus RS485" (= 485MB, richtig). Klemmen laut KA01159C 5.4.2:
  95 = B (Data+), 96 = A (Data-), 99 = C (DGND), 81/82 nur externe Terminierung. Adapter "USB TO RS485"
  mit GND/A+/B-. 14:53 am Adapter A/B getauscht -> seitdem kommt nach JEDER Anfrage genau ein
  Byte 00 zurueck, ~50 ms nach dem Senden, bei ALLEN Baudraten/Paritaeten/Modi, in Ruhe nichts.
  Deutung: kein Geraete-Antwortrahmen, sondern die Leitung kippt nach dem Freigeben durch den
  Adapter in den Ruhezustand "0" (Break) -> der Vorspann der Modul-Terminierung kommt am Adapter an
  (Leitung ist also elektrisch verbunden), aber mit dieser Polung verkehrt herum. Die Polung vor dem
  Tausch war demnach die richtige; auch damit kam keine Antwort.
- 15:00 A/B zurueckgetauscht (Adapter neu eingesteckt). 15:01 Dauertest (139 Anfragen) + voller
  Stufe-1-Scan: 0 Reaktionen, auch die 00-Bytes sind wieder weg (bestaetigt die Deutung oben).
  STAND: Hardwareseite weitgehend ausgeschlossen, COM am Modul blinkt nie. Naechster Schritt:
  E+H-Service (Seriennr., Bestellcode CM448-AA36A11AABAA+AB) - welcher Feldbus ist aktiv
  (RS485 vs. TCP/Ethernet), ist Modbus RS485 freigeschaltet?
- 07.10.2026 ~14:45, vor dem Telefonat mit E+H: Liquiline eingeschaltet, Adapter BG01XFU4 am
  Hub (/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BG01XFU4-if00-port0, heute ttyUSB3).
  tools/scan_liquiline.py Stufe 1 komplett + Stufe 2 ASCII 19200 E/N ueber alle 247 Adressen:
  0 Reaktionen. tools/dauertest_liquiline.py (NEU): passiv 8 s = 0 Byte (keine Stoerung auf der
  Leitung); ASCII 19200/E Adr 247: 139 Anfragen, 0 Byte; RTU 19200/E Adr 247: 97 Anfragen,
  0 Byte; ASCII 19200/E Adr 1: 70 Anfragen, 0 Byte. Befund identisch zum 30.09. Der namenlose
  CH340 am Hub (heute ttyUSB2) wurde vorsichtshalber ebenfalls gescannt: 0 Reaktionen.
  Zusammenfassung fuer den E+H-Service: docs/liquiline_telefonat_eh.txt.
- ACHTUNG 07.10.2026: Der USB-Hub steckt seit 14:35 in einer anderen Pi-Buchse (xhci-hcd.1 statt
  hcd.0). Der by-path des Netzteils in config.yml (platform-xhci-hcd.0-usb-0:2.1:1.0-port0) ist
  damit falsch, bis der Hub zurueckgesteckt oder der Pfad angepasst ist.
Naechster Schritt: am Geraet pruefen, ob Modbus ueberhaupt aktiviert ist (ab Werk AUS) und ob
ein RS485-Modul (Modul 485) verbaut ist; Adresse/Baudrate/Modus dort ablesen. Stufe 2 (Adressen
1-247) laeuft pro Adapter ~25 min und hilft nichts, solange Modbus aus ist.



\## Spannungsquelle Joy-IT DPM86xx ("DC SOURCE 48V") — ERLEDIGT, am Geraet geprueft 06.10.2026

Grauer Kasten ohne Display, Aufschrift "DC SOURCE 48V", Netzanschluss, USB-Kabel zum Pi, zwei
Ausgangskabel zur Zelle. Der USB-Seriell-Wandler (CH340, 1a86, ohne Seriennummer) sitzt im Kasten.
In config.yml stand faelschlich tdk_lambda_zplus.

\- 05.10. und 06.10. vormittags: keine Antwort auf irgendein Protokoll (DPM simple, Modbus RTU, SCPI,
  99 Adressen, 7 Baudraten, passiv). Ursache: der Kasten war AUS. Der Pi sieht den CH340 trotzdem,
  weil USB ihn versorgt - /dev/ttyUSB0 ist also KEIN Lebenszeichen des Geraets.
\- Eingeschaltet: tools/lese_netzteil.py 9/9 Antworten bei 9600 8N1, Adresse 01, Frame ":01r30=0,,\n"
  (zwei Kommas + LF, wie in Matthias' Code). Geraet meldet max 60 V / 5 A -> 5-A-Modell (DPM8605-Klasse),
  nicht 50 A wie ein DPM8650. Sollwerte vorgefunden: 5 V / 3 A, Ausgang aus, Modus 1 (Konstantstrom), 21 Grad.
\- Treiber backend/drivers/joyit_dpm86.py am Geraet verifiziert: initial_commands (Ausgang aus),
  measure_output, set_voltage(5.0) + Rueckkontrolle, stop().
\- Ausgang ein/aus mit Freigabe getestet (ohne Zelle): 1 V / 0,1 A gesetzt, eingeschaltet -> Ausgang 1,
  gemessen 1,0 V / 0,0 A, Modus 0 (Konstantspannung, da keine Last); stop_current() -> Ausgang 0, 0 V.
  Sollwerte im Geraet stehen jetzt auf 1 V / 0,1 A.
\- Grenzen laut Labor: 48 V (config.yml voltage_limit), Strom wird je Versuch eingetragen.
\- Offen: welches Modell steckt genau im Kasten (Typenschild innen)? Nur fuer die Doku, nicht fuer den Betrieb.
\- 07.10.2026: Es gibt DREI graue Kaesten. Der erste (06.10. verifiziert, Sollwerte 1 V / 0,1 A hinterlassen) wurde
  abgesteckt; seit 16:05 haengt ein zweiter an Hub-Buchse 2.4.2 (config.yml angepasst): max 60 V / 5 A,
  Adresse 01, 9600 Baud, Ausgang aus, Sollwerte 5 V / 3 A, 25 Grad. Ein dritter Wandler an Buchse 2.4.4
  antwortet nicht (Kasten vermutlich aus). Der dritte Kasten ist nicht per USB am Pi.

\## Inficon Micro GC Fusion

\### ERLEDIGT, am Geraet geprueft (06.10.2026, Pi per LAN direkt am microGC)

\- Netz: der microGC hat KEINEN DHCP-Server. Er zeigt am Display "automatic IP address" 169.254.1.1 (Link-Local/Selbstvergabe). Die in OFFENE_FRAGEN_teilsbeantwirtet.txt genannte 10.10.0.1 antwortet nicht (Ping/HTTP ohne Antwort). eth0 des Pi wartete auf DHCP und bekam nichts; Profil "Wired connection 1" im NetworkManager umgestellt auf ipv4.method link-local und ipv4.never-default yes (ohne sudo moeglich). Pi bekam 169.254.230.104, Ping 0,2 ms, HTTP 200. WLAN (ufz-m2m) bleibt parallel die Standardroute, SSH/Internet laufen weiter.
\- Alle Lese-Endpunkte des Treibers antworten mit HTTP 200 und erwartetem JSON: Status `["public:sequence-not-loaded","public:standby"]`, /v1/lastRun `{"dataLocation":"/runData/<uuid>"}`, Laufdaten (~250 kB), /v1/methods/userMethods (18 Methoden). Wurzel `/` antwortet 200 (Verbindungstest des Treibers). `/v1/methods` ohne `userMethods` liefert nginx 500 - nicht benutzen.
\- Peak-Tabellen-Schema: `detectors[<modul>:tcd].analysis.peaks[]` mit area/height/top/start/end/snr/tailing/baselinePoints, bei kalibrierten Peaks zusaetzlich label/concentration/normalizedConcentration, bei Gruppen inGroup/isGroup. Stimmt mit der Annahme in run_data_to_csv() ueberein - geprueft an testdata_microgc(1).fusion-data (25 benannte Peaks) und am letzten Lauf des Geraets vom 29.07.2026. Modul D hat nur unbenannte Peaks und faellt korrekt heraus. Weitere Felder im Lauf: methodName, runTimeStamp, frontInletTotalConcentration, annotations, softwareVersion.
\- Treiberfehler behoben: dataLocation enthaelt bereits "/runData/", der Treiber stellte es nochmal voran (Geraet tolerierte das). Jetzt run_data_path().
\- Methoden: microGC_Standard_Method_calibrated_0726 ist vorhanden und laut Labor (06.10.2026) die aktuelle, zu verwendende Methode. microGC_Standard_Method_calibrated_11_25 liegt ebenfalls auf dem Geraet, wird nicht benutzt. Name bleibt Experimentparameter (test_microgc_run).
\- BakeOut-Dauer 20 min laut Labor. Kein Timeout im Code noetig: _wait_until_ready() pollt den Status bis "ready", der 10-s-Timeout in config.yml gilt je Statusabfrage, nicht fuer den ganzen Vorgang.
\- Lesewerkzeug tools/lese_microgc.py (nur GET auf Lesepfade, Steuerbefehle gesperrt).
\- ECHTER LAUF 06.10.2026 15:05 (tools/starte_microgc_lauf.py, Methode ..._0726, Freigabe durch Rafael): loadMethod -> HTTP 200 mit `{"$public.currentMethodLocation": ".../microGC_Standard_Method_calibrated_0726"}`, run -> HTTP 200 `{"runWhenReady":"true"}`. Statusfolge: standby -> preparing (27 s) -> method-running (~5 min) -> loading-method -> preparing (~2 min) -> **ready**. Gesamt 454 s. Neue dataLocation, Laufdaten 525 kB abgeholt, CSV korrekt (Probe war Luft: O2/N2 ca. 21/78 % normiert, Rest 0). Das Geraet kehrt nach "public:ready" zurueck - genau der Zustand, auf den der Treiber wartet. Damit sind loadMethod, run, Statuspolling und Datenabholung komplett am Geraet bestaetigt.
\- Geraeteuhr geht ca. 11 min nach (runTimeStamp 12:54:23Z bei tatsaechlichem Start 13:05:43Z). Fuer die Zuordnung Lauf <-> Experiment nicht die Geraetezeit, sondern die dataLocation/UUID verwenden (macht der Treiber so).

\### Offen

\- BakeOut wurde nicht ausgeloest und muss laut Rafael (06.10.2026) auch nicht getestet werden. Pfad stammt aus dem Referenzcode, gleiches Muster wie loadMethod/run.
\- Treiber im Backend-Verbund (Setup, Experiment test_microgc_run) noch nicht gegen das echte Geraet gefahren - bisher nur die HTTP-Ebene mit identischen Pfaden ueber tools/. Sobald die uebrigen Geraete in config.yml echt sind, test_microgc_status und test_microgc_run einmal ueber das Backend laufen lassen.
\- Bleibt 169.254.1.1 nach Neustart des microGC stabil? Link-Local-Adressen koennen sich aendern. Beim naechsten Einschalten am Display kontrollieren; falls instabil, am Geraet eine feste Adresse vergeben und config.yml anpassen.


\## Relais / 3-2-Wegehaehne

\- Welcher GPIO-Pin schaltet welches Ventil? Zuordnungsliste erstellen.
\- Stimmt die Invertierung? An einem einzelnen Relais prüfen: Schaltet es bei off() tatsächlich durch?
\- Welche Stellung ist der sichere Grundzustand pro Ventil — also die Stellung, in die es bei Programmstart und -ende gehen soll?
\- Wie viele Kanäle werden tatsächlich benutzt von den sechzehn?
\- Braucht die Relaisplatine eine eigene 12-V-Versorgung, oder reicht der Pi?

