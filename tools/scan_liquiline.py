# Reiner LESE-Scan fuer den Endress+Hauser Liquiline CM442/CM448: sucht Anschluss, Busadresse,
# Baudrate, Paritaet und Uebertragungsmodus, wenn nichts davon bekannt ist.
#
# SICHERHEIT - am Geraet darf nichts veraendert werden:
#   Gesendet wird ausschliesslich Funktionscode 0x03 ("Read Holding Registers"), ein reiner
#   Lesebefehl. Die schreibenden Funktionscodes (0x05 Write Single Coil, 0x06 Write Single
#   Register, 0x0F/0x10 Write Multiple) kommen im Skript nicht vor. Durchgesetzt wird das von
#   _guarded_write() unten mit drei Sperren VOR jedem einzelnen ser.write(): Whitelist des
#   Funktionscodes, Adressbereich 1-247 (0 = Broadcast gesperrt, weil Broadcast nur fuer
#   Schreibbefehle sinnvoll ist und keine Antwort erzeugt) und eine Kontrolle des Funktionscode-
#   Bytes im fertigen Frame. Schlaegt eine an, bricht das Skript hart ab.
#
# Was gescannt wird und warum (Quelle: docs/handbuch_liquiline_modbus.pdf):
#   - MODUS: Das Geraet beherrscht ueber RS485 sowohl Modbus ASCII (":" + Hex + LRC + CRLF,
#     Abschnitt 3.2.1) als auch Modbus RTU (binaer + CRC16, Abschnitt 3.2.2). Welcher am Geraet
#     eingestellt ist, wissen wir nicht - deshalb beide. Der Treiber
#     backend/drivers/endress_hauser_liquiline.py spricht ASCII, deshalb steht ASCII zuerst.
#   - BAUDRATE: Handbuch nennt 1200-115200 bei Werkseinstellung 19200 - alle acht werden probiert,
#     die Werkseinstellung zuerst.
#   - PARITAET: Modbus-ueblich ist gerade (E); N und O werden mitgeprueft, weil die Einstellung am
#     Geraet aenderbar ist.
#   - BUSADRESSE: 1-247. Werkseinstellung ist 247; config.yml:85 behauptet, das Geraet sei auf 1
#     gesetzt - am Geraet NICHT bestaetigt. Stufe 1 prueft deshalb nur diese beiden Kandidaten
#     ueber alle uebrigen Kombinationen (schnell); erst wenn das leer bleibt, faehrt Stufe 2 den
#     vollen Adressbereich ab (--voll erzwingt Stufe 2 sofort).
#
# Gelesen wird Register 0 (= AI1 Value, erstes Register des ersten AI-Blocks, Abschnitt 7.3.2.2),
# ein Register. Welcher Wert dort steht, ist fuer den Scan egal - es zaehlt nur, DASS eine
# formal gueltige Antwort mit passender Adresse und Pruefsumme zurueckkommt.
#
# Aufruf aus der Repo-Wurzel:
#     .venv/bin/python tools/scan_liquiline.py                 # alle Anschluesse, Stufe 1 (+2)
#     .venv/bin/python tools/scan_liquiline.py --dry-run       # zeigt nur Frames und Portliste
#     .venv/bin/python tools/scan_liquiline.py --port /dev/serial/by-id/usb-...
#     .venv/bin/python tools/scan_liquiline.py --voll          # sofort Adressen 1-247
import glob
import os
import sys
import time

import serial

_HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HIER)
sys.path.insert(0, os.path.dirname(_HIER))   # Repo-Wurzel, fuer backend.*
from backend.drivers.endress_hauser_liquiline import _lrc  # noqa: E402

FC_READ_HOLDING = 0x03       # einziger erlaubter Funktionscode, reiner Lesebefehl
FC_VERBOTEN = (0x05, 0x06, 0x0F, 0x10)   # schreibende Funktionscodes

START_REGISTER = 0           # AI1 Value (Abschnitt 7.3.2.2)
ANZAHL_REGISTER = 1

BAUDRATES = [19200, 9600, 38400, 57600, 115200, 4800, 2400, 1200]  # Werkseinstellung zuerst
PARITIES = [serial.PARITY_EVEN, serial.PARITY_NONE, serial.PARITY_ODD]
MODI = ["ASCII", "RTU"]
ADRESSEN_STUFE1 = [1, 247]       # config.yml-Behauptung, dann Werkseinstellung
ADRESSEN_STUFE2 = range(1, 248)  # voller Modbus-Adressbereich, 0 = Broadcast ausgenommen


