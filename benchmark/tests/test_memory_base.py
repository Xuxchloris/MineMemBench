"""Prove the MemoryBackend ABC is implementable and usable.

Uses a small test-local in-memory dummy; real backends land in M4+.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from minemembench.core.models import EventType, ExperienceEvent
from minemembench.memory.base import (
    MemoryBackend,
    MemoryItem,
    MemoryQuery,
    MemoryStats,
)


class InMemoryBackend(MemoryBackend):
    """Minimal dict-backed implementation used only in tests."""

    def __init__(self) -> None:
        self._items: dict[str, MemoryItem] = {}

    async def add(self, event: ExperienceEvent) -> None:
        self._items[event.event_id] = MemoryItem(
            item_id=event.event_id,
            event=event,
            score=None,
            created_at=datetime.now(UTC),
        )

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        items = [
            item
            for item in self._items.values()
            if query.episode_id is None or item.event.episode_id == query.episode_id
        ]
        event_type_filter = query.filters.get("event_type")
        if event_type_filter is not None:
            items = [
                item
                for item in items
                if item.event.event_type.value == event_type_filter
            ]
        return items[: query.limit]

    async def update(self, event: ExperienceEvent) -> None:
        if event.event_id in self._items:
            self._items[event.event_id].event = event

    async def reset(self, episode_id: str) -> None:
        self._items = {
            item_id: item
            for item_id, item in self._items.items()
            if item.event.episode_id != episode_id
        }

    async def stats(self) -> MemoryStats:
        return MemoryStats(backend="in-memory-dummy", item_count=len(self._items))


def _make_event(event_id: str, episode_id: str, outcome: str = "ok") -> ExperienceEvent:
    return ExperienceEvent(
        event_id=event_id,
        episode_id=episode_id,
        timestamp=datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC),
        actor="player:Steve",
        target="agent",
        event_type=EventType.PLAYER_SHARED_RESOURCE,
        context={"item": "bread", "count": 2},
        outcome=outcome,
    )


def test_abc_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        MemoryBackend()  # type: ignore[abstract]


async def test_add_retrieve_stats() -> None:
    backend = InMemoryBackend()
    await backend.add(_make_event("e1", "ep-1"))
    await backend.add(_make_event("e2", "ep-1"))
    await backend.add(_make_event("e3", "ep-2"))

    items = await backend.retrieve(MemoryQuery(query_text="bread", episode_id="ep-1"))
    assert [item.item_id for item in items] == ["e1", "e2"]
    assert items[0].event.event_type is EventType.PLAYER_SHARED_RESOURCE
    assert items[0].score is None

    stats = await backend.stats()
    assert stats.backend == "in-memory-dummy"
    assert stats.item_count == 3


async def test_retrieve_limit_and_filters() -> None:
    backend = InMemoryBackend()
    for index in range(3):
        await backend.add(_make_event(f"e{index}", "ep-1"))

    limited = await backend.retrieve(MemoryQuery(query_text="bread", limit=2))
    assert len(limited) == 2

    filtered = await backend.retrieve(
        MemoryQuery(query_text="bread", filters={"event_type": "agent_died"})
    )
    assert filtered == []


async def test_update_replaces_stored_event() -> None:
    backend = InMemoryBackend()
    await backend.add(_make_event("e1", "ep-1", outcome="old fact"))
    await backend.update(_make_event("e1", "ep-1", outcome="new fact"))

    items = await backend.retrieve(MemoryQuery(query_text="fact"))
    assert items[0].event.outcome == "new fact"


async def test_reset_only_clears_one_episode() -> None:
    backend = InMemoryBackend()
    await backend.add(_make_event("e1", "ep-1"))
    await backend.add(_make_event("e2", "ep-2"))

    await backend.reset("ep-1")

    stats = await backend.stats()
    assert stats.item_count == 1
    remaining = await backend.retrieve(MemoryQuery(query_text="bread"))
    assert [item.event.episode_id for item in remaining] == ["ep-2"]
