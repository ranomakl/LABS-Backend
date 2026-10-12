# Aufgaben 12.10.2026 abends (Bibliothek, am Rechner) - Vorbereitung Testlauf Di 13.10.

Stand: Backend 1ac1fed, Dummys 97bc6c3, beides auf GitHub (main). Liquiline laeuft per Modbus RTU,
Fehlerpfad nachgebessert. Reihenfolge nach Wichtigkeit.

## 1. Repos holen (5 min)

    cd LABS-Backend        && git pull
    cd ../LABS-DeviceDummys && git pull
    cd ../LABS-User-Interface && git pull

## 2. Lesen (20 min)

- `docs/fehlerpfad_nachbesserung_12-10-2026.md` - was heute am Fehlerpfad geaendert wurde und warum,
  Abschnitt 8 = Testanleitung am echten Netzteil fuer morgen frueh.
- `OFFENE_FRAGEN.md`, Abschnitt Liquiline, ab "ANTWORT E+H" - der ganze Weg bis zum Durchbruch.

## 3. Mit den Dummys durchspielen (30 min, Windows-PC)

Wie in `docs/test_fehlerpfad_dummys.md` (config.dummy.yml als config.yml, Dummys + Backend + Frontend).

- Experiment `test_liquiline_messung` (minutes 1) starten: im Monitoring muessen ph_ch1_value,
  ph_ch2_value, temperature_value alle 2 s neue Werte zeigen; nach dem Ende Status Finished,
  values.json enthaelt ~30 Werte je Kanal.
- Fehlerpfad-Test 2 aus der Anleitung einmal wiederholen (STUMM_bronkhorst_mfc): neu ist, dass nach
  ~40 s `CommandSeries [...] failed.` und `repeating device.stop() in 5.0 s` kommen muss, und nach dem
  Loeschen der STUMM-Datei `Stopped`.
- Frontend: Routinen neu laden, damit `kolbe_elektrolyse_ph` erscheint (neues Experiment = Elektrolyse
  + pH beider Elektroden + Temperatur). Mit Dummys einmal starten (minutes 1), Kurven pruefen.

## 4. E+H antworten (10 min)

Case 01976469: Geraet antwortet im RTU-Modus einwandfrei (19200 8E1, Adresse 247); im ASCII-Modus kam
in zwei Wochen kein einziges Byte, bei sonst identischer Verkabelung. Fall kann geschlossen werden.
Optionale Frage: Ist bekannt, dass der ASCII-Modus beim CM448 (Firmware-Stand nennen, steht im
Geraetemenue Diagnose/Systeminformationen oder im Webserver) nicht antwortet?

## 5. Fuer morgen frueh im Labor vormerken (vor dem langen Lauf, ca. 30 min)

1. ERST ALLE GERAETE EINSCHALTEN (Netzteil, MFC, Pumpe, Liquiline, microGC am LAN), DANN das Backend
   starten (kein Autostart!): `cd ~/LABS/LABS-Backend && .venv/bin/python main.py` im Terminal; beenden
   mit Strg+C. Im Log muss jedes Geraet als `Ready` erscheinen. Ein Geraet, das beim Start aus ist, geht
   nach ~40 s nach Error und wird als "nicht verfuegbar" uebersprungen - alle Experimente mit diesem
   Geraet fehlen dann bis zum naechsten Backend-Start (am 12.10. abends so gesehen: MFC und Pumpe aus ->
   kolbe_elektrolyse_ph nicht verfuegbar). Spaeter eingeschaltet = Backend neu starten.
   Probelauf 12.10. abends mit echter config.yml: Liquiline Ready, test_liquiline_all_channels ueber die
   API bis Finished gelaufen (Status Bad wegen Sensoren), Netzteil antwortet, Ausgang aus.
2. Netzteil-Test aus der Fehlerpfad-Doku Abschnitt 8: Geraet ausschalten / USB-Kabel ziehen, jeweils
   pruefen, dass der Ausgang danach AUS ist.
3. Liquiline-Sensoren: Display muss fuer CH1 und CH2 einen pH-Wert zeigen (heute "X --- ---" = kein
   Sensorwert). Memosens-Stecker an Elektrode und Geraet pruefen, Diagnoseliste am Geraet ansehen.
   Erst dann liefert `kolbe_elektrolyse_ph` echte pH-Werte (Status "Good" statt "Bad").
4. Lauf mit `kolbe_elektrolyse_ph` statt `kolbe_elektrolyse` starten, Parameter wie bisher.

## Offen, nicht fuer morgen

- Hardware-Interlock fuer das Netzteil, systemd-Autostart, Stopp-Reihenfolge, Frontend-Alarm bei Failed
  (Liste in der Fehlerpfad-Doku, Abschnitt 9).
- microGC-Messplan ins Elektrolyse-Experiment (`docs/aufgabe_microgc_im_experiment.txt`).
- Liquiline dauerhaft per LAN: nicht noetig; falls gewuenscht am Geraet Netzmaske 255.255.0.0 setzen.
