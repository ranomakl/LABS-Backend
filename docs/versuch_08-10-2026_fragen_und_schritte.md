# Laborversuch 08.10.2026 - Kolbe-Elektrolyse im Flow: Fragen und Einzelschritte

Grundlage: docs/Maximal_Workflow_-_Kolbe_electrolysis_-_Flow.pdf (Max Pohl, Version 2).
Stand 07.10.2026. Vereinbart: das Backend faehrt EINZELNE Schritte, die der Reihe nach von Hand
angestossen werden, kein durchgeschriebener Gesamtablauf. Werte werden beim Start eingegeben.

Das Backend kann vier Stellen des Workflows uebernehmen: Netzteil (DC source), Pumpe,
Bronkhorst (Gaszaehler, "MFM" im Workflow) und microGC. Nicht im Backend, bleibt Handarbeit:
Loesungen, Reaktor, Ruehrer (800 rpm), Gasbeutel, N2-Haehne, Dichtheitstest, Ansaeuern,
Spuelen mit Cyclohexan/Wasser/Aceton, Probenahme. pH/Leitfaehigkeit/Temperatur von Hand,
solange der Liquiline pausiert (enabled: false in config.yml).


## Offene Fragen (bitte vor dem Versuch beantworten)

Stand 08.10. 10:40: Antworten aus dem Versuchsplan eingetragen (vier identische Wiederholungen 26174-26177,
Excel-Blaetter in docs/versuchsplanung_26174-26177.zip, Blattnamen in Klammern). Kernwerte: 550 mA,
219 min, Pumpe 100 mL/min, Bronkhorst 50er als Zaehler, microGC online alle 10/20 min + 3x offline.
Weiter offen (nicht aus den Daten): 7 Polung, 10 Drehrichtung, 14 BakeOut. Frage 1 am 08.10. geklaert: Ventil immer 100 %.

### Bronkhorst - WICHTIGSTER PUNKT

1. Im Workflow ist der Bronkhorst ein reiner GASZAEHLER am Reaktorausgang (Durchfluss ablesen,
   auf 0 mLn zuruecksetzen, Endmenge notieren). Unser Geraet (FG-201CV) ist aber ein REGLER mit
   Ventil. Das Backend setzt den Sollwert beim Start und beim Beenden auf 0 = Ventil ZU. Steht das
   Geraet am Reaktorausgang, ist damit der Gasweg zum Gasbeutel versperrt (Druckaufbau!).
   Wie wird das bisher von Hand gemacht: Sollwert 100 % oder Ventil im Menue auf "offen"?
   -> Antwort (08.10., vom Chemiker bestaetigt): Der Bronkhorst ist reiner GASZAEHLER, das Ventil
      bleibt IMMER auf 100 %. Umgesetzt im Treiber: initial/final_commands oeffnen das Ventil
      (Setpoint 32000 = 50 mL/min), Setpoint wird zur Kontrolle zurueckgelesen (Observable
      'setpoint' = 50.0). Die Setpoint-0-Logik vom 25./31.08. ist raus. stop_mfc schliesst weiterhin
      bewusst das Ventil - im Versuch nicht benutzen.
2. Welcher der beiden Zaehler ist morgen dran: der 50er (BG01B77U, in config.yml) oder der 20er?
   Der 50er war am 07.10. nicht am Pi eingesteckt.
   -> Antwort (aus Versuchsplan, Analytics B11): max. flow rate 50 mLn/min -> der 50er (BG01B77U), wie in config.yml.
3. "Zaehler auf 0 zuruecksetzen" kann der Treiber noch nicht (nur lesen). Soll das eingebaut werden?
   -> Antwort (aus Versuchsplan, Blatt Exp_protocol): Spalte "cumul. Gas vol. [mln N2]" beginnt bei 0 -> JA, Reset
         noetig. Handbuch: Parameter "Reset" (Prozess 115, Parameter 8), Wert 1 = Zaehlerwert nullen; vorher
         "Reset counter enable" (Prozess 104, Parameter 9) pruefen. Alternative ohne Schreibzugriff: Startwert
         merken und im Bericht abziehen (tools/auswertung.py). Am Geraet noch zu verifizieren.

