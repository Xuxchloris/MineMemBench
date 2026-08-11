"""Synthetic, network-free acceptance tests for frozen Formal V1 analysis."""

from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import pytest

from minemembench.evaluation.formal_m15 import (
    DEFAULT_SPEC,
    FormalCell,
    FormalIntegrityError,
    FormalStudySpec,
    analyze_formal,
    cell_rows,
    classify_failure,
    exact_mcnemar_p,
    failure_point,
    holm_adjust,
    load_formal_dataset,
    paired_bootstrap_ci,
    pairwise_rows,
    retrieval_evidence,
)
from minemembench.scenarios.base import ScenarioResult

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_controlled_campaign as campaign  # noqa: E402
import run_formal_m15_v1 as producer  # noqa: E402

NOW = datetime(2026, 8, 11, tzinfo=UTC).isoformat().replace("+00:00", "Z")
COMMIT = "b" * 40
FINGERPRINT = "a" * 64
STATUS_FINGERPRINT = "c" * 64


def test_frozen_production_plan_is_exactly_320_runs() -> None:
    assert DEFAULT_SPEC.expected_runs == 320
    assert DEFAULT_SPEC.study_id == "m15-formal-v1-controlled-20260811-attempt2"
    assert DEFAULT_SPEC.seeds == tuple(range(1011, 1021))
    assert DEFAULT_SPEC.backends == ("none", "vector", "mem0", "letta")
    assert [cell.name for cell in DEFAULT_SPEC.cells] == [
        "delayed_200_20",
        "world_update_depth3",
        "noise_10",
        "noise_30",
        "noise_50",
        "lifetime_l1",
        "lifetime_l2",
        "lifetime_l3",
    ]


def test_every_frozen_cell_passes_real_campaign_preflight(tmp_path: Path) -> None:
    total = 0
    for scenario in DEFAULT_SPEC.scenarios:
        cells = [cell for cell in DEFAULT_SPEC.cells if cell.scenario == scenario]
        args = Namespace(
            scenario=scenario,
            seeds=",".join(str(seed) for seed in DEFAULT_SPEC.seeds),
            backends=",".join(DEFAULT_SPEC.backends),
            cell=[
                json.dumps({"name": cell.name, "params": dict(cell.params)})
                for cell in cells
            ],
        )
        plan, error = campaign.prepare_campaign(args)
        assert error is None
        assert plan is not None
        schedule = campaign.build_schedule(
            cells=plan["cells"],
            backends=plan["backends"],
            seeds=plan["seeds"],
            python=sys.executable,
            results_dir=tmp_path / scenario,
            scenario=scenario,
        )
        total += len(schedule)
        assert all(entry["expected_health_mode"] == "mock" for entry in schedule)
        assert all(entry["fixture_identity"] for entry in schedule)
    assert total == 320


def _spec() -> FormalStudySpec:
    cell = FormalCell(
        name="synthetic_delayed",
        scenario="delayed_recall",
        semantics_param="recall_semantics_version",
        semantics_version="entity_key_v2",
        params={
            "interference_count": 200,
            "similar_distractor_count": 20,
            "recall_semantics_version": "entity_key_v2",
        },
        order=0,
    )
    return FormalStudySpec(
        study_id="synthetic-formal-v1",
        backends=("none", "vector", "mem0", "letta"),
        seeds=(1001, 1002),
        cells=(cell,),
    )


def _producer() -> dict[str, object]:
    return {
        "source_tree_fingerprint": FINGERPRINT,
        "source_file_count": 3,
        "git_available": True,
        "git_commit": COMMIT,
        "git_dirty": False,
        "git_status_fingerprint": STATUS_FINGERPRINT,
    }


def _planner() -> dict[str, object]:
    return {
        "model": "test-model",
        "temperature": 0.0,
        "system_prompt_hash": "system",
        "tool_set_hash": "tools",
        "planner_user_template_hash": "template",
        "retrieval_limit": 10,
    }


def _event(seed: int, episode: str) -> dict[str, object]:
    return {
        "event_id": f"target-{seed}",
        "episode_id": episode,
        "timestamp": "2026-08-11T00:00:00Z",
        "actor": "instructor",
        "target": "cache",
        "event_type": "location_discovered",
        "location": None,
        "context": {
            "entity_key": f"cache-{seed}",
            "x": 8.0,
            "y": 64.0,
            "z": 0.0,
        },
        "outcome": "observed",
        "raw_events": [],
    }


