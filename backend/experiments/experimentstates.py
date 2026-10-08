from abc import ABC
import time

from backend.helpers_exceptions import IState


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
        try:
            self.experiment.stop()
        except Exception as error:  # noqa: BLE001 - alles, Hauptsache finish_experiment laeuft
            self.experiment.log.error("Stopping devices after failure raised: {error}", error=error)
        finally:
            self.experiment.finish_experiment()


class Stopped(Failed): pass
