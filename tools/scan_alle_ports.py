# Reiner LESE-Scan ueber ALLE seriellen Anschluesse: sucht die Longer WT600-2J, wenn weder
# Anschluss noch Pumpenadresse noch Baudrate bekannt sind.
#
# Fuehrt die Matrix aus scan_pumpe.py (RID an Adressen 1-30, Baudraten 1200/9600/19200, Paritaet
# gerade und keine) auf jedem gefundenen Adapter aus und meldet am Ende, auf welchem Anschluss
# mit welcher Adresse und Baudrate eine gueltige Antwort kam.
#
# SICHERHEIT - die Pumpe darf sich unter keinen Umstaenden drehen: geschrieben wird
# ausschliesslich ueber _guarded_write() aus scan_pumpe.py (PDU-Whitelist b"RID", Adressbereich
# 1-30 ohne Broadcast, Byte-Muster-Kontrolle auf WJ/WID). Dieses Skript baut keinen eigenen
# Schreibpfad. Siehe tools/README.md, Abschnitt "Sicherheit".
#
# HINWEIS: Gescannt werden auch Anschluesse, an denen andere Geraete haengen (z.B. der
# Bronkhorst-MFC). Das ist unbedenklich - der RID-Frame ist ein Lesebefehl, und seine Bytes
# (E9 ...) sind fuer die anderen Protokolle im Aufbau kein gueltiger Befehlsanfang; sie werden
# dort verworfen. Mit --nur <text> laesst sich die Auswahl trotzdem einschraenken.
#
# Aufruf aus der Repo-Wurzel:
#     .venv/bin/python tools/scan_alle_ports.py
#     .venv/bin/python tools/scan_alle_ports.py --dry-run        # zeigt nur die Portliste
#     .venv/bin/python tools/scan_alle_ports.py --nur FTDI       # nur passende Anschluesse
#     .venv/bin/python tools/scan_alle_ports.py --anlauf 5       # laengere Anlaufwartezeit
import glob
import os
import sys
import time

import serial

_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HIER)                    # Nachbarskripte (scan_pumpe)
sys.path.insert(0, os.path.dirname(_HIER))   # Repo-Wurzel, fuer backend.*
from scan_pumpe import (CMD_RID, ADDRESSES, BAUDRATES, PARITIES,      # noqa: E402
                        _guarded_write, _read_frames, _interpret, selftest)


# Wartezeit nach dem Oeffnen des Ports, bevor die erste Adresse angefragt wird.
# serial.Serial() setzt beim Oeffnen DTR und RTS aktiv - an manchen RS485-Adaptern versorgt das
# erst die Wandlerelektronik bzw. weckt die Gegenstelle. Beim Schliessen fallen die Leitungen
# wieder ab, deshalb wird nach JEDEM Oeffnen gewartet, nicht nur einmal je Anschluss. 0,1 s wie in
# scan_pumpe.py reichen dafuer nicht - die halbe Adressliste liefe sonst ins Leere, waehrend die
# Gegenstelle noch anlaeuft.
ANLAUF = 2.0
if "--anlauf" in sys.argv:
    ANLAUF = float(sys.argv[sys.argv.index("--anlauf") + 1])


def ports():
    """Alle seriellen Anschluesse, bevorzugt die stabilen by-id-Pfade (die ttyUSBn-Nummern
    wechseln beim Umstecken, die by-id-Namen nicht)."""
    gefunden = sorted(glob.glob("/dev/serial/by-id/*"))
    if not gefunden:  # kein by-id-Verzeichnis (z.B. Adapter ohne Seriennummer)
        gefunden = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    if "--nur" in sys.argv:
        muster = sys.argv[sys.argv.index("--nur") + 1]
        gefunden = [p for p in gefunden if muster in p]
    return gefunden


