from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from minemembench.core.fairness import CAMPAIGN_MODE_CONTROLLED
from minemembench.core.models import (
    ActionResult,
    ActionStatus,
    BotMode,
    EntityKind,
    Equipped,
    ExperienceEvent,
    HeldItem,
    InventoryItem,
    NearbyEntity,
    Position,
    WorldState,
)
from minemembench.core.runner import AgentRunner
from minemembench.memory.base import (
    EventRecordingBackend,
    MemoryBackend,
    MemoryItem,
    MemoryQuery,
    MemoryStats,
)
from minemembench.scenarios.base import ScenarioContext, ScenarioParamError, ScenarioResult
from minemembench.scenarios.failure_learning import ObservedPreconditionError
from minemembench.scenarios.failure_learning_multi import (
    FAILURE_FAMILIES,
    FailureLearningMultiScenario,
    compute_multi_failure_retrieval_metrics,
    failure_applicability_plan,
    source_transfer_entities_multi,
)

from .conftest import FakeLLM, make_settings

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_controlled_campaign as campaign  # noqa: E402


def ward_error(entity: str, item: str) -> str:
    return (
        f"{entity.split('_', 1)[0]} ward rejects the attack: "
        f"{item} must be equipped to harm it"
    )


REQUIREMENTS = {
    entity: family.required_item
    for family in FAILURE_FAMILIES
    for entity in (family.source_entity, family.transfer_entity)
}


class FailureMemory(MemoryBackend):
    def __init__(self, backend: str = "failure-list") -> None:
        self.events: list[ExperienceEvent] = []
        self.backend = backend

    async def add(self, event: ExperienceEvent) -> None:
        self.events.append(event)

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        return [
            MemoryItem(
                item_id=event.event_id,
                event=event,
                score=1.0 - index / 100,
                created_at=event.timestamp,
            )
            for index, event in enumerate(self.events[: query.limit])
            if query.episode_id is None or event.episode_id == query.episode_id
        ]

    async def update(self, event: ExperienceEvent) -> None:
        await self.add(event)

    async def reset(self, episode_id: str) -> None:
        self.events = [
            event for event in self.events if event.episode_id != episode_id
        ]

    async def stats(self) -> MemoryStats:
        return MemoryStats(backend=self.backend, item_count=len(self.events))


class HeterogeneousFailureBot:
    def __init__(self, *, source_attacks_succeed: bool = False) -> None:
        self.alive = {
            name: 1011 + index
            for index, name in enumerate(REQUIREMENTS)
        }
        self.equipped: str | None = None
        self.source_attacks_succeed = source_attacks_succeed

    async def get_state(self) -> WorldState:
        return WorldState(
            timestamp=datetime(2026, 8, 9, tzinfo=UTC),
            mode=BotMode.MOCK,
            username="BenchBot",
            health=20,
            food=20,
            saturation=5,
            oxygen=20,
            position=Position(x=0, y=64, z=0),
            yaw=0,
            pitch=0,
            dimension="minecraft:overworld",
            time_of_day=6000,
            is_raining=False,
            experience_level=0,
            inventory=[
                InventoryItem(
                    slot=index,
                    name=item,
                    display_name=item.replace("_", " ").title(),
                    count=1,
                )
                for index, item in enumerate(
                    ("gold_nugget", "iron_ingot", "string")
                )
            ],
            equipped=Equipped(
                hand=(
                    HeldItem(
                        name=self.equipped,
                        display_name=self.equipped.replace("_", " ").title(),
                    )
                    if self.equipped
                    else None
                )
            ),
            nearby_entities=[
                NearbyEntity(
                    id=entity_id,
                    name=name,
                    display_name=name.replace("_", " ").title(),
                    kind=EntityKind.HOSTILE,
                    position=Position(x=3 + index, y=64, z=4),
                    distance=5 + index,
                )
                for index, (name, entity_id) in enumerate(self.alive.items())
            ],
        )

    async def execute(
        self, action: str, arguments: dict, timeout_ms: int = 30000
    ) -> ActionResult:
        del timeout_ms
        status = ActionStatus.COMPLETED
        error = None
        result: dict | None = {}
        if action == "equip_item":
            self.equipped = str(arguments["item"])
            result = {"item": self.equipped}
        elif action == "attack_entity":
            entity_id = arguments.get("entity_id")
            name = arguments.get("name")
            if entity_id is not None:
                name = next(
                    (
                        key
                        for key, value in self.alive.items()
                        if value == entity_id
                    ),
                    None,
                )
            if name not in self.alive:
                status, error, result = (
                    ActionStatus.FAILED,
                    "no matching entity",
                    None,
                )
            elif (
                self.equipped != REQUIREMENTS[str(name)]
                and not self.source_attacks_succeed
            ):
                status, error, result = (
                    ActionStatus.FAILED,
                    ward_error(str(name), REQUIREMENTS[str(name)]),
                    None,
                )
            else:
                del self.alive[str(name)]
                result = {"entity_name": name, "killed": True}
        now = datetime(2026, 8, 9, tzinfo=UTC)
        return ActionResult(
            action_id=uuid.uuid4().hex,
            action=action,
            status=status,
            started_at=now,
            finished_at=now,
            result=result,
            error=error,
            state_after=await self.get_state(),
        )


