\# Am Geraet zu pruefen



\## Bronkhorst FG-201CV

\- Baudrate: 38400 angenommen, ungeprueft (Zeichen pro Sek. auf serieller Leitung)
nachgucken ob Gerät/Treiber gleiche haben. (DIP Schalter am Gerät selbst, Kalibrierzertifikat oder 
Brokhorstsoftware)



\- Knotenadresse: 3 aus Handbuchbeispiel, real evtl. 128 (RS485 können mehrere Geräte an einer Leitung)
auf typschild, über brokhorst software, kalibrierungszertifikat

\- Maximalfluss in mL/min: vom Typenschild ablesen



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

