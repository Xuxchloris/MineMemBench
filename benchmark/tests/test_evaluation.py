"""M11 report tests: result loading, aggregation, CSV/Markdown/charts.

All result JSONs here are synthetic test inputs fabricated only as fixtures
in tmp_path — the real results/ directory is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from minemembench.cli import main
from minemembench.core.models import ActionStatus, Position
from minemembench.core.runner import RunLog, RunStep
from minemembench.evaluation.metrics import Aggregate, aggregate, load_results
from minemembench.evaluation.reporter import write_charts, write_csv, write_markdown
from minemembench.scenarios.base import ScenarioResult


def _make_result(
    scenario: str,
    backend: str,
    success: bool,
    *,
    episode: str = "ep",
    seed: int = 1,
    metrics: dict[str, Any] | None = None,
    steps: list[RunStep] | None = None,
    run_log: bool = True,
) -> ScenarioResult:
    """A synthetic ScenarioResult with a small deterministic run log."""

    if steps is None:
        steps = [
            RunStep(
                index=index,
                position=Position(x=0.0, y=0.0, z=0.0),
                retrieved_memory_count=index + 1,
                action="wait",
                arguments={},
                reason="synthetic test run",
                action_status=ActionStatus.COMPLETED,
                prompt_tokens=10,
                completion_tokens=5,
                latency_s=0.5,
            )
            for index in range(2)
        ]
    log: RunLog | None = None
    if run_log:
        log = RunLog(
            run_id="run",
            memory_backend=backend,
            goal="goal",
            model="test-model",
            temperature=0.0,
            steps=steps,
            llm_calls=1,
            total_prompt_tokens=20,
            total_completion_tokens=10,
            success=success,
        )
    return ScenarioResult(
        scenario=scenario,
        episode_id=episode,
        seed=seed,
        memory_backend=backend,
        success=success,
        metrics=metrics or {},
        run_log=log,
    )


def _write_result(results_dir: Path, result: ScenarioResult) -> Path:
    path = (
        results_dir
        / f"scenario_{result.scenario}_{result.memory_backend}_{result.episode_id}_{result.seed}.json"
    )
    path.write_text(result.to_json(), encoding="utf-8")
    return path


def _single_step(retrieved: int, latency: float) -> list[RunStep]:
    return [
        RunStep(
            index=0,
            position=Position(x=0.0, y=0.0, z=0.0),
            retrieved_memory_count=retrieved,
            action="wait",
            arguments={},
            reason="synthetic test run",
            action_status=ActionStatus.COMPLETED,
            prompt_tokens=5,
            completion_tokens=1,
            latency_s=latency,
        )
    ]


# --- load_results ---------------------------------------------------------


def test_load_results_reads_valid_and_skips_bad(tmp_path, caplog) -> None:
    _write_result(tmp_path, _make_result("delayed_recall", "vector", True, episode="a"))
    _write_result(tmp_path, _make_result("world_update", "none", False, episode="b"))

    bad_syntax = tmp_path / "scenario_broken.json"
    bad_syntax.write_text("{ not valid json", encoding="utf-8")
    bad_schema = tmp_path / "scenario_schema.json"
    bad_schema.write_text(json.dumps({"scenario": "x"}), encoding="utf-8")
    not_a_scenario = tmp_path / "some_run.json"
    not_a_scenario.write_text("{}", encoding="utf-8")

    with caplog.at_level("WARNING"):
        results = load_results(tmp_path)

    assert sorted(result.scenario for result in results) == [
        "delayed_recall",
        "world_update",
    ]
    assert "scenario_broken.json" in caplog.text
    assert "scenario_schema.json" in caplog.text
    assert "some_run.json" not in caplog.text


def test_load_results_empty_dir_is_empty(tmp_path) -> None:
    assert load_results(tmp_path) == []


# --- aggregate ------------------------------------------------------------


def test_aggregate_means_and_rates(tmp_path) -> None:
    first = _make_result(
        "delayed_recall",
        "vector",
        True,
        episode="a",
        seed=1,
        metrics={
            "total_prompt_tokens": 100,
            "total_completion_tokens": 50,
            "llm_calls": 2,
            "avg_add_latency_ms": 10.0,
            "avg_retrieve_latency_ms": 5.0,
            "fact_retrieval_rank": 1,
        },
    )
    second = _make_result(
        "delayed_recall",
        "vector",
        False,
        episode="b",
        seed=2,
        metrics={
            "total_prompt_tokens": 200,
            "total_completion_tokens": 100,
            "llm_calls": 3,
            "avg_add_latency_ms": None,
            "avg_retrieve_latency_ms": None,
            "fact_retrieval_rank": None,
        },
    )
    world = _make_result(
        "world_update",
        "none",
        True,
        episode="c",
        metrics={"current_fact_accuracy": 1, "stale_action": 0},
        steps=_single_step(retrieved=0, latency=0.2),
    )
    failure = _make_result(
        "failure_learning",
        "vector",
        True,
        episode="d",
        metrics={"adaptation": 1, "avg_add_latency_ms": 7.0},
    )

    aggregates = aggregate([first, second, world, failure])
    by_key = {(agg.scenario, agg.memory_backend): agg for agg in aggregates}
    assert set(by_key) == {
        ("delayed_recall", "vector"),
        ("world_update", "none"),
        ("failure_learning", "vector"),
    }

    recall = by_key[("delayed_recall", "vector")]
    assert recall.runs == 2
    assert recall.success_rate == pytest.approx(0.5)
    assert recall.avg_total_prompt_tokens == pytest.approx(150.0)
    assert recall.avg_total_completion_tokens == pytest.approx(75.0)
    assert recall.avg_llm_calls == pytest.approx(2.5)
    assert recall.avg_retrieved_memories == pytest.approx(1.5)  # (1+2)+(1+2) / 4
    assert recall.avg_add_latency_ms == pytest.approx(10.0)
    assert recall.avg_retrieve_latency_ms == pytest.approx(5.0)
    assert recall.avg_decision_latency_s == pytest.approx(0.5)
    assert recall.fact_retrieval_rank == pytest.approx(1.0)

    world_agg = by_key[("world_update", "none")]
    assert world_agg.runs == 1
    assert world_agg.current_fact_accuracy == pytest.approx(1.0)
    assert world_agg.stale_action == pytest.approx(0.0)
    assert world_agg.adaptation is None
    assert world_agg.avg_retrieved_memories == pytest.approx(0.0)
    assert world_agg.avg_decision_latency_s == pytest.approx(0.2)

    failure_agg = by_key[("failure_learning", "vector")]
    assert failure_agg.adaptation == pytest.approx(1.0)
    assert failure_agg.fact_retrieval_rank is None
    assert failure_agg.current_fact_accuracy is None
    assert failure_agg.stale_action is None
    assert failure_agg.avg_add_latency_ms == pytest.approx(7.0)


def test_aggregate_propagates_none_without_run_log(tmp_path) -> None:
    result = _make_result(
        "delayed_recall", "none", False, episode="a", run_log=False
    )
    aggregates = aggregate([result])

    assert len(aggregates) == 1
    agg = aggregates[0]
    assert agg.runs == 1
    assert agg.success_rate == pytest.approx(0.0)
    assert agg.avg_retrieved_memories is None
    assert agg.avg_decision_latency_s is None
    assert agg.avg_total_prompt_tokens is None


# --- write_csv ------------------------------------------------------------


def test_write_csv_contains_values_and_na_cells(tmp_path) -> None:
    aggregates = [
        Aggregate(
            scenario="delayed_recall",
            memory_backend="vector",
            runs=2,
            success_rate=0.5,
            avg_total_prompt_tokens=150.0,
            avg_total_completion_tokens=75.0,
            avg_llm_calls=2.5,
            avg_retrieved_memories=2.0,
            avg_add_latency_ms=10.0,
            avg_retrieve_latency_ms=5.0,
            avg_decision_latency_s=0.5,
            fact_retrieval_rank=1.0,
        ),
        Aggregate(
            scenario="world_update",
            memory_backend="none",
            runs=1,
            success_rate=0.0,
            current_fact_accuracy=1.0,
            stale_action=0.0,
        ),
    ]
    out = tmp_path / "summary.csv"
    write_csv(aggregates, out)

    text = out.read_text(encoding="utf-8")
    assert "scenario,memory_backend,runs,success_rate" in text
    assert (
        "delayed_recall,vector,2,0.5,150,75,2.5,2,10,5,0.5,1,N/A,N/A,N/A" in text
    )
    assert (
        "world_update,none,1,0,N/A,N/A,N/A,N/A,N/A,N/A,N/A,N/A,1,0,N/A" in text
    )


# --- write_markdown -------------------------------------------------------


def test_write_markdown_contains_header_tables_and_footer(tmp_path) -> None:
    results = [
        _make_result(
            "delayed_recall",
            "vector",
            True,
            episode="a",
            metrics={
                "total_prompt_tokens": 100,
                "total_completion_tokens": 50,
                "fact_retrieval_rank": 1,
            },
        ),
        _make_result(
            "world_update",
            "none",
            False,
            episode="b",
            metrics={"current_fact_accuracy": 0, "stale_action": 1},
            steps=_single_step(retrieved=0, latency=0.2),
        ),
    ]
    out = tmp_path / "report.md"
    write_markdown(aggregate(results), results, out)

    text = out.read_text(encoding="utf-8")
    assert "# MineMemBench Benchmark Report" in text
    assert "Total runs: 2" in text
    assert "Memory backends: none, vector" in text
    assert "Scenarios: delayed_recall, world_update" in text
    assert "## delayed_recall" in text
    assert "## world_update" in text
    assert "fact_retrieval_rank" in text
    assert "stale_action" in text
    assert "100.0%" in text
    assert "0.0%" in text
    assert "N/A" in text
    assert "real run logs" in text


# --- write_charts ---------------------------------------------------------


def test_write_charts_skips_empty_data_charts(tmp_path, caplog) -> None:
    aggregates = [
        Aggregate(
            scenario="delayed_recall", memory_backend="none", runs=1, success_rate=0.0
        ),
        Aggregate(
            scenario="world_update", memory_backend="vector", runs=1, success_rate=1.0
        ),
    ]
    with caplog.at_level("INFO"):
        written = write_charts(aggregates, tmp_path)

    names = {path.name for path in written}
    assert "success_rate_by_backend.png" in names
    assert "total_tokens_by_backend.png" not in names
    assert "retrieval_latency_by_backend.png" not in names
    assert "stale_action_rate.png" not in names
    assert "success_vs_tokens.png" not in names
    assert "no world_update stale_action data" in caplog.text


def test_write_charts_renders_each_chart_when_data_present(tmp_path) -> None:
    aggregates = [
        Aggregate(
            scenario="delayed_recall",
            memory_backend="vector",
            runs=2,
            success_rate=0.5,
            avg_total_prompt_tokens=150.0,
            avg_total_completion_tokens=75.0,
            avg_retrieve_latency_ms=5.0,
        ),
        Aggregate(
            scenario="world_update",
            memory_backend="vector",
            runs=1,
            success_rate=0.0,
            avg_total_prompt_tokens=50.0,
            avg_total_completion_tokens=10.0,
            avg_retrieve_latency_ms=7.5,
            stale_action=0.5,
        ),
        Aggregate(
            scenario="world_update",
            memory_backend="none",
            runs=1,
            success_rate=1.0,
            avg_total_prompt_tokens=20.0,
            avg_total_completion_tokens=5.0,
            stale_action=1.0,
        ),
    ]
    written = write_charts(aggregates, tmp_path)

    names = {path.name for path in written}
    assert names == {
        "success_rate_by_backend.png",
        "total_tokens_by_backend.png",
        "retrieval_latency_by_backend.png",
        "stale_action_rate.png",
        "success_vs_tokens.png",
    }
    for path in written:
        assert path.stat().st_size > 0


# --- CLI ------------------------------------------------------------------


def test_report_command_writes_report_into_results_dir(tmp_path) -> None:
    _write_result(
        tmp_path,
        _make_result(
            "delayed_recall",
            "vector",
            True,
            episode="a",
            metrics={
                "total_prompt_tokens": 100,
                "total_completion_tokens": 50,
                "fact_retrieval_rank": 1,
            },
        ),
    )

    code = main(["report", "--results-dir", str(tmp_path)])
    assert code == 0

    report_dir = tmp_path / "report"
    assert (report_dir / "summary.csv").exists()
    assert (report_dir / "report.md").exists()
    charts = list((report_dir / "charts").glob("*.png"))
    assert any(path.name == "success_rate_by_backend.png" for path in charts)


def test_report_command_missing_results_dir_is_an_error(tmp_path, capsys) -> None:
    missing = tmp_path / "does_not_exist"
    code = main(["report", "--results-dir", str(missing)])
    assert code == 2
    assert "results directory not found" in capsys.readouterr().err
