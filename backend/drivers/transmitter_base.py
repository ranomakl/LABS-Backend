from backend.devices.base import *
from abc import ABC, abstractmethod


class BaseDevice(ABC):
    """Abstract interface for read-only multi-channel measurement transmitters (e.g. a Modbus
    multiparameter analyzer with several plug-in sensor channels for pH/conductivity/temperature/...).
    Every driver for this instrument type must implement these. Unlike pump_base/mfc_base, there is
    no actuation here - these devices are polled, not commanded."""

    @abstractmethod
    def read_channel(self, channel, **kwargs):
        """Query the current measured value (+ status/unit, if the instrument provides them) of one
        configured channel. `channel` identifies the channel by the name used in config.yml, not by
        a hardware slot number - see the concrete driver for how that mapping is configured."""
        pass
