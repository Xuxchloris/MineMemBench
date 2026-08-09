"""Same-seed comparison with fail-closed fairness validity."""

from __future__ import annotations

import json
from typing import Any

from ..scenarios.base import ScenarioResult
from .models import (
    ComparisonCell,
    FairnessFieldComparison,
    SameSeedComparison,
)
from .replay import build_replay

BACKEND_ORDER = ("none", "vector", "mem0", "letta")
_FAIRNESS_FIELDS = (
    "planner_model",
    "temperature",
    "system_prompt_hash",
    "tool_set_hash",
    "planner_user_template_hash",
    "minecraft_version",
    "world_seed",
    "fixture_selector",
    "fixture_identity",
    "scenario",
    "scenario_params",
    "campaign_mode",
    "run_seed",
    "source_tree_fingerprint",
    "source_file_count",
    "git_commit",
    "git_dirty",
    "git_status_fingerprint",
)


def _canonical_params(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True, separators=(",", ":"))


def _comparison_evidence(result: ScenarioResult) -> dict[str, Any]:
    logs = (
        [entry.run_log for entry in result.run_logs]
        if result.run_logs
        else ([result.run_log] if result.run_log is not None else [])
    )
    steps = [step for log in logs for step in log.steps]
    first = steps[0] if steps else None
    prompt = sum(log.total_prompt_tokens for log in logs) if logs else None
    completion = (
        sum(log.total_completion_tokens for log in logs) if logs else None
    )
    replay = build_replay(result)
    return {
        "retrieved_top_k": (
            [item.model_dump(mode="json") for item in first.retrieved_items]
            if first is not None
            else []
        ),
        "first_action": (
            {
                "action": first.action,
                "arguments": dict(first.arguments),
                "reason": first.reason,
                "status": first.action_status.value,
                "error": first.action_error,
            }
            if first is not None
            else None
        ),
        "preparation": result.metrics.get(
            "preparation_before_first_attempt",
            result.metrics.get("prepared_before_first_transfer_attack"),
        ),
        "failure_repetition": result.metrics.get("failure_repeated"),
        "steps": len(steps) if logs else None,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": (
            prompt + completion
            if prompt is not None and completion is not None
            else None
        ),
        "llm_latency_ms": (
            round(sum(step.latency_s for step in steps) * 1000, 4)
            if logs
            else None
        ),
        "retrieval_latency_ms": result.metrics.get(
            "avg_retrieve_latency_ms"
        ),
        "end_to_end_latency_ms": result.metrics.get(
            "end_to_end_latency_ms"
        ),
        "replay_frames": [
            {
                "sequence": frame.sequence,
                "phase": frame.phase,
                "retrieved": frame.retrieval.item_count,
                "action": frame.planner.action,
                "reason": frame.planner.reason,
                "status": frame.outcome.status,
                "error": frame.outcome.error,
            }
            for frame in replay.frames
        ],
    }


def build_same_seed_comparison(
    runs: list[tuple[str, ScenarioResult]], *, anchor_run_id: str
) -> SameSeedComparison | None:
    anchor = next((result for run_id, result in runs if run_id == anchor_run_id), None)
    if anchor is None:
        return None
    params_key = _canonical_params(anchor.params)
    selected = [
        (run_id, result)
        for run_id, result in runs
        if result.scenario == anchor.scenario
        and result.seed == anchor.seed
        and result.campaign_mode == anchor.campaign_mode
        and _canonical_params(result.params) == params_key
        and result.memory_backend in BACKEND_ORDER
    ]
    grouped: dict[str, list[tuple[str, ScenarioResult]]] = {
        backend: [] for backend in BACKEND_ORDER
    }
    for pair in selected:
        grouped[pair[1].memory_backend].append(pair)

    cells: list[ComparisonCell] = []
    unique: dict[str, ScenarioResult] = {}
    for backend in BACKEND_ORDER:
        pairs = grouped[backend]
        if not pairs:
            cells.append(ComparisonCell(backend=backend, status="missing"))
        elif len(pairs) > 1:
            cells.append(
                ComparisonCell(
                    backend=backend,
                    status="duplicate",
                    run_ids=[run_id for run_id, _result in pairs],
                )
            )
        else:
            run_id, result = pairs[0]
            unique[backend] = result
            cells.append(
                ComparisonCell(
                    backend=backend,
                    status="present",
                    run_ids=[run_id],
                    success=result.success,
                    fairness_valid=(
                        result.fairness.valid if result.fairness is not None else None
                    ),
                    metrics=dict(result.metrics),
                    **_comparison_evidence(result),
                )
            )

    comparisons: list[FairnessFieldComparison] = []
    any_fail = any(cell.status == "duplicate" for cell in cells)
    any_unknown = any(cell.status == "missing" for cell in cells)
    for backend, result in unique.items():
        if result.fairness is None:
            any_unknown = True
        elif not result.fairness.valid:
            any_fail = True

    for field in _FAIRNESS_FIELDS:
        values: dict[str, Any] = {}
        missing = False
        for backend, result in unique.items():
            fairness = result.fairness
            value = getattr(fairness, field) if fairness is not None else None
            values[backend] = value
            if value is None:
                missing = True
        controlled_fixture_world = (
            field == "world_seed"
            and len(unique) >= 2
            and all(value is None for value in values.values())
            and all(
                result.campaign_mode == "controlled"
                and result.fairness is not None
                and bool(result.fairness.fixture_selector)
                and bool(result.fairness.fixture_identity)
                for result in unique.values()
            )
        )
        if controlled_fixture_world:
            # Controlled Mode has no Minecraft world seed: the versioned,
            # non-empty fixture selector+identity is its complete world
            # identity.  Null is therefore explicit N/A, not missing data.
            status = "pass"
        elif len(unique) < 2 or missing:
            status = "unknown"
            any_unknown = True
        else:
            encoded = {
                json.dumps(value, sort_keys=True, default=str) for value in values.values()
            }
            status = "pass" if len(encoded) == 1 else "fail"
            if status == "fail":
                any_fail = True
        if field == "git_dirty" and any(value is True for value in values.values()):
            status = "fail"
            any_fail = True
        comparisons.append(
            FairnessFieldComparison(field=field, status=status, values=values)
        )

    verdict = "fail" if any_fail else "unknown" if any_unknown else "pass"
    return SameSeedComparison(
        scenario=anchor.scenario,
        seed=anchor.seed,
        campaign_mode=anchor.campaign_mode,
        params=dict(anchor.params),
        verdict=verdict,
        cells=cells,
        fairness_fields=comparisons,
    )
