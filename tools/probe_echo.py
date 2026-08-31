# Diagnose: kommt IRGENDETWAS zurueck - auch das eigene Echo? Kein Echo-Filter.
# Gleiche RID-Sperre wie scan_pumpe.py.
import sys, time, serial
import os
_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HIER)                    # Nachbarskripte (scan_pumpe)
sys.path.insert(0, os.path.dirname(_HIER))   # Repo-Wurzel, fuer backend.*
from scan_pumpe import PORT, CMD_RID, _guarded_write

for baudrate, parity in ((1200, "E"), (9600, "N")):
    ser = serial.Serial(PORT, baudrate=baudrate, bytesize=8, parity=parity,
                        stopbits=1, timeout=0.05)
    with ser:
        time.sleep(0.1)
        for address in (1, 31 - 1):   # 30 statt Broadcast 31 - die Sperre laesst 31 nicht durch
            frame = _guarded_write(ser, address, CMD_RID)
            time.sleep(0.8)
            raw = ser.read(256)
            print(f"{baudrate}Bd/{parity} Adr {address}: gesendet {frame.hex(' ').upper()}")
            print(f"    empfangen ({len(raw)} Byte): {raw.hex(' ').upper() or '<nichts>'}")
        print(f"    CTS={ser.cts} DSR={ser.dsr} CD={ser.cd} RI={ser.ri}")
