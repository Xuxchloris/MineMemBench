"""Recursive, cached, read-only index over raw benchmark evidence."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from pydantic import ValidationError

from ..scenarios.base import ScenarioResult
from .models import (
    CampaignCard,
    CampaignCellSummary,
    CampaignMatrixCell,
    FileDiagnostic,
    IndexSnapshot,
    RunCard,
)


@dataclass
class _CacheEntry:
    signature: tuple[int, int]
    kind: Literal["result", "manifest"]
    value: ScenarioResult | dict[str, Any] | None
    partial: bool = False
    stale: bool = False
    invalid: bool = False
    error_category: str | None = None


def _opaque_id(relative_path: str) -> str:
    return hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:24]


def _semantics_version(result: ScenarioResult) -> str | None:
    ground_truth = result.evaluation_ground_truth
    if ground_truth is not None:
        return str(ground_truth.semantics_version)
    for key in (
        "lifetime_semantics_version",
        "failure_semantics_version",
        "noise_semantics_version",
        "update_semantics_version",
        "recall_semantics_version",
    ):
        value = result.params.get(key)
        if isinstance(value, str):
            return value
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _result_measurements(result: ScenarioResult) -> dict[str, int | float | None]:
    logs = (
        [entry.run_log for entry in result.run_logs]
        if result.run_logs
        else ([result.run_log] if result.run_log is not None else [])
    )
    prompt = sum(log.total_prompt_tokens for log in logs) if logs else None
    completion = (
        sum(log.total_completion_tokens for log in logs) if logs else None
    )
    llm_latency = (
        round(
            sum(step.latency_s for log in logs for step in log.steps) * 1000,
            4,
        )
        if logs
        else None
    )
    retrieval = _number(result.metrics.get("avg_retrieve_latency_ms"))
    end_to_end = _number(result.metrics.get("end_to_end_latency_ms"))
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": (
            prompt + completion
            if prompt is not None and completion is not None
            else None
        ),
        "llm_latency_ms": llm_latency,
        "retrieval_latency_ms": retrieval,
        "end_to_end_latency_ms": end_to_end,
    }


def _summary_values(
    records: list[tuple[dict[str, Any], ScenarioResult | None]],
) -> dict[str, Any]:
    statuses = [
        entry.get("status") if isinstance(entry.get("status"), str) else "pending"
        for entry, _result in records
    ]
    # A producer may leave a parseable result behind when the manifest rejects
    # the run (source/input/fairness mismatch, nonzero process, etc.). Preserve
    # that failed evidence in status counts, but never admit it to research
    # success/cost aggregates.
    results = [
        result
        for entry, result in records
        if entry.get("status") == "ok" and result is not None
    ]
    valid_results = [
        result
        for result in results
        if result.fairness is not None and result.fairness.valid
    ]
    invalid_results = [
        result
        for result in results
        if result.fairness is not None and not result.fairness.valid
    ]
    # Costs and latency are research aggregates too: a run that failed
    # fairness validation must remain inspectable but cannot contribute any
    # pooled measurement.
    measurements = [_result_measurements(result) for result in valid_results]
    prompt_values = [
        int(value)
        for item in measurements
        if (value := item["prompt_tokens"]) is not None
    ]
    completion_values = [
        int(value)
        for item in measurements
        if (value := item["completion_tokens"]) is not None
    ]
    llm_values = [
        float(value)
        for item in measurements
        if (value := item["llm_latency_ms"]) is not None
    ]
    retrieval_values = [
        float(value)
        for item in measurements
        if (value := item["retrieval_latency_ms"]) is not None
    ]
    end_to_end_values = [
        float(value)
        for item in measurements
        if (value := item["end_to_end_latency_ms"]) is not None
    ]
    success_count = sum(result.success for result in valid_results)
    prompt = sum(prompt_values) if prompt_values else None
    completion = sum(completion_values) if completion_values else None
    return {
        "scheduled": len(records),
        "completed": statuses.count("ok") + statuses.count("failed"),
        "ok": statuses.count("ok"),
        "failed": statuses.count("failed"),
        "pending": statuses.count("pending"),
        "success_count": success_count,
        "success_rate": (
            round(success_count / len(valid_results), 4)
            if valid_results
            else None
        ),
        "valid_count": len(valid_results),
        "invalid_count": len(invalid_results),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": (
            prompt + completion
            if prompt is not None and completion is not None
            else None
        ),
        "mean_llm_latency_ms": _mean(llm_values),
        "mean_retrieval_latency_ms": _mean(retrieval_values),
        "mean_end_to_end_latency_ms": _mean(end_to_end_values),
    }


class ResultIndex:
    """Index known evidence files without ever mutating the results tree."""

    def __init__(self, results_dir: str | Path) -> None:
        self.root = Path(results_dir).resolve()
        self._cache: dict[Path, _CacheEntry] = {}
        self._run_ids: dict[str, Path] = {}
        self._manifest_ids: dict[str, Path] = {}
        self._campaign_by_run_id: dict[str, str] = {}
        self._producer_status_by_run_id: dict[str, str] = {}
        self._lock = RLock()
        self.parse_count = 0
        self._last_snapshot: IndexSnapshot | None = None

    def _relative(self, path: Path) -> str | None:
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except (OSError, ValueError):
            return None

    def _discover(self) -> list[tuple[Path, Literal["result", "manifest"]]]:
        if not self.root.is_dir():
            return []
        discovered: list[tuple[Path, Literal["result", "manifest"]]] = []
        skipped = {
            "stores",
            "logs",
            "report",
            "__pycache__",
            ".git",
            ".venv",
            "node_modules",
            "server",
        }
        for directory, dirnames, filenames in os.walk(
            self.root, followlinks=False
        ):
            parent = Path(directory)
            dirnames[:] = [
                name
                for name in dirnames
                if name not in skipped
                and not name.startswith(".")
                and not (parent / name).is_symlink()
            ]
            for filename in filenames:
                kind: Literal["result", "manifest"] | None = None
                if filename.startswith("scenario_") and filename.endswith(".json"):
                    kind = "result"
                elif filename == "campaign_manifest.json":
                    kind = "manifest"
                if kind is None:
                    continue
                path = parent / filename
                if not path.is_file() or self._relative(path) is None:
                    continue
                discovered.append((path.resolve(), kind))
        return sorted(
            discovered, key=lambda pair: self._relative(pair[0]) or ""
        )

    def _parse(
        self,
        path: Path,
        kind: Literal["result", "manifest"],
        signature: tuple[int, int],
    ) -> _CacheEntry:
        previous = self._cache.get(path)
        self.parse_count += 1
        try:
            text = path.read_text(encoding="utf-8")
            if kind == "result":
                raw_result = json.loads(text)
                value: ScenarioResult | dict[str, Any] = (
                    ScenarioResult.model_validate(raw_result)
                )
            else:
                raw = json.loads(text)
                if not isinstance(raw, dict):
                    raise TypeError("manifest root is not an object")
                value = raw
            return _CacheEntry(signature=signature, kind=kind, value=value)
        except json.JSONDecodeError:
            return _CacheEntry(
                signature=signature,
                kind=kind,
                value=previous.value if previous is not None else None,
                partial=True,
                stale=previous is not None and previous.value is not None,
                error_category="partial_json",
            )
        except ValidationError:
            return _CacheEntry(
                signature=signature,
                kind=kind,
                value=previous.value if previous is not None else None,
                stale=previous is not None and previous.value is not None,
                invalid=True,
                error_category="schema_invalid",
            )
        except (OSError, UnicodeError, TypeError):
            return _CacheEntry(
                signature=signature,
                kind=kind,
                value=previous.value if previous is not None else None,
                stale=previous is not None and previous.value is not None,
                invalid=True,
                error_category="read_invalid",
            )

    def _manifest_result(
        self,
        manifest_path: Path,
        raw_entry: dict[str, Any],
        results_by_path: dict[Path, ScenarioResult],
        results_by_name: dict[str, list[tuple[Path, ScenarioResult]]],
    ) -> tuple[Path, ScenarioResult] | None:
        raw_files = raw_entry.get("result_files")
        files = raw_files if isinstance(raw_files, list) else []
        for raw in files:
            if not isinstance(raw, str) or not raw:
                continue
            supplied = Path(raw)
            candidates = (
                [supplied.resolve()]
                if supplied.is_absolute()
                else [
                    (manifest_path.parent / supplied).resolve(),
                    (self.root / supplied).resolve(),
                    (manifest_path.parent / supplied.name).resolve(),
                ]
            )
            for candidate in candidates:
                result = results_by_path.get(candidate)
                if result is not None:
                    return candidate, result
            matching = results_by_name.get(supplied.name, [])
            if len(matching) == 1:
                return matching[0]
        return None

    def refresh(self) -> IndexSnapshot:
        """Atomically refresh mappings for concurrent HTTP/SSE readers."""

        with self._lock:
            return self._refresh_unlocked()

    def _refresh_unlocked(self) -> IndexSnapshot:
        discovered = self._discover()
        present = {path for path, _kind in discovered}
        changed = present != set(self._cache)
        self._cache = {
            path: entry for path, entry in self._cache.items() if path in present
        }
        for path, kind in discovered:
            try:
                stat = path.stat()
            except OSError:
                continue
            signature = (stat.st_mtime_ns, stat.st_size)
            cached = self._cache.get(path)
            if cached is None or cached.signature != signature:
                changed = True
                self._cache[path] = self._parse(path, kind, signature)

        # The prior snapshot and opaque-id maps are immutable from the
        # reader's perspective.  When discovery/signatures are unchanged,
        # reuse them instead of rebuilding hundreds/thousands of Pydantic
        # cards for every SSE/detail request.
        if not changed and self._last_snapshot is not None:
            return self._last_snapshot

        diagnostics: list[FileDiagnostic] = []
        runs: list[RunCard] = []
        campaigns: list[CampaignCard] = []
        self._run_ids = {}
        self._manifest_ids = {}
        revision_rows: list[str] = []
        results_by_path: dict[Path, ScenarioResult] = {}
        results_by_name: dict[str, list[tuple[Path, ScenarioResult]]] = {}
        manifests: list[tuple[Path, _CacheEntry, str, dict[str, Any]]] = []

        for path, entry in sorted(
            self._cache.items(), key=lambda pair: self._relative(pair[0]) or ""
        ):
            relative = self._relative(path)
            if relative is None:
                continue
            file_id = _opaque_id(relative)
            revision_rows.append(
                f"{relative}|{entry.signature[0]}|{entry.signature[1]}|"
                f"{entry.partial}|{entry.stale}|{entry.invalid}|"
                f"{entry.error_category}"
            )
            if entry.partial or entry.invalid:
                diagnostics.append(
                    FileDiagnostic(
                        file_id=file_id,
                        relative_path=relative,
                        kind=entry.kind,
                        partial=entry.partial,
                        stale=entry.stale,
                        invalid=entry.invalid,
                        error_category=entry.error_category,
                    )
                )
            if entry.kind == "result" and isinstance(entry.value, ScenarioResult):
                result = entry.value
                self._run_ids[file_id] = path
                results_by_path[path] = result
                results_by_name.setdefault(path.name, []).append((path, result))
                fairness = result.fairness
                measurement = _result_measurements(result)
                primary_log = result.run_log
                runs.append(
                    RunCard(
                        run_id=file_id,
                        relative_path=relative,
                        scenario=result.scenario,
                        seed=result.seed,
                        memory_backend=result.memory_backend,
                        success=result.success,
                        campaign_mode=result.campaign_mode,
                        params=dict(result.params),
                        semantics_version=_semantics_version(result),
                        git_commit=(fairness.git_commit if fairness else None),
                        source_fingerprint=(
                            fairness.source_tree_fingerprint if fairness else None
                        ),
                        model=(primary_log.model if primary_log else None),
                        temperature=(
                            primary_log.temperature if primary_log else None
                        ),
                        **measurement,
                        fairness_valid=(fairness.valid if fairness else None),
                        fairness_invalid_reason=(
                            fairness.invalid_reason if fairness else None
                        ),
                        metrics=dict(result.metrics),
                        partial=entry.partial,
                        stale=entry.stale,
                    )
                )
            elif entry.kind == "manifest" and isinstance(entry.value, dict):
                self._manifest_ids[file_id] = path
                manifests.append((path, entry, file_id, entry.value))

        campaign_assignments: dict[str, str] = {}
        producer_records: dict[str, list[dict[str, Any]]] = {}
        for path, entry, campaign_id, manifest in manifests:
            raw_runs = manifest.get("runs")
            manifest_runs = [
                run for run in raw_runs if isinstance(run, dict)
            ] if isinstance(raw_runs, list) else []
            records: list[tuple[dict[str, Any], ScenarioResult | None]] = []
            for raw_run in manifest_runs:
                matched = self._manifest_result(
                    path, raw_run, results_by_path, results_by_name
                )
                result = matched[1] if matched is not None else None
                records.append((raw_run, result))
                if matched is not None:
                    relative = self._relative(matched[0])
                    if relative is not None:
                        run_id = _opaque_id(relative)
                        campaign_assignments.setdefault(
                            run_id, campaign_id
                        )
                        producer_records.setdefault(run_id, []).append(raw_run)

            declared_cells = manifest.get("cells")
            cell_specs: list[tuple[str, dict[str, Any]]] = []
            if isinstance(declared_cells, list):
                for raw_cell in declared_cells:
                    if not isinstance(raw_cell, dict):
                        continue
                    name = str(raw_cell.get("name", "default"))
                    params = raw_cell.get("effective_params", raw_cell.get("params", {}))
                    cell_specs.append(
                        (name, dict(params) if isinstance(params, dict) else {})
                    )
            if not cell_specs:
                names = sorted(
                    {
                        str(run.get("cell", "default"))
                        for run in manifest_runs
                    }
                )
                cell_specs = [(name, {}) for name in names]

            cell_summaries: list[CampaignCellSummary] = []
            for name, params in cell_specs:
                selected = [
                    record
                    for record in records
                    if str(record[0].get("cell", "default")) == name
                ]
                cell_summaries.append(
                    CampaignCellSummary(
                        name=name, params=params, **_summary_values(selected)
                    )
                )

            raw_backends = manifest.get("backends")
            backends = (
                [str(backend) for backend in raw_backends]
                if isinstance(raw_backends, list)
                else sorted(
                    {
                        str(run.get("backend"))
                        for run in manifest_runs
                        if run.get("backend") is not None
                    }
                )
            )
            matrix: list[CampaignMatrixCell] = []
            for name, params in cell_specs:
                for backend in backends:
                    selected = [
                        record
                        for record in records
                        if str(record[0].get("cell", "default")) == name
                        and str(record[0].get("backend")) == backend
                    ]
                    matrix.append(
                        CampaignMatrixCell(
                            name=name,
                            backend=backend,
                            params=params,
                            **_summary_values(selected),
                        )
                    )

            totals = _summary_values(records)
            provenance = manifest.get("provenance")
            provenance = provenance if isinstance(provenance, dict) else {}
            missing_ok_results = sum(
                raw_run.get("status") == "ok" and result is None
                for raw_run, result in records
            )
            error_count = totals["failed"] + totals["invalid_count"] + missing_ok_results
            completed = totals["completed"]
            scheduled = totals["scheduled"]
            if entry.partial or entry.stale:
                status = "partial"
            elif totals["failed"] or error_count:
                status = "failed"
            elif scheduled and completed == scheduled:
                status = "completed"
            elif completed or totals["pending"]:
                status = "running"
            else:
                status = "pending"
            seeds = manifest.get("seeds")
            campaigns.append(
                CampaignCard(
                    campaign_id=campaign_id,
                    relative_path=self._relative(path) or path.name,
                    schema_version=(
                        str(manifest["schema_version"])
                        if manifest.get("schema_version") is not None
                        else None
                    ),
                    scenario=(
                        str(manifest["scenario"])
                        if manifest.get("scenario") is not None
                        else None
                    ),
                    semantics_version=(
                        str(manifest["semantics_version"])
                        if manifest.get("semantics_version") is not None
                        else None
                    ),
                    mode=(
                        str(manifest["mode"])
                        if manifest.get("mode") is not None
                        else None
                    ),
                    created_at=(
                        str(manifest["created_at"])
                        if manifest.get("created_at") is not None
                        else None
                    ),
                    git_commit=(
                        str(provenance["git_commit"])
                        if provenance.get("git_commit") is not None
                        else None
                    ),
                    source_fingerprint=(
                        str(provenance["source_tree_fingerprint"])
                        if provenance.get("source_tree_fingerprint") is not None
                        else None
                    ),
                    source_file_count=(
                        int(provenance["source_file_count"])
                        if isinstance(provenance.get("source_file_count"), int)
                        else None
                    ),
                    seeds=[int(seed) for seed in seeds]
                    if isinstance(seeds, list)
                    and all(isinstance(seed, int) for seed in seeds)
                    else [],
                    backends=backends,
                    cells=cell_summaries,
                    matrix=matrix,
                    run_count=scheduled,
                    completed_count=completed,
                    ok_count=totals["ok"],
                    failed_count=totals["failed"],
                    pending_count=totals["pending"],
                    invalid_count=totals["invalid_count"],
                    error_count=error_count,
                    remaining_count=max(0, scheduled - completed),
                    progress_percent=(
                        round(completed / scheduled * 100, 2)
                        if scheduled
                        else 0.0
                    ),
                    status=status,
                    prompt_tokens=totals["prompt_tokens"],
                    completion_tokens=totals["completion_tokens"],
                    total_tokens=totals["total_tokens"],
                    mean_llm_latency_ms=totals["mean_llm_latency_ms"],
                    mean_retrieval_latency_ms=(
                        totals["mean_retrieval_latency_ms"]
                    ),
                    mean_end_to_end_latency_ms=(
                        totals["mean_end_to_end_latency_ms"]
                    ),
                    eta_seconds=None,
                    partial=entry.partial,
                    stale=entry.stale,
                )
            )

        producer_status_by_run_id: dict[str, str] = {}
        updated_runs: list[RunCard] = []
        for card in runs:
            records = producer_records.get(card.run_id, [])
            if not records:
                producer_status = "standalone"
                producer_error = None
            elif len(records) > 1:
                producer_status = "ambiguous"
                producer_error = "result is linked by multiple campaign entries"
            else:
                raw_status = records[0].get("status")
                producer_status = (
                    raw_status
                    if raw_status in {"ok", "failed", "pending"}
                    else "ambiguous"
                )
                raw_error = records[0].get("error")
                producer_error = (
                    str(raw_error) if raw_error is not None else None
                )
            producer_status_by_run_id[card.run_id] = producer_status
            updated_runs.append(
                card.model_copy(
                    update={
                        "campaign_id": campaign_assignments.get(card.run_id),
                        "producer_status": producer_status,
                        "producer_error": producer_error,
                    }
                )
            )
        runs = updated_runs
        self._campaign_by_run_id = dict(campaign_assignments)
        self._producer_status_by_run_id = producer_status_by_run_id
        revision = hashlib.sha256(
            "\n".join(revision_rows).encode("utf-8")
        ).hexdigest()
        snapshot = IndexSnapshot(
            revision=revision,
            results_dir=self.root.name,
            campaigns=campaigns,
            runs=runs,
            diagnostics=diagnostics,
            result_file_count=sum(
                entry.kind == "result" for entry in self._cache.values()
            ),
            manifest_file_count=sum(
                entry.kind == "manifest" for entry in self._cache.values()
            ),
            partial_file_count=sum(
                entry.partial for entry in self._cache.values()
            ),
            invalid_file_count=sum(
                entry.invalid for entry in self._cache.values()
            ),
        )
        self._last_snapshot = snapshot
        return snapshot

    def get_run(self, run_id: str) -> ScenarioResult | None:
        with self._lock:
            path = self._run_ids.get(run_id)
            if path is None:
                return None
            entry = self._cache.get(path)
            return (
                entry.value
                if entry and isinstance(entry.value, ScenarioResult)
                else None
            )

    def get_campaign_id(self, run_id: str) -> str | None:
        """Return the manifest campaign owning a run, when one is known."""

        with self._lock:
            return self._campaign_by_run_id.get(run_id)

    def iter_runs(
        self,
        *,
        campaign_id: str | None = None,
        accepted_only: bool = False,
    ) -> list[tuple[str, ScenarioResult]]:
        with self._lock:
            return [
                (run_id, result)
                for run_id in sorted(self._run_ids)
                if campaign_id is None
                or self._campaign_by_run_id.get(run_id) == campaign_id
                if not accepted_only
                or self._producer_status_by_run_id.get(run_id) in {
                    "ok",
                    "standalone",
                }
                if (result := self.get_run(run_id)) is not None
            ]
