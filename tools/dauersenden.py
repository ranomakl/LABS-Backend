# Sendet 25 s lang durchgehend RID an Adresse 1, damit man die TXD/RXD-LEDs am Adapter beobachten
# kann. Gleiche RID-Sperre wie scan_pumpe.py (importiert): nur Lesebefehl, kein WJ, kein WID -
# die Pumpe kann sich dadurch nicht drehen.
import sys, time, serial
import os
_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HIER)                    # Nachbarskripte (scan_pumpe)
sys.path.insert(0, os.path.dirname(_HIER))   # Repo-Wurzel, fuer backend.*
from scan_pumpe import PORT, CMD_RID, _guarded_write

print("25 Sekunden Dauersenden auf 1200 Baud, gerade Paritaet, an Adresse 1.")
print("Schau auf die LEDs am Adapter:")
print("  TXD blinkt  -> Adapter sendet tatsaechlich auf den Bus")
print("  TXD dunkel  -> es geht nichts raus (Adapter/Treiberpfad)")
print("  RXD blinkt  -> die Pumpe antwortet (dann sind wir fast am Ziel)\n")

empfangen = 0
with serial.Serial(PORT, baudrate=1200, bytesize=8, parity="E", stopbits=1, timeout=0.05) as ser:
    ende = time.monotonic() + 25
    n = 0
    while time.monotonic() < ende:
        _guarded_write(ser, 1, CMD_RID)
        n += 1
        time.sleep(0.2)
        raw = ser.read(256)
        if raw:
            empfangen += len(raw)
            print(f"  Bytes empfangen: {raw.hex(' ').upper()}")
        if n % 10 == 0:
            print(f"  ... {n} Frames gesendet")

print(f"\nFertig: {n} Frames gesendet, {empfangen} Byte empfangen.")
