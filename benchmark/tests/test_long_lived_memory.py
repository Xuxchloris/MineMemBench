from __future__ import annotations

import json
import math
import uuid
from datetime import UTC, datetime

import pytest

from minemembench.core.fairness import CAMPAIGN_MODE_CONTROLLED
from minemembench.core.models import (
    ActionResult,
    ActionStatus,
    BotMode,
    EntityKind,
    ExperienceEvent,
    InventoryItem,
    NearbyEntity,
    NearbyPlayer,
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
from minemembench.memory.no_memory import NoMemoryBackend
from minemembench.scenarios.base import ScenarioContext, ScenarioParamError
from minemembench.scenarios.long_lived_memory import (
    FINAL_GOAL,
    LongLivedMemoryScenario,
)

from .conftest import FakeLLM, make_settings


class ListMemory(MemoryBackend):
    def __init__(self) -> None:
        self.events: list[ExperienceEvent] = []

    async def add(self, event: ExperienceEvent) -> None:
        self.events.append(event)

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        events = [
            event
            for event in self.events
            if query.episode_id is None or event.episode_id == query.episode_id
        ]
        return [
            MemoryItem(
                item_id=event.event_id,
                event=event,
                score=1.0 - index / 1000,
                created_at=event.timestamp,
            )
            for index, event in enumerate(events[: query.limit])
        ]

    async def update(self, event: ExperienceEvent) -> None:
        await self.add(event)

    async def reset(self, episode_id: str) -> None:
        self.events = [event for event in self.events if event.episode_id != episode_id]

    async def stats(self) -> MemoryStats:
        return MemoryStats(backend="list", item_count=len(self.events))


class LifetimeBot:
    def __init__(self) -> None:
        self.position = Position(x=0, y=64, z=0)
        self.token_exists = True
        self.token_inventory = 0
        self.calls: list[tuple[str, dict]] = []

    async def get_state(self) -> WorldState:
        token = Position(x=40, y=64, z=0)
        steve = Position(x=1, y=64, z=2)
        nearby_entities = []
        if self.token_exists and math.dist(
            (self.position.x, self.position.y, self.position.z),
            (token.x, token.y, token.z),
        ) <= 32:
            nearby_entities.append(
                NearbyEntity(
                    id=1005,
                    name="lifetime_token",
                    display_name="Lifetime Token",
                    kind=EntityKind.ITEM,
                    position=token,
                    distance=math.dist(
                        (self.position.x, self.position.y, self.position.z),
                        (token.x, token.y, token.z),
                    ),
                )
            )
        nearby_players = []
        if math.dist(
            (self.position.x, self.position.y, self.position.z),
            (steve.x, steve.y, steve.z),
        ) <= 32:
            nearby_players.append(
                NearbyPlayer(username="Steve", position=steve, distance=0)
            )
        inventory = [
            InventoryItem(slot=0, name="stone", display_name="Stone", count=32)
        ]
        if self.token_inventory:
            inventory.append(
                InventoryItem(
                    slot=1,
                    name="lifetime_token",
                    display_name="Lifetime Token",
                    count=self.token_inventory,
                )
            )
        return WorldState(
            timestamp=datetime(2026, 8, 9, tzinfo=UTC),
            mode=BotMode.MOCK,
            username="BenchBot",
            health=20,
            food=20,
            saturation=5,
            oxygen=20,
            position=self.position,
            yaw=0,
            pitch=0,
            dimension="minecraft:overworld",
            time_of_day=6000,
            is_raining=False,
            experience_level=0,
            inventory=inventory,
            nearby_entities=nearby_entities,
            nearby_players=nearby_players,
        )

    async def execute(
        self, action: str, arguments: dict, timeout_ms: int = 30000
    ) -> ActionResult:
        self.calls.append((action, dict(arguments)))
        status = ActionStatus.COMPLETED
        error = None
        result: dict | None = {}
        if action == "move_to":
            self.position = Position(
                x=float(arguments["x"]),
                y=float(arguments["y"]),
                z=float(arguments["z"]),
            )
            result = {"position": self.position.model_dump()}
        elif action == "collect_item":
            if (
                arguments.get("name") == "lifetime_token"
                and self.token_exists
                and math.dist(
                    (self.position.x, self.position.y, self.position.z),
                    (40, 64, 0),
                )
                <= float(arguments.get("max_distance", 16))
            ):
                self.position = Position(x=40, y=64, z=0)
                self.token_exists = False
                self.token_inventory = 1
                result = {"item_name": "lifetime_token", "collected": True}
            else:
                status = ActionStatus.FAILED
                error = "no dropped item 'lifetime_token' within range"
                result = None
        elif action == "give_item":
            visible = math.dist(
                (self.position.x, self.position.y, self.position.z), (1, 64, 2)
            ) <= 32
            if self.token_inventory and visible:
                self.token_inventory = 0
                result = {"item": "lifetime_token", "count": 1, "target": "Steve"}
            else:
                status = ActionStatus.FAILED
                error = "player not visible: Steve"
                result = None
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


def _outputs(session_count: int, *, solve: bool) -> list[str]:
    move_origin = json.dumps(
        {"action": "move_to", "arguments": {"x": 0, "y": 64, "z": 0}, "reason": "session survey"}
    )
    wait = json.dumps(
        {"action": "wait", "arguments": {"seconds": 0.1}, "reason": "no route evidence"}
    )
    if not solve:
        return [move_origin] * session_count + [wait] * 8
    route = [
        json.dumps({"action": "move_to", "arguments": {"x": 40, "y": 64, "z": 0}, "reason": "use observed cache route"}),
        json.dumps({"action": "collect_item", "arguments": {"name": "lifetime_token"}, "reason": "collect observed resource"}),
        json.dumps({"action": "move_to", "arguments": {"x": 1, "y": 64, "z": 2}, "reason": "return to observed recipient"}),
        json.dumps({"action": "give_item", "arguments": {"username": "Steve", "item": "lifetime_token"}, "reason": "deliver resource"}),
        wait,
        wait,
        wait,
        wait,
    ]
    return [move_origin] * session_count + route


async def _run(
    memory: MemoryBackend,
    *,
    solve: bool = True,
    final_outputs: list[str] | None = None,
):
    scenario = LongLivedMemoryScenario()
    scenario.apply_params(
        {
            "lifetime_event_count": 8,
            "session_count": 2,
            "relevant_update_count": 1,
            "similar_event_count": 2,
            "lifetime_semantics_version": "lifetime_v1",
        }
    )
    bot = LifetimeBot()
    outputs = _outputs(2, solve=solve)
    if final_outputs is not None:
        outputs = outputs[:2] + final_outputs
    llm = FakeLLM(outputs)
    recording = EventRecordingBackend(memory)
    runner = AgentRunner(bot, recording, llm)
    ctx = ScenarioContext(
        bot=bot,
        memory=recording,
        runner=runner,
        llm=llm,
        settings=make_settings(),
        seed=42,
        episode_id="episode-lifetime",
        campaign_mode=CAMPAIGN_MODE_CONTROLLED,
    )
    result = await scenario.run(ctx)
    result.injected_events = list(recording.offered_events)
    result.phase_records = list(ctx.records)
    return scenario, result, llm


@pytest.mark.asyncio
async def test_lifetime_v1_persists_memory_but_resets_each_working_transcript() -> None:
    scenario, result, llm = await _run(ListMemory())
    assert result.success is True
    assert result.metrics["task_success"] == 1
    assert result.metrics["offered_event_count"] == 8
    assert len(result.injected_events) == 8
    assert len(result.run_logs) == 3
    assert [record.run_log.steps[0].index for record in result.run_logs] == [0, 0, 0]
    assert result.run_log == result.run_logs[-1].run_log
    assert len(result.phase_records) == 5
    assert result.metrics["target_recall_first_decision"] == 1
    assert result.metrics["target_route_utilization"] == 1
    assert result.metrics["meaningful_action_count"] == 4
    assert len(result.run_log.steps) == 4
    assert all(step.action != "wait" for step in result.run_log.steps)

    # Calls 0/1 start semantic sessions; call 2 starts the final task. Each
    # AgentRunner call must begin with an empty working transcript.
    for call_index in (0, 1, 2):
        user = llm.calls[call_index][-1]["content"]
        assert "Recent actions this episode (JSON, most recent last):\n[]" in user

    target = result.evaluation_ground_truth
    assert target is not None and target.semantics_version == "lifetime_v1"
    assert target.target_event_id == scenario.target_event_id
    assert "40" not in FINAL_GOAL
    assert all("required_item" not in event.context for event in result.injected_events)
    assert result.observed_action_results[0].state_after is not None
    assert any(
        entity.name == "lifetime_token"
        for entity in result.observed_action_results[0].state_after.nearby_entities
    )


@pytest.mark.asyncio
async def test_lifetime_no_memory_has_no_long_term_retrieval_or_route_success() -> None:
    _scenario, result, _llm = await _run(NoMemoryBackend(), solve=False)
    assert result.success is False
    assert result.metrics["target_recall_first_decision"] == 0
    assert result.metrics["target_route_utilization"] is None
    assert all(
        step.retrieved_items == []
        for labeled in result.run_logs
        for step in labeled.run_log.steps
    )


@pytest.mark.asyncio
async def test_lifetime_recovery_after_invalid_attempts_is_not_primary_success() -> None:
    wait = json.dumps(
        {"action": "wait", "arguments": {"seconds": 0.1}, "reason": "done"}
    )
    recovery = [
        json.dumps({"action": "collect_item", "arguments": {"name": "lifetime_token"}, "reason": "premature collect"}),
        json.dumps({"action": "move_to", "arguments": {"x": 40, "y": 64, "z": 0}, "reason": "approach cache"}),
        json.dumps({"action": "collect_item", "arguments": {"name": "lifetime_token"}, "reason": "recover token"}),
        json.dumps({"action": "give_item", "arguments": {"username": "Steve", "item": "lifetime_token"}, "reason": "premature give"}),
        json.dumps({"action": "move_to", "arguments": {"x": 1, "y": 64, "z": 2}, "reason": "return"}),
        json.dumps({"action": "give_item", "arguments": {"username": "Steve", "item": "lifetime_token"}, "reason": "recover delivery"}),
        wait,
        wait,
    ]
    _scenario, result, _llm = await _run(
        ListMemory(), final_outputs=recovery
    )
    assert result.success is False
    assert result.metrics["task_success"] == 0
    assert result.metrics["invalid_collect_attempt"] == 1
    assert result.metrics["invalid_give_attempt"] == 1
    assert result.metrics["eventual_recovery_after_invalid_attempt"] == 1
    assert result.metrics["collect_completed"] == 1
    assert result.metrics["delivery_completed"] == 1
    assert len(result.run_log.steps) == 6


@pytest.mark.parametrize(
    "params",
    [
        {"lifetime_event_count": 1},
        {"session_count": 0},
        {"lifetime_event_count": 3, "session_count": 3},
        {"lifetime_event_count": 4, "relevant_update_count": 2, "similar_event_count": 2},
        {"lifetime_semantics_version": "legacy"},
    ],
)
def test_lifetime_params_fail_closed(params: dict) -> None:
    scenario = LongLivedMemoryScenario()
    with pytest.raises(ScenarioParamError):
        scenario.apply_params(params)


@pytest.mark.asyncio
async def test_lifetime_controlled_event_stream_is_deterministic_across_backends() -> None:
    _scenario_a, a, _llm_a = await _run(ListMemory())
    _scenario_b, b, _llm_b = await _run(ListMemory())
    normalize = lambda result: [
        event.model_dump(mode="json", exclude={"episode_id"})
        for event in result.injected_events
    ]
    assert normalize(a) == normalize(b)
