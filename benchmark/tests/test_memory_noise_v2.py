"""TASK-016 key_retention_v2 falsification tests, hermetic.

These tests fail on semantic contamination: count-dependent target identity,
unstable noise prefixes, near-miss keys, planner-visible labels, probe-fed
metrics, ground-truth leakage, and compatibility drift with legacy results.
No network, no real LLM API, no real subprocesses.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from minemembench.agent.planner import memory_view_for_prompt
from minemembench.core.models import EventType, ExperienceEvent
from minemembench.core.runner import AgentRunner
from minemembench.memory.base import (
    EventRecordingBackend,
    MemoryBackend,
    MemoryItem,
    MemoryItemSnapshot,
    MemoryQuery,
    MemoryStats,
)
from minemembench.memory.no_memory import NoMemoryBackend
from minemembench.memory.vector_memory import VectorMemoryBackend
from minemembench.scenarios.base import (
    KeyRetentionGroundTruth,
    ScenarioContext,
    ScenarioParamError,
    ScenarioResult,
)
from minemembench.scenarios.memory_noise_stress import (
    GOAL,
    MemoryNoiseStressScenario,
    compute_key_retention_metrics,
    noise_entity_keys,
    target_entity_key,
)

from .conftest import FakeBotClient, SmartFakeLLM, make_settings

_BANNED_TOKENS = (
    "target",
    "noise",
    "relevant",
    "irrelevant",
    "correct",
    "wrong",
    "priority",
    "current",
    "stale",
)


async def _run_v2(
    memory,
    *,
    seed: int,
    noise_count: int,
    episode_id: str,
    campaign_mode: str = "controlled",
) -> ScenarioResult:
    scenario = MemoryNoiseStressScenario()
    scenario.apply_params(
        {"noise_count": noise_count, "noise_semantics_version": "key_retention_v2"}
    )
    recording = EventRecordingBackend(memory)
    llm = SmartFakeLLM()
    bot = FakeBotClient()
    ctx = ScenarioContext(
        bot=bot,
        memory=recording,
        runner=AgentRunner(bot, recording, llm),
        llm=llm,
        settings=make_settings(),
        seed=seed,
        episode_id=episode_id,
        campaign_mode=campaign_mode,
    )
    result = await scenario.run(ctx)
    result.injected_events = list(recording.offered_events)
    return result


def _semantic_stream(result: ScenarioResult) -> list[tuple]:
    return [
        (
            event.event_id,
            event.timestamp,
            event.actor,
            event.target,
            event.event_type,
            event.location,
            event.context,
            event.outcome,
        )
        for event in result.injected_events
    ]


def _noise_semantics(event: ExperienceEvent) -> tuple:
    """The backend-visible identity of a v2 event, minus id/timestamp/episode."""

    return (event.actor, event.event_type, tuple(sorted(event.context.items())))


# --- legacy compatibility -------------------------------------------------------


async def test_legacy_defaults_and_native_behavior_unchanged(tmp_path) -> None:
    scenario = MemoryNoiseStressScenario()
    assert scenario.params == {
        "noise_count": 0,
        "noise_semantics_version": "legacy",
    }

    scenario.apply_params({"noise_count": 5})
    llm = SmartFakeLLM()
    bot = FakeBotClient()
    memory = VectorMemoryBackend(str(tmp_path / "legacy.db"))
    ctx = ScenarioContext(
        bot=bot,
        memory=memory,
        runner=AgentRunner(bot, memory, llm),
        llm=llm,
        settings=make_settings(),
        seed=42,
        episode_id="ep-legacy-noise",
    )
    result = await scenario.run(ctx)

    assert result.run_log is not None
    assert result.run_log.goal == GOAL
    assert result.evaluation_ground_truth is None
    assert "target_retrieval_rank" not in result.metrics
    assert "retrieved_item_count" not in result.metrics
    assert result.metrics["relevant_memory_precision"] == 1.0
    assert result.metrics["irrelevant_retrieval_rate"] == 0.0
    assert result.retrieval_probes[0].phase == "evaluate"


def test_old_result_json_without_v2_fields_still_loads() -> None:
    """A pre-TASK-016 legacy result (no version param, no ground truth)
    validates unchanged: optional fields default to None."""

    old_payload: dict[str, Any] = {
        "scenario": "memory_noise_stress",
        "episode_id": "ep-old",
        "seed": 42,
        "memory_backend": "vector",
        "success": True,
        "metrics": {
            "task_success": 1,
            "relevant_memory_precision": 1.0,
            "irrelevant_retrieval_rate": 0.0,
            "retrieval_latency_ms": 1.5,
            "token_cost": 15,
        },
        "params": {"noise_count": 0},
    }
    result = ScenarioResult.model_validate(old_payload)
    assert result.evaluation_ground_truth is None
    assert result.params == {"noise_count": 0}
    assert result.metrics["relevant_memory_precision"] == 1.0


# --- fail-closed gates ------------------------------------------------------------


def test_invalid_params_and_versions_fail_closed() -> None:
    scenario = MemoryNoiseStressScenario()
    with pytest.raises(ScenarioParamError):
        scenario.apply_params({"noise_semantics_version": "bogus"})
    with pytest.raises(ScenarioParamError):
        scenario.apply_params({"noise_count": -1})
    with pytest.raises(ScenarioParamError):
        scenario.apply_params({"noise_count": 1.5})
    with pytest.raises(ScenarioParamError):
        scenario.apply_params({"unknown_knob": 1})


async def test_controlled_legacy_fails_closed_before_side_effects() -> None:
    """A legacy Controlled memory-noise run is research-invalid: rejected at
    setup before any bot action, LLM call, or memory write."""

    scenario = MemoryNoiseStressScenario()  # legacy default
    llm = SmartFakeLLM()
    bot = FakeBotClient()
    recording = EventRecordingBackend(NoMemoryBackend())
    ctx = ScenarioContext(
        bot=bot,
        memory=recording,
        runner=AgentRunner(bot, recording, llm),
        llm=llm,
        settings=make_settings(),
        seed=42,
        episode_id="ep-gate",
        campaign_mode="controlled",
    )
    with pytest.raises(ScenarioParamError, match="key_retention_v2"):
        await scenario.run(ctx)
    assert recording.offered_events == []
    assert bot.execute_calls == []
    assert llm.calls == []


# --- deterministic identities ------------------------------------------------------


def test_target_key_is_deterministic_fixed_width_and_seed_dependent() -> None:
    key = target_entity_key(42)
    assert key == target_entity_key(42)
    assert key != target_entity_key(43)
    prefix, suffix = key.split("-", 1)
    assert prefix == "cache"
    assert len(suffix) == 8
    assert all(char in "0123456789abcdef" for char in suffix)


async def test_target_identity_independent_of_noise_count(tmp_path) -> None:
    """The target key and target event content must not move with
    `noise_count` (Controlled event ids hash the full effective params by
    design, so identity independence is asserted on the key/coordinates)."""

    results = [
        await _run_v2(
            NoMemoryBackend(),
            seed=42,
            noise_count=count,
            episode_id=f"ep-t-{count}",
        )
        for count in (0, 10, 1000)
    ]
    truths = [result.evaluation_ground_truth for result in results]
    assert all(isinstance(truth, KeyRetentionGroundTruth) for truth in truths)
    assert {truth.target_entity_key for truth in truths} == {target_entity_key(42)}

    target_contexts = set()
    for result in results:
        target_event = result.injected_events[0]  # experience phase is first
        assert target_event.context["entity_key"] == target_entity_key(42)
        target_contexts.add(tuple(sorted(target_event.context.items())))
        assert target_event.actor == "scenario-instructor"
        assert target_event.event_type is EventType.LOCATION_DISCOVERED
    assert len(target_contexts) == 1  # same target location at every level


async def test_noise_prefix_stability_and_uniqueness(tmp_path) -> None:
    """Cells N and M (N < M) share the same first N noise events; at 1000 the
    keys/coordinates stay unique and never near-miss the target key."""

    small = await _run_v2(
        NoMemoryBackend(), seed=42, noise_count=10, episode_id="ep-n-10"
    )
    large = await _run_v2(
        NoMemoryBackend(), seed=42, noise_count=1000, episode_id="ep-n-1000"
    )

    small_noise = [_noise_semantics(e) for e in small.injected_events[1:]]
    large_noise = [_noise_semantics(e) for e in large.injected_events[1:]]
    assert len(small_noise) == 10
    assert len(large_noise) == 1000
    assert large_noise[:10] == small_noise  # prefix stability

    target_key = target_entity_key(42)
    keys = [e.context["entity_key"] for e in large.injected_events]
    assert len(set(keys)) == 1001  # target + 1000 noise, all unique
    for key in keys[1:]:
        assert sum(a != b for a, b in zip(key, target_key, strict=True)) > 1

    coords = [
        (e.context["x"], e.context["y"], e.context["z"])
        for e in large.injected_events
    ]
    assert len(set(coords)) == 1001  # target + noise coordinates unique

    empty = await _run_v2(
        NoMemoryBackend(), seed=42, noise_count=0, episode_id="ep-n-0"
    )
    assert len(empty.injected_events) == 1  # target only
    truth = empty.evaluation_ground_truth
    assert isinstance(truth, KeyRetentionGroundTruth)
    assert truth.noise_event_ids == []


def test_noise_key_generator_prefix_stability_and_near_miss_rejection() -> None:
    target = target_entity_key(7)
    full = noise_entity_keys(7, target, 50)
    assert noise_entity_keys(7, target, 50) == full  # deterministic
    assert full[:5] == noise_entity_keys(7, target, 5)  # count-independent
    assert len(set(full)) == 50
    for key in full:
        assert sum(a != b for a, b in zip(key, target, strict=True)) > 1


async def test_controlled_v2_streams_identical_across_backends(tmp_path) -> None:
    """NoMemory and Vector receive the identical offered event stream (only
    episode_id differs) for the same (seed, effective params)."""

    for seed in (42, 43, 44):
        first = await _run_v2(
            NoMemoryBackend(), seed=seed, noise_count=50, episode_id=f"ep-s1-{seed}"
        )
        second = await _run_v2(
            VectorMemoryBackend(str(tmp_path / f"s-{seed}.db")),
            seed=seed,
            noise_count=50,
            episode_id=f"ep-s2-{seed}",
        )
        assert _semantic_stream(first) == _semantic_stream(second)
        assert all(e.event_id.startswith("ctrl-") for e in first.injected_events)
        assert {e.episode_id for e in first.injected_events} == {f"ep-s1-{seed}"}
        assert {e.episode_id for e in second.injected_events} == {f"ep-s2-{seed}"}


async def test_native_v2_keeps_uuid_event_ids(tmp_path) -> None:
    result = await _run_v2(
        VectorMemoryBackend(str(tmp_path / "native.db")),
        seed=42,
        noise_count=3,
        episode_id="ep-native-v2",
        campaign_mode="native",
    )
    assert len(result.injected_events) == 4
    assert not any(e.event_id.startswith("ctrl-") for e in result.injected_events)
    assert isinstance(result.evaluation_ground_truth, KeyRetentionGroundTruth)


# --- no labels, no leakage ----------------------------------------------------------


async def test_no_banned_labels_or_ground_truth_leakage(tmp_path) -> None:
    scenario = MemoryNoiseStressScenario()
    scenario.apply_params(
        {"noise_count": 20, "noise_semantics_version": "key_retention_v2"}
    )
    recording = EventRecordingBackend(VectorMemoryBackend(str(tmp_path / "labels.db")))
    llm = SmartFakeLLM()
    bot = FakeBotClient()
    ctx = ScenarioContext(
        bot=bot,
        memory=recording,
        runner=AgentRunner(bot, recording, llm),
        llm=llm,
        settings=make_settings(),
        seed=42,
        episode_id="ep-labels",
        campaign_mode="controlled",
    )
    result = await scenario.run(ctx)
    result.injected_events = list(recording.offered_events)
    assert result.run_log is not None

    # Prompt-visible event content carries no semantics labels.
    for event in result.injected_events:
        assert set(event.context) == {"entity_key", "x", "y", "z"}
        rendered = (
            json.dumps(event.context).lower()
            + event.actor.lower()
            + event.event_type.value.lower()
        )
        assert not any(token in rendered for token in _BANNED_TOKENS)

    # The goal names the key and leaks no coordinates or labels.
    goal = result.run_log.goal
    truth = result.evaluation_ground_truth
    assert isinstance(truth, KeyRetentionGroundTruth)
    assert truth.target_entity_key in goal
    target = result.injected_events[0].context
    assert str(target["x"]) not in goal
    assert str(target["z"]) not in goal
    assert not any(token in goal.lower() for token in _BANNED_TOKENS)

    # Ground-truth ids never reach the planner; the prompt memory view carries
    # no bookkeeping fields (ids, scores, storage timestamps, metadata).
    step0_items = result.run_log.steps[0].retrieved_items
    views = [memory_view_for_prompt(item) for item in step0_items]
    for view in views:
        assert set(view) == {"event"}
        serialized = json.dumps(view)
        for banned in ("item_id", "event_id", "episode_id", "score", "created_at"):
            assert banned not in serialized
    prompt_text = "".join(
        message["content"] for call in llm.calls for message in call
    )
    assert prompt_text  # the planner was really invoked
    for event in result.injected_events:
        assert event.event_id not in prompt_text


# --- metric math ---------------------------------------------------------------------


def _snapshot(event_id: str, entity_key: str = "cache-00000000") -> MemoryItemSnapshot:
    now = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)
    return MemoryItemSnapshot(
        item_id=event_id,
        score=None,
        created_at=now,
        metadata={},
        event=ExperienceEvent(
            event_id=event_id,
            episode_id="ep",
            timestamp=now,
            actor="scenario-instructor",
            event_type=EventType.LOCATION_DISCOVERED,
            context={"entity_key": entity_key, "x": 1.0, "y": 64.0, "z": 2.0},
        ),
    )


def test_metric_math_empty_retrieval() -> None:
    metrics = compute_key_retention_metrics([], "t", ["n1", "n2"])
    assert metrics == {
        "target_retrieval_rank": None,
        "target_recall": 0,
        "target_retrieval_precision": None,
        "noise_retrieval_rate": None,
        "target_top1": None,
        "retrieved_item_count": 0,
    }


def test_metric_math_target_rank1_with_noise() -> None:
    items = [_snapshot("t"), _snapshot("n1"), _snapshot("n2"), _snapshot("x")]
    metrics = compute_key_retention_metrics(items, "t", ["n1", "n2"])
    assert metrics["target_retrieval_rank"] == 1
    assert metrics["target_recall"] == 1
    assert metrics["target_retrieval_precision"] == 0.25
    assert metrics["noise_retrieval_rate"] == 0.5
    assert metrics["target_top1"] == 1
    assert metrics["retrieved_item_count"] == 4


def test_metric_math_target_below_rank1() -> None:
    items = [_snapshot("n1"), _snapshot("n2"), _snapshot("t")]
    metrics = compute_key_retention_metrics(items, "t", ["n1", "n2"])
    assert metrics["target_retrieval_rank"] == 3
    assert metrics["target_recall"] == 1
    assert metrics["target_retrieval_precision"] == round(1 / 3, 4)
    assert metrics["noise_retrieval_rate"] == round(2 / 3, 4)
    assert metrics["target_top1"] == 0


def test_metric_math_target_absent_and_unknown_top() -> None:
    # Known noise only: measured miss, top1 0.
    items = [_snapshot("n1"), _snapshot("n2")]
    metrics = compute_key_retention_metrics(items, "t", ["n1", "n2"])
    assert metrics["target_retrieval_rank"] is None
    assert metrics["target_recall"] == 0
    assert metrics["target_retrieval_precision"] == 0.0
    assert metrics["noise_retrieval_rate"] == 1.0
    assert metrics["target_top1"] == 0

    # Unknown items only: rates 0.0, top1 N/A.
    items = [_snapshot("x"), _snapshot("y")]
    metrics = compute_key_retention_metrics(items, "t", ["n1", "n2"])
    assert metrics["target_recall"] == 0
    assert metrics["target_retrieval_precision"] == 0.0
    assert metrics["noise_retrieval_rate"] == 0.0
    assert metrics["target_top1"] is None

    # Unknown top item with the target below: top1 N/A, rank still measured.
    items = [_snapshot("x"), _snapshot("t")]
    metrics = compute_key_retention_metrics(items, "t", ["n1"])
    assert metrics["target_retrieval_rank"] == 2
    assert metrics["target_top1"] is None


# --- causal snapshot, not the probe ---------------------------------------------------


class FlipFlopBackend(MemoryBackend):
    """First retrieval (the causal step-0 one) returns the episode's items;
    every later retrieval (including the diagnostic probe) returns nothing."""

    def __init__(self) -> None:
        self._items: list[MemoryItem] = []
        self._retrieve_calls = 0

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
        self._retrieve_calls += 1
        if self._retrieve_calls > 1:
            return []
        return [
            item
            for item in self._items
            if item.event.episode_id == query.episode_id
        ][: query.limit]

    async def update(self, event: ExperienceEvent) -> None:
        pass

    async def reset(self, episode_id: str) -> None:
        self._items = [
            item for item in self._items if item.event.episode_id != episode_id
        ]

    async def stats(self) -> MemoryStats:
        return MemoryStats(backend="flipflop", item_count=len(self._items))


async def test_metrics_come_from_causal_snapshot_not_probe() -> None:
    result = await _run_v2(
        FlipFlopBackend(), seed=42, noise_count=5, episode_id="ep-flip"
    )

    # The diagnostic probe saw NOTHING (recorded as raw evidence)...
    assert len(result.retrieval_probes) == 1
    assert result.retrieval_probes[0].phase == "evaluate-diagnostic"
    assert result.retrieval_probes[0].items == []

    # ...yet the logged metrics describe the causal step-0 snapshot, which
    # contained target + 5 noise events in insertion order (target first).
    assert result.metrics["target_recall"] == 1
    assert result.metrics["target_retrieval_rank"] == 1
    assert result.metrics["target_top1"] == 1
    assert result.metrics["retrieved_item_count"] == 6
    assert result.metrics["noise_retrieval_rate"] == round(5 / 6, 4)
    assert (
        result.metrics["retrieval_evidence_source"]
        == "run_log.steps[0].retrieved_items"
    )
    # Legacy retrieval-semantics keys stay N/A in v2 (no silent redefinition).
    assert result.metrics["relevant_memory_precision"] is None
    assert result.metrics["irrelevant_retrieval_rate"] is None


# --- typed ground truth ----------------------------------------------------------------


async def test_ground_truth_serialization_and_metric_rederivation(tmp_path) -> None:
    """Vector (non-empty retrieval) and NoMemory (empty retrieval) runs:
    ground truth survives the result JSON round-trip and every headline v2
    metric re-derives exactly from the restored snapshot alone."""

    vector_result = await _run_v2(
        VectorMemoryBackend(str(tmp_path / "gt.db")),
        seed=42,
        noise_count=10,
        episode_id="ep-gt-vector",
    )
    none_result = await _run_v2(
        NoMemoryBackend(), seed=42, noise_count=10, episode_id="ep-gt-none"
    )

    v2_metric_keys = (
        "target_retrieval_rank",
        "target_recall",
        "target_retrieval_precision",
        "noise_retrieval_rate",
        "target_top1",
        "retrieved_item_count",
    )
    for result in (vector_result, none_result):
        restored = ScenarioResult.model_validate_json(result.to_json())
        truth = restored.evaluation_ground_truth
        assert isinstance(truth, KeyRetentionGroundTruth)
        assert truth.semantics_version == "key_retention_v2"
        assert truth.target_event_id
        assert truth.target_entity_key == target_entity_key(42)
        assert len(truth.noise_event_ids) == 10
        # Ground truth ids match the actual offered stream.
        offered_ids = [event.event_id for event in result.injected_events]
        assert truth.target_event_id == offered_ids[0]
        assert truth.noise_event_ids == offered_ids[1:]

        step0_items = restored.run_log.steps[0].retrieved_items
        recomputed = compute_key_retention_metrics(
            step0_items, truth.target_event_id, truth.noise_event_ids
        )
        for key in v2_metric_keys:
            assert restored.metrics[key] == recomputed[key]
        assert restored.metrics["relevant_memory_precision"] is None
        assert restored.metrics["irrelevant_retrieval_rate"] is None

    # The NoMemory run really is the measured empty-retrieval miss.
    assert none_result.metrics["target_recall"] == 0
    assert none_result.metrics["target_retrieval_rank"] is None
    assert none_result.metrics["target_retrieval_precision"] is None
    assert none_result.metrics["noise_retrieval_rate"] is None
    assert none_result.metrics["target_top1"] is None
    assert none_result.metrics["retrieved_item_count"] == 0
    # The vector run really retrieved the stored facts.
    assert vector_result.metrics["retrieved_item_count"] > 0
    assert vector_result.metrics["target_recall"] == 1


def test_ground_truth_is_a_discriminated_union_member() -> None:
    truth = KeyRetentionGroundTruth(
        semantics_version="key_retention_v2",
        target_event_id="t",
        target_entity_key="cache-0123abcd",
        noise_event_ids=["n1", "n2"],
    )
    payload = json.loads(truth.model_dump_json())
    assert payload["semantics_version"] == "key_retention_v2"
    restored = ScenarioResult(
        scenario="memory_noise_stress",
        episode_id="ep",
        seed=1,
        memory_backend="none",
        success=False,
        evaluation_ground_truth=payload,
    )
    assert isinstance(restored.evaluation_ground_truth, KeyRetentionGroundTruth)
    assert restored.evaluation_ground_truth.noise_event_ids == ["n1", "n2"]
