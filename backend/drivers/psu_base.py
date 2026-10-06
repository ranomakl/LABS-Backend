from backend.devices.base import *
from abc import ABC, abstractmethod


class BaseDevice(AbstractBaseDevice, ABC):
    """Gemeinsame Schnittstelle aller Spannungsquellen (Joy-IT DPM86xx, TDK Lambda Z+, spaeter Keithley).
    Experimente in config.yml sollen nur diese Methoden benutzen, damit das Geraet per Treiberwechsel
    austauschbar bleibt. Messwerte kommen ueber die Observables "voltage" (V) und "current" (A)."""

    @abstractmethod
    def output_constant_current(self, current, max_voltage, amount_of_charge=None): pass

    @abstractmethod
    def output_constant_voltage(self, voltage, max_current, amount_of_charge=None): pass

    @abstractmethod
    def stop_current(self, *args, **kwargs): pass

    @abstractmethod
    def set_voltage(self, voltage): pass

    @abstractmethod
    def set_current(self, current): pass

    @abstractmethod
    def set_output(self, on): pass

    @abstractmethod
    def measure_output(self): pass
