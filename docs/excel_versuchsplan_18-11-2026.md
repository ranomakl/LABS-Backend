# Excel-Versuchsplan: Stufe 1 bis 3 gebaut (18.11.2026)

Umsetzung von docs/konzept_excel_versuchsplan_10-11-2026.md: Stufe 1 (Datei lesen, Werte zeigen), Stufe 2
(Routinenformular vorbelegen) und Stufe 3 (Messwerte nach dem Lauf in eine KOPIE der Datei schreiben,
Download auf der Stage-Seite). Frontend: LABS-User-Interface; Backend: nur der neue Endpunkt /api/run_log.
Erklaerung fuer Chemiker und Bediener: docs/excel_versuchsplan_erklaert_18-11-2026.txt.

Entscheidungen mit Rafael am 18.11.2026:

- Die Vorlage der Chemiker bleibt unveraendert, keine Versionszelle. LABS erkennt sie an den Beschriftungen
  in Spalte A (z.B. "Pool volume" in Setup_parameter!A27). Stimmt eine Beschriftung nicht, wird die Datei
  abgelehnt und die Abweichung genannt - lieber ablehnen als still falsche Werte lesen.
- Carbonsaeure: die Vorlage rechnet n-C4, n-C6, n-C8 einzeln; an Port 6 haengt die fertige Mischung, also
  wird die Summe der drei Volumina als vol_carbonsaeure vorbelegt.
- Leitsalz (Na2SO4 in Gramm) bleibt leer, bis der Chemiker die Stammloesung nennt
  (docs/fragen_chemiker_excel_vorlage_18-11-2026.txt).
- Zuordnungen fuer alle Routinen, die die Vorlage abdeckt: Kolbe-Elektrolyse am Messstand I (kolbe_elektrolyse,
  _ph, _gc, _2k, _3x, kolbe_n2_spuelung, _3x, kolbe_pumpe_zeit, _3x, kolbe_gas_zaehlen_pumpe, kolbe_gc_messung)
  und ansatz / ph_regelung am Messstand II.

## 1. Bedienung

Im Frontend auf der Stage-Seite (eine Stage = eine Routine) gibt es den Block "Versuchsplan (Excel-Vorlage
der Chemiker)". Datei auswaehlen, "Versuchsplan lesen und Formular vorbelegen".

1. LABS prueft, ob es die bekannte Vorlage ist, und liest die Zellen laut Zuordnungsdatei fuer die Routine
   dieser Stage.
2. Eine Tabelle zeigt je Parameter: Zelle, Beschriftung in der Vorlage, gelesener Rohwert, uebernommener Wert,
   Hinweis. Parameter ohne Wert sind gelb markiert.
3. Das Formular "Add run" unten ist mit den Werten vorbelegt. Leere Felder (gelber Rand) von Hand fuellen,
   dann "Add". Es wird KEIN Lauf automatisch angelegt und nichts an die Station geschickt.
4. Danach wie bisher "Submit Stage".

Meldungen (oben auf der Seite):

- "Versuchsplan nicht uebernommen: ... passt zu keiner bekannten Vorlage ..." - Datei ist nicht die
  Flusszellen-Vorlage oder eine Zeile wurde verschoben; die Meldung nennt die Zelle(n).
- "... enthaelt eine Formel, aber keinen gespeicherten Wert. Die Datei in Excel oeffnen, speichern ..." -
  openpyxl liest nur die von Excel gespeicherten Formelergebnisse.
- Warnungen (gelb): Zweikammer-Vorlage bei Einkammer-Routine, Messmodus nicht galvanostatisch, Einheit der
  Station passt nicht zur Zuordnung, Parameter in der Zuordnung, den die Station nicht kennt.

## 2. Zuordnungsdatei

LABS-User-Interface/app/experiments/versuchsplan_vorlagen/kolbe_flow_v1.yml. Eine Datei je Vorlage, darin:

    vorlage:
      name: ...
      erkennung:                # Zelle: erwartete Beschriftung (Gross-/Kleinschreibung und Leerzeichen egal)
        Setup_parameter!A27: Pool volume
      pruefungen:               # Warnung, wenn ein Wert nicht wie erwartet ist
        - { zelle: Setup_parameter!B29, erwartet: galvanostatic, meldung: ... }
    routinen:
      kolbe_elektrolyse_gc:
        nur_wenn: { zelle: Setup_parameter!B9, wert: One-Chamber }      # Warnung, kein Abbruch
        parameter:
          rate:    { zelle: Setup_parameter!B18, einheit_routine: mL/min }
          current: { zelle: Setup_parameter!B30, einheit_vorlage: mA, einheit_routine: A, faktor: 0.001, runden: 4 }
          gc_minutes: { zellen: Exp_protocol!A3:A17, trenner: ";", ganzzahl: true }
      ansatz:
        parameter:
          vol_carbonsaeure: { summe: [Exp_preparation!B6, Exp_preparation!B7, Exp_preparation!B8], runden: 2 }