def llm_action(action: str, arguments: dict, reason: str) -> str:
    return json.dumps(
        {"action": action, "arguments": arguments, "reason": reason}
    )


async def _run_multi(
    observed_failure_count: int,
    *,
    episode_id: str,
    backend: str = "failure-list",
    seed: int = 42,
    transfer_actions: list[str] | None = None,
):
    scenario = FailureLearningMultiScenario()
    scenario.apply_params(
        {
            "failure_semantics_version": (
                "observed_precondition_applicability_v4"
            ),
            "observed_failure_count": observed_failure_count,
            "interference_count": 2,
        }
    )
    source_families, target = failure_applicability_plan(
        seed, observed_failure_count
    )
    if transfer_actions is None:
        transfer_actions = [
            llm_action(
                "equip_item",
                {"item": target.required_item},
                "apply the matching observed environmental precondition",
            ),
            llm_action(
                "attack_entity",
                {"name": target.transfer_entity},
                "attack after preparation",
            ),
            *[
                llm_action("wait", {"seconds": 0.1}, "done")
                for _ in range(3)
            ],
        ]
    llm = FakeLLM(transfer_actions)
    bot = HeterogeneousFailureBot()
    recording = EventRecordingBackend(FailureMemory(backend))
    runner = AgentRunner(bot, recording, llm)
    ctx = ScenarioContext(
        bot=bot,
        memory=recording,
        runner=runner,
        llm=llm,
        settings=make_settings(),
        seed=seed,
        episode_id=episode_id,
        campaign_mode=CAMPAIGN_MODE_CONTROLLED,
    )
    result = await scenario.run(ctx)
    result.injected_events = list(recording.offered_events)
    return result, source_families, target


@pytest.mark.parametrize("observed_failure_count", [2, 3])
def test_v4_plan_has_one_applicable_and_real_heterogeneous_distractors(
    observed_failure_count: int,
) -> None:
    # Family and visible inventory order must not encode the hidden mapping.
    # The mapping is learnable only from the raw failed ActionResult.
    assert tuple(family.required_item for family in FAILURE_FAMILIES) == (
        "iron_ingot",
        "string",
        "gold_nugget",
    )
    assert tuple(family.required_item for family in FAILURE_FAMILIES) != (
        "gold_nugget",
        "iron_ingot",
        "string",
    )
    for seed in range(12):
        sources, target = failure_applicability_plan(
            seed, observed_failure_count
        )
        assert len(sources) == observed_failure_count
        assert len({family.name for family in sources}) == observed_failure_count
        assert sum(family.name == target.name for family in sources) == 1
        assert all(
            family.required_item != target.required_item
            for family in sources
            if family.name != target.name
        )
        names, transfer = source_transfer_entities_multi(
            seed, observed_failure_count
        )
        assert names == tuple(family.source_entity for family in sources)
        assert transfer == target.transfer_entity

    # The preregistered calibration seeds cannot solve applicability by always
    # choosing the first (or always the second) source failure.
    relevant_positions = []
    for seed in (42, 43, 44):
        sources, target = failure_applicability_plan(seed, 2)
        relevant_positions.append(
            next(index for index, family in enumerate(sources) if family.name == target.name)
        )
    assert set(relevant_positions) == {0, 1}


