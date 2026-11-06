# Messstand II - Zugabe ueber das Auswahlventil (06.11.2026)

Erster Baustein fuer das automatische Ansetzen der Reaktionsloesung (Anforderung vom 06.11.2026):
EINE Zugabe aus einem Port des 16-Wege-Ventils in den Reaktor, gefolgt vom Spuelen mit Wasser.
Noch NICHT gebaut: die Rezeptrechnung (Volumina aus Konzentrationen, Blatt 2 der Exceltabelle) und die
pH-Schleife. Beide bauen auf diesem Baustein auf.

Stand: am PC gegen die Dummys getestet (Abschnitt 6). Am Geraet noch NICHT gelaufen.

## 1. Aufbau und Prinzip

    Port 1 Wasser, Port 2..16 Chemikalien  ->  valve1  ->  Schlauch  ->  pump1  ->  Reaktor

Der Schlauch zwischen Ventil und Reaktor (einschliesslich Pumpenschlauch) fasst das **Totvolumen**.
Er ist zwischen zwei Zugaben immer mit Wasser gefuellt. Eine Zugabe aus Port P laeuft so:

1. Pumpe steht. Ventil auf P. Die Position wird zurueckgelesen.
2. Pumpe foerdert das Volumen V. Vorne laeuft dabei das Wasser aus dem Schlauch in den Reaktor,
   die Chemikalie steht noch im Schlauch.
3. Pumpe steht. Ventil auf Wasser (Port 1).
4. Pumpe foerdert die Spuelmenge. Das schiebt die Chemikalie in den Reaktor, danach steht wieder
   Wasser im Schlauch.

In den Reaktor gelangen also **V + Spuelmenge**, davon V Chemikalie.
Spuelmenge = `dead_volume_ml` x `flush_factor` (vorlaeufig 0,5 mL x 1,5 = 0,75 mL).
Zwei Chemikalien treffen sich nie im Schlauch, erst im Reaktor.

Das Ventil schaltet nur bei stehender Pumpe. Port 1 muss Wasser sein: dorthin faehrt das Ventil beim
Backend-Start.

## 2. Einstellungen (config.messstand2.yml, bei pump1 unter `dosing:`)

Alle Werte sind Pflicht. Fehlt einer, wird die Pumpe beim Start nicht angelegt (Fehlermeldung im Log
und im Geraetestatus) - lieber kein Start als still falsche Konzentrationen.

| Schluessel | Wert | Bedeutung |
|---|---|---|
| `valve` | valve1 | Name des Ventils unter devices |
| `water_port` | 1 | Port mit Wasser |
| `dead_volume_ml` | 0.5 | Totvolumen Ventil -> Reaktor. VORLAEUFIG, am Aufbau ausmessen (Abschnitt 5) |
| `flush_factor` | 1.5 | Spuelmenge als Vielfaches des Totvolumens (Anforderung: 1 bis 2) |
| `min_rate_ml_min` | 0.018 | kleinste Flussrate (Kopf DG 6 Rollen, Schlauch Nr. 5 = 1,65 mm) |
| `max_rate_ml_min` | 5.0 | groesste Flussrate; am Geraet bis 5 mL/min getestet, Handbuch nennt 18 |
| `min_dose_seconds` | 10 | kleine Volumen laufen so langsam, dass die Pumpe mindestens 10 s foerdert |

Optional: `valve_timeout_s` (20, so lange darf das Ventil bis zur richtigen Position brauchen) und
`settle_s` (0,5, Pause zwischen Ventil und Pumpenstart).

Flussrate: automatisch = Volumen / 10 s, begrenzt auf min/max. Beispiele: 50 uL -> 0,3 mL/min,
200 uL -> 1,2 mL/min, ab 0,83 mL -> 5 mL/min (50 mL dauern dann 10 Minuten).

## 3. Routinen

Volumen immer in mL: 0.2 = 200 uL, 0.05 = 50 uL.

