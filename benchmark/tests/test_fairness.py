"""M15B fairness-audit tests: FairnessRecord contents and the post-run
completed-episode reset verification against fake backends (hermetic, no
network)."""

from __future__ import annotations

from datetime import UTC, datetime

from minemembench.agent.planner import (
    PLANNER_USER_TEMPLATE_HASH,
    SYSTEM_PROMPT_HASH,
    TOOL_SET_HASH,
)
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
    """Fake backend with switchable scope honoring and failure injection."""

    def __init__(
        self,
        items: list[MemoryItem],
        *,
        scoped: bool = True,
        fail_reset: bool = False,
        fail_retrieve: bool = False,
    ) -> None:
        self._items = list(items)
        self._scoped = scoped
        self._fail_reset = fail_reset
        self._fail_retrieve = fail_retrieve
        self.reset_calls: list[str] = []

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
        if self._fail_retrieve:
            raise RuntimeError("retrieve exploded")
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
        self.reset_calls.append(episode_id)
        if self._fail_reset:
            raise RuntimeError("reset exploded")
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


async def _run_check(
    checker: FairnessChecker,
    backend: ScriptedBackend,
    *,
    episode_id: str = "ep-run",
    run_seed: int | None = 42,
) -> FairnessRecord:
    return await checker.check(
        memory=backend,
        scenario="delayed_recall",
        scenario_params={},
        episode_id=episode_id,
        run_seed=run_seed,
        probe_query="previous run goal",
    )


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
    assert record.planner_user_template_hash == PLANNER_USER_TEMPLATE_HASH
    assert len(record.planner_user_template_hash) == 64
    assert record.scenario == "delayed_recall"
    assert record.scenario_params == {
        "interference_count": 200,
        "similar_distractor_count": 20,
    }
    assert record.valid is True
    assert record.reset_performed is False


def test_fairness_record_defaults_unknown_version() -> None:
    record = _checker()._base_record(scenario="world_update", scenario_params={})
    assert record.minecraft_version == "unknown"
    assert record.world_seed is None


# --- completed-episode reset verification ------------------------------------


async def test_check_resets_completed_episode_and_probes_both_scopes() -> None:
    backend = ScriptedBackend([_memory_item(_event("e1", "ep-run"))])
    record = await _run_check(_checker(), backend)

    # The COMPLETED episode was reset, then both the reset scope and a fresh
    # scope were probed and found empty.
    assert backend.reset_calls[0] == "ep-run"
    assert record.reset_episode == "ep-run"
    assert record.reset_performed is True
    assert record.reset_error is None
    assert record.post_reset_items == 0
    assert record.fresh_scope_episode is not None
    assert record.fresh_scope_episode != "ep-run"
    assert record.fresh_scope_items == 0
    assert record.valid is True
    assert record.invalid_reason is None


async def test_check_records_run_seed_and_probe_query() -> None:
    backend = ScriptedBackend([])
    record = await _run_check(_checker(), backend, run_seed=44)
    assert record.run_seed == 44
    assert record.probe_query == "previous run goal"


async def test_probe_scopes_are_cleaned_up_afterwards() -> None:
    """Both probed scopes get a best-effort reset after probing, so a backend
    that lazily creates per-scope state (one letta agent per episode) is left
    with no probe artifacts."""

    backend = ScriptedBackend([_memory_item(_event("e1", "ep-run"))])
    record = await _run_check(_checker(), backend)

    assert backend.reset_calls == [
        "ep-run",  # the completed-episode reset
        "ep-run",  # best-effort cleanup after the post-reset probe
        record.fresh_scope_episode,  # cleanup of the fresh probe scope
    ]


async def test_check_marks_invalid_when_reset_leaves_items() -> None:
    """A backend that ignores reset leaks the completed episode's items into
    the post-reset probe: invalid, but the record is still produced."""

    class ResetIgnoringBackend(ScriptedBackend):
        async def reset(self, episode_id: str) -> None:
            self.reset_calls.append(episode_id)  # records but does NOT delete

    backend = ResetIgnoringBackend([_memory_item(_event("e1", "ep-run"))])
    record = await _run_check(_checker(), backend)

    assert record.reset_performed is True
    assert record.post_reset_items == 1
    assert record.valid is False
    assert record.invalid_reason is not None
    assert "post-reset" in record.invalid_reason or "reset episode" in record.invalid_reason


async def test_check_marks_invalid_when_reset_raises() -> None:
    backend = ScriptedBackend(
        [_memory_item(_event("e1", "ep-run"))], fail_reset=True
    )
    record = await _run_check(_checker(), backend)

    assert record.reset_performed is False
    assert record.reset_error is not None
    assert "reset exploded" in record.reset_error
    assert record.valid is False
    assert record.invalid_reason is not None


async def test_check_marks_invalid_when_probe_raises() -> None:
    backend = ScriptedBackend(
        [_memory_item(_event("e1", "ep-run"))], fail_retrieve=True
    )
    record = await _run_check(_checker(), backend)

    assert record.reset_performed is True
    assert record.post_reset_items is None  # probe never completed
    assert record.valid is False
    assert record.invalid_reason is not None
    assert "cleanup probe" in record.invalid_reason


async def test_check_marks_invalid_when_fresh_scope_is_contaminated() -> None:
    """A scope-ignoring backend surfaces another episode's items under a
    brand-new episode id: the fresh-scope probe catches it."""

    backend = ScriptedBackend(
        [_memory_item(_event("e1", "ep-run")), _memory_item(_event("e2", "ep-other"))],
        scoped=False,
    )
    record = await _run_check(_checker(), backend)

    assert record.fresh_scope_items is not None and record.fresh_scope_items > 0
    assert record.valid is False
    assert record.invalid_reason is not None
    assert "fresh scope" in record.invalid_reason


def test_fairness_record_roundtrips_through_json() -> None:
    record = _checker(minecraft_version="1.20.4")._base_record(
        scenario="memory_noise_stress", scenario_params={"noise_count": 50}
    )
    parsed = FairnessRecord.model_validate_json(record.model_dump_json())
    assert parsed.model_dump() == record.model_dump()


def test_fairness_record_without_template_hash_still_validates() -> None:
    """Backward compatibility: pre-TASK-009 records (no fingerprint field)
    must still load, defaulting to None."""

    record = _checker()._base_record(scenario="delayed_recall", scenario_params={})
    payload = record.model_dump()
    del payload["planner_user_template_hash"]
    parsed = FairnessRecord.model_validate(payload)
    assert parsed.planner_user_template_hash is None
    assert parsed.system_prompt_hash == SYSTEM_PROMPT_HASH
