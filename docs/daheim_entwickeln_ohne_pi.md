# Daheim am PC weiterarbeiten (ohne Pi, ohne Geraete)

Stand 07.10.2026. Alles liegt auf GitHub (Nutzer ranomakl):

| Repo | Inhalt | Branch |
|------|--------|--------|
| LABS-Backend | Twisted-Backend, Treiber, config.yml, tools/, docs/ | main (= netzteil-joyit) |
| LABS-User-Interface | Flask-Frontend (Experimente anlegen, Monitoring-Kurven) | main |
| LABS-DeviceDummys | Simulator fuer die alten Dummy-Geraete (Knauer-Ventile, Ismatec, Omnicoll, TDK-Netzteil, Liquiline) | main |

## Aufbau am PC (drei Terminals)

1. Simulator: `cd LABS-DeviceDummys && python main.py`
2. Backend mit der Simulator-Konfiguration: in LABS-Backend `config.dummy.yml` nach `config.yml`
   kopieren (die echte config.yml dabei NICHT ueberschreiben, vorher wegsichern oder nur im
   Arbeitsbaum, nicht committen), dann `python main.py`. Das Backend lauscht auf Port 11123.
3. Frontend: `cd LABS-User-Interface`, venv anlegen, `pip install -r requirements.txt`,
   `flask db upgrade`, `flask run`. Beim ersten Start wird ein Admin-Konto angelegt, die Zugangsdaten
   stehen in der Konsole. Im Frontend eine Station mit Adresse `127.0.0.1:11123` eintragen.

Danach: Experimenttyp waehlen (z.B. test_psu_output), Werte eingeben, einreihen, Backend auf Start.
Die Monitoring-Seite zeigt die Kurven des laufenden Experiments - mit simulierten Werten.

## Was daheim geht und was nicht

- Geht: Frontend-Entwicklung (z.B. Zahlentabelle neben den Kurven auf der Monitoring-Seite -
  die Daten kommen einmal pro Sekunde ueber /api/get_updates, siehe app/monitoring/views.py und
  app/static/plots.js), Backend-Code ohne Hardware, config.yml-Experimente anlegen und pruefen
  (yaml laden + Verweise, siehe Pruefskript-Idee in den Commits vom 07.10.), twisted.trial-Tests
  unter backend/test/.
- Geht NICHT: echte Geraete. Fuer Joy-IT-Netzteil, Longer-Pumpe, Bronkhorst und microGC gibt es
  keinen Dummy; mit config.dummy.yml laufen stattdessen die alten Dummy-Geraete. Live-Messwerte
  vom Labor sieht man daheim nicht - das Backend schreibt sie pro Lauf auf dem Pi nach
  logs/<Jahr>/<Monat>/<Tag>/<Experiment-ID>/values.json; nach dem Versuch kopieren.

## Wo was steht

- Fragen und Einzelschritte fuer den Versuch: docs/versuch_08-10-2026_fragen_und_schritte.md
- Geraete-Befunde (Adressen, Adapter, was am Geraet geprueft ist): OFFENE_FRAGEN.md
- Werkzeuge fuer Geraetetests (nur lesend, mit Sperren): tools/README.md
- Liquiline fuer den E+H-Service: docs/liquiline_telefonat_eh.txt
- Workflow aus dem Labor: docs/Maximal_Workflow_-_Kolbe_electrolysis_-_Flow.pdf

## Am Pi (Labor) gilt

- Geraete mit `enabled: false` in config.yml (liquiline, demo_gpio_valve) werden nicht verbunden,
  ihre Experimente beim Start mit Warnung uebersprungen. Nicht erreichbare Geraete blockieren den
  Start nicht mehr.
- Netzteil haengt am by-path (Hub-Buchse 2.4.2), muss dort bleiben; alle FTDI-Adapter sind ueber
  ihre Seriennummer angesprochen und duerfen wandern.
