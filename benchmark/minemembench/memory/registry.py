"""Name → factory registry for memory backends.

Backends are injected into the agent loop through this registry; the planner
never branches on backend names. New backends (vector, mem0, letta, ...)
register a factory here — no other code changes allowed.
"""

from __future__ import annotations

from collections.abc import Callable

from ..core.config import Settings
from .base import MemoryBackend
from .letta_adapter import LettaBackend
from .mem0_adapter import Mem0Backend
from .no_memory import NoMemoryBackend
from .vector_memory import VectorMemoryBackend

#: A factory builds a ready-to-use backend from the process settings.
BackendFactory = Callable[[Settings], MemoryBackend]


class MemoryRegistryError(Exception):
    """Raised when an unknown backend name is requested."""


_FACTORIES: dict[str, BackendFactory] = {}


def register_backend(name: str, factory: BackendFactory) -> None:
    """Register `factory` under `name`, replacing any previous entry."""

    _FACTORIES[name] = factory


def available_backends() -> list[str]:
    """Names of all registered backends, sorted."""

    return sorted(_FACTORIES)


def create_memory_backend(name: str, settings: Settings) -> MemoryBackend:
    """Instantiate the backend registered under `name`."""

    try:
        factory = _FACTORIES[name]
    except KeyError:
        available = ", ".join(available_backends())
        raise MemoryRegistryError(
            f"unknown memory backend {name!r}. Available now: {available}. "
            "Other backends (graphiti) arrive in later milestones."
        ) from None
    return factory(settings)


# Built-in backends. `none` is the Phase-1 baseline (M4); `vector` is the
# local SQLite baseline (M6); `mem0` is the framework memory condition (M8);
# `letta` is the stateful-agent server condition (M9).
register_backend("none", lambda settings: NoMemoryBackend())
register_backend(
    "vector",
    lambda settings: VectorMemoryBackend(db_path=settings.vector_db_path),
)
register_backend(
    "mem0",
    lambda settings: Mem0Backend(settings=settings),
)
register_backend(
    "letta",
    lambda settings: LettaBackend(settings=settings),
)
