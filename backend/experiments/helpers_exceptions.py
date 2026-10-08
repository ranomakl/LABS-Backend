class ParameterError(Exception):
    """Raised when parameters cannot be processed."""
    pass


class ExperimentFailedError(Exception):
    """Experiment ended in Failed (device error or stop condition); used as errback for Setup."""