def scan_port(port):
    """Fahrt die volle Matrix auf einem Anschluss ab. Gibt (Treffer, Unklares) zurueck."""
    treffer, unklar = [], []
    for baudrate in BAUDRATES:
        for parity in PARITIES:
            label = f"{baudrate:>5} Baud, Paritaet {parity}"
            try:
                ser = serial.Serial(port, baudrate=baudrate, bytesize=8, parity=parity,
                                    stopbits=1, timeout=0.05)
            except serial.SerialException as error:
                print(f"    [{label}] nicht zu oeffnen: {error}")
                return treffer, unklar   # belegter/defekter Port: weitere Versuche sparen
            # Bei 1200 Baud dauert allein ein 7-Byte-Frame ~64 ms je Richtung.
            window = 0.8 if baudrate <= 1200 else 0.4
            print(f"    [{label}] Adressen 1-30 ...", end="", flush=True)
            with ser:
                time.sleep(ANLAUF)
                for address in ADDRESSES:
                    frame = _guarded_write(ser, address, CMD_RID)
                    frames, rest = _read_frames(ser, window, echo=frame)
                    for reply in frames:
                        ok, text = _interpret(reply)
                        eintrag = (port, baudrate, parity, address,
                                   reply.hex(" ").upper(), text)
                        (treffer if ok else unklar).append(eintrag)
                        print(f"\n      {'TREFFER' if ok else 'unklar '} Adresse {address:>2}: "
                              f"{reply.hex(' ').upper()}  -> {text}", end="")
                    if rest:
                        unklar.append((port, baudrate, parity, address,
                                       rest.hex(" ").upper(), "unvollstaendige Bytes"))
                        print(f"\n      Rest    Adresse {address:>2}: "
                              f"{rest.hex(' ').upper()}", end="")
            print(" fertig.")
    return treffer, unklar


def main():
    liste = ports()
    if not liste:
        print("Kein serieller Anschluss gefunden (weder /dev/serial/by-id/* noch /dev/ttyUSB*).")
        return 1

    print(f"{len(liste)} Anschluesse:")
    for port in liste:
        ziel = os.path.realpath(port)
        print(f"  {port}" + (f"  -> {os.path.basename(ziel)}" if ziel != port else ""))
    print(f"\nJe Anschluss: {len(BAUDRATES)} Baudraten x {len(PARITIES)} Paritaeten x "
          f"{len(ADDRESSES)} Adressen. Gesendet wird ausschliesslich RID (Lesebefehl).")

    if "--dry-run" in sys.argv:
        print("\n--dry-run: Es wurde nichts gesendet.")
        return 0

    alle_treffer, alle_unklar = [], []
    for nummer, port in enumerate(liste, 1):
        print(f"\n[{nummer}/{len(liste)}] {port}")
        treffer, unklar = scan_port(port)
        alle_treffer.extend(treffer)
        alle_unklar.extend(unklar)

    print("\n" + "=" * 78)
    if alle_treffer:
        print("GEFUNDEN - gueltige RID-Antwort:")
        for port, baudrate, parity, address, raw, text in alle_treffer:
            print(f"  Anschluss : {port}")
            print(f"  Adresse   : {address}   ({text})")
            print(f"  Baudrate  : {baudrate}, Paritaet {parity}, 8 Datenbits, 1 Stoppbit")
            print(f"  Rohframe  : {raw}\n")
        port, baudrate, parity, address, _, _ = alle_treffer[0]
        print("Fuer config.yml unter dosing_pump:")
        print(f"      address: {port}")
        print(f"      pump_address: {address}")
        print(f"      serial_parameters:")
        print(f"        baudrate: {baudrate}")
        if parity != "E":
            print(f'        parity: "{parity}"   # weicht von der Blogquelle (E) ab!')
    else:
        print("KEINE gueltige Antwort auf keinem Anschluss, keiner Adresse, keiner Baudrate.")
        print("Moegliche Ursachen: Pumpe aus; RS485-Modul nicht im DB15-Port; A/B vertauscht;")
        print("Adapter sendet RS232 statt RS485 bzw. braucht RTS-Umschaltung (tools/probe_rts_"
              "toggle.py); andere Baudrate als 1200/9600/19200 (tools/scan_breit.py).")
    if alle_unklar:
        print(f"\n{len(alle_unklar)} unklare/unvollstaendige Reaktionen (Auszug):")
        for port, baudrate, parity, address, raw, text in alle_unklar[:15]:
            print(f"  {os.path.basename(port)}, {baudrate} Baud/{parity}, Adresse {address}: "
                  f"{raw}  -> {text}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    selftest()
    print()
    sys.exit(main())
