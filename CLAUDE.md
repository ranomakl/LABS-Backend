# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

LABS ("Laboratory Automation and Batch Scheduling") is a Twisted-based Python backend that controls
laboratory hardware (pumps, valves, a power supply, an NMR spectrometer, a fraction collector, etc.)
to run automated electrochemical synthesis experiments. It has been published alongside several papers
(see README.md for release/DOI history) and is still in active development — some features are
intentionally unfinished.

## Setup & running

```bash
py3 -m venv .venv
pip install -r requirements.txt
python main.py
```

`main.py` loads `config.yml`, constructs `backend.setup.setup.Setup`, and starts the Twisted `reactor`.
There is no build step, linter config, or test suite currently in the repo (some source files carry
Twisted-trial `# -*- test-case-name: backend.test.test_base -*-` style comments pointing at test modules
that don't exist yet — if you add tests, put them under `backend/test/` and run with
`python -m twisted.trial backend.test`).

## `config.yml` is the source of truth for hardware & experiments

Almost everything domain-specific lives in `config.yml`, not in Python:

- `listen port` / `destination port` / `log_level` — top-level server config.
- `devices:` — maps a device name (used everywhere else, including in code below) to a `driver`
  (must match a module name under `backend/drivers/`, loaded dynamically), an `address`
  (`COMx` → serial, IP:port → TCP — auto-detected), and optional driver-specific kwargs
  (`command_parameters`, `channel`, ...).
- `experiments:` — each entry is a reusable, parametrized "recipe": `parameters` (typed inputs),
  `observables` (which device readings to expose), `conditions`/`stopconditions` (named condition
  instances, see below), and `commands`, an ordered list where each item is either
  `[device, method, [args], {kwargs}]` (calls `method` on `device`) or `[other_experiment_name, {kwargs}]`
  (runs another experiment as a nested subexperiment). String args/kwargs may contain `{parameter_name}`
  placeholders that get filled in from the experiment's own parameters at instantiation time.

When asked to add/modify lab behavior, look here first — a new "routine" is usually a new `experiments:`
entry composed from existing device commands and existing experiment recipes, not new Python code.

## Architecture

Everything is asynchronous (Twisted `Deferred`s) and event-driven (a homegrown observer pattern:
`IObservable`/`IObserver`/`BaseObservable` in `backend/helpers_exceptions.py`). The same
`StateMachineMixIn` pattern (also in `backend/helpers_exceptions.py`) is reused at three different
levels of the stack — `Setup`, devices, and commands — each with its own state enum module and
`IState` subclasses whose `enter()`/`new_state()` drive transitions.

- **`backend/setup/`** — `Setup` (in `setup.py`) is the top-level orchestrator: owns all devices,
  builds one `ExperimentFactory` per `experiments:` entry, holds the experiment run queue
  (`experiment_id_order` + `experiments`), and is itself a state machine
  (`setupstates.py`: `Initializing → Paused → Ready → Busy → {Stopped, Failed, Shutdown}`) — `Ready.enter()`
  auto-advances to the next queued experiment. `setuptofrontend.py` exposes the whole thing over plain
  HTTP: any `GET /api/<name>` is routed to `Setup.remote_<name>(**querystring_as_json)`; see the
  `remote_*` methods on `Setup` for the actual API surface (start/stop/shutdown, add/insert experiments,
  station overview, experiment types, run tables, observable updates, component list).

- **`backend/devices/`** — `DeviceFactory.construct_device` dynamically imports
  `backend.drivers.<driver>` and instantiates its `Device` class (one shared instance per address, so
  two config entries pointing at the same address share a connection). `base.py` defines the device
  class hierarchy: `AbstractBaseDevice` (single connection, TCP or serial, owns a `cmd_queue` and its
  own device-level state machine — `devicestate.py`: `NotReady/Initializing/Ready/CollectingCommands/
  Busy/Waiting/Error/Stopped/Shutdown`), `MultichannelBaseDevice` (fans out to per-channel
  `ChannelProxy` objects that proxy most device methods but keep independent state/queues), and
  `ChannelProxy` itself.

- **`backend/commands/`** — a `Command` wraps one wire-level request/response with its own state
  machine (`commandstate.py`), retry/timeout/urgent-priority handling, and a `parser` (`parser.py`,
  e.g. `REParser`) that turns a raw reply line into a `Result`. `CommandSeries` batches multiple
  commands (used via the `with device.commandseries:` context manager) so they execute atomically
  as a unit, including nested series. `RepeatedCommand` polls on an interval;
  `WaitCommand` blocks a device in `Busy`/`Waiting` state until a condition fires.

- **`backend/drivers/`** — one module per physical instrument model; the module name is exactly the
  `driver:` value used in `config.yml`. Each defines a `commands` dict mapping a human-readable command
  name to `[wire_command_string, optional_reply_regex]`, plus `cmd_string`/`initial_commands`/
  `final_commands`/`handle_event`. Drivers subclass an instrument-type base (`pump_base.py`,
  `two_way_valve_base.py`/`multipos_valve_base.py`, `psu_base.py`, `thermostat_base.py`, `nmr_base.py`,
  `fraction_collector_base.py`) which defines the abstract public interface for that instrument type
  (e.g. every pump driver must implement `dispense`, `continuous_flow`, `stop_pumping`). Adding support
  for a new instrument = add a new driver module implementing the right base interface.

- **`backend/experiments/`** — `ExperimentFactory` parses one `experiments:` config entry once at
  startup (resolving device names and nested-experiment references). `get_experiment`/
  `get_subexperiment` then instantiate a per-run `Experiment`/`Subexperiment` with concrete parameter
  values substituted in. `Experiment.execute()` runs its command list sequentially over `Deferred`
  chains, tracks every subscribed device's observable updates, and writes per-run logs under
  `logs/<year>/<month>/<day>/<experiment_id>/` (`log.json`, `log.txt`, `values.json`).

- **`backend/conditions/`** — `ConditionHandler` is a pub/sub condition evaluator: devices/observables
  it's watching call back on every update, and it re-checks all registered `ABCondition`s, firing their
  deferred(s) the first time one turns true. `conditions.py` provides the building blocks referenced by
  name from `config.yml`'s `conditions:`/`stopconditions:` sections (`TimeCondition`,
  `ObservableEqualsValueCondition` and friends, `DevicesStateEqualsCondition`/`DevicesWaitingCondition`,
  `CombinedCondition`, `OngoingCondition`) and instantiated via `ABCondition.from_configsnippet`.

- **`backend/combined_observables/`** — derived observables layered on a device's raw observables:
  `TimeIntegral` (running integral of a numeric observable over time) and `MathExpression` (arbitrary
  expression over other observables, evaluated with `py_expression_eval`).

## Logging

Global logging goes to `logs/log.json` (JSON) and stdout, filtered by `config.yml`'s `log_level`
(Twisted `Logger`). Each experiment run additionally gets its own log directory as described above.
