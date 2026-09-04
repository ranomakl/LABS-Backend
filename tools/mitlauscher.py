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


def _durchgang(sender, hoerer, name_sender, name_hoerer):
    """Sendet 30 RID-Frames auf `sender` und sammelt alles, was auf `hoerer` ankommt."""
    print(f"\n--- {name_sender}  ==>  {name_hoerer} ---")
    hoerer.reset_input_buffer()
    empfangen = bytearray()
    for address in range(1, 31):
        _guarded_write(sender, address, CMD_RID)
        ende = time.monotonic() + 0.25
        while time.monotonic() < ende:
            brocken = hoerer.read(64)
            if brocken:
                empfangen.extend(brocken)
    print(f"{len(empfangen)} von ~{ERWARTET} erwarteten Bytes empfangen.")
    if empfangen:
        print(f"Erste 60 Bytes: {bytes(empfangen[:60]).hex(' ').upper()}")
    return bytes(empfangen)


def _sauber(rohbytes):
    """True, wenn erkennbar echte Frames ankamen (Startflag E9 im Datenstrom)."""
    return 0xE9 in rohbytes[:16]


print(f"Adapter 1 (an der Pumpe): {TX_PORT}")
print(f"Adapter 2 (Mitlauscher):  {RX_PORT}")
print(f"{BAUDRATE} Baud, Paritaet {PARITAET}, Adressen 1-30, nur RID.")

with serial.Serial(TX_PORT, baudrate=BAUDRATE, bytesize=8, parity=PARITAET,
                   stopbits=1, timeout=0.05) as a1, \
     serial.Serial(RX_PORT, baudrate=BAUDRATE, bytesize=8, parity=PARITAET,
                   stopbits=1, timeout=0.05) as a2:
    time.sleep(0.2)
    hin = _durchgang(a1, a2, "Adapter 1", "Adapter 2")
    zurueck = _durchgang(a2, a1, "Adapter 2", "Adapter 1")

# Beide Richtungen einzeln auszuwerten trennt Sende- von Empfangsfehler. Genau darauf kommt es
# an: Adapter 1 hat in allen bisherigen Laeufen nie ein einziges Byte empfangen - ob sein
# Empfangszweig ueberhaupt funktioniert, war nie gemessen.
print("\n" + "=" * 70)
if _sauber(hin) and _sauber(zurueck):
    print("BEIDE RICHTUNGEN IN ORDNUNG.")
    print("Beide Adapter senden und empfangen, die Leitung bis zur Klemme steht, A/B sind")
    print("zueinander richtig herum. Der Fehler sitzt damit hinter der Klemme: Pumpe,")
    print("DB15-Modul, Verpolung zur Pumpe hin, oder die Pumpe antwortet schlicht nicht.")
    print("Naechster Schritt: A/B AN DER PUMPENSEITE tauschen, dann tools/schnelltest.py.")
elif _sauber(hin) and not zurueck:
    print("ADAPTER 1 SENDET, EMPFAENGT ABER NICHT.")
    print("Das erklaert den bisherigen Befund vollstaendig - 0 Byte auf jeder Parameter-")
    print("kombination, weil der Empfangszweig taub ist. Rollentausch pruefen: Adapter 2 an")
    print("die Pumpe, dann tools/schnelltest.py --port <Adapter 2>.")
elif zurueck and not hin:
    print("ADAPTER 1 SENDET NICHT (empfaengt aber).")
    print("Sendefreigabe oder Treiberbaustein defekt. Rollentausch wie oben.")
elif hin or zurueck:
    print("BYTES KOMMEN AN, ABER VERZERRT.")
    print("Typisch fuer vertauschte A/B zwischen den Adaptern oder unterschiedliche Baudraten.")
    print("A/B an Adapter 2 tauschen und noch einmal messen.")
else:
    print("IN KEINER RICHTUNG ETWAS.")
    print("Erst pruefen: liegen A/B/GND beider Adapter wirklich auf DENSELBEN Klemmen?")
    print("Dann A/B an Adapter 2 tauschen und wiederholen. Bleibt es dabei, sind beide")
    print("Adapter zusammen nicht funktionsfaehig - dann die beiden Adapter direkt")
    print("miteinander verbinden (A-A, B-B, GND-GND, nichts sonst) und erneut messen.")
print("=" * 70)
