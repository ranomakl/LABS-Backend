# -*- test-case-name: backend.test.test_base -*-
"""
Shared base for drivers that switch a 3/2-way valve (two flow paths, "A" and "B") through a relay
that is itself driven by setting a Raspberry Pi GPIO pin high/low (via gpiozero) - not by sending
a command over a wire protocol.

This is a fundamentally different situation from every other driver in backend/drivers/: there is
no request/response, no reply to parse, and no way to ever read the real valve position back - the
device only ever knows the position it last *told* the relay to take. To still reuse
AbstractBaseDevice's cmd_queue/state machine (so valve moves are correctly sequenced with other
device commands, and so `device.wait(...)` / stopconditions work exactly like for every other
device), `NoWireProtocol` below stands in for the usual `BaseDeviceProtocol`: instead of writing
bytes to a socket/serial port, it drives the GPIO pin directly, in-process. See the module
docstring in the concrete driver (e.g. raspi_gpio_relay_valve.py) for the safety-critical
explanation of the `inverted` flag.
"""
from backend.devices.base import *
from abc import ABC, abstractmethod

from twisted.logger import Logger

_log = Logger(namespace="relay_3_2_valve_base")

POSITIONS = ("A", "B")


def normalize_position(position) -> str:
    """Accepts "a"/"A"/"b"/"B" (whitespace-tolerant); raises ValueError on anything else. Used both
    for `safe_state` from config.yml and for `set_position(...)` arguments, so a typo fails loudly
    instead of silently doing nothing to the valve."""
    try:
        normalized = position.strip().upper()
    except AttributeError:
        raise ValueError(f"Valve position must be a string, got {position!r}.")
    if normalized not in POSITIONS:
        raise ValueError(f"Valve position must be one of {POSITIONS}, got {position!r}.")
    return normalized


class NoWireProtocol:
    """
    Stand-in for BaseDeviceProtocol, used as `self.protocol` on the device.

    VERIFIED against the current implementation (backend/commands/commands.py Command.execute and
    backend/devices/devicestate.py Shutdown.enter): only `write_command(command_object)` and
    `lose_connection()` are ever called on `device.protocol` for a device that never receives
    anything (replies_commands = False) - so those are the only two methods this stand-in needs to
    provide. It does NOT subclass BaseDeviceProtocol/LineReceiver, because there is no byte stream
    to receive on.
    """
    def __init__(self, device):
        self.device = device

    def write_command(self, command_object) -> None:
        self.device.drive_pin(command_object.parameters.commandstring)

    def lose_connection(self) -> None:
        pass  # nothing to disconnect; only present so Shutdown.enter() has something to call


class ReleasingOutputPin:
    """
    Pin-Objekt fuer Low-Active-Relaisplatinen, deren Steuerseite an 5 V haengt (28.10.2026, GC-Ventile).

    Problem: Solche Platinen schalten das Relais ueber den Spannungsunterschied zwischen ihren 5 V und dem
    Pi-Pin. Pin auf Masse = 5 V Unterschied = an. Pin auf 3,3 V = 1,7 V Unterschied = IMMER NOCH AN. Der Pi
    kann das Relais also einschalten, aber nicht ausschalten - mit keiner Einstellung von `inverted`.
    Loesung hier: "aus" = Pin LOSLASSEN (Eingang mit Pull-Down, wie vor dem Backend-Start). Dann zieht die
    Platine ihren Eingang selbst auf 5 V -> Unterschied 0 -> Relais aus. "an" = Pin als Ausgang auf Masse.
    Siehe docs/relaisplatine_erklaerung_28-10-2026.txt.

    Nachteil: Im losgelassenen Zustand drueckt die Platine ueber Widerstand + Optokoppler ca. 3,8 V in den
    Pi-Eingang (Schutzdiode faengt es ab, Strom < 1 mA). Die saubere Loesung bleibt, die Steuerseite der
    Platine auf 3,3 V zu legen und dann normal mit inverted: true (ohne release_when_off) zu fahren.

    Gleiche Schnittstelle wie gpiozero.DigitalOutputDevice, soweit der Treiber sie benutzt:
    .on() = Relais bestromen, .off() = Relais stromlos, .value, .close().
    """
    PULL_WHEN_RELEASED = "down"   # Zustand, in dem die Relais am 27.10. vor dem Backend-Start nachweislich aus waren

    def __init__(self, pin_number: int, *, initial_value: bool, simulate: bool):
        if simulate:
            from gpiozero.pins.mock import MockFactory
            self.factory = MockFactory()
        else:
            from gpiozero import Device
            Device.ensure_pin_factory()
            self.factory = Device.pin_factory
        self.pin_number = int(pin_number)
        self.pin = self.factory.pin(self.pin_number)
        self._value = None
        if initial_value:
            self.on()
        else:
            self.off()

    def on(self) -> None:
        """Relais bestromen: Pin als Ausgang auf Masse."""
        self.pin.function = "output"
        self.pin.state = 0
        self._value = True

    def off(self) -> None:
        """Relais stromlos: Pin loslassen (Eingang + Pull-Down), die Platine zieht ihn selbst auf ihre 5 V."""
        self.pin.function = "input"
        self.pin.pull = self.PULL_WHEN_RELEASED
        self._value = False

    @property
    def value(self) -> bool:
        return bool(self._value)

    def close(self) -> None:
        try:
            self.pin.close()
        finally:
            self.factory.release_pins(self, self.pin_number)
            self.pin = None