def _result(
    *,
    spec: FormalStudySpec,
    backend: str,
    seed: int,
    success: bool,
    retrieval: bool,
    environment_failure: bool = False,
) -> dict[str, object]:
    cell = spec.cells[0]
    episode = f"episode-{backend}-{seed}"
    event = _event(seed, episode)
    retrieved = (
        [
            {
                "item_id": f"item-{backend}-{seed}",
                "score": 1.0,
                "created_at": "2026-08-11T00:00:01Z",
                "metadata": {},
                "event": event,
            }
        ]
        if retrieval
        else []
    )
    if success or environment_failure:
        action = "move_to"
        arguments = {"x": 8.0, "y": 64.0, "z": 0.0}
        status = "failed" if environment_failure else "completed"
    else:
        action = "wait"
        arguments = {"seconds": 1}
        status = "completed"
    step = {
        "index": 0,
        "position": {"x": 8.0 if success else 0.0, "y": 64.0, "z": 0.0},
        "retrieved_memory_count": len(retrieved),
        "retrieved_items": retrieved,
        "action": action,
        "arguments": arguments,
        "reason": "synthetic reason ignored by attribution",
        "action_status": status,
        "action_error": "adapter failed" if environment_failure else None,
        "action_result": None,
        "prompt_tokens": 10,
        "completion_tokens": 2,
        "latency_s": 0.1,
    }
    run_log = {
        "run_id": f"run-{backend}-{seed}",
        "memory_backend": backend,
        "goal": "Return to the learned cache.",
        "model": "test-model",
        "temperature": 0.0,
        "steps": [step],
        "llm_calls": 1,
        "total_prompt_tokens": 10,
        "total_completion_tokens": 2,
        "success": success,
        "collected_event_count": 0,
    }
    fairness = {
        "checked_at": NOW,
        "minecraft_version": "mock",
        "world_seed": None,
        "planner_model": "test-model",
        "temperature": 0.0,
        "system_prompt_hash": "system",
        "tool_set_hash": "tools",
        "planner_user_template_hash": "template",
        **_producer(),
        "scenario": cell.scenario,
        "scenario_params": dict(cell.params),
        "campaign_mode": "controlled",
        "fixture_selector": "canonical",
        "fixture_identity": "synthetic-fixture",
        "run_seed": seed,
        "reset_episode": episode,
        "reset_performed": True,
        "reset_error": None,
        "post_reset_items": 0,
        "fresh_scope_episode": f"fresh-{backend}-{seed}",
        "fresh_scope_items": 0,
        "probe_query": "probe",
        "valid": True,
        "invalid_reason": None,
    }
    return {
        "scenario": cell.scenario,
        "episode_id": episode,
        "seed": seed,
        "memory_backend": backend,
        "success": success,
        "campaign_mode": "controlled",
        "metrics": {
            "task_success": int(success),
            "target_recall": int(retrieval),
            "fact_retrieval_rank": 1 if retrieval else None,
            "total_prompt_tokens": 10,
            "total_completion_tokens": 2,
            "llm_calls": 1,
            "avg_add_latency_ms": 1.0,
            "avg_retrieve_latency_ms": 2.0,
        },
        "run_log": run_log,
        "params": dict(cell.params),
        "fairness": fairness,
        "retrieval_probes": [],
        "injected_events": [event],
        "evaluation_ground_truth": {
            "semantics_version": "entity_key_v2",
            "target_event_id": f"target-{seed}",
            "target_entity_key": f"cache-{seed}",
            "distractor_event_ids": [],
        },
        "observed_action_results": [],
        "phase_records": [],
        "run_logs": [],
    }


