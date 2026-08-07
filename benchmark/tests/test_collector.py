"""EventCollector tests: scripted fake bot + recording backend, no network.

The fake bot yields a scripted RawGameEvent stream (including unmappable
events and a duplicate event_id); the recording backend reuses the pattern
from test_memory_base.py and adds failure/gate hooks.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from minemembench.core.models import (
    EventType,
    ExperienceEvent,
    RawEventKind,
    RawGameEvent,
)
from minemembench.events.collector import EventCollector
from minemembench.events.mapper import SemanticMapper
from minemembench.memory.base import MemoryBackend, MemoryItem, MemoryQuery, MemoryStats

TS = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def _raw(
    kind: RawEventKind, event_id: str, data: dict[str, Any] | None = None
) -> RawGameEvent:
    return RawGameEvent(event_id=event_id, timestamp=TS, kind=kind, data=data or {})


class FakeEventBot:
    """Yields a scripted stream; optionally drops the connection mid-stream."""

    def __init__(
        self,
        events: list[RawGameEvent],
        username: str = "BenchBot",
        disconnect_after: int | None = None,
    ) -> None:
        self.events = events
        self.username = username
        self.disconnect_after = disconnect_after

    async def iter_events(self) -> Any:
        for index, event in enumerate(self.events):
            if self.disconnect_after is not None and index >= self.disconnect_after:
                raise ConnectionError("simulated WebSocket disconnect")
            yield event


class RecordingBackend(MemoryBackend):
    """Records added events; optionally fails or gates persistence."""

    def __init__(
        self,
        fail_first_n: int = 0,
        *,
        gate: asyncio.Event | None = None,
        block_after: int = 0,
    ) -> None:
        self.fail_first_n = fail_first_n
        self.gate = gate
        self.block_after = block_after
        self.calls = 0
        self.added: list[ExperienceEvent] = []
        self.blocked_on: list[ExperienceEvent] = []

    async def add(self, event: ExperienceEvent) -> None:
        self.calls += 1
        if self.calls <= self.fail_first_n:
            raise RuntimeError("backend exploded")
        if self.gate is not None and self.calls > self.block_after:
            self.blocked_on.append(event)
            await self.gate.wait()
        self.added.append(event)

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        return []

    async def update(self, event: ExperienceEvent) -> None:
        return None

    async def reset(self, episode_id: str) -> None:
        return None

    async def stats(self) -> MemoryStats:
        return MemoryStats(backend="recording", item_count=len(self.added))


def _raw_ids(events: list[ExperienceEvent]) -> list[str]:
    return [event.raw_events[0].event_id for event in events]


async def _let_consumer_finish() -> None:
    """Yield once so the consumer task can process the finite fake stream.

    The fake stream is fully synchronous, so a single loop iteration is enough
    for the consumer to map and persist every event.
    """

    await asyncio.sleep(0)


async def test_only_mapped_events_reach_memory() -> None:
    stream = [
        _raw(RawEventKind.ITEM_DROPPED, "r1", {"dropper": "Steve", "item": "bread", "count": 2}),
        _raw(RawEventKind.CHAT, "r2", {"username": "Steve", "message": "hi"}),
        _raw(RawEventKind.ENTITY_HURT, "r3", {"victim": "BenchBot", "attacker": "Steve"}),
        _raw(RawEventKind.HEALTH, "r4", {"health": 10}),
        _raw(RawEventKind.ENTITY_HURT, "r5", {"victim": "BenchBot", "attacker": None}),
        _raw(RawEventKind.ITEM_DROPPED, "r6", {"dropper": "BenchBot", "item": "dirt", "count": 1}),
    ]
    backend = RecordingBackend()
    collector = EventCollector(FakeEventBot(stream), backend)

    await collector.start("ep-1")
    await _let_consumer_finish()
    collected = await collector.stop()

    assert _raw_ids(backend.added) == ["r1", "r3"]
    assert _raw_ids(collected) == ["r1", "r3"]
    assert [event.event_type for event in collected] == [
        EventType.PLAYER_SHARED_RESOURCE,
        EventType.PLAYER_ATTACKED_AGENT,
    ]
    assert all(event.episode_id == "ep-1" for event in collected)
    assert collector.dropped_count == 0


async def test_duplicate_raw_event_ids_are_deduplicated() -> None:
    shared = _raw(RawEventKind.ITEM_DROPPED, "dup-1", {"dropper": "Steve", "item": "bread", "count": 2})
    stream = [
        shared,
        shared,
        _raw(RawEventKind.ITEM_DROPPED, "dup-2", {"dropper": "Alex", "item": "apple", "count": 1}),
    ]
    backend = RecordingBackend()
    collector = EventCollector(FakeEventBot(stream), backend)

    await collector.start("ep-1")
    await _let_consumer_finish()
    collected = await collector.stop()

    assert _raw_ids(collected) == ["dup-1", "dup-2"]
    assert _raw_ids(backend.added) == ["dup-1", "dup-2"]


async def test_failing_memory_add_is_counted_and_never_crashes() -> None:
    stream = [
        _raw(RawEventKind.ITEM_DROPPED, "f1", {"dropper": "Steve", "item": "bread", "count": 1}),
        _raw(RawEventKind.ITEM_DROPPED, "f2", {"dropper": "Steve", "item": "apple", "count": 1}),
        _raw(RawEventKind.ITEM_DROPPED, "f3", {"dropper": "Alex", "item": "cake", "count": 1}),
    ]
    backend = RecordingBackend(fail_first_n=1)
    collector = EventCollector(FakeEventBot(stream), backend)

    await collector.start("ep-1")
    await _let_consumer_finish()
    collected = await collector.stop()

    assert collector.dropped_count == 1
    assert _raw_ids(backend.added) == ["f2", "f3"]
    assert _raw_ids(collected) == ["f1", "f2", "f3"]


async def test_stop_flushes_remaining_buffer() -> None:
    gate = asyncio.Event()
    backend = RecordingBackend(gate=gate, block_after=1)
    stream = [
        _raw(RawEventKind.ITEM_DROPPED, "b1", {"dropper": "Steve", "item": "bread", "count": 1}),
        _raw(RawEventKind.ITEM_DROPPED, "b2", {"dropper": "Alex", "item": "apple", "count": 1}),
    ]
    collector = EventCollector(FakeEventBot(stream), backend)

    await collector.start("ep-1")
    await asyncio.sleep(0.05)  # consumer mapped both, blocked persisting b2
    stop_task = asyncio.create_task(collector.stop())
    await asyncio.sleep(0.05)  # consumer cancelled; stop() re-persists b2 and blocks
    assert backend.calls == 3  # b1 + b2 cancelled in consumer + b2 again in stop()
    gate.set()
    collected = await stop_task

    assert _raw_ids(backend.added) == ["b1", "b2"]
    assert _raw_ids(collected) == ["b1", "b2"]


async def test_stream_disconnect_ends_collection_cleanly() -> None:
    stream = [
        _raw(RawEventKind.ITEM_DROPPED, "d1", {"dropper": "Steve", "item": "bread", "count": 1}),
        _raw(RawEventKind.ITEM_DROPPED, "d2", {"dropper": "Alex", "item": "apple", "count": 1}),
        _raw(RawEventKind.ITEM_DROPPED, "d3", {"dropper": "Chris", "item": "cake", "count": 1}),
    ]
    backend = RecordingBackend()
    collector = EventCollector(FakeEventBot(stream, disconnect_after=2), backend)

    await collector.start("ep-1")
    await _let_consumer_finish()
    collected = await collector.stop()  # must not raise

    assert _raw_ids(collected) == ["d1", "d2"]
    assert _raw_ids(backend.added) == ["d1", "d2"]


async def test_stop_without_start_returns_empty() -> None:
    collector = EventCollector(FakeEventBot([]), RecordingBackend())

    assert await collector.stop() == []


async def test_custom_mapper_is_used() -> None:
    class FixedMapper(SemanticMapper):
        def map_event(
            self,
            raw: RawGameEvent,
            *,
            bot_username: str,
            episode_id: str,
        ) -> ExperienceEvent | None:
            return ExperienceEvent(
                event_id="fixed-id",
                episode_id=episode_id,
                timestamp=raw.timestamp,
                actor=bot_username,
                event_type=EventType.AGENT_DIED,
                raw_events=[raw],
            )

    backend = RecordingBackend()
    collector = EventCollector(
        FakeEventBot([_raw(RawEventKind.CHAT, "c1", {"username": "Steve", "message": "hi"})]),
        backend,
        mapper=FixedMapper(),
    )

    await collector.start("ep-1")
    await _let_consumer_finish()
    collected = await collector.stop()

    assert _raw_ids(collected) == ["c1"]
    assert backend.added[0].event_id == "fixed-id"
