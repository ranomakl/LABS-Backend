from __future__ import annotations
from multiprocessing.connection import wait
from typing import TYPE_CHECKING

from twisted.internet import reactor, defer, task

from abc import ABC
from .helpers_exceptions import DeviceShutdownError, DeviceErrorError
from backend.helpers_exceptions import IState


if TYPE_CHECKING:
    from backend.commands import ABDeviceCommand


class DeviceState(IState, ABC):
    callLater = reactor.callLater   # Klassenattribut, damit Tests eine task.Clock einsetzen koennen

    def __init__(self, device, *args, **kwargs):
        self.device = device

    def send_cmd(self, cmd: ABDeviceCommand):
        if cmd.parameters.urgent:
            pos = 0
            for queued_cmd in self.device.cmd_queue:
                if queued_cmd.parameters.urgent:
                    pos += 1
                else:
                    break
            self.device.cmd_queue.insert(pos, cmd)
        else:
            self.device.cmd_queue.append(cmd)

    def handle_success(self, result):
        cmd = result.command
        return task.deferLater(reactor, cmd.parameters.inter_command_time, self.device.set_state, result,
                                cmd.parameters.next_devicestate).addCallback(lambda _: result)

    def handle_fail(self, failure):
        cmd = failure.value.command
        cmd.device.state = Error
        # 12.10.2026: War der gescheiterte Befehl ein DRINGENDER (Abschaltpfad: device.stop()/shutdown()),
        # darf es nicht bei diesem einen Versuch bleiben - der Error-Zustand wiederholt stop(), bis das
        # Geraet bestaetigt. (Error.handle_fail macht dasselbe fuer Befehle, die IM Error-Zustand scheitern.)
        state = cmd.device.stateobject
        if cmd.parameters.shutdown_path and isinstance(state, Error):
            state.schedule_stop_retry()
        return failure

    def add_command_callbacks(self, cmd):
        def success(result):
            return self.device.stateobject.handle_success(result)
        def fail(result):
            return self.device.stateobject.handle_fail(result)
        cmd.deferred_result.addCallbacks(success, fail)

    def new_state(self, state, *args, **kwargs):
        """
        Setting states is delegated to the current state, so that in Shutdown- or Errorstate it can be ignored.
        :param *args:
        :param **kwargs:
        :param state:
        :return:
        """
        self.device.stateobject = state


class NotReady(DeviceState):
    def enter(self):
        pass


class CollectingCommands(DeviceState):
    def __init__(self, device):
        super().__init__(device)
        self.commandseries = None  # set by CommandSeries

    def enter(self):
        pass

    def send_cmd(self, cmd: ABDeviceCommand):
        if cmd.parameters.urgent:
            self.commandseries.parameters.urgent = True
        self.commandseries.commandlist.append(cmd)

    def add_command_callbacks(self, cmd):
        pass


class Ready(DeviceState):
    def enter(self):
        try:
            cmd = self.device.cmd_queue.pop(0)
        except IndexError:
            pass
        else:
            self.send_cmd(cmd)

    def send_cmd(self, cmd: ABDeviceCommand):
        self.device.execute_cmd(cmd)
        self.device.state = cmd.parameters.devicestate_while_executing


class Initializing(Ready):
    def enter(self): pass


