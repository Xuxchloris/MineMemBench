"""Rendering: CSV, Markdown, and matplotlib charts for the M11 report.

Matplotlib is imported lazily inside `write_charts` so the rest of the
package never depends on it; the `report` extra in pyproject.toml installs
it. Charts whose values are entirely unmeasured are skipped with a logged
note — empty or fabricated charts are never written.
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..scenarios.base import ScenarioResult
from .metrics import Aggregate

logger = logging.getLogger(__name__)

#: Scenario-specific metrics shown per scenario when any run measured them.
_SCENARIO_METRIC_FIELDS = (
    "fact_retrieval_rank",
    "current_fact_accuracy",
    "stale_action",
    "adaptation",
)

_FOOTER = (
    "All numbers in this report are computed from the real run logs under "
    "`results/scenario_*.json`; nothing is fabricated. Unmeasured values are "
    "shown as N/A."
)


def _trim(value: str) -> str:
    """Drop trailing zeros from a fixed-point rendering ('2.5000' -> '2.5')."""

    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value or "0"


def _fmt_num(value: Any, decimals: int = 2) -> str:
    """Format a number for the Markdown tables; None renders as N/A."""

    if value is None:
        return "N/A"
    return _trim(f"{float(value):.{decimals}f}")


def _fmt_percent(value: Any) -> str:
    """Format a rate as a percentage for the Markdown tables."""

    if value is None:
        return "N/A"
    return f"{float(value):.1%}"


def _fmt_csv(value: Any) -> str:
    """Format one cell for the CSV report; None renders as N/A."""

    if value is None:
        return "N/A"
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    return _trim(f"{float(value):.4f}")


def write_csv(aggregates: Sequence[Aggregate], path: str | Path) -> Path:
    """Write the per-(scenario, backend) aggregates as a stdlib CSV."""

    path = Path(path)
    columns = list(Aggregate.model_fields.keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for agg in aggregates:
            writer.writerow(
                {column: _fmt_csv(getattr(agg, column)) for column in columns}
            )
    return path


def _scenario_metric_columns(aggregates: Sequence[Aggregate]) -> list[str]:
    """Scenario-specific metric columns with data for this scenario's cells."""

    return [
        field
        for field in _SCENARIO_METRIC_FIELDS
        if any(getattr(agg, field) is not None for agg in aggregates)
    ]