@pytest.mark.asyncio
@pytest.mark.parametrize("observed_failure_count", [2, 3])
@pytest.mark.parametrize("seed", [42, 43, 44])
async def test_v4_uses_real_failures_and_strict_applicable_transfer(
    observed_failure_count: int,
    seed: int,
) -> None:
    result, source_families, target = await _run_multi(
        observed_failure_count,
        episode_id=f"episode-applicability-{observed_failure_count}-{seed}",
        seed=seed,
    )
    assert result.success is True
    assert result.metrics["observed_failure_count"] == observed_failure_count
    assert result.metrics["relevant_source_failure_count"] == 1
    assert result.metrics["irrelevant_source_failure_count"] == (
        observed_failure_count - 1
    )
    assert result.metrics["relevant_failure_recall"] == 1.0
    assert result.metrics["irrelevant_failure_retrieval"] == (
        observed_failure_count - 1
    )
    assert result.metrics["preparation_before_first_attempt"] == 1
    assert result.metrics["wrong_preparation"] == 0
    assert result.run_log is not None
    assert len(result.run_log.steps) == 2
    assert len(result.observed_action_results) == observed_failure_count
    assert all(
        item.status is ActionStatus.FAILED and item.error
        for item in result.observed_action_results
    )
    assert [
        item.error for item in result.observed_action_results
    ] == [
        ward_error(family.source_entity, family.required_item)
        for family in source_families
    ]
    failure_events = [
        event
        for event in result.injected_events
        if event.event_type.value == "task_failed"
    ]
    assert len(failure_events) == observed_failure_count
    assert all(
        "required_item" not in event.context
        and "applicable" not in event.context
        and "next time" not in json.dumps(event.context).lower()
        for event in failure_events
    )
    truth = result.evaluation_ground_truth
    assert truth is not None
    assert (
        truth.semantics_version
        == "observed_precondition_applicability_v4"
    )
    assert truth.transfer_entity == target.transfer_entity
    assert truth.required_item == target.required_item
    assert sum(
        source.applicable_to_transfer for source in truth.source_failures
    ) == 1


@pytest.mark.asyncio
async def test_v4_wrong_family_is_primary_failure_but_recovery_is_separate() -> None:
    _sources, target = failure_applicability_plan(42, 2)
    wrong_item = next(
        family.required_item
        for family in FAILURE_FAMILIES
        if family.name != target.name
    )
    actions = [
        llm_action("equip_item", {"item": wrong_item}, "picked similar failure"),
        llm_action(
            "attack_entity",
            {"name": target.transfer_entity},
            "first transfer attempt",
        ),
        llm_action(
            "equip_item",
            {"item": target.required_item},
            "recover from raw failure",
        ),
        llm_action(
            "attack_entity",
            {"name": target.transfer_entity},
            "recovery attack",
        ),
        llm_action("wait", {"seconds": 0.1}, "done"),
    ]
    result, _source_families, _target = await _run_multi(
        2,
        episode_id="episode-wrong-family",
        transfer_actions=actions,
    )
    assert result.success is False
    assert result.metrics["wrong_preparation"] == 1
    assert result.metrics["failure_repeated"] == 1
    assert result.metrics["transfer_success"] == 0
    assert result.metrics["eventual_recovery_after_failure"] == 1
    assert result.run_log is not None
    assert len(result.run_log.steps) == 4


@pytest.mark.asyncio
async def test_v4_correct_preparation_overwritten_before_attack_is_not_success() -> None:
    _sources, target = failure_applicability_plan(42, 2)
    wrong_item = next(
        family.required_item
        for family in FAILURE_FAMILIES
        if family.name != target.name
    )
    actions = [
        llm_action(
            "equip_item",
            {"item": target.required_item},
            "initially apply matching failure",
        ),
        llm_action(
            "equip_item", {"item": wrong_item}, "overwrite with distractor"
        ),
        llm_action(
            "attack_entity",
            {"name": target.transfer_entity},
            "first transfer attempt with wrong current equipment",
        ),
        llm_action(
            "equip_item",
            {"item": target.required_item},
            "recover after the raw failure",
        ),
        llm_action(
            "attack_entity",
            {"name": target.transfer_entity},
            "recovery attack",
        ),
    ]
    result, _source_families, _target = await _run_multi(
        2,
        episode_id="episode-overwritten-preparation",
        transfer_actions=actions,
    )
    assert result.success is False
    assert result.metrics["preparation_before_first_attempt"] == 0
    assert result.metrics["wrong_preparation"] == 1
    assert result.metrics["failure_repeated"] == 1
    assert result.metrics["transfer_success"] == 0
    assert result.metrics["eventual_recovery_after_failure"] == 1


