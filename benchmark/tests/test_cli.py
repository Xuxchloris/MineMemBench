"""CLI tests: scenario arg parsing and error exits (hermetic, no network).

The unknown-scenario and missing-goal paths are validated before any bot
connection, so these run without a bridge or LLM.
"""

from __future__ import annotations

from minemembench.cli import _build_parser, main


def test_scenario_args_parse() -> None:
    args = _build_parser().parse_args(
        [
            "run",
            "--scenario",
            "delayed_recall",
            "--memory",
            "vector",
            "--runs",
            "3",
            "--seed",
            "7",
        ]
    )
    assert args.scenario == "delayed_recall"
    assert args.memory == "vector"
    assert args.runs == 3
    assert args.seed == 7


def test_scenario_args_defaults() -> None:
    args = _build_parser().parse_args(["run", "--scenario", "delayed_recall"])
    assert args.scenario == "delayed_recall"
    assert args.memory == "none"
    assert args.runs == 1
    assert args.seed == 42


def test_plain_goal_mode_defaults_unchanged() -> None:
    args = _build_parser().parse_args(["run", "--goal", "walk to 10,64,10"])
    assert args.scenario is None
    assert args.goal == "walk to 10,64,10"
    assert args.success_at is None
    assert args.max_steps == 10
    assert args.memory == "none"


def test_run_without_goal_or_scenario_is_an_error() -> None:
    assert main(["run", "--memory", "none"]) == 2


def test_unknown_scenario_exits_two_with_message(capsys) -> None:
    code = main(["run", "--scenario", "does_not_exist", "--memory", "none"])
    assert code == 2
    captured = capsys.readouterr()
    assert "unknown scenario" in captured.err
    assert "delayed_recall" in captured.err


def test_zero_runs_is_rejected() -> None:
    assert main(["run", "--scenario", "delayed_recall", "--runs", "0"]) == 2
