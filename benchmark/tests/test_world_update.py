"""Scenario B hermetic tests: FakeBotClient + SmartFakeLLM, no network.

Exercises the full world_update lifecycle in-process against a real
VectorMemoryBackend (tmp_path SQLite) and the NoMemoryBackend baseline.
"""

from __future__ import annotations

from minemembench.core.runner import AgentRunner
from minemembench.memory.base import MemoryQuery
from minemembench.memory.no_memory import NoMemoryBackend
from minemembench.memory.vector_memory import VectorMemoryBackend
from minemembench.scenarios.base import ScenarioContext
from minemembench.scenarios.registry import available_scenarios
from minemembench.scenarios.world_update import GOAL, WorldUpdateScenario

from .conftest import FakeBotClient, SmartFakeLLM, make_settings


async def _run_scenario(
    memory,
    seed: int = 42,
    episode_id: str = "ep-world-update",
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
    return await WorldUpdateScenario().run(ctx)


async def test_vector_naive_baseline_uses_stale_fact(tmp_path) -> None:
    """The vector baseline returns the stale fact first on ties (documented)."""

    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    result = await _run_scenario(memory)

    assert result.scenario == "world_update"
    assert result.episode_id == "ep-world-update"
    assert result.seed == 42
    assert result.memory_backend == "vector"
    assert result.success is False
    assert result.metrics["task_success"] == 0
    assert result.metrics["current_fact_accuracy"] == 0
    assert result.metrics["stale_action"] == 1
    assert result.metrics["final_distance_to_b"] > 0.0

    assert result.run_log is not None
    assert result.run_log.success is False
    assert result.run_log.goal == GOAL
    assert "coordinates" not in GOAL and "x=" not in GOAL


async def test_no_memory_retrieves_nothing() -> None:
    memory = NoMemoryBackend()
    result = await _run_scenario(memory)

    assert result.memory_backend == "none"
    assert result.success is False
    assert result.metrics["task_success"] == 0
    assert result.metrics["current_fact_accuracy"] is None
    assert result.metrics["stale_action"] == 0
    assert result.metrics["avg_add_latency_ms"] is None
    assert result.metrics["avg_retrieve_latency_ms"] is None

    assert result.run_log is not None
    assert result.run_log.success is False
    assert len(result.run_log.steps) == 3  # waited out the whole budget


async def test_noise_facts_never_leak_coordinates(tmp_path) -> None:
    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    await _run_scenario(memory)

    items = await memory.retrieve(
        MemoryQuery(
            query_text="world supply cache",
            episode_id="ep-world-update",
            limit=20,
        )
    )
    cache_events = [
        item for item in items if item.event.context.get("subject") == "supply_cache"
    ]
    noise_events = [
        item for item in items if item.event.context.get("subject") == "world"
    ]
    assert len(cache_events) == 2  # stale A + current B
    assert len(noise_events) == 5
    for item in noise_events:
        rendered = " ".join(str(value) for value in item.event.context.values())
        assert "cache" not in rendered
        assert "supply" not in rendered
        assert "crate" not in rendered
        assert item.event.context.get("x") is None


async def test_deterministic_across_runs(tmp_path) -> None:
    first = await _run_scenario(VectorMemoryBackend(str(tmp_path / "a.db")))
    second = await _run_scenario(VectorMemoryBackend(str(tmp_path / "b.db")))
    deterministic_keys = (
        "task_success",
        "current_fact_accuracy",
        "stale_action",
        "final_distance_to_b",
        "llm_calls",
        "total_prompt_tokens",
        "total_completion_tokens",
    )
    for key in deterministic_keys:
        assert first.metrics[key] == second.metrics[key]


def test_scenario_registry_lists_world_update() -> None:
    assert "world_update" in available_scenarios()
