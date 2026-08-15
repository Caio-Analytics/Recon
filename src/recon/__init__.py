"""Recon — profiler exploratório de dados."""
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    # Fonte única da versão: o pyproject.toml. Antes o número aparecia
    # hardcoded no payload e divergia do pacote instalado.
    __version__ = _version("recon")
except PackageNotFoundError:  # rodando direto do source, sem instalação
    __version__ = "0.0.0+dev"

from .pipeline import DataProfiler  # noqa: E402  (precisa de __version__ definido)

__all__ = ["DataProfiler", "__version__"]
