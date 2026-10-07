# Reines LESE-Werkzeug fuer Bronkhorst FLOW-BUS/ProPar-ASCII-Geraete (EL-FLOW Prestige u.a.):
# Typenschild abfragen (Seriennummer, Messbereich, Einheit, Fluid), Messwert, Sollwert, Zaehler.
#
# SICHERHEIT: Gesendet wird AUSSCHLIESSLICH Befehl 04 (Parameter lesen). Jeder Frame wird vor dem
# Senden in _guarded_write() geprueft: Befehlsbyte muss "04" sein, sonst harter Abbruch. Es gibt
# keinen anderen Schreibpfad. Schreibbefehl 01 (z.B. Setpoint) kommt im Skript nicht vor.
#
# Frames nach docs/handbuch_bronkhorst.pdf Abschnitt 3.8 (Lesen):
#   ":" LEN NODE "04" ECHO_PROZESS ECHO_PARAMETER PROZESS PARAMETER [STRINGLAENGE] "\r\n"
# Antwort: ":" LEN NODE "02" ECHO_PROZESS ECHO_PARAMETER WERT "\r\n"
# Frame-Bausteine (_rw_pair, Typen) kommen aus dem Treiber, damit Werkzeug und Treiber nie
# auseinanderlaufen.
#
# Aufruf aus der Repo-Wurzel:
#     .venv/bin/python tools/lese_mfc.py --port /dev/serial/by-id/usb-FTDI_..._BG01B8RX-if00-port0
#     Optionen: --node 03 (sonst werden Knoten 1-10 probiert), --baud 38400
import argparse
import os
import sys
import time

import serial

_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HIER))
from backend.drivers.bronkhorst_mfc import (  # noqa: E402
    CMD_READ, READ_ECHO_INDEX, TYPE_UINT16, TYPE_FLOAT, TYPE_STRING, _rw_pair, _hex_to_int16, _hex_to_float32)

# (Name, Prozess, Parameter, Typ) - Quellen: Handbuch Abschnitt 3.9, Testbericht 31.08.2026
PARAMETER = [
    ("Messwert (1/0)",        1,   0, TYPE_UINT16),
    ("Sollwert (1/1)",        1,   1, TYPE_UINT16),
    ("Capacity100% (1/13)",   1,  13, TYPE_FLOAT),
    ("Capacity unit (1/31)",  1,  31, TYPE_STRING),
    ("Fluid name (1/17)",     1,  17, TYPE_STRING),
    ("Seriennummer (113/3)",  113, 3, TYPE_STRING),
    ("Zaehler (104/1)",       104, 1, TYPE_FLOAT),
]


class SafetyViolation(RuntimeError):
    pass


def read_frame(node: int, process: int, parameter: int, data_type: int) -> bytes:
    body = f"{node:02X}{CMD_READ}{_rw_pair(process, data_type, READ_ECHO_INDEX)}{_rw_pair(process, data_type, parameter)}"
    if data_type == TYPE_STRING:
        body += "00"   # Stringlaenge 0 = bis zum Nullzeichen (Handbuch 3.8)
    length = len(body) // 2
    return f":{length:02X}{body}\r\n".encode("ascii")


def _guarded_write(ser, frame: bytes) -> None:
    """Einziger Schreibpfad: laesst nur Lesebefehl 04 durch."""
    text = frame.decode("ascii")
    if not text.startswith(":") or text[5:7] != CMD_READ or "01" == text[5:7]:
        raise SafetyViolation(f"Frame ist kein Lesebefehl: {text!r}")
    ser.reset_input_buffer()
    ser.write(frame)
    ser.flush()


def decode(reply: str, data_type: int):
    # reply ohne ":" und CRLF: LEN NODE 02 ECHOPROC ECHOPAR WERT...
    wert = reply[10:]
    if data_type == TYPE_UINT16:
        return _hex_to_int16(wert[:4])
    if data_type == TYPE_FLOAT:
        return _hex_to_float32(wert[:8])
    # Stringantwort am Geraet beobachtet: nach dem Echo-Paar ein Laengenbyte (00 = bis Nullzeichen),
    # dann die Zeichen, dann 00. Beispiel: :0D03020161 00 6D6C6E2F6D696E 00 -> "mln/min"
    raw = bytes.fromhex(wert)[1:]
    return raw.split(b"\x00")[0].decode("ascii", "replace")


def frage(ser, node, name, process, parameter, data_type, wartezeit=0.4):
    frame = read_frame(node, process, parameter, data_type)
    _guarded_write(ser, frame)
    ende = time.monotonic() + wartezeit
    puffer = b""
    while time.monotonic() < ende:
        puffer += ser.read(128)
        if b"\r\n" in puffer:
            break
    antwort = puffer.decode("ascii", "replace").strip()
    # Nur eine echte Leseantwort (Befehl 02 vom gefragten Knoten) zaehlt; ":0105" o.ae. ist eine
    # Fehler-/Statusmeldung (z.B. falscher Knoten) und gilt beim Knotenscan nicht als Treffer.
    if not antwort.startswith(":") or len(antwort) < 11 or antwort[3:7] != f"{node:02X}02":
        return frame, antwort, None
    try:
        return frame, antwort, decode(antwort[1:], data_type)
    except Exception as e:  # noqa: BLE001
        return frame, antwort, f"nicht dekodierbar ({e})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--node", type=lambda s: int(s, 16), default=None, help="Knoten hex, z.B. 03")
    ap.add_argument("--baud", type=int, default=38400)
    a = ap.parse_args()
    ser = serial.Serial(a.port, a.baud, bytesize=8, parity="N", stopbits=1, timeout=0.05)
    print(f"Port {a.port}, {a.baud} Baud 8N1 - nur Lesebefehle (04)")

    knoten = [a.node] if a.node is not None else list(range(1, 11))
    gefunden = None
    for n in knoten:
        frame, antwort, wert = frage(ser, n, *PARAMETER[0])
        if wert is not None:
            print(f"Knoten {n:02X} antwortet: {frame.decode().strip()} -> {antwort}")
            gefunden = n
            break
    if gefunden is None:
        print("Kein Knoten antwortet (Geraet aus? falscher Adapter? Baudrate?)")
        return 1
    print()
    for name, process, parameter, data_type in PARAMETER:
        frame, antwort, wert = frage(ser, gefunden, name, process, parameter, data_type)
        print(f"{name:24s} {frame.decode().strip():26s} -> {antwort:34s} = {wert}")
    ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
