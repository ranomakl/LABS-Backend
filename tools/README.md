# Diagnosewerkzeuge fuer die Inbetriebnahme

Eigenstaendige Skripte zum Ausmessen von Geraeten, die noch nicht in `config.yml` eingetragen
werden koennen, weil Adresse oder Baudrate unbekannt sind. Sie laufen ohne Twisted und ohne
`Setup`, benutzen aber die Frame-Logik der echten Treiber, damit sie genau das Format testen,
das der Treiber spaeter spricht.

Aufruf immer aus der Repo-Wurzel, z.B.:

    .venv/bin/python tools/scan_pumpe.py --dry-run

## Sicherheit

Alle Pumpenskripte sind **reine Lesewerkzeuge**. Gesendet wird ausschliesslich die PDU `RJ`
("Read running parameter"; bis 06.10.2026 `RID`, das die WT600-2J aber NICHT beantwortet). Durchgesetzt wird das von `_guarded_write()` in `scan_pumpe.py` - dem
einzigen Pfad, ueber den geschrieben wird - mit drei Sperren, die vor jedem `write()` greifen:

1. PDU-Whitelist: nur `b"RJ"` und `b"RID"`
2. Adressbereich 1-30, Broadcast 31 gesperrt
3. Byte-Muster-Kontrolle am fertigen Frame auf `WJ` und `WID`

`WJ` ("Set running parameter") ist der einzige Befehl, der den Motor startet, `WID` ueberschreibt
die Geraeteadresse. Beide kommen in diesen Skripten nicht vor. Bei Verstoss wird `SafetyViolation`
geworfen, bevor etwas auf die Leitung geht. Die uebrigen Skripte importieren `_guarded_write()`
aus `scan_pumpe.py`, statt selbst zu schreiben - die Sperre gilt also fuer alle.

## Skripte

| Skript | Zweck |
|---|---|
| `scan_pumpe.py` | Hauptwerkzeug. RID ueber Adressen 1-30 bei 1200/9600/19200 Baud, Paritaet gerade und keine. `--dry-run` zeigt nur die Frames, `--port <pfad>` waehlt die Schnittstelle. |
| `schnelltest.py` | Verkuerzte Fassung (~40 s) fuer die Wiederholung nach einer Verkabelungsaenderung: nur 1200/E und 9600/E. |
| `scan_breit.py` | Breiterer Baudratenscan: 2400, 4800, 38400, 57600, 115200. |
| `dauersenden.py` | Sendet 25 s durchgehend RID, damit man die TXD/RXD-LEDs am Adapter beobachten kann. Trennt "Adapter sendet nicht" von "Gegenstelle antwortet nicht". |
| `probe_rts.py` | Testet beide RTS-Zustaende - manche RS485-Adapter schalten die Senderichtung darueber. |
| `probe_rts_toggle.py` | Wie `probe_rts.py`, aber RTS wird pro Frame umgeschaltet (gesetzt vor dem Senden, geloest nach dem letzten Bit) - der Betriebsfall fuer Adapter mit RTS-gesteuerter Sendefreigabe. |
| `mitlauscher.py` | Braucht einen ZWEITEN Adapter, parallel an dieselben Klemmen. Sendet auf dem einen, hoert auf dem anderen mit. Trennt "Adapter sendet nicht" von "Pumpe antwortet nicht" - die einzige Messung, die das rein in Software entscheidet. |
| `probe_echo.py` | Gibt alle empfangenen Rohbytes aus, auch das eigene Echo (das der Scanner sonst herausfiltert). Zeigt, ob ueberhaupt irgendetwas zurueckkommt. |
| `scan_alle_ports.py` | Fuehrt die Matrix aus `scan_pumpe.py` auf ALLEN seriellen Anschluessen aus, wenn unklar ist, an welchem Adapter die Pumpe haengt. Nutzt dessen `_guarded_write()`. |
| `scan_liquiline.py` | Endress+Hauser Liquiline CM44x: sendet ausschliesslich Modbus FC03 (Read Holding Registers, eigene Sperre `_guarded_write()` im Skript), ASCII und RTU, 1200-115200 Baud, Paritaet E/N/O, erst Adressen 1 und 247, dann 1-247. `--dry-run`, `--port <pfad>`, `--voll`. |
| `dauertest_liquiline.py` | Liquiline: sendet N Sekunden lang FC03 an EINE feste Einstellung (Standard ASCII 19200/E Adresse 247) und zaehlt Antworten und Rohbytes; `--passiv` lauscht nur. Fuer die Fehlersuche mit dem Techniker am Geraet. Schreibt nur ueber `_guarded_write()` aus `scan_liquiline.py`. |
| `lese_mfc.py` | Bronkhorst FLOW-BUS/ProPar: Typenschild (Seriennummer, Messbereich, Einheit, Fluid), Messwert, Sollwert, Zaehler lesen. Sendet ausschliesslich Lesebefehl 04 (Sperre `_guarded_write()`), probiert Knoten 1-10 oder `--node 03`. |

