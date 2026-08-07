"""NoMemoryBackend contract tests: the baseline must remember nothing."""

from __future__ import annotations

from minemembench.core.models import ExperienceEvent
from minemembench.memory.base import MemoryBackend, MemoryQuery
from minemembench.memory.no_memory import NoMemoryBackend

from .conftest import load_fixture


def _event() -> ExperienceEvent:
    return ExperienceEvent.model_validate(load_fixture("experience_event.json"))


def test_is_a_memory_backend() -> None:
    assert isinstance(NoMemoryBackend(), MemoryBackend)


async def test_add_and_update_are_no_ops() -> None:
    backend = NoMemoryBackend()
    await backend.add(_event())
    await backend.update(_event())

    items = await backend.retrieve(MemoryQuery(query_text="bread"))
    assert items == []


async def test_reset_is_a_no_op_and_retrieve_stays_empty() -> None:
    backend = NoMemoryBackend()
    await backend.add(_event())
    await backend.reset("ep-001")

    assert await backend.retrieve(MemoryQuery(query_text="anything", limit=5)) == []


async def test_stats_reports_none_and_zero() -> None:
    backend = NoMemoryBackend()
    await backend.add(_event())

    stats = await backend.stats()
    assert stats.backend == "none"
    assert stats.item_count == 0
