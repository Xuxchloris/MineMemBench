from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from minemembench.core.fairness import FairnessRecord
from minemembench.core.models import ActionStatus, EventType, ExperienceEvent, Position
from minemembench.core.runner import RunLog, RunStep
from minemembench.dashboard.compare import build_same_seed_comparison
from minemembench.dashboard.index import ResultIndex
from minemembench.dashboard.replay import build_replay
from minemembench.dashboard.server import create_server
from minemembench.memory.base import MemoryItemSnapshot
from minemembench.scenarios.base import LifetimeGroundTruth, ScenarioResult

from .conftest import make_world_state


def _fairness(backend: str, *, system_hash: str = "system", dirty: bool = False) -> FairnessRecord:
    return FairnessRecord(
        checked_at=datetime(2026, 8, 9, tzinfo=UTC),
        minecraft_version="1.20.4",
        world_seed=123,
        planner_model="deepseek-test",
        temperature=0,
        system_prompt_hash=system_hash,
        tool_set_hash="tools",
        planner_user_template_hash="user-template",
        source_tree_fingerprint="source-fingerprint",
        source_file_count=120,
        git_available=True,
        git_commit="a" * 40,
        git_dirty=dirty,
        git_status_fingerprint="status",
        scenario="long_lived_memory",
        scenario_params={
            "lifetime_event_count": 8,
            "session_count": 2,
            "relevant_update_count": 1,
            "similar_event_count": 2,
            "lifetime_semantics_version": "lifetime_v1",
        },
        campaign_mode="controlled",
        fixture_selector="lifetime_route_v1",
        fixture_identity="fixture",
        run_seed=42,
        valid=True,
    )


def _result(
    backend: str = "vector",
    *,
    system_hash: str = "system",
    dirty: bool = False,
    include_secret: bool = False,
) -> ScenarioResult:
    target = Position(x=40, y=64, z=0)
    event = ExperienceEvent(
        event_id="target-event",
        episode_id=f"episode-{backend}",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        actor="agent",
        target="lifetime_token",
        event_type=EventType.RESOURCE_DISCOVERED,
        location=target,
        context={
            "subject": "old_field_cache",
            "x": 40,
            "y": 64,
            "z": 0,
            **({"api_key": "DASHBOARD-SECRET-SENTINEL"} if include_secret else {}),
        },
    )
    item = MemoryItemSnapshot(
        item_id="item",
        score=0.9,
        created_at=event.timestamp,
        event=event,
    )
    step = RunStep(
        index=0,
        position=target,
        world_state=make_world_state(),
        retrieved_memory_count=1,
        retrieved_items=[item],
        action="move_to",
        arguments={"x": 40, "y": 64, "z": 0},
        reason="navigate to remembered cache",
        action_status=ActionStatus.COMPLETED,
        action_result={"position": target.model_dump()},
        prompt_tokens=10,
        completion_tokens=5,
        latency_s=0.01,
    )
    log = RunLog(
        run_id=f"run-{backend}",
        memory_backend=backend,
        goal="Recover the lifetime token and deliver it to Steve.",
        model="deepseek-test",
        temperature=0,
        steps=[step],
        llm_calls=1,
        total_prompt_tokens=10,
        total_completion_tokens=5,
        success=False,
    )
    params = dict(_fairness(backend).scenario_params)
    return ScenarioResult(
        scenario="long_lived_memory",
        episode_id=f"episode-{backend}",
        seed=42,
        memory_backend=backend,
        success=True,
        campaign_mode="controlled",
        metrics={"task_success": 1, "unmeasured": None},
        run_log=log,
        params=params,
        fairness=_fairness(backend, system_hash=system_hash, dirty=dirty),
        injected_events=[event],
        evaluation_ground_truth=LifetimeGroundTruth(
            semantics_version="lifetime_v1",
            target_event_id=event.event_id,
            item_name="lifetime_token",
            pickup_position=target,
            recipient="Steve",
            recipient_position=Position(x=1, y=64, z=2),
        ),
    )


def _write_result(directory: Path, backend: str = "vector", **kwargs) -> Path:
    path = directory / f"scenario_long_lived_memory_{backend}_run.json"
    path.write_text(_result(backend, **kwargs).to_json(), encoding="utf-8")
    return path


