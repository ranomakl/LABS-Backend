# Drei Zellen parallel - ein Backend, ein Experiment, GC im Kreis (26.10.2026)

Ziel (Rafael, 26.10.2026): Am 28.10.2026 sollen drei Zellen gleichzeitig elektrolysiert werden.
Vorhanden: 3 Netzteile (Joy-IT DPM8650, baugleich), 3 Bronkhorst (2x 50, 1x 20 mln/min), 3 Zellen,
aber nur EINE Pumpe (pumpt fuer alle gleich), EINE Liquiline (Mehrkanal), EIN microGC. Der GC soll
abwechselnd messen (Z1, Z2, Z3, Z1, ...); alle ~21 min je Zelle reicht. Ventile fuer die Umschaltung
"kommen noch".

## Entscheidung: ein Backend, ein Experiment fuer alle drei Zellen

Nicht drei Backend-Prozesse (die geteilten Geraete Pumpe/GC/Liquiline kann nur ein Prozess halten),
sondern ein Experiment, dessen Befehlsliste alle drei Netzteile und Zaehler anspricht. Die Rezepte in
config.yml sind nur Befehlslisten; das Backend faehrt die Befehle nacheinander ab und wartet am Ende,
bis alle Geraete fertig sind. Schrittmodus, Frontend und Start-Knopf bleiben wie bisher.

## Geraete (config.yml)

| Zelle | Netzteil | Steckplatz (by-path) | MFC | Adapter (by-id) | Messbereich |
|---|---|---|---|---|---|
| Z1 | psu1 | 2.4.2 | mfc1 | BG01B77U (M18212352B) | 50 mln/min |
| Z2 | psu2 | 2.1   | mfc2 | BG01B1W6 (M18212352C) | 50 mln/min |
| Z3 | psu3 | 2.2.1 | mfc3 | BG01B8RX (M18216421B) | 20 mln/min (Geraet meldet 20000 uln/min) |

Alle Netzteile haben Adresse 01, 9600 Baud; die CH340-Adapter sind nur ueber den USB-Steckplatz
unterscheidbar - **Stecker nicht umstecken**. Alle MFC Knoten 03, 38400 Baud. Die Bronkhorst
brauchen ein eigenes Steckernetzteil (15-24 V), ueber USB allein antworten sie nicht (26.10.: MFC 3).
Geprueft am 26.10.2026 mit tools/lese_netzteil.py und tools/lese_mfc.py (reine Lesewerkzeuge).

Die bisherigen Geraete `psu` und `mfc` heissen jetzt `psu1` und `mfc1`; alle alten Experimente
(kolbe_elektrolyse_gc usw.) wurden umbenannt und laufen unveraendert weiter.

Ventile `ventil_z1..3` (raspi_gpio_relay_valve, Pins 17/27/22 als ANNAHME): Position B = Gasweg der
Zelle zum GC offen, A = zu (safe_state, spannungslos). Bis die Ventile verkabelt sind, steht
`simulate: true` in config.yml - der Treiber schaltet dann kein echtes Relais, der Rundlauf laeuft
aber schon. **Beim Verkabeln: simulate entfernen, pin/inverted/safe_state am echten Aufbau pruefen.**

## GC-Rundlauf (Treiber inficon_microgc_fusion)

Am Geraet `microgc` stehen die Gasstroeme:

```yaml
    flush_s: 30
    streams:
      - { name: Z1, valves: { ventil_z1: B, ventil_z2: A, ventil_z3: A } }
      - { name: Z2, valves: { ventil_z1: A, ventil_z2: B, ventil_z3: A } }
      - { name: Z3, valves: { ventil_z1: A, ventil_z2: A, ventil_z3: B } }
```

`run_schedule_named(..., streams: "alle")` (oder "Z1;Z3") misst die Stroeme im Kreis:
- jeder faellige Lauf (Liste, Intervall oder Dauermessung mit gc_minutes 0) misst den NAECHSTEN Strom;
- vor dem Lauf werden die Ventile des Stroms gestellt und `flush_s` gewartet (entfaellt, wenn die
  Ventile schon so stehen); dann Leerlauf abwarten, Lauf starten, Daten holen wie bisher;
- Laufname `<versuch>_<Strom> <t> min`, Tags + Stromname; Dateien logs/.../microgc/<versuch>_Z1_<t>_min.*;
- Konzentrationen als `gc_<Strom>_<Label>` (gc_Z1_H2, gc_Z2_H2, ...), dazu `gc_stream` = zuletzt gemessene Zelle;
- Abschlussmessung (final_run) nach dem Ende der Elektrolyse einmal JE Strom (`<versuch>_Z1_Ende <t> min`, ...);
  das Experiment endet erst danach - bei drei Zellen also bis zu ~3 x 7 min plus Spuelzeiten nach dem Netzteil-Aus;
