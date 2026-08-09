"""AgentRunner tests with a FakeBotClient — loop semantics, no network."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from minemembench.core.models import (
    ActionResult,
    ActionStatus,
    EventType,
    ExperienceEvent,
    Position,
    WorldState,
)
from minemembench.core.runner import AgentRunner, RunLog
from minemembench.memory.no_memory import NoMemoryBackend
from minemembench.memory.vector_memory import VectorMemoryBackend

from .conftest import FakeLLM, make_world_state


class FakeBotClient:
    """In-memory bot bridge: `move_to` teleports, everything else holds still."""

    def __init__(self, start: Position | None = None) -> None:
        self._position = start or Position(x=0.0, y=64.0, z=0.0)
        self.execute_calls: list[tuple[str, dict[str, Any]]] = []

    async def get_state(self) -> WorldState:
        return make_world_state(self._position.x, self._position.y, self._position.z)

    async def execute(
        self, action: str, arguments: dict[str, Any], timeout_ms: int = 30000
    ) -> ActionResult:
        self.execute_calls.append((action, arguments))
        if action == "move_to":
            self._position = Position(
                x=float(arguments["x"]),
                y=float(arguments["y"]),
                z=float(arguments["z"]),
            )
        now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)
        return ActionResult(
            action_id=uuid.uuid4().hex,
            action=action,
            status=ActionStatus.COMPLETED,
            started_at=now,
            finished_at=now,
            result={"position": self._position.model_dump()},
            error=None,
            state_after=await self.get_state(),
        )


def _move_to_output(x: float, y: float, z: float) -> str:
    return json.dumps(
        {"action": "move_to", "arguments": {"x": x, "y": y, "z": z},
         "reason": "heading to the goal"}
    )


WAIT_OUTPUT = json.dumps(
    {"action": "wait", "arguments": {"seconds": 1}, "reason": "holding position"}
)


class RecordingEventCollector:
    """Stub collector recording start/stop calls for the runner integration."""

    def __init__(self, collected: list[ExperienceEvent] | None = None) -> None:
        self._collected = collected or []
        self.start_calls: list[str] = []
        self.stop_calls = 0

    async def start(self, episode_id: str) -> None:
        self.start_calls.append(episode_id)

    async def stop(self) -> list[ExperienceEvent]:
        self.stop_calls += 1
        return self._collected


def _experience(event_id: str, event_type: EventType) -> ExperienceEvent:
    return ExperienceEvent(
        event_id=event_id,
        episode_id="ep-1",
        timestamp=datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC),
        actor="Steve",
        event_type=event_type,
    )


async def test_reaches_success_at_and_stops() -> None:
    llm = FakeLLM([_move_to_output(10, 64, 10)] * 5)  # extra outputs unused
    runner = AgentRunner(FakeBotClient(), NoMemoryBackend(), llm)

    log = await runner.run_goal(
        "go to (10, 64, 10)",
        max_steps=5,
        success_at=Position(x=10.0, y=64.0, z=10.0),
    )

    assert log.success is True
    assert len(log.steps) == 1  # stopped as soon as the goal was reached
    assert log.llm_calls == 1
    assert log.total_prompt_tokens == 10
    assert log.total_completion_tokens == 5
    assert log.memory_backend == "none"
    assert log.model == "fake-model"
    assert log.temperature == 0.0
    assert log.goal == "go to (10, 64, 10)"
    assert log.run_id

    step = log.steps[0]
    assert step.index == 0
    assert step.action == "move_to"
    assert step.arguments == {"x": 10, "y": 64, "z": 10}
    assert step.action_status is ActionStatus.COMPLETED
    assert step.retrieved_memory_count == 0
    assert step.position == Position(x=10.0, y=64.0, z=10.0)
    assert step.reason == "heading to the goal"


async def test_objective_step_predicate_stops_without_post_completion_actions() -> None:
    llm = FakeLLM([WAIT_OUTPUT] * 5)
    bot = FakeBotClient()
    runner = AgentRunner(bot, NoMemoryBackend(), llm)

    log = await runner.run_goal(
        "stop after the first completed wait",
        max_steps=5,
        success_when=lambda step: (
            step.action == "wait"
            and step.action_status is ActionStatus.COMPLETED
        ),
    )

    assert log.success is True
    assert len(log.steps) == 1
    assert log.llm_calls == 1
    assert len(bot.execute_calls) == 1


async def test_success_radius_is_two_blocks() -> None:
    llm = FakeLLM([_move_to_output(11, 64, 10)])  # 1 block away from target
    runner = AgentRunner(FakeBotClient(), NoMemoryBackend(), llm)

    log = await runner.run_goal(
        "close enough", max_steps=5, success_at=Position(x=10.0, y=64.0, z=10.0)
    )

    assert log.success is True


async def test_max_steps_without_reaching_goal() -> None:
    llm = FakeLLM([WAIT_OUTPUT] * 3)
    bot = FakeBotClient()
    runner = AgentRunner(bot, NoMemoryBackend(), llm)

    log = await runner.run_goal(
        "never moving",
        max_steps=3,
        success_at=Position(x=100.0, y=64.0, z=100.0),
    )

    assert log.success is False
    assert len(log.steps) == 3
    assert log.llm_calls == 3
    assert log.total_prompt_tokens == 30
    assert log.total_completion_tokens == 15
    assert len(bot.execute_calls) == 3
    assert [step.index for step in log.steps] == [0, 1, 2]


async def test_run_log_to_json_round_trips() -> None:
    llm = FakeLLM([_move_to_output(10, 64, 10)])
    runner = AgentRunner(FakeBotClient(), NoMemoryBackend(), llm)

    log = await runner.run_goal(
        "serialize me", max_steps=2, success_at=Position(x=10.0, y=64.0, z=10.0)
    )

    parsed = json.loads(log.to_json())
    assert parsed["success"] is True
    assert parsed["memory_backend"] == "none"
    assert parsed["llm_calls"] == 1
    assert parsed["steps"][0]["action"] == "move_to"
    # The JSON must validate back into the same model.
    assert RunLog.model_validate(parsed) == log


async def test_runner_starts_and_stops_event_collector() -> None:
    llm = FakeLLM([_move_to_output(10, 64, 10)])
    collector = RecordingEventCollector(
        [
            _experience("c1", EventType.PLAYER_SHARED_RESOURCE),
            _experience("c2", EventType.PLAYER_ATTACKED_AGENT),
        ]
    )
    runner = AgentRunner(
        FakeBotClient(), NoMemoryBackend(), llm, event_collector=collector
    )

    log = await runner.run_goal(
        "go to (10, 64, 10)",
        max_steps=5,
        success_at=Position(x=10.0, y=64.0, z=10.0),
    )

    assert collector.start_calls == [log.run_id]
    assert collector.stop_calls == 1
    assert log.collected_event_count == 2


async def test_run_log_without_collector_counts_zero() -> None:
    llm = FakeLLM([_move_to_output(10, 64, 10)])
    runner = AgentRunner(FakeBotClient(), NoMemoryBackend(), llm)

    log = await runner.run_goal(
        "go to (10, 64, 10)",
        max_steps=1,
        success_at=Position(x=10.0, y=64.0, z=10.0),
    )

    assert log.collected_event_count == 0


async def test_run_goal_uses_provided_episode_id_for_collector() -> None:
    llm = FakeLLM([_move_to_output(10, 64, 10)])
    collector = RecordingEventCollector([])
    runner = AgentRunner(
        FakeBotClient(), NoMemoryBackend(), llm, event_collector=collector
    )

    await runner.run_goal(
        "go to (10, 64, 10)",
        max_steps=5,
        success_at=Position(x=10.0, y=64.0, z=10.0),
        episode_id="ep-custom",
    )

    assert collector.start_calls == ["ep-custom"]


async def test_run_goal_scopes_planner_memory_to_provided_episode(tmp_path) -> None:
    """A provided episode_id hides other runs' events from the planner.

    The shared db holds one event under episode "ep-1"; a run scoped to
    "ep-2" must retrieve nothing, or the loop would see run 1's event.
    """
    memory = VectorMemoryBackend(str(tmp_path / "shared.db"))
    await memory.add(_experience("e1", EventType.LOCATION_DISCOVERED))

    llm = FakeLLM([WAIT_OUTPUT, WAIT_OUTPUT])
    runner = AgentRunner(FakeBotClient(), memory, llm)

    log = await runner.run_goal("recall the chest", max_steps=2, episode_id="ep-2")

    assert log.run_id != "ep-2"  # run_id is still freshly generated
    assert all(step.retrieved_memory_count == 0 for step in log.steps)