| Routine | Parameter | Was passiert |
|---|---|---|
| `zugabe` | port, volume | eine Zugabe aus `port` mit Spuelen (Abschnitt 1). port = 1: nur Wasser, kein Spuelschritt |
| `spuelen` | volume | nur Wasser aus Port 1: Schlauch fuellen, nach einem Abbruch spuelen, von Hand auffuellen |
| `dosiertest` | volume, repeats, pause | `repeats` mal `volume` Wasser, dazwischen `pause` Sekunden - zum Auswiegen |

Im Monitoring: `dosing_step` (aktueller Schritt als Text), `dosing_flow_ml_min` (Flussrate, solange die
Pumpe foerdert, sonst 0), `dosed_ml` (Chemikalie), `flushed_ml` (Wasser), `delivered_ml` (Summe in den
Reaktor), `valve1 position`.

Jede Routine ist im Schrittmodus EIN Schritt: senden, Start druecken, laeuft bis zum Ende durch.

## 4. Was bei Fehlern und bei "Stop Experiments" passiert

- **Ventil erreicht die Position nicht / antwortet nicht:** Die Pumpe startet nicht, der Lauf endet als
  Failed.
- **Ungueltige Eingabe** (Port, den es nicht gibt, Volumen 0, Flussrate ausserhalb der Grenzen): Lauf
  endet sofort als Failed, nichts bewegt sich. Die Meldung steht im Log und in `dosing_step`.
- **Stop Experiments mitten in der Zugabe:** Die Pumpe haelt an. Im Log steht dann als Fehler, dass
  im Schlauch noch Chemikalie von Port P steht. Vor dem naechsten Ansatz `spuelen` laufen lassen
  (Auslauf dabei in den Abfall halten, wenn die Chemikalie nicht in den Reaktor soll).
- Nach Failed oder Stop wie immer: Backend neu starten.

## 5. Erster Test am Geraet (Reihenfolge)

Alles zuerst nur mit Wasser an ALLEN benutzten Ports.

1. `git pull`, Backend neu starten, im Frontend "Download Experiments from Station".
   Im Geraetestatus muessen valve1 und pump1 "Ready" sein.
2. Schlaeuche fuellen: Auslauf in ein Becherglas, `spuelen` mit z.B. 5 mL, bis keine Luft mehr kommt.
   Fuer jeden Chemikalien-Port einmal `zugabe` (port, 2 mL), damit auch dessen Zuleitung gefuellt ist.
3. Ventil pruefen: `zugabe` mit port 3 und 0,2 mL. Am Ventil mitlesen: 3, dann zurueck auf 1.
   Die Pumpe darf nur laufen, waehrend das Ventil steht.
4. Dosiergenauigkeit auswiegen (Waage, Becherglas, Wasser 1 g = 1 mL):
   `dosiertest` mit volume 0.2, repeats 10, pause 10 und danach volume 0.05, repeats 10, pause 10.
   Notieren: Einzelwerte oder wenigstens Summe und Streuung.
   Erwartung: Die Pumpe hat 6 Rollen und foerdert mit diesem Schlauch etwa 0,18 mL pro Umdrehung,
   also rund 30 uL pro Rollensegment. 50 uL sind damit weniger als zwei Segmente - die Einzeldosis
   kann deutlich streuen. Ist die Streuung zu gross: duennerer Schlauch (z.B. 0,51 mm) oder der
   Dosiermodus der Pumpe (WD/WSD, 10 uL Aufloesung, braucht "Dispensing" am Geraet; im Treiber noch
   nicht benutzt).
5. Totvolumen bestimmen: Schlauch mit Wasser fuellen, an einen Port eine gefaerbte Loesung (oder
   verduennte Lauge und pH messen). `zugabe` mit kleinem Volumen und beobachten, nach wie viel
   gefoerdertem Volumen die Farbe am Auslauf ankommt. Den Wert als `dead_volume_ml` eintragen.
   Faustwert zum Gegenpruefen: Schlauch 1,65 mm Innendurchmesser fasst 2,1 uL pro mm, 0,5 mL sind
   also nur etwa 23 cm.
