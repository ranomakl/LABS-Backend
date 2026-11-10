# Konzept: Excel-Versuchsplan in LABS einlesen und am Ende befuellen (10.11.2026)

Anforderung (Rafael, 10.11.2026, schon in "Anforderungen ab 08.10": "die Excel file soll uebernommen werden
koennen"): Die Chemiker planen jeden Versuch in einer Excel-Vorlage und tragen am Ende die Messwerte von Hand
nach. LABS soll die Datei entgegennehmen, die Routinenparameter daraus vorbelegen und nach dem Lauf die
Messwerte in die Datei schreiben. Noch nichts gebaut; dieses Papier ist die Grundlage fuer die Umsetzung am PC.

Untersuchte Vorlage: docs/versuchsplanung_26174-26177.zip, Datei Experiment_26174_flow_cell_opt_cond_max_1-chamber_rep_1.xlsx
(Kolbe-Elektrolyse, Flusszelle, eine Kammer). Alle Zellangaben unten beziehen sich auf diese Vorlage.

## 1. Kurzfassung

- Die Vorlage hat fuenf Blaetter mit festen Zellpositionen. Eingaben fuer LABS stehen in `Setup_parameter` und
  `Exp_preparation`, die Messwerttabelle, die LABS befuellen kann, ist `Exp_protocol`. `Exp_postprocessing` und
  der Grossteil von `Analytics` bleiben Handarbeit.
- Bauen in drei Stufen: (1) Datei hochladen und Parameter anzeigen, (2) Routinenformular damit vorbelegen,
  (3) nach dem Lauf eine Kopie der Datei mit Messwerten fuellen und zum Download anbieten.
- Die Zuordnung Zelle <-> Parameter steht in einer YAML-Datei (`excel_vorlage_v1.yml`), nicht im Code. Die
  Vorlage bekommt eine Versionszelle, damit LABS eine veraenderte Vorlage erkennt und ablehnt, statt still
  falsche Werte zu lesen.
- Alles Noetige ist da: openpyxl 3.1.5 und pandas sind schon in LABS-User-Interface/requirements.txt, das
  Frontend hat eine Upload-Route (design_data_upload), und tools/auswertung.py liefert bereits Tabellen im
  Zeitraster (`--csv --takt 600`).
- Aufwand grob: Stufe 1+2 ein bis zwei Tage, Stufe 3 noch einmal so viel.

## 2. Die Vorlage

| Blatt | Inhalt | Rolle fuer LABS |
|---|---|---|
| `Setup_parameter` | Versuchsnummer, Beschreibung, Operator, Reaktor, Elektroden, Pumpe und Flussrate, Loesung (Saeuren, Verhaeltnis, Konzentrationen, pH, Poolvolumen), Elektrochemie (Modus, Strom, geplante FE, Dauer per Formel) | Eingabe: Routinenparameter |
| `Exp_preparation` | Rezeptrechnung per Formel: Wasser Teil 1 = Pool/2, Saeurevolumina aus Konzentration und festem Verhaeltnis 3:8:1, Leitsalz in g, NaOH/H2SO4 zum pH-Einstellen (Handeintrag), Wasser Teil 2 als Rest; Wiegungen, End-pH, Leitfaehigkeit | Eingabe fuer `ansatz` (das "Blatt 2" aus docs/messstand2_zugabe_06-11-2026.md, Frage 1); Ausgabe: tatsaechlich dosiertes NaOH, End-pH |
| `Exp_protocol` | Zeitraster 0, 10, ..., 60, 80, ..., 200, 219 min sowie Zeilen Before / After Electrolysis / After Acidification / After Purging. Spalten: kumuliertes Gasvolumen [mln N2], pH, Leitfaehigkeit [mS/cm], kumuliertes H2 [mln], Zellspannung [V], Temperatur [degC], Beobachtungen | Ausgabe: genau die Messwerte, die LABS mitschreibt |
| `Exp_postprocessing` | Wiegungen, Dichten, Phasentrennung, Spuelvolumina | Handarbeit, LABS laesst es leer |
| `Analytics` | microGC-Geraet/-Methode, Anzahl Messungen, N2-Spuelung vor/nach, GC-MS-Angaben | teils Eingabe (N2-Spuelung, GC-Methode), Rest Handarbeit |

Wichtig fuer das Lesen: Die Vorlage rechnet mit Formeln (z.B. `Exp_preparation!B6` = Saeurevolumen,
`Setup_parameter!B33` = Dauer). openpyxl liest mit `data_only=True` die von Excel zuletzt gespeicherten
Ergebnisse. Das funktioniert nur, wenn die Datei in Excel gespeichert wurde (nicht frisch aus einem Skript
erzeugt). LABS prueft deshalb, ob die Formelzellen Werte haben, und meldet sonst "Datei in Excel oeffnen,
speichern, erneut hochladen".

## 3. Was heute schon da ist

- **Frontend** (LABS-User-Interface, Flask): Upload-Route `experiments.upload_stage` mit `design_data_upload`
  (app/experiments/views.py, Zeile ~416) nimmt Dateien fuer Stages entgegen. Parameter eines Runs gehen als
  Formular-POST an `http://<station>/api/add_experiment` (app/experiments/models.py, Zeile ~748), Felder
  `experiment_id`, `experiment_type` und die Parameter als Name=Wert.
- **Backend**: `remote_add_experiment` nimmt genau diese Felder. Jeder Lauf schreibt `logs/<J>/<M>/<T>/<run>/`
  mit `values.json` (alle Observables mit Zeitstempel), `lauf.json` (Typ, Parameter, Start/Ende), `log.txt`,
  `bericht.html`. `tools/auswertung.py <run> --csv datei.csv --takt 600` liefert eine Tabelle im 10-Minuten-Raster.
- **Bibliotheken**: openpyxl und pandas im Frontend vorhanden; im Backend-venv fehlt openpyxl (dort nicht
  noetig, wenn das Frontend die Excel-Arbeit macht).
- **Messwerte** (Namen aus config.yml, Messstand I): `liquiline ph_ch1_value` [pH], `liquiline conductivity_value`
  [mS/cm], `liquiline temperature_value` [degC], `psu1 voltage` [V], `psu1 current` [A], `mfc1 counter` [mLn]
  (Gaszaehler), `mfc1 flow` [mL/min], microGC `gc_H2`, `gc_CO2`, ... Zweikammer: `ph_z2`, `temperature_z2`.

## 4. Zielablauf

1. Chemiker fuellt die Vorlage wie bisher in Excel aus, speichert sie.
2. Im Frontend beim Anlegen eines Runs: "Versuchsplan (.xlsx) hochladen". Das Frontend prueft Vorlagenversion,
   liest die Zellen laut Zuordnungsdatei und zeigt eine Tabelle: Zelle, Bezeichnung, gelesener Wert, Ziel-
   parameter, Routine. Nicht zuordenbare Werte werden angezeigt und mitgespeichert, aber nicht gesendet.
3. Das Routinenformular wird vorbelegt. Der Chemiker prueft, aendert bei Bedarf, drueckt Start. Kein Autostart.
4. Die Datei wird mit dem Run gespeichert (Frontend-Datenbank oder Upload-Ordner, Dateiname + Run-ID).
5. Nach dem Lauf: "Versuchsplan befuellen". Das Frontend holt die Messwerte im Zeitraster vom Backend (neuer
   Endpunkt, Abschnitt 6), schreibt sie in eine KOPIE der Datei (`<name>_LABS.xlsx`) und bietet sie zum
   Download an. Das Original bleibt unveraendert; so gehen Formeln, Formate und Diagramme nie verloren.
6. Die befuellte Kopie liegt zusaetzlich im Laufordner des Backends neben bericht.html (per API hochgeladen oder
   das Backend schreibt sie selbst, siehe Abschnitt 6, Variante B).

## 5. Zuordnung Vorlage -> LABS (Eingabe)

Messstand I, Kolbe-Elektrolyse (Routinen `kolbe_elektrolyse_gc` / `kolbe_elektrolyse_2k`, `kolbe_n2_spuelung`,
`kolbe_pumpe_zeit`):

| Zelle | Bezeichnung in der Vorlage | Einheit | LABS-Parameter | Routine | Bemerkung |
|---|---|---|---|---|---|
| `Setup_parameter!B1` | Experiment number | - | `versuch` | kolbe_elektrolyse_gc, _2k | auch fuer die Run-ID und den GC-Dateinamen |
| `Setup_parameter!B18` | flow rate | mL/min | `rate` | kolbe_elektrolyse_*, kolbe_pumpe_zeit | |
| `Setup_parameter!B30` | voltage/current | mA | `current` | kolbe_elektrolyse_* | Vorlage in mA, LABS je nach Treiber in A: Umrechnung in der Zuordnungsdatei (`faktor: 0.001`) pruefen |
| `Setup_parameter!B33` | Duration (Formel) | min | `minutes` | kolbe_elektrolyse_* | Formelzelle, braucht gespeicherten Wert; 26174: 219 min |
| `Setup_parameter!B29` | Measurement mode | - | - | - | nur pruefen: "galvanostatic" erwartet, sonst Warnung |
| `Setup_parameter!B9` | one- or two-chamber | - | - | Routinenwahl | "One-Chamber" -> kolbe_elektrolyse_gc, "Two-Chamber" -> kolbe_elektrolyse_2k |
| `Analytics!B12` | N2 purging before electrolysis | min | `minutes` | kolbe_n2_spuelung | |
| `Analytics!B13` | N2 purging after electrolysis | mLn | - | - | Volumen statt Zeit; Routine mit Zaehler-Stopp gibt es noch nicht |
| `Analytics!B3` | microGC method | - | `method` | kolbe_gc_messung | Name muss am GC existieren |
| `Analytics!B7` | Number of measurements | - | - | - | gc_minutes-Raster ableiten? Offen (Abschnitt 8) |
| - | - | - | `max_voltage` | kolbe_elektrolyse_* | steht NICHT in der Vorlage; Standardwert aus der Zuordnungsdatei, Zelle in der Vorlage ergaenzen |
| - | - | - | `gc_minutes` | kolbe_elektrolyse_gc | nicht in der Vorlage; Vorschlag: Zeitraster aus `Exp_protocol!A3:A17` uebernehmen ("0;10;20;...;219") |

Messstand II, Ansetzen der Loesung (Routine `ansatz`, docs/messstand2_zugabe_06-11-2026.md Abschnitt 9):

| Zelle | Bezeichnung | Einheit | LABS-Parameter | Bemerkung |
|---|---|---|---|---|
| `Exp_preparation!B5` | Water (part 1) | mL | `vol_wasser` | Formel Pool/2 |
| `Exp_preparation!B6` | n-butanoic acid | mL | `vol_saeure1` | Formel; Port aus der Zuordnungsdatei (welche Saeure an welchem Ventil-Port) |
| `Exp_preparation!B7` | n-hexanoic acid | mL | `vol_saeure2` | dito |
| `Exp_preparation!B8` | n-octanoic acid | mL | (dritte Saeure) | `ansatz` hat heute nur zwei Saeuren-Felder: Routine um `port_saeure3`/`vol_saeure3` erweitern oder `add_recipe` direkt mit freier Rezeptzeile |
| `Exp_preparation!B12` | NaOH (10 M) | mL | `vol_naoh` | in der Vorlage Handeintrag; wird spaeter von der pH-Schleife ersetzt |
| `Exp_preparation!B17` | Na2SO4 | g | - | Feststoff, LABS dosiert nur Fluessigkeiten: entweder Stammloesung (dann Volumen = g / Konzentration der Stammloesung, Faktor in der Zuordnungsdatei) oder Handzugabe |
| `Setup_parameter!B27` | Pool volume | mL | `zielvolumen` | |
| `Setup_parameter!B26` | pH value | - | Ziel-pH der pH-Schleife | Baustein noch nicht gebaut |

Die Vorlage rechnet die Saeuren mit festem Verhaeltnis 3:8:1 (Hinweis in D6:D8), obwohl B22 ein frei
eingebbares Verhaeltnis enthaelt. Das ist ein Punkt fuer die Chemiker, nicht fuer LABS; LABS nimmt die Werte
aus B6:B8 so, wie Excel sie ausgerechnet hat.

## 6. Zuordnung LABS -> Vorlage (Ausgabe nach dem Lauf)

Blatt `Exp_protocol`, eine Zeile je Zeitpunkt aus Spalte A (0, 10, ..., 219 min, Zeile 3 bis 17):

| Spalte | Ueberschrift | Observable (Messstand I) | Rechenweg |
|---|---|---|---|
| B | cumul. Gas vol. [mln N2] | `mfc1 counter` | Zaehlerstand zum Zeitpunkt minus Stand bei t=0 |
| C | pH | `liquiline ph_ch1_value` | Wert zum Zeitpunkt (naechster Messwert, max. 30 s Abstand) |
| D | conductivity [mS/cm] | `liquiline conductivity_value` | dito |
| E | cumul. H2 vol. [mln N2] | `gc_H2` x Gasvolumen | nur wenn GC laeuft; sonst leer lassen |
| F | cell potential [V] | `psu1 voltage` | dito; bei 2K/3 Zellen psu1..3 in Beobachtungen oder eigene Spalten |
| G | Temp [degC] | `liquiline temperature_value` | dito |
| H | Observations | - | frei lassen; optional Hinweis "aus LABS-Lauf <run-id> befuellt am <Datum>" |

Zeitbezug: t=0 ist der Start der Routine `kolbe_elektrolyse_*` (Startzeit aus `lauf.json`), nicht der Start
der Spuelung davor. Die Zeile "Before" (Zeile 2) bekommt pH/Leitfaehigkeit aus dem letzten Wert vor dem Start
(z.B. aus dem Spuellauf), "After Electrolysis" den letzten Wert des Elektrolyselaufs. "After Acidification" und
"After Purging" bleiben Handarbeit, bis es Routinen dafuer gibt.

Weitere Zellen:

| Zelle | Inhalt | Quelle |
|---|---|---|
| `Setup_parameter!B2` | Experiment date | Startdatum aus `lauf.json` |
| `Setup_parameter!B5` | Operator | angemeldeter Frontend-Benutzer, falls leer |
| `Exp_preparation!B12` | NaOH (10 M) tatsaechlich | spaeter: `dosed_ml` der pH-Schleife |
| `Exp_preparation!B18` | final pH | letzter pH vor dem Elektrolysestart |
| `Exp_preparation!B19` | final conductivity | dito |

Technische Varianten fuer die Messwerte:

- **Variante A (empfohlen):** neuer Backend-Endpunkt `GET /api/run_table?experiment=<run-id>&takt=600`
  (oder `&zeitpunkte=0;10;20;...`), der die Tabellenfunktion aus tools/auswertung.py wiederverwendet und
  JSON liefert. Das Frontend schreibt damit die Excel-Kopie. Vorteil: Excel-Code nur an einer Stelle
  (Frontend, openpyxl schon da), Backend bleibt schlank.
- **Variante B:** das Backend bekommt openpyxl, speichert die hochgeladene Datei im Laufordner und befuellt sie
  nach `Finished` selbst (wie heute bericht.html ueber auswertung.py). Vorteil: Datei liegt automatisch beim
  Lauf; Nachteil: Excel-Logik doppelt (Lesen im Frontend, Schreiben im Backend) oder der Upload muss durchs
  Backend.

Ein Versuch besteht aus mehreren Laeufen (Spuelen, N2, Elektrolyse, Gaszaehlen). Die Vorlage wird deshalb
nicht an einen Run gebunden, sondern an die Versuchsnummer (`Setup_parameter!B1` = Parameter `versuch`).
Beim Befuellen sucht LABS alle Laeufe mit diesem `versuch`-Wert am betreffenden Tag.

## 7. Zuordnungsdatei (Vorschlag)

Eine YAML-Datei pro Vorlagenversion im Frontend-Repo, z.B. `app/excel/vorlagen/kolbe_flow_v1.yml`:

    vorlage:
      name: Kolbe Flusszelle
      version_zelle: Setup_parameter!F1      # neue Zelle in der Vorlage, Inhalt z.B. "LABS-v1"
      version: LABS-v1
    eingabe:
      - zelle: Setup_parameter!B18
        parameter: rate
        routinen: [kolbe_elektrolyse_gc, kolbe_elektrolyse_2k, kolbe_pumpe_zeit]
        einheit: mL/min
      - zelle: Setup_parameter!B30
        parameter: current
        routinen: [kolbe_elektrolyse_gc, kolbe_elektrolyse_2k]
        einheit: mA
        faktor: 0.001                        # falls LABS A erwartet - pruefen
      - zelle: Setup_parameter!B33
        parameter: minutes
        routinen: [kolbe_elektrolyse_gc, kolbe_elektrolyse_2k]
        formel: true                         # gespeicherter Wert noetig
    ausgabe:
      blatt: Exp_protocol
      zeit_spalte: A
      zeit_zeilen: 3-17
      spalten:
        B: { observable: "mfc1 counter", art: differenz_zu_t0 }
        C: { observable: "liquiline ph_ch1_value", art: wert }
        D: { observable: "liquiline conductivity_value", art: wert }
        F: { observable: "psu1 voltage", art: wert }
        G: { observable: "liquiline temperature_value", art: wert }
      zellen:
        Setup_parameter!B2: { quelle: startdatum }

Regeln: Fehlt die Versionszelle oder stimmt die Version nicht, wird die Datei abgelehnt. Fehlt ein Wert, wird
der Parameter nicht vorbelegt (kein stiller Standardwert, ausser er steht ausdruecklich als `standard:` in
der Zuordnung). Jede Einheit wird gegen die Einheit der Routine aus `experiment_types` geprueft.

## 8. Offene Fragen (vor Stufe 2 klaeren)

1. Welche Vorlage ist die aktuelle Master-Vorlage, und darf eine Versionszelle hinein? (Vorschlag F1 in
   `Setup_parameter`.) Gibt es weitere Vorlagen (Batch, Zweikammer) mit anderem Aufbau?
2. Strom in mA (Vorlage) gegen Einheit von `current` in LABS: pruefen, wie psu1 den Wert erwartet.
3. `max_voltage` und `gc_minutes` stehen nicht in der Vorlage: Zellen ergaenzen oder Standardwerte?
4. Gaszaehler: ist `mfc1 counter` kumuliert ab Backend-Start oder ab Lauf? Bestimmt den Rechenweg in Spalte B.
5. Leitsalz als Feststoff: Stammloesung fuer den Ansatz, oder bleibt die Einwaage Handarbeit?
6. Drei Saeuren in der Vorlage, zwei in `ansatz`: Routine erweitern.
7. Wer "besitzt" die Datei nach dem Lauf: Download aus dem Frontend reicht, oder soll sie zusaetzlich auf
   einem Netzlaufwerk landen?
8. Vorlage mit Formeln ohne gespeicherte Werte (z.B. aus LibreOffice ohne Neuberechnung): ablehnen oder die
   Formeln in Python nachrechnen? Vorschlag: ablehnen mit klarer Meldung.

## 9. Stufenplan

| Stufe | Inhalt | Ergebnis | Aufwand |
|---|---|---|---|
| 0 | Kommandozeilenwerkzeug `tools/excel_lesen.py <datei.xlsx> [zuordnung.yml]`: liest die Vorlage, zeigt Zelle/Wert/Parameter als Tabelle, meckert bei fehlender Version oder fehlenden Werten | zeigt in einer Stunde, ob die Zuordnung traegt; dient spaeter als Testbasis | halber Tag |
| 1 | Frontend: Upload beim Anlegen eines Runs, Anzeige der gelesenen Werte, Ablage der Datei zum Run | Chemiker sieht, was LABS gelesen hat | halber bis ein Tag |
| 2 | Vorbelegen des Routinenformulars, Routinenwahl nach Zellen (Kammern), Einheitenpruefung | kein Abtippen mehr | halber bis ein Tag |
| 3 | Backend-Endpunkt `run_table` (Variante A), Frontend befuellt die Kopie, Download; Ablage im Laufordner | `Exp_protocol` automatisch gefuellt | ein bis zwei Tage |
| 4 | Spaeter: `ansatz` aus `Exp_preparation`, NaOH-Verbrauch aus der pH-Schleife zurueckschreiben | Messstand II angebunden | nach der pH-Schleife |

Tests ohne Hardware: die vier Dateien in docs/versuchsplanung_26174-26177.zip als Testdaten fuer Stufe 0 bis 2;
fuer Stufe 3 ein beliebiger alter Laufordner unter logs/ (values.json + lauf.json) plus Dummy-Backend.

## 10. Risiken

- **Verschobene Zeilen in der Vorlage** sind die Hauptgefahr: ohne Versionszelle liest LABS stumm die falsche
  Zelle. Darum Versionspruefung und zusaetzlich die Bezeichnung in Spalte A gegen den erwarteten Text pruefen
  (z.B. "flow rate" neben B18).
- **Formelzellen ohne Wert** (Abschnitt 2).
- **Einheiten** (mA/A, min/s, mL/uL): jede Zuordnung traegt ihre Einheit, das Frontend vergleicht mit der
  Routine und bricht bei Abweichung ab.
- **Ein Excel, viele Laeufe:** die Zuordnung ueber `versuch` muss eindeutig sein; gleicher Versuchsname an
  zwei Tagen ist heute schon moeglich.
- **Schreibende Excel-Bibliothek** verliert Diagramme und manche Formatierungen. Darum nur in eine Kopie
  schreiben; das Original bleibt beim Chemiker.
