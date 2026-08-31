# Reiner LESE-Scan fuer die Longer WT600-2J: sucht Pumpenadresse und Baudrate per RID-Befehl
# ("Read pump address"), weil das Geraet kein zugaengliches Display hat.
#
# SICHERHEIT - die Pumpe darf sich unter keinen Umstaenden drehen:
#   Es wird ausschliesslich die PDU b"RID" gesendet. WJ ("Set running parameter", der einzige
#   Befehl, der den Motor startet) und WID ("Write pump address") kommen im Skript nicht vor.
#   Durchgesetzt wird das von _guarded_write() unten mit drei unabhaengigen Sperren, die VOR
#   jedem einzelnen ser.write() greifen (Whitelist der PDU, Adressbereich 1-30 ohne Broadcast,
#   Byte-Muster-Kontrolle am fertigen Frame). Schlaegt eine an, bricht das Skript hart ab.
#
# Die Frame-/Pruefsummenlogik wird bewusst aus dem Treiber importiert statt nachgebaut, damit
# der Scan exakt das Frameformat testet, das der Treiber spaeter auch spricht.
# Protokoll: docs/protokoll_pumpe.md.
import sys
import time

import serial

import os
_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HIER)                    # Nachbarskripte (scan_pumpe)
sys.path.insert(0, os.path.dirname(_HIER))   # Repo-Wurzel, fuer backend.*
from backend.drivers.longer_wt600 import FLAG, _build_frame, _xor  # noqa: E402

# Port ist per --port ueberschreibbar; Vorgabe ist der Adapter an der WT600.
PORT = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BG01XVQG-if00-port0"
if "--port" in sys.argv:
    PORT = sys.argv[sys.argv.index("--port") + 1]
BAUDRATES = [1200, 9600, 19200]
# Die Blogquelle nennt nur 1200 mit gerader Paritaet. Da die Baudrate ohnehin unbekannt ist, ist
# auch die Paritaet nicht gesichert - deshalb je Baudrate beide Varianten. "E" zuerst, weil das
# die dokumentierte ist.
PARITIES = [serial.PARITY_EVEN, serial.PARITY_NONE]
ADDRESSES = range(1, 31)  # 1-30; 31 = Broadcast ist bewusst NICHT dabei (siehe _guarded_write)

CMD_RID = b"RID"  # 52 49 44 - "Read pump address", reiner Lesebefehl


# --------------------------------------------------------------------------- Sperre

ALLOWED_PDUS = frozenset({CMD_RID})
FORBIDDEN_MARKERS = (b"WJ", b"WID")  # Start/Stop-Drehzahlbefehl bzw. Adresse-Ueberschreiben


class SafetyViolation(RuntimeError):
    """Wird geworfen, bevor irgendetwas auf die Leitung geht."""


def _guarded_write(ser, address: int, pdu: bytes) -> bytes:
    """Einziger Pfad, ueber den dieses Skript auf die serielle Schnittstelle schreibt.
    Baut den Frame, prueft ihn dreifach und sendet ihn erst dann."""
    if pdu not in ALLOWED_PDUS:
        raise SafetyViolation(f"PDU {pdu!r} steht nicht auf der Whitelist {set(ALLOWED_PDUS)}.")
    if not 1 <= address <= 30:
        raise SafetyViolation(f"Adresse {address} ausserhalb 1-30 (Broadcast 31 ist gesperrt).")

    frame = _build_frame(address, pdu)

    for marker in FORBIDDEN_MARKERS:
        if marker in frame:
            raise SafetyViolation(f"Schreibbefehl {marker!r} im Frame {frame.hex(' ').upper()}.")
    if frame[3:3 + len(pdu)] != CMD_RID:
        raise SafetyViolation(f"Frame enthaelt nicht RID: {frame.hex(' ').upper()}.")

    ser.reset_input_buffer()
    ser.write(frame)
    ser.flush()
    return frame


# --------------------------------------------------------------------------- Antwort lesen

def _read_frames(ser, window: float, echo: bytes):
    """Sammelt bis zum Ablauf des Zeitfensters und gibt alle vollstaendigen Frames zurueck.
    Frames, die identisch mit der eigenen Anfrage sind, werden verworfen - manche RS485-Adapter
    spiegeln im Halbduplexbetrieb das eigene Senden zurueck."""
    buffer, frames = bytearray(), []
    deadline = time.monotonic() + window
    while time.monotonic() < deadline:
        chunk = ser.read(64)
        if chunk:
            buffer.extend(chunk)
        while True:
            while buffer and buffer[0] != FLAG:
                del buffer[0]  # Rauschen bis zum naechsten moeglichen Frameanfang verwerfen
            if len(buffer) < 3:
                break
            length = 3 + buffer[2] + 1  # Flag+Adresse+Laengenbyte + PDU + FCS
            if len(buffer) < length:
                break
            frame = bytes(buffer[:length])
            del buffer[:length]
            if frame != echo:
                frames.append(frame)
    return frames, bytes(buffer)


