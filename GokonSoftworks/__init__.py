from .wetworks import LOG_PATH, GokonSoftworksError, log
from .worker import Backend, BackendError, backend, shutdown_backend
__all__ = [
    "Backend",
    "BackendError",
    "CoreTools",
    "GokonSoftworksError",
    "LOG_PATH",
    "backend",
    "log",
    "shutdown_backend",
]

def __getattr__(name):
    if name == "CoreTools":
        from .gokon_gui import CoreTools

        return CoreTools
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
