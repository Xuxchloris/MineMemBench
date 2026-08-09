"""M15B stress-scenario hermetic tests: end-to-end runs of the extended
scenarios at non-default difficulty parameters (FakeBotClient +
SmartFakeLLM, no network)."""

from __future__ import annotations

from minemembench.core.runner import AgentRunner
from minemembench.memory.vector_memory import VectorMemoryBackend
from minemembench.scenarios.base import ScenarioContext
from minemembench.scenarios.delayed_recall import DelayedRecallScenario
from minemembench.scenarios.world_update import WorldUpdateScenario

from .conftest import FakeBotClient, SmartFakeLLM, make_settings


async def _run(scenario, memory, seed=42, episode_id="ep-stress"):
    settings = make_settings()
    bot = FakeBotClient()
    llm = SmartFakeLLM()
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
    return await scenario.run(ctx)


async def test_delayed_recall_with_distractors_scores_stress_metrics(tmp_path) -> None:
    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    scenario = DelayedRecallScenario()
    scenario.apply_params({"similar_distractor_count": 5})
    result = await _run(scenario, memory)

    # The similar facts crowd retrieval: a stale target-chest lookalike ranks
    # first (and the memory-naive LLM navigates to it), so navigation fails
    # even though the correct fact is still among the retrieved items. The
    # retrieval-side metrics capture exactly that degradation: the reported
    # rank is the CORRECT fact's position (2), never the wrong lookalike's.
    assert result.metrics["task_success"] == 0
    assert result.metrics["fact_retrieval_rank"] == 2
    assert result.metrics["recall_accuracy"] == 1
    assert result.metrics["wrong_fact_rate"] == 0.4
    assert result.metrics["retrieval_precision"] == 0.6

    stats = await memory.stats()
    assert stats.item_count == 1 + 10 + 5  # target + noise + distractors


async def test_delayed_recall_high_interference_count(tmp_path) -> None:
    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    scenario = DelayedRecallScenario()
    scenario.apply_params({"interference_count": 200})
    result = await _run(scenario, memory)

    assert result.metrics["task_success"] == 1
    assert result.metrics["recall_accuracy"] == 1
    stats = await memory.stats()
    assert stats.item_count == 1 + 200


async def test_world_update_depth_three_chain(tmp_path) -> None:
    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    scenario = WorldUpdateScenario()
    scenario.apply_params({"update_depth": 3})
    result = await _run(scenario, memory)

    # The naive vector baseline surfaces a stale location (A/B/C) first; three
    # of the four stored cache facts are obsolete.
    assert result.metrics["task_success"] == 0
    assert result.metrics["current_fact_accuracy"] == 0
    assert result.metrics["stale_memory_rate"] == 0.75
    assert result.metrics["obsolete_fact_retrieval_rate"] == 0.75
    assert result.metrics["stale_action"] == 1

    assert result.params == {"update_depth": 3, "update_semantics_version": "legacy"}
    # Raw retrieval results are preserved in the run log (M15B requirement).
    assert len(result.retrieval_probes) == 1
    probe = result.retrieval_probes[0]
    assert probe.items
    assert all(
        item.event.context.get("subject") == "supply_cache" for item in probe.items
    )
    assert len(probe.items) == 4  # A, B, C, D all retrieved