def build_output_pin(pin_number: int, *, inverted: bool, initial_position: str, simulate: bool,
                     release_when_off: bool = False):
    """
    Claim one GPIO pin as a gpiozero DigitalOutputDevice for one relay/valve.

    On the *returned* pin object, calling `.on()` always means "energize the relay" and `.off()`
    always means "de-energize it" - regardless of how the physical board is wired. The electrical
    inversion of a particular relay board is handled once, here, via gpiozero's own `active_high`
    parameter:

        active_high = not inverted

    VERIFIED in this repo's venv against gpiozero 2.0.1: with active_high=False, calling .on()
    drives the physical pin LOW and .off() drives it HIGH - i.e. exactly the inversion described
    for this relay board (see the concrete driver's module docstring for the colleague's working
    reference code this was checked against).

    `initial_value` is passed straight to the gpiozero constructor so the pin is atomically driven
    to `initial_position` the instant it is claimed - it is never left floating or in an
    arbitrary/previous state, however briefly, between process start and the first explicit
    set_position() call.

    `simulate=True` uses gpiozero's MockFactory instead of autodetecting real GPIO hardware - this
    is for developing off a Raspberry Pi (e.g. on Windows) ONLY. It is passed explicitly per pin
    construction (not via the global gpiozero.Device.pin_factory), so enabling it for one
    valve/device in config.yml can never accidentally put a *different*, real valve into
    simulation. When simulate=False (the default) and no real GPIO backend can be found, gpiozero
    raises gpiozero.exc.BadPinFactory - this driver deliberately does NOT catch that and silently
    fall back to a mock, because doing so on real hardware (e.g. after a permissions problem) would
    make the backend believe it is switching a valve when nothing physical happens at all.
    """
    from gpiozero import DigitalOutputDevice

    active_high = not inverted
    # ASSUMPTION: "B" is defined as the energized state, "A" as de-energized/rest - see the
    # concrete driver's module docstring. Not verified against the physical valve wiring.
    initial_value = (initial_position == "B")

    if release_when_off:
        # 28.10.2026: Low-Active-Platine mit 5-V-Steuerseite - "aus" = Pin loslassen statt Pin high.
        # `inverted` spielt hier keine Rolle: "an" ist immer Pin auf Masse (so schaltet jede Low-Active-Platine),
        # "aus" ist immer losgelassen. Es wird nur verlangt, dass inverted: true gesetzt ist, damit die
        # config.yml die Platine ehrlich beschreibt (Masse = an) und ein spaeteres Entfernen von
        # release_when_off (nach Umklemmen auf 3,3 V) nicht in die falsche Richtung schaltet.
        if not inverted:
            raise ValueError(
                f"GPIO pin {pin_number}: release_when_off: true ist nur fuer Low-Active-Platinen gedacht "
                f"(Pin auf Masse = Relais an) und verlangt daher inverted: true.")
        if simulate:
            _log.warn(
                "GPIO pin {pin}: simulate=True -> using gpiozero MockFactory. NO real relay is being "
                "switched. This must only be set for development away from the Raspberry Pi.",
                pin=pin_number,
            )
        return ReleasingOutputPin(pin_number, initial_value=initial_value, simulate=simulate)

    kwargs = dict(active_high=active_high, initial_value=initial_value)
    if simulate:
        from gpiozero.pins.mock import MockFactory
        kwargs["pin_factory"] = MockFactory()
        _log.warn(
            "GPIO pin {pin}: simulate=True -> using gpiozero MockFactory. NO real relay is being "
            "switched. This must only be set for development away from the Raspberry Pi.",
            pin=pin_number,
        )
    # ASSUMPTION: BCM pin numbering (gpiozero's default) - double-check `pin` in config.yml against
    # the physical pin actually wired, not the board's physical pin-header number.
    return DigitalOutputDevice(pin_number, **kwargs)


class BaseDevice(AbstractBaseDevice, ABC):
    @abstractmethod
    def set_position(self, position: str, **kwargs):
        """Move the valve to logical position "A" or "B"."""
        pass