6. Laufzeiten im Backend-Log pruefen: Zeile "Laufzeit Soll x s / Ist y s" je Pumpschritt. Abweichungen
   ueber 0,1 s melden.

## 6. Technik (fuer die Weiterarbeit)

- `backend/drivers/valve_dosing.py`: `ValveDosingMixIn` + reine Rechenfunktionen (`choose_rate`,
  `plan_addition`, `plan_totals`). Der Pumpentreiber `longer_bt100_1f.py` bindet das MixIn ein und
  liefert `_dosing_pump_start` / `_dosing_pump_stop`. Ohne Abschnitt `dosing:` verhaelt sich die Pumpe
  wie bisher. Der Kern (Setup, Experiment) ist unveraendert, Messstand I ist nicht betroffen.
- Muster wie beim microGC: die Pumpe ist das einzige kommandierte Geraet, bleibt fuer die ganze Zugabe
  Busy (Bedingung `dosing == finished`) und stellt das Ventil ueber `link_devices` selbst. Darum steht
  valve1 in den Routinen nur unter observables.
- Zeitsteuerung: Laufzeit = Senden des Start- bis Senden des Stoppbefehls (`Command.time`), kein
  periodisches Abfragen der Pumpe waehrend der Zugabe.
- Beim Abbruch/Fehler schickt der Baustein KEINEN eigenen Pumpenstopp: das macht der Abschaltpfad
  (`final_commands`). Zwei Stoppbefehle direkt hintereinander vertauschen die Antworten und kosten die
  Verbindung (am Dummy gesehen, Begruendung im Code bei `_dosing_close`).
- Tests: `backend/test/test_valve_dosing.py` (39 Tests, ohne Hardware).
- Dummy-Umgebung am PC: `LABS-DeviceDummys/longer_bt100_1f.py` (Port 12363, rechnet das gefoerderte
  Volumen mit) und ein zweites Knauer-Ventil (Port 12364, nur 6 Positionen).
  `config.messstand2.dummy.yml` wird aus `config.messstand2.yml` erzeugt (nur die drei Adressen):

      sed -e 's|address: 10.42.0.103:10001|address: 127.0.0.1:12364|' \
          -e 's|address: /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BG01X3TF-if00-port0|address: 127.0.0.1:12363|' \
          -e 's|address: /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BG02Q3TM-if00-port0|address: 127.0.0.1:12353|' \
          config.messstand2.yml

  Start: erst `python main.py` in LABS-DeviceDummys, dann `python main.py config.messstand2.dummy.yml`.
- Am Dummy gelaufen (06.11.2026): Zugabe 50 uL / 200 uL / 2 mL, dosiertest 3 x 50 uL, spuelen 1 mL
  (Laufzeiten Soll/Ist auf 0,02 s, Volumen laut Dummy auf 1 uL); Stop mitten in der Dosis; Port 9 an
  einem 6-Port-Ventil; stummes Ventil.

## 7. Bekannte Grenzen und Hinweise

Diese Punkte sind beim Bauen und Testen aufgefallen. Sie sind keine Fehler im Code, muessen aber beim
Labortest und bei den naechsten Bausteinen beachtet werden.

**Dosiergenauigkeit**

- **Kleine Dosen koennen streuen.** Die Pumpe ist eine Schlauchpumpe mit 6 Rollen. Mit dem jetzigen
  Schlauch (Nr. 5, 1,65 mm) foerdert sie rechnerisch etwa 0,18 mL pro Umdrehung, also rund 30 uL pro
  Rollensegment (abgeleitet aus dem Bereich 0,018-18 mL/min bei 0,1-100 U/min). Eine 50-uL-Dosis ist
  weniger als zwei Segmente; wie viel wirklich kommt, haengt davon ab, wo die Rollen gerade stehen.
  200 uL sind knapp sieben Segmente und damit deutlich unkritischer. Das Auswiegen (Abschnitt 5,
  Punkt 4) zeigt, wie gross die Streuung wirklich ist.
