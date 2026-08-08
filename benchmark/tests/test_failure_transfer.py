"""Scenario E hermetic tests: FailureTransferScenario with FakeBotClient + a
tool-aware fake LLM (no network).

The fake LLM mirrors a memory-driven planner: it prepares the required tool
when the tool-requirement fact is retrieved, navigates to the remembered
location, and otherwise waits. Nothing in the scenario tells it to prepare the
tool — adaptation must emerge from the retrieved memories.
"""

from __future__ import annotations

import json

from minemembench.agent.llm_provider import LLMProvider, LLMResponse
from minemembench.core.models import ExperienceEvent
from minemembench.core.runner import AgentRunner
from minemembench.memory.base import MemoryBackend, MemoryItem, MemoryQuery, MemoryStats
from minemembench.memory.vector_memory import VectorMemoryBackend
from minemembench.scenarios.base import ScenarioContext
from minemembench.scenarios.failure_transfer import (
    FIRST_GOAL,
    REQUIRED_TOOL,
    FailureTransferScenario,
)
from minemembench.scenarios.registry import available_scenarios

from .conftest import FakeBotClient, make_settings

_MEMORY_MARKER = "Retrieved long-term memories (JSON):\n"
_TRANSCRIPT_MARKER = "Recent actions this episode (JSON, most recent last):\n"


def _parse_section(content: str, marker: str):
    start = content.find(marker)
    if start == -1:
        return None
    body = content[start + len(marker):]
    for next_marker in (_MEMORY_MARKER, _TRANSCRIPT_MARKER):
        if next_marker == marker:
            continue
        index = body.find(next_marker)
        if index != -1:
            body = body[:index]
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _first_coords(items: list[dict]):
    for item in items:
        context = item.get("event", {}).get("context", {})
        if "x" in context and "y" in context and "z" in context:
            return (float(context["x"]), float(context["y"]), float(context["z"]))
    return None


class TransferSmartFakeLLM(LLMProvider):
    """Equips the remembered tool, then moves to the remembered location.

    Deterministic from the planner's message alone: with no tool fact in the
    retrieved memories it waits (mirroring a memory-less planner).
    """

    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    @property
    def model(self) -> str:
        return "transfer-fake"

    @property
    def temperature(self) -> float:
        return 0.0

    async def chat(
        self, messages: list[dict[str, str]], *, max_tokens: int = 2048
    ) -> LLMResponse:
        self.calls.append(messages)
        content = messages[-1]["content"]
        memories = _parse_section(content, _MEMORY_MARKER) or []
        transcript = _parse_section(content, _TRANSCRIPT_MARKER) or []
        has_tool = REQUIRED_TOOL in json.dumps(memories)
        equipped = any(entry.get("action") == "equip_item" for entry in transcript)
        coords = _first_coords(memories)

        if not has_tool:
            action = {
                "action": "wait",
                "arguments": {"seconds": 1},
                "reason": "no remembered facts to act on",
            }
        elif not equipped:
            action = {
                "action": "equip_item",
                "arguments": {"item": REQUIRED_TOOL},
                "reason": "preparing the tool remembered from the failed attempt",
            }
        elif coords is not None:
            action = {
                "action": "move_to",
                "arguments": {"x": coords[0], "y": coords[1], "z": coords[2]},
                "reason": "navigating to the remembered goal location",
            }
        else:
            action = {
                "action": "wait",
                "arguments": {"seconds": 1},
                "reason": "no goal coordinates remembered",
            }
        return LLMResponse(
            content=json.dumps(action),
            prompt_tokens=10,
            completion_tokens=5,
            latency_s=0.01,
            model=self.model,
        )


class EmptyMemoryBackend(MemoryBackend):
    """Fake backend that never returns anything: the no-adaptation control."""

    async def add(self, event: ExperienceEvent) -> None:
        pass

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        return []

    async def update(self, event: ExperienceEvent) -> None:
        pass

    async def reset(self, episode_id: str) -> None:
        pass

    async def stats(self) -> MemoryStats:
        return MemoryStats(backend="empty", item_count=0)


async def _run_scenario(
    memory,
    seed: int = 42,
    episode_id: str = "ep-failure-transfer",
    llm: TransferSmartFakeLLM | None = None,
    **params,
):
    llm = llm or TransferSmartFakeLLM()
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
    scenario = FailureTransferScenario()
    scenario.apply_params(params)
    return await scenario.run(ctx)


async def test_vector_transfers_tool_preparation(tmp_path) -> None:
    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    result = await _run_scenario(memory)

    assert result.scenario == "failure_transfer"
    assert result.memory_backend == "vector"
    assert result.success is True
    assert result.metrics["attempt_1_success"] == 0
    assert result.metrics["attempt_1_prepared"] == 0
    assert result.metrics["adaptation_success"] == 1
    assert result.metrics["preparation_rate"] == 1.0
    assert result.metrics["failure_repetition_rate"] == 0.0
    assert result.metrics["transfer_success_rate"] == 1.0
    assert result.params == {"transfer_count": 2, "noise_fact_count": 5}


async def test_first_attempt_goal_has_no_coordinates(tmp_path) -> None:
    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    result = await _run_scenario(memory)
    assert "coordinates" not in FIRST_GOAL and "x=" not in FIRST_GOAL
    assert result.run_log is not None
    assert "coordinates" not in result.run_log.goal and "x=" not in result.run_log.goal


async def test_no_memories_means_no_adaptation() -> None:
    result = await _run_scenario(EmptyMemoryBackend())

    assert result.success is False
    assert result.metrics["adaptation_success"] == 0
    assert result.metrics["preparation_rate"] == 0.0
    assert result.metrics["failure_repetition_rate"] == 1.0
    assert result.metrics["transfer_success_rate"] == 0.0


async def test_multiple_transfer_tasks_aggregate(tmp_path) -> None:
    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    result = await _run_scenario(memory, transfer_count=4)

    assert result.metrics["transfer_tasks"] == 3
    assert result.metrics["preparation_rate"] == 1.0
    assert result.metrics["transfer_success_rate"] == 1.0


async def test_deterministic_across_runs(tmp_path) -> None:
    first = await _run_scenario(VectorMemoryBackend(str(tmp_path / "a.db")))
    second = await _run_scenario(VectorMemoryBackend(str(tmp_path / "b.db")))
    deterministic_keys = (
        "attempt_1_success",
        "adaptation_success",
        "preparation_rate",
        "failure_repetition_rate",
        "transfer_success_rate",
        "llm_calls",
        "total_prompt_tokens",
        "total_completion_tokens",
    )
    for key in deterministic_keys:
        assert first.metrics[key] == second.metrics[key]


def test_scenario_registry_lists_failure_transfer() -> None:
    assert "failure_transfer" in available_scenarios()
