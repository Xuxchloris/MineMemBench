"""VectorMemoryBackend contract tests (hermetic: tmp_path SQLite files)."""

from __future__ import annotations

from datetime import UTC, datetime

from minemembench.core.models import EventType, ExperienceEvent
from minemembench.memory.base import MemoryQuery
from minemembench.memory.vector_memory import VectorMemoryBackend


def _event(
    event_id: str,
    episode_id: str,
    *,
    event_type: EventType = EventType.RESOURCE_DISCOVERED,
    target: str | None = None,
    context: dict | None = None,
    outcome: str | None = None,
) -> ExperienceEvent:
    return ExperienceEvent(
        event_id=event_id,
        episode_id=episode_id,
        timestamp=datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
        actor="agent",
        target=target,
        event_type=event_type,
        context=context or {},
        outcome=outcome,
    )


def _backend(tmp_path) -> VectorMemoryBackend:
    return VectorMemoryBackend(str(tmp_path / "mem.db"))


async def test_add_retrieve_stats_contract(tmp_path) -> None:
    db = tmp_path / "mem.db"
    backend = VectorMemoryBackend(str(db))
    await backend.add(_event("e1", "ep-1", outcome="chest at the north base"))

    items = await backend.retrieve(MemoryQuery(query_text="where is the chest"))
    assert len(items) == 1
    assert items[0].item_id == "e1"
    assert items[0].event.outcome == "chest at the north base"
    assert items[0].score is not None and items[0].score > 0.0
    assert items[0].created_at.tzinfo is not None

    stats = await backend.stats()
    assert stats.backend == "vector"
    assert stats.item_count == 1
    assert stats.extra["db_path"] == str(db)
    assert stats.extra["embedder"] == "hash"
    assert stats.extra["avg_add_latency_ms"] is not None
    assert stats.extra["avg_retrieve_latency_ms"] is not None


async def test_episode_isolation(tmp_path) -> None:
    backend = _backend(tmp_path)
    await backend.add(_event("e1", "ep-1", outcome="chest at the north base"))
    await backend.add(_event("e2", "ep-2", outcome="chest at the south base"))

    only_ep1 = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert [item.item_id for item in only_ep1] == ["e1"]

    all_items = await backend.retrieve(MemoryQuery(query_text="chest"))
    assert {item.item_id for item in all_items} == {"e1", "e2"}


async def test_reset_clears_only_that_episode(tmp_path) -> None:
    backend = _backend(tmp_path)
    await backend.add(_event("e1", "ep-1", outcome="chest at the north base"))
    await backend.add(_event("e2", "ep-2", outcome="diamonds deep underground"))

    await backend.reset("ep-1")

    assert (await backend.stats()).item_count == 1
    items = await backend.retrieve(MemoryQuery(query_text="chest"))
    assert [item.event.episode_id for item in items] == ["ep-2"]


async def test_relevant_event_outranks_unrelated(tmp_path) -> None:
    backend = _backend(tmp_path)
    await backend.add(_event("e1", "ep-1", outcome="chest at the base"))
    await backend.add(
        _event(
            "e2",
            "ep-1",
            event_type=EventType.AGENT_DIED,
            outcome="diamonds buried deep underground",
        )
    )

    items = await backend.retrieve(MemoryQuery(query_text="where is the chest"))
    assert items[0].item_id == "e1"
    assert items[0].score > items[1].score


async def test_update_overwrites_stale_content(tmp_path) -> None:
    backend = _backend(tmp_path)
    await backend.add(_event("e1", "ep-1", outcome="chest is at the north base"))
    await backend.update(_event("e1", "ep-1", outcome="chest is at the south base"))

    items = await backend.retrieve(MemoryQuery(query_text="chest"))
    assert items[0].item_id == "e1"
    assert items[0].event.outcome == "chest is at the south base"

    stats = await backend.stats()
    assert stats.item_count == 1  # updated, never appended


async def test_persistence_across_instances(tmp_path) -> None:
    db = str(tmp_path / "mem.db")
    first = VectorMemoryBackend(db)
    await first.add(_event("e1", "ep-1", outcome="chest at the north base"))

    second = VectorMemoryBackend(db)
    items = await second.retrieve(MemoryQuery(query_text="chest"))
    assert items[0].event.outcome == "chest at the north base"
    assert (await second.stats()).item_count == 1


async def test_custom_embedder_is_used(tmp_path) -> None:
    class KeywordEmbedder:
        name = "keyword"

        def embed(self, text: str) -> list[float]:
            return [1.0, 0.0] if "chest" in text else [0.0, 1.0]

    backend = VectorMemoryBackend(
        str(tmp_path / "mem.db"), embedder=KeywordEmbedder()
    )
    await backend.add(_event("e1", "ep-1", outcome="chest at the base"))
    await backend.add(_event("e2", "ep-1", outcome="diamonds deep underground"))

    items = await backend.retrieve(MemoryQuery(query_text="chest", limit=2))
    assert [item.item_id for item in items] == ["e1", "e2"]
    assert items[0].score > items[1].score

    stats = await backend.stats()
    assert stats.extra["embedder"] == "keyword"
