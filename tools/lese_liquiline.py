# Reiner LESE-Test fuer den Endress+Hauser Liquiline CM44x ueber Modbus RTU (ersetzt scan_liquiline.py und
# dauertest_liquiline.py, die noch aus der ASCII-Zeit stammen und nicht mehr starten). Es wird
# AUSSCHLIESSLICH Funktionscode 0x03 (Read Holding Registers) gesendet - am Geraet wird nichts veraendert.
#
# Ablauf: 1) Einstellung suchen (alle Baudraten, Paritaeten E/N/O, Adressen 247 und 1), 2) Konfigurations-
# register 501-513 (Baud, Paritaet, RS485, Modus, Watchdog, Ethernet) anzeigen, 3) alle 16 AI-Bloecke
# (Wert/Status/Einheit) dekodieren. Mit --dauer N sendet es stattdessen N Sekunden lang alle 0,3 s dieselbe
# Anfrage, damit die COM-LED am Modul 485MB und TXD/RXD am Adapter beobachtet werden koennen.
#
# Erfahrung 04.11.2026 (Messstand II, Adapter BG02Q3TM): Die COM-LED blinkt NUR bei gueltigen Rahmen im am
# Geraet eingestellten Modus. Dunkle COM-LED bei blinkendem TXD heisst meist "Menue falsch" (Setup/General
# settings/Extended setup/Modbus: RTU, 19200, Even, Adresse 247), nicht "Kabel falsch".
#
# Aufruf aus der Repo-Wurzel:
#   .venv/bin/python tools/lese_liquiline.py --port /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BG02Q3TM-if00-port0
#   .venv/bin/python tools/lese_liquiline.py --port ... --dauer 120      # LED-Beobachtung
#   .venv/bin/python tools/lese_liquiline.py --port ... --adresse 247 --baud 19200 --paritaet E   # ohne Suche
import argparse
import os
import sys
import time

import serial

_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HIER))   # Repo-Wurzel, fuer backend.*
from backend.drivers.endress_hauser_liquiline import (_build_request, _crc16, expected_frame_length,  # noqa: E402
                                                      _decode_float, UNIT_CODES)

STATUS = {0: "Good", 1: "Uncertain", 2: "Bad", 3: "Not assigned"}
BAUDRATES = (19200, 9600, 38400, 115200, 57600, 4800, 2400, 1200)
FC_READ_HOLDING = 0x03


def _guarded_request(address: int, start: int, quantity: int) -> bytes:
    if not 1 <= address <= 247:
        raise RuntimeError(f"Adresse {address} ausserhalb 1-247 (0 = Broadcast gesperrt).")
    req = _build_request(address, FC_READ_HOLDING, start, quantity)
    if req[1] != FC_READ_HOLDING:
        raise RuntimeError(f"Nur FC03 erlaubt, Frame {req.hex(' ')}")
    return req


def ask(ser, address, start, quantity, window=0.6):
    req = _guarded_request(address, start, quantity)
    ser.reset_input_buffer(); ser.write(req); ser.flush()
    buf = bytearray(); deadline = time.monotonic() + window
    while time.monotonic() < deadline:
        buf.extend(ser.read(256))
        if buf[:len(req)] == req:            # Echo des Halbduplex-Adapters
            del buf[:len(req)]
        n = expected_frame_length(bytes(buf))
        if n and len(buf) >= n:
            frame = bytes(buf[:n])
            if frame[0] == address and _crc16(frame[:-2]) == frame[-2:]:
                return frame
            del buf[0]
    return bytes(buf) or None


def regs(frame):
    data = frame[3:-2]
    return [(data[2 * i] << 8) | data[2 * i + 1] for i in range(len(data) // 2)]


def find_settings(port):
    for baud in BAUDRATES:
        for par in "ENO":
            with serial.Serial(port, baud, bytesize=8, parity=par, stopbits=1, timeout=0.05) as ser:
                for addr in (247, 1):
                    f = ask(ser, addr, 0, 1)
                    if isinstance(f, bytes) and len(f) >= 5 and f[0] == addr and f[1] in (3, 0x83):
                        return baud, par, addr, f
                    time.sleep(0.05)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--adresse", type=int)
    ap.add_argument("--baud", type=int)
    ap.add_argument("--paritaet", choices="ENO")
    ap.add_argument("--dauer", type=int, default=0, help="Sekunden Dauersenden statt Scan")
    ap.add_argument("--byte-order", default="1-0-3-2")
    a = ap.parse_args()

    if a.dauer:
        baud, par, addr = a.baud or 19200, a.paritaet or "E", a.adresse or 247
        req = _guarded_request(addr, 0, 1)
        n = got = 0
        print(f"Dauersenden {a.dauer} s: {baud} 8{par}1 Adresse {addr}, Frame {req.hex(' ').upper()}")
        with serial.Serial(a.port, baud, parity=par, timeout=0.05) as ser:
            end = time.monotonic() + a.dauer
            while time.monotonic() < end:
                ser.write(req); ser.flush(); n += 1
                buf = bytearray(); t = time.monotonic() + 0.25
                while time.monotonic() < t:
                    buf.extend(ser.read(64))
                if buf:
                    got += 1; print(time.strftime("%H:%M:%S"), "EMPFANGEN", buf.hex(" ").upper(), flush=True)
        print(f"fertig: {n} Anfragen, {got} Reaktionen")
        return

    if a.baud and a.paritaet and a.adresse:
        baud, par, addr = a.baud, a.paritaet, a.adresse
    else:
        found = find_settings(a.port)
        if not found:
            print("KEINE ANTWORT auf allen Baudraten/Paritaeten, Adressen 247 und 1. Am Geraet pruefen: "
                  "Setup/General settings/Extended setup/Modbus -> RTU, 19200, Even, Adresse 247; "
                  "Klemmen 95 = B, 96 = A, 99 = GND; COM-LED am Modul 485MB.")
            sys.exit(1)
        baud, par, addr, f = found
        print(f"ANTWORT: {baud} Baud, Paritaet {par}, Adresse {addr}: {f.hex(' ').upper()}")

    with serial.Serial(a.port, baud, bytesize=8, parity=par, stopbits=1, timeout=0.05) as ser:
        f = ask(ser, addr, 501, 13)
        if f and f[1] == 3:
            r = regs(f)
            print(f"Konfig 501-513: {r} -> Baud-Code {r[0]} (4 = 19200), Parity {r[2]} (0 = Even), RS485 {r[3]}, "
                  f"Modus {r[4]} (0 = RTU), Watchdog {_decode_float(r[5], r[6], a.byte_order)} s, Ethernet {r[8]}")
        else:
            print("Konfig-Register: keine/ungueltige Antwort", f.hex(" ") if f else None)
        for blk in range(16):
            f = ask(ser, addr, blk * 4, 4)
            if f and f[1] == 3:
                r = regs(f)
                val = _decode_float(r[0], r[1], a.byte_order); st = r[2] & 0xFF; un = r[3] & 0xFF
                print(f"AI{blk + 1:2d} (Reg {blk * 4:2d}): {val:10.4f}  {UNIT_CODES.get(un, un):8s} "
                      f"Status {st} {STATUS.get(st, '?')}")
            else:
                print(f"AI{blk + 1:2d}: keine Antwort {f.hex(' ') if f else ''}")
            time.sleep(0.05)


if __name__ == "__main__":
    main()
