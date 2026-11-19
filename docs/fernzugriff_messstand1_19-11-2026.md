# Fernzugriff auf Messstand I ohne Monitor - Optionen und Bedenken (19.11.2026)

Stand: Ueberlegung, **nichts davon ist eingerichtet**. Zusammenfassung des Gespraechs Rafael / Claude vom 19.11.2026.

## Ausgangslage

- Pi von Messstand I: `Raspberry-PI-MP-002`, WLAN "ufz-m2m", aktuell 141.65.150.197 (per DHCP, kann sich aendern).
- Am Pi haengt kein Monitor. Die Chemiker muessen von ihren eigenen Rechnern aus arbeiten.
- LABS wird bisher von Hand gestartet (Desktop-Symbol "LABS starten" oder per SSH `tools/labs_start.sh`).
- Der Pi-Desktop (labwc/Wayland, Benutzer `pohlma` automatisch angemeldet) laeuft auch ohne Monitor.

## Kurzfassung

Fuer den normalen Versuchsbetrieb reicht der Browser: `http://141.65.150.197:5000`. RDP oder VNC braucht es
dafuer nicht. Was der Browser heute **nicht** kann: LABS starten/beenden (z. B. nach einem Absturz) und das
Geraetestatus-Fenster zeigen. Dafuer braucht es entweder einen Desktop-Fernzugriff oder zwei kleine Erweiterungen
(Autostart, Geraetestatus im Frontend).

Empfehlung: Versuche im Browser fahren. Fuer den Desktop zuerst **VNC im Browser (noVNC)** ausprobieren, weil
auf den PCs nichts installiert werden muss. Autostart ist vorerst zurueckgestellt (Entscheidung Rafael 19.11.).

## Die Wege im Vergleich

| Weg | Auf den PCs noetig | Was man sieht | Stand auf dem Pi |
|---|---|---|---|
| Browser, nur LABS | nichts | Weboberflaeche (Versuche starten, verfolgen, stoppen) | laeuft |
| VNC mit Viewer | VNC-Viewer installieren (vermutlich genehmigungspflichtig) | den echten Pi-Desktop | `wayvnc` installiert, nicht eingeschaltet |
| VNC im Browser (noVNC) | nichts | den echten Pi-Desktop im Browser-Tab | muesste auf dem Pi eingerichtet werden, nicht getestet |
| RDP (`xrdp`) | nichts (Windows-Bordmittel) | eine eigene, zweite Sitzung | nicht installiert (0.10.1 im Paketarchiv) |
| Raspberry Pi Connect | nichts | Pi-Desktop im Browser | installiert, laeuft aber ueber einen Cloud-Dienst ausserhalb des UFZ |

## Bedenken

### Browser allein

- **Kein Start/Stopp von LABS:** Stuerzt das Backend ab oder startet der Pi neu (Stromausfall), ist LABS weg und
  nur per SSH wieder zu starten.
- **Geraetestatus fehlt:** Das Fenster mit gruenen Haken / roten Kreuzen (`tools/geraete_fenster.py`) ist ein
  Desktop-Programm und im Browser nicht sichtbar.
- **Uebersprungene Geraete:** Geraete, die beim Start aus oder nicht eingesteckt waren, kommen erst nach einem
  Backend-Neustart dazu. Auch das geht vom Browser aus nicht.
- **Adresse kann sich aendern:** DHCP. Der Entwurf der Mail an die IT (feste IP, Name z. B.
  `labs-messstand1.ufz.de`) liegt in `docs/mail_it_feste_ip_pi_04-11-2026.txt`; ob sie verschickt wurde, ist offen.
- **Mehrere Nutzer gleichzeitig:** Alle sehen dieselbe Station und koennen sich in die Quere kommen.

### Zugriffsschutz (am 19.11. nachgeprueft)

