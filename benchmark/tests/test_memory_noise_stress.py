"""Scenario D hermetic tests: MemoryNoiseStressScenario with FakeBotClient +
SmartFakeLLM (from conftest), no network.

Exercises the full memory_noise_stress lifecycle against the real
VectorMemoryBackend (tmp_path SQLite) and the NoMemoryBackend baseline.
"""

from __future__ import annotations

from minemembench.core.runner import AgentRunner
from minemembench.memory.no_memory import NoMemoryBackend
from minemembench.memory.vector_memory import VectorMemoryBackend
from minemembench.scenarios.base import ScenarioContext
from minemembench.scenarios.memory_noise_stress import GOAL, MemoryNoiseStressScenario
from minemembench.scenarios.registry import available_scenarios

from .conftest import FakeBotClient, SmartFakeLLM, make_settings


async def _run_scenario(
    memory,
    seed: int = 42,
    episode_id: str = "ep-memory-noise",
    llm: SmartFakeLLM | None = None,
    noise_count: int | None = None,
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
    scenario = MemoryNoiseStressScenario()
    if noise_count is not None:
        scenario.apply_params({"noise_count": noise_count})
    return await scenario.run(ctx)


async def test_vector_recalls_with_zero_noise(tmp_path) -> None:
    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    result = await _run_scenario(memory, noise_count=0)

    assert result.scenario == "memory_noise_stress"
    assert result.memory_backend == "vector"
    assert result.success is True
    assert result.metrics["task_success"] == 1
    assert result.metrics["relevant_memory_precision"] == 1.0
    assert result.metrics["irrelevant_retrieval_rate"] == 0.0
    assert result.metrics["token_cost"] >= 0
    assert result.metrics["end_to_end_latency_s"] is not None
    assert result.metrics["retrieval_latency_ms"] is not None

    assert result.params == {"noise_count": 0, "noise_semantics_version": "legacy"}
    assert result.run_log is not None
    assert result.run_log.goal == GOAL


async def test_vector_key_memory_survives_noise_flood(tmp_path) -> None:
    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    result = await _run_scenario(memory, noise_count=100)

    assert result.success is True
    assert result.metrics["task_success"] == 1
    assert result.metrics["relevant_memory_precision"] == 1.0
    assert result.metrics["irrelevant_retrieval_rate"] == 0.0

    stats = await memory.stats()
    assert stats.item_count == 101  # 1 key memory + 100 noise facts


async def test_raw_retrieval_probe_recorded(tmp_path) -> None:
    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    result = await _run_scenario(memory, noise_count=5)

    assert len(result.retrieval_probes) == 1
    probe = result.retrieval_probes[0]
    assert probe.phase == "evaluate"
    assert probe.query_text == "target chest location"
    assert probe.items
    assert all(item.event.event_type for item in probe.items)
    assert any(
        item.event.context.get("subject") == "target_chest" for item in probe.items
    )


async def test_no_memory_retrieves_nothing() -> None:
    memory = NoMemoryBackend()
    result = await _run_scenario(memory)

    assert result.memory_backend == "none"
    assert result.success is False
    assert result.metrics["task_success"] == 0
    assert result.metrics["relevant_memory_precision"] is None
    assert result.metrics["irrelevant_retrieval_rate"] is None
    assert result.metrics["retrieval_latency_ms"] is None


async def test_deterministic_across_runs(tmp_path) -> None:
    first = await _run_scenario(VectorMemoryBackend(str(tmp_path / "a.db")), noise_count=50)
    second = await _run_scenario(VectorMemoryBackend(str(tmp_path / "b.db")), noise_count=50)
    deterministic_keys = (
        "task_success",
        "relevant_memory_precision",
        "irrelevant_retrieval_rate",
        "llm_calls",
        "total_prompt_tokens",
        "total_completion_tokens",
    )
    for key in deterministic_keys:
        assert first.metrics[key] == second.metrics[key]


def test_scenario_registry_lists_memory_noise_stress() -> None:
    assert "memory_noise_stress" in available_scenarios()
