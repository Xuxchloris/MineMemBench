"""Scenario A hermetic tests: FakeBotClient + SmartFakeLLM, no network.

Exercises the full delayed_recall lifecycle in-process against a real
VectorMemoryBackend (tmp_path SQLite) and the NoMemoryBackend baseline.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from minemembench.agent.llm_provider import LLMProvider, LLMResponse
from minemembench.core.models import ActionResult, ActionStatus, Position, WorldState
from minemembench.core.runner import AgentRunner
from minemembench.memory.base import MemoryQuery
from minemembench.memory.no_memory import NoMemoryBackend
from minemembench.memory.vector_memory import VectorMemoryBackend
from minemembench.scenarios.base import ScenarioContext
from minemembench.scenarios.delayed_recall import GOAL, DelayedRecallScenario
from minemembench.scenarios.registry import available_scenarios

from .conftest import make_settings, make_world_state

#: Spawn position; scenario A offsets the target from here, seeded.
SPAWN = Position(x=0.0, y=64.0, z=0.0)

WAIT_OUTPUT = json.dumps(
    {"action": "wait", "arguments": {"seconds": 1}, "reason": "no coordinates remembered"}
)


class FakeBotClient:
    """In-memory bot bridge: `move_to` teleports, everything else holds still."""

    def __init__(self, start: Position | None = None) -> None:
        self._position = start or Position(x=SPAWN.x, y=SPAWN.y, z=SPAWN.z)
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


class SmartFakeLLM(LLMProvider):
    """Answers move_to to the remembered chest coordinates when present.

    Scans the planner's user message for the retrieved target_chest memory.
    With no such memory it falls back to `wait`, mirroring a memory-less LLM.
    """

    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    @property
    def model(self) -> str:
        return "smart-fake"

    @property
    def temperature(self) -> float:
        return 0.0

    async def chat(
        self, messages: list[dict[str, str]], *, max_tokens: int = 2048
    ) -> LLMResponse:
        self.calls.append(messages)
        coords = _find_chest_coordinates(messages[-1]["content"])
        if coords is None:
            content = WAIT_OUTPUT
        else:
            content = json.dumps(
                {
                    "action": "move_to",
                    "arguments": {"x": coords[0], "y": coords[1], "z": coords[2]},
                    "reason": "returning to the learned target chest",
                }
            )
        return LLMResponse(
            content=content,
            prompt_tokens=10,
            completion_tokens=5,
            latency_s=0.01,
            model=self.model,
        )


def _find_chest_coordinates(user_message: str) -> tuple[float, float, float] | None:
    """Pull target_chest x/y/z out of the planner's memory section, if any."""

    marker = "Retrieved long-term memories (JSON):\n"
    start = user_message.find(marker)
    if start == -1:
        return None
    body = user_message[start + len(marker):]
    try:
        items = json.loads(body)
    except json.JSONDecodeError:
        return None
    for item in items:
        context = item.get("event", {}).get("context", {})
        if context.get("subject") == "target_chest":
            return (
                float(context["x"]),
                float(context["y"]),
                float(context["z"]),
            )
    return None


async def _run_scenario(
    memory,
    seed: int = 42,
    episode_id: str = "ep-delayed-recall",
    llm: SmartFakeLLM | None = None,
):
    llm = llm or SmartFakeLLM()
    settings = make_settings()
    bot = FakeBotClient()
    runner = AgentRunner(bot, memory, llm)
    ctx = ScenarioContext(
        bot=bot,
        memory=memory,
        runner=runner,
        llm=llm,
        settings=settings,
        seed=seed,
        episode_id=episode_id,
    )
    return await DelayedRecallScenario().run(ctx)


async def test_vector_recalls_the_fact_and_succeeds(tmp_path) -> None:
    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    result = await _run_scenario(memory)

    assert result.scenario == "delayed_recall"
    assert result.episode_id == "ep-delayed-recall"
    assert result.seed == 42
    assert result.memory_backend == "vector"
    assert result.success is True
    assert result.metrics["task_success"] == 1
    assert result.metrics["fact_retrieval_rank"] == 1
    assert result.metrics["final_distance_to_target"] == 0.0

    assert result.run_log is not None
    assert result.run_log.success is True
    assert result.run_log.goal == GOAL
    assert "coordinates" not in GOAL and "x=" not in GOAL
    assert len(result.run_log.steps) == 1  # reached the target on the first step

    stats = await memory.stats()
    assert stats.item_count == 11  # 1 chest fact + 10 noise facts


