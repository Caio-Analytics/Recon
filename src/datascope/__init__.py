from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    
    
    __version__ = _version("datascope")
except PackageNotFoundError:  
    __version__ = "0.0.0+dev"

from .pipeline import DataProfiler  # noqa: E402  (precisa de __version__ definido)

__all__ = ["DataProfiler", "__version__"]
