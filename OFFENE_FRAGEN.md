\# Am Geraet zu pruefen



\## Bronkhorst FG-201CV

\- Baudrate: 38400 angenommen, ungeprueft

\- Knotenadresse: 3 aus Handbuchbeispiel, real evtl. 128

\- Maximalfluss in mL/min: vom Typenschild ablesen



\## Longer WT600-2J

\- Ack-Frame beim Schreiben: geraten, Blogquelle zeigt es nicht

\- Pumpenadresse: 1 als Werkseinstellung angenommen

\- Schlauchfaktoren mL/Umdrehung: echte Werte fehlen

\- Baudrate 1200 / gerade Paritaet aus Blogquelle

## Endress+Hauser Liquiline CM442/CM448 - Treiber spricht ASCII. Geraet muss auf ASCII stehen! Menu/Setup/General settings/Extended setup/Modbus/Transmission Mode - Modbus ist ab Werk AUSGESCHALTET. Unter "Enable" einschalten - Busadresse: per DIP-Schalter oder Software, pruefen - Registeradressen der tatsaechlich angeschlossenen Sensoren pruefen



\## Inficon Micro GC Fusion

\- Peak-Tabellen-Schema in run\_data\_to\_csv() ist Annahme

&#x20; -> echten Lauf ausgeben lassen, JSON-Struktur vergleichen

\- IP-Adresse pruefen (169.254.1.1 aus Kollegen-Screenshot?)

\- Race Condition bei sehr schnellen Laeufen dokumentiert



\## Relais / 3-2-Wegehaehne

\- Signal ist INVERTIERT: relais.off() = Strom fliesst = Ventil schaltet

\- gpiozero, DigitalOutputDevice, Pin 17 im Beispiel

\- Nur am Pi testbar

