"""
Driver for a single channel of a 16-channel, 12V relay module, wired to a Raspberry Pi's GPIO pins
via gpiozero, that switches one 3/2-way valve between its two flow paths "A" and "B".

One config.yml `devices:` entry == one relay channel == one GPIO pin == one valve. A 16-channel
board can host up to 16 such entries (each with its own `pin`), independent of each other.

----------------------------------------------------------------------------------------------
CRITICAL: signal inversion. Get this wrong and every valve using it flips to the wrong path -
in an electrosynthesis setup that can mean routing reagent/product into the wrong line.

VERIFIED (from a colleague's working code against this specific relay board model):

    from gpiozero import DigitalOutputDevice
    from time import sleep
    relais = DigitalOutputDevice(17)
    relais.off()   # Signal invertiert auf dem Relais-Board: off = Strom fliesst
    sleep(5)
    relais.on()    # zurueck in den Grundzustand

i.e. on THIS board, .off() energizes the relay (current flows) and .on() is the de-energized rest
state - the OPPOSITE of what the names "on"/"off" suggest. This driver exposes that as the
`inverted` config.yml flag and maps it onto gpiozero's own `active_high` parameter
(active_high = not inverted; verified against gpiozero 2.0.1 - see
backend/drivers/relay_3_2_valve_base.py:build_output_pin). A DIFFERENT relay board may switch the
"normal" way around - set `inverted: false` for that board. There is no safe default here: check
`inverted` against the physical board before running anything.

ASSUMPTION (not verified against the physical valve - confirm on the real Raspberry Pi setup
before relying on this for an actual experiment):
    - Position "B" is defined as the ENERGIZED relay state, "A" as DE-ENERGIZED/rest. This is a
      labeling convention chosen in this driver, matching a spring-return 3/2-way valve where "A"
      is the path taken with no power applied at all (so a power loss fails to "A").
    - GPIO pin numbers in config.yml are BCM numbers (gpiozero's default numbering scheme), not
      physical header pin numbers.
    - ~0.2s (`command_execution_time` below) covers real solenoid actuation time; override per
      device via config.yml's generic `command_parameters: {command_execution_time: ...}` if the
      real valve needs longer before the next command may run.
----------------------------------------------------------------------------------------------

No communication, no protocol, no feedback: this driver only ever sets a GPIO pin high or low in
this same process. It cannot read the real valve position back - `current_position`/the "position"
observable reflect only what this driver itself last commanded (see
backend/drivers/relay_3_2_valve_base.py:NoWireProtocol for how that's wired into the normal
AbstractBaseDevice command machinery so valve moves still sequence correctly with other commands).

Development without a Raspberry Pi (e.g. on Windows): set `simulate: true` on a device in
config.yml to use gpiozero's Mock pin factory instead of real GPIO hardware - see config.yml for
an example. Leave it unset/false for a real deployment; a real GPIO failure will then raise loudly
(gpiozero.exc.BadPinFactory) instead of silently pretending to switch a valve.
"""
from .relay_3_2_valve_base import (BaseDevice, SinglechannelBaseDevice, CommandParameterFactory, parser,
                                    normalize_position, build_output_pin, NoWireProtocol)
import re


class Device(SinglechannelBaseDevice, BaseDevice):
    replies_commands = False
    log_name = "Raspi GPIO Relay Valve"
    # ASSUMPTION: see module docstring - adjust via config.yml's `command_parameters:` if needed.
    command_parameter_factory = CommandParameterFactory(command_execution_time=.2)
    parser_parameter_factory = parser.ParserParameterFactory(parserclass=parser.SuccessParser)
    delimiter = "\n"

    commands = {
        "SET_A": ["SET_A"],
        "SET_B": ["SET_B"],
    }

    def __init__(self, address, *args, pin: int, inverted: bool, safe_state: str, simulate: bool = False, **kwargs):
        """
        :param pin: BCM GPIO pin number this valve's relay is wired to. Required, no default -
            get this wrong and you switch the wrong valve.
        :param inverted: CRITICAL, no default - True if .off() energizes the relay on this board
            (see module docstring), False for a normal (non-inverted) board.
        :param safe_state: "A" or "B" - the position driven immediately on startup and on every
            stop()/shutdown(). No default: which position is actually safe is specific to how this
            valve is plumbed into the setup and must be chosen deliberately.
        :param simulate: True to use gpiozero's Mock pin factory (development without a Raspberry
            Pi) instead of real GPIO hardware. Defaults to False (real hardware).
        """
        super().__init__(address, *args, **kwargs)
        self.pin_number = int(pin)
        self.inverted = bool(inverted)
        self.safe_state = normalize_position(safe_state)
        self.simulate = bool(simulate)
        self._pin = None
        self.current_position = None

    def get_connection_method(self):
        # There is no TCP/serial connection to detect from `address` - see module docstring.
        # Overriding this is what bypasses AbstractBaseDevice's IP-or-COMx address check entirely.
        return self._gpio_connect

    def _gpio_connect(self):
        self._pin = build_output_pin(self.pin_number, inverted=self.inverted,
                                      initial_position=self.safe_state, simulate=self.simulate)
        self.log.info(
            "GPIO pin {pin} claimed (inverted={inverted}, simulate={simulate}), "
            "driven to safe state {safe_state!r}.",
            pin=self.pin_number, inverted=self.inverted, simulate=self.simulate,
            safe_state=self.safe_state,
        )
        return self.connection_done(NoWireProtocol(self))

    def shutdown(self):
        return super().shutdown().addBoth(self._release_pin)

    def _release_pin(self, result):
        if self._pin is not None:
            try:
                self._pin.close()
            except Exception:
                self.log.warn("Failed to cleanly release GPIO pin {pin}.", pin=self.pin_number)
            self._pin = None
        return result

    def cmd_string(self, command_parameters: CommandParameterFactory) -> str:
        return command_parameters.commandstring

    def initial_commands(self):
        self.set_position(self.safe_state)

    def final_commands(self):
        self.set_position(self.safe_state)

    def handle_event(self, match: re.Match) -> None:
        pass

    def drive_pin(self, commandstring: str) -> None:
        """
        The only actual hardware action this driver performs. Called by
        NoWireProtocol.write_command in place of writing bytes to a wire.
        :param commandstring: "SET_A" or "SET_B" (see `commands` above).
        """
        position = commandstring.split("_", 1)[1]
        energize = (position == "B")  # ASSUMPTION: see module docstring.
        if energize:
            self._pin.on()
        else:
            self._pin.off()
        self.current_position = position
        self.update_observables({"position": position})
        self.log.info(
            "GPIO pin {pin} set for position {position} ({state}).",
            pin=self.pin_number, position=position, state="energized" if energize else "de-energized",
        )

    def set_position(self, position: str, **kwargs):
        position = normalize_position(position)
        return self.write(f"SET_{position}", **kwargs)
