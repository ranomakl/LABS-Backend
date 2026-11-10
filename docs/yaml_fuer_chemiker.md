# YAML fuer Chemiker (10.11.2026)

Wie die Konfigurationsdatei von LABS aufgebaut ist und wie man sie liest und aendert, ohne
Programmcode anzufassen. Beispiele aus config.messstand2.yml (Messstand II).

## 1. Worum es geht

YAML ist eine Textdatei mit Einrueckungen, in der LABS alles Fachliche nachschlaegt: welche Geraete am
Messstand haengen und welche Routinen es gibt. Wer eine Routine aendern oder ein Volumen anpassen will,
aendert diese Datei, nicht den Programmcode.

Am Messstand II heisst die Datei `config.messstand2.yml` und liegt im Ordner LABS-Backend auf dem Pi.
Messstand I hat seine eigene Datei `config.yml`. Das Backend liest die Datei nur beim Start, nach jeder
Aenderung muss es also neu gestartet werden.

YAML ist kein Programm. Es ist eine Liste von Namen mit Werten, so wie ein Laborprotokoll: links steht,
was gemeint ist, rechts der Wert. Alles, was man dafuer braucht, sind fuenf Regeln.

## 2. Die fuenf Grundregeln

**1. Name, Doppelpunkt, Leerzeichen, Wert.** Jede Zeile ist ein Eintrag. Nach dem Doppelpunkt kommt ein
Leerzeichen, dann der Wert.

    water_port: 1
    dead_volume_ml: 0.5

**2. Einrueckung zeigt, was wozu gehoert.** Was unter einem Namen eingerueckt steht, gehoert zu ihm.
Immer Leerzeichen, nie die Tab-Taste. In der LABS-Datei sind es zwei Leerzeichen pro Stufe. Steht hinter
dem Doppelpunkt nichts, folgen die Werte in den eingerueckten Zeilen darunter.

    pump1:
      driver: longer_bt100_1f
      dosing:
        water_port: 1
        dead_volume_ml: 0.5

Hier gehoert `dosing` zu `pump1`, und `water_port` gehoert zu `dosing`.

**3. Listen beginnen mit Strich und Leerzeichen.** Jeder Strich ist ein Eintrag. Eine kurze Liste darf
auch in eckigen Klammern in einer Zeile stehen, die Eintraege durch Komma getrennt.

    observables:
      - [valve1, position, str, ""]
      - [pump1, dosed_ml, float, mL]

**4. Alles hinter einem Rautezeichen ist Kommentar.** Das Backend ueberliest es. Die LABS-Datei nutzt
Kommentare als Laborbuch: Datum, was getestet wurde, was noch offen ist. Eigene Notizen gehoeren genau
dorthin.

    dead_volume_ml: 0.5      # VORLAEUFIG, am Aufbau ausmessen

**5. Zahlen mit Punkt, Text ohne Anfuehrungszeichen.** Dezimaltrenner ist der Punkt, also `0.2` fuer
200 uL. Text steht meist ohne Anfuehrungszeichen. Anfuehrungszeichen braucht man nur, wenn der Wert leer
ist (`""`) oder geschweifte Klammern enthaelt, wie in `"{volume}"`.

## 3. So ist die LABS-Datei aufgebaut

Die Datei hat drei Teile, von oben nach unten: ein paar Grundeinstellungen, die Geraete und die Routinen.

| Teil | Name in der Datei | Was drinsteht | Wer aendert das |
|---|---|---|---|
| Grundeinstellungen | `listen port`, `step_mode`, `log_level` | Netzwerkport des Backends, Schrittmodus an oder aus | selten jemand |
| Geraete | `devices:` | je Geraet ein Name wie `pump1`, sein Treiber, seine Adresse am Pi und Einstellungen wie `dosing:` | bei Umbau, neuem Schlauch, gemessenem Totvolumen |
| Routinen | `experiments:` | je Routine ein Name wie `zugabe`, ihre Parameter, was angezeigt wird und welche Befehle laufen | wer neue Ablaeufe braucht |

