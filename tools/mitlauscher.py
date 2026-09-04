# Diagnose mit ZWEI Adaptern: sendet RID auf dem einen und hoert gleichzeitig auf dem anderen mit.
#
# Warum das die entscheidende Messung ist: bisher kam auf der Empfangsleitung nie ein Byte an -
# aber daraus laesst sich nicht schliessen, ob der Adapter ueberhaupt sendet. Die TXD-LED haengt
# vor dem Treiberbaustein, und viele Halbduplex-Adapter schalten den Empfaenger waehrend des
# Sendens ab, hoeren sich also selbst nicht. Ein zweiter Adapter, parallel an dieselben Klemmen
# geklemmt, trennt die beiden Faelle sauber:
#
#   Mitlauscher empfaengt die Frames -> Adapter 1 treibt den Bus wirklich, die Leitung bis zur
#       Klemme ist in Ordnung. Der Fehler sitzt dann dahinter: Pumpe, DB15-Modul, Verpolung
#       zur Pumpe hin oder falsche Uebertragungsparameter.
#   Mitlauscher empfaengt nichts -> es geht schon vor der Klemme nichts hinaus. Adapter 1 ist
#       kein RS485-Adapter, defekt, oder seine Sendefreigabe kommt nie.
#
# Verkabelung: A von Adapter 2 an A von Adapter 1, B an B, GND an GND (parallel auf denselben
# Klemmen - RS485 ist ein Bus, Mithoeren ist vorgesehen). Kommt nichts an, einmal A/B am
# Mitlauscher tauschen: empfaengt er dann, sind die A/B-Beschriftungen der beiden Adapter
# zueinander vertauscht - genau die Verpolung, die auch zur Pumpe hin bestehen kann.
#
# Gleiche RID-Sperre wie scan_pumpe.py (importiert): gesendet wird nur der Lesebefehl.
import sys, time, serial
import os
_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HIER)                    # Nachbarskripte (scan_pumpe)
sys.path.insert(0, os.path.dirname(_HIER))   # Repo-Wurzel, fuer backend.*
from scan_pumpe import PORT, CMD_RID, _guarded_write

TX_PORT = PORT   # Adapter an der Pumpe
RX_PORT = None   # Mitlauscher, per --rx zu setzen
if "--tx" in sys.argv:
    TX_PORT = sys.argv[sys.argv.index("--tx") + 1]
if "--rx" in sys.argv:
    RX_PORT = sys.argv[sys.argv.index("--rx") + 1]

if RX_PORT is None:
    print("Aufruf: .venv/bin/python tools/mitlauscher.py --rx <Pfad des zweiten Adapters>")
    print("        [--tx <Pfad des Adapters an der Pumpe>]   (Vorgabe: {})".format(TX_PORT))
    print("\nVerfuegbare Schnittstellen:")
    import glob
    for pfad in sorted(glob.glob("/dev/serial/by-id/*")):
        print("   ", pfad)
    sys.exit(1)
if RX_PORT == TX_PORT:
    print("Sende- und Mithoerschnittstelle sind identisch - das misst nichts.")
    sys.exit(1)

BAUDRATE, PARITAET = 1200, "E"
ERWARTET = 30 * 7   # 30 Adressen a 7 Byte RID-Frame

print(f"Senden auf   {TX_PORT}")
print(f"Mithoeren auf {RX_PORT}")
print(f"{BAUDRATE} Baud, Paritaet {PARITAET}, Adressen 1-30, nur RID.\n")

with serial.Serial(RX_PORT, baudrate=BAUDRATE, bytesize=8, parity=PARITAET,
                   stopbits=1, timeout=0.05) as rx, \
     serial.Serial(TX_PORT, baudrate=BAUDRATE, bytesize=8, parity=PARITAET,
                   stopbits=1, timeout=0.05) as tx:
    time.sleep(0.2)
    rx.reset_input_buffer()
    empfangen = bytearray()
    for address in range(1, 31):
        _guarded_write(tx, address, CMD_RID)
        ende = time.monotonic() + 0.25
        while time.monotonic() < ende:
            brocken = rx.read(64)
            if brocken:
                empfangen.extend(brocken)

print(f"Mitlauscher hat {len(empfangen)} von ~{ERWARTET} erwarteten Bytes empfangen.")
if empfangen:
    print(f"Erste 60 Bytes: {bytes(empfangen[:60]).hex(' ').upper()}")
    if empfangen[0] == 0xE9 or 0xE9 in empfangen[:8]:
        print("\n-> Startflag E9 ist dabei: Adapter 1 treibt den Bus korrekt.")
        print("   Der Fehler sitzt hinter der Klemme (Pumpe, DB15-Modul, Verpolung dorthin).")
    else:
        print("\n-> Bytes kommen an, aber verzerrt. Typisch fuer vertauschte A/B oder eine")
        print("   abweichende Baudrate zwischen den beiden Adaptern.")
else:
    print("\n-> Nichts empfangen. Entweder sendet Adapter 1 nicht auf die RS485-Leitung,")
    print("   oder A/B sind zwischen den beiden Adaptern vertauscht. A/B am Mitlauscher")
    print("   tauschen und noch einmal messen - erst dann ist die Aussage belastbar.")