@pytest.mark.asyncio
async def test_v4_event_and_source_evidence_equal_across_backend_fakes() -> None:
    none_result, _sources, _target = await _run_multi(
        3, episode_id="episode-none", backend="none"
    )
    vector_result, _sources, _target = await _run_multi(
        3, episode_id="episode-vector", backend="vector"
    )
    normalize_events = lambda result: [
        event.model_dump(mode="json", exclude={"episode_id"})
        for event in result.injected_events
    ]
    assert normalize_events(none_result) == normalize_events(vector_result)

    def source_evidence(result):
        return [
            {
                "action": item.action,
                "status": item.status,
                "error": item.error,
                "equipped": (
                    item.state_after.equipped if item.state_after else None
                ),
                "entities": (
                    [
                        (entity.id, entity.name)
                        for entity in item.state_after.nearby_entities
                    ]
                    if item.state_after
                    else []
                ),
            }
            for item in result.observed_action_results
        ]

    assert source_evidence(none_result) == source_evidence(vector_result)


@pytest.mark.asyncio
async def test_v4_fails_closed_if_source_attack_unexpectedly_succeeds() -> None:
    scenario = FailureLearningMultiScenario()
    scenario.apply_params({})
    memory = EventRecordingBackend(FailureMemory())
    llm = FakeLLM([])
    bot = HeterogeneousFailureBot(source_attacks_succeed=True)
    ctx = ScenarioContext(
        bot=bot,
        memory=memory,
        runner=AgentRunner(bot, memory, llm),
        llm=llm,
        settings=make_settings(),
        seed=42,
        episode_id="bad-multi",
        campaign_mode=CAMPAIGN_MODE_CONTROLLED,
    )
    await scenario.setup(ctx)
    with pytest.raises(ObservedPreconditionError):
        await scenario.experience_phase(ctx)
    assert memory.offered_events == []


@pytest.mark.parametrize("count", [1, 4, True])
def test_v4_failure_count_validation(count) -> None:
    scenario = FailureLearningMultiScenario()
    with pytest.raises(ScenarioParamError):
        scenario.apply_params({"observed_failure_count": count})


def test_v4_retrieval_empty_is_measured_miss_not_precision_zero() -> None:
    metrics = compute_multi_failure_retrieval_metrics(
        [], ["relevant"], ["irrelevant"], ["noise"]
    )
    assert metrics["relevant_failure_recall"] == 0.0
    assert metrics["irrelevant_failure_retrieval"] == 0
    assert metrics["failure_retrieval_precision"] is None
    assert metrics["irrelevant_failure_retrieval_rate"] is None
    assert metrics["failure_rank"] is None


def test_old_multi_v3_ground_truth_still_loads() -> None:
    result = ScenarioResult.model_validate(
        {
            "scenario": "failure_learning_multi",
            "episode_id": "historical-v3",
            "seed": 42,
            "memory_backend": "none",
            "success": False,
            "evaluation_ground_truth": {
                "semantics_version": "observed_precondition_multi_v3",
                "task_family": "warded_hostile",
                "source_failure_event_ids": ["a", "b"],
                "source_entities": ["zombie", "skeleton"],
                "transfer_entity": "spider",
                "required_item": "gold_nugget",
                "expected_source_action": "attack_entity",
                "expected_source_status": "failed",
                "expected_source_errors": ["one", "two"],
                "interference_event_ids": [],
            },
        }
    )
    assert result.evaluation_ground_truth is not None
    assert (
        result.evaluation_ground_truth.semantics_version
        == "observed_precondition_multi_v3"
    )


@pytest.mark.asyncio
async def test_v4_campaign_evidence_audits_partition_and_leakage(tmp_path) -> None:
    result, _sources, _target = await _run_multi(
        3, episode_id="campaign-evidence-v4"
    )
    path = tmp_path / "scenario_failure_learning_multi_vector_v4.json"
    payload = result.model_dump(mode="json")
    path.write_text(json.dumps(payload), encoding="utf-8")
    fingerprints, error = campaign._failure_evidence_fingerprints(
        path, expected_failure_count=3
    )
    assert error is None
    assert fingerprints is not None

    broken_partition = json.loads(json.dumps(payload))
    broken_partition["evaluation_ground_truth"][
        "irrelevant_failure_event_ids"
    ] = []
    path.write_text(json.dumps(broken_partition), encoding="utf-8")
    _fingerprints, error = campaign._failure_evidence_fingerprints(
        path, expected_failure_count=3
    )
    assert error is not None and "partition" in error

    leaked = json.loads(json.dumps(payload))
    failure_event = next(
        event
        for event in leaked["injected_events"]
        if event["event_type"] == "task_failed"
    )
    failure_event["context"]["required_item"] = "gold_nugget"
    path.write_text(json.dumps(leaked), encoding="utf-8")
    _fingerprints, error = campaign._failure_evidence_fingerprints(
        path, expected_failure_count=3
    )
    assert error is not None and "leaked" in error
