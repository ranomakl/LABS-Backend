from collections import ChainMap, defaultdict
from pathlib import Path
import time
import sys

from twisted.internet import defer, reactor
from twisted.logger import (textFileLogObserver, FilteringLogObserver, LogLevelFilterPredicate, LogLevel,
                            globalLogBeginner, Logger, jsonFileLogObserver)

from backend.devices.devicefactory import DeviceFactory
from backend.experiments import experimentstates
from backend.experiments.experimentfactory import ExperimentFactory
from backend.helpers_exceptions import IObserver, StateMachineMixIn, BaseObservable
from .setupstates import *
from .setuptofrontend import SetupChannelFactory
from backend.conditions.conditionhandler import ConditionHandler


def initialize_logger(level, filename):
    filter_predicate = LogLevelFilterPredicate(defaultLogLevel=LogLevel.levelWithName(level))

    json_observer = jsonFileLogObserver(open(filename, "w"))
    json_observer = FilteringLogObserver(json_observer, [filter_predicate])

    app_observer = textFileLogObserver(sys.stdout)
    app_observer = FilteringLogObserver(app_observer, [filter_predicate])
    globalLogBeginner.beginLoggingTo([app_observer, json_observer])


class Setup(IObserver, StateMachineMixIn, BaseObservable):
    listenTCP = reactor.listenTCP

    def __init__(self, config: dict):
        self.config = config
        # 13.10.2026 Schrittmodus (docs/vorschlag_schrittmodus_frontend.md): true = nach jedem fertigen
        # Experiment Paused statt Ready; das naechste startet erst mit "Start Experiments" (/api/start),
        # Senden startet nie etwas. Standard false = Warteschlange laeuft wie bisher von selbst durch.
        self.step_mode = bool(config.get("step_mode", False))
        logpath = Path("logs/")
        logpath.mkdir(parents=True, exist_ok=True)
        initialize_logger(self.config["log_level"], logpath / "log.json")
        self.log = Logger(namespace="Experimental Setup")
        self.conditionhandler = ConditionHandler()
        super().__init__(initial_stateclass=Initializing)
        self.experimentfactories = {}
        self._devices = {}
        self._channels = {}
        self.experiments = {}
        self.experiment_id_order = []
        self._current_experiment_index = -1
        self._frontend_server = SetupChannelFactory(self)
        self.listenTCP(int(self.config["listen port"]), self._frontend_server)
        self.devices_and_channels = ChainMap(self._devices, self._channels)
        self._device_factory = DeviceFactory()
        # Geraete mit `enabled: false` in config.yml bleiben eingetragen, werden aber nicht verbunden;
        # Experimente, die sie benutzen, werden in _get_experimentfactories uebersprungen.
        self.disabled_devices = []
        # 27.10.2026: Geraete, die beim Start nicht verbinden (Name -> Fehlertext), fuer /api/device_states
        # und das Statusfenster tools/geraete_fenster.py. Sie fehlen in devices_and_channels.
        self.unavailable_devices = {}
        deferred_devices = []
        for name, parameters in self.config["devices"].items():
            parameters = dict(parameters)
            if not parameters.pop("enabled", True):
                self.disabled_devices.append(name)
                self.log.info("Geraet {name} ist deaktiviert (enabled: false) und wird nicht verbunden.", name=name)
                continue
            deferred_devices.append(self.get_device_or_channel(name, parameters))

        # consumeErrors: ein Geraet, das nicht verbindet, darf den Start der uebrigen nicht blockieren.
        # Der Fehler ist in get_device_or_channel bereits protokolliert.
        deferred_devices = defer.DeferredList(deferred_devices, consumeErrors=True)
        deferred_devices.addCallback(self._link_devices)
        deferred_devices.addCallback(self._get_experimentfactories)
        deferred_devices.addCallback(self.set_state, Paused)

    @property
    def current_experiment(self):
        try:
            return self.stateobject.get_current_experiment()
        except IndexError:
            return None

    @property
    def current_experiment_index(self):
        return self._current_experiment_index

    @current_experiment_index.setter
    def current_experiment_index(self, new_index: int):
        if new_index >= len(self.experiment_id_order):
            raise IndexError
        else:
            self._current_experiment_index = new_index
    
    def remote_start(self):
        return self.start()

    def remote_stop(self):
        if self.current_experiment is None:
            for device in self.devices_and_channels.values():
                device.stop()
        else:
            self.current_experiment.state = experimentstates.Stopped
        self.state = Stopped

    def remote_pause(self):
        pass

    def remote_shutdown(self):
        for device in self._devices.values():
            device.shutdown()

    def remote_insert_experiment_after(self, existing_id: str, experiment_id: str, experiment_type: str, **kwargs):
        return self.insert_experiment_after(existing_id, experiment_id, experiment_type, **kwargs)

    def remote_add_experiment(self, experiment_id: str, experiment_type: str, **kwargs):
        return self.add_experiment(experiment_id, experiment_type, **kwargs)

    def remote_station_overview(self):
        # 13.10.2026: zusaetzlich step_mode, finished_runs (fertige Schritte) und next_experiment_name
        # (naechster wartender Schritt), damit das Frontend im Schrittmodus "Schritt N von M fertig,
        # naechster: X" zeigen kann. Die alten Felder bleiben unveraendert.
        index = self._current_experiment_index
        order = self.experiment_id_order
        current = self.current_experiment
        return {
            "status": self.state.__name__,
            "running_experiment_name": current.id if current is not None else "",
            "total_experiments_queued": len(order),
            "current_run_number": index + 1 if current is not None else "",
            "step_mode": self.step_mode,
            "finished_runs": index + 1 if current is None else index,
            "next_experiment_name": order[index + 1] if index + 1 < len(order) else "",
        }

    def remote_get_experiment_types(self):
        experiment_types = {}
        for experiment_type, experiment_factory in self.experimentfactories.items():
            experiment_types[experiment_type] = {
                "parameters": experiment_factory.experiment_parameter_details,
                "observables": experiment_factory.experiment_observable_details
            }
        return experiment_types

    def remote_station_run_tables(self):
        experiments = []
        for id, experiment in self.experiments.items():
            data = {
                "name": id,
                "type": experiment.factory.experiment_name,
                "parameters": experiment.parameters,
                "state": experiment.state.__name__
            }
            experiments.append(data)
        return experiments

    _TIME_UNITS_S = {"s": 1, "sec": 1, "seconds": 1, "min": 60, "minutes": 60, "h": 3600, "hours": 3600}

    @classmethod
    def _planned_duration_s(cls, experiment):
        """Summe aller Experiment-Parameter mit Zeiteinheit (s/min/h) in Sekunden; None, wenn es keinen gibt.
        Parameter liegen als {name: [wert, einheit]} vor (ExperimentFactory._get_experiment_parameters)."""
        total = None
        for value in (getattr(experiment, "parameters", None) or {}).values():
            try:
                number, unit = value
                factor = cls._TIME_UNITS_S[str(unit).strip().lower()]
                total = (total or 0.0) + float(number) * factor
            except (TypeError, ValueError, KeyError):
                continue
        return total

    def remote_get_updates(self, component_observable_pairs: Optional[dict] = None, from_timestamp: Optional[str] = None, to_timestamp: Optional[str] = None):
        response = {"timestamp": time.time()}
        from_timestamp = float(from_timestamp) if from_timestamp is not None else None
        to_timestamp = float(to_timestamp) if to_timestamp is not None else None
        if self.current_experiment is None:
            response["current_experiment"] = ""
            response["experiment_started"] = ""
        else:
            response["current_experiment"] = self.current_experiment.id
            response["experiment_started"] = self.current_experiment.starting_time
            # 08.10.2026: geplante Dauer aus den Zeit-Parametern des Experiments (z.B. minutes: [float, min]),
            # damit das Frontend neben dem Timer die Uhrzeit des voraussichtlichen Endes zeigen kann.
            duration = self._planned_duration_s(self.current_experiment)
            response["experiment_planned_duration_s"] = duration
            started = self.current_experiment.starting_time
            response["experiment_planned_end"] = started + duration if (duration is not None and started) else None
        if component_observable_pairs is None:
            component_observable_pairs = defaultdict(list)
            if self.current_experiment is None:
                component_observable_pairs = {device: [] for device in self.devices_and_channels.keys()}
            else:
                for observable_detail in self.current_experiment.observable_details:
                    component_observable_pairs[observable_detail[0]].append(observable_detail[1])
        updates = response["updates"] = defaultdict(dict)
        for componentname, observablenames in component_observable_pairs.items():
            for observablename in observablenames:
                updates[componentname][observablename] = self.devices_and_channels[componentname].get_updates(
                    observablename, from_timestamp, to_timestamp)
        return response

    def remote_station_components(self):
        components_list = []
        for name, device_or_channel in self.devices_and_channels.items():
            component_details = {
                    "component_name": name,
                    "component_log_name": device_or_channel.log_name, 
                    "component_address": device_or_channel.full_address                  
                }
            try:
                component_details["channel"] = device_or_channel.channel
            except AttributeError:
                pass
            components_list.append(component_details)
        return components_list

    # Geraetezustaende, in denen das Geraet NICHT benutzbar ist (fuer "ok" in remote_device_states).
    _DEVICE_STATES_NOT_OK = ("Error", "Shutdown", "NotReady", "Initializing", "CollectingCommands")

    def remote_device_states(self):
        """27.10.2026: Zustand jedes in config.yml eingetragenen Geraets, in Config-Reihenfolge, fuer das
        Statusfenster nach dem Start (tools/geraete_fenster.py). Anders als station_components stehen hier
        auch Geraete drin, die nicht verbunden sind (fehlen in devices_and_channels) oder deaktiviert sind.
        ok: True = verbunden und benutzbar; state: Geraetezustand bzw. "nicht verbunden"/"deaktiviert";
        reason: Fehlertext, wenn nicht ok."""
        states = []
        for name, parameters in self.config["devices"].items():
            entry = {"name": name, "driver": str(parameters.get("driver", "")),
                     "address": str(parameters.get("address", "")), "ok": False, "state": "", "reason": ""}
            if name in self.disabled_devices:
                entry.update(state="deaktiviert", reason="enabled: false in config.yml")
            elif name in self.unavailable_devices:
                entry.update(state="nicht verbunden", reason=self.unavailable_devices[name])
            else:
                component = self.devices_and_channels.get(name)
                if component is None:
                    entry.update(state="nicht verbunden", reason="Verbindungsaufbau noch nicht abgeschlossen")
                else:
                    device = getattr(component, "device", component)
                    state = device.state.__name__
                    entry.update(state=state, ok=state not in self._DEVICE_STATES_NOT_OK)
                    if not entry["ok"]:
                        entry["reason"] = f"Geraet im Zustand {state}"
            states.append(entry)
        return states

    def get_device_or_channel(self, name, parameters):
        try:
            deferred_device_or_channel = self._device_factory.construct_device(conditionhandler=self.conditionhandler,
                                                                               **parameters)
        except Exception:
            # z.B. serieller Pfad existiert nicht (Adapter nicht eingesteckt) - SerialPort() wirft sofort.
            self.log.failure("Geraet {name} konnte nicht angelegt werden und wird uebersprungen.", name=name)
            self.unavailable_devices[name] = f"konnte nicht angelegt werden: {sys.exc_info()[1]}"
            return defer.fail()

        def observe_and_add(device_or_channel, name):
            device_or_channel.subscribe(self)
            self.conditionhandler.add_observable(device_or_channel)
            try:
                device = device_or_channel.device
            except AttributeError:
                device = device_or_channel
            else:
                self._channels[name] = device_or_channel
                name = f"{parameters['driver']} {parameters['address']}"
                device.subscribe(self)
            self._devices[name] = device
            return device_or_channel

        def log_unavailable(reason, name):
            self.log.error("Geraet {name} nicht verfuegbar, wird uebersprungen: {reason}",
                           name=name, reason=reason.getErrorMessage())
            self.unavailable_devices[name] = reason.getErrorMessage() or reason.type.__name__
            return reason
        return deferred_device_or_channel.addCallback(observe_and_add, name).addErrback(log_unavailable, name)

    def _link_devices(self, result):
        """26.10.2026: Geraete, die andere Geraete brauchen (der microGC stellt vor jedem Lauf die Ventile
        seiner Gasstroeme), bekommen nach dem Verbinden aller Geraete die Geraeteliste gereicht."""
        for name, device in list(self.devices_and_channels.items()):
            link = getattr(device, "link_devices", None)
            if link is None:
                continue
            try:
                link(self.devices_and_channels)
            except Exception:  # noqa: BLE001
                self.log.failure("Geraet {name}: link_devices fehlgeschlagen.", name=name)
        return result

    def _missing_references(self, experimentconfig: dict) -> list[str]:
        """Geraete/Teilexperimente, die ein Experiment braucht, aber die beim Start nicht verfuegbar sind
        (deaktiviert, nicht verbunden oder selbst uebersprungen)."""
        missing = set()
        for item in experimentconfig["commands"] or []:
            if len(item) == 4:
                if item[0] not in self.devices_and_channels:
                    missing.add(f"Geraet {item[0]}")
            elif item[0] not in self.experimentfactories:
                missing.add(f"Experiment {item[0]}")
        for details in experimentconfig["observables"] or []:
            if details[0] not in self.devices_and_channels:
                missing.add(f"Geraet {details[0]}")
        return sorted(missing)

    def _get_experimentfactories(self, result):
        self.skipped_experiments = {}
        for name, experimentconfig in self.config["experiments"].items():
            missing = self._missing_references(experimentconfig)
            if missing:
                self.skipped_experiments[name] = missing
                self.log.warn("Experiment {name} wird uebersprungen, nicht verfuegbar: {missing}",
                              name=name, missing=", ".join(missing))
                continue
            self.experimentfactories[name] = ExperimentFactory(self, experimentconfig, name)
        return result

    def _get_conditions(self, result):
        return result

    def insert_experiment_after(self, existing_id: str, experiment_id: str, experiment_type: str, **kwargs):
        return self.stateobject.insert_experiment_after(existing_id, experiment_id, experiment_type, **kwargs)

    def add_experiment(self, experiment_id: str, experiment_type: str, **kwargs):
        return self.insert_experiment_after(None, experiment_id, experiment_type, **kwargs)

    def start(self):
        if self.state == Paused or self.state == Stopped:
            self.state = Ready

    def execute_experiment(self, experiment):
        def stop_observing(result, experiment):
            experiment.unsubscribe(self)
            return result
        for device in self.devices_and_channels.values():
            device.reset_observables()
        experiment.subscribe(self)
        deferred = experiment.execute()
        deferred.addBoth(stop_observing, experiment)
        deferred.addCallbacks(self._experiment_finished, self.set_state, errbackArgs=[Failed])
        deferred.addErrback(lambda failure: self.log.error("Experiment {id} failed: {err}",
                                                           id=experiment.id, err=failure.getErrorMessage()))

    def _experiment_finished(self, result):
        # Schrittmodus: anhalten, bis "Start Experiments" den naechsten Schritt freigibt.
        self.state = Paused if self.step_mode else Ready
        return result

    def update(self, observable, observable_key, updated_value, timestamp):
        pass