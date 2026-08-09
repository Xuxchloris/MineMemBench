"""M15B stress-layer parameter tests: CLI parsing, apply_params defaults,
similar-distractor generation, and update-chain generation.

All tests are hermetic (no network, no real LLM API).
"""

from __future__ import annotations

import random

import pytest

from minemembench.cli import _build_parser, _parse_scenario_params, main
from minemembench.core.models import Position
from minemembench.core.runner import AgentRunner
from minemembench.memory.vector_memory import VectorMemoryBackend
from minemembench.scenarios.base import ScenarioContext, ScenarioParamError
from minemembench.scenarios.delayed_recall import (
    DelayedRecallScenario,
    build_similar_distractors,
)
from minemembench.scenarios.offsets import seeded_offset
from minemembench.scenarios.world_update import WorldUpdateScenario, build_update_chain

from .conftest import FakeBotClient, SmartFakeLLM, make_settings

SPAWN = Position(x=0.0, y=64.0, z=0.0)


# --- CLI --scenario-param parsing -------------------------------------------


def test_parse_scenario_params_coerces_types() -> None:
    params = _parse_scenario_params(
        [
            "interference_count=200",
            "similar_distractor_count=20",
            "update_depth=3",
            "flag=true",
            "ratio=0.5",
            "name=stress",
        ]
    )
    assert params == {
        "interference_count": 200,
        "similar_distractor_count": 20,
        "update_depth": 3,
        "flag": True,
        "ratio": 0.5,
        "name": "stress",
    }
    assert isinstance(params["interference_count"], int)
    assert isinstance(params["ratio"], float)
    assert isinstance(params["flag"], bool)


def test_parse_scenario_params_missing_equals_raises() -> None:
    with pytest.raises(ValueError, match="KEY=VALUE"):
        _parse_scenario_params(["interference_count"])


def test_parse_scenario_params_empty_key_raises() -> None:
    with pytest.raises(ValueError, match="empty key"):
        _parse_scenario_params(["=5"])


def test_cli_scenario_param_flag_parses() -> None:
    args = _build_parser().parse_args(
        [
            "run",
            "--scenario",
            "delayed_recall",
            "--scenario-param",
            "interference_count=200",
            "--scenario-param",
            "similar_distractor_count=20",
        ]
    )
    assert args.scenario_param == ["interference_count=200", "similar_distractor_count=20"]
    assert _parse_scenario_params(args.scenario_param) == {
        "interference_count": 200,
        "similar_distractor_count": 20,
    }


def test_cli_scenario_param_defaults_to_empty() -> None:
    args = _build_parser().parse_args(["run", "--scenario", "delayed_recall"])
    assert args.scenario_param == []


def test_main_rejects_unknown_scenario_param_fail_fast(capsys) -> None:
    """An unknown parameter exits 2 before any bot connection is attempted."""

    code = main(
        [
            "run",
            "--scenario",
            "delayed_recall",
            "--scenario-param",
            "no_such_param=1",
        ]
    )
    assert code == 2
    captured = capsys.readouterr()
    assert "unknown scenario parameter" in captured.err


def test_main_rejects_invalid_scenario_param_value(capsys) -> None:
    code = main(
        [
            "run",
            "--scenario",
            "world_update",
            "--scenario-param",
            "update_depth=0",
        ]
    )
    assert code == 2
    captured = capsys.readouterr()
    assert "update_depth" in captured.err


def test_run_help_shows_scenario_param(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["run", "--help"])
    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "--scenario-param" in output
    for backend in ("none", "vector", "mem0", "letta", "graphiti"):
        assert backend in output
    for scenario in (
        "delayed_recall",
        "world_update",
        "memory_noise_stress",
        "failure_learning",
    ):
        assert scenario in output


# --- apply_params defaults / validation -------------------------------------


def test_delayed_recall_default_params_preserve_old_behavior() -> None:
    scenario = DelayedRecallScenario()
    assert scenario.params == {
        "interference_count": 10,
        "similar_distractor_count": 0,
        "recall_semantics_version": "legacy",
    }
    scenario.apply_params({})
    assert scenario.params == {
        "interference_count": 10,
        "similar_distractor_count": 0,
        "recall_semantics_version": "legacy",
    }


def test_delayed_recall_apply_params_overrides() -> None:
    scenario = DelayedRecallScenario()
    scenario.apply_params({"interference_count": 500, "similar_distractor_count": 50})
    assert scenario.params == {
        "interference_count": 500,
        "similar_distractor_count": 50,
        "recall_semantics_version": "legacy",
    }


def test_delayed_recall_rejects_unknown_semantics_version() -> None:
    scenario = DelayedRecallScenario()
    with pytest.raises(ScenarioParamError, match="recall_semantics_version"):
        scenario.apply_params({"recall_semantics_version": "v3"})
    scenario.apply_params({"recall_semantics_version": "entity_key_v2"})
    assert scenario.params["recall_semantics_version"] == "entity_key_v2"


def test_apply_params_rejects_unknown_key() -> None:
    scenario = DelayedRecallScenario()
    with pytest.raises(ScenarioParamError, match="unknown scenario parameter"):
        scenario.apply_params({"no_such_param": 1})


def test_apply_params_rejects_invalid_values() -> None:
    scenario = DelayedRecallScenario()
    with pytest.raises(ScenarioParamError, match="interference_count"):
        scenario.apply_params({"interference_count": -1})
    with pytest.raises(ScenarioParamError, match="similar_distractor_count"):
        scenario.apply_params({"similar_distractor_count": "many"})


def test_world_update_default_and_validation() -> None:
    scenario = WorldUpdateScenario()
    assert scenario.params == {
        "update_depth": 1,
        "update_semantics_version": "legacy",
    }
    scenario.apply_params({"update_depth": 3})
    assert scenario.params == {
        "update_depth": 3,
        "update_semantics_version": "legacy",
    }
    with pytest.raises(ScenarioParamError, match="update_depth"):
        scenario.apply_params({"update_depth": 0})
    with pytest.raises(ScenarioParamError, match="update_semantics_version"):
        scenario.apply_params({"update_semantics_version": "v3"})


async def test_delayed_recall_default_params_run_matches_classic(tmp_path) -> None:
    """apply_params({}) produces the exact Phase-1 outcome (11 memories)."""

    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    scenario = DelayedRecallScenario()
    scenario.apply_params({})
    llm = SmartFakeLLM()
    bot = FakeBotClient()
    runner = AgentRunner(bot, memory, llm)
    ctx = ScenarioContext(
        bot=bot,
        memory=memory,
        runner=runner,
        llm=llm,
        settings=make_settings(),
        seed=42,
        episode_id="ep-defaults",
    )
    result = await scenario.run(ctx)

    assert result.metrics["task_success"] == 1
    assert result.metrics["fact_retrieval_rank"] == 1
    assert result.metrics["recall_accuracy"] == 1
    assert result.metrics["wrong_fact_rate"] == 0.0
    assert result.metrics["retrieval_precision"] == 1.0
    assert result.params == {
        "interference_count": 10,
        "similar_distractor_count": 0,
        "recall_semantics_version": "legacy",
    }
    assert result.evaluation_ground_truth is None  # legacy has no v2 oracle
    stats = await memory.stats()
    assert stats.item_count == 11  # 1 chest fact + 10 noise facts


# --- similar-distractor generation ------------------------------------------


def test_build_similar_distractors_deterministic() -> None:
    target = Position(x=10.0, y=64.0, z=20.0)
    first = build_similar_distractors(
        target, SPAWN, random.Random(44), 20
    )
    second = build_similar_distractors(
        target, SPAWN, random.Random(44), 20
    )
    assert first == second


def test_build_similar_distractors_count_and_shape() -> None:
    target = Position(x=10.0, y=64.0, z=20.0)
    distractors = build_similar_distractors(target, SPAWN, random.Random(44), 7)
    assert len(distractors) == 7
    for context in distractors:
        assert context["subject"]
        assert {"x", "y", "z"} <= set(context)
        assert (context["x"], context["y"], context["z"]) != (
            target.x,
            target.y,
            target.z,
        )


def test_build_similar_distractors_cycles_all_kinds() -> None:
    target = Position(x=10.0, y=64.0, z=20.0)
    distractors = build_similar_distractors(target, SPAWN, random.Random(44), 4)
    subjects = [d["subject"] for d in distractors]
    assert any("_chest" in subject and subject != "target_chest" for subject in subjects)
    assert any(subject.startswith("red_") for subject in subjects)
    assert subjects.count("target_chest") == 2  # wrong location + stale location
    stale = [d for d in distractors if "used to be" in str(d.get("note", ""))]
    assert len(stale) == 1


def test_build_similar_distractors_zero_is_empty() -> None:
    assert (
        build_similar_distractors(Position(x=1.0, y=64.0, z=1.0), SPAWN, random.Random(1), 0)
        == []
    )


# --- update-chain generation ------------------------------------------------


def test_build_update_chain_depth_one_matches_classic() -> None:
    chain = build_update_chain(SPAWN, 42, 1)
    assert chain[0] == seeded_offset(SPAWN, random.Random(42))
    assert chain[1] == seeded_offset(SPAWN, random.Random(42 + 100))
    assert len(chain) == 2
    assert chain[0] != chain[1]


def test_build_update_chain_depth_three_prefixes_depth_one() -> None:
    depth_1 = build_update_chain(SPAWN, 42, 1)
    depth_3 = build_update_chain(SPAWN, 42, 3)
    assert len(depth_3) == 4
    # A higher depth must never perturb shallower locations.
    assert depth_3[:2] == depth_1
    assert len({(p.x, p.y, p.z) for p in depth_3}) == 4  # all distinct


def test_build_update_chain_deterministic() -> None:
    assert build_update_chain(SPAWN, 7, 3) == build_update_chain(SPAWN, 7, 3)
