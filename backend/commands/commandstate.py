from abc import ABC, abstractmethod
import time

from twisted.internet import reactor

from backend.commands.helpers_exceptions import (CommandError, CommandRetryError, CommandTimeoutError,
                                                 CommandResponseError, CommandAction, CommandErrorError)
from backend.helpers_exceptions import IState
from backend.commands.results import Result


class CommandState(IState, ABC):
    callLater = reactor.callLater

    def __init__(self, command):
        self._command = command

    def new_state(self, state):
        self._command.stateobject = state


class NotSent(CommandState):
    def enter(self):
        pass


class Sent(CommandState):
    def enter(self):
        self._command.time = time.time()

        def timedout():
            self._command.timer = None
            reply = Result()
            reply.command = self._command
            # 12.10.2026: Laeuft der Befehl innerhalb einer CommandSeries (so sendet device.stop() die
            # Abschaltbefehle), muss der Timeout an die SERIE gehen - genau wie eine Antwort ueber
            # device.receive() an device.current_command (= die Serie) geht. Vorher landete der Timeout
            # nur beim inneren Befehl: der scheiterte still, die Serie blieb fuer immer "NotSent", das
            # Geraet erfuhr nichts davon (Netzteil-AUS 4x gesendet, dann nie wieder; kein Error-Zustand,
            # wenn ein Geraet schon bei initial_commands nicht antwortet).
            target = self._command
            series = getattr(self._command, "parent_command_series", None)
            if series is not None and series.current_command is self._command:
                target = series
            target.temp_result = CommandTimeoutError(reply=reply)
            target.state = Retry

        self._command.timer = self.callLater(self._command.parameters.timeout, timedout)


class Success(CommandState):
    def enter(self):
        self._command.deferred_result.callback(self._command.temp_result)


class Retry(CommandState):
    def __new__(cls, command, *args, **kwargs):
        command.fail_count += 1

        if command.fail_count > command.parameters.retries:
            command.temp_result = CommandRetryError(reply=command.temp_result)

        fail_conditions = [
            isinstance(command.temp_result, CommandRetryError),
            (isinstance(command.temp_result, CommandErrorError) and
             command.parameters.on_error == CommandAction.FAIL),
            (isinstance(command.temp_result, CommandTimeoutError) and
             command.parameters.on_timeout == CommandAction.FAIL),
        ]

        for entry in fail_conditions:
            if entry:
                return Fail(command)
        return super().__new__(cls)

    def enter(self):
        self._command.execute()


class Fail(CommandState):
    def enter(self):
        self._command.temp_result.command = self._command
        self._command.deferred_result.errback(self._command.temp_result)


class Cancelled(CommandState):
    def enter(self):
        pass
