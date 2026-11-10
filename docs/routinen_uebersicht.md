# Routinen-Uebersicht (Stand 02.11.2026)

Alle Routinen aus config.yml, die im Frontend unter "Routines" erscheinen, und wofuer sie da sind.
Faustregel: **kolbe_...** sind Versuchsschritte, **test_.../stop_...** sind Geraetetests (einzelnes Geraet
pruefen, nicht fuer den Versuch). Ein Versuch = mehrere Schritte nacheinander, jeder Schritt eine Routine,
im Schrittmodus je ein Klick auf "Start Experiments" (docs/ablauf_versuch_im_labor.md, Abschnitt 6).
Wie die Konfigurationsdatei aufgebaut ist und wie man Routinen aendert: docs/yaml_fuer_chemiker.md.

## Elektrolyse - welche Routine fuer welchen Aufbau

| Routine | Aufbau | Geraete | Parameter |
|---|---|---|---|
| `kolbe_elektrolyse_gc` | **eine Zelle, eine Kammer** (wie bisher) | psu1, mfc1, dosing_pump, Liquiline (pH CH1, Leitfaehigkeit, Temperatur), microGC | versuch, gc_minutes, current, max_voltage, minutes, rate |
| `kolbe_elektrolyse_2k` | **eine Zelle, zwei Kammern** (neu 02.11.) | wie _gc, dazu mfc2 am Katholytgas, zweiter pH ph_z2 mit Temperatur temperature_z2, zweite Pumpe anolyte_pump | wie _gc, dazu rate_anolyte |
| `kolbe_elektrolyse_3x` | **drei Zellen parallel** (26.10.) | psu1-3, mfc1-3, beide Pumpen, Liquiline (pH Z1/Z2/Z3), microGC im Kreis ueber ventil_z1-3 | versuch, gc_minutes, current_z1/z2/z3, max_voltage, minutes, rate, rate_anolyte |
| `kolbe_elektrolyse_ph` | eine Zelle ohne GC (aelter) | psu1, mfc1, dosing_pump, Liquiline | current, max_voltage, minutes, rate |
| `kolbe_elektrolyse` | eine Zelle ohne GC und ohne Liquiline (aelteste) | psu1, mfc1, dosing_pump | current, max_voltage, minutes, rate |

Gemeinsam: Netzteil `minutes` lang mit `current`, Spannungsgrenze `max_voltage`, danach Ausgang aus; Pumpe(n)
gleich lang; Zaehler der Bronkhorst auf 0 und live. Bei _gc/_2k/_3x misst der GC nach `gc_minutes`
(0 = Dauermessung, Zahl = alle N min, Liste `0;10;20` = feste Zeitpunkte) und nach dem Ende noch einmal
(Abschlussmessung, bei _3x je Zelle). Details: docs/microgc_messplan_im_experiment_13-10-2026.md,
docs/zweikammer_2k_02-11-2026.md, docs/gc_rundlauf_3_zellen_26-10-2026.md.

## Weitere Versuchsschritte (Pumpen, Spuelen, Gas zaehlen)

| Routine | Was | Parameter |
|---|---|---|
| `kolbe_pumpe_zeit` | Pumpe `minutes` lang mit `rate`, mfc1 live (Befuellen/Umwaelzen) | rate, minutes |
| `kolbe_n2_spuelung` | wie kolbe_pumpe_zeit, Zaehler vorher auf 0 (N2-Spuelung) | rate, minutes |
| `kolbe_gas_zaehlen` | nur mfc1: Zaehler auf 0, `minutes` lang zaehlen, keine Pumpe | minutes |
| `kolbe_gas_zaehlen_pumpe` | Gas zaehlen, waehrend die Pumpe umwaelzt | minutes, rate |
| `kolbe_gc_messung` | eine einzelne GC-Messung von Hand (Methode laden, Lauf mit Name/Tags, Daten holen) | method, name, tags |
| `..._3x` (kolbe_pumpe_zeit_3x, kolbe_n2_spuelung_3x, kolbe_gas_zaehlen_pumpe_3x) | dasselbe fuer drei Zellen: mfc1-3 und beide Pumpen | rate, rate_anolyte, minutes |

## Geraetetests (nicht fuer den Versuch)

