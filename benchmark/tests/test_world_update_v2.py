"""TASK-013 temporal_chain_v2 falsification tests (P1–P6), hermetic.

These tests fail on semantic contamination: coordinate collisions, planner-
visible labels, hidden oracle cues, probe-fed metrics, and compatibility
drift with legacy/round-4/round-5 artifacts.
"""

from __future__ import annotations

import copy
import glob
import json
import random
from datetime import UTC, datetime
from typing import Any

import pytest
from _pytest.outcomes import Skipped
from pydantic import ValidationError

from minemembench.agent.planner import memory_view_for_prompt
from minemembench.core.models import (
    EventType,
    ExperienceEvent,
)
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
    EntityKeyGroundTruth,
    ScenarioContext,
    ScenarioParamError,
    ScenarioResult,
    TemporalChainGroundTruth,
)
from minemembench.scenarios.world_update import (
    GOAL_TEMPORAL_CHAIN_V2,
    WorldUpdateScenario,
    compute_temporal_chain_metrics,
)

from .conftest import FakeBotClient, SmartFakeLLM, make_settings

_BANNED_TOKENS = (
    "moved",
    "stale",
    "current",
    "initial",
    "latest",
    "wrong",
    "old",
    "former",
    "correct",
    "update",
    "priority",
    "trust",
)


async def _run_v2(
    memory,
    *,
    seed: int,
    depth: int,
    episode_id: str,
) -> ScenarioResult:
    scenario = WorldUpdateScenario()
    scenario.apply_params(
        {"update_depth": depth, "update_semantics_version": "temporal_chain_v2"}
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
        campaign_mode="controlled",
    )
    result = await scenario.run(ctx)
    result.injected_events = list(recording.offered_events)
    return result


def _chain_events(result: ScenarioResult) -> list[ExperienceEvent]:
    return [
        event
        for event in result.injected_events
        if event.context.get("subject") == "supply_cache"
    ]


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


def _oracle(goal: str, views: list[dict[str, Any]]) -> tuple[Any, Any, Any] | None:
    """Test-only oracle (P2/P3): the current location is the chain candidate
    with the unique maximum semantic timestamp. Ambiguous (non-unique)
    timestamps report None — never a guess from order or labels."""

    assert goal == GOAL_TEMPORAL_CHAIN_V2
    chain = [
        view
        for view in views
        if view["event"]["context"].get("subject") == "supply_cache"
    ]
    if not chain:
        return None
    timestamps = [view["event"]["timestamp"] for view in chain]
    if len(set(timestamps)) != len(timestamps):
        return None
    newest = max(chain, key=lambda view: view["event"]["timestamp"])
    context = newest["event"]["context"]
    return (context["x"], context["y"], context["z"])


# --- P1: temporal validity -----------------------------------------------------


async def test_p1_temporal_validity_across_seeds_and_depths(tmp_path) -> None:
    for seed in (42, 43, 44):
        for depth in (1, 2, 3, 4):
            result = await _run_v2(
                NoMemoryBackend(),
                seed=seed,
                depth=depth,
                episode_id=f"ep-p1-{seed}-{depth}",
            )
            chain = _chain_events(result)
            assert len(chain) == depth + 1

            coords = [(e.context["x"], e.context["y"], e.context["z"]) for e in chain]
            assert len(set(coords)) == len(coords)  # unique coordinates

            timestamps = [event.timestamp for event in chain]
            assert len(set(timestamps)) == len(timestamps)
            assert timestamps == sorted(timestamps)  # strictly increasing

            for event in chain:
                assert event.actor == "scenario-instructor"
                assert event.event_type is EventType.WORLD_FACT_UPDATED
                assert set(event.context) == {"subject", "x", "y", "z"}
                rendered = json.dumps(event.context).lower()
                assert not any(token in rendered for token in _BANNED_TOKENS)

            ground_truth = result.evaluation_ground_truth
            assert isinstance(ground_truth, TemporalChainGroundTruth)
            assert ground_truth.entity_key == "supply_cache"
            assert ground_truth.stale_event_ids == [e.event_id for e in chain[:-1]]
            assert ground_truth.current_event_id == chain[-1].event_id


