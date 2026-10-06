"""Erster Test der Joy-IT DPM86xx Spannungsquelle - REINES LESEWERKZEUG.

Sendet ausschliesslich Lesebefehle ("r") im Frameformat des Treibers backend/drivers/joyit_dpm86.py
und gibt Anfrage und Rohantwort aus. Schreibbefehle ("w") sind gesperrt: _guarded_write() prueft jeden
Frame vor dem Senden. Der Ausgang wird also weder ein- noch ausgeschaltet, Sollwerte bleiben unveraendert.

Aufruf aus der Repo-Wurzel:
    .venv/bin/python tools/lese_netzteil.py --port /dev/serial/by-path/<...>
    .venv/bin/python tools/lese_netzteil.py --dry-run      # nur Frames anzeigen
Ohne --port werden die vorhandenen seriellen Anschluesse aufgelistet.

Vorher pruefen: Netzteil hat Strom am Leistungseingang, GND des Netzteils ist mit GND des
RS485-Adapters verbunden (Hinweis aus Matthias' Code), Geraet steht auf "simple protocol".
"""
import argparse
import glob
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.drivers.joyit_dpm86 import FUNCTIONS, READ, frame  # noqa: E402


class SafetyViolation(Exception):
    pass


def _guarded_write(ser, line: str):
    if not re.fullmatch(r":\d{2}r\d{2}=0,,", line):
        raise SafetyViolation(f"Nur Lesebefehle erlaubt, gesperrt: {line!r}")
    ser.write((line + "\n").encode())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port")
    ap.add_argument("--adresse", default="01", help="Geraeteadresse, Werkseinstellung 01")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    frames = [(fn, frame(args.adresse, READ, fn)) for fn in FUNCTIONS]
    if args.dry_run:
        for fn, f in frames:
            print(f"{FUNCTIONS[fn][0]:18} {f}")
        return
    if not args.port:
        print("Kein --port angegeben. Vorhandene Anschluesse:")
        for p in sorted(glob.glob("/dev/serial/by-path/*") + glob.glob("/dev/serial/by-id/*")):
            print("  ", p, "->", Path(p).resolve())
        return

    import serial
    antworten = 0
    with serial.Serial(args.port, args.baud, bytesize=8, parity="N", stopbits=1, timeout=1.0) as ser:
        ser.reset_input_buffer()
        for fn, f in frames:
            name, factor = FUNCTIONS[fn]
            _guarded_write(ser, f)
            raw = ser.readline()
            m = re.match(rb":\d{2}r\d{2}=(\d+)", raw)
            wert = f"= {round(int(m.group(1)) * factor, 3)}" if m else ""
            antworten += bool(raw)
            print(f"{name:18} {f:14} -> {raw!r} {wert}")
            time.sleep(0.05)
    print(f"\n{antworten}/{len(frames)} Antworten.")
    if antworten == 0:
        print("Keine Antwort: Strom am Netzteil? Gemeinsame Masse? A/B tauschen? Richtiger Port?")


if __name__ == "__main__":
    main()
