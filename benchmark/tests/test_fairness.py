"""M15B fairness-audit tests: FairnessRecord contents and the episode-leakage
probe against fake backends (hermetic, no network)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from minemembench.agent.planner import SYSTEM_PROMPT_HASH, TOOL_SET_HASH
from minemembench.core.fairness import FairnessChecker, FairnessRecord
from minemembench.core.models import EventType, ExperienceEvent
from minemembench.memory.base import MemoryBackend, MemoryItem, MemoryQuery, MemoryStats

from .conftest import FakeLLM, make_settings


def _event(event_id: str, episode_id: str) -> ExperienceEvent:
    return ExperienceEvent(
        event_id=event_id,
        episode_id=episode_id,
        timestamp=datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC),
        actor="test",
        event_type=EventType.WORLD_FACT_UPDATED,
        context={"subject": "world", "fact": "rain"},
    )


class ScriptedBackend(MemoryBackend):
    """Fake backend: optionally honors episode scoping (default) or ignores it."""

    def __init__(self, items: list[MemoryItem], *, scoped: bool = True) -> None:
        self._items = list(items)
        self._scoped = scoped

    async def add(self, event: ExperienceEvent) -> None:
        self._items.append(
            MemoryItem(
                item_id=event.event_id,
                event=event,
                score=None,
                created_at=datetime.now(UTC),
            )
        )

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        if self._scoped:
            return [
                item
                for item in self._items
                if item.event.episode_id == query.episode_id
            ][: query.limit]
        return self._items[: query.limit]

    async def update(self, event: ExperienceEvent) -> None:
        pass

    async def reset(self, episode_id: str) -> None:
        self._items = [
            item
            for item in self._items
            if item.event.episode_id != episode_id
        ]

    async def stats(self) -> MemoryStats:
        return MemoryStats(backend="scripted", item_count=len(self._items))


def _memory_item(event: ExperienceEvent) -> MemoryItem:
    return MemoryItem(
        item_id=event.event_id,
        event=event,
        score=0.9,
        created_at=datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC),
    )


def _checker(**overrides) -> FairnessChecker:
    settings = make_settings(**overrides)
    return FairnessChecker(settings, FakeLLM([]))


# --- FairnessRecord contents -------------------------------------------------


def test_fairness_record_contains_controlled_variables() -> None:
    checker = _checker(minecraft_version="1.20.4", world_seed=12345)
    record = checker._base_record(
        scenario="delayed_recall",
        scenario_params={"interference_count": 200, "similar_distractor_count": 20},
    )

    assert isinstance(record, FairnessRecord)
    assert record.minecraft_version == "1.20.4"
    assert record.world_seed == 12345
    assert record.planner_model == "fake-model"
    assert record.temperature == 0.0
    assert len(record.system_prompt_hash) == 64
    assert len(record.tool_set_hash) == 64
    assert record.system_prompt_hash == SYSTEM_PROMPT_HASH
    assert record.tool_set_hash == TOOL_SET_HASH
    assert record.scenario == "delayed_recall"
    assert record.scenario_params == {
        "interference_count": 200,
        "similar_distractor_count": 20,
    }
    assert record.valid is True
    assert record.episode_leakage_checked is False


def test_fairness_record_defaults_unknown_version() -> None:
    record = _checker()._base_record(scenario="world_update", scenario_params={})
    assert record.minecraft_version == "unknown"
    assert record.world_seed is None


# --- episode-leakage probe ---------------------------------------------------


async def test_leakage_probe_clean_when_backend_scopes_episodes() -> None:
    previous = _memory_item(_event("prev-1", "ep-prev"))
    backend = ScriptedBackend([previous], scoped=True)
    leaked, count = await _checker().run_leakage_probe(
        backend, "ep-prev", "ep-next", "supply cache location"
    )
    assert leaked is False
    assert count == 0


async def test_leakage_probe_detects_leak_when_backend_ignores_scope() -> None:
    previous = _memory_item(_event("prev-1", "ep-prev"))
    backend = ScriptedBackend([previous], scoped=False)
    leaked, count = await _checker().run_leakage_probe(
        backend, "ep-prev", "ep-next", "supply cache location"
    )
    assert leaked is True
    assert count == 1


async def test_check_first_run_skips_probe_and_stays_valid() -> None:
    backend = ScriptedBackend([], scoped=False)
    record = await _run_check(_checker(), backend, previous=None, next_="ep-1")
    assert record.episode_leakage_checked is False
    assert record.episode_leakage_leaked is None
    assert record.valid is True


async def test_check_marks_invalid_when_leaked() -> None:
    previous = _memory_item(_event("prev-1", "ep-prev"))
    backend = ScriptedBackend([previous], scoped=False)
    record = await _run_check(_checker(), backend, previous="ep-prev", next_="ep-next")

    assert record.episode_leakage_checked is True
    assert record.episode_leakage_leaked is True
    assert record.episode_leakage_previous == "ep-prev"
    assert record.episode_leakage_next == "ep-next"
    assert record.valid is False
    assert record.invalid_reason is not None
    assert "ep-prev" in record.invalid_reason


async def test_check_keeps_valid_when_no_leak() -> None:
    previous = _memory_item(_event("prev-1", "ep-prev"))
    backend = ScriptedBackend([previous], scoped=True)
    record = await _run_check(_checker(), backend, previous="ep-prev", next_="ep-next")

    assert record.episode_leakage_checked is True
    assert record.episode_leakage_leaked is False
    assert record.valid is True
    assert record.invalid_reason is None


async def _run_check(checker, backend, *, previous, next_) -> FairnessRecord:
    return await checker.check(
        memory=backend,
        scenario="delayed_recall",
        scenario_params={},
        previous_episode=previous,
        next_episode=next_,
        leak_probe_query="previous run goal",
    )


async def test_check_uses_previous_episode_content_query() -> None:
    previous = _memory_item(_event("prev-1", "ep-prev"))
    backend = ScriptedBackend([previous], scoped=False)
    record = await _run_check(_checker(), backend, previous="ep-prev", next_="ep-next")
    assert record.leak_probe_query == "previous run goal"


def test_fairness_record_roundtrips_through_json() -> None:
    record = _checker(minecraft_version="1.20.4")._base_record(
        scenario="memory_noise_stress", scenario_params={"noise_count": 50}
    )
    parsed = FairnessRecord.model_validate_json(record.model_dump_json())
    assert parsed.model_dump() == record.model_dump()