def write_markdown(
    aggregates: Sequence[Aggregate],
    results: Sequence[ScenarioResult],
    path: str | Path,
) -> Path:
    """Write a Markdown report: header, one table per scenario, and footer."""

    path = Path(path)
    scenarios = sorted({result.scenario for result in results})
    backends = sorted({result.memory_backend for result in results})

    lines = [
        "# MineMemBench Benchmark Report",
        "",
        f"- Generated at: {datetime.now(UTC).isoformat()}",
        f"- Total runs: {len(results)}",
        f"- Memory backends: {', '.join(backends) or 'none'}",
        f"- Scenarios: {', '.join(scenarios) or 'none'}",
        "",
        "_All numbers in this report are computed from real run logs; "
        "unmeasured values are shown as N/A._",
        "",
    ]

    for scenario in sorted({agg.scenario for agg in aggregates}):
        scenario_aggs = [agg for agg in aggregates if agg.scenario == scenario]
        metric_columns = _scenario_metric_columns(scenario_aggs)
        columns = [
            "memory_backend",
            "runs",
            "success rate",
            "avg prompt tokens",
            "avg completion tokens",
            "avg llm calls",
            "avg retrieved memories",
            "avg add latency (ms)",
            "avg retrieve latency (ms)",
            "avg decision latency (s)",
            *metric_columns,
        ]
        lines.append(f"## {scenario}")
        lines.append("")
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("|" + "|".join(["---"] * len(columns)) + "|")
        for agg in scenario_aggs:
            values = [
                agg.memory_backend,
                str(agg.runs),
                _fmt_percent(agg.success_rate),
                _fmt_num(agg.avg_total_prompt_tokens),
                _fmt_num(agg.avg_total_completion_tokens),
                _fmt_num(agg.avg_llm_calls),
                _fmt_num(agg.avg_retrieved_memories),
                _fmt_num(agg.avg_add_latency_ms),
                _fmt_num(agg.avg_retrieve_latency_ms),
                _fmt_num(agg.avg_decision_latency_s),
            ]
            values.extend(_fmt_num(getattr(agg, field)) for field in metric_columns)
            lines.append("| " + " | ".join(values) + " |")
        lines.append("")

    lines.extend(["---", "", _FOOTER, ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _pyplot() -> Any:
    """Lazily import matplotlib.pyplot; matplotlib must be installed."""

    import matplotlib.pyplot as plt

    return plt


def _bar_chart(
    out_dir: Path,
    filename: str,
    title: str,
    ylabel: str,
    items: Sequence[tuple[str, float]],
    *,
    ylim: tuple[float, float] | None = None,
) -> Path:
    """One vertical bar chart from (label, value) pairs."""

    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = [str(item[0]) for item in items]
    values = [float(item[1]) for item in items]
    ax.bar(range(len(items)), values, tick_label=labels)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    if ylim is not None:
        ax.set_ylim(*ylim)
    fig.tight_layout()
    path = out_dir / filename
    fig.savefig(path)
    plt.close(fig)
    return path


def _chart_success_rate(
    aggregates: Sequence[Aggregate], out_dir: Path
) -> Path | None:
    """(a) Task success rate by backend, one bar group per scenario."""

    scenarios = sorted({agg.scenario for agg in aggregates})
    backends = sorted({agg.memory_backend for agg in aggregates})
    if not scenarios or not backends:
        return None
    lookup = {(agg.scenario, agg.memory_backend): agg for agg in aggregates}

    plt = _pyplot()
    width = 0.8 / len(scenarios)
    fig, ax = plt.subplots(figsize=(8, 5))
    for index, scenario in enumerate(scenarios):
        x_positions: list[float] = []
        heights: list[float] = []
        for backend_index, backend in enumerate(backends):
            agg = lookup.get((scenario, backend))
            if agg is not None and agg.success_rate is not None:
                x_positions.append(backend_index + index * width)
                heights.append(agg.success_rate)
        ax.bar(x_positions, heights, width=width, label=scenario)
    ax.set_xticks(
        [position + (len(scenarios) - 1) * width / 2 for position in range(len(backends))]
    )
    ax.set_xticklabels(backends)
    ax.set_ylim(0, 1)
    ax.set_ylabel("task success rate")
    ax.set_title("Task success rate by memory backend")
    ax.legend()
    fig.tight_layout()
    path = out_dir / "success_rate_by_backend.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def _chart_token_totals(
    aggregates: Sequence[Aggregate], out_dir: Path
) -> Path | None:
    """(b) Total token cost (prompt + completion) per backend."""

    totals: dict[str, float] = {}
    for agg in aggregates:
        if agg.avg_total_prompt_tokens is None and agg.avg_total_completion_tokens is None:
            continue
        tokens = (agg.avg_total_prompt_tokens or 0.0) + (
            agg.avg_total_completion_tokens or 0.0
        )
        totals[agg.memory_backend] = (
            totals.get(agg.memory_backend, 0.0) + agg.runs * tokens
        )
    if not totals:
        return None
    return _bar_chart(
        out_dir,
        "total_tokens_by_backend.png",
        "Total token cost by memory backend",
        "total tokens (prompt + completion)",
        sorted(totals.items()),
    )


def _chart_retrieval_latency(
    aggregates: Sequence[Aggregate], out_dir: Path
) -> Path | None:
    """(c) Mean memory-retrieval latency per backend."""

    per_backend: dict[str, list[float]] = {}
    for agg in aggregates:
        if agg.avg_retrieve_latency_ms is not None:
            per_backend.setdefault(agg.memory_backend, []).append(
                agg.avg_retrieve_latency_ms
            )
    if not per_backend:
        return None
    items = sorted(
        (backend, sum(values) / len(values))
        for backend, values in per_backend.items()
    )
    return _bar_chart(
        out_dir,
        "retrieval_latency_by_backend.png",
        "Average memory retrieval latency by backend",
        "avg retrieve latency (ms)",
        items,
    )


def _chart_stale_action(
    aggregates: Sequence[Aggregate], out_dir: Path
) -> Path | None:
    """(d) Stale-action rate for the world_update scenario only."""

    items = [
        (agg.memory_backend, agg.stale_action)
        for agg in aggregates
        if agg.scenario == "world_update" and agg.stale_action is not None
    ]
    if not items:
        logger.info(
            "skipping stale-action chart: no world_update stale_action data"
        )
        return None
    return _bar_chart(
        out_dir,
        "stale_action_rate.png",
        "Stale-action rate (world_update scenario)",
        "stale-action rate",
        items,
        ylim=(0, 1),
    )


def _chart_success_vs_tokens(
    aggregates: Sequence[Aggregate], out_dir: Path
) -> Path | None:
    """(e) Success-rate vs total-tokens scatter, one series per backend."""

    series: dict[str, list[tuple[float, float]]] = {}
    for agg in aggregates:
        if agg.success_rate is None:
            continue
        if agg.avg_total_prompt_tokens is None and agg.avg_total_completion_tokens is None:
            continue
        tokens = (agg.avg_total_prompt_tokens or 0.0) + (
            agg.avg_total_completion_tokens or 0.0
        )
        series.setdefault(agg.memory_backend, []).append((tokens, agg.success_rate))
    if not series:
        return None

    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(8, 5))
    for backend, points in sorted(series.items()):
        ax.scatter(
            [point[0] for point in points],
            [point[1] for point in points],
            label=backend,
        )
    ax.set_xlabel("total tokens (prompt + completion)")
    ax.set_ylabel("task success rate")
    ax.set_ylim(0, 1)
    ax.set_title("Task success rate vs total token cost")
    ax.legend()
    fig.tight_layout()
    path = out_dir / "success_vs_tokens.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def write_charts(aggregates: Sequence[Aggregate], out_dir: str | Path) -> list[Path]:
    """Render one PNG per report chart, skipping charts with no data.

    Matplotlib (Agg backend) is imported lazily here; `ImportError` is left
    for the caller (the report CLI) to turn into an install hint.
    """

    import matplotlib

    matplotlib.use("Agg")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for renderer in (
        _chart_success_rate,
        _chart_token_totals,
        _chart_retrieval_latency,
        _chart_stale_action,
        _chart_success_vs_tokens,
    ):
        path = renderer(aggregates, out_dir)
        if path is not None:
            written.append(path)
    return written