Je Parameter: `zelle` (eine Zelle), `zellen` (Bereich, verbunden mit `trenner`), `summe` (Liste, addiert),
`faktor` (Umrechnung), `runden`/`ganzzahl` (Darstellung), `text: true` (unveraendert als Text),
`einheit_routine` (wird gegen die Einheit der Station geprueft), `hinweis` (Text fuer die Anzeige).
Parameter der Routine ohne Eintrag bleiben leer und werden gemeldet. Eine neue Vorlage = neue YAML-Datei im
selben Ordner, kein Code.

## 3. Was aus der Flusszellen-Vorlage kommt

| Routine | aus der Vorlage | von Hand |
|---|---|---|
| kolbe_elektrolyse_gc | versuch (B1), rate (B18), current (B30, mA->A), minutes (B33, Formel), gc_minutes (Exp_protocol A3:A17) | max_voltage |
| kolbe_elektrolyse_2k | wie oben | max_voltage, rate_anolyte |
| kolbe_n2_spuelung | rate (B18), minutes (Analytics!B12) | - |
| kolbe_gc_messung | method (Analytics!B3), name (B1) | tags |
| ansatz | vol_wasser (Exp_preparation!B5), vol_carbonsaeure (B6+B7+B8), vol_naoh (B12, falls eingetragen), ziel_ph (Setup!B26), zielvolumen (Setup!B27) | vol_leitsalz, toleranz, vol_gross, vol_klein, wartezeit_ph_messung, pause_zugabe |
| ph_regelung | ziel_ph, zielvolumen | toleranz, vol_gross, vol_klein, wartezeit_ph_messung, startvolumen |

Beispiel 26174: rate 100, current 0.55, minutes 219.3, gc_minutes 0;10;20;...;219; ansatz: vol_wasser 50,
vol_carbonsaeure 17.92, ziel_ph 9.5, zielvolumen 100.

## 4. Technik und Tests

- app/experiments/versuchsplan.py: `Versuchsplan.laden(datei)` erkennt die Vorlage, `fuer_routine(name,
  {parameter: einheit})` liefert `Ergebnis` (werte, zeilen fuer die Anzeige, hinweise, offen). Nur openpyxl
  und PyYAML, ohne Flask testbar.
- app/experiments/views.py: Route POST /upload_versuchsplan/<stage_id>; `edit_stage` rendert ueber
  `_render_stage(stage_id, vorbelegung, plan)`.
- app/templates/experiments/stage_detail.html: Upload-Block, Tabelle "Aus dem Versuchsplan gelesen",
  Vorbelegung im Formular "Add run".
- Tests: tests/test_versuchsplan.py (Leser, 14 Tests, nachgebaute Vorlage; echte Vorlage unter tests/data/
  wird mitgeprueft, wenn vorhanden - gitignored) und tests/test_versuchsplan_route.py (4 Tests durch die
  Flask-Seite: Vorbelegung, Warnung, Ablehnung, ohne Datei). Lauf im Frontend-Ordner:
  `.venv/Scripts/python -m unittest tests.test_versuchsplan tests.test_versuchsplan_route`.

## 5. Stufe 3: Ergebnis-Excel (18.11.2026, zweiter Commit)

- Der hochgeladene Versuchsplan wird je Stage abgelegt (Frontend instance/versuchsplaene/stage_<id>.xlsx,
  versuchsplan_ablage.py). Block "Ergebnis-Excel" auf der Stage-Seite zeigt die abgelegte Datei und den Knopf.
- GET /download_ergebnis/<stage_id>: fuer alle geschickten Runs der Stage /api/run_log an der Station abfragen,
  den letzten fertigen nehmen, mit versuchsplan_befuellen.befuellen() die Kopie schreiben, als
  <Original>_LABS.xlsx senden. Protokoll (was eingetragen wurde) als Meldungen.
- Zuordnung im Abschnitt `ausgabe` der YAML: kolbe_elektrolyse_* -> Exp_protocol Zeitraster (B Gaszaehler-
  Differenz, C pH, D Leitfaehigkeit, F Spannung, G Temperatur; Zeile 18 letzte Werte; H3 Vermerk; Setup!B2 Datum);
  kolbe_n2_spuelung -> Zeile "Before"; ansatz -> Exp_preparation B12 (dosed_ml minus feste Zugaben), B18 End-pH;
  ph_regelung -> B18.
- Backend: `Setup.remote_run_log(experiment_id)` / `run_log_lesen()` in setup.py, Test backend/test/test_run_log.py.
- Tests Frontend: tests/test_versuchsplan_befuellen.py (10), tests/test_versuchsplan_route.py (8, Station per mock).

## 6. Offen

- Antworten des Chemikers: docs/fragen_chemiker_excel_vorlage_18-11-2026.txt (Leitsalz, NaOH-Formel,
  max_voltage, N2 nach der Elektrolyse, weitere Vorlagen).
- Eine zusammengefuehrte Ergebnisdatei ueber alle Stages eines Versuchs (Ansatz + Spuelung + Elektrolyse):
  braucht ein verbindendes Merkmal (Versuchsnummer).
- Spalte E (kumuliertes H2) aus GC-Daten; Leitfaehigkeit am Messstand II (kein Sensor in der Config).
- Am Pi noch nicht ausprobiert: Frontend und Backend pullen und neu starten, keine DB-Aenderung, keine neuen Pakete.
