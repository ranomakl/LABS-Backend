from backend.devices.base import *
from abc import ABC, abstractmethod


class BaseDevice(ABC):
    """Abstract interface for mass flow controller / mass flow meter drivers.
    Every driver for this instrument type (e.g. bronkhorst_mfc) must implement these."""

    @abstractmethod
    def measure_flow(self, **kwargs):
        """Query the currently measured flow."""
        pass

    @abstractmethod
    def set_setpoint(self, setpoint, **kwargs):
        """Set the flow setpoint."""
        pass

    @abstractmethod
    def stop_flow(self, **kwargs):
        """Set the setpoint to 0 / close the controller."""
        pass

    # NEU (fuer bronkhorst_mfc.py ergaenzt): Totalizer/Counter-Messwert, zusaetzlich zum
    # Momentanfluss. Bestehende Treiber dieses Typs muessen die Methode ggf. nachruesten.
    @abstractmethod
    def read_counter(self, **kwargs):
        """Query an accumulating totalizer/counter value, if the instrument has one."""
        pass