- Die Weboberflaeche (Port 5000) hat eine Anmeldung; die Versuchsseiten leiten ohne Login auf `/login` um.
- **Die Backend-Schnittstelle (Port 11123) ist ohne Anmeldung aus dem Netz erreichbar.**
  `http://141.65.150.197:11123/api/station_overview` antwortet von der WLAN-Adresse aus ohne Login; auf demselben
  Port liegt auch `/api/shutdown`. Wer die Adresse kennt und im selben Netz ist, kommt also am Login des
  Frontends vorbei. Das sollte unabhaengig vom Fernzugriff geklaert werden (Port nur lokal oeffnen oder absichern).

### VNC

- **Viewer noetig:** Das Windows-eigene "Remotedesktop" kann kein VNC. Ein Viewer (TigerVNC, RealVNC Viewer)
  muss auf jeden PC, vermutlich mit Genehmigung. Ausweg: noVNC, dann reicht der Browser.
- **Ein gemeinsamer Desktop:** Alle sehen dasselbe Bild und teilen sich eine Maus.
- **Voller Zugriff:** Wer drauf ist, arbeitet als `pohlma` mit Terminal, Dateien und Konfiguration - nicht nur als
  LABS-Bediener.
- **Offener Port im Institutsnetz:** braucht ein eigenes Passwort und vermutlich das Einverstaendnis der IT.

### RDP (`xrdp`)

RDP geht technisch, passt hier aber schlechter als VNC. Auf diesem Pi nicht ausprobiert, die Punkte stammen aus
allgemeiner Erfahrung mit `xrdp`:

- **Zweite Sitzung statt des laufenden Desktops:** `xrdp` kann die Wayland-Sitzung nicht uebernehmen und startet
  einen eigenen X11-Desktop. Statusfenster und Browser vom Pi-Desktop sind dort nicht zu sehen.
- **Zwei Sitzungen desselben Benutzers:** Mit dem automatisch angemeldeten `pohlma` gibt das oft einen schwarzen
  oder sofort schliessenden Bildschirm. Abhilfe: eigener Benutzer nur fuer RDP oder Auto-Anmeldung abschalten.
- LABS selbst laeuft unabhaengig weiter; die Symbole "LABS starten" / "LABS beenden" wuerden auch dort gehen.
- Vorteil: nichts auf den PCs zu installieren. Voller Zugriff und offener Port gelten wie bei VNC.

### Raspberry Pi Connect

Zeigt den Desktop im Browser, laeuft aber ueber einen Dienst von Raspberry Pi ausserhalb des UFZ. Fuer ein
Institutsgeraet nicht ohne Rueckfrage bei der IT.

### Autostart (systemd-Dienst) - zurueckgestellt

Wuerde LABS beim Booten und nach einem Absturz von selbst starten. Bedenken:

- **Geraete beim Booten noch aus:** Sie werden uebersprungen und fehlen bis zum naechsten Backend-Neustart.
- **Ungepruefter Code geht von selbst live:** Das Startskript macht bei jedem Start `git pull`. Im Autostart
  muesste das raus; Aktualisieren waere dann ein bewusster Schritt.
- **Wartung:** Der Dienst belegt die seriellen Anschluesse und muss fuer Tests am Pi angehalten werden.
- **Laufender Versuch ist nach einem Absturz weg** und wird nicht fortgesetzt. Offen ist, in welchem Zustand die
  Geraete stehen bleiben, vor allem ob ein Netzteil weiter Strom liefert (vgl.
  `docs/vorfall_08-10-2026_netzteil_blieb_an.txt`). Ob das Backend beim Start die Netzteile sicher ausschaltet,
  ist nicht geprueft.
- **Dauerschleife:** Ohne Grenze wuerde ein Dienst, der immer wieder abstuerzt, die Geraete immer wieder ansprechen.

## Offene Punkte

1. IT fragen: feste IP / DNS-Name; ist ein weiterer offener Port am Pi (VNC, noVNC oder RDP) im Netz "ufz-m2m"
   erlaubt?
2. Entscheiden: noVNC ausprobieren oder `xrdp` mit eigenem Benutzer testen.
3. Backend-Port 11123 absichern oder nur lokal oeffnen.
4. Spaeter: Geraetestatus und "Backend neu starten" ins Frontend; Autostart erst, wenn das Verhalten der Netzteile
   beim Backend-Start geprueft ist.