### Netzteil

4. Vorgabe 150 mA/cm^2. Elektrodenflaeche, oder direkt der Strom in A? (Geraet max. 5 A)
   -> Antwort (aus Versuchsplan, Setup_parameter B30/B13): 550 mA galvanostatisch = 50 mA/cm^2 x 11 cm^2
         (NICHT 150 mA/cm^2 wie im Workflow-PDF). Backend-Parameter: current = 0.55 A.
5. Dauer der Elektrolyse? (Zeitgeber kann ins Backend, dann schaltet es selbst ab.)
   -> Antwort (aus Versuchsplan, B33): 219,28 min (fuer 0,5 FE bei z = 1) -> minutes = 219. Protokollzeiten:
         0, 10, 20, 30, 40, 50, 60, 80, 100, 120, 140, 160, 180, 200, 219 min.
6. 48 V Spannungsgrenze bleibt?
   -> Antwort: Nicht im Versuchsplan (dort nur "cell potential [V]" als Messgroesse). 48 V bleibt als
         Geraeteobergrenze; die Zellspannung wird vom Netzteil alle 0,5 s mitgeschrieben.
7. Polung: WE = +, CE = - laut Workflow. Wer prueft die Kabel am Reaktor?
   -> Antwort: Nicht aus den Daten ableitbar. WE und CE sind beide platiniertes Titan, 11 cm^2 (Setup_parameter
         B12-B15). Kabel am Reaktor von Hand pruefen.

### Pumpe

8. Foerderrate in mL/min? (Bereich mit Schlauch 3,2x6,4 mm: 53 bis 533 mL/min)
   -> Antwort (aus Versuchsplan, B18): 100 mL/min (Pumpe LP-WT600-2J, B17). Backend: rate = 100.
9. Die Pumpe laeuft im Workflow mehrfach: Befuellen, Dichtheitstest, Elektrolyse, Nachspuelen
   10 min, Leersaugen, Spuelen mit Cyclohexan. Nur der Elektrolyse-Lauf ueber das Backend,
   oder auch die Spuelschritte als eigene Befehle?
   -> Antwort (teilweise aus Versuchsplan): N2-Spuelung VOR der Elektrolyse 10 min (Analytics B12), NACH der
         Elektrolyse bis 150 mLn N2 (B13), dazu Nachspuelen 10 min laut Workflow. Welche Pumpenlaeufe ueber
         das Backend gehen sollen, steht nicht in den Daten -> Vorschlag: Elektrolyse + Nachspuelen (pumpe_zeit),
         Rest von Hand.
10. Drehrichtung: clockwise = im Uhrzeigersinn (06.10. beobachtet). Foerdert das in der Anlage
    zur Zelle? Beim Einbau pruefen.
    -> Antwort: Nicht aus den Daten ableitbar. Beim Einbau pruefen.

### microGC

11. Online im Bypass (alle 10 min eine Messung waehrend der Elektrolyse) oder nur offline aus
    dem Gasbeutel (3 Messungen je Beutel)?
    -> Antwort (aus Versuchsplan, Analytics B5-B8): BEIDES. Online: Ja. Offline: Ja, 3 Messungen, die letzte
          zaehlt fuer die Quantifizierung. Methode: MicroGC_standard_method_calibrated_0726 (B3), kalibriert
          15.07.2026 (B4). H2-Messung: Nein (B15).
12. Der Workflow benennt Messungen ("25057_10 min") und vergibt Tags ("Kolbe", Initialen). Der
    Treiber startet bisher namenlos (API-Aufruf run statt runWithName). Soll das ergaenzt werden?
    Versuchsnummer morgen?
    -> Antwort (aus Versuchsplan, Setup_parameter B1): Versuchsnummern 26174, 26175, 26176, 26177 (Wiederholung
          1-4). Namensschema wie im Workflow: "<Nummer>_<Zeit> min" bzw. "<Nummer>_rep1..3". -> runWithName
          einbauen (Treiber nutzt bisher run ohne Namen). Tags: "Kolbe", Operator "Max Pohl" (B5).