def _interpret(frame: bytes):
    """(ok, Text) - prueft Pruefsumme und Befehlsecho eines Antwortframes."""
    address, length = frame[1], frame[2]
    pdu, fcs = frame[3:3 + length], frame[-1]
    expected = _xor(frame[1:-1])
    if fcs != expected:
        return False, f"Pruefsumme falsch (ist {fcs:02X}, erwartet {expected:02X})"
    if pdu[:3] != CMD_RID:
        return False, f"kein RID-Echo, PDU = {pdu!r}"
    return True, f"RID bestaetigt, Geraet meldet Adresse {address}"


# --------------------------------------------------------------------------- Selbsttest

def selftest():
    """Rechnet die Frame-/Pruefsummenlogik gegen die Beispiele aus docs/protokoll_pumpe.md nach,
    bevor die Hardware angefasst wird. Die Beispiele sind Schreibframes - hier werden sie NICHT
    gesendet, sondern nur rechnerisch verglichen."""
    known = [
        (1, b"\x57\x4a\x00\x96\x01\x01", "E9 01 06 57 4A 00 96 01 01 8C"),
        (1, b"\x57\x49\x44\x07", "E9 01 04 57 49 44 07 58"),
        (4, b"\x57\x4a\x01\x40\x01\x01", "E9 04 06 57 4A 01 40 01 01 5E"),
        (4, b"\x57\x4a\x00\x32\x01\x00", "E9 04 06 57 4A 00 32 01 00 2C"),
        (4, b"\x57\x4a\x00\x32\x00\x00", "E9 04 06 57 4A 00 32 00 00 2D"),
    ]
    for address, pdu, expected in known:
        got = _build_frame(address, pdu).hex(" ").upper()
        assert got == expected, f"Selbsttest fehlgeschlagen: {got} != {expected}"
    print(f"Selbsttest: {len(known)}/{len(known)} Referenzframes aus docs/protokoll_pumpe.md "
          f"stimmen byte-genau.")
    print(f"RID-Frame an Adresse 1: {_build_frame(1, CMD_RID).hex(' ').upper()}")


# --------------------------------------------------------------------------- Scan

def scan():
    hits = []
    noise = []
    for baudrate in BAUDRATES:
        for parity in PARITIES:
            label = f"{baudrate} Baud, Paritaet {parity}"
            try:
                ser = serial.Serial(PORT, baudrate=baudrate, bytesize=8, parity=parity,
                                    stopbits=1, timeout=0.05)
            except serial.SerialException as error:
                print(f"[{label}] Port nicht zu oeffnen: {error}")
                continue

            # Bei 1200 Baud dauert allein ein 7-Byte-Frame ~64 ms je Richtung.
            window = 0.8 if baudrate <= 1200 else 0.4
            print(f"[{label}] Adressen 1-30 ...", end="", flush=True)
            with ser:
                time.sleep(0.1)  # Adapter/Leitung beruhigen lassen
                for address in ADDRESSES:
                    frame = _guarded_write(ser, address, CMD_RID)
                    frames, rest = _read_frames(ser, window, echo=frame)
                    for reply in frames:
                        ok, text = _interpret(reply)
                        entry = (baudrate, parity, address, reply.hex(" ").upper(), text)
                        (hits if ok else noise).append(entry)
                        print(f"\n  {'TREFFER' if ok else 'unklar '} Adresse {address:>2}: "
                              f"{reply.hex(' ').upper()}  -> {text}", end="")
                    if rest:
                        noise.append((baudrate, parity, address, rest.hex(" ").upper(),
                                      "unvollstaendige Bytes"))
                        print(f"\n  Rest    Adresse {address:>2}: {rest.hex(' ').upper()}", end="")
            print(" fertig.")

    print("\n" + "=" * 70)
    if hits:
        print("GEFUNDEN:")
        for baudrate, parity, address, raw, text in hits:
            print(f"  {baudrate} Baud, Paritaet {parity}, angefragte Adresse {address}: {text}")
            print(f"      Rohframe: {raw}")
        print("\nFuer config.yml unter dosing_pump:")
        baudrate, parity, address, _, _ = hits[0]
        print(f"      pump_address: {address}")
        print(f"      serial_parameters:")
        print(f"        baudrate: {baudrate}")
        if parity != "E":
            print(f"        parity: \"{parity}\"   # weicht von der Blogquelle (E) ab!")
    else:
        print("KEINE Antwort auf keiner Kombination.")
        print("Moegliche Ursachen: Pumpe aus; RS485-Modul nicht im DB15-Port; A/B vertauscht;")
        print("Adapter sendet RS232 statt RS485; andere Baudrate als die drei getesteten.")
    if noise:
        print(f"\n{len(noise)} unklare/unvollstaendige Antworten (Auszug):")
        for entry in noise[:10]:
            print(f"  {entry[0]} Baud/{entry[1]}, Adresse {entry[2]}: {entry[3]}  -> {entry[4]}")
    print("=" * 70)


if __name__ == "__main__":
    selftest()
    if "--dry-run" in sys.argv:
        print("\n--dry-run: Es wurde nichts gesendet.")
        print("RID-Frames, die der Scan senden wuerde:")
        for address in ADDRESSES:
            print(f"  Adresse {address:>2}: {_build_frame(address, CMD_RID).hex(' ').upper()}")
        sys.exit(0)
    print(f"\nPort: {PORT}")
    print(f"Gesendet wird ausschliesslich RID (Lesebefehl). Kein WJ, kein WID, kein Start.\n")
    scan()
