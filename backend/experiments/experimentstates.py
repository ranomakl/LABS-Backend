from abc import ABC
import time

from backend.helpers_exceptions import IState
from .helpers_exceptions import ExperimentFailedError


class ExperimentState(IState, ABC):
    def __init__(self, experiment):
        self.experiment = experiment

    def enter(self):
        pass

    def new_state(self, state):
        self.experiment.stateobject = state


class Waiting(ExperimentState):
    pass


class Running(ExperimentState):
    def enter(self):
        self.experiment.start_log_observer()
        self.experiment.starting_time = time.time()
        self.experiment.save_run_info()
        for device in self.experiment.devices_and_channels.values():
            device.subscribe(self.experiment)

class Finished(ExperimentState):
    def enter(self):
        self.experiment.finishing_time = time.time()  
        self.experiment.finish_experiment()      

class Failed(ExperimentState):
    def enter(self):
        # 08.10.2026: stop() kann scheitern (Geraet im Error-Zustand) - die Messwerte muessen TROTZDEM
        # geschrieben werden (finish_experiment), sonst sind Stunden an Daten weg (Versuch 26174:
        # values.json fehlte, aus log.txt rekonstruiert).
        self.experiment.finishing_time = time.time()   # sonst lauf.json: final_state null
        try:
            self.experiment.stop()
        except Exception as error:  # noqa: BLE001 - alles, Hauptsache finish_experiment laeuft
            self.experiment.log.error("Stopping devices after failure raised: {error}", error=error)
        finally:
            self.experiment.finish_experiment()
        self._notify_setup()

    def _notify_setup(self):
        # Das Setup wartet auf deferred_success (setup.execute_experiment). Ohne errback bleibt es fuer
        # immer "Busy" mit dem abgebrochenen Experiment (so im Original und am 08.10.2026 im Labor).
        deferred = self.experiment.deferred_success
        if not deferred.called:
            deferred.errback(ExperimentFailedError(f"{self.experiment.log_name} failed"))

    def new_state(self, state):
        # Endzustand. Ein zweites Geraet im Error-Zustand oder ein spaetes Finished darf
        # stop()/finish_experiment()/errback nicht noch einmal ausloesen (AlreadyCalledError).
        # Manueller Stopp nach Fehler (Setup.remote_stop): Geraete nur nochmal abschalten.
        if isinstance(state, Stopped):
            try:
                self.experiment.stop()
            except Exception as error:  # noqa: BLE001
                self.experiment.log.error("Stopping devices again raised: {error}", error=error)
            return
        self.experiment.log.warn("Experiment already {current}, ignoring transition to {new}",
                                 current=type(self).__name__, new=type(state).__name__)


class Stopped(Failed):
    def _notify_setup(self):
        pass   # Setup.remote_stop setzt seinen Zustand selbst auf Stopped
