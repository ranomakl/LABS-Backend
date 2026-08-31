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

\### OFFEN, sicherheitsrelevant

\- Der gespeicherte Setpoint des Geraets steht auf 32000 = 100 % (= 50 mL/min), die Ventiloeffnung
  entsprechend am Anschlag (61,67 %, laut Handbuch der typische Maximalwert). Solange kein Gas
  anliegt, passiert nichts — sobald Gas aufgedreht wird, faehrt das Geraet aber sofort auf Vollausschlag.
  Vor dem ersten Gasbetrieb Setpoint auf 0 schreiben (entspricht Device.stop_flow()).
\- initial_commands() im Treiber ist leer, setzt den Setpoint beim Start also NICHT zurueck; nur
  final_commands() ruft stop_flow(). Ueberlegen, ob der Start ebenfalls auf 0 fahren soll.



\## Longer WT600-2J

\- Ack-Frame beim Schreiben: geraten, Blogquelle zeigt es nicht
-> über LABS Backend lösen?

\- Pumpenadresse: 1 als Werkseinstellung angenommen

Display? , Werkseinstellung 1 (?)

\- Schlauchfaktoren mL/Umdrehung: echte Werte fehlen
welche Schläuche  tatsächlich verwenden? Für jeden einen Faktor, ab in die config.yml

\- Baudrate 1200 / gerade Paritaet aus Blogquelle

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