13. Wenn online: Messung dauert 7,5 min, Intervall 10 min. Backend taktet automatisch, oder jede
    Messung von Hand anstossen?
    -> Antwort (aus Versuchsplan, Exp_protocol Spalte A): Messzeitpunkte 0-60 min alle 10 min, danach alle 20 min
          bis 200, zuletzt 219 min = 15 Messungen. Ob Backend oder Hand steht nicht in den Daten -> Vorschlag:
          Backend taktet nach dieser Liste (Messung dauert 7,5 min, passt in 10 min).
14. BakeOut 20 min am Tagesanfang: von Hand am Geraet oder ueber das Backend (test_microgc_bakeout)?
    -> Antwort: Nicht im Versuchsplan. Offen.

### Messwerte alle 10 Minuten

15. Das Backend schreibt alle Messwerte seiner Geraete laufend ins Versuchslog
    (logs/<Datum>/<Experiment-ID>/values.json). pH, Leitfaehigkeit, Temperatur fehlen
    (Liquiline pausiert) -> von Hand notieren. Reicht das Log, oder zusaetzlich eine
    10-Minuten-Tabelle?
    -> Antwort (aus Versuchsplan, Blatt Exp_protocol): Die 10-Minuten-Tabelle EXISTIERT als Vorlage mit den Spalten
          cumul. Time [min] | cumul. Gas vol. [mln N2] | pH | conductivity [mS/cm] | cumul. H2 vol. | cell potential [V]
          | Temp [C] | Observations, Zeilen "Before", 0...219, "After Electrolysis", "After Acidification",
          "After Purging". Das Backend kann davon Gasvolumen (mfc.counter) und Zellspannung (psu) liefern;
          pH/Leitfaehigkeit/Temperatur von Hand (Liquiline pausiert). tools/auswertung.py --takt 600 gibt das
          Raster; TODO: Exp_protocol direkt aus den Logs befuellen.


## Live-Beobachtung im Frontend (LABS-User-Interface)

Ja, moeglich - mit zwei Einschraenkungen:

- Das Frontend (Flask, liegt auf dem Pi unter ~/LABS/LABS-User-Interface, eigene .venv, laeuft
  aktuell NICHT) hat eine Monitoring-Seite, die einmal pro Sekunde /api/get_updates vom Backend
  abholt und die Werte als Diagramme zeichnet.
- Gezeigt werden NUR die Observables des GERADE LAUFENDEN Experiments. Ist kein Experiment aktiv,
  gibt es nichts zu sehen. Deshalb braucht es fuer die Elektrolyse einen Schritt, der die ganze
  Zeit laeuft (Schritt 5 unten), nicht nur "Netzteil an" und sofort fertig.
- Das Netzteil misst von selbst alle 0,5 s Strom und Spannung, sobald es eingeschaltet ist
  (start_measuring_output). Bronkhorst und Pumpe messen bisher nur auf Anfrage (einmal pro
  Befehl). Fuer die Live-Kurven von Gasfluss/Zaehler/Drehzahl muss im Treiber ein periodisches
  Abfragen ergaenzt werden (repeated_query, wie beim Netzteil) - TODO vor dem Versuch.
  -> ERLEDIGT 08.10. frueh (Commit 300542f, am PC gegen LABS-DeviceDummys getestet, NICHT am
     Geraet): MFC pollt flow+counter 1x/s ab set_setpoint(>0) bis stop_flow, Pumpe pollt
     Drehzahl/Zustand 1x/s ab start_pumping bis stop_pumping. Zusaetzlich zeigt das Frontend
     jetzt eine Zahlentabelle "Current values" mit Versuchszeit ueber den Kurven
     (LABS-User-Interface Commit 738bdca). Details und offene Pruefpunkte:
     docs/uebergabe_live_monitoring_08-10-2026.md

Vor dem Versuch: Frontend starten (flask run in LABS-User-Interface) und die Station mit der
Backend-Adresse (Pi, Port 11123) eintragen.


## Einzelschritte fuer morgen (Vorschlag, Reihenfolge wie im Workflow)