async def test_controlled_v2_streams_identical_across_backend_scopes(tmp_path) -> None:
    """TASK-013 §3: NoMemory and Vector receive the identical offered event
    stream (only episode_id differs) for seeds 42/43/44."""

    for seed in (42, 43, 44):
        first = await _run_v2(
            NoMemoryBackend(), seed=seed, depth=3, episode_id=f"ep-s1-{seed}"
        )
        second = await _run_v2(
            VectorMemoryBackend(str(tmp_path / f"s-{seed}.db")),
            seed=seed,
            depth=3,
            episode_id=f"ep-s2-{seed}",
        )
        assert _semantic_stream(first) == _semantic_stream(second)
        assert all(e.event_id.startswith("ctrl-") for e in first.injected_events)


async def test_controlled_mode_fails_closed_for_legacy(tmp_path) -> None:
    """No research-invalid legacy Controlled run may be produced."""

    scenario = WorldUpdateScenario()  # legacy default
    bot = FakeBotClient()
    llm = SmartFakeLLM()
    memory = NoMemoryBackend()
    ctx = ScenarioContext(
        bot=bot,
        memory=memory,
        runner=AgentRunner(bot, memory, llm),
        llm=llm,
        settings=make_settings(),
        seed=42,
        episode_id="ep-gate",
        campaign_mode="controlled",
    )
    try:
        await scenario.run(ctx)
    except ScenarioParamError as exc:
        assert "temporal_chain_v2" in str(exc)
    else:  # pragma: no cover - must never reach
        raise AssertionError("legacy Controlled world_update was not rejected")


# --- P2: unique visible oracle -------------------------------------------------


async def test_p2_oracle_selects_unique_newest_as_current(tmp_path) -> None:
    for seed in (42, 43, 44):
        result = await _run_v2(
            VectorMemoryBackend(str(tmp_path / f"p2-{seed}.db")),
            seed=seed,
            depth=3,
            episode_id=f"ep-p2-{seed}",
        )
        assert result.run_log is not None
        step0_items = result.run_log.steps[0].retrieved_items
        views = [memory_view_for_prompt(item) for item in step0_items]
        answer = _oracle(result.run_log.goal, views)
        assert answer is not None

        ground_truth = result.evaluation_ground_truth
        current = next(
            item for item in step0_items
            if item.event.event_id == ground_truth.current_event_id
        )
        assert answer == (
            current.event.context["x"],
            current.event.context["y"],
            current.event.context["z"],
        )


# --- P3: no hidden cue ---------------------------------------------------------


async def test_p3_oracle_time_is_the_only_cue(tmp_path) -> None:
    result = await _run_v2(
        VectorMemoryBackend(str(tmp_path / "p3.db")),
        seed=42,
        depth=3,
        episode_id="ep-p3",
    )
    assert result.run_log is not None
    views = [
        memory_view_for_prompt(item)
        for item in result.run_log.steps[0].retrieved_items
    ]
    answer = _oracle(result.run_log.goal, views)
    assert answer is not None

    # Order is not the cue.
    for permutation_seed in (0, 1, 2):
        shuffled = list(views)
        random.Random(permutation_seed).shuffle(shuffled)
        assert _oracle(result.run_log.goal, shuffled) == answer
    assert _oracle(result.run_log.goal, list(reversed(views))) == answer

    # Views carry no bookkeeping fields.
    for view in views:
        assert set(view) == {"event"}
        serialized = json.dumps(view)
        for banned in (
            "item_id",
            "event_id",
            "episode_id",
            "score",
            "created_at",
            "metadata",
            "raw_events",
        ):
            assert banned not in serialized

    # Equal timestamps -> ambiguity, never an order-based guess.
    flattened = copy.deepcopy(views)
    for view in flattened:
        if view["event"]["context"].get("subject") == "supply_cache":
            view["event"]["timestamp"] = "2026-01-01T00:00:00+00:00"
    assert _oracle(result.run_log.goal, flattened) is None

    # A different candidate with the unique newest timestamp wins: time —
    # not insertion order or a label — is the defined semantic cue.
    repointed = copy.deepcopy(views)
    chain_views = [
        view
        for view in repointed
        if view["event"]["context"].get("subject") == "supply_cache"
    ]
    usurper = chain_views[0]
    usurper["event"]["timestamp"] = "2099-01-01T00:00:00+00:00"
    expected = (
        usurper["event"]["context"]["x"],
        usurper["event"]["context"]["y"],
        usurper["event"]["context"]["z"],
    )
    assert _oracle(result.run_log.goal, repointed) == expected