Die Geraetenamen sind frei gewaehlt und tauchen in den Routinen wieder auf. `pump1` oben unter
`devices:` ist dieselbe Pumpe, die unten in `zugabe` die Befehle bekommt. Ein Tippfehler im Namen trennt
die beiden, und das Backend laesst die Routine beim Start weg.

Jede Routine besteht aus vier festen Bloecken, die immer da sind, auch wenn sie leer bleiben:

- `parameters:` die Felder, die man im Frontend ausfuellt, mit Typ und Einheit
- `observables:` die Werte, die im Monitoring angezeigt und im Bericht mitgeschrieben werden
- `commands:` die Befehle an die Geraete, in dieser Reihenfolge
- `conditions:` und `stopconditions:` Bedingungen, bei den Messstand-II-Routinen bisher leer

## 4. Eine Routine lesen: die Zugabe

So steht die Routine `zugabe` in der Datei. Sie stellt das Ventil auf einen Port, foerdert ein Volumen
und spuelt mit Wasser nach.

      zugabe:
        conditions:
        stopconditions:
        parameters:
          port: [float, ""]
          volume: [float, mL]
        observables:
          - [valve1, position, str, ""]
          - [pump1, dosing_step, str, ""]
          - [pump1, dosed_ml, float, mL]
          - [pump1, flushed_ml, float, mL]
          - [pump1, delivered_ml, float, mL]
          - [pump1, dosing_flow_ml_min, float, mL/min]
        commands:
          - [pump1, add_from_port, [], { port: "{port}", volume: "{volume}" }]

| Zeile | Bedeutung |
|---|---|
| `zugabe:` | Der Name der Routine. So heisst sie im Frontend. |
| `conditions:` und `stopconditions:` | Leer, hier keine Bedingungen. Die Zeilen bleiben trotzdem stehen. |
| `port: [float, ""]` | Ein Eingabefeld namens port, eine Zahl, ohne Einheit. |
| `volume: [float, mL]` | Ein Eingabefeld namens volume, eine Zahl in mL. |
| `- [valve1, position, str, ""]` | Zeige im Monitoring die Position von valve1 als Text. |
| `- [pump1, dosed_ml, float, mL]` | Zeige den Wert dosed_ml von pump1 als Zahl in mL. |
| `- [pump1, add_from_port, [], {...}]` | Der einzige Befehl: pump1 soll add_from_port ausfuehren. |
| `{ port: "{port}", volume: "{volume}" }` | Die Werte aus den Eingabefeldern werden eingesetzt. |

Die geschweiften Klammern sind Platzhalter. `"{volume}"` heisst: nimm, was im Frontend im Feld volume
eingetragen wurde. Der Name in den Klammern muss genau einem Eintrag unter `parameters:` entsprechen.

Jede Zeile unter `observables:` hat vier Angaben in fester Reihenfolge: Geraet, Messwert, Typ, Einheit.
Beim Typ steht `float` fuer eine Zahl und `str` fuer Text.

## 5. Einen Wert aendern oder eine Routine kopieren

**Einen Wert aendern**, zum Beispiel das gemessene Totvolumen eintragen:

1. Die Datei `config.messstand2.yml` in einem Texteditor oeffnen, nicht in Word.
2. Die Zeile `dead_volume_ml: 0.5` im Block `dosing:` unter `pump1:` suchen.
3. Nur die Zahl ersetzen, mit Punkt als Dezimaltrenner. Die Einrueckung davor nicht anfassen.
4. Im Kommentar dahinter notieren, woher der Wert kommt, mit Datum.
5. Speichern, Backend neu starten, im Frontend "Download Experiments from Station".

**Eine Routine kopieren**, zum Beispiel ein zweites Rezept mit anderen Komponenten:

