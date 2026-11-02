# Zwei-Kammer-Zelle, ein Versuch: Routine `kolbe_elektrolyse_2k` (02.11.2026)

Anforderung (ANFORDERUNGEN.txt, PRIO): "Versuchsablauf fuer 1er-Versuch mit 2 Kammern - so wie bisher, nur dass
es einen zusaetzlichen pH-/Temperatur-Wert gibt, sowie einen zweiten MFM/Bronkhorst, der das bildende Gas im
Katholyt misst." Antworten Rafael 29.10./02.11.: Katholytgas = **mfc2** (Bronkhorst 2); zweiter pH-Sensor =
**ph_z2** (Liquiline CH3 = Modbus AI4); zweite Temperatur ja, ueber **AI6**.

## Was die Routine macht

`kolbe_elektrolyse_2k` = `kolbe_elektrolyse_gc` plus:

| Neu | Geraet | Was |
|---|---|---|
| Katholytgas | mfc2 | Zaehler auf 0, Fluss + Zaehler live (kein Sollwert, Ventil wie immer 100 %) |
| zweiter pH | liquiline ph_z2 | Wert + Status, 2-s-Takt wie ph_ch1 |
| zweite Temperatur | liquiline temperature_z2 | AI6, Temperatur des Sensors an CH3 |
| zweite Pumpe | anolyte_pump | laeuft `minutes` lang mit `rate_anolyte` |

Unveraendert: psu1 (Strom `current`, Spannungsgrenze `max_voltage`, `minutes` lang, dann Ausgang aus), mfc1 am
Anolytgas, dosing_pump mit `rate`, Leitfaehigkeit, Temperatur CH1, GC-Messplan nach `gc_minutes` (0 =
Dauermessung) mit Abschlussmessung nach dem Ende. Der GC misst nur den bisherigen Strom (kein Ventil-Rundlauf).

Parameter im Frontend: versuch, gc_minutes, current, max_voltage, minutes, rate, rate_anolyte.

**ANNAHME Pumpenzuordnung** (nicht bestaetigt, nach den Namen und docs/neuePumpe.txt): dosing_pump am Katholyt
(`rate`), anolyte_pump am Anolyt (`rate_anolyte`). Ist es umgekehrt, einfach die Raten vertauscht eintragen -
beide laufen gleich lang.

## Vor dem ersten Lauf am Pi

1. `git pull`, Backend neu starten, im Frontend "Routinen neu laden" (neue Routine + Parameter rate_anolyte).
2. **Liquiline, einmalig:** Setup / Outputs / Modbus / AI 6: Datenquelle CH3 (zweiter pH-Sensor), Messwert
   Temperatur. Ohne das meldet temperature_z2 Status "Not assigned" und Wert 0. Pruefen mit der Routine
   test_liquiline_all_channels (zeigt jetzt auch temperature_z2_value/_status) oder test_liquiline_scan.
3. mfc2 und anolyte_pump muessen an sein (Bronkhorst mit Steckernetzteil, Pumpe am Adapter BG01W2OJ), sonst
   wird die Routine beim Backend-Start mit Warnung uebersprungen.

## Getestet

Dummys am PC (02.11.2026, minutes 1, gc_minutes 0, rate 100, rate_anolyte 50): beide Pumpen laufen mit
eigener Drehzahl (113 / 60 rpm) und stoppen am Ende, mfc1 + mfc2 zaehlen, ph_ch1/ph_z2/temperature/
temperature_z2 im 2-s-Takt mit Status Good, GC 5 Laeufe + Abschlussmessung, Finished. Dummy-Liquiline
simuliert jetzt auch AI4/AI5/AI6 (LABS-DeviceDummys).