class Error(DeviceState):
    """Geraet hat einen Befehl endgueltig nicht beantwortet/fehlerhaft beantwortet, oder die Verbindung
    ist weg (base.AbstractBaseDevice.connection_lost).

    08.10.2026 (Versuch 26174): Das Netzteil blieb nach EINEM unbeantworteten Lesebefehl in diesem
    Zustand haengen und verweigerte auch den Ausschaltbefehl - der Ausgang blieb an, waehrend Pumpe
    und Zaehler laengst gestoppt waren. Deshalb:
      - DRINGENDE Befehle (urgent=True, das sind die final_commands aus device.stop()/shutdown(),
        also Netzteil aus, Pumpe Stopp, Ventil auf) werden auch im Error-Zustand gesendet.
      - Der Wechsel nach Stopped/Shutdown/NotReady ist erlaubt (Abschluss von stop()/shutdown()).
    12.10.2026 (Review, docs/fehlerpfad_nachbesserung_12-10-2026.md):
      - Wird ein dringender Befehl NICHT bestaetigt (Timeout nach allen Retries, keine Verbindung),
        wird device.stop() alle RETRY_INTERVAL Sekunden wiederholt - solange, bis das Geraet bestaetigt
        (-> Stopped) oder das Geraet Shutdown/Wiederverbindung erreicht. Vorher: 4 Versuche in 10 s,
        dann nie wieder.
      - Dringende Befehle werden der Reihe nach gesendet (nie zwei gleichzeitig auf der Leitung).
      - Ohne Verbindung (protocol is None) scheitert ein dringender Befehl sofort und sauber; das
        Abschalten uebernimmt dann connection_done()/initial_commands() nach der Wiederverbindung,
        zusaetzlich laeuft die stop()-Wiederholung weiter.
      - Initializing ist erlaubt: einziger Weg dorthin ist connection_done() nach Wiederverbindung.
    Alles andere bleibt ignoriert, das Geraet gilt bis zum Neustart/Wiederverbindung als defekt."""
    RETRY_INTERVAL = 5.0   # s zwischen zwei Wiederholungen von device.stop() nach unbestaetigtem Abschalten

    def __init__(self, device, *args, **kwargs):
        super().__init__(device, *args, **kwargs)
        self._retry_call = None     # IDelayedCall der naechsten stop()-Wiederholung
        self._in_flight = False     # laeuft gerade ein dringender Befehl auf der Leitung?

    def enter(self):
        self.device.cmd_queue = []

    def send_cmd(self, cmd: ABDeviceCommand):
        if not cmd.parameters.urgent:
            error = DeviceErrorError("Cannot send commands in Error state!")
            self.device.log.error(f"{str(error)}")
            raise error
        if getattr(self.device, "protocol", None) is None:
            error = DeviceErrorError(f"NO CONNECTION, cannot send urgent command {cmd}")
            error.command = cmd
            self.device.log.error("{error}", error=error)
            cmd.deferred_result.errback(error)    # -> handle_fail -> stop()-Wiederholung
            return
        if self._in_flight:
            # Nie zwei Befehle gleichzeitig auf die Leitung: device.current_command wuerde ueberschrieben
            # und die Antwort dem falschen Befehl zugeordnet. handle_success/handle_fail senden den naechsten.
            self.device.cmd_queue.append(cmd)
            return
        self._execute(cmd)

    def _execute(self, cmd: ABDeviceCommand):
        self.device.log.warn("Error state: sending URGENT command anyway (shutdown path): {cmd}", cmd=cmd)
        self._in_flight = True
        self.device.execute_cmd(cmd)

    def _send_next(self):
        self._in_flight = False
        if self.device.cmd_queue:
            self._execute(self.device.cmd_queue.pop(0))

    def handle_success(self, result):
        self._send_next()
        return super().handle_success(result)

    def handle_fail(self, failure):
        self._send_next()                      # wartet schon ein weiterer dringender Befehl, geht der jetzt raus
        cmd = getattr(failure.value, "command", None)
        if cmd is not None and cmd.parameters.shutdown_path:
            if self._in_flight:
                self.device.log.error("Error state: shutdown command {cmd} NOT confirmed ({err}) - next one is "
                                      "already on its way", cmd=cmd, err=failure.getErrorMessage())
            else:
                self.device.log.error("Error state: shutdown command {cmd} NOT confirmed ({err}) - repeating "
                                      "device.stop() in {t} s", cmd=cmd, err=failure.getErrorMessage(),
                                      t=self.RETRY_INTERVAL)
                self.schedule_stop_retry()
        return failure

    def schedule_stop_retry(self):
        if self._retry_call is not None and self._retry_call.active():
            return
        self._retry_call = self.callLater(self.RETRY_INTERVAL, self._retry_stop)

    def _cancel_stop_retry(self):
        if self._retry_call is not None and self._retry_call.active():
            self._retry_call.cancel()
        self._retry_call = None

    def _retry_stop(self):
        self._retry_call = None
        if self.device.stateobject is not self:
            return
        self.device.log.warn("Error state: repeating device.stop() (final commands) until the device confirms")
        try:
            # Fehler sind in handle_fail protokolliert und loesen die naechste Wiederholung aus;
            # der Errback hier verhindert nur "Unhandled error in Deferred".
            self.device.stop().addErrback(lambda _: None)
        except Exception as error:  # noqa: BLE001 - Wiederholung darf an nichts scheitern
            self.device.log.error("Error state: device.stop() raised {error}", error=error)
            self.schedule_stop_retry()

    def new_state(self, state, *args, **kwargs):
        # CollectingCommands: device.stop()/shutdown() sammeln die final_commands in einer CommandSeries
        # (with-Block). Ohne diesen Wechsel landet jeder einzelne Abschaltbefehl direkt hier in send_cmd,
        # ist dort noch nicht als urgent markiert und wird abgewiesen - die Serie geht dann LEER raus
        # (Dummy-Test 08.10.2026: "sending URGENT command anyway: CommandSeries []").
        if isinstance(state, CollectingCommands):
            super().new_state(state, *args, **kwargs)
        elif isinstance(state, (Stopped, Shutdown, NotReady, Initializing)):
            self._cancel_stop_retry()
            super().new_state(state, *args, **kwargs)