async def test_no_memory_cannot_recall() -> None:
    memory = NoMemoryBackend()
    result = await _run_scenario(memory)

    assert result.memory_backend == "none"
    assert result.success is False
    assert result.metrics["task_success"] == 0
    assert result.metrics["fact_retrieval_rank"] is None
    assert result.metrics["avg_add_latency_ms"] is None
    assert result.metrics["avg_retrieve_latency_ms"] is None

    assert result.run_log is not None
    assert result.run_log.success is False
    assert len(result.run_log.steps) == 3  # waited out the whole budget


async def test_noise_facts_never_leak_the_target(tmp_path) -> None:
    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    await _run_scenario(memory)

    items = await memory.retrieve(
        MemoryQuery(query_text="world", episode_id="ep-delayed-recall", limit=20)
    )
    chest_events = [
        item for item in items if item.event.context.get("subject") == "target_chest"
    ]
    noise_events = [
        item for item in items if item.event.context.get("subject") != "target_chest"
    ]
    assert len(chest_events) == 0  # zero-overlap chest fact is excluded
    assert len(noise_events) == 10
    for item in noise_events:
        rendered = " ".join(str(value) for value in item.event.context.values())
        assert "chest" not in rendered
        assert "target" not in rendered
        assert item.event.context.get("x") is None


async def test_deterministic_across_runs(tmp_path) -> None:
    first = await _run_scenario(VectorMemoryBackend(str(tmp_path / "a.db")))
    second = await _run_scenario(VectorMemoryBackend(str(tmp_path / "b.db")))
    deterministic_keys = (
        "task_success",
        "fact_retrieval_rank",
        "final_distance_to_target",
        "llm_calls",
        "total_prompt_tokens",
        "total_completion_tokens",
    )
    for key in deterministic_keys:
        assert first.metrics[key] == second.metrics[key]
    assert first.metrics["final_distance_to_target"] == 0.0


def test_scenario_registry_lists_delayed_recall() -> None:
    assert "delayed_recall" in available_scenarios()


def _moved_to(result) -> tuple[float, float, float] | None:
    """The coordinates the run's first step moved to, if any."""
    args = result.run_log.steps[0].arguments
    return (float(args["x"]), float(args["y"]), float(args["z"]))


def _all_chest_coordinates(user_message: str) -> list[tuple[float, float, float]]:
    """Every target_chest coordinate present in the planner's memory section."""
    marker = "Retrieved long-term memories (JSON):\n"
    start = user_message.find(marker)
    if start == -1:
        return []
    try:
        items = json.loads(user_message[start + len(marker):])
    except json.JSONDecodeError:
        return []
    coords = []
    for item in items:
        context = item.get("event", {}).get("context", {})
        if context.get("subject") == "target_chest":
            coords.append(
                (
                    float(context["x"]),
                    float(context["y"]),
                    float(context["z"]),
                )
            )
    return coords


async def test_runs_sharing_a_vector_db_are_independent(tmp_path) -> None:
    """Run 2's planner must never see run 1's events in a shared SQLite file.

    Two full scenario runs with different episode ids write into one db; the
    second run's planner prompt must only ever carry its own episode's chest
    fact, never run 1's coordinates.
    """
    memory = VectorMemoryBackend(str(tmp_path / "shared.db"))

    llm1 = SmartFakeLLM()
    result1 = await _run_scenario(memory, seed=42, episode_id="ep-run-1", llm=llm1)
    assert result1.success is True
    target1 = _moved_to(result1)
    assert target1 is not None

    llm2 = SmartFakeLLM()
    result2 = await _run_scenario(memory, seed=7, episode_id="ep-run-2", llm=llm2)
    assert result2.success is True
    target2 = _moved_to(result2)
    assert target2 is not None
    assert target1 != target2  # distinct seeds -> distinct targets

    for messages in llm2.calls:
        assert target1 not in _all_chest_coordinates(messages[-1]["content"])

    run2_prompts = [
        _all_chest_coordinates(messages[-1]["content"]) for messages in llm2.calls
    ]
    assert any(target2 in coords for coords in run2_prompts)
