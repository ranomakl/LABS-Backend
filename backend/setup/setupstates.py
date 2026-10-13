from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from backend.helpers_exceptions import IState
from .helpers_exceptions import SetupStateError, NonUniqueIDError, ExperimentOrderError
if TYPE_CHECKING:
    from backend.setup.setup import Setup


from abc import ABC, abstractmethod


class SetupState(IState, ABC):
    def __init__(self, setup):
        self.setup: Setup = setup

    def new_state(self, state):
        self.setup.stateobject = state

    def insert_experiment_after(self, existing_id: Optional[str], experiment_id: str, experiment_type: str, **kwargs):
        if experiment_id in self.setup.experiment_id_order:
            raise NonUniqueIDError(f"{experiment_id} already used.")
        new_index = len(self.setup.experiment_id_order)
        if existing_id is not None:
            for index, exp_id in enumerate(self.setup.experiment_order):
                if exp_id == existing_id:
                    new_index = index + 1
            if not new_index > self.setup.current_experiment_index:
                raise ExperimentOrderError("Experiment can't be inserted before current running experiment.")
        # 13.10.2026: Factory ZUERST holen. Vorher wurde die ID schon eingereiht und erst dann die
        # Factory nachgeschlagen - bei unbekanntem Experimenttyp blieb eine ID ohne Experiment in der
        # Schlange zurueck, und jeder spaetere Start scheiterte mit KeyError auf diese ID.
        try:
            factory = self.setup.experimentfactories[experiment_type]
        except KeyError:
            raise SetupStateError(f"Unknown experiment type {experiment_type!r} "
                                  f"(known: {sorted(self.setup.experimentfactories)})") from None
        experiment = factory.get_experiment(experiment_id, **kwargs)
        self.setup.experiment_id_order.insert(new_index, experiment_id)
        self.setup.experiments[experiment_id] = experiment

    def get_current_experiment(self):
        return None


class Initializing(SetupState):
    def enter(self):
        pass

    def insert_experiment_after(self, existing_id: Optional[str], experiment_id: str, experiment_type: str, **kwargs):
        raise SetupStateError("Experiment can't be added in Initializing state.")


class Ready(SetupState):
    def enter(self):
        try:
            self.setup.current_experiment_index += 1
        except IndexError:
            # 13.10.2026 Schrittmodus: leere Warteschlange -> zurueck auf Paused, sonst wuerde das
            # naechste GESENDETE Experiment sofort beim Senden starten (insert_experiment_after).
            if self.setup.step_mode:
                self.setup.state = Paused
            return
        else:
            self.setup.state = Busy
            self.setup.execute_experiment(self.setup.current_experiment)

    def insert_experiment_after(self, existing_id: Optional[str], experiment_id: str, experiment_type: str, **kwargs):
        super().insert_experiment_after(existing_id, experiment_id, experiment_type, **kwargs)
        if not self.setup.step_mode:   # Schrittmodus: nur einreihen, Start ausschliesslich per /api/start
            self.enter()


class Busy(SetupState):
    def enter(self):
        pass

    def get_current_experiment(self):
        id = self.setup.experiment_id_order[self.setup.current_experiment_index]
        return self.setup.experiments[id]


class Paused(Busy):
    def get_current_experiment(self):
        # Schrittmodus: im Paused-Zustand laeuft nichts (das Experiment am aktuellen Index ist das
        # gerade beendete) - sonst meldet station_overview/get_updates es weiter als laufend.
        if self.setup.step_mode:
            return None
        return super().get_current_experiment()


class Shutdown(SetupState):
    def enter(self):
        pass

    def new_state(self, stateclass):
        raise SetupStateError("Setup is in shutdown state.")

    def insert_experiment_after(self, existing_id: Optional[str], experiment_id: str, experiment_type: str, **kwargs):
        raise SetupStateError("Can't add experiment, setup is in shutdown state.")


class Failed(SetupState):
    def enter(self):
        pass

    def new_state(self, stateclass):
        # 08.10.2026: Stop/Shutdown muessen auch nach einem Fehler moeglich sein (Geraete sicher
        # abschalten, Backend sauber beenden). Weiterarbeiten (Ready/Busy) erst nach Neustart.
        if isinstance(stateclass, (Stopped, Shutdown)):   # kommt als Instanz (s. StateMachineMixIn.state)
            self.setup.stateobject = stateclass
            return
        raise SetupStateError("Setup is in failed state.")

    def insert_experiment_after(self, existing_id: Optional[str], experiment_id: str, experiment_type: str, **kwargs):
        raise SetupStateError("Can't add experiment, setup is in failed state.")


class Stopped(SetupState):
    def enter(self):
        pass