def _write_fixture(
    root: Path,
    *,
    outcomes: Callable[[str, int], bool] | None = None,
) -> FormalStudySpec:
    spec = _spec()
    outcomes = outcomes or (lambda backend, seed: backend != "none")
    campaign_dir = root / "delayed_recall"
    campaign_dir.mkdir(parents=True)
    entries: list[dict[str, object]] = []
    for index, (seed, backend) in enumerate(
        (seed, backend) for seed in spec.seeds for backend in spec.backends
    ):
        retrieval = backend != "none"
        result = _result(
            spec=spec,
            backend=backend,
            seed=seed,
            success=outcomes(backend, seed),
            retrieval=retrieval,
        )
        result_path = campaign_dir / f"scenario_delayed_recall_{backend}_{seed}.json"
        result_path.write_text(json.dumps(result), encoding="utf-8")
        entries.append(
            {
                "index": index,
                "scenario": "delayed_recall",
                "seed": seed,
                "backend": backend,
                "cell": spec.cells[0].name,
                "requested_params": dict(spec.cells[0].params),
                "effective_params": dict(spec.cells[0].params),
                "fixture_selector": "canonical",
                "fixture_identity": "synthetic-fixture",
                "expected_health_mode": "mock",
                "health_mode": "mock",
                "status": "ok",
                "returncode": 0,
                "result_files": [str(result_path.resolve())],
            }
        )
    campaign = {
        "schema_version": "controlled-campaign/v4",
        "mode": "controlled",
        "scenario": "delayed_recall",
        "semantics_version": "entity_key_v2",
        "results_dir": str(campaign_dir.resolve()),
        "provenance": _producer(),
        "seeds": list(spec.seeds),
        "backends": list(spec.backends),
        "cells": [
            {
                "name": spec.cells[0].name,
                "params": dict(spec.cells[0].params),
                "effective_params": dict(spec.cells[0].params),
            }
        ],
        "fixtures": [["canonical", "synthetic-fixture"]],
        "runs": entries,
    }
    (campaign_dir / "campaign_manifest.json").write_text(
        json.dumps(campaign), encoding="utf-8"
    )
    study = {
        "schema_version": "minemembench-formal-study/v1",
        "study_id": spec.study_id,
        "mode": "controlled",
        "results_dir": str(root.resolve()),
        "producer": _producer(),
        "planner": _planner(),
        "preregistration": {"path": "synthetic-prereg.md", "sha256": "1" * 64},
        "analysis": {"path": "synthetic-analysis.py", "sha256": "2" * 64},
        "plan": spec.plan_dict(),
        "expected_runs": spec.expected_runs,
        "campaigns": [
            {
                "scenario": "delayed_recall",
                "relative_dir": "delayed_recall",
                "expected_runs": spec.expected_runs,
                "cells": [spec.cells[0].plan_dict()],
                "status": "complete",
                "returncode": 0,
            }
        ],
        "status": "complete",
        "started_runs": spec.expected_runs,
        "actual_runs": spec.expected_runs,
        "retries": 0,
        "exclusions": 0,
    }
    (root / "formal_study_manifest.json").write_text(
        json.dumps(study), encoding="utf-8"
    )
    return spec


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_synthetic_all_success_and_all_failure(tmp_path: Path) -> None:
    all_success = tmp_path / "all_success"
    all_success.mkdir()
    spec = _write_fixture(all_success, outcomes=lambda _backend, _seed: True)
    dataset = load_formal_dataset(all_success, spec=spec)
    assert all(row["success_n"] == 2 for row in cell_rows(dataset, spec))

    all_failure = tmp_path / "all_failure"
    all_failure.mkdir()
    spec = _write_fixture(all_failure, outcomes=lambda _backend, _seed: False)
    dataset = load_formal_dataset(all_failure, spec=spec)
    assert all(row["success_n"] == 0 for row in cell_rows(dataset, spec))


def test_synthetic_analysis_writes_all_required_outputs(tmp_path: Path) -> None:
    root = tmp_path / "outputs"
    root.mkdir()
    spec = _write_fixture(root)
    paths = analyze_formal(root, spec=spec)
    assert set(paths) == {
        "summary",
        "runs",
        "cells",
        "pairwise",
        "failure_points",
        "failure_attribution",
        "report",
        "success_curves",
        "retrieval_curves",
    }
    assert all(path.is_file() and path.stat().st_size > 0 for path in paths.values())
    summary = _json(paths["summary"])
    assert summary["integrity"]["verdict"] == "PASS"  # type: ignore[index]


def test_paired_disagreement_and_exact_mcnemar(tmp_path: Path) -> None:
    root = tmp_path / "paired"
    root.mkdir()
    spec = _write_fixture(
        root,
        outcomes=lambda backend, seed: backend in {"vector", "letta"}
        or (backend == "mem0" and seed == 1002),
    )
    rows = pairwise_rows(load_formal_dataset(root, spec=spec), spec)
    vector_mem0 = next(row for row in rows if row["backend_a"] == "vector" and row["backend_b"] == "mem0")
    assert vector_mem0["a_success_b_failure"] == 1
    assert vector_mem0["a_failure_b_success"] == 0
    assert vector_mem0["exact_mcnemar_p"] == 1.0
    assert exact_mcnemar_p(10, 0) == pytest.approx(2 / 1024)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_seed", "manifest run count mismatch"),
        ("duplicate_seed", "manifest run count mismatch"),
        ("wrong_commit", "result producer provenance mismatch"),
        ("wrong_fingerprint", "result producer provenance mismatch"),
        ("wrong_cell", "result params mismatch"),
        ("fairness_invalid", "fairness invalid"),
        ("wrong_expected_runs", "formal expected_runs mismatch"),
    ],
)
def test_integrity_mismatches_fail_closed(tmp_path: Path, mutation: str, message: str) -> None:
    root = tmp_path / mutation
    root.mkdir()
    spec = _write_fixture(root)
    campaign_path = root / "delayed_recall" / "campaign_manifest.json"
    campaign = _json(campaign_path)
    first_file = Path(str(campaign["runs"][0]["result_files"][0]))  # type: ignore[index]
    result = _json(first_file)
    if mutation == "missing_seed":
        removed = campaign["runs"].pop()  # type: ignore[union-attr]
        Path(str(removed["result_files"][0])).unlink()
        _save(campaign_path, campaign)
    elif mutation == "duplicate_seed":
        campaign["runs"].append(dict(campaign["runs"][0]))  # type: ignore[union-attr,index]
        _save(campaign_path, campaign)
    elif mutation == "wrong_commit":
        result["fairness"]["git_commit"] = "d" * 40  # type: ignore[index]
        _save(first_file, result)
    elif mutation == "wrong_fingerprint":
        result["fairness"]["source_tree_fingerprint"] = "d" * 64  # type: ignore[index]
        _save(first_file, result)
    elif mutation == "wrong_cell":
        result["params"]["interference_count"] = 201  # type: ignore[index]
        _save(first_file, result)
    elif mutation == "fairness_invalid":
        result["fairness"]["valid"] = False  # type: ignore[index]
        result["fairness"]["invalid_reason"] = "synthetic contamination"  # type: ignore[index]
        _save(first_file, result)
    elif mutation == "wrong_expected_runs":
        study_path = root / "formal_study_manifest.json"
        study = _json(study_path)
        study["expected_runs"] = spec.expected_runs + 1
        _save(study_path, study)
    with pytest.raises(FormalIntegrityError, match=message):
        load_formal_dataset(root, spec=spec)


