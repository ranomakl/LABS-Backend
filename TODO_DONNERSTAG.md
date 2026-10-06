# Bis zum Labortest am Donnerstag, 08.10.2026

Stand 06.10.2026. Grundlage: ANFORDERUNGEN.txt und OFFENE_FRAGEN_teilsbeantwirtet.txt (auf origin/main),
Code und config.yml auf dem Branch `netzteil-joyit`.

Gebraucht wird je EIN Geraet pro Typ. Nicht fuer Donnerstag: zweiter Bronkhorst-MFC (BG01B1W6),
zweite Pumpe Longer BT100-1F (erst Stufe II), Liquiline (pausiert bis Antwort von E+H).

WICHTIG: config.yml ist noch die Dummy-Konfiguration. Ausser MFC und Netzteil zeigen alle Geraete
auf 127.0.0.1 (LABS-DeviceDummys).

## Code (ohne Geraete machbar)

### Spannungsquelle Joy-IT DPM8650
- [x] Treiber backend/drivers/joyit_dpm86.py nach Matthias' Protokoll (9600 8N1, `:01r30=0,,`),
      ohne tkinter/Threads. Gegen simuliertes Geraet (pty) getestet, am echten Geraet NOCH NICHT.
- [x] Gemeinsame Schnittstelle in psu_base.py: set_voltage, set_current, set_output, measure_output,
      output_constant_current/-voltage, stop_current. TDK-Treiber angepasst.
- [x] config.yml: psu auf joyit_dpm86 umgestellt (by-path-Adresse am Donnerstag pruefen).
- [x] Lesewerkzeug tools/lese_netzteil.py (nur Lesebefehle).
- [x] base.py: by-path-Adressen mit Doppelpunkt wurden als IP:Port zerlegt - behoben.
- [ ] voltage_limit / current_limit in config.yml auf die Werte des Versuchs setzen (stehen auf
      Geraetemaximum 60 V / 50 A).
- [ ] Keithley 2230-30-1 Treiber auf derselben Schnittstelle (spaeter, Vorlage von Matthias liegt vor).
- [ ] Optional: externer Sensor ueber Spannungseingang (Anforderung, noch nicht beruecksichtigt).

### Pumpe Longer WT600-2J
- [ ] config.yml: echten Adapter BG01XVQG statt 127.0.0.1 eintragen.
- [ ] Schlauch 3,2 x 6,4 mm mit 0,8883 mL/Umdrehung eintragen (steht noch Platzhalter LS16: 0.5;
      ANFORDERUNGEN.txt hakt das faelschlich als erledigt ab).

### MFC Bronkhorst
- [ ] Counter zuruecksetzen ergaenzen (gefordert, bisher nur read_counter).
- [ ] Startreihenfolge-Bug: MFC beim Backend-Start aus -> Init schlaegt fehl, Backend laeuft trotzdem
      weiter, spaeter AlreadyCalledError in backend/commands/commandstate.py:36. Banner
      "***** BHT MBC3C ..." beim Einschalten erkennen und Setpoint erneut auf 0 setzen.

### Relais / 3-2-Wegehaehne
- [ ] config.yml: je ein Eintrag fuer GPIO 17, 27, 22, 5, 6, 13, 19, 26; simulate: true entfernen;
      safe_state = aus fuer alle.
- [ ] Belegungsliste Ventil -> Relaiskanal -> GPIO als Vorschlag fuer das Labor.
- [ ] /boot/firmware/config.txt: gpio=17,27,22,5,6,13,19,26=op,dh (aendert den Pi, braucht Neustart -
      nur nach Freigabe).

### microGC (optional)
- [ ] config.yml: Adresse 10.10.0.1, Methode microGC_Standard_Method_calibrated_0726 als Parameter,
      Timeout fuer BakeOut > 20 min.
- [ ] Beispieldaten testdata_microgc.fusion-data mit der JSON->CSV-Annahme im Code vergleichen
      (Datei liegt noch nicht im Repo - wo ist sie?).

### Aufraeumen
- [ ] Dateien von origin/main (ANFORDERUNGEN.txt, OFFENE_FRAGEN_teilsbeantwirtet.txt, download.zip mit
      Matthias' Code) in den Arbeitsbranch holen.
- [ ] Befunde vom 05.10. in OFFENE_FRAGEN eintragen (zweiter MFC M18212352C, Netzteil ist Joy-IT,
      Startreihenfolge-Bug, Adapterstand).

## Labor (Verkabelung, vor Donnerstag)

- [ ] Netzteil: Leistungseingang mit Strom versorgen; GND Netzteil mit GND RS485-Adapter verbinden;
      "simple protocol" eingestellt (Werkseinstellung).
- [ ] Pumpe: beide Pumpen-Adapter (BG01XVQG, BG01X3TF) einstecken; am Bedienfeld pruefen, ob
      Fernsteuerung eingeschaltet werden muss; zweiten Adapter parallel fuer tools/mitlauscher.py.
- [ ] Relais: 12-V-Versorgung, Platine an die vorgeschlagenen GPIO-Pins.
- [ ] microGC: LAN-Kabel Pi <-> microGC.

## Reihenfolge am Donnerstag

1. MFC (Kontrolle, laeuft bereits)
2. Netzteil: zuerst `.venv/bin/python tools/lese_netzteil.py` (listet Ports), dann mit `--port ...`
3. Pumpe: tools/mitlauscher.py, dann tools/schnelltest.py
4. Relais
5. microGC
