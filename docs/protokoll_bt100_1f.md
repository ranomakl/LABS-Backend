# Longer BT100-1F - RS485-Protokoll (Kurzfassung)

Quelle: `docs/BT100-1F-RS485-Protocol.pdf` ("LONGER RS485 Protocol for BT100-1F", Herstellerdokument,
am 04.11.2026 ueber Drifton/Longer erhalten). Bedienhandbuch: `docs/BT100-1F-Operating-Manual.pdf`
(enthaelt das Protokoll NICHT). Treiber: `backend/drivers/longer_bt100_1f.py`,
Tests: `backend/test/test_longer_bt100_1f.py`, Lesetest: `tools/lese_bt100_1f.py`.

## Schnittstelle

- 1200 Baud, 8 Datenbits, gerade Paritaet, 1 Stoppbit (8E1). Keine Baudrateneinstellung am Geraet.
- Am Geraet: System Setting -> Ext Cont. ON, Address 1-30 (ab Werk 1). Beides am 02.11.2026 gesetzt.
- Verdrahtung am RS485-Klemmenmodul: A, B, GND (Klemmen festziehen - 02.11. war GND lose).
  DB15 alternativ: Pin 2 = B, Pin 3 = A.
- Adresse 31 = Broadcast: alle Pumpen fuehren aus, keine antwortet.

## Frame

```
E9  ADR  LEN  PDU...  FCS
```

- `E9` Start-Flag. `ADR` Pumpenadresse. `LEN` = Anzahl PDU-Bytes (vor dem Stuffing).
- `FCS` = XOR ueber ADR, LEN und PDU (ungestufft).
- **Byte-Stuffing** nach dem Flag: `E8` -> `E8 00`, `E9` -> `E8 01`. Beim Empfang zurueckwandeln.
  Beispiel a (unten): LEN = 0E, auf dem Draht aber 15 PDU-Bytes, weil `03 E8` als `03 E8 00` geht.
- Mehrbyte-Werte big-endian (hoechstes Byte zuerst).
- Befehlskuerzel sind ASCII (B 42, C 43, D 44, F 46, I 49, R 52, S 53, T 54, W 57).

## Befehle (PDU)

| Befehl | Anfrage-PDU | Antwort-PDU | Bedeutung |
|---|---|---|---|
| WF | `WF` Fluss(4) State1(1) | `WF` Fluss(4) | Flussrate-Modus: Fluss in nL/min setzen + Start/Stop/Richtung |
| RF | `RF` | `RF` Fluss(4) State1(1) | Flussrate-Modus lesen |
| WD | `WD` Vol(4) Kopien(2) Fluss(4) Pause(2) | `WD` | Dosierparameter: Vol in 0,01 mL (1-999000), Kopien 0-9999 (0 = endlos), Fluss nL/min, Pause 0,1 s (0-59940) |
| RD | `RD` | `RD` Vol(4) Kopien(2) Fluss(4) Pause(2) | Dosierparameter lesen |
| WSD | `WSD` State1(1) | `WSD` | Dosier-Modus Start/Stop |
| RSD | `RSD` | `RSD` State1(1) | Dosier-Modus Zustand lesen |
| WT | `WT` Kopf(1) Schlauch(1) | `WT` | Pumpenkopf/Schlauch setzen |
| RT | `RT` | `RT` Kopf(1) Schlauch(1) | Pumpenkopf/Schlauch lesen |
| WB | `WB` Zeit(2) | `WB` | Ruecksaugzeit in 0,1 s (0-999) |
| RB | `RB` | `RB` Zeit(2) | Ruecksaugzeit lesen |
| WID | `WID` Neu(1) | `WID` | Adresse setzen (auch per Broadcast, einzeln anschliessen) |
| RID | `RID` | `RID` | Adresse lesen (Antwort traegt die Adresse im ADR-Byte) |

State1: Bit 0 Start (1) / Stop (0), Bit 1 cw (1) / ccw (0), Bit 2 Prime (volle 100 rpm).

Pumpenkopf-Nr: 1 YZ2515, 2 YZ1515, 3 DG 6 Rollen, 4 DG 10 Rollen.
Schlauch-Nr: YZ1515 1-7 = 0,8 / 1,6 / 2,4 / 3,1 / 4,8 / 6,4 / 7,9 mm; YZ2515 1-4 = 4,8 / 6,4 / 7,9 / 9,6 mm;
DG 1-9 = 0,13 / 0,25 / 0,51 / 1,02 / 1,65 / 2,00 / 2,40 / 2,79 / 3,17 mm.

## Herstellerbeispiele (Anhang 7, alle im Test nachgerechnet)

```
a) WD, Pumpe 1: 10,0 mL, 200 Kopien, 100,0 mL/min, Pause 1,0 s
   -> E9 01 0E 57 44 00 00 03 E8 00 00 C8 05 F5 E1 00 00 0A 24     (03 E8 -> 03 E8 00 gestufft)
   <- E9 01 02 57 44 10
b) RF, Pumpe 1
   -> E9 01 02 52 46 17
   <- E9 01 07 52 46 0E E6 B2 80 02 CA     (250000000 nL/min = 250,0 mL/min; 02 = steht, cw)
c) WT, Pumpe 1: Kopf YZ2515, Schlauch 6,4 mm
   -> E9 01 04 57 54 02 02 06
   <- E9 01 02 57 54 00
Am Geraet 02.11.2026: RID -> E9 01 03 52 49 44 5D, Antwort identisch (Echo).
```

## Was der Treiber benutzt

Nur den Flussrate-Modus: `WF` (Fluss + Start/Stop + Richtung in einem Frame), `RF` (Live-Werte),
`RT` und `RID` (beim Verbinden). Dosieren laeuft zeitgesteuert ueber `WF` wie bei der WT600, weil der
geraeteeigene Dosier-Modus (`WD`/`WSD`) den Control Mode "Dispensing" am Geraet voraussetzt.
Beim Verbinden liest der Treiber `RF` und schreibt erst danach den Stopp, damit die am Geraet
eingestellte Flussrate erhalten bleibt.

Unterschied zur WT600-2J: die kennt `WJ`/`RJ` (Drehzahl in rpm) - die BT100-1F antwortet darauf nicht
(so am 02.11.2026 beobachtet, erklaert durch dieses Dokument).