| Routine | Geraet | Was |
|---|---|---|
| `test_psu_output` / `stop_psu_output` | psu1 | Ausgang an mit current/max_voltage, bis Stop-Routine / aus |
| `test_psu2_output`, `test_psu3_output` + stop | psu2, psu3 | dasselbe fuer Netzteil 2 und 3 (Zuordnung zu den Zellen pruefen) |
| `test_mfc_setpoint`, `test_mfc2_setpoint`, `test_mfc3_setpoint` | mfc1-3 | Sollwert `flow` setzen und messen |
| `test_mfc_counter`, `test_mfc2_counter`, `test_mfc3_counter` | mfc1-3 | Zaehler einmal lesen |
| `test_mfc1_zaehlen`, `test_mfc2_zaehlen`, `test_mfc3_zaehlen` | mfc1-3 | Zaehler auf 0, `minutes` lang zaehlen (Einheit pruefen) |
| `stop_mfc`, `stop_mfc2`, `stop_mfc3` | mfc1-3 | Fluss stoppen |
| `test_wt600_speed` / `stop_wt600` | dosing_pump | Drehzahl `rpm` setzen, Pumpe laeuft bis Stop |
| `test_anolyte_speed` / `stop_anolyte` / `test_anolyte_lauf` | anolyte_pump | dasselbe fuer die zweite Pumpe; _lauf = `minutes` lang mit `rate` |
| `test_live_polling` | mfc1, dosing_pump | Volumen `volume` mit `rate` dosieren, Live-Werte pruefen |
| `test_liquiline_ph` | Liquiline | pH CH1 einmal lesen |
| `test_liquiline_all_channels` | Liquiline | alle eingerichteten Kanaele lesen (pH CH1, Leitfaehigkeit, Temperatur, ph_z2, ph_z3, temperature_z2) |
| `test_liquiline_scan` | Liquiline | alle 16 Modbus-Bloecke lesen (welcher Analogeingang liefert was) |
| `test_microgc_status` | microGC | Status abfragen (ready / bakeout / method-running) |
| `test_microgc_bakeout` | microGC | BakeOut `minutes` starten (am Geraet nie getestet) |
| `test_microgc_run` | microGC | Methode laden, ein Lauf ohne Namen, Daten holen |
| `test_microgc_plan` | microGC | Messplan wie im Experiment, aber ohne andere Geraete |
| `test_ventil_z1..z3` | ventil_z1-3 | ein Ventil `minutes` lang auf `position` (A/B) halten |
| `test_gasweg_z1..z3` | mfcN + Ventile | Gasweg einer Zelle zum GC oeffnen, andere zu, Fluss zaehlen |
| `test_gc_ventile_3x` | mfc1-3, Ventile, microGC | GC-Rundlauf ueber drei Zellen ohne Netzteile |

## Beim Routinen-Laden im Frontend

Administration -> Routines -> "Download Experiments from Station" holt die Liste vom Backend. Neue oder
geaenderte Routinen (neue Parameter/Observablen) erscheinen nur so; eine schon geladene Routine wird nicht
aktualisiert - deshalb bekommen geaenderte Routinen einen neuen Namen (z.B. _gc, _2k). Fehlt eine Routine,
war beim Backend-Start eines ihrer Geraete aus (Backend ueberspringt sie mit Warnung im Log).

## Messstand II (zweiter Pi, config.messstand2.yml)

Diese Uebersicht beschreibt Messstand I (config.yml). Messstand II hat eine eigene Konfiguration und eigene
Routinen. Stand 06.11.2026: Geraetetests (`test_valve1_position`, `test_pump1_read`, `test_pump1_flow`,
`test_pump1_stop`, `test_liquiline_scan`) und der erste Baustein fuer das automatische Ansetzen der
Reaktionsloesung:

| Routine | Parameter | Was passiert |
|---|---|---|
| `zugabe` | port, volume (mL) | eine Zugabe aus einem Port des 16-Wege-Ventils, danach Spuelen mit Wasser |
| `spuelen` | volume (mL) | nur Wasser aus Port 1 |
| `dosiertest` | volume (mL), repeats, pause (s) | mehrmals dasselbe Wasservolumen, zum Auswiegen |
| `vorfuellen` | vol_wasser (mL), port_a..port_d (0 = ungenutzt), vol_je_port (mL) | vor dem ersten Ansatz alle Schlaeuche fuellen: Wasser, dann je Port seine Chemikalie mit Spuelen; Auslauf ins Becherglas (10.11.2026) |
| `ansatz` | port/vol Leitsalz, vol Wasser, port/vol Saeure 1 und 2, port_naoh, ziel_ph, toleranz, wartezeit (s), zielvolumen (mL), pause (s) | ganzer Ansatz in einem Lauf: feste Zugaben mit Spuelen, dann pH mit NaOH/Saeure 1 auf ziel_ph regeln, dann mit Wasser auf das Zielvolumen auffuellen (10.11.2026) |

Beschreibung, Testreihenfolge fuers Labor, bekannte Grenzen und offene Fragen:
`docs/messstand2_zugabe_06-11-2026.md`.