- **Abhilfe, falls die Streuung zu gross ist:** duennerer Schlauch (kleineres Volumen je Segment) oder
  der Dosiermodus der Pumpe (Befehle WD/WSD, 10 uL Aufloesung, braucht die Einstellung "Dispensing" am
  Geraet). Der Dosiermodus ist im Treiber noch nicht benutzt.
- **Fuer die pH-Schleife ist die Streuung weniger schlimm als fuer das Rezept:** die Schleife misst nach
  jeder Zugabe den pH und regelt nach. Bei den Rezeptzugaben (Leitsalz, Carbonsaeure, NaOH) geht ein
  Dosierfehler dagegen direkt in die Konzentration ein - die sind aber gross (mL statt uL).
- **Die Dosierung ist zeitgesteuert.** Volumen = Flussrate x Laufzeit. Die Laufzeit stimmt am Dummy auf
  0,02 s. Ob die Flussrate der Pumpe stimmt, haengt an der Schlauchkalibrierung der Pumpe selbst.
- **Grosse Volumen dauern.** Bei hoechstens 5 mL/min braucht 50 mL zehn Minuten. `max_rate_ml_min`
  kann erhoeht werden, sobald am Geraet eine hoehere Rate getestet ist (Handbuch: bis 18 mL/min).

**Totvolumen und Spuelen**

- **Das Reagenz kommt erst mit dem Spuelwasser im Reaktor an.** Nach Schritt 2 steht es noch im
  Schlauch. Ist `dead_volume_ml` zu klein eingetragen, bleibt ein Teil der Chemikalie im Schlauch und
  kommt erst mit der NAECHSTEN Zugabe - die Konzentrationen stimmen dann nicht. Lieber etwas zu gross
  als zu klein.
- **0,5 mL sind vermutlich zu knapp.** Der Schlauch mit 1,65 mm Innendurchmesser fasst etwa 2,1 uL pro
  mm; 0,5 mL entsprechen nur rund 23 cm zwischen Ventil und Reaktor, einschliesslich Pumpenschlauch.
  Unbedingt ausmessen (Abschnitt 5, Punkt 5).
- **Das Spuelwasser landet im Reaktor** und zaehlt zum Gesamtvolumen. Das ist gewollt (Wasser ist das
  Loesungsmittel), muss aber in der Rezeptrechnung beruecksichtigt werden.
- **Die pH-Schleife gibt vor allem Wasser zu.** Jeder 50- oder 200-uL-Schritt bringt 0,75 mL
  Spuelwasser mit. Zwanzig Schritte sind 15 mL. Der naechste Baustein muss vor jedem Schritt pruefen,
  ob noch Platz bis zum Zielvolumen ist.
- **Die Schlaeuche muessen luftfrei sein.** Eine Luftblase nimmt Platz weg, es kommt weniger an als
  berechnet. Vor dem ersten Lauf alle benutzten Zuleitungen und den Schlauch zum Reaktor fuellen.
- **Der Auslauf im Reaktor:** haengt er frei ueber der Fluessigkeit, kann ein Tropfen (30-50 uL) am
  Schlauchende haengen bleiben. Das Schlauchende sollte eintauchen oder die Gefaesswand beruehren.

**Abbruch und Fehler**

- **Nach "Stop Experiments" oder einem Fehler mitten in der Zugabe steht Chemikalie im Schlauch.**
  Das Backend meldet das als Fehler im Log ("im Schlauch steht noch Reagenz von Port P"). Vor dem
  naechsten Ansatz `spuelen`. Das Ventil bleibt in diesem Fall auf dem Chemikalien-Port stehen; beim
  Backend-Neustart faehrt es auf Port 1.
