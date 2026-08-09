"""TASK-020 observed_precondition_v2 falsification tests (hermetic).

The tests exercise a real ActionResult-shaped source failure, transfer
behavior, causal retrieval evidence, event-stream equality, leakage guards,
and fail-closed anomalies.  No network, live bot, LLM API, or subprocess is
used.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from minemembench import cli
from minemembench.agent.planner import memory_view_for_prompt
from minemembench.core.models import (
    ActionResult,
    ActionStatus,
    EventType,
    ExperienceEvent,
    HealthResponse,
    HeldItem,
    WorldState,
)
from minemembench.core.runner import AgentRunner, RunStep
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
    ObservedPreconditionGroundTruth,
    ScenarioContext,
    ScenarioParamError,
    ScenarioResult,
)
from minemembench.scenarios.failure_learning import (
    REQUIRED_ITEM,
    SEMANTICS_OBSERVED_PRECONDITION_V2,
    FailureLearningScenario,
    ObservedPreconditionError,
    compute_observed_precondition_metrics,
    compute_transfer_behavior_metrics,
    source_transfer_entities,
)

from .conftest import FakeLLM, make_settings


WARDED_ERROR = (
    "the warded hostile resists the attack: gold_nugget must be equipped "
    "to harm it"
)


def _decision(action: str, arguments: dict[str, Any], reason: str) -> str:
    return json.dumps(
        {"action": action, "arguments": arguments, "reason": reason}
    )


def _transfer_outputs(transfer_entity_id: int) -> list[str]:
    return [
        _decision("equip_item", {"item": REQUIRED_ITEM}, "prepare"),
        _decision(
            "attack_entity", {"entity_id": transfer_entity_id}, "attack target"
        ),
        _decision("wait", {"seconds": 0.1}, "observe"),
        _decision("wait", {"seconds": 0.1}, "finish"),
    ]


class WardedBot:
    """Protocol-shaped fake for the versioned warded-hostiles fixture."""

    def __init__(
        self,
        *,
        source_mode: str = "normal",
        pre_equipped: bool = False,
    ) -> None:
        self.state = cli.warded_hostiles_fixture_state().model_copy(deep=True)
        if pre_equipped:
            self.state.equipped.hand = HeldItem(
                name=REQUIRED_ITEM, display_name="Gold Nugget"
            )
        self.source_mode = source_mode
        self.execute_calls: list[tuple[str, dict[str, Any]]] = []
        self.results: list[ActionResult] = []

    async def get_state(self) -> WorldState:
        return self.state.model_copy(deep=True)

    def _entity_name(self, entity_id: int) -> str:
        return next(e.name for e in self.state.nearby_entities if e.id == entity_id)

    async def execute(
        self, action: str, arguments: dict[str, Any], timeout_ms: int = 30000
    ) -> ActionResult:
        del timeout_ms
        self.execute_calls.append((action, dict(arguments)))
        now = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)
        status = ActionStatus.COMPLETED
        result: dict[str, Any] | None = {}
        error: str | None = None

        if action == "equip_item":
            item = str(arguments["item"])
            if item != REQUIRED_ITEM:
                status = ActionStatus.FAILED
                result = None
                error = f"item not in inventory: {item}"
            else:
                self.state.equipped.hand = HeldItem(
                    name=REQUIRED_ITEM, display_name="Gold Nugget"
                )
                result = {"item": REQUIRED_ITEM, "destination": "hand"}
        elif action == "attack_entity":
            entity_id = int(arguments["entity_id"])
            entity_name = self._entity_name(entity_id)
            if self.state.equipped.hand is None:
                if self.source_mode == "unexpected_success":
                    result = {"entity_name": entity_name, "killed": True}
                    self.state.nearby_entities = [
                        entity for entity in self.state.nearby_entities
                        if entity.id != entity_id
                    ]
                else:
                    status = ActionStatus.FAILED
                    result = None
                    error = None if self.source_mode == "empty_error" else WARDED_ERROR
                    if self.source_mode == "remove_on_failure":
                        self.state.nearby_entities = [
                            entity for entity in self.state.nearby_entities
                            if entity.id != entity_id
                        ]
            else:
                result = {"entity_name": entity_name, "killed": True}
                self.state.nearby_entities = [
                    entity for entity in self.state.nearby_entities
                    if entity.id != entity_id
                ]
        elif action == "wait":
            result = {"waited_seconds": float(arguments["seconds"])}
        else:  # pragma: no cover - a scripted test action is a test defect
            raise AssertionError(f"unexpected action {action!r}")

        action_result = ActionResult(
            action_id=f"fake-{len(self.results)}-{action}",
            action=action,
            status=status,
            started_at=now,
            finished_at=now,
            result=result,
            error=error,
            state_after=await self.get_state(),
        )
        self.results.append(action_result)
        return action_result


class ListBackend(MemoryBackend):
    """Small auditable fake; optionally returns memories only once."""

    def __init__(self, *, first_retrieval_only: bool = False) -> None:
        self.events: list[ExperienceEvent] = []
        self.queries: list[MemoryQuery] = []
        self.first_retrieval_only = first_retrieval_only

    async def add(self, event: ExperienceEvent) -> None:
        self.events.append(event)

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        self.queries.append(query)
        if self.first_retrieval_only and len(self.queries) > 1:
            return []
        events = [
            event for event in self.events
            if query.episode_id is None or event.episode_id == query.episode_id
        ]
        return [
            MemoryItem(
                item_id=event.event_id,
                event=event,
                score=1.0 - index * 0.01,
                created_at=event.timestamp,
            )
            for index, event in enumerate(events[: query.limit])
        ]

    async def update(self, event: ExperienceEvent) -> None:
        self.events = [old for old in self.events if old.event_id != event.event_id]
        self.events.append(event)

    async def reset(self, episode_id: str) -> None:
        self.events = [event for event in self.events if event.episode_id != episode_id]

    async def stats(self) -> MemoryStats:
        return MemoryStats(backend="list-fake", item_count=len(self.events))


async def _run_v2(
    memory: MemoryBackend,
    *,
    seed: int = 42,
    episode_id: str = "ep-v2",
    interference_count: int = 0,
    bot: WardedBot | None = None,
) -> tuple[ScenarioResult, FailureLearningScenario, WardedBot, FakeLLM, EventRecordingBackend]:
    scenario = FailureLearningScenario()
    scenario.apply_params(
        {
            "failure_semantics_version": SEMANTICS_OBSERVED_PRECONDITION_V2,
            "interference_count": interference_count,
        }
    )
    source_name, transfer_name = source_transfer_entities(seed)
    del source_name
    warded = bot or WardedBot()
    state = await warded.get_state()
    transfer_id = next(e.id for e in state.nearby_entities if e.name == transfer_name)
    llm = FakeLLM(_transfer_outputs(transfer_id))
    recording = EventRecordingBackend(memory)
    ctx = ScenarioContext(
        bot=warded,
        memory=recording,
        runner=AgentRunner(warded, recording, llm),
        llm=llm,
        settings=make_settings(),
        seed=seed,
        episode_id=episode_id,
        campaign_mode="controlled",
    )
    result = await scenario.run(ctx)
    result.injected_events = list(recording.offered_events)
    return result, scenario, warded, llm, recording


def _snapshot(event_id: str) -> MemoryItemSnapshot:
    event = ExperienceEvent(
        event_id=event_id,
        episode_id="ep",
        timestamp=datetime(2026, 8, 8, tzinfo=UTC),
        actor="test",
        event_type=EventType.WORLD_FACT_UPDATED,
    )
    return MemoryItemSnapshot(
        item_id=event_id,
        event=event,
        score=1.0,
        created_at=event.timestamp,
    )


def _step(
    index: int,
    action: str,
    arguments: dict[str, Any],
    status: ActionStatus,
) -> RunStep:
    return RunStep(
        index=index,
        position=cli.canonical_fixture_state().position,
        retrieved_memory_count=0,
        action=action,
        arguments=arguments,
        reason="test",
        action_status=status,
        prompt_tokens=0,
        completion_tokens=0,
        latency_s=0.0,
    )


def _normalized_stream(result: ScenarioResult) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for event in result.injected_events:
        payload = event.model_dump(mode="json")
        payload["episode_id"] = "<episode>"
        normalized.append(payload)
    return normalized


def test_defaults_versions_entities_and_old_json_compatibility() -> None:
    scenario = FailureLearningScenario()
    assert scenario.params == {
        "failure_semantics_version": "legacy",
        "interference_count": 0,
    }
    assert source_transfer_entities(42) == ("zombie", "skeleton")
    assert source_transfer_entities(43) == ("skeleton", "zombie")
    assert source_transfer_entities(44) == ("zombie", "skeleton")
    with pytest.raises(ScenarioParamError):
        scenario.apply_params({"failure_semantics_version": "unknown"})
    with pytest.raises(ScenarioParamError):
        scenario.apply_params({"interference_count": -1})

    restored = ScenarioResult.model_validate(
        {
            "scenario": "failure_learning",
            "episode_id": "old",
            "seed": 1,
            "memory_backend": "none",
            "success": False,
        }
    )
    assert restored.observed_action_results == []
    assert restored.evaluation_ground_truth is None


async def test_controlled_legacy_fails_before_side_effects() -> None:
    scenario = FailureLearningScenario()
    bot = WardedBot()
    memory = EventRecordingBackend(NoMemoryBackend())
    llm = FakeLLM([])
    ctx = ScenarioContext(
        bot=bot,
        memory=memory,
        runner=AgentRunner(bot, memory, llm),
        llm=llm,
        settings=make_settings(),
        seed=42,
        episode_id="gate",
        campaign_mode="controlled",
    )
    with pytest.raises(ScenarioParamError, match="observed_precondition_v2"):
        await scenario.run(ctx)
    assert bot.execute_calls == []
    assert memory.offered_events == []
    assert llm.calls == []


async def test_fixture_fingerprint_accepts_only_selected_visible_world() -> None:
    health = HealthResponse(
        status="ok", mode="mock", connected=True, username="BenchBot", uptime_s=1
    )
    warded = WardedBot()
    identity = await cli._assert_controlled_fixture(
        warded, health, cli.CONTROLLED_WARDED_FIXTURE_SELECTOR
    )
    assert identity == cli.CONTROLLED_WARDED_FIXTURE_IDENTITY

    warded.state.inventory.pop()
    with pytest.raises(Exception, match="warded_hostiles_v1"):
        await cli._assert_controlled_fixture(
            warded, health, cli.CONTROLLED_WARDED_FIXTURE_SELECTOR
        )


async def test_end_to_end_source_evidence_event_and_transfer_metrics(tmp_path) -> None:
    result, scenario, bot, llm, _recording = await _run_v2(
        VectorMemoryBackend(str(tmp_path / "v2.db")), interference_count=2
    )
    assert result.success is True
    assert result.params == {
        "failure_semantics_version": SEMANTICS_OBSERVED_PRECONDITION_V2,
        "interference_count": 2,
    }
    assert scenario.source_entity != scenario.transfer_entity
    assert result.run_log is not None
    assert scenario.transfer_entity in result.run_log.goal
    assert scenario.source_entity not in result.run_log.goal
    goal = result.run_log.goal.lower()
    assert "gold_nugget" not in goal
    assert "equip" not in goal
    assert WARDED_ERROR.lower() not in goal

    failures = [
        event for event in result.injected_events
        if event.event_type is EventType.TASK_FAILED
    ]
    assert len(failures) == 1
    assert len(result.injected_events) == 3
    raw = result.observed_action_results
    assert len(raw) == 1
    assert raw[0] == bot.results[0]
    assert raw[0].status is ActionStatus.FAILED
    assert raw[0].result is None
    assert raw[0].error == WARDED_ERROR
    assert failures[0].context == {
        "task_family": "warded_hostile",
        "entity": scenario.source_entity,
        "action": "attack_entity",
        "status": "failed",
        "error": WARDED_ERROR,
        "equipped_before": None,
    }
    assert all(
        event.event_type is not EventType.TASK_FAILED
        for event in result.injected_events[1:]
    )
    assert any(
        entity.name == scenario.source_entity
        for entity in (await bot.get_state()).nearby_entities
    )

    truth = result.evaluation_ground_truth
    assert isinstance(truth, ObservedPreconditionGroundTruth)
    assert truth.source_failure_event_id == failures[0].event_id
    assert truth.expected_source_error == raw[0].error
    assert truth.required_item == REQUIRED_ITEM
    assert result.metrics["prepared_before_first_transfer_attack"] == 1
    assert result.metrics["failure_repeated"] == 0
    assert result.metrics["transfer_attack_completed"] == 1
    assert result.metrics["transfer_success"] == 1
    assert result.metrics["retrieval_evidence_source"] == (
        "run_log.steps[0].retrieved_items"
    )
    assert result.run_log.steps[1].action_result == {
        "entity_name": scenario.transfer_entity,
        "killed": True,
    }
    assert result.run_log.steps[1].action_error is None

    # Evaluation ground truth never enters any memory view, query, or prompt.
    forbidden = (
        "source_failure_event_id",
        "expected_source_status",
        "expected_source_error",
        '"required_item"',
    )
    rendered_events = json.dumps(
        [memory_view_for_prompt(item) for item in result.run_log.steps[0].retrieved_items]
    )
    rendered_prompts = json.dumps(llm.calls)
    for token in forbidden:
        assert token not in rendered_events
        assert token not in rendered_prompts


@pytest.mark.parametrize(
    "source_mode,pre_equipped,match",
    [
        ("unexpected_success", False, "must fail"),
        ("empty_error", False, "empty error"),
        ("remove_on_failure", False, "disappeared"),
        ("normal", True, "unequipped"),
    ],
)
async def test_source_failure_anomalies_fail_closed(
    source_mode: str, pre_equipped: bool, match: str
) -> None:
    scenario = FailureLearningScenario()
    scenario.apply_params(
        {"failure_semantics_version": SEMANTICS_OBSERVED_PRECONDITION_V2}
    )
    bot = WardedBot(source_mode=source_mode, pre_equipped=pre_equipped)
    memory = EventRecordingBackend(NoMemoryBackend())
    llm = FakeLLM([])
    ctx = ScenarioContext(
        bot=bot,
        memory=memory,
        runner=AgentRunner(bot, memory, llm),
        llm=llm,
        settings=make_settings(),
        seed=42,
        episode_id=f"bad-{source_mode}",
        campaign_mode="controlled",
    )
    await scenario.setup(ctx)
    with pytest.raises(ObservedPreconditionError, match=match):
        await scenario.experience_phase(ctx)
    assert memory.offered_events == []


@pytest.mark.parametrize("seed", [42, 43, 44])
async def test_event_stream_and_source_evidence_equal_across_backends(
    tmp_path, seed: int
) -> None:
    results: list[ScenarioResult] = []
    source_evidence: list[dict[str, Any]] = []
    for label, backend in (
        ("none", NoMemoryBackend()),
        ("vector", VectorMemoryBackend(str(tmp_path / f"stream-{seed}.db"))),
        ("fake", ListBackend()),
    ):
        result, _scenario, _bot, _llm, _recording = await _run_v2(
            backend,
            seed=seed,
            episode_id=f"ep-{seed}-{label}",
            interference_count=3,
        )
        results.append(result)
        source_evidence.append(
            result.observed_action_results[0].model_dump(mode="json")
        )
    assert _normalized_stream(results[0]) == _normalized_stream(results[1])
    assert _normalized_stream(results[1]) == _normalized_stream(results[2])
    assert source_evidence[0] == source_evidence[1] == source_evidence[2]


async def test_step0_metrics_ignore_flipflop_diagnostic_probe() -> None:
    backend = ListBackend(first_retrieval_only=True)
    result, _scenario, _bot, _llm, _recording = await _run_v2(backend)
    assert result.run_log is not None
    assert result.run_log.steps[0].retrieved_items
    assert result.retrieval_probes[0].items == []
    assert result.metrics["failure_retrieval_rank"] == 1
    assert result.metrics["failure_recall"] == 1
    assert result.metrics["failure_top1"] == 1


def test_retrieval_metric_math_empty_absent_rank_and_unknown_top() -> None:
    assert compute_observed_precondition_metrics([], "f", ["i"] ) == {
        "failure_retrieval_rank": None,
        "failure_recall": 0,
        "failure_retrieval_precision": None,
        "interference_retrieval_rate": None,
        "failure_top1": None,
        "retrieved_item_count": 0,
    }
    rank = compute_observed_precondition_metrics(
        [_snapshot("unknown"), _snapshot("i"), _snapshot("f")], "f", ["i"]
    )
    assert rank["failure_retrieval_rank"] == 3
    assert rank["failure_recall"] == 1
    assert rank["failure_retrieval_precision"] == pytest.approx(1 / 3, abs=1e-4)
    assert rank["interference_retrieval_rate"] == pytest.approx(1 / 3, abs=1e-4)
    assert rank["failure_top1"] is None
    absent = compute_observed_precondition_metrics(
        [_snapshot("i")], "f", ["i"]
    )
    assert absent["failure_recall"] == 0
    assert absent["failure_top1"] == 0


@pytest.mark.parametrize(
    "steps,expected",
    [
        (
            [
                _step(0, "equip_item", {"item": REQUIRED_ITEM}, ActionStatus.COMPLETED),
                _step(1, "attack_entity", {"entity_id": 1002}, ActionStatus.COMPLETED),
            ],
            (1, 0, 1, 1, 0),
        ),
        (
            [
                _step(0, "attack_entity", {"entity_id": 1002}, ActionStatus.FAILED),
                _step(1, "equip_item", {"item": REQUIRED_ITEM}, ActionStatus.COMPLETED),
                _step(2, "attack_entity", {"entity_id": 1002}, ActionStatus.COMPLETED),
            ],
            (0, 1, 1, 0, 1),
        ),
        (
            [
                _step(0, "equip_item", {"item": "stone_sword"}, ActionStatus.COMPLETED),
                _step(1, "attack_entity", {"entity_id": 1002}, ActionStatus.FAILED),
            ],
            (0, 1, 0, 0, 0),
        ),
        (
            [_step(0, "attack_entity", {"entity_id": 1001}, ActionStatus.COMPLETED)],
            (0, 0, 0, 0, 0),
        ),
        (
            [
                _step(0, "equip_item", {"item": REQUIRED_ITEM}, ActionStatus.FAILED),
                _step(1, "attack_entity", {"entity_id": 1002}, ActionStatus.FAILED),
            ],
            (0, 1, 0, 0, 0),
        ),
        (
            [
                _step(0, "equip_item", {"item": REQUIRED_ITEM}, ActionStatus.COMPLETED),
                _step(1, "attack_entity", {"entity_id": 1002}, ActionStatus.FAILED),
            ],
            (1, 0, 0, 0, 0),
        ),
    ],
)
def test_behavior_sequences(steps: list[RunStep], expected: tuple[int, ...]) -> None:
    metrics = compute_transfer_behavior_metrics(
        steps,
        transfer_entity="skeleton",
        transfer_entity_id=1002,
        required_item=REQUIRED_ITEM,
    )
    assert tuple(metrics.values()) == expected


def test_fixture_selection_has_no_backend_input() -> None:
    params = {
        "failure_semantics_version": SEMANTICS_OBSERVED_PRECONDITION_V2,
        "interference_count": 0,
    }
    assert cli.controlled_fixture_spec("failure_learning", params) == (
        cli.CONTROLLED_WARDED_FIXTURE_SELECTOR,
        cli.CONTROLLED_WARDED_FIXTURE_IDENTITY,
    )
    assert cli.controlled_fixture_spec(
        "memory_noise_stress",
        {"noise_semantics_version": "key_retention_v2", "noise_count": 0},
    ) == (cli.CONTROLLED_FIXTURE_SELECTOR, cli.CONTROLLED_FIXTURE_IDENTITY)
