# Dauertest fuer den Endress+Hauser Liquiline CM44x: schickt N Sekunden lang im Takt dieselbe
# Modbus-FC03-Leseanfrage an EINE bekannte Einstellung (Standard: ASCII, 19200 Baud, Paritaet E,
# Busadresse 247 = Werkseinstellung) und zaehlt, was zurueckkommt - gueltige Antworten, Rohbytes,
# Muell. Gedacht fuer die Fehlersuche am Geraet: Techniker stellt etwas um, Dauertest zeigt sofort,
# ob sich etwas aendert. Daneben die COM-LED am Modul 485 beobachten.
#
# SICHERHEIT: schreibt ausschliesslich ueber _guarded_write() aus scan_liquiline.py (nur FC03,
# Adressbereich 1-247). Es gibt keinen anderen Schreibpfad in diesem Skript.
#
# Aufruf aus der Repo-Wurzel:
#     .venv/bin/python tools/dauertest_liquiline.py --port /dev/serial/by-id/usb-FTDI_..._BG01XFU4-if00-port0
#     Optionen: --sekunden 30  --baud 19200  --paritaet E|N|O  --adresse 247  --modus ASCII|RTU
#               --passiv   (sendet NICHTS, lauscht nur - zeigt Stoerungen/Fremdverkehr auf der Leitung)
import argparse
import os
import sys
import time

import serial

_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HIER)
sys.path.insert(0, os.path.dirname(_HIER))
from scan_liquiline import _guarded_write, _interpret, _lesen  # noqa: E402

PARITAET = {"E": serial.PARITY_EVEN, "N": serial.PARITY_NONE, "O": serial.PARITY_ODD}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--sekunden", type=float, default=30)
    ap.add_argument("--baud", type=int, default=19200)
    ap.add_argument("--paritaet", choices=PARITAET, default="E")
    ap.add_argument("--adresse", type=int, default=247)
    ap.add_argument("--modus", choices=["ASCII", "RTU"], default="ASCII")
    ap.add_argument("--fenster", type=float, default=0.2, help="Wartezeit je Anfrage in s")
    ap.add_argument("--passiv", action="store_true", help="nur lauschen, nichts senden")
    a = ap.parse_args()

    print(f"Port {a.port}  {a.modus} {a.baud} Baud 8{a.paritaet}1  Adresse {a.adresse}  "
          f"{a.sekunden:.0f} s  {'PASSIV (kein Senden)' if a.passiv else 'FC03-Anfragen'}")
    ser = serial.Serial(a.port, a.baud, bytesize=8, parity=PARITAET[a.paritaet],
                        stopbits=1, timeout=0.05)
    ser.reset_input_buffer()

    anfragen = gueltig = 0
    rohbytes = bytearray()
    beispiele = []
    ende = time.monotonic() + a.sekunden
    try:
        while time.monotonic() < ende:
            if a.passiv:
                chunk = ser.read(256)
                if chunk:
                    rohbytes.extend(chunk)
                continue
            frame = _guarded_write(ser, a.adresse, a.modus)
            anfragen += 1
            antwort = _lesen(ser, a.fenster, echo=frame)
            if antwort:
                rohbytes.extend(antwort)
                ok, text = _interpret(antwort, a.adresse, a.modus)
                if ok:
                    gueltig += 1
                if len(beispiele) < 5:
                    beispiele.append((ok, text, antwort))
    finally:
        ser.close()

    print(f"Anfragen gesendet: {anfragen}")
    print(f"Gueltige Antworten: {gueltig}")
    print(f"Empfangene Rohbytes insgesamt: {len(rohbytes)}")
    if rohbytes:
        print(f"  erste 64 Byte: {bytes(rohbytes[:64]).hex(' ').upper()}")
    for ok, text, antwort in beispiele:
        print(f"  {'TREFFER' if ok else 'verworfen'}: {text}  <- {antwort!r}")
    if not rohbytes:
        print("ERGEBNIS: kein einziges Byte empfangen - Gegenstelle schweigt.")
    return 0 if gueltig else 1


if __name__ == "__main__":
    sys.exit(main())
