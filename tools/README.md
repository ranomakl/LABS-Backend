# Diagnosewerkzeuge fuer die Inbetriebnahme

Eigenstaendige Skripte zum Ausmessen von Geraeten, die noch nicht in `config.yml` eingetragen
werden koennen, weil Adresse oder Baudrate unbekannt sind. Sie laufen ohne Twisted und ohne
`Setup`, benutzen aber die Frame-Logik der echten Treiber, damit sie genau das Format testen,
das der Treiber spaeter spricht.

Aufruf immer aus der Repo-Wurzel, z.B.:

    .venv/bin/python tools/scan_pumpe.py --dry-run

## Sicherheit

Alle Pumpenskripte sind **reine Lesewerkzeuge**. Gesendet wird ausschliesslich die PDU `RID`
("Read pump address"). Durchgesetzt wird das von `_guarded_write()` in `scan_pumpe.py` - dem
einzigen Pfad, ueber den geschrieben wird - mit drei Sperren, die vor jedem `write()` greifen:

1. PDU-Whitelist: nur `b"RID"`
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
| `probe_echo.py` | Gibt alle empfangenen Rohbytes aus, auch das eigene Echo (das der Scanner sonst herausfiltert). Zeigt, ob ueberhaupt irgendetwas zurueckkommt. |

## Selbsttest

`scan_pumpe.py` rechnet beim Start die Frame- und XOR-Logik gegen alle fuenf Beispielframes aus
`docs/protokoll_pumpe.md` nach, bevor Hardware angefasst wird. Schlaegt das fehl, stimmt etwas am
Treiber nicht und der Scan bricht ab.