- unbekannter Strom oder nicht verbundenes Ventil = Fehler beim Start (statt stundenlang die falsche Zelle zu messen);
- ohne `streams` verhaelt sich alles wie vorher (ein Strom, gc_H2 ...).

Setup reicht den Geraeten nach dem Verbinden die Geraeteliste (`link_devices`), damit der GC seine
Ventile kennt (backend/setup/setup.py `_link_devices`).

Rechnung: ein GC-Lauf ~7 min + 30 s Spuelen -> jede Zelle etwa alle 22-23 min, bei 219 min ~9 Punkte je Zelle.

## Experimente (config.yml, Abschnitt "Drei Zellen parallel")

| Experiment | Geraete | Parameter |
|---|---|---|
| kolbe_pumpe_zeit_3x (Dichtheitstest) | Pumpe, mfc1-3 | rate, minutes |
| kolbe_n2_spuelung_3x | Pumpe, mfc1-3 (Zaehler zurueckgesetzt) | rate, minutes |
| kolbe_elektrolyse_3x | psu1-3, mfc1-3, Pumpe, Liquiline, Ventile, microGC (streams alle, final_run) | versuch, gc_minutes, current_z1, current_z2, current_z3, max_voltage, minutes, rate |
| kolbe_gas_zaehlen_pumpe_3x | Pumpe, mfc1-3 | minutes, rate |

Der Strom ist je Zelle einstellbar (current_z1..3), Spannungsgrenze, Dauer und Pumprate gelten fuer alle.
Im Frontend: Administration -> Routines -> "Download Experiments from Station", dann die vier neuen Routinen anlegen.

## Dummy-Umgebung

LABS-DeviceDummys/main.py hat neue Ports: 12356/12357 (mfc2/mfc3), 12361/12362 (psu2/psu3, TDK-Dummy).
`python main.py config.dummy.yml` startet das Backend mit der Dummy-Konfiguration, ohne config.yml zu
ueberschreiben (neu 26.10.). Ventile laufen dort ueber den gpiozero-Mock.

Durchstich 26.10.2026 auf dem Pi (Dummys, kolbe_elektrolyse_3x, 2.5 min, gc_minutes 0, Spuelzeit 30 s):
Laeufe 26180_Z1_0 min, 26180_Z2_0.7 min, ... im Kreis mit Ventilumschaltung, danach Abschlussmessungen
Z1/Z2/Z3, dann Finished. Unit-Tests: backend/test/test_microgc_gasstroeme.py (11), die alten
test_microgc_abschlussmessung.py (15) laufen weiter.

## Vorgezogenes Umschalten (Variante B), 27.10.2026

`switch_after_s: 60` am microgc (config.yml): 60 s nach dem Start eines Laufs stellt der Treiber die Ventile
schon auf den Gasstrom, den der naechste Lauf voraussichtlich misst (`_peek_next_stream`: naechster im Kreis,
sonst Beginn der Abschlussserie). Die Probenahme des GC ist dann vorbei, die Leitung spuelt waehrend der
7,6 min Trennung; der naechste Lauf schaltet nicht mehr um und wartet kein `flush_s`. Nur solange der Lauf,
der den Timer gesetzt hat, noch der aktive ist. Trifft die Vorhersage nicht zu (z.B. Dauermessung endet
waehrend des Laufs), schaltet der naechste Lauf wie bisher um und wartet `flush_s`. `switch_after_s: 0` =
altes Verhalten. Dummy-Config: 10 s, weil ein Dummy-Lauf nur ~40 s dauert.

## Zweite Pumpe (Anolyt), 27.10.2026

Geraet `anolyte_pump` (zweite WT600-2J, Adapter BG01W2OJ). In allen `_3x`-Routinen laeuft sie parallel zur
`dosing_pump` mit derselben Dauer `minutes` und eigener Rate `rate_anolyte` (Vorgabe docs/neuePumpe.txt).
Dummy: Port 12358.

## Offen

- Ventile verkabeln (Relaisplatine), Pins/Invertierung/Ruhelage pruefen, `simulate` entfernen.
- Erster Start des neuen Backends am echten Aufbau: alle drei Netzteile und MFC muessen an sein.
- Frontend: Tabellen/Kurven der drei Zellen nebeneinander (LABS-User-Interface).
- Liquiline: Kanaele je nach Sensoranzahl (heute nur Zelle 1: pH, Leitfaehigkeit, Temperatur).
- Zaehler-Einheit des 20er-MFC (uln?) am Geraet pruefen - der Treiber rechnet mit max_flow_ml_min 20.
