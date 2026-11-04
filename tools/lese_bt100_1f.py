# Reiner LESE-Test fuer die Longer BT100-1F (Messstand II): sendet RID, RT und RF und zeigt die
# Antworten dekodiert an. Die Pumpe darf sich dabei unter keinen Umstaenden drehen - deshalb:
#   - Whitelist der PDUs (nur RID, RT, RF, RD, RSD, RB - alle "R"-Lesebefehle des Protokolls),
#   - Adressbereich 1-30 (Broadcast 31 gesperrt),
#   - Byte-Muster-Kontrolle am fertigen Frame auf alle "W"-Schreibbefehle (WF, WD, WSD, WT, WB, WID).
# Schlaegt eine Sperre an, bricht das Skript VOR dem ersten ser.write() hart ab.
#
# Frame/Stuffing/Parser werden aus dem Treiber importiert, damit genau das getestet wird, was der
# Treiber spaeter spricht. Protokoll: docs/BT100-1F-RS485-Protocol.pdf, docs/protokoll_bt100_1f.md.
#
# Aufruf aus der Repo-Wurzel:
#   .venv/bin/python tools/lese_bt100_1f.py                 # Adapter BG01X3TF, Adresse 1
#   .venv/bin/python tools/lese_bt100_1f.py --port /dev/ttyUSB0 --adresse 2
#   .venv/bin/python tools/lese_bt100_1f.py --dry-run       # nur Frames anzeigen, nichts senden
import os
import sys
import time

import serial

_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HIER))   # Repo-Wurzel, fuer backend.*
from backend.drivers.longer_bt100_1f import (FLAG, ESCAPE, build_wire_frame, unstuff, _xor,  # noqa: E402
                                             _u32, PUMP_HEADS)

PORT = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BG01X3TF-if00-port0"
ADDRESS = 1
if "--port" in sys.argv:
    PORT = sys.argv[sys.argv.index("--port") + 1]
if "--adresse" in sys.argv:
    ADDRESS = int(sys.argv[sys.argv.index("--adresse") + 1])
DRY_RUN = "--dry-run" in sys.argv

# --------------------------------------------------------------------------- Sperre

ALLOWED_PDUS = frozenset({b"RID", b"RT", b"RF", b"RD", b"RSD", b"RB"})
FORBIDDEN_MARKERS = (b"WF", b"WD", b"WSD", b"WT", b"WB", b"WID")


class SafetyViolation(RuntimeError):
    """Wird geworfen, bevor irgendetwas auf die Leitung geht."""


def _guarded_write(ser, address: int, pdu: bytes) -> bytes:
    if pdu not in ALLOWED_PDUS:
        raise SafetyViolation(f"PDU {pdu!r} steht nicht auf der Whitelist {sorted(ALLOWED_PDUS)}.")
    if not 1 <= address <= 30:
        raise SafetyViolation(f"Adresse {address} ausserhalb 1-30 (Broadcast 31 ist gesperrt).")
    frame = build_wire_frame(address, pdu)
    for marker in FORBIDDEN_MARKERS:
        if marker in frame:
            raise SafetyViolation(f"Schreibbefehl {marker!r} im Frame {frame.hex(' ').upper()}.")
    if unstuff(frame[1:])[2:2 + len(pdu)] != pdu:
        raise SafetyViolation(f"Frame enthaelt nicht die erlaubte PDU: {frame.hex(' ').upper()}.")
    if DRY_RUN:
        print(f"  (dry-run) wuerde senden: {frame.hex(' ').upper()}")
        return frame
    ser.reset_input_buffer()
    ser.write(frame)
    ser.flush()
    return frame


# --------------------------------------------------------------------------- Antwort lesen