1. Den ganzen Block der Vorlage markieren, von der Namenszeile bis zur letzten Befehlszeile, und unter
   dem Block `experiments:` noch einmal einfuegen.
2. Der Kopie einen neuen Namen geben. Zwei Routinen mit gleichem Namen ueberschreiben sich, nur die
   letzte bleibt.
3. Parameter, Observables und Befehle anpassen. Jeder Platzhalter in den Befehlen braucht sein
   Eingabefeld unter `parameters:`.
4. Pruefen, dass die Einrueckung der Kopie genau der Vorlage entspricht.
5. Einen Kommentar darueber setzen: Datum, Zweck, Stand des Tests.

Die Routinen `zugabe`, `spuelen`, `dosiertest` und `ansatz` sind gute Vorlagen. Was eine Routine kann,
haengt an den Befehlen, die der Treiber kennt. Fuer die Pumpe am Messstand II sind das `add_from_port`,
`pump_water` und `add_recipe`. Neue Befehle brauchen neuen Programmcode, neue Kombinationen davon nur
einen neuen Eintrag in der Datei.

## 6. Typische Fehler

Die meisten Fehler sind Tippfehler in der Form, nicht im Inhalt. Das Backend meldet sie beim Start im
Log, die Routine fehlt dann im Frontend.

| Fehler | Was passiert | Woran man es erkennt |
|---|---|---|
| Tab statt Leerzeichen eingerueckt | Die Datei laesst sich nicht lesen, das Backend startet nicht | Fehlermeldung mit "tab" und Zeilennummer im Log |
| Eine Stufe zu viel oder zu wenig eingerueckt | Der Eintrag landet beim falschen Block oder die Datei ist ungueltig | Routine fehlt, oder Fehlermeldung mit Zeilennummer |
| Kein Leerzeichen nach dem Doppelpunkt | `volume:0.2` ist ein Name ohne Wert | Routine fehlt oder Wert ist leer |
| Komma statt Punkt in der Zahl | `0,2` wird als Text gelesen, nicht als Zahl | Lauf endet sofort als Failed |
| Geraetename vertippt | `pumpe1` statt `pump1` gibt es nicht | Log: "Experiment ... wird uebersprungen, fehlt: Geraet pumpe1" |
| Platzhalter ohne Parameter | `"{menge}"` im Befehl, aber kein `menge:` unter parameters | Routine fehlt oder Fehler beim Senden |
| Pflichtwert unter `dosing:` geloescht | Die Pumpe wird beim Start nicht angelegt | Geraetestatus rot, Log nennt den fehlenden Schluessel |
| Zwei Routinen mit gleichem Namen | Nur die untere bleibt | Die obere ist im Frontend verschwunden |

Der schnellste Weg, einen Fehler zu finden: Datei schliessen, Backend neu starten und im Terminalfenster
des Starts die Zeilen mit "uebersprungen" oder "Error" lesen. Das Start-Skript zeigt sie am Ende von
selbst an. Danach die genannte Zeile in der Datei mit dem Block darueber vergleichen.

## 7. Checkliste vor dem Neustart

- [ ] Nur Leerzeichen zum Einruecken, keine Tabs
- [ ] Nach jedem Doppelpunkt ein Leerzeichen
- [ ] Zahlen mit Punkt, nicht mit Komma
- [ ] Jeder Platzhalter `"{name}"` hat seinen Eintrag unter `parameters:`
- [ ] Geraetenamen genau so geschrieben wie unter `devices:`
- [ ] Routinenname ist neu und kommt nur einmal vor
- [ ] Aenderung als Kommentar mit Datum notiert
- [ ] Backend neu gestartet und im Startfenster keine Zeile mit "uebersprungen"
- [ ] Im Frontend "Download Experiments from Station" gedrueckt
- [ ] Neue oder geaenderte Routine zuerst nur mit Wasser gefahren
