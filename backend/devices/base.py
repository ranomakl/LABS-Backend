# -*- test-case-name: backend.test.test_base -*-

from abc import ABC, abstractmethod
import re
import time
from typing import Optional

from twisted.logger import Logger
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import ClientFactory, connectionDone
from twisted.internet.serialport import SerialPort
from twisted.internet import defer, reactor, error
from twisted.internet.abstract import isIPAddress
from twisted.python import failure

from backend.commands import (commandstate, parser, ABDeviceCommand, IProtocolCommand, Command, CommandSeries,
                              RepeatedCommand, WaitCommand, CommandErrorError, CommandParameterFactory)
from backend.commands.results import Result
from backend.devices import devicestate
from backend.conditions.conditionhandler import ConditionHandler
from .helpers_exceptions import UnknownConnectionTypeError
from backend.helpers_exceptions import IObservable, BaseObservable, StateMachineMixIn


class ICommander(IObservable):
    @abstractmethod
    def write(self, command_name: str, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def query(self, command_name: str, **kwargs):
        raise NotImplementedError


class ICommunicator(ABC):
    @abstractmethod
    def connect(self) -> defer.Deferred:
        raise NotImplementedError

    @abstractmethod
    def receive(self, line: str) -> None:
        raise NotImplementedError


class IStateDevice(ABC):
    """work with backend.devices.states.devicestate and provide a list called cmd_queue"""
    @property
    @abstractmethod
    def state(self):
        raise NotImplementedError

    @abstractmethod
    def send_cmd(self, cmd: ABDeviceCommand):
        raise NotImplementedError

    @abstractmethod
    def execute_cmd(self, cmd: ABDeviceCommand):
        raise NotImplementedError


class StateDeviceMixIn(StateMachineMixIn, IStateDevice, ABC):
    def __init__(self, *args, initial_stateclass=devicestate.NotReady, **kwargs):
        super().__init__(*args, initial_stateclass=initial_stateclass, **kwargs)


class BaseDeviceProtocol(LineReceiver):
    def __init__(self):
        self.non_delimited_replies = []  # treated as a reply anyways
        self.device = None

    def connectionMade(self):
        self.device = self.factory.device
        self.delimiter = self.device.delimiter.encode()
        self.non_delimited_replies = tuple(key.encode() for key in self.device.reply_to_state.keys())
        self.factory.d_protocol.callback(self)

    def dataReceived(self, data):
        super().dataReceived(data)
        for reply in self.non_delimited_replies:
            if reply in self._buffer:
                self._buffer = self._buffer.replace(reply, b"")
                self.lineReceived(reply)

    def rawDataReceived(self, data):
        raise NotImplementedError

    def lineReceived(self, line):
        result = Result(line.decode())
        self.device.receive(result)

    def write_command(self, command_object: IProtocolCommand):
        self.sendLine(command_object.bytestring)
        self.device.log.info(f"Wrote {command_object.parameters.commandstring} to device.")

    def lose_connection(self):
        if not isinstance(self.transport, SerialPort):
            self.transport.loseConnection()

    def connectionLost(self, reason: failure.Failure = connectionDone):
        self.device.protocol = None
        # 12.10.2026: Bei SERIELLEN Geraeten ist das der einzige Hinweis auf einen Verbindungsabbruch
        # (USB-Adapter weg, Twisted meldet ConnectionDone/ConnectionLost); clientConnectionLost der
        # Factory gibt es nur fuer TCP. Vorher wurde hier nur protocol=None gesetzt: das Geraet blieb
        # Busy, das Experiment lief weiter, die Messung starb leise, ein Netzteil blieb an.
        self.device.connection_lost(reason)
        return reason


class BaseDeviceProtocolFactory(ClientFactory):
    protocol = BaseDeviceProtocol
    noisy = False

    def __init__(self, device):
        self.log = device.log
        self.d_protocol = defer.Deferred()
        self.device = device

    def clientConnectionFailed(self, connector, reason):
        self.log.error("Failed connecting to {address}: {reason}", address=connector.getDestination(), reason=reason)
        self.d_protocol.errback(reason)

    def clientConnectionLost(self, connector, reason: failure.Failure):
        r = reason.trap(error.ConnectionDone)
        if not r == error.ConnectionDone:
            self.log.error("Lost connection to {address}: {reason}", address=connector.getDestination(), reason=reason)
        self.device.connection_lost(reason)


class DeviceAndChannelBase(StateDeviceMixIn, BaseObservable, ABC):
    def __init__(self, *args, **kwargs):
        self.active_repeated_commands = {}
        super().__init__(*args, **kwargs)

    @abstractmethod
    def write(self, command_name: str, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def query(self, command_name: str, **kwargs):
        raise NotImplementedError

    # @StateMachineMixIn.stateobject.setter
    # def stateobject(self, state):
    #     StateMachineMixIn.stateobject.fset(self, state)
    #     self.update_observables({"state": str(state)})

    def reuse_state_without_enter(self, state):
        self._state = state
        self.log.info(f"Set state back to {state}")

    @property
    def commandseries(self):
        return self.get_commandseries()

    def get_commandseries(self, *args, **kwargs):
        return CommandSeries(self, *args, **kwargs)

    def send_cmd(self, cmd: ABDeviceCommand):
        self.stateobject.add_command_callbacks(cmd)
        self.stateobject.send_cmd(cmd)

    def __repr__(self):
        return f"{self.__class__.__name__}"

    def wait(self, condition, *args, **kwargs):
        command = WaitCommand(self, condition, *args, **kwargs)
        self.send_cmd(command)
        return command

    def busy(self, condition, *args, **kwargs):
        return self.wait(condition, *args, devicestate_while_executing=devicestate.Busy, **kwargs)

    def _repeated_commands(self, write_function, command_name, *args, **kwargs):
        cmd = RepeatedCommand(self, write_function, command_name, *args, run_while_device_busy=True, **kwargs)

        def remove_cmd(result, cmd_name):
            self.active_repeated_commands.pop(cmd_name)
            return result

        def add_cmd(result, cmd_name):
            try:
                self.active_repeated_commands[cmd_name].deferred_stop.callback(None)
            except KeyError:
                pass
            self.active_repeated_commands[cmd_name] = cmd
            return result

        cmd.deferred_result.addCallback(add_cmd, command_name)
        cmd.deferred_stop.addBoth(remove_cmd, command_name)
        self.send_cmd(cmd)
        return cmd

    def repeated_write(self, *args, **kwargs):
        return self._repeated_commands(self.write, *args, **kwargs)

    def repeated_query(self, *args, **kwargs):
        return self._repeated_commands(self.query, *args, **kwargs)

    def stop_repeated_commands(self):
        stop_deferreds = [command.deferred_stop for command in self.active_repeated_commands.values()]
        for deferred in stop_deferreds:
            deferred.callback(None)


class AbstractBaseDevice(ICommander, ICommunicator, DeviceAndChannelBase):
    protocol_factory_class = BaseDeviceProtocolFactory
    callLater = reactor.callLater
    RECONNECT_INTERVAL = 2.0   # s zwischen zwei Wiederverbindungsversuchen nach connection_lost()
    reply_to_state = {}
    event_patterns = []
    error_patterns = []
    replies_commands = False
    serial_parameters = {}
    delimiter = "\r"
    log_name = "BaseDevice"

    commands = {}
    command_parameter_factory = CommandParameterFactory()
    parser_parameter_factory = parser.ParserParameterFactory()

    def __init_subclass__(cls, **kwargs):
        """Compiles all regular expressions and makes all parameter_objects in the commands of a subclass on its
        initialization."""
        for command in cls.commands.values():
            if isinstance(command[0], str):
                command[0] = cls.command_parameter_factory(commandstring=command[0])
            try:
                parser_info = command[1]
            except IndexError:
                command.append(cls.parser_parameter_factory())
            else:
                if isinstance(parser_info, str):
                    command[1] = cls.parser_parameter_factory(parserclass=parser.REParser,
                                                              pattern=re.compile(parser_info))
                elif parser_info.parserclass == parser.REParser:
                    parser_info.kwargs["pattern"] = re.compile(parser_info.kwargs["pattern"])

    def __init__(self, address, *args, conditionhandler: ConditionHandler = ConditionHandler(), command_parameters: dict = None, parser_parameters: dict = None, serial_parameters: dict = None, **kwargs):
        self.conditionhandler = conditionhandler
        self.full_address = address
        self.log_name = f"{self.log_name} on {self.full_address}"
        self.log = Logger(namespace=self.log_name)
        super().__init__(*args, initial_stateclass=devicestate.NotReady, **kwargs)
        self.address, self.port = self.get_address()
        self.connection_method = self.get_connection_method()
        self.protocol_factory = self.protocol_factory_class(self)
        self.protocol = None
        self._reconnect_call = None      # IDelayedCall des naechsten Wiederverbindungsversuchs
        self._reconnect_attempts = 0
        self.cmd_queue: list[ABDeviceCommand] = []
        self.current_command: Optional[ABDeviceCommand] = None

        command_parameters = command_parameters if command_parameters is not None else {}
        parser_parameters = parser_parameters if parser_parameters is not None else {}
        self.command_parameter_factory = self.command_parameter_factory(**command_parameters)
        self.parser_parameter_factory = self.parser_parameter_factory(**parser_parameters)
        # config.yml may override single keys of the driver's serial_parameters class attribute
        # (e.g. baudrate) without having to repeat the whole dict.
        self.serial_parameters = {**self.serial_parameters, **(serial_parameters or {})}

    def connect(self) -> defer.Deferred:
        return self.connection_method()

    def get_address(self):
        address, port = self.full_address, None
        # POSIX-Geraetepfade nicht zerlegen: /dev/serial/by-path/...usb-0:2.2.2:1.0-port0 enthaelt
        # Doppelpunkte, ist aber keine IP:Port-Adresse.
        if ":" in self.full_address and not self.full_address.startswith("/"):
            address, port = self.full_address.split(":", 1)
            port = int(port)
        return address, port

    def get_connection_method(self):
        if isIPAddress(self.address):
            return self._tcp
        elif re.match("COM[0-9]{1,3}", self.address.upper()):
            return self._serial
        elif self.address.startswith("/"):  # POSIX device path, e.g. /dev/ttyUSB0 or /dev/serial/by-id/...
            return self._serial
        else:
            raise UnknownConnectionTypeError(f"Could not recognize address: {self.full_address}")

    def stop(self):
        self.cmd_queue = []
        # self.state = devicestate.Ready
        with self.get_commandseries(command_parameter = self.command_parameter_factory(urgent = True, shutdown_path = True, next_devicestate = devicestate.Stopped)) as series:
            self.final_commands()
        self.stop_repeated_commands()
        return series.deferred_result

    def shutdown(self):
        return self.stop().addBoth(self.set_state, devicestate.Shutdown)

    def connection_done(self, protocol) -> defer.Deferred:
        self.log.info(f"Connected to {self.full_address}.")
        self.protocol = protocol
        self.state = devicestate.Initializing
        with self.commandseries as series:
            self.initial_commands()
        return series.deferred_result.addCallback(lambda _: protocol)

    def _new_protocol_deferred(self) -> defer.Deferred:
        # Beim ersten Verbinden ist d_protocol frisch; bei einer Wiederverbindung wurde es schon gefeuert
        # und braucht einen Nachfolger (connectionMade/clientConnectionFailed feuern immer factory.d_protocol).
        if self.protocol_factory.d_protocol.called:
            self.protocol_factory.d_protocol = defer.Deferred()
        return self.protocol_factory.d_protocol

    def _serial(self) -> defer.Deferred:
        d_protocol = self._new_protocol_deferred().addCallback(self.connection_done)
        protocol = self.protocol_factory.buildProtocol(self.address)
        protocol.factory = self.protocol_factory
        SerialPort(protocol, self.address, reactor, **self.serial_parameters)   # ruft connectionMade sofort
        return d_protocol

    def _tcp(self) -> defer.Deferred:
        d_protocol = self._new_protocol_deferred().addCallback(self.connection_done)
        reactor.connectTCP(self.address, self.port, self.protocol_factory)
        return d_protocol

    def connection_lost(self, reason):
        """Verbindung zum Geraet ist weg (seriell: BaseDeviceProtocol.connectionLost; TCP: zusaetzlich
        BaseDeviceProtocolFactory.clientConnectionLost - deshalb idempotent).

        12.10.2026: Vorher wurde das Geraet still auf Shutdown gesetzt, das Experiment lief weiter und
        hat davon nie erfahren (Experiment.update reagierte nur auf "Error"). Jetzt:
          1. Zustand Error -> ein laufendes Experiment geht nach Failed und stoppt die UEBRIGEN Geraete.
          2. Wiederverbindung alle RECONNECT_INTERVAL s (seriell: sobald die Geraetedatei wieder da ist).
             Nach der Wiederverbindung laeuft connection_done() -> initial_commands(), und die schalten
             bei Netzteil/MFC/Pumpe den sicheren Zustand (Ausgang aus, Ventil auf, Pumpe stopp).
        Ein absichtlich beendetes Geraet (Shutdown) wird nicht wiederverbunden."""
        if self.state == devicestate.Shutdown:
            return
        if self._reconnect_call is not None and self._reconnect_call.active():
            return   # schon gemeldet (TCP meldet den Verlust doppelt)
        message = reason.getErrorMessage() if hasattr(reason, "getErrorMessage") else str(reason)
        self.log.error("CONNECTION LOST to {address}: {reason} - device -> Error, reconnecting every {t} s",
                       address=self.full_address, reason=message, t=self.RECONNECT_INTERVAL)
        self.update_observables({"errorcode": f"connection lost: {message}"})   # String, kein Failure (values.json!)
        self.state = devicestate.Error
        self._reconnect_attempts = 0
        self._schedule_reconnect()

    def _schedule_reconnect(self):
        if self._reconnect_call is not None and self._reconnect_call.active():
            return
        self._reconnect_call = self.callLater(self.RECONNECT_INTERVAL, self._reconnect)

    def _reconnect(self):
        self._reconnect_call = None
        if self.state == devicestate.Shutdown:
            return
        self._reconnect_attempts += 1
        log = self.log.info if self._reconnect_attempts in (1, 5) or self._reconnect_attempts % 30 == 0 else self.log.debug
        log("Reconnect attempt {n} to {address}", n=self._reconnect_attempts, address=self.full_address)
        try:
            deferred = self.connect()
        except Exception as error:  # noqa: BLE001 - z.B. serial.SerialException: Geraetedatei (noch) nicht da
            log("Reconnect attempt {n} failed: {error}", n=self._reconnect_attempts, error=error)
            self._schedule_reconnect()
            return

        def failed(failure):
            log("Reconnect attempt {n} failed: {error}", n=self._reconnect_attempts, error=failure.getErrorMessage())
            self._schedule_reconnect()

        def connected(result):
            self.log.info("RECONNECTED to {address} after {n} attempt(s); initial_commands set the safe state.",
                          address=self.full_address, n=self._reconnect_attempts)
            return result
        deferred.addCallbacks(connected, failed)

    @abstractmethod
    def initial_commands(self):
        pass

    @abstractmethod
    def final_commands(self):
        pass

    def write(self, command_name: str, **kwargs):
        """
        This is used to send a command_name to the device.
        :param query: is this a query or not?
        :param command_name: human readable command_name
        :return: Deferred that fires when a temp_result for the command_name was obtained.
        """
        cmd = self.get_cmd(command_name, **kwargs)
        self.send_cmd(cmd)
        return cmd

    def query(self, command_name: str, **kwargs):
        return self.write(command_name, query=True, **kwargs)

    @abstractmethod
    def cmd_string(self, command_parameters: CommandParameterFactory) -> str:
        """
        This is called to get a formatted commandstring.
        :param command_parameters: CommandParameterFactory object to provide parameters, e.g. command_parameters.query
        and command_parameters.commandstring.
        :return: fully formatted commandstring including values
        """
        raise NotImplementedError

    def get_cmd(self, command_name: str, **kwargs):
        raw_cmd = self.commands[command_name]

        command_parameter = raw_cmd[0](**kwargs)
        parser_parameter = raw_cmd[1](**kwargs)

        commandstring = self.cmd_string(command_parameter)
        command_parameter = command_parameter(commandstring=commandstring)
        cmd = Command(self, command_parameter, parser_parameter)
        if isinstance(cmd.parser, parser.SuccessParser) and not self.replies_commands:
            def receive_dummy_result(result):
                self.callLater(cmd.parameters.command_execution_time + cmd.parameters.inter_command_time,
                               self.receive, Result(f"NO RESULT for {cmd}"))
                return result
            cmd.parameters.timeout += cmd.parameters.command_execution_time + cmd.parameters.inter_command_time
            cmd.deferred_execution.addCallback(receive_dummy_result)
        return cmd

    @abstractmethod
    def handle_event(self, match: re.Match) -> None:
        raise NotImplementedError

    def _was_event(self, reply: Result) -> bool:
        is_event = False
        for pattern in self.event_patterns:
            for match in re.finditer(pattern, reply.line):
                is_event = True
                self.handle_event(match)
                self.update_observables(match.groupdict(), reply.time)
        return is_event

    def _was_error(self, reply: Result) -> bool:
        is_error = False
        for pattern in self.error_patterns:
            match = re.match(pattern, reply.line)
            if match:
                is_error = True
                self.current_command.temp_result = CommandErrorError(reply, match=match)
                self.current_command.state = commandstate.Retry
        return is_error

    def receive(self, reply: Result) -> None:
        """
        Receive a reply from the protocol, check if it was an eventstring or error, if not try to parse the result
        :param reply:
        :return: current_command, so that the protocol can read its state
        """
        self.log.info(f"Received {reply}")
        if not self._was_event(reply) and not self._was_error(reply):
            # get the state from parser, if commandstate.Fail is returned, no retries will be done.
            self.current_command.temp_result, self.current_command.state = self.current_command.parser(reply)
            self.current_command.device.update_observables(reply.parameters, reply.time)

    def execute_cmd(self, cmd: ABDeviceCommand):
        self.current_command = cmd
        cmd.execute()


class SinglechannelBaseDevice(AbstractBaseDevice, ABC):
    pass


class MultichannelBaseDevice(AbstractBaseDevice, ABC):
    def __init__(self, address, *args, **kwargs):
        super().__init__(address, *args, **kwargs)
        self.channelcount = 0
        self.channels = {}
        self.channel_acting = None

    @abstractmethod
    def _get_channels(self) -> defer.Deferred:
        raise NotImplementedError

    def update_observables(self, observables: dict, timestamp: float = time.time()):
        if "channel" in observables.keys():
            self.channels[int(observables.pop("channel"))].update_observables(observables, timestamp)
        else:
            super().update_observables(observables, timestamp)

    def initial_commands(self):
        super().initial_commands()

        def _set_channels(result):
            self.channelcount = int(result.parameters["channelcount"])  # channelcount must be in RE Parser
            for channel in range(1, self.channelcount + 1):
                self.channels[channel] = ChannelProxy(channel, self)
            self.log.info("ChannelProxys created.")
            return result
        self._get_channels().deferred_result.addCallback(_set_channels)

    def write(self, command_name: str, channel=None, **kwargs):
        if channel is None:
            channel = self.channelcount
        try:
            channelproxy = self.channels[channel]
        except KeyError:
            return super().write(command_name, channel=channel, **kwargs)
        else:
            return channelproxy.write(command_name, channel=channel, **kwargs)

    def wait(self, condition, *args, channel=None, **kwargs):
        if channel is None:
            channel = self.channelcount
        try:
            channelproxy = self.channels[channel]
        except KeyError:
            return super().wait(condition, *args, **kwargs)
        else:
            return channelproxy.wait(condition, *args, **kwargs)

    def stop(self):
        if self.channel_acting is None:
            deferreds = []
            self.cmd_queue = []
            for channel in self.channels.values():
                if not channel.state == devicestate.Stopped:
                    deferreds.append(channel.stop())
            return defer.DeferredList(deferreds).addCallback(self.set_state, devicestate.Stopped)
        else:
            with self.get_commandseries(command_parameter = self.command_parameter_factory(urgent = True, shutdown_path = True)) as series:
                self.final_commands()
            self.stop_repeated_commands()
            return series.deferred_result.addCallback(self.channel_acting.set_state, devicestate.Stopped)


class ChannelProxy(ICommander, DeviceAndChannelBase):
    def __init__(self, channel: int, device: MultichannelBaseDevice, *args, **kwargs):
        self.channel = channel
        self.device = device
        self.log_name = f"{self.device.log_name} channel {self.channel} on {self.device.full_address}"
        self.log = Logger(namespace=self.log_name)
        super().__init__(*args, initial_stateclass=devicestate.Ready, **kwargs)
        self.original_device_write = self.device.write
        self.original_device_wait = self.device.wait
        self.original_device_get_commandseries = self.device.get_commandseries
        self.cmd_queue = []
        self.current_command: Optional[ABDeviceCommand] = None

    def _temp_write_commandseries_change(self, function):
        def wrapper(*args, **kwargs):
            self.device.write = self.write
            self.device.wait = self.wait
            self.device.get_commandseries = self.get_commandseries
            self.device.channel_acting = self
            return_value = function(*args, **kwargs)
            self.device.channel_acting = None
            self.device.write = self.original_device_write
            self.device.wait = self.original_device_wait
            self.device.get_commandseries = self.original_device_get_commandseries
            return return_value
        return wrapper

    def write(self, command_name: str, channel=None, **kwargs):
        """
        This is used to send a command_name to the device.
        :param channel: In case a command should not be sent with self.channel
        :param command_name: human readable command_name
        :return: Deferred that fires when a temp_result for the command_name was obtained.
        """
        if channel is None:
            channel = self.channel
        cmd = self.device.get_cmd(command_name, channel=channel, **kwargs)
        cmd.device = self
        self.send_cmd(cmd)
        return cmd

    def wait(self, condition, *args, **kwargs):
        condition.observable_objects.append(self)
        command = super().wait(condition, *args, **kwargs)
        return command

    def stop(self):
        self.cmd_queue = []
        return self._temp_write_commandseries_change(self.device.stop)()

    def query(self, command_name: str, **kwargs):
        return self.write(command_name, query=True, **kwargs)

    def execute_cmd(self, cmd: ABDeviceCommand):
        self.current_command = cmd
        if isinstance(cmd, WaitCommand):
            cmd.execute()
        else:
            self.device.send_cmd(cmd)

    def __getattr__(self, item):
        if item in MultichannelBaseDevice.__dict__:
            raise AttributeError(f"{self.__class__.__name__} object has no attribute {item}")
        attribute = self.device.__getattribute__(item)
        if callable(attribute):
            return self._temp_write_commandseries_change(attribute)
        else:
            return attribute
