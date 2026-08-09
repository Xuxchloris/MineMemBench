"""TASK-011 entity_key_v2 falsification tests (P1–P4), hermetic.

These tests fail on semantic contamination: key/coordinate collisions,
planner-visible labels, hidden oracle cues, and metric drift between the
logged values and an independent re-derivation from the typed ground truth.
"""

from __future__ import annotations

import copy
import json
import random
import re
from datetime import UTC, datetime
from typing import Any

from minemembench.agent.planner import memory_view_for_prompt
from minemembench.core.models import EventType, ExperienceEvent
from minemembench.core.runner import AgentRunner
from minemembench.memory.base import (
    EventRecordingBackend,
    MemoryItemSnapshot,
)
from minemembench.memory.no_memory import NoMemoryBackend
from minemembench.memory.vector_memory import VectorMemoryBackend
from minemembench.scenarios.base import ScenarioContext, ScenarioResult
from minemembench.scenarios.controlled import controlled_event_identity
from minemembench.scenarios.delayed_recall import (
    DelayedRecallScenario,
    compute_entity_key_metrics,
    distractor_entity_keys,
    target_entity_key,
)

from .conftest import FakeBotClient, SmartFakeLLM, make_settings

#: Correctness/staleness/priority labels that must never appear in
#: planner-visible candidate content.
_BANNED_TOKENS = (
    "wrong",
    "stale",
    "old",
    "former",
    "decoy",
    "correct",
    "used to be",
    "invalid",
    "expired",
    "outdated",
    "priority",
    "trust",
)

_KEY_RE = re.compile(r"\bcache-[0-9a-f]{8}\b")