def test_failure_attribution_R_P_E_ignores_reason_text() -> None:
    spec = _spec()
    retrieval_failure = ScenarioResult.model_validate(
        _result(spec=spec, backend="none", seed=1001, success=False, retrieval=False)
    )
    present_wrong_action = ScenarioResult.model_validate(
        _result(spec=spec, backend="vector", seed=1001, success=False, retrieval=True)
    )
    environment_failure = ScenarioResult.model_validate(
        _result(
            spec=spec,
            backend="vector",
            seed=1001,
            success=False,
            retrieval=True,
            environment_failure=True,
        )
    )
    assert classify_failure(retrieval_failure, retrieval_evidence(retrieval_failure)[0]) == "R"
    assert classify_failure(present_wrong_action, retrieval_evidence(present_wrong_action)[0]) == "P"
    assert classify_failure(environment_failure, retrieval_evidence(environment_failure)[0]) == "E"


def test_target_position_fails_closed_on_context_location_contradiction() -> None:
    spec = _spec()
    raw = _result(
        spec=spec,
        backend="vector",
        seed=1001,
        success=False,
        retrieval=True,
    )
    raw["injected_events"][0]["location"] = {  # type: ignore[index]
        "x": 99.0,
        "y": 64.0,
        "z": 0.0,
    }
    result = ScenarioResult.model_validate(raw)
    with pytest.raises(FormalIntegrityError, match="contradicts typed context"):
        classify_failure(result, retrieval_present=True)


def test_failure_point_none_first_and_middle() -> None:
    assert failure_point([("10", 8, 10), ("30", 8, 10), ("50", 8, 10)]) is None
    assert failure_point([("10", 7, 10), ("30", 10, 10), ("50", 10, 10)]) == "10"
    assert failure_point([("10", 8, 10), ("30", 7, 10), ("50", 10, 10)]) == "30"


def test_holm_and_bootstrap_are_deterministic() -> None:
    adjusted = holm_adjust([0.01, 0.04, 0.03])
    assert adjusted == pytest.approx([0.03, 0.06, 0.06])
    first = paired_bootstrap_ci([1, 1, 0, 1], [0, 1, 0, 0], resamples=1000)
    second = paired_bootstrap_ci([1, 1, 0, 1], [0, 1, 0, 0], resamples=1000)
    assert first == second
    assert first[0] <= 0.5 <= first[1]


def test_formal_producer_rejects_wrong_freeze_before_output(tmp_path: Path) -> None:
    results_dir = tmp_path / "must-not-exist"
    repo_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "run_formal_m15_v1.py"),
            "--results-dir",
            str(results_dir),
            "--expected-git-commit",
            "0" * 40,
            "--expected-source-fingerprint",
            "0" * 64,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "formal preflight failed" in completed.stderr
    assert not results_dir.exists()


def test_formal_producer_counts_failed_attempt_separately(tmp_path: Path) -> None:
    campaign_dir = tmp_path / "long_lived_memory"
    campaign_dir.mkdir()
    (campaign_dir / "campaign_manifest.json").write_text(
        json.dumps(
            {
                "runs": [
                    {"status": "ok"},
                    {"status": "failed"},
                    {"status": "pending"},
                ]
            }
        ),
        encoding="utf-8",
    )
    campaigns = [
        {"relative_dir": "long_lived_memory"},
        {"relative_dir": "not_started"},
    ]
    assert producer._count_campaign_statuses(tmp_path, campaigns) == (1, 2)
