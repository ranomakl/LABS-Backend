# Verkuerzter Wiederholungstest nach einer Verkabelungsaenderung.
# Gleiche RID-Sperre wie scan_pumpe.py (importiert): nur Lesebefehl, kein WJ, kein WID.
import sys, time, serial
import os
_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HIER)                    # Nachbarskripte (scan_pumpe)
sys.path.insert(0, os.path.dirname(_HIER))   # Repo-Wurzel, fuer backend.*
from scan_pumpe import PORT, CMD_RID, _guarded_write, _read_frames, _interpret

treffer = []
for baudrate, parity in ((1200, "E"), (9600, "E")):
    with serial.Serial(PORT, baudrate=baudrate, bytesize=8, parity=parity,
                       stopbits=1, timeout=0.05) as ser:
        time.sleep(0.1)
        roh = 0
        for address in range(1, 31):
            frame = _guarded_write(ser, address, CMD_RID)
            frames, rest = _read_frames(ser, 0.5 if baudrate <= 1200 else 0.25, echo=frame)
            roh += len(frames) + (1 if rest else 0)
            for reply in frames:
                ok, text = _interpret(reply)
                print(f"  {'TREFFER' if ok else 'unklar '} {baudrate}Bd/{parity} Adr {address}: "
                      f"{reply.hex(' ').upper()} -> {text}")
                if ok:
                    treffer.append((baudrate, parity, address))
            if rest:
                print(f"  Rest    {baudrate}Bd/{parity} Adr {address}: {rest.hex(' ').upper()}")
        print(f"[{baudrate} Baud/{parity}] {roh} Reaktionen")

print()
if treffer:
    baudrate, parity, address = treffer[0]
    print(f"GEFUNDEN -> config.yml, dosing_pump:  pump_address: {address}, baudrate: {baudrate}")
else:
    print("Weiterhin keine Antwort.")