async def _run_v2(
    memory,
    *,
    seed: int,
    distractor_count: int,
    episode_id: str,
) -> ScenarioResult:
    scenario = DelayedRecallScenario()
    scenario.apply_params(
        {
            "similar_distractor_count": distractor_count,
            "recall_semantics_version": "entity_key_v2",
        }
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


def _candidate_events(result: ScenarioResult) -> list[ExperienceEvent]:
    return [
        event
        for event in result.injected_events
        if "entity_key" in event.context
    ]


def _oracle(goal: str, views: list[dict[str, Any]]) -> tuple[Any, Any, Any] | None:
    """Test-only oracle (P2/P3): resolve the goal's entity key using ONLY the
    neutral planner views. Returns the unique location, or None when the key
    does not resolve to exactly one candidate."""

    match = _KEY_RE.search(goal)
    assert match is not None, f"goal names no entity key: {goal!r}"
    key = match.group(0)
    hits = [
        view
        for view in views
        if view["event"]["context"].get("entity_key") == key
    ]
    if len(hits) != 1:
        return None
    context = hits[0]["event"]["context"]
    return (context["x"], context["y"], context["z"])


# --- P1: simultaneous truth ---------------------------------------------------


async def test_p1_simultaneous_truth_across_seeds_and_levels(tmp_path) -> None:
    for seed in (42, 43, 44):
        for count in (0, 5, 20, 50):
            result = await _run_v2(
                NoMemoryBackend(),
                seed=seed,
                distractor_count=count,
                episode_id=f"ep-p1-{seed}-{count}",
            )
            candidates = _candidate_events(result)
            assert len(candidates) == 1 + count

            keys = [event.context["entity_key"] for event in candidates]
            assert len(set(keys)) == len(keys)  # keys unique
            coords = [
                (e.context["x"], e.context["y"], e.context["z"]) for e in candidates
            ]
            assert len(set(coords)) == len(coords)  # coordinates unique

            # One location per key: no key ever maps to two locations.
            by_key: dict[str, set] = {}
            for event in candidates:
                by_key.setdefault(event.context["entity_key"], set()).add(
                    (event.context["x"], event.context["y"], event.context["z"])
                )
            assert all(len(locations) == 1 for locations in by_key.values())

            # Common neutral schema/actor/type; value types match.
            for event in candidates:
                assert event.actor == "scenario-instructor"
                assert event.event_type is EventType.LOCATION_DISCOVERED
                assert set(event.context) == {"entity_key", "x", "y", "z"}
                assert isinstance(event.context["entity_key"], str)
                assert all(
                    isinstance(event.context[axis], float)
                    for axis in ("x", "y", "z")
                )
                rendered = json.dumps(event.context).lower()
                assert not any(token in rendered for token in _BANNED_TOKENS)

            # Distractor keys are one-character mutations of the target key.
            target_key = result.evaluation_ground_truth.target_entity_key
            for key in keys[1:]:
                assert key != target_key
                assert len(key) == len(target_key)
                differences = sum(a != b for a, b in zip(key, target_key))
                assert differences == 1


def test_p1_key_generators_are_deterministic_and_mutation_shaped() -> None:
    key = target_entity_key(42)
    assert key == target_entity_key(42)
    assert key != target_entity_key(43)
    assert _KEY_RE.fullmatch(key)
    first_five = distractor_entity_keys(key, 5)
    assert first_five == distractor_entity_keys(key, 5)
    # Count-independent prefix: the first 5 of 50 equal the 5-of-5 request.
    assert distractor_entity_keys(key, 50)[:5] == first_five
    assert len(set(distractor_entity_keys(key, 50))) == 50


# --- P2: unique planner-visible derivation ------------------------------------


async def test_p2_oracle_uniquely_resolves_the_declared_target(tmp_path) -> None:
    for seed in (42, 43, 44):
        result = await _run_v2(
            VectorMemoryBackend(str(tmp_path / f"p2-{seed}.db")),
            seed=seed,
            distractor_count=20,
            episode_id=f"ep-p2-{seed}",
        )
        assert result.run_log is not None
        step0_items = result.run_log.steps[0].retrieved_items
        views = [memory_view_for_prompt(item) for item in step0_items]
        answer = _oracle(result.run_log.goal, views)
        assert answer is not None

        # The oracle's location is exactly the declared target's location.
        ground_truth = result.evaluation_ground_truth
        target = next(
            item for item in step0_items
            if item.event.event_id == ground_truth.target_event_id
        )
        assert answer == (
            target.event.context["x"],
            target.event.context["y"],
            target.event.context["z"],
        )
        # The goal names the target key and no coordinates.
        assert ground_truth.target_entity_key in result.run_log.goal
        assert "initial briefing" in result.run_log.goal


# --- P3: no hidden cue ---------------------------------------------------------


async def test_p3_oracle_invariant_to_order_and_free_of_bookkeeping(tmp_path) -> None:
    result = await _run_v2(
        VectorMemoryBackend(str(tmp_path / "p3.db")),
        seed=42,
        distractor_count=20,
        episode_id="ep-p3",
    )
    assert result.run_log is not None
    views = [
        memory_view_for_prompt(item)
        for item in result.run_log.steps[0].retrieved_items
    ]
    answer = _oracle(result.run_log.goal, views)
    assert answer is not None

    # Permutations/reversals never change the answer (order is not the cue).
    for permutation_seed in (0, 1, 2):
        shuffled = list(views)
        random.Random(permutation_seed).shuffle(shuffled)
        assert _oracle(result.run_log.goal, shuffled) == answer
    assert _oracle(result.run_log.goal, list(reversed(views))) == answer

    # Timestamps are not the cue either (A-REVIEW-011 M-1): deep-copy the
    # exact neutral views and overwrite every timestamp with distinct,
    # adversarially ordered values — the oracle answer must not move.
    mutated = copy.deepcopy(views)
    adversarial = ["2099-01-01T00:00:00+00:00", "1970-01-01T00:00:00+00:00"]
    for index, view in enumerate(mutated):
        # Distinct per-view values, newest-first order (anti-chronological).
        year = 2099 - index
        view["event"]["timestamp"] = f"{year}-06-15T12:00:00+00:00"
    mutated[0]["event"]["timestamp"] = adversarial[0]
    if len(mutated) > 1:
        mutated[1]["event"]["timestamp"] = adversarial[1]
    assert len({v["event"]["timestamp"] for v in mutated}) == len(mutated)
    assert _oracle(result.run_log.goal, mutated) == answer

    # The views carry no bookkeeping fields the oracle could exploit.
    for view in views:
        assert set(view) == {"event"}
        assert set(view["event"]) == {
            "actor",
            "target",
            "event_type",
            "location",
            "context",
            "outcome",
            "timestamp",
        }
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


async def test_p3_target_key_independent_of_distractor_count(tmp_path) -> None:
    """The target key is generated before/independently of distractors."""

    results = [
        await _run_v2(
            NoMemoryBackend(),
            seed=42,
            distractor_count=count,
            episode_id=f"ep-key-{count}",
        )
        for count in (0, 5, 50)
    ]
    keys = {r.evaluation_ground_truth.target_entity_key for r in results}
    assert keys == {target_entity_key(42)}


# --- P4: independent metric re-derivation --------------------------------------


async def test_p4_metrics_rederive_exactly_from_result_json(tmp_path) -> None:
    """Rank-1 (vector) and empty-retrieval (none) cases, re-derived from the
    serialized ScenarioResult alone."""

    vector_result = await _run_v2(
        VectorMemoryBackend(str(tmp_path / "p4.db")),
        seed=42,
        distractor_count=20,
        episode_id="ep-p4-vector",
    )
    none_result = await _run_v2(
        NoMemoryBackend(), seed=42, distractor_count=20, episode_id="ep-p4-none"
    )

    for result in (vector_result, none_result):
        restored = ScenarioResult.model_validate_json(result.to_json())
        ground_truth = restored.evaluation_ground_truth
        assert ground_truth is not None
        assert ground_truth.semantics_version == "entity_key_v2"
        assert ground_truth.target_entity_key
        step0_items = restored.run_log.steps[0].retrieved_items
        recomputed = compute_entity_key_metrics(
            step0_items,
            ground_truth.target_event_id,
            ground_truth.distractor_event_ids,
        )
        for key, value in recomputed.items():
            assert restored.metrics[key] == value
        # v2 legacy-compat keys: recall mirrors target_recall, wrong/legacy
        # precision are N/A — true off-target entities are never "wrong".
        assert restored.metrics["recall_accuracy"] == recomputed["target_recall"]
        assert restored.metrics["wrong_fact_rate"] is None
        assert restored.metrics["retrieval_precision"] is None

    # The vector run really is the rank-1 case; none is the measured miss.
    assert vector_result.metrics["fact_retrieval_rank"] == 1
    assert vector_result.metrics["target_recall"] == 1
    assert none_result.metrics["fact_retrieval_rank"] is None
    assert none_result.metrics["target_recall"] == 0
    assert none_result.metrics["target_retrieval_precision"] is None
    assert none_result.metrics["off_target_retrieval_rate"] is None


def _snapshot(event_id: str, entity_key: str) -> MemoryItemSnapshot:
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


def test_p4_metric_math_target_below_off_target_and_absent() -> None:
    distractors = [f"d{i}" for i in range(3)]

    # Target below off-target items: rank reflects the true position.
    items = [_snapshot("d0", "cache-00000000"), _snapshot("t", "cache-11111111")]
    metrics = compute_entity_key_metrics(items, "t", distractors)
    assert metrics["fact_retrieval_rank"] == 2
    assert metrics["target_recall"] == 1
    assert metrics["target_retrieval_precision"] == 0.5
    assert metrics["off_target_retrieval_rate"] == 0.5

    # Target absent, only off-target entities: measured miss, not N/A.
    items = [_snapshot("d1", "cache-00000001"), _snapshot("d2", "cache-00000002")]
    metrics = compute_entity_key_metrics(items, "t", distractors)
    assert metrics["fact_retrieval_rank"] is None
    assert metrics["target_recall"] == 0
    assert metrics["target_retrieval_precision"] == 0.0
    assert metrics["off_target_retrieval_rate"] == 1.0

    # Unknown ids are neither target nor off-target.
    items = [_snapshot("mystery", "cache-99999999")]
    metrics = compute_entity_key_metrics(items, "t", distractors)
    assert metrics["target_recall"] == 0
    assert metrics["off_target_retrieval_rate"] == 0.0


# --- legacy separation ----------------------------------------------------------


async def test_legacy_result_json_without_ground_truth_still_loads(tmp_path) -> None:
    """Old result files (no evaluation_ground_truth key) validate to None,
    and legacy runs keep the legacy goal text, event semantics, and metrics
    unchanged."""

    scenario = DelayedRecallScenario()
    assert scenario.params["recall_semantics_version"] == "legacy"
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
        episode_id="ep-legacy",
    )
    result = await scenario.run(ctx)
    assert result.evaluation_ground_truth is None
    assert result.run_log is not None
    assert result.run_log.goal == (
        "Return to the target chest you learned about at the start of this episode."
    )
    assert "target_recall" not in result.metrics
    assert "off_target_retrieval_rate" not in result.metrics

    payload = json.loads(result.to_json())
    payload.pop("evaluation_ground_truth")
    restored = ScenarioResult.model_validate(payload)
    assert restored.evaluation_ground_truth is None
    assert restored.metrics == result.metrics


