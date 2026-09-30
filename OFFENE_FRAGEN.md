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



\## Longer WT600-2J — Adress-/Baudratensuche OFFEN, Geraet antwortet nicht

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
Naechster Schritt: am Geraet pruefen, ob Modbus ueberhaupt aktiviert ist (ab Werk AUS) und ob
ein RS485-Modul (Modul 485) verbaut ist; Adresse/Baudrate/Modus dort ablesen. Stufe 2 (Adressen
1-247) laeuft pro Adapter ~25 min und hilft nichts, solange Modbus aus ist.



\## Inficon Micro GC Fusion

\- Welche IP-Adresse hat das Gerät? (Im Screenshot war 169.254.1.1 zu sehen — das ist eine Selbstvergabe-Adresse, was auf Direktverbindung ohne DHCP hindeutet. Im Institutsnetz vermutlich eine andere.)
\- Wie ist das Peak-Tabellen-Schema im JSON eines echten Laufs aufgebaut? Ein Lauf ausgeben lassen und die Struktur mit der Annahme im Code vergleichen.
\- Welche Methoden sind auf dem Gerät hinterlegt, und wie lauten ihre Namen? (Für test_microgc_run als Parameter.)
\- Wie lange dauert ein BakeOut typischerweise? (Relevant für die Timeout-Einstellung.)


\## Relais / 3-2-Wegehaehne

\- Welcher GPIO-Pin schaltet welches Ventil? Zuordnungsliste erstellen.
\- Stimmt die Invertierung? An einem einzelnen Relais prüfen: Schaltet es bei off() tatsächlich durch?
\- Welche Stellung ist der sichere Grundzustand pro Ventil — also die Stellung, in die es bei Programmstart und -ende gehen soll?
\- Wie viele Kanäle werden tatsächlich benutzt von den sechzehn?
\- Braucht die Relaisplatine eine eigene 12-V-Versorgung, oder reicht der Pi?