def _read_frames(ser, window: float, echo: bytes):
    """Sammelt bis zum Ablauf des Zeitfensters, entstufft und gibt vollstaendige Frames zurueck.
    Das eigene Echo (Halbduplex-Adapter) wird verworfen."""
    buffer, frames = bytearray(), []
    deadline = time.monotonic() + window
    while time.monotonic() < deadline:
        chunk = ser.read(64)
        if chunk:
            buffer.extend(chunk)
        while True:
            while buffer and buffer[0] != FLAG:
                del buffer[0]
            if len(buffer) < 3:
                break
            decoded, i, complete = bytearray(), 1, False
            while i < len(buffer):
                byte = buffer[i]
                if byte == FLAG:
                    break
                if byte == ESCAPE:
                    if i + 1 >= len(buffer):
                        break
                    nxt = buffer[i + 1]
                    decoded.append(ESCAPE if nxt == 0x00 else FLAG if nxt == 0x01 else nxt)
                    i += 2
                else:
                    decoded.append(byte)
                    i += 1
                if len(decoded) >= 2 and len(decoded) == 2 + decoded[1] + 1:
                    complete = True
                    break
            if not complete:
                break
            wire = bytes(buffer[:i])
            del buffer[:i]
            if wire != echo:
                frames.append(bytes([FLAG]) + bytes(decoded))
    return frames, bytes(buffer)


def _interpret(frame: bytes) -> str:
    address, length = frame[1], frame[2]
    pdu, fcs = frame[3:3 + length], frame[-1]
    expected = _xor(frame[1:-1])
    if fcs != expected:
        return f"Pruefsumme falsch (ist {fcs:02X}, erwartet {expected:02X})"
    if pdu[:3] == b"RID":
        return f"RID: Pumpe meldet Adresse {address}"
    if pdu[:3] == b"RSD" and length >= 4:
        return f"RSD: Dosier-Modus State1 = {pdu[3]:02X}"
    if pdu[:2] == b"RF" and length >= 7:
        flow = _u32(pdu[2:6]); state = pdu[6]
        return (f"RF: Flussrate {flow / 1e6:.3f} mL/min ({flow} nL/min), "
                f"{'LAEUFT' if state & 1 else 'steht'}, {'cw' if state & 2 else 'ccw'}"
                f"{', Prime' if state & 4 else ''}")
    if pdu[:2] == b"RT" and length >= 4:
        return f"RT: Pumpenkopf {pdu[2]} ({PUMP_HEADS.get(pdu[2], '?')}), Schlauch-Nr {pdu[3]}"
    if pdu[:2] == b"RD" and length >= 14:
        vol = _u32(pdu[2:6]); copies = (pdu[6] << 8) | pdu[7]; flow = _u32(pdu[8:12]); pause = (pdu[12] << 8) | pdu[13]
        return f"RD: Dosiervolumen {vol / 100:.2f} mL, {copies} Kopien, {flow / 1e6:.3f} mL/min, Pause {pause / 10:.1f} s"
    if pdu[:2] == b"RB" and length >= 4:
        return f"RB: Ruecksaugzeit {((pdu[2] << 8) | pdu[3]) / 10:.1f} s"
    return f"unbekannte Antwort, PDU = {pdu.hex(' ').upper()}"


# --------------------------------------------------------------------------- Hauptprogramm

def main():
    print(f"BT100-1F Lesetest - Port {PORT}, Adresse {ADDRESS}, 1200 Baud 8E1"
          + (" (DRY-RUN, es wird nichts gesendet)" if DRY_RUN else ""))
    ser = None
    if not DRY_RUN:
        ser = serial.Serial(PORT, baudrate=1200, bytesize=8, parity=serial.PARITY_EVEN, stopbits=1, timeout=0.05)
    try:
        for pdu in (b"RID", b"RT", b"RF", b"RD", b"RSD", b"RB"):
            print(f"\n> {pdu.decode()}")
            frame = _guarded_write(ser, ADDRESS, pdu)
            if DRY_RUN:
                continue
            print(f"  gesendet:  {frame.hex(' ').upper()}")
            frames, rest = _read_frames(ser, 1.0, frame)
            for reply in frames:
                print(f"  empfangen: {reply.hex(' ').upper()}  ->  {_interpret(reply)}")
            if not frames:
                print("  keine Antwort" + (f" (Rest im Puffer: {rest.hex(' ').upper()})" if rest else ""))
            time.sleep(0.2)
    finally:
        if ser is not None:
            ser.close()


if __name__ == "__main__":
    main()