def test_index_caches_unchanged_files_and_retains_last_good_partial(tmp_path) -> None:
    path = _write_result(tmp_path)
    index = ResultIndex(tmp_path)
    first = index.refresh()
    assert len(first.runs) == 1
    assert index.parse_count == 1
    assert index.refresh().revision == first.revision
    assert index.refresh() is first
    assert index.parse_count == 1

    path.write_text('{"scenario":', encoding="utf-8")
    partial = index.refresh()
    assert partial.partial_file_count == 1
    assert len(partial.runs) == 1
    assert partial.runs[0].stale is True
    assert partial.diagnostics[0].error_category == "partial_json"

    path.write_text(_result().to_json(), encoding="utf-8")
    repaired = index.refresh()
    assert repaired.partial_file_count == 0
    assert repaired.invalid_file_count == 0
    assert repaired.runs[0].stale is False


@pytest.mark.parametrize(
    "schema",
    [None, "controlled-campaign/v2", "controlled-campaign/v3", "controlled-campaign/v4"],
)
def test_index_reads_historical_manifest_shapes_without_rewriting(tmp_path, schema) -> None:
    directory = tmp_path / ((schema or "legacy").replace("/", "_"))
    directory.mkdir()
    payload = {
        "scenario": "delayed_recall",
        "mode": "controlled",
        "seeds": [42],
        "backends": ["none"],
        "runs": [{"status": "ok", "scenario_params": {"interference_count": 10}}],
    }
    if schema is not None:
        payload["schema_version"] = schema
    path = directory / "campaign_manifest.json"
    original = json.dumps(payload)
    path.write_text(original, encoding="utf-8")
    index = ResultIndex(tmp_path)
    snapshot = index.refresh()
    card = next(card for card in snapshot.campaigns if card.relative_path.startswith(directory.name))
    assert card.schema_version == schema
    assert card.ok_count == 1
    assert path.read_text(encoding="utf-8") == original


