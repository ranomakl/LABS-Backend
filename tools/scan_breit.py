# Breiterer Baudratenscan, gleiche RID-Sperre wie scan_pumpe.py (importiert, nicht nachgebaut).
import sys, time, serial
import os
_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HIER)                    # Nachbarskripte (scan_pumpe)
sys.path.insert(0, os.path.dirname(_HIER))   # Repo-Wurzel, fuer backend.*
from scan_pumpe import PORT, CMD_RID, _guarded_write, _read_frames, _interpret

treffer = 0
for baudrate in (2400, 4800, 38400, 57600, 115200):
    for parity in ("E", "N"):
        try:
            ser = serial.Serial(PORT, baudrate=baudrate, bytesize=8, parity=parity,
                                stopbits=1, timeout=0.05)
        except serial.SerialException as e:
            print(f"[{baudrate} {parity}] Port nicht zu oeffnen: {e}"); continue
        n = 0
        with ser:
            time.sleep(0.1)
            for address in range(1, 31):
                frame = _guarded_write(ser, address, CMD_RID)
                frames, rest = _read_frames(ser, 0.5 if baudrate < 9600 else 0.3, echo=frame)
                for reply in frames:
                    ok, text = _interpret(reply)
                    n += 1; treffer += ok
                    print(f"  {'TREFFER' if ok else 'unklar'} {baudrate}Bd/{parity} Adr {address}: "
                          f"{reply.hex(' ').upper()} -> {text}")
                if rest:
                    n += 1
                    print(f"  Rest {baudrate}Bd/{parity} Adr {address}: {rest.hex(' ').upper()}")
        print(f"[{baudrate} Baud, Paritaet {parity}] {n} Reaktionen")
print(f"\n=> {treffer} gueltige RID-Antworten")