# --- A-REVIEW-011 H-1: legacy Controlled identity derivation --------------------


async def _run_legacy_controlled(memory, *, seed: int, episode_id: str):
    scenario = DelayedRecallScenario()  # legacy defaults
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


async def test_legacy_controlled_identity_keeps_pre_task011_derivation(tmp_path) -> None:
    """A legacy Controlled run's experience event id/timestamp must equal
    `controlled_event_identity` over the TWO pre-existing difficulty params
    (no version key); the v2 id derives from the full versioned params and is
    distinct, while the logical timestamp is unchanged."""

    legacy = await _run_legacy_controlled(
        NoMemoryBackend(), seed=42, episode_id="ep-id-legacy"
    )
    legacy_experience = legacy.injected_events[0]
    expected_id, expected_ts = controlled_event_identity(
        seed=42,
        params={"interference_count": 10, "similar_distractor_count": 0},
        phase="experience",
        ordinal=0,
    )
    assert legacy_experience.event_id == expected_id
    assert legacy_experience.timestamp == expected_ts

    v2 = await _run_v2(
        NoMemoryBackend(), seed=42, distractor_count=0, episode_id="ep-id-v2"
    )
    v2_experience = v2.injected_events[0]
    v2_expected_id, v2_expected_ts = controlled_event_identity(
        seed=42,
        params={
            "interference_count": 10,
            "similar_distractor_count": 0,
            "recall_semantics_version": "entity_key_v2",
        },
        phase="experience",
        ordinal=0,
    )
    assert v2_experience.event_id == v2_expected_id
    assert v2_experience.event_id != expected_id  # versioned namespace
    assert v2_experience.timestamp == expected_ts  # logical clock unchanged
