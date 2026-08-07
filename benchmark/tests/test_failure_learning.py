"""Scenario C hermetic tests: FakeBotClient + SmartFakeLLM, no network.

Exercises the full failure_learning lifecycle in-process against a real
VectorMemoryBackend (tmp_path SQLite) and the NoMemoryBackend baseline.
"""

from __future__ import annotations

from minemembench.core.runner import AgentRunner
from minemembench.memory.base import MemoryQuery
from minemembench.memory.no_memory import NoMemoryBackend
from minemembench.memory.vector_memory import VectorMemoryBackend
from minemembench.scenarios.base import ScenarioContext
from minemembench.scenarios.failure_learning import GOAL, FailureLearningScenario
from minemembench.scenarios.registry import available_scenarios

from .conftest import FakeBotClient, SmartFakeLLM, make_settings


async def _run_scenario(
    memory,
    seed: int = 42,
    episode_id: str = "ep-failure-learning",
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
    return await FailureLearningScenario().run(ctx)


async def test_vector_adapts_from_failure(tmp_path) -> None:
    """The scout debrief makes attempt 2 beeline to the crate."""

    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    result = await _run_scenario(memory)

    assert result.scenario == "failure_learning"
    assert result.episode_id == "ep-failure-learning"
    assert result.seed == 42
    assert result.memory_backend == "vector"
    assert result.success is True
    assert result.metrics["attempt_1_success"] == 0
    assert result.metrics["attempt_2_success"] == 1
    assert result.metrics["adaptation"] == 1
    assert result.metrics["final_distance_to_crate_2"] == 0.0

    assert result.run_log is not None
    assert result.run_log.success is True
    assert result.run_log.goal == GOAL
    assert "coordinates" not in GOAL and "x=" not in GOAL


async def test_no_memory_fails_both_attempts() -> None:
    memory = NoMemoryBackend()
    result = await _run_scenario(memory)

    assert result.memory_backend == "none"
    assert result.success is False
    assert result.metrics["attempt_1_success"] == 0
    assert result.metrics["attempt_2_success"] == 0
    assert result.metrics["adaptation"] == 0
    assert result.metrics["avg_add_latency_ms"] is None
    assert result.metrics["avg_retrieve_latency_ms"] is None


async def test_noise_facts_never_leak_coordinates(tmp_path) -> None:
    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    await _run_scenario(memory)

    items = await memory.retrieve(
        MemoryQuery(
            query_text="world supply crate",
            episode_id="ep-failure-learning",
            limit=20,
        )
    )
    noise_events = [
        item for item in items if item.event.context.get("subject") == "world"
    ]
    assert len(noise_events) == 5
    for item in noise_events:
        rendered = " ".join(str(value) for value in item.event.context.values())
        assert "crate" not in rendered
        assert "supply" not in rendered
        assert "location" not in rendered
        assert item.event.context.get("x") is None


async def test_deterministic_across_runs(tmp_path) -> None:
    first = await _run_scenario(VectorMemoryBackend(str(tmp_path / "a.db")))
    second = await _run_scenario(VectorMemoryBackend(str(tmp_path / "b.db")))
    deterministic_keys = (
        "attempt_1_success",
        "attempt_2_success",
        "adaptation",
        "final_distance_to_crate_1",
        "final_distance_to_crate_2",
        "llm_calls",
        "total_prompt_tokens",
        "total_completion_tokens",
    )
    for key in deterministic_keys:
        assert first.metrics[key] == second.metrics[key]


def test_scenario_registry_lists_failure_learning() -> None:
    assert "failure_learning" in available_scenarios()
