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


def build_output_pin(pin_number: int, *, inverted: bool, initial_position: str, simulate: bool):
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
