"""Result loading and per-(scenario, memory backend) aggregation (M11).

Every value in an `Aggregate` is derived from real scenario result files;
anything unmeasured stays `None` (rendered as N/A) and is never zero-filled.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, ValidationError

from ..core.runner import RunStep
from ..scenarios.base import ScenarioResult

logger = logging.getLogger(__name__)


class Aggregate(BaseModel):
    """One report row: a (scenario, memory backend) cell of the benchmark.

    Field order is the canonical report column order. `None` means the value
    was not measured by any run in the group.
    """

    model_config = ConfigDict(validate_assignment=True)

    scenario: str
    memory_backend: str
    runs: int
    success_rate: float | None = None
    avg_total_prompt_tokens: float | None = None
    avg_total_completion_tokens: float | None = None
    avg_llm_calls: float | None = None
    avg_retrieved_memories: float | None = None
    avg_add_latency_ms: float | None = None
    avg_retrieve_latency_ms: float | None = None
    avg_decision_latency_s: float | None = None
    fact_retrieval_rank: float | None = None
    current_fact_accuracy: float | None = None
    stale_action: float | None = None
    adaptation: float | None = None


def _mean(values: Iterable[Any]) -> float | None:
    """Mean of the numeric values, skipping None; None when nothing measured."""

    present = [
        float(value)
        for value in values
        if value is not None and isinstance(value, (int, float))
    ]
    return sum(present) / len(present) if present else None


def load_results(results_dir: str | Path) -> list[ScenarioResult]:
    """Load every valid `scenario_*.json` under `results_dir`.

    Files are validated against `ScenarioResult`; malformed or schema-invalid
    files are skipped with a logged warning so one corrupt file never breaks
    the whole report.
    """

    path = Path(results_dir)
    results: list[ScenarioResult] = []
    for result_path in sorted(path.glob("scenario_*.json")):
        try:
            results.append(
                ScenarioResult.model_validate_json(
                    result_path.read_text(encoding="utf-8")
                )
            )
        except (OSError, ValidationError) as exc:
            logger.warning(
                "skipping invalid result file %s: %s", result_path.name, exc
            )
    return results


def _steps(result: ScenarioResult) -> list[RunStep]:
    """The run-log steps of a result, or [] when no run log was recorded."""

    return list(result.run_log.steps) if result.run_log is not None else []


def _metric_values(group: list[ScenarioResult], key: str) -> list[Any]:
    """Per-run values of one metrics-dict key across the group."""

    return [result.metrics.get(key) for result in group]


def _aggregate_group(group: list[ScenarioResult]) -> Aggregate:
    """Summarize one (scenario, backend) group into a single Aggregate."""

    all_steps = [step for result in group for step in _steps(result)]
    return Aggregate(
        scenario=group[0].scenario,
        memory_backend=group[0].memory_backend,
        runs=len(group),
        success_rate=_mean([result.success for result in group]),
        avg_total_prompt_tokens=_mean(_metric_values(group, "total_prompt_tokens")),
        avg_total_completion_tokens=_mean(
            _metric_values(group, "total_completion_tokens")
        ),
        avg_llm_calls=_mean(_metric_values(group, "llm_calls")),
        avg_retrieved_memories=_mean(
            [step.retrieved_memory_count for step in all_steps]
        ),
        avg_add_latency_ms=_mean(_metric_values(group, "avg_add_latency_ms")),
        avg_retrieve_latency_ms=_mean(_metric_values(group, "avg_retrieve_latency_ms")),
        avg_decision_latency_s=_mean([step.latency_s for step in all_steps]),
        fact_retrieval_rank=_mean(_metric_values(group, "fact_retrieval_rank")),
        current_fact_accuracy=_mean(_metric_values(group, "current_fact_accuracy")),
        stale_action=_mean(_metric_values(group, "stale_action")),
        adaptation=_mean(_metric_values(group, "adaptation")),
    )


def aggregate(results: list[ScenarioResult]) -> list[Aggregate]:
    """Group results by (scenario, memory_backend) and summarize each cell.

    Averages are over the runs in the cell; `None` propagates whenever no run
    measured the value (never zero-filled).
    """

    grouped: dict[tuple[str, str], list[ScenarioResult]] = defaultdict(list)
    for result in results:
        grouped[(result.scenario, result.memory_backend)].append(result)
    aggregates = [_aggregate_group(group) for group in grouped.values()]
    return sorted(aggregates, key=lambda agg: (agg.scenario, agg.memory_backend))
