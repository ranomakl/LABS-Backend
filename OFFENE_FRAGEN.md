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

\### Naechste Schritte am Geraet

\- A/B tauschen. Wahrscheinlichste Ursache. Die A/B-Beschriftung ist herstelleruebergreifend
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
- Modbus ist ab Werk AUSGESCHALTET. Unter "Enable" einschalten 
- Busadresse: per DIP-Schalter oder Software, pruefen 
im Modbus Menü?
- Registeradressen der tatsaechlich angeschlossenen Sensoren pruefen
welcher sensor an welchen gerät hängt und welches register dazu gehört. auf gerät sehen welcher sensor erkannt wird?
Zuordnung zu Registern steht SD01189C Tabelle
Notieren, welche Sensoren an welchen Kanälen hängen (pH auf Kanal 1, Leitfähigkeit auf Kanal 2 etc.).
Die Registerzuordnung zuhause anhand der Tabelle.



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