## Selbsttest

`scan_pumpe.py` rechnet beim Start die Frame- und XOR-Logik gegen alle fuenf Beispielframes aus
`docs/protokoll_pumpe.md` nach, bevor Hardware angefasst wird. Schlaegt das fehl, stimmt etwas am
Treiber nicht und der Scan bricht ab.
| `lese_netzteil.py` | Joy-IT DPM86xx Spannungsquelle: sendet ausschliesslich Lesebefehle (`:01rNN=0,,`, Sperre `_guarded_write()` im Skript) und zeigt Messwerte, Sollwerte und Ausgangszustand. Ohne `--port` listet es die seriellen Anschluesse auf, `--dry-run` zeigt nur die Frames. |
| `lese_microgc.py` | Inficon Micro GC Fusion ueber LAN: sendet ausschliesslich HTTP-GET auf Lese-Endpunkte (Status, Methodenliste, letzter Lauf; Whitelist in `_guarded_get()`, Pfade mit `!cmd.` sind gesperrt - kein BakeOut, kein Methodenstart). Zeigt die Peak-Tabelle des letzten Laufs als CSV, `--csv`/`--json` schreiben sie in Dateien. Standardadresse 169.254.1.1. |
| `starte_microgc_lauf.py` | **Steuert den microGC** (Gegenstueck zu `lese_microgc.py`): laedt eine Methode (Standard: `microGC_Standard_Method_calibrated_0726`, laut Labor die aktuelle), startet einen Lauf mit denselben Pfaden wie der Treiber, protokolliert jeden Statuswechsel mit Zeitstempel und speichert die neuen Laufdaten als JSON+CSV unter `logs/microgc_test/`. Ohne `--ja` nur Anzeige. Kein BakeOut. Verbraucht Traegergas - nur nach Freigabe. |

## Auswertung im Nachhinein: `auswertung.py`

Kein Diagnosewerkzeug, sondern liest die Versuchslogs `logs/<Jahr>/<Monat>/<Tag>/<Experiment-ID>/`
(`values.json` = alle Messwerte, `lauf.json` = Typ, Parameter, Einheiten, Start/Ende - wird vom Backend
seit 08.10.2026 geschrieben). Greift auf kein Geraet zu, nur Standardbibliothek.

    .venv/bin/python tools/auswertung.py --liste                      # alle Laeufe (Datum, Dauer, Typ, Observablen)
    .venv/bin/python tools/auswertung.py --html                       # BERICHT fuer den neuesten Lauf -> logs/.../<ID>/bericht.html
    .venv/bin/python tools/auswertung.py --html --tag 2026-10-08      # Tagesbericht, alle Laeufe des Tages in einer Datei
    .venv/bin/python tools/auswertung.py "<Experiment-ID>" --html ~/bericht.html --takt 600
    .venv/bin/python tools/auswertung.py                              # Terminal: Uebersicht + Tabelle alle 10 s
    .venv/bin/python tools/auswertung.py "<Experiment-ID>" --csv werte.csv --takt 600   # 10-Minuten-Tabelle als CSV

Der HTML-Bericht ist EINE Datei ohne Internet-Abhaengigkeiten (im Browser oeffnen, drucken, per Mail
verschicken): Kopf mit Typ/Parametern/Start/Ende/Dauer, Kennzahlen je Observable, eine Kurve je
Observable (Fadenkreuz beim Ueberfahren), Messwerttabelle im Raster `--takt` (Standard 10 s) und
zwei Knoepfe, die alle Rohwerte bzw. die Tabelle als CSV herunterladen.

Die Experiment-ID ist der Verzeichnisname unter logs/, so wie das Frontend ihn vergibt
(z.B. `test_0810-Polling test-3`), in Anfuehrungszeichen wegen der Leerzeichen.
