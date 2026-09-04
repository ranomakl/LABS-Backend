# Diagnose: braucht der RS485-Adapter RTS als Sendefreigabe (DE), die pro Frame umgeschaltet wird?
#
# probe_rts.py testet nur STATISCHE RTS-Zustaende. Bei einem Adapter mit RTS-gesteuertem
# Treiberbaustein ist statisch aber immer falsch: dauerhaft an heisst, wir halten den Bus
# besetzt und koennen die Antwort der Pumpe gar nicht hoeren; dauerhaft aus heisst, unser
# Frame erreicht die Leitung nie. Richtig ist: RTS vor dem Frame setzen, nach dem letzten
# Bit wieder loesen. Genau das macht dieses Skript - fuer beide Polaritaeten.
#
# Gleiche RID-Sperre wie scan_pumpe.py (importiert): nur Lesebefehl, kein WJ, kein WID.
import sys, time, serial
import os
_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HIER)                    # Nachbarskripte (scan_pumpe)
sys.path.insert(0, os.path.dirname(_HIER))   # Repo-Wurzel, fuer backend.*
from scan_pumpe import PORT, CMD_RID, _guarded_write, _read_frames, _interpret

if "--port" in sys.argv:
    PORT = sys.argv[sys.argv.index("--port") + 1]

# rts_bei_tx: Pegel, der waehrend des Sendens anliegt. Beide Polaritaeten, weil die Boards
# das unterschiedlich verdrahten (manche invertieren RTS auf dem Weg zum DE-Pin).
for rts_bei_tx in (True, False):
    for baudrate, paritaet in ((1200, "E"), (9600, "E")):
        reaktionen = 0
        with serial.Serial(PORT, baudrate=baudrate, bytesize=8, parity=paritaet,
                           stopbits=1, timeout=0.05) as ser:
            ser.rts = not rts_bei_tx      # Ruhezustand: empfangsbereit
            time.sleep(0.1)
            for address in range(1, 31):
                ser.rts = rts_bei_tx
                # _guarded_write() ruft flush(), das unter POSIX auf tcdrain wartet - kehrt
                # also erst zurueck, wenn das letzte Bit die Schnittstelle verlassen hat.
                frame = _guarded_write(ser, address, CMD_RID)
                time.sleep(11.0 / baudrate)   # ein Zeichenrahmen Nachlauf (11 Bit bei 8E1)
                ser.rts = not rts_bei_tx      # zurueck auf Empfang, bevor die Pumpe antwortet
                frames, rest = _read_frames(ser, 0.6 if baudrate <= 1200 else 0.3, echo=frame)
                for reply in frames:
                    ok, text = _interpret(reply)
                    reaktionen += 1
                    print(f"  {'TREFFER' if ok else 'unklar '} RTS-TX={rts_bei_tx} "
                          f"{baudrate}Bd Adr {address}: {reply.hex(' ').upper()} -> {text}")
                if rest:
                    reaktionen += 1
                    print(f"  Rest    RTS-TX={rts_bei_tx} {baudrate}Bd Adr {address}: "
                          f"{rest.hex(' ').upper()}")
        print(f"RTS waehrend TX = {rts_bei_tx}, {baudrate} Baud/{paritaet}: "
              f"{reaktionen} Reaktionen")