- **Nach Failed oder Stop muss das Backend neu gestartet werden** - wie bei allen Routinen.
- **Ein leerer Vorrat wird noch NICHT erkannt.** Die Pumpe foerdert dann Luft, das Backend merkt es
  nicht. Erst die pH-Schleife soll abbrechen, wenn der pH auf Zugaben nicht reagiert.
- **Die Fuellstaende und das Reaktorvolumen werden nicht gemessen**, nur gerechnet.

**Test und Dummys**

- **Am Geraet ist dieser Baustein noch nicht gelaufen.** Getestet ist die Logik, nicht die Mechanik.
- **Das Dummy-Ventil hat nur 6 Positionen.** Ports 7-16 sind erst am echten Ventil pruefbar (der
  Treiber liest die Anzahl der Positionen beim Start vom Ventil).
- **Wie lange das echte Ventil zum Schalten braucht, ist nicht gemessen.** Der Baustein fragt die
  Position bis zu 20 s lang ab (`valve_timeout_s`), bevor er aufgibt.

## 8. Entscheidungen und offene Fragen

Mit Rafael am 06.11.2026 festgelegt:

- Wasser liegt auf Port 1. Die uebrigen Ports sind frei waehlbar und stehen spaeter in der Konfiguration.
- Die pH-Elektrode kommt an der Liquiline auf AI 1 (stellt Rafael am Geraet ein).
- Der Reaktor steht auf einer Ruehrplatte, die von selbst laeuft; LABS steuert sie nicht.
- Das Totvolumen wird gemessen; bis dahin gelten 0,5 mL aus der Anforderung.
- pH-Schleife: vier Stufen wie in der Anforderung (stark/200 uL, stark/50 uL, schwach/200 uL,
  schwach/50 uL). Ist der Ziel-pH danach nicht erreicht, macht sie in der feinsten Stufe weiter, bis
  das Zielvolumen erreicht ist, und stoppt dann mit Meldung.

Fragen an den Chemiker (fuer Rezept und pH-Schleife, nicht fuer diesen Baustein):

1. Blatt 2 der Standard-Exceltabelle, damit die Volumenrechnung der Standardrechnung entspricht.
2. Schritt "50 % des Loesungsmittels, wenn noch nicht erreicht": mit Wasser auffuellen, bis das Gefaess
   zur Haelfte des Gesamtvolumens gefuellt ist?
3. Carbonsaeuren: Reinstoff oder Loesung, welche Konzentration, wie viele verschiedene pro Ansatz?
4. Uebliches Gesamtvolumen und maximales Volumen des Gefaesses?
5. Wartezeit nach einer Zugabe: feste Zeit (z.B. 30 s) oder warten, bis sich der pH nicht mehr aendert?
6. Welche vier pH-Reagenzien? Ist die starke Base dieselbe 10 M NaOH wie bei der Neutralisation?
7. Spuelmenge: Start mit dem 1,5-fachen Totvolumen in Ordnung?
8. Ziel-pH bei vollem Zielvolumen nicht erreicht: Fehlermeldung, oder gilt die Loesung trotzdem als fertig?
9. Ist der Lauf nach dem Ansetzen zu Ende, oder soll die Loesung spaeter automatisch weitergepumpt werden?

Noch zu tun:

- pH-Elektrode an der Liquiline auf AI 1 legen (Setup/Outputs/Modbus/AI 1), dann in
  config.messstand2.yml unter liquiline/channels statt `ai1: 0` einen Namen wie `ph: 0` eintragen.
- Naechste Bausteine: festes Rezept (Leitsalz, Wasser, Carbonsaeuren, NaOH, Auffuellen) mit
  Volumenbudget, danach die pH-Schleife (Abbruch, wenn der pH nicht reagiert).
- In der Anforderung ist vertauscht: Saeure SENKT den pH, Base HEBT ihn.