# --- P4: independent metric derivation ------------------------------------------


async def test_p4_metrics_rederive_exactly_from_result_json(tmp_path) -> None:
    """Vector depth-3 (stale top-1, D below stale items) and NoMemory
    (empty retrieval) cases, re-derived from the serialized result alone."""

    vector_result = await _run_v2(
        VectorMemoryBackend(str(tmp_path / "p4.db")),
        seed=42,
        depth=3,
        episode_id="ep-p4-vector",
    )
    none_result = await _run_v2(
        NoMemoryBackend(), seed=42, depth=3, episode_id="ep-p4-none"
    )

    for result in (vector_result, none_result):
        restored = ScenarioResult.model_validate_json(result.to_json())
        ground_truth = restored.evaluation_ground_truth
        assert isinstance(ground_truth, TemporalChainGroundTruth)
        step0_items = restored.run_log.steps[0].retrieved_items
        recomputed = compute_temporal_chain_metrics(
            step0_items,
            ground_truth.current_event_id,
            ground_truth.stale_event_ids,
        )
        for key, value in recomputed.items():
            assert restored.metrics[key] == value
        # Compatibility mirrors.
        assert (
            restored.metrics["current_fact_accuracy"]
            == recomputed["current_fact_top1"]
        )
        assert (
            restored.metrics["obsolete_fact_retrieval_rate"]
            == recomputed["stale_fact_retrieval_rate"]
        )

    # The vector run really is the D-below-stale case; none is the empty miss.
    assert vector_result.metrics["current_fact_recall"] == 1
    assert vector_result.metrics["current_fact_top1"] == 0
    assert vector_result.metrics["stale_memory_rate"] == 0.75
    assert none_result.metrics["current_fact_recall"] == 0
    assert none_result.metrics["current_fact_retrieval_rank"] is None
    assert none_result.metrics["current_fact_retrieval_precision"] is None
    assert none_result.metrics["stale_fact_retrieval_rate"] is None


def _snapshot(event_id: str, subject: str = "supply_cache") -> MemoryItemSnapshot:
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
            event_type=EventType.WORLD_FACT_UPDATED,
            context={"subject": subject, "x": 1.0, "y": 64.0, "z": 2.0},
        ),
    )


def test_p4_metric_math_rank1_absent_and_noise_only() -> None:
    stale = ["a", "b", "c"]

    # D at rank 1.
    items = [_snapshot("d"), _snapshot("a")]
    metrics = compute_temporal_chain_metrics(items, "d", stale)
    assert metrics["current_fact_retrieval_rank"] == 1
    assert metrics["current_fact_top1"] == 1
    assert metrics["current_fact_recall"] == 1
    assert metrics["current_fact_retrieval_precision"] == 0.5
    assert metrics["stale_fact_retrieval_rate"] == 0.5
    assert metrics["stale_memory_rate"] == 0.5

    # D absent, stale items present: measured miss.
    items = [_snapshot("a"), _snapshot("b")]
    metrics = compute_temporal_chain_metrics(items, "d", stale)
    assert metrics["current_fact_retrieval_rank"] is None
    assert metrics["current_fact_recall"] == 0
    assert metrics["current_fact_top1"] == 0
    assert metrics["stale_fact_retrieval_rate"] == 1.0
    assert metrics["stale_memory_rate"] == 1.0

    # Noise-only non-empty retrieval: recall 0, rates 0.0, top1/stale N/A.
    items = [_snapshot("n1", subject="world"), _snapshot("n2", subject="world")]
    metrics = compute_temporal_chain_metrics(items, "d", stale)
    assert metrics["current_fact_recall"] == 0
    assert metrics["current_fact_retrieval_precision"] == 0.0
    assert metrics["stale_fact_retrieval_rate"] == 0.0
    assert metrics["current_fact_top1"] is None
    assert metrics["stale_memory_rate"] is None


# --- P5: causal snapshot, not the probe ------------------------------------------


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


