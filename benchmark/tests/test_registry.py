"""Registry tests: known names build backends, unknown names fail clearly."""

from __future__ import annotations

import pytest

from minemembench.memory.mem0_adapter import Mem0Backend
from minemembench.memory.no_memory import NoMemoryBackend
from minemembench.memory.registry import (
    MemoryRegistryError,
    available_backends,
    create_memory_backend,
)
from minemembench.memory.vector_memory import VectorMemoryBackend

from .conftest import make_settings


def test_create_none_backend() -> None:
    backend = create_memory_backend("none", make_settings())
    assert isinstance(backend, NoMemoryBackend)


def test_create_vector_backend(tmp_path) -> None:
    settings = make_settings(vector_db_path=str(tmp_path / "mem.db"))
    backend = create_memory_backend("vector", settings)
    assert isinstance(backend, VectorMemoryBackend)


def test_create_mem0_backend_does_not_import_mem0(tmp_path) -> None:
    # Constructing the backend must be lazy: no mem0ai import, no SDK build.
    settings = make_settings(mem0_qdrant_path=str(tmp_path / "mem0_qdrant"))
    backend = create_memory_backend("mem0", settings)
    assert isinstance(backend, Mem0Backend)
    assert backend._memory is None  # client built lazily on first use


def test_available_backends_lists_registered_names() -> None:
    assert "none" in available_backends()
    assert "vector" in available_backends()
    assert "mem0" in available_backends()


def test_unknown_backend_raises_clear_error() -> None:
    with pytest.raises(MemoryRegistryError) as exc_info:
        create_memory_backend("letta", make_settings())

    message = str(exc_info.value)
    assert "'letta'" in message
    assert "none" in message  # lists what IS available
    assert "vector" in message
    assert "later milestones" in message