class Stopped(DeviceState):
    def enter(self):
        self.device.cmd_queue = []

    def send_cmd(self, cmd: ABDeviceCommand):
        self.device.log.error("Device stopped, cannot send Commands in this state.")


class Shutdown(DeviceState):
    def enter(self):
        try:
            self.device.protocol.lose_connection()
        except AttributeError:  # in case the connection was lost and the state is set by this event
            pass

    def send_cmd(self, cmd: ABDeviceCommand):
        error = DeviceShutdownError("Cannot send commands in Shutdown state!")
        self.device.log.error(f"{str(error)}")
        raise error

    def new_state(self, state, *args, **kwargs):
        pass


class Busy(DeviceState):
    def __init__(self, device, condition, waitcommand, *args, **kwargs):
        super().__init__(device, *args, **kwargs)
        self.condition = condition
        self._ready_for_urgent_command = False
        self.waitcommand = waitcommand
        self._accept_state = False
        self._defer_result = None

    def _run_next_urgent_cmd(self):
        try:
            parameters = self.device.cmd_queue[0].parameters
            if (parameters.urgent or parameters.run_while_device_busy) and self._ready_for_urgent_command:
                cmd = self.device.cmd_queue.pop(0)
                self._ready_for_urgent_command = False
                self.device.execute_cmd(cmd)
        except IndexError:
            pass

    def _ready(self):
        try:
            self._defer_result.callback(None)
        except AttributeError:
            self._ready_for_urgent_command = True
            self._run_next_urgent_cmd()

    def handle_success(self, result):
        cmd = result.command
        if cmd == self.waitcommand:
            if self._ready_for_urgent_command:  # meaning we are not waiting for a commands reply, if we are, we have to wait until it's success is handled
                self._accept_state = True
                self._ready_for_urgent_command = False
                return super().handle_success(result)
            else:
                def accept_and_return_result(_):
                    self._accept_state = True
                    return result
                self._defer_result = defer.Deferred().addCallback(accept_and_return_result).addCallback(super().handle_success)
                return self._defer_result
        else:
            return super().handle_success(result)

    def enter(self):
        self.device.log.info(f"Waiting for {self.condition}")
        self.device.conditionhandler.add_condition(self.condition, self.waitcommand.deferred_result)
        self._ready()

    def new_state(self, state, *args, **kwargs):
        if isinstance(state, (Shutdown, Error, Stopped)) and not self._accept_state:
            self.waitcommand.deferred_result.errback(state)
            self.device.conditionhandler.remove_deferred_for_condition(self.waitcommand.deferred_result, self.condition)
        elif isinstance(state, Ready) and not self._accept_state:
            self._ready()
            return
        super().new_state(state)

    def send_cmd(self, cmd: ABDeviceCommand):
        super().send_cmd(cmd)
        self._run_next_urgent_cmd()


class Waiting(Busy):
    pass