Jeder Schritt = ein Eintrag unter experiments: in config.yml, von Hand angestossen. Werte in
Klammern sind Parameter, die beim Start eingegeben werden. "vorhanden" = Eintrag existiert schon,
"neu" = muss noch angelegt werden.

| Nr | Schritt | Geraet | Backend-Experiment | Status |
|----|---------|--------|--------------------|--------|
| 0 | Alles sicher: Netzteil aus, Pumpe aus, Zaehler lesen | psu, dosing_pump, mfc | passiert automatisch beim Backend-Start | vorhanden |
| 1 | microGC BakeOut 20 min (Tagesanfang) | microgc | test_microgc_bakeout (minutes=20) | vorhanden, Frage 14 |
| 2 | microGC Methode laden | microgc | Teil von test_microgc_run | vorhanden |
| 3 | Pumpe an zum Befuellen/Dichtheitstest (Rate, Minuten) | dosing_pump + mfc lesen | kolbe_pumpe_zeit (rate, minutes) | VORHANDEN 08.10. |
| 4 | N2-Spuelung 10 min: Zaehler auf 0, Pumpe laeuft, Gas live | mfc, dosing_pump | kolbe_n2_spuelung (rate, minutes) | VORHANDEN 08.10. |
| 5 | Elektrolyse: Zaehler 0, Pumpe + Netzteil laufen 'minutes', Netzteil schaltet selbst ab, alles live | psu, mfc, dosing_pump | kolbe_elektrolyse (current 0.55, max_voltage 48, minutes 219, rate 100) | VORHANDEN 08.10. (Logik am Geraet mit 50 mA/2 V/20 s geprueft) |
| 6 | waehrenddessen microGC-Messungen nach Plan (Name "26174_<t> min") | microgc | NICHT ueber das Backend (nur ein Experiment zur Zeit), sondern tools/kolbe_gc_messplan.py im zweiten Terminal | VORHANDEN 08.10. |
| 7 | Netzteil aus (Ende oder Notfall) | psu | stop_psu_output | vorhanden |
| 8 | N2-Spuelen nach Ansaeuern bis ~150 mLn: Zaehler 0, Gas live, ohne Pumpe | mfc | kolbe_gas_zaehlen (minutes) | VORHANDEN 08.10. |
| 9 | Pumpe aus | dosing_pump | stop_wt600 | vorhanden |
| 10 | Nachspuelen 10 min mit Reaktionsloesung | dosing_pump | kolbe_pumpe_zeit (rate 100, minutes 10) | VORHANDEN 08.10. |
| 11 | Offline-Gasbeutel: 3x microGC-Messung ("26174_rep1..3") | microgc | kolbe_gc_messung (method, name, tags) oder kolbe_gc_messplan.py --einzel rep1 | VORHANDEN 08.10. (benannter Lauf am Geraet ungetestet) |

Notfall: stop_psu_output und stop_wt600 sind jederzeit einreihbar; ausserdem /api/stop am Backend
und der Netzschalter am grauen Kasten.

Nicht ueber das Backend (von Hand): Ruehrer, N2-Hahn auf/zu, Gasbeutel auf/zu, Spritze H2SO4,
Spuelen mit Cyclohexan/Wasser/Aceton, Leersaugen, Probenahme, pH/Leitfaehigkeit/Temperatur.

## Code-TODO vor dem Versuch (nach Beantwortung der Fragen)

- [x] Frage 1 geklaert; Bronkhorst initial/final = Ventil offen (08.10.).
- [x] mfc: Zaehler-Reset (reset_counter, am Geraet geprueft) und periodisches Lesen (08.10.).
- [x] dosing_pump: periodisches Lesen; run_for_minutes(rate, minutes) in mL/min (08.10.).
- [x] Schritt kolbe_elektrolyse (current, max_voltage, minutes, rate) mit Abschalten am Ende (08.10.).
- [x] microgc: run_method_named (POST wie runWithName) + tools/kolbe_gc_messplan.py (08.10., am Geraet ungetestet: BakeOut).
- [x] Frontend auf dem Pi laeuft, Station eingetragen (08.10.). Neue Experimente: Routines Administration -> Download Experiments from Station.