class SafetyViolation(RuntimeError):
    """Wird geworfen, bevor irgendetwas auf die Leitung geht."""


# --------------------------------------------------------------------------- Pruefsummen

def _crc16(data: bytes) -> int:
    """CRC-16/MODBUS (Poly 0x8005 reflektiert = 0xA001, Startwert 0xFFFF), Rueckgabe als int.
    Auf der Leitung steht er little-endian (niederwertiges Byte zuerst)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def _pdu(bus_address: int) -> bytes:
    """Adresse + Funktionscode + Startregister(2B) + Anzahl(2B) - fuer beide Modi identisch,
    sie unterscheiden sich nur in Rahmen und Pruefsumme."""
    return bytes([bus_address, FC_READ_HOLDING]) + START_REGISTER.to_bytes(2, "big") \
        + ANZAHL_REGISTER.to_bytes(2, "big")


def _frame_ascii(bus_address: int) -> bytes:
    """':' + Hexdarstellung der PDU + LRC(2 Hexzeichen) + CRLF (Abschnitt 3.2.1)."""
    pdu = _pdu(bus_address)
    return f":{pdu.hex().upper()}{_lrc(pdu):02X}\r\n".encode("ascii")


def _frame_rtu(bus_address: int) -> bytes:
    """PDU + CRC16 little-endian, kein Rahmenzeichen (Abschnitt 3.2.2)."""
    pdu = _pdu(bus_address)
    return pdu + _crc16(pdu).to_bytes(2, "little")


# --------------------------------------------------------------------------- Sperre

def _guarded_write(ser, bus_address: int, modus: str) -> bytes:
    """Einziger Pfad, ueber den dieses Skript auf die serielle Schnittstelle schreibt."""
    if not 1 <= bus_address <= 247:
        raise SafetyViolation(f"Busadresse {bus_address} ausserhalb 1-247 (0 = Broadcast gesperrt).")
    if FC_READ_HOLDING not in (0x03, 0x04):
        raise SafetyViolation(f"Funktionscode {FC_READ_HOLDING:#04x} ist kein Lesebefehl.")

    frame = _frame_ascii(bus_address) if modus == "ASCII" else _frame_rtu(bus_address)

    # Kontrolle am fertigen Frame: das Funktionscode-Byte muss 0x03 sein und darf keiner der
    # schreibenden Codes sein - in ASCII steht es als zwei Hexzeichen an Position 3-4.
    gesendet_fc = int(frame[3:5], 16) if modus == "ASCII" else frame[1]
    if gesendet_fc != FC_READ_HOLDING or gesendet_fc in FC_VERBOTEN:
        raise SafetyViolation(f"Frame traegt Funktionscode {gesendet_fc:#04x}: "
                              f"{frame.hex(' ').upper()}")

    ser.reset_input_buffer()
    ser.write(frame)
    ser.flush()
    return frame


# --------------------------------------------------------------------------- Antwort pruefen

def _interpret(rohbytes: bytes, bus_address: int, modus: str):
    """(ok, Text) - prueft Rahmen, Adresse und Pruefsumme einer Antwort."""
    if modus == "ASCII":
        if not rohbytes.startswith(b":"):
            return False, "kein ':' am Anfang - kein Modbus-ASCII-Rahmen"
        koerper = rohbytes[1:].split(b"\r")[0]
        try:
            roh = bytes.fromhex(koerper.decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            return False, f"keine gueltige Hexdarstellung: {rohbytes!r}"
        if len(roh) < 3:
            return False, f"Antwort zu kurz: {roh.hex(' ').upper()}"
        nutzlast, pruefsumme = roh[:-1], roh[-1]
        erwartet = _lrc(nutzlast)
        if pruefsumme != erwartet:
            return False, f"LRC falsch (ist {pruefsumme:02X}, erwartet {erwartet:02X})"
    else:
        if len(rohbytes) < 4:
            return False, f"Antwort zu kurz: {rohbytes.hex(' ').upper()}"
        nutzlast, pruefsumme = rohbytes[:-2], int.from_bytes(rohbytes[-2:], "little")
        erwartet = _crc16(nutzlast)
        if pruefsumme != erwartet:
            return False, f"CRC16 falsch (ist {pruefsumme:04X}, erwartet {erwartet:04X})"

    antwort_adresse, funktion = nutzlast[0], nutzlast[1]
    if antwort_adresse != bus_address:
        return False, f"fremde Adresse {antwort_adresse} (gefragt war {bus_address})"
    if funktion == FC_READ_HOLDING | 0x80:
        # Ausnahmeantwort - das Geraet IST da, lehnt nur dieses Register ab. Das ist ein Treffer!
        code = nutzlast[2] if len(nutzlast) > 2 else 0
        return True, f"Modbus-Ausnahme {code} auf FC03 - Geraet antwortet, Register abgelehnt"
    if funktion != FC_READ_HOLDING:
        return False, f"unerwarteter Funktionscode {funktion:#04x}"
    return True, f"gueltige FC03-Antwort, {len(nutzlast) - 3} Byte Registerdaten"


def _lesen(ser, fenster: float, echo: bytes) -> bytes:
    """Sammelt bis zum Ablauf des Zeitfensters und verwirft ein eventuelles Sende-Echo
    (manche RS485-Adapter spiegeln im Halbduplexbetrieb das eigene Senden zurueck)."""
    puffer = bytearray()
    ende = time.monotonic() + fenster
    while time.monotonic() < ende:
        brocken = ser.read(256)
        if brocken:
            puffer.extend(brocken)
    if puffer.startswith(echo):
        del puffer[:len(echo)]
    return bytes(puffer)


# --------------------------------------------------------------------------- Selbsttest

def selftest():
    """Rechnet beide Pruefsummen gegen oeffentliche Referenzwerte nach, bevor Hardware angefasst
    wird. Das Handbuch selbst enthaelt kein durchgerechnetes Beispiel (siehe Treiberkommentar),
    deshalb wird gegen die Modbus-Spezifikation geprueft."""
    # LRC: kanonisches Modbus-ASCII-Beispiel FC03, Slave 0x11, Start 0x006B, Anzahl 3 -> LRC 0x7E
    referenz = bytes.fromhex("1103006B0003")
    assert _lrc(referenz) == 0x7E, f"LRC-Selbsttest: {_lrc(referenz):02X} != 7E"

    # CRC-16/MODBUS: Pruefwert des CRC-Katalogs fuer die Eingabe "123456789" ist 0x4B37.
    assert _crc16(b"123456789") == 0x4B37, f"CRC-Selbsttest: {_crc16(b'123456789'):04X} != 4B37"

    # Struktureigenschaft von CRC-16/MODBUS: der CRC ueber Nutzlast+angehaengten CRC ist 0.
    rahmen = _frame_rtu(1)
    assert _crc16(rahmen) == 0, f"CRC-Restwert-Selbsttest: {_crc16(rahmen):04X} != 0000"

    print("Selbsttest: LRC (Modbus-ASCII-Referenz), CRC16 (Katalog-Pruefwert 4B37) und "
          "CRC-Restwert stimmen.")
    print(f"  ASCII-Frame an Busadresse 1: {_frame_ascii(1)!r}")
    print(f"  RTU-Frame   an Busadresse 1: {_frame_rtu(1).hex(' ').upper()}")


# --------------------------------------------------------------------------- Scan

def ports():
    gefunden = sorted(glob.glob("/dev/serial/by-id/*"))
    if not gefunden:
        gefunden = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    if "--port" in sys.argv:
        gefunden = [sys.argv[sys.argv.index("--port") + 1]]
    return gefunden


def scan_port(port, adressen):
    treffer, unklar = [], []
    for modus in MODI:
        for baudrate in BAUDRATES:
            for parity in PARITIES:
                label = f"{modus:<5} {baudrate:>6} Baud  Paritaet {parity}"
                try:
                    ser = serial.Serial(port, baudrate=baudrate, bytesize=8, parity=parity,
                                        stopbits=1, timeout=0.05)
                except serial.SerialException as fehler:
                    print(f"    [{label}] nicht zu oeffnen: {fehler}")
                    return treffer, unklar
                # Ein FC03-Anfrage/Antwort-Paar ist in ASCII ~34 Byte; bei 1200 Baud sind das
                # allein ~0,3 s Uebertragungszeit.
                fenster = 0.35 if baudrate <= 2400 else 0.12
                print(f"    [{label}] {len(adressen)} Adressen ...", end="", flush=True)
                with ser:
                    time.sleep(0.3)   # Adapter/Leitung beruhigen lassen
                    for adresse in adressen:
                        frame = _guarded_write(ser, adresse, modus)
                        antwort = _lesen(ser, fenster, echo=frame)
                        if not antwort:
                            continue
                        ok, text = _interpret(antwort, adresse, modus)
                        eintrag = (port, modus, baudrate, parity, adresse,
                                   antwort.hex(" ").upper(), text)
                        (treffer if ok else unklar).append(eintrag)
                        print(f"\n      {'TREFFER' if ok else 'unklar '} Adresse {adresse:>3}: "
                              f"{antwort.hex(' ').upper()}  -> {text}", end="")
                print(" fertig.")
    return treffer, unklar


def durchlauf(liste, adressen, stufe):
    print(f"\n{'=' * 78}\nStufe {stufe}: {len(adressen)} Adressen x {len(MODI)} Modi x "
          f"{len(BAUDRATES)} Baudraten x {len(PARITIES)} Paritaeten je Anschluss\n{'=' * 78}")
    treffer, unklar = [], []
    for nummer, port in enumerate(liste, 1):
        print(f"\n[{nummer}/{len(liste)}] {port}")
        t, u = scan_port(port, adressen)
        treffer.extend(t)
        unklar.extend(u)
    return treffer, unklar


def bericht(treffer, unklar):
    print("\n" + "=" * 78)
    if treffer:
        print("GEFUNDEN:")
        for port, modus, baudrate, parity, adresse, roh, text in treffer:
            print(f"  Anschluss   : {port}")
            print(f"  Busadresse  : {adresse}")
            print(f"  Baudrate    : {baudrate}, Paritaet {parity}, 8 Datenbits, 1 Stoppbit")
            print(f"  Modus       : Modbus {modus}")
            print(f"  Rohantwort  : {roh}")
            print(f"  Befund      : {text}\n")
        port, modus, baudrate, parity, adresse, _, _ = treffer[0]
        print("Fuer config.yml unter liquiline:")
        print(f"      address: {port}")
        print(f"      bus_address: {adresse}")
        if modus != "ASCII":
            print(f"      # ACHTUNG: Geraet spricht Modbus RTU, der Treiber spricht ASCII!")
            print(f"      # Entweder das Geraet auf ASCII umstellen oder den Treiber erweitern.")
    else:
        print("KEINE gueltige Antwort - kein Anschluss, keine Adresse, keine Baudrate, kein Modus.")
        print("Moegliche Ursachen: Geraet aus; RS485 nicht angeklemmt; A/B vertauscht;")
        print("Modbus am Geraetemenue nicht freigeschaltet (Liquiline braucht ggf. eine")
        print("Freischaltung der Feldbus-Schnittstelle); Adapter defekt.")
    if unklar:
        print(f"\n{len(unklar)} Reaktionen, die kein gueltiger Frame waren (Auszug) - "
              f"das ist trotzdem ein Lebenszeichen auf der Leitung:")
        for port, modus, baudrate, parity, adresse, roh, text in unklar[:15]:
            print(f"  {os.path.basename(port)}, {modus} {baudrate}/{parity}, Adresse {adresse}: "
                  f"{roh}  -> {text}")
    print("=" * 78)


def main():
    liste = ports()
    if not liste:
        print("Kein serieller Anschluss gefunden.")
        return 1
    print(f"\n{len(liste)} Anschluesse:")
    for port in liste:
        ziel = os.path.realpath(port)
        print(f"  {port}" + (f"  -> {os.path.basename(ziel)}" if ziel != port else ""))
    print("\nGesendet wird ausschliesslich Funktionscode 03 (Read Holding Registers).")

    if "--dry-run" in sys.argv:
        print("\n--dry-run: Es wurde nichts gesendet.")
        return 0

    if "--voll" in sys.argv:
        treffer, unklar = durchlauf(liste, list(ADRESSEN_STUFE2), 2)
    else:
        treffer, unklar = durchlauf(liste, ADRESSEN_STUFE1, 1)
        if not treffer:
            print("\nStufe 1 ohne Treffer - jetzt der volle Adressbereich 1-247.")
            t2, u2 = durchlauf(liste, list(ADRESSEN_STUFE2), 2)
            treffer, unklar = t2, unklar + u2
    bericht(treffer, unklar)
    return 0


if __name__ == "__main__":
    selftest()
    sys.exit(main())
