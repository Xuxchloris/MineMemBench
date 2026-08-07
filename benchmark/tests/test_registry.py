"""Registry tests: known names build backends, unknown names fail clearly."""

from __future__ import annotations

import pytest

from minemembench.memory.no_memory import NoMemoryBackend
from minemembench.memory.registry import (
    MemoryRegistryError,
    available_backends,
    create_memory_backend,
)

from .conftest import make_settings


def test_create_none_backend() -> None:
    backend = create_memory_backend("none", make_settings())
    assert isinstance(backend, NoMemoryBackend)


def test_available_backends_lists_none() -> None:
    assert "none" in available_backends()


def test_unknown_backend_raises_clear_error() -> None:
    with pytest.raises(MemoryRegistryError) as exc_info:
        create_memory_backend("vector", make_settings())

    message = str(exc_info.value)
    assert "'vector'" in message
    assert "none" in message  # lists what IS available
    assert "later milestones" in message