async def test_p5_metrics_come_from_causal_snapshot_not_probe(tmp_path) -> None:
    result = await _run_v2(
        FlipFlopBackend(), seed=42, depth=3, episode_id="ep-p5"
    )

    # The diagnostic probe saw NOTHING (recorded as raw evidence)...
    assert len(result.retrieval_probes) == 1
    assert result.retrieval_probes[0].phase == "evaluate-diagnostic"
    assert result.retrieval_probes[0].items == []

    # ...yet the logged metrics describe the causal step-0 snapshot, which
    # contained the whole chain (A,B,C,D in insertion order: D below stale).
    assert result.metrics["current_fact_recall"] == 1
    assert result.metrics["current_fact_retrieval_rank"] == 4
    assert result.metrics["current_fact_top1"] == 0
    assert result.metrics["stale_memory_rate"] == 0.75
    assert (
        result.metrics["retrieval_evidence_source"]
        == "run_log.steps[0].retrieved_items"
    )
    # The stale first move is a behavior metric from the run log.
    assert result.metrics["stale_action"] == 1


# --- P6: compatibility ----------------------------------------------------------


async def test_p6_legacy_behavior_unchanged(tmp_path) -> None:
    scenario = WorldUpdateScenario()
    scenario.apply_params({"update_depth": 3})
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
        episode_id="ep-legacy-wu",
    )
    result = await scenario.run(ctx)

    assert result.run_log is not None
    assert result.run_log.goal == "Retrieve the supply cache."
    assert result.evaluation_ground_truth is None
    assert "current_fact_retrieval_rank" not in result.metrics
    assert "final_distance_to_current" not in result.metrics
    assert result.metrics["stale_memory_rate"] == 0.75  # legacy semantics
    assert result.metrics["current_fact_accuracy"] == 0


def _round_artifact_paths() -> tuple[list[str], list[str]]:
    """Local round-4/round-5 evidence files (gitignored; absent in a clean
    checkout)."""

    round4 = sorted(
        glob.glob("results/stress_controlled_round4_temporal_200_20/scenario_*.json")
    )
    round5 = sorted(
        glob.glob(
            "results/stress_controlled_round5_entity_key_v2_200_20/scenario_*.json"
        )
    )
    return round4, round5


def test_p6_round4_and_round5_result_files_still_load() -> None:
    """The typed-union refactor must not change round-5 loading; round-4
    files (no ground-truth field) validate to None.

    Portability contract (A-REVIEW-013): when BOTH artifact sets are absent
    (clean checkout) the test explicitly skips; a partial/absent single set
    or a wrong count fails. The strict all-24 gate for this workspace is the
    reviewer command recorded in B-COMPLETION-013, not this unit test.
    """

    round4, round5 = _round_artifact_paths()
    if not round4 and not round5:
        pytest.skip(
            "round-4/5 artifacts absent (clean checkout); the strict all-24 "
            "workspace gate is documented in B-COMPLETION-013"
        )
    assert len(round4) == 12
    assert len(round5) == 12
    for path in round4:
        with open(path, encoding="utf-8") as handle:
            result = ScenarioResult.model_validate(json.load(handle))
        assert result.evaluation_ground_truth is None
    for path in round5:
        with open(path, encoding="utf-8") as handle:
            result = ScenarioResult.model_validate(json.load(handle))
        ground_truth = result.evaluation_ground_truth
        assert isinstance(ground_truth, EntityKeyGroundTruth)
        assert ground_truth.target_event_id
        assert ground_truth.target_entity_key


def test_p6_evidence_test_skips_when_both_artifact_sets_absent(monkeypatch) -> None:
    """Hermetic absence path: with zero artifacts the evidence test SKIPS —
    the real local results are never moved, deleted, or copied."""

    monkeypatch.setattr(glob, "glob", lambda pattern: [])
    with pytest.raises(Skipped):
        test_p6_round4_and_round5_result_files_still_load()


def test_temporal_chain_ground_truth_enforces_entity_key() -> None:
    """The chain member accepts exactly `supply_cache`; anything else is a
    ValidationError (A-REVIEW-013 F-2)."""

    with pytest.raises(ValidationError):
        TemporalChainGroundTruth(
            semantics_version="temporal_chain_v2",
            entity_key="banana",
            current_event_id="d",
        )
    valid = TemporalChainGroundTruth(
        semantics_version="temporal_chain_v2",
        stale_event_ids=["a", "b", "c"],
        current_event_id="d",
    )
    assert valid.entity_key == "supply_cache"
