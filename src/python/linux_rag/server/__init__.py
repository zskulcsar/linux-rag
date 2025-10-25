"""gRPC server bootstrap package for the Linux RAG services."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

__all__ = ["ServerConfig", "serve"]

if TYPE_CHECKING:  # pragma: no cover - import is only for type checkers
    from .main import ServerConfig, serve


def __getattr__(name: str):
    if name in __all__:
        module = import_module(".main", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(__all__)
