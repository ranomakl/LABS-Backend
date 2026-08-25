from backend.devices.base import *
from abc import ABC, abstractmethod


class BaseDevice(ABC):
    """Abstract interface for gas chromatograph controllers reachable over a network API (e.g. a
    Micro GC talking REST/HTTP instead of serial/TCP framing). Every driver for this instrument
    type must implement these. Unlike pump_base/mfc_base, there is no persistent byte-stream
    connection - see the concrete driver for how request/response cycles are mapped onto the
    existing Command/state-machine machinery."""

    @abstractmethod
    def start_bakeout(self, minutes, **kwargs):
        """Start a bakeout procedure (minutes-to-hours long). Must return/represent completion via
        the device's existing Busy state machine, not by blocking - see the concrete driver."""
        pass

    @abstractmethod
    def load_method(self, method_name, **kwargs):
        """Load a method by name, ready to be executed with run_method()."""
        pass

    @abstractmethod
    def run_method(self, **kwargs):
        """Execute the currently loaded method (minutes-to-hours long, same non-blocking
        requirement as start_bakeout)."""
        pass

    @abstractmethod
    def get_status(self, **kwargs):
        """Query the current system/sequence status."""
        pass

    @abstractmethod
    def get_last_run_data(self, **kwargs):
        """Fetch the full datafile (JSON) of the most recently completed run. Any conversion to
        another format (e.g. CSV) is data post-processing, not device communication, and must NOT
        live here - see the concrete driver's separate, pure conversion function."""
        pass