def test_campaign_overview_derives_live_matrix_progress_cost_and_provenance(
    tmp_path,
) -> None:
    result_path = _write_result(tmp_path, "vector")
    rejected_result_path = _write_result(tmp_path, "none")
    manifest = {
        "schema_version": "controlled-campaign/v4",
        "created_at": "2026-08-09T00:00:00+00:00",
        "mode": "controlled",
        "scenario": "long_lived_memory",
        "semantics_version": "lifetime_v1",
        "provenance": {
            "git_commit": "a" * 40,
            "source_tree_fingerprint": "source-fingerprint",
            "source_file_count": 120,
        },
        "seeds": [42],
        "backends": ["none", "vector", "mem0", "letta"],
        "cells": [
            {
                "name": "lifetime-8",
                "params": {"lifetime_event_count": 8},
                "effective_params": _result().params,
            }
        ],
        "runs": [
            {
                "cell": "lifetime-8",
                "backend": "vector",
                "status": "ok",
                "result_files": [str(result_path)],
            },
            {
                "cell": "lifetime-8",
                "backend": "none",
                "status": "failed",
                "result_files": [str(rejected_result_path)],
            },
            {
                "cell": "lifetime-8",
                "backend": "mem0",
                "status": "pending",
                "result_files": [],
            },
            {
                "cell": "lifetime-8",
                "backend": "letta",
                "status": "pending",
                "result_files": [],
            },
        ],
    }
    (tmp_path / "campaign_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    index = ResultIndex(tmp_path)
    snapshot = index.refresh()
    campaign = snapshot.campaigns[0]
    assert campaign.status == "failed"
    assert campaign.progress_percent == 50
    assert campaign.completed_count == 2
    assert campaign.remaining_count == 2
    assert campaign.error_count == 1
    assert campaign.git_commit == "a" * 40
    assert campaign.source_fingerprint == "source-fingerprint"
    assert campaign.total_tokens == 15
    vector = next(cell for cell in campaign.matrix if cell.backend == "vector")
    assert vector.valid_count == 1
    assert vector.success_rate == 1
    assert vector.total_tokens == 15
    rejected = next(cell for cell in campaign.matrix if cell.backend == "none")
    assert rejected.failed == 1
    assert rejected.valid_count == 0
    assert rejected.success_count == 0
    assert rejected.success_rate is None
    assert rejected.total_tokens is None
    assert all(run.campaign_id == campaign.campaign_id for run in snapshot.runs)
    rejected_run = next(
        run for run in snapshot.runs if run.memory_backend == "none"
    )
    assert rejected_run.producer_status == "failed"
    assert [
        result.memory_backend
        for _run_id, result in index.iter_runs(
            campaign_id=campaign.campaign_id, accepted_only=True
        )
    ] == ["vector"]


def test_fairness_invalid_ok_result_is_excluded_from_all_aggregates(tmp_path) -> None:
    invalid = _result("vector")
    assert invalid.fairness is not None
    invalid.fairness = invalid.fairness.model_copy(update={"valid": False})
    result_path = tmp_path / "scenario_long_lived_memory_vector_invalid.json"
    result_path.write_text(invalid.to_json(), encoding="utf-8")
    manifest = {
        "schema_version": "controlled-campaign/v4",
        "mode": "controlled",
        "scenario": "long_lived_memory",
        "seeds": [42],
        "backends": ["vector"],
        "cells": [
            {
                "name": "invalid",
                "params": {},
                "effective_params": invalid.params,
            }
        ],
        "runs": [
            {
                "cell": "invalid",
                "backend": "vector",
                "status": "ok",
                "result_files": [str(result_path)],
            }
        ],
    }
    (tmp_path / "campaign_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    campaign = ResultIndex(tmp_path).refresh().campaigns[0]
    assert campaign.invalid_count == 1
    cell = campaign.matrix[0]
    assert cell.valid_count == 0
    assert cell.invalid_count == 1
    assert cell.success_rate is None
    assert campaign.total_tokens is None
    assert campaign.mean_llm_latency_ms is None
    assert campaign.mean_retrieval_latency_ms is None
    assert campaign.mean_end_to_end_latency_ms is None


def test_same_treatment_compare_is_scoped_to_anchor_campaign(tmp_path) -> None:
    for campaign_name in ("campaign-a", "campaign-b"):
        directory = tmp_path / campaign_name
        directory.mkdir()
        manifest_runs = []
        for backend in ("none", "vector", "mem0", "letta"):
            result_path = _write_result(directory, backend)
            manifest_runs.append(
                {
                    "cell": "same",
                    "backend": backend,
                    "status": "ok",
                    "result_files": [str(result_path)],
                }
            )
        (directory / "campaign_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "controlled-campaign/v4",
                    "mode": "controlled",
                    "scenario": "long_lived_memory",
                    "semantics_version": "lifetime_v1",
                    "seeds": [42],
                    "backends": ["none", "vector", "mem0", "letta"],
                    "cells": [{"name": "same", "effective_params": _result().params}],
                    "runs": manifest_runs,
                }
            ),
            encoding="utf-8",
        )

    index = ResultIndex(tmp_path)
    snapshot = index.refresh()
    first_campaign = next(
        campaign
        for campaign in snapshot.campaigns
        if campaign.relative_path.startswith("campaign-a/")
    )
    anchor = next(
        run
        for run in snapshot.runs
        if run.campaign_id == first_campaign.campaign_id
        and run.memory_backend == "none"
    )
    scoped = build_same_seed_comparison(
        index.iter_runs(campaign_id=index.get_campaign_id(anchor.run_id)),
        anchor_run_id=anchor.run_id,
    )
    assert scoped is not None and scoped.verdict == "pass"
    assert all(cell.status == "present" for cell in scoped.cells)
    global_comparison = build_same_seed_comparison(
        index.iter_runs(), anchor_run_id=anchor.run_id
    )
    assert global_comparison is not None and global_comparison.verdict == "fail"
    assert all(cell.status == "duplicate" for cell in global_comparison.cells)

    server = create_server(tmp_path, port=0, poll_interval=0.1)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(
            base + f"/api/compare?anchor={anchor.run_id}", timeout=3
        ) as response:
            api_comparison = json.loads(response.read())
        assert api_comparison["verdict"] == "pass"
        assert all(cell["status"] == "present" for cell in api_comparison["cells"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_historical_result_without_new_multirun_fields_still_validates() -> None:
    payload = _result().model_dump(mode="json", exclude={"run_logs", "phase_records"})
    restored = ScenarioResult.model_validate(payload)
    assert restored.run_logs == []
    assert restored.phase_records == []


def test_replay_is_deterministic_and_separates_r_u_p_e() -> None:
    result = _result()
    first = build_replay(result)
    second = build_replay(result)
    assert first == second
    assert len(first.frames) == 1
    frame = first.frames[0]
    assert frame.retrieval.item_count == 1
    assert frame.utilization.status == "supported"
    assert frame.planner.action == "move_to"
    assert frame.outcome.status == "completed"
    assert len(first.trajectory) == 2
    assert first.available_memory[0]["event_id"] == "target-event"
    assert [event.kind for event in first.timeline] == [
        "memory_offered",
        "retrieve",
        "decide",
        "action",
        "outcome",
        "evaluation",
    ]
    assert first.frames[0].semantic_events == [
        "RETRIEVE · 1 item(s)",
        "DECIDE · move_to",
        "ACTION · move_to",
        "OUTCOME · completed",
    ]
    assert first.frames[0].world_state is not None
    assert first.terrain_reconstructed is False
    assert {marker.kind for marker in first.trajectory_markers} >= {
        "target",
        "action",
        "success",
    }
    assert first.attribution_counts == {"R": 1, "U": 1, "P": 1, "E": 1, "Unknown": 0}


def test_same_seed_compare_pass_fail_and_unknown() -> None:
    four = [(backend, _result(backend)) for backend in ("none", "vector", "mem0", "letta")]
    passed = build_same_seed_comparison(four, anchor_run_id="none")
    assert passed is not None and passed.verdict == "pass"
    vector = next(cell for cell in passed.cells if cell.backend == "vector")
    assert vector.retrieved_top_k[0]["event"]["event_id"] == "target-event"
    assert vector.first_action is not None
    assert vector.first_action["action"] == "move_to"
    assert vector.steps == 1
    assert vector.total_tokens == 15
    assert vector.replay_frames[0]["status"] == "completed"

    mismatched = list(four)
    mismatched[-1] = ("letta", _result("letta", system_hash="different"))
    failed = build_same_seed_comparison(mismatched, anchor_run_id="none")
    assert failed is not None and failed.verdict == "fail"
    assert next(field for field in failed.fairness_fields if field.field == "system_prompt_hash").status == "fail"

    missing = build_same_seed_comparison(four[:2], anchor_run_id="none")
    assert missing is not None and missing.verdict == "unknown"

    dirty = [(backend, _result(backend, dirty=True)) for backend in ("none", "vector", "mem0", "letta")]
    rejected = build_same_seed_comparison(dirty, anchor_run_id="none")
    assert rejected is not None and rejected.verdict == "fail"


def test_controlled_compare_treats_fixture_world_seed_as_explicit_na() -> None:
    runs: list[tuple[str, ScenarioResult]] = []
    for backend in ("none", "vector", "mem0", "letta"):
        result = _result(backend)
        assert result.fairness is not None
        fairness = result.fairness.model_copy(update={"world_seed": None})
        runs.append((backend, result.model_copy(update={"fairness": fairness})))

    comparison = build_same_seed_comparison(runs, anchor_run_id="none")
    assert comparison is not None and comparison.verdict == "pass"
    world_seed = next(
        field for field in comparison.fairness_fields if field.field == "world_seed"
    )
    assert world_seed.status == "pass"
    assert set(world_seed.values.values()) == {None}

    # Null remains Unknown when the versioned fixture identity is absent; this
    # preserves fail-closed loading for incomplete historical records.
    incomplete = list(runs)
    last_result = incomplete[-1][1]
    assert last_result.fairness is not None
    incomplete[-1] = (
        "letta",
        last_result.model_copy(
            update={
                "fairness": last_result.fairness.model_copy(
                    update={"fixture_identity": None}
                )
            }
        ),
    )
    unknown = build_same_seed_comparison(incomplete, anchor_run_id="none")
    assert unknown is not None and unknown.verdict == "unknown"
    assert next(
        field for field in unknown.fairness_fields if field.field == "world_seed"
    ).status == "unknown"


def test_dashboard_api_is_read_only_sanitized_and_traversal_safe(tmp_path) -> None:
    _write_result(tmp_path, include_secret=True)
    adjacent_env = tmp_path / ".env"
    adjacent_env.write_text("API_KEY=ENV-SECRET-SENTINEL", encoding="utf-8")
    server = create_server(tmp_path, port=0, poll_interval=0.1)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/snapshot", timeout=3) as response:
            snapshot_bytes = response.read()
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["Content-Security-Policy"]
        snapshot = json.loads(snapshot_bytes)
        run_id = snapshot["runs"][0]["run_id"]
        with urllib.request.urlopen(base + f"/api/runs/{run_id}", timeout=3) as response:
            detail = response.read()
        assert b"DASHBOARD-SECRET-SENTINEL" not in detail
        assert b"ENV-SECRET-SENTINEL" not in snapshot_bytes + detail
        assert b"[REDACTED]" in detail

        with pytest.raises(urllib.error.HTTPError) as traversal:
            urllib.request.urlopen(base + "/api/runs/..%2F..%2F.env", timeout=3)
        assert traversal.value.code == 404

        request = urllib.request.Request(base + "/api/snapshot", method="POST")
        with pytest.raises(urllib.error.HTTPError) as method:
            urllib.request.urlopen(request, timeout=3)
        assert method.value.code == 405
        assert adjacent_env.read_text(encoding="utf-8") == "API_KEY=ENV-SECRET-SENTINEL"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_large_synthetic_tree_uses_mtime_cache_without_reparse(tmp_path) -> None:
    for index in range(120):
        directory = tmp_path / f"campaign-{index // 20}" / f"cell-{index // 5}"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"scenario_long_lived_memory_vector_{index}.json"
        payload = _result().model_copy(
            update={"episode_id": f"episode-{index}", "seed": index}
        )
        path.write_text(payload.to_json(), encoding="utf-8")

    started = time.perf_counter()
    index = ResultIndex(tmp_path)
    first = index.refresh()
    cold_s = time.perf_counter() - started
    assert len(first.runs) == 120
    assert index.parse_count == 120
    parsed = index.parse_count

    started = time.perf_counter()
    second = index.refresh()
    cached_s = time.perf_counter() - started
    assert index.parse_count == parsed
    assert second.revision == first.revision
    # Generous regression guards: correctness relies on zero reparses; these
    # only catch accidental quadratic scans on ordinary test hardware.
    assert cold_s < 10
    assert cached_s < 5


def test_index_refresh_and_run_lookup_are_atomic_for_sse_threads(tmp_path) -> None:
    for number in range(24):
        path = tmp_path / f"scenario_long_lived_memory_vector_{number}.json"
        path.write_text(
            _result().model_copy(
                update={"episode_id": f"atomic-{number}", "seed": number}
            ).to_json(),
            encoding="utf-8",
        )
    index = ResultIndex(tmp_path)
    snapshot = index.refresh()
    run_ids = [card.run_id for card in snapshot.runs]

    def refresh_many() -> None:
        for _ in range(40):
            index.refresh()

    def lookup_many() -> None:
        for _ in range(80):
            assert all(index.get_run(run_id) is not None for run_id in run_ids)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(refresh_many),
            executor.submit(refresh_many),
            executor.submit(lookup_many),
            executor.submit(lookup_many),
        ]
        for future in futures:
            future.result(timeout=15)


def test_dashboard_static_mvp_exposes_campaign_replay_and_compare_controls() -> None:
    static = (
        Path(__file__).resolve().parents[1]
        / "minemembench"
        / "dashboard"
        / "static"
    )
    html = (static / "index.html").read_text(encoding="utf-8")
    javascript = (static / "app.js").read_text(encoding="utf-8")
    for required in (
        'id="campaigns"',
        'id="memory-history"',
        'id="observed-actions"',
        'id="timeline"',
        'id="seek"',
        'id="speed"',
        '<option value="0.5">0.5×</option>',
        '<option value="2">2×</option>',
        'id="trajectory"',
        'id="compare"',
    ):
        assert required in html
    for required in (
        "matrixTable",
        "renderTimeline",
        "WORLDSTATE / INVENTORY AT DECISION",
        "Retrieved top-k",
        "Side-by-side replay timeline",
        "trajectory_disclaimer",
    ):
        assert required in javascript
