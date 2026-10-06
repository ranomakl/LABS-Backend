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
      ohne tkinter/Threads. 06.10. AM GERAET VERIFIZIERT: Init (Ausgang aus), Messen, Sollwert schreiben
      und zuruecklesen, stop(). Ausgang EIN/AUS ebenfalls getestet (1 V / 0,1 A ohne Last: Ausgang an,
      1,0 V gemessen, danach aus, 0 V).
- [x] Gemeinsame Schnittstelle in psu_base.py: set_voltage, set_current, set_output, measure_output,
      output_constant_current/-voltage, stop_current. TDK-Treiber angepasst.
- [x] config.yml: psu auf joyit_dpm86 umgestellt, by-path-Adresse eingetragen (Kasten immer in denselben USB-Port).
- [x] Lesewerkzeug tools/lese_netzteil.py (nur Lesebefehle).
- [x] base.py: by-path-Adressen mit Doppelpunkt wurden als IP:Port zerlegt - behoben.
- [x] voltage_limit 48 V (Vorgabe Labor), current_limit 5 A (Geraetemaximum); Strom je Versuch als
      Experimentparameter.
- [ ] Keithley 2230-30-1 Treiber auf derselben Schnittstelle (spaeter, Vorlage von Matthias liegt vor).
- [ ] Optional: externer Sensor ueber Spannungseingang (Anforderung, noch nicht beruecksichtigt).

### Pumpe Longer WT600-2J — LAEUFT (06.10.2026 am Geraet verifiziert)
- [x] config.yml: Adapter BG02Q0XU, Adresse 1, 1200/8E1, Schlauch 3,2x6,4 mm = 0,8883 mL/U.
- [x] Ursache fuer "keine Antwort" seit August: Pumpe beantwortet RID nicht. Scanner auf RJ umgestellt.
- [x] Treiber: Drehzahl 0 wird von der Pumpe ignoriert -> MIN_RPM 60, Stopp ueber Start/Stop-Bit.
- [~] Drehrichtung: clockwise=True = im Uhrzeigersinn (beobachtet). Ob das zur Zelle foerdert, beim Einbau pruefen.
- [ ] Zweite Pumpe (BG01W2OJ) antwortet nur sporadisch - GND am Adapter pruefen. Nicht fuer Stufe I.

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

### microGC — LAEUFT (06.10.2026 am Geraet verifiziert inkl. echtem Lauf)
- [x] Geraet hat keinen DHCP-Server, sondern Link-Local 169.254.1.1 (nicht 10.10.0.1). eth0-Profil
      "Wired connection 1" auf link-local + never-default gestellt; config.yml: address 169.254.1.1.
- [x] Methode bleibt Parameter von test_microgc_run (microGC_Standard_Method_calibrated_0726 ist auf dem
      Geraet; ..._11_25 liegt auch dort, laut Labor 06.10. gilt aber die 0726). Kein BakeOut-Timeout noetig, Treiber pollt bis "ready".
- [x] Beispieldaten testdata_microgc(1).fusion-data UND letzter Lauf vom Geraet gegen run_data_to_csv()
      geprueft: Struktur stimmt, CSV korrekt. Laufdaten-URL im Treiber korrigiert (run_data_path()).
- [x] Lesewerkzeug tools/lese_microgc.py (Status, Methodenliste, letzter Lauf als CSV).
- [x] 06.10. 15:05 echter Lauf mit ..._0726 (tools/starte_microgc_lauf.py): loadMethod/run HTTP 200,
      454 s, Rueckkehr nach "public:ready" = Treiber passt. Neue Laufdaten als CSV korrekt.
- [ ] Donnerstag: test_microgc_status / test_microgc_run einmal ueber das Backend (Setup) fahren, sobald
      die anderen Geraete echt sind. BakeOut weiterhin ungetestet (20 min).
- [ ] Nach Neustart des microGC kontrollieren, ob die Adresse 169.254.1.1 gleich bleibt.

### Aufraeumen
- [ ] Dateien von origin/main (ANFORDERUNGEN.txt, OFFENE_FRAGEN_teilsbeantwirtet.txt, download.zip mit
      Matthias' Code) in den Arbeitsbranch holen.
- [ ] Befunde vom 05.10. in OFFENE_FRAGEN eintragen (zweiter MFC M18212352C, Netzteil ist Joy-IT,
      Startreihenfolge-Bug, Adapterstand).

## Labor (Verkabelung, vor Donnerstag)

- [x] Netzteil: antwortet, sobald der graue Kasten eingeschaltet ist. Kein RS485-Adapter, USB direkt.
- [x] Pumpe: laeuft an Adapter BG02Q0XU, keine Einstellung am Geraet noetig.
- [ ] Relais: 12-V-Versorgung, Platine an die vorgeschlagenen GPIO-Pins.
- [x] microGC: LAN-Kabel Pi <-> microGC steckt, Geraet antwortet (06.10.2026).

## Reihenfolge am Donnerstag

1. MFC (Kontrolle, laeuft bereits)
2. Netzteil: zuerst `.venv/bin/python tools/lese_netzteil.py` (listet Ports), dann mit `--port ...`
3. Pumpe: tools/scan_pumpe.py --port <BG02Q0XU> (Kontrolle, ~1 min)
4. Relais
5. microGC: `.venv/bin/python tools/lese_microgc.py` (Kontrolle, nur lesend), dann erster Lauf nach Freigabe
