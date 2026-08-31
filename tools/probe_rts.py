# Nur-Lese-Nachtest: gleiche RID-Sperre wie scan_pumpe.py, aber mit beiden RTS-Zustaenden.
import sys, time, serial
import os
_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HIER)                    # Nachbarskripte (scan_pumpe)
sys.path.insert(0, os.path.dirname(_HIER))   # Repo-Wurzel, fuer backend.*
from scan_pumpe import PORT, CMD_RID, _guarded_write, _read_frames, _interpret

for rts in (False, True):
    for baudrate in (1200, 9600):
        ser = serial.Serial(PORT, baudrate=baudrate, bytesize=8, parity="E",
                            stopbits=1, timeout=0.05)
        ser.rts = rts
        got = 0
        with ser:
            time.sleep(0.1)
            for address in range(1, 31):
                frame = _guarded_write(ser, address, CMD_RID)
                frames, rest = _read_frames(ser, 0.6 if baudrate <= 1200 else 0.3, echo=frame)
                for reply in frames:
                    ok, text = _interpret(reply)
                    got += 1
                    print(f"  RTS={rts} {baudrate}Bd Adr {address}: {reply.hex(' ').upper()} -> {text}")
                if rest:
                    got += 1
                    print(f"  RTS={rts} {baudrate}Bd Adr {address}: Rest {rest.hex(' ').upper()}")
        print(f"RTS={rts}, {baudrate} Baud: {got} Reaktionen")
