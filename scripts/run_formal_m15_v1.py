"""One-shot, no-resume producer for the frozen M15 Controlled Formal V1."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minemembench.agent.planner import (
    PLANNER_USER_TEMPLATE_HASH,
    SYSTEM_PROMPT_HASH,
    TOOL_SET_HASH,
)
from minemembench.core.config import Settings
from minemembench.core.provenance import capture_source_provenance, source_freeze_error
from minemembench.evaluation.formal_m15 import (
    DEFAULT_SPEC,
    FORMAL_RESULTS_RELATIVE,
    FORMAL_STUDY_SCHEMA,
    RETRIEVAL_LIMIT,
    sha256_file,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CAMPAIGN_RUNNER = REPO_ROOT / "scripts" / "run_controlled_campaign.py"
ANALYSIS_SCRIPT = REPO_ROOT / "scripts" / "analyze_formal_m15.py"
DEFAULT_PREREGISTRATION = (
    REPO_ROOT / "docs" / "preregistration_m15_formal_v1_attempt2.md"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        default=str(REPO_ROOT / FORMAL_RESULTS_RELATIVE),
    )
    parser.add_argument("--expected-git-commit", required=True)
    parser.add_argument("--expected-source-fingerprint", required=True)
    parser.add_argument(
        "--preregistration",
        default=str(DEFAULT_PREREGISTRATION),
    )
    parser.add_argument(
        "--expected-planner-model",
        default="deepseek-v4-flash",
    )
    parser.add_argument(
        "--expected-temperature",
        type=float,
        default=0.0,
    )
    return parser


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _atomic_manifest(path: Path, manifest: dict[str, Any]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _compact_provenance(provenance: Any) -> dict[str, Any]:
    value = provenance.model_dump(mode="json")
    return {
        key: value[key]
        for key in (
            "source_tree_fingerprint",
            "source_file_count",
            "git_available",
            "git_commit",
            "git_dirty",
            "git_status_fingerprint",
        )
    }


def _source_error(expected_commit: str, expected_fingerprint: str) -> tuple[Any, str | None]:
    provenance = capture_source_provenance(REPO_ROOT)
    error = source_freeze_error(
        provenance,
        require_clean=True,
        expected_source_fingerprint=expected_fingerprint,
        expected_git_commit=expected_commit,
    )
    return provenance, error


def _campaign_command(
    *,
    scenario: str,
    directory: Path,
    cells: list[Any],
) -> list[str]:
    command = [
        sys.executable,
        str(CAMPAIGN_RUNNER),
        "--results-dir",
        str(directory),
        "--scenario",
        scenario,
        "--seeds",
        ",".join(str(seed) for seed in DEFAULT_SPEC.seeds),
        "--backends",
        ",".join(DEFAULT_SPEC.backends),
        "--require-clean-source",
    ]
    for cell in cells:
        command += [
            "--cell",
            json.dumps(
                {"name": cell.name, "params": dict(cell.params)},
                separators=(",", ":"),
            ),
        ]
    return command


def _count_campaign_statuses(
    root: Path,
    campaigns: list[dict[str, Any]],
) -> tuple[int, int]:
    """Return successful and started run counts from child manifests."""

    successful = 0
    started = 0
    for campaign in campaigns:
        path = root / campaign["relative_dir"] / "campaign_manifest.json"
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        runs = data.get("runs")
        if isinstance(runs, list):
            successful += sum(
                isinstance(run, dict) and run.get("status") == "ok" for run in runs
            )
            started += sum(
                isinstance(run, dict) and run.get("status") in {"ok", "failed"}
                for run in runs
            )
    return successful, started


def _refresh_counts(root: Path, manifest: dict[str, Any]) -> None:
    successful, started = _count_campaign_statuses(root, manifest["campaigns"])
    manifest["actual_runs"] = successful
    manifest["started_runs"] = started


def _formal_environment() -> dict[str, str]:
    """Child environment with loopback services excluded from proxies."""

    environment = dict(os.environ)
    existing = environment.get("NO_PROXY") or environment.get("no_proxy") or ""
    entries = [entry.strip() for entry in existing.split(",") if entry.strip()]
    for loopback in ("localhost", "127.0.0.1"):
        if loopback not in entries:
            entries.append(loopback)
    value = ",".join(entries)
    environment["NO_PROXY"] = value
    environment["no_proxy"] = value
    return environment


def _manifest(
    *,
    root: Path,
    producer: Any,
    settings: Settings,
    preregistration: Path,
) -> dict[str, Any]:
    campaigns: list[dict[str, Any]] = []
    for scenario in DEFAULT_SPEC.scenarios:
        cells = [cell for cell in DEFAULT_SPEC.cells if cell.scenario == scenario]
        relative_dir = scenario
        command = _campaign_command(
            scenario=scenario,
            directory=root / relative_dir,
            cells=cells,
        )
        campaigns.append(
            {
                "scenario": scenario,
                "relative_dir": relative_dir,
                "expected_runs": len(cells) * len(DEFAULT_SPEC.backends) * len(DEFAULT_SPEC.seeds),
                "cells": [cell.plan_dict() for cell in cells],
                "command": command,
                "status": "pending",
                "returncode": None,
            }
        )
    return {
        "schema_version": FORMAL_STUDY_SCHEMA,
        "study_id": DEFAULT_SPEC.study_id,
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "controlled",
        "results_dir": str(root),
        "preregistration": {
            "path": str(preregistration),
            "sha256": sha256_file(preregistration),
        },
        "analysis": {
            "path": str(ANALYSIS_SCRIPT),
            "sha256": sha256_file(ANALYSIS_SCRIPT),
        },
        "producer": _compact_provenance(producer),
        "planner": {
            "model": settings.llm_model,
            "temperature": settings.llm_temperature,
            "thinking": settings.llm_thinking,
            "llm_base_url_sha256": hashlib.sha256(
                settings.llm_base_url.encode("utf-8")
            ).hexdigest(),
            "system_prompt_hash": SYSTEM_PROMPT_HASH,
            "tool_set_hash": TOOL_SET_HASH,
            "planner_user_template_hash": PLANNER_USER_TEMPLATE_HASH,
            "retrieval_limit": RETRIEVAL_LIMIT,
        },
        "backend_config": {
            "none": {"implementation": "NoMemoryBackend"},
            "vector": {
                "implementation": "VectorMemoryBackend",
                "embedder": "HashEmbedder",
                "store": "campaign-local SQLite",
            },
            "mem0": {
                "implementation": "Mem0Backend",
                "mem0ai_version": _package_version("mem0ai"),
                "embedder_model": settings.mem0_embedder_model,
                "embedding_dimensions": 384,
                "store": "campaign-local Qdrant path",
                "planner_provider_model": settings.llm_model,
            },
            "letta": {
                "implementation": "LettaBackend",
                "letta_client_version": _package_version("letta-client"),
                "server_image": (
                    "letta/letta:0.16.8@sha256:"
                    "aa66c3eeee13d2dfc40c650d709b550237ee31bfc91942a52fa488a13fa8c102"
                ),
                "embedding_service_image": (
                    "ollama/ollama:latest@sha256:"
                    "b88c73ace3e115f8ec53dc8761ae1c0aabfa675406e3681786b98757ce050f42"
                ),
                "embedding": "ollama/nomic-embed-text:latest",
                "server_base_url_sha256": hashlib.sha256(
                    settings.letta_base_url.encode("utf-8")
                ).hexdigest(),
            },
        },
        "plan": DEFAULT_SPEC.plan_dict(),
        "expected_runs": DEFAULT_SPEC.expected_runs,
        "campaigns": campaigns,
        "policy": {
            "primary_endpoint": "strict task_success",
            "retry": "none",
            "replacement": "none",
            "exclusion": "none; integrity mismatch stops whole study",
            "stopping": "exactly 320 planned runs unless integrity failure",
        },
        "status": "frozen",
        "started_runs": 0,
        "actual_runs": 0,
        "retries": 0,
        "exclusions": 0,
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = Path(args.results_dir).resolve()
    preregistration = Path(args.preregistration).resolve()
    if not preregistration.is_file():
        print(f"formal preflight failed: preregistration missing: {preregistration}", file=sys.stderr)
        return 2
    if not ANALYSIS_SCRIPT.is_file() or not CAMPAIGN_RUNNER.is_file():
        print("formal preflight failed: frozen producer/analysis script missing", file=sys.stderr)
        return 2
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        print(f"formal preflight failed: output is not new/empty: {root}", file=sys.stderr)
        return 2
    settings = Settings()
    if settings.llm_model != args.expected_planner_model:
        print(
            f"formal preflight failed: planner model {settings.llm_model!r} != {args.expected_planner_model!r}",
            file=sys.stderr,
        )
        return 2
    if settings.llm_temperature != args.expected_temperature:
        print("formal preflight failed: planner temperature mismatch", file=sys.stderr)
        return 2
    try:
        producer, error = _source_error(
            args.expected_git_commit,
            args.expected_source_fingerprint,
        )
    except (OSError, ValueError) as exc:
        print(f"formal preflight failed: cannot capture source: {exc}", file=sys.stderr)
        return 2
    if error is not None:
        print(f"formal preflight failed: {error}", file=sys.stderr)
        return 2

    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "formal_study_manifest.json"
    manifest = _manifest(
        root=root,
        producer=producer,
        settings=settings,
        preregistration=preregistration,
    )
    _atomic_manifest(manifest_path, manifest)
    print(
        f"formal study frozen before run 1: {DEFAULT_SPEC.expected_runs} planned, "
        "started_runs=0, retries=0"
    )

    for campaign in manifest["campaigns"]:
        current, error = _source_error(
            args.expected_git_commit,
            args.expected_source_fingerprint,
        )
        if error is not None or _compact_provenance(current) != manifest["producer"]:
            campaign["status"] = "integrity_stopped"
            campaign["error"] = error or "producer identity changed"
            manifest["status"] = "integrity_stopped"
            manifest["stop_reason"] = campaign["error"]
            _refresh_counts(root, manifest)
            _atomic_manifest(manifest_path, manifest)
            print(f"formal campaign STOPPED: {campaign['error']}", file=sys.stderr)
            return 1
        campaign["status"] = "running"
        manifest["status"] = "running"
        _refresh_counts(root, manifest)
        _atomic_manifest(manifest_path, manifest)
        completed = subprocess.run(
            campaign["command"],
            cwd=str(REPO_ROOT),
            env=_formal_environment(),
            check=False,
        )
        campaign["returncode"] = completed.returncode
        _refresh_counts(root, manifest)
        if completed.returncode != 0:
            campaign["status"] = "producer_stopped"
            manifest["status"] = "producer_stopped"
            manifest["stop_reason"] = (
                f"campaign {campaign['scenario']} returned {completed.returncode}"
            )
            _atomic_manifest(manifest_path, manifest)
            print(
                f"formal campaign STOPPED in {campaign['scenario']} with return code {completed.returncode}; no retry is permitted",
                file=sys.stderr,
            )
            return 1
        campaign["status"] = "complete"
        _atomic_manifest(manifest_path, manifest)

    _refresh_counts(root, manifest)
    if manifest["actual_runs"] != DEFAULT_SPEC.expected_runs:
        manifest["status"] = "integrity_stopped"
        _atomic_manifest(manifest_path, manifest)
        print("formal campaign STOPPED: final run count mismatch", file=sys.stderr)
        return 1
    manifest["status"] = "complete"
    manifest["completed_at"] = datetime.now(UTC).isoformat()
    _atomic_manifest(manifest_path, manifest)
    print(f"formal producer complete: {manifest['actual_runs']}/{DEFAULT_SPEC.expected_runs}, retries=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
