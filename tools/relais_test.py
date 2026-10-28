"""
Einzeltest fuer ein Relais der GC-Ventil-Platine OHNE Backend (28.10.2026).
Nutzt genau den Mechanismus des Treibers (release_when_off):
    AN  = Pin als Ausgang auf Masse
    AUS = Pin loslassen (Eingang + Pull-Down) -> Platine zieht ihn selbst auf ihre 5 V

Aufruf (LABS muss BEENDET sein, sonst ist der Pin belegt):
    cd ~/LABS/LABS-Backend && .venv/bin/python tools/relais_test.py 17
BCM-Nummern:  17 = Header-Pin 11 = Relais 1 = ventil_z1
              27 = Header-Pin 13 = Relais 2 = ventil_z2
              22 = Header-Pin 15 = Relais 3 = ventil_z3
Erwartung: Relais-LED aus -> 5 s an -> aus. Sonst nichts klickt.
"""
import sys, os, subprocess
from time import sleep

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.drivers.relay_3_2_valve_base import build_output_pin

BCM = int(sys.argv[1]) if len(sys.argv) > 1 else 17
AN_SEKUNDEN = float(sys.argv[2]) if len(sys.argv) > 2 else 5


def zeige(text):
    pc = subprocess.run(["pinctrl", "get", str(BCM)], capture_output=True, text=True).stdout.strip()
    print(f"{text:28s} pinctrl: {pc}", flush=True)


pin = build_output_pin(BCM, inverted=True, initial_position="A", simulate=False, release_when_off=True)
try:
    zeige("AUS (losgelassen)")
    sleep(3)
    pin.on()
    zeige(f"AN  (Masse) fuer {AN_SEKUNDEN:g} s")
    sleep(AN_SEKUNDEN)
    pin.off()
    zeige("AUS (losgelassen)")
    sleep(2)
finally:
    pin.off()
    pin.close()
    zeige("Pin freigegeben")
