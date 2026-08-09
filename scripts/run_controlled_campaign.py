"""Controlled campaign runner (TASK-004, generalized for world_update in
TASK-014 and memory_noise_stress in TASK-016).

Owns the full lifecycle of one Controlled Mode campaign:

1. Preflight-validates the ENTIRE campaign (cells, semantics version, seeds,
   backends, output path) before creating any manifest, store, log, or
   process — fail closed with exit code 2, no traceback, no writes.
2. Computes the COMPLETE schedule before execution: seed-major, with a
   precomputed counterbalanced backend order (Latin-square rotation across
   the approved backends) and alternating cell order, so backend/cell
   position is not aliased with wall time.
3. Writes the manifest (schema version, scenario, semantics version, cells
   with requested AND effective params, per-run commands, expected health
   mode, canonical fixture identity, log paths) BEFORE the first run starts.
4. For every scheduled run: starts a FRESH `BOT_MOCK=1` bot adapter process
   on its own port (canonical fixture per run), waits for mock health,
   invokes one single-run controlled CLI call, then terminates the adapter.
5. After each run, validates the produced result JSON against the
   pre-registered entry (scenario, seed, backend, mode, effective params,
   fairness incl. fixture identity). A failed/invalid run is left exactly as
   it happened: the manifest records `status=failed` with the reason and the
   runner STOPS — it never retries, replaces, or deletes evidence.

Usage (C, after A release; PowerShell):

    .venv\\Scripts\\python scripts\\run_controlled_campaign.py `
        --results-dir results\\stress_controlled_wu_round1 `
        --scenario world_update `
        --seeds 42,43,44 `
        --cell '{"name":"chain3","params":{"update_depth":3,"update_semantics_version":"temporal_chain_v2"}}'
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from minemembench.cli import (
    CONTROLLED_FIXTURE_SELECTOR,
    CONTROLLED_VERSION_PARAM,
    controlled_fixture_spec,
    validate_controlled_policy,
)
from minemembench.core.provenance import (
    SourceProvenance,
    capture_source_provenance,
    source_freeze_error,
)
from minemembench.scenarios.base import ScenarioParamError
from minemembench.scenarios.registry import ScenarioRegistryError, create_scenario

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BOT_ENTRY = REPO_ROOT / "minecraft" / "dist" / "index.js"
DEFAULT_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"

#: The four Controlled Mode backends, in canonical (pre-rotation) order.
DEFAULT_BACKENDS = ("none", "vector", "mem0", "letta")

#: Manifest schema marker; bumped when the manifest shape changes.
MANIFEST_SCHEMA_VERSION = "controlled-campaign/v4"

_BOT_URL_PLACEHOLDER = "BOT_URL_PLACEHOLDER"

#: Safe cell names: one path component, letters/digits plus `._-`, no
#: separators or traversal, bounded length.
_CELL_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def counterbalanced_order(backends: list[str], seed_index: int) -> list[str]:
    """Latin-square rotation: seed i starts at offset i % len(backends).

    Every backend occupies every schedule position exactly once per full
    rotation, so backend identity is not aliased with execution order.
    """

    n = len(backends)
    offset = seed_index % n
    return [*backends[offset:], *backends[:offset]]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results-dir", required=True, help="Isolated campaign output directory.")
    parser.add_argument(
        "--scenario",
        choices=sorted(CONTROLLED_VERSION_PARAM),
        default="delayed_recall",
        help="Controlled scenario (default delayed_recall; backward compatible).",
    )
    parser.add_argument("--seeds", default="42,43,44", help="Comma-separated unique seeds (default 42,43,44).")
    parser.add_argument("--backends", default=",".join(DEFAULT_BACKENDS))
    parser.add_argument(
        "--cell",
        action="append",
        required=True,
        metavar='{"name":...,"params":{...}}',
        help="One difficulty cell as JSON; repeatable.",
    )
    parser.add_argument("--python", default=str(DEFAULT_PYTHON))
    parser.add_argument("--bot-entry", default=str(DEFAULT_BOT_ENTRY))
    parser.add_argument(
        "--require-clean-source",
        action="store_true",
        help=(
            "Fail before creating the output directory unless git provenance "
            "is available and the complete worktree is clean. Recording a "
            "clean tree does not itself authorize a formal campaign."
        ),
    )
    return parser


def prepare_campaign(args: argparse.Namespace) -> tuple[dict[str, Any] | None, str | None]:
    """Validate the complete campaign BEFORE anything is written or spawned.

    Returns (plan, None) on success or (None, error_message) on any preflight
    failure. The plan carries per-cell requested params (byte-for-byte as
    given) plus the full effective params after Scenario validation/defaults.
    """

    cells: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for raw in args.cell:
        try:
            cell = json.loads(raw)
        except json.JSONDecodeError as exc:
            return None, f"--cell is not valid JSON: {exc}"
        if not isinstance(cell, dict) or set(cell) != {"name", "params"}:
            return None, (
                "--cell must be a JSON object with exactly 'name' and "
                f"'params': {raw!r}"
            )
        name = cell["name"]
        if (
            not isinstance(name, str)
            or not _CELL_NAME_RE.match(name)
            or name in (".", "..")
        ):
            return None, (
                f"unsafe cell name {name!r}: one path component, "
                "letters/digits plus . _ -, max 64 chars, no traversal"
            )
        if name in seen_names:
            return None, f"duplicate cell name {name!r}"
        seen_names.add(name)
        if not isinstance(cell["params"], dict):
            return None, f"cell {name!r}: 'params' must be a JSON object"
        try:
            scenario = create_scenario(args.scenario)
            scenario.apply_params(cell["params"])
        except (ScenarioRegistryError, ScenarioParamError, ValueError) as exc:
            # Known user-input errors only; an implementation defect must
            # surface as a crash, not a clean rejection (A-REVIEW-014 Low).
            return None, f"cell {name!r}: {exc}"
        cells.append(
            {
                "name": name,
                "params": cell["params"],
                "effective_params": scenario.params,
            }
        )

    # Semantic duplicates: a cell name is only a label. Two cells with the
    # same canonical (scenario, effective params) signature are ONE treatment
    # and must never be scheduled as separate observations (A-REVIEW-014).
    seen_signatures: dict[str, str] = {}
    for cell in cells:
        signature = json.dumps(
            {"scenario": args.scenario, "effective_params": cell["effective_params"]},
            sort_keys=True,
            separators=(",", ":"),
        )
        previous = seen_signatures.get(signature)
        if previous is not None:
            return None, (
                f"cells {previous!r} and {cell['name']!r} are semantically "
                f"duplicate: identical effective params "
                f"{cell['effective_params']!r} for scenario {args.scenario!r}"
            )
        seen_signatures[signature] = cell["name"]

    # Scenarios whose Controlled cells must explicitly request the v2
    # semantics version in the REQUESTED params (not just via defaults), so
    # the pre-registered manifest records the treatment choice byte-for-byte.
    explicit_version_required = {
        "world_update": ("update_semantics_version", "temporal_chain_v2"),
        "memory_noise_stress": ("noise_semantics_version", "key_retention_v2"),
        "failure_learning": (
            "failure_semantics_version",
            "observed_precondition_v2",
        ),
    }
    requirement = explicit_version_required.get(args.scenario)
    if requirement is not None:
        version_param, required_version = requirement
        for cell in cells:
            if cell["params"].get(version_param) != required_version:
                return None, (
                    f"cell {cell['name']!r}: {args.scenario} cells must "
                    f"explicitly request {version_param}={required_version}"
                )

    version_param = CONTROLLED_VERSION_PARAM[args.scenario]
    versions = {cell["effective_params"][version_param] for cell in cells}
    if len(versions) != 1:
        return None, (
            f"all cells must share one semantics version, got "
            f"{sorted(str(v) for v in versions)}"
        )
    semantics_version = versions.pop()
    policy_error = validate_controlled_policy(
        args.scenario, cells[0]["effective_params"]
    )
    if policy_error is not None:
        return None, policy_error

    try:
        seeds = [int(part) for part in args.seeds.split(",")]
    except ValueError:
        return None, f"--seeds must be comma-separated integers: {args.seeds!r}"
    if not seeds or len(set(seeds)) != len(seeds):
        return None, "--seeds must be a non-empty list of unique integers"

    backends = [part.strip() for part in args.backends.split(",") if part.strip()]
    if not backends or len(set(backends)) != len(backends):
        return None, "--backends must be a non-empty list of unique names"
    unsupported = sorted(set(backends) - set(DEFAULT_BACKENDS))
    if unsupported:
        return None, (
            f"unsupported backend(s): {', '.join(unsupported)} "
            f"(approved: {', '.join(DEFAULT_BACKENDS)})"
        )

    return (
        {
            "scenario": args.scenario,
            "semantics_version": semantics_version,
            "cells": cells,
            "seeds": seeds,
            "backends": backends,
        },
        None,
    )


def build_schedule(
    *,
    cells: list[dict[str, Any]],
    backends: list[str],
    seeds: list[int],
    python: str,
    results_dir: Path,
    scenario: str = "delayed_recall",
) -> list[dict[str, Any]]:
    """The full planned schedule: seed-major, counterbalanced, precomputed.

    Cell order alternates by (seed, backend) position so control does not
    always precede stress. Every entry carries its exact CLI command (with
    only the REQUESTED param overrides, so historical delayed-recall commands
    stay semantically identical), both param dicts, and the canonical fixture
    identity; the bot URL is a placeholder, substituted with the fresh
    per-run port at execution time.
    """

    schedule: list[dict[str, Any]] = []
    index = 0
    for seed_index, seed in enumerate(seeds):
        for backend_index, backend in enumerate(counterbalanced_order(backends, seed_index)):
            ordered_cells = (
                cells if (seed_index + backend_index) % 2 == 0 else list(reversed(cells))
            )
            for cell in ordered_cells:
                command = [
                    python,
                    "-m",
                    "minemembench",
                    "run",
                    "--scenario",
                    scenario,
                    "--memory",
                    backend,
                    "--runs",
                    "1",
                    "--seed",
                    str(seed),
                    "--campaign-mode",
                    "controlled",
                    "--bot-url",
                    _BOT_URL_PLACEHOLDER,
                ]
                for key, value in cell["params"].items():
                    command += ["--scenario-param", f"{key}={value}"]
                log_base = f"run_{index:03d}_{backend}_{cell['name']}_seed{seed}"
                fixture_selector, fixture_identity = controlled_fixture_spec(
                    scenario, cell["effective_params"]
                )
                schedule.append(
                    {
                        "index": index,
                        "scenario": scenario,
                        "seed": seed,
                        "backend": backend,
                        "cell": cell["name"],
                        "requested_params": cell["params"],
                        "effective_params": cell["effective_params"],
                        "expected_health_mode": "mock",
                        "fixture_selector": fixture_selector,
                        "fixture_identity": fixture_identity,
                        "bot_port": None,
                        "command": command,
                        # Pre-registered durable per-run diagnostics.
                        "log_stdout": str(results_dir / "logs" / f"{log_base}.stdout.log"),
                        "log_stderr": str(results_dir / "logs" / f"{log_base}.stderr.log"),
                        "result_files": [],
                        "status": "pending",
                        "returncode": None,
                    }
                )
                index += 1
    return schedule


def write_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
    """(Re)write the campaign manifest — called before execution AND after
    every run, so a stopped campaign keeps its full partial state."""

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _spawn_bot(
    bot_entry: Path,
    port: int,
    fixture_selector: str = CONTROLLED_FIXTURE_SELECTOR,
) -> subprocess.Popen[bytes]:
    """Start a fresh explicitly selected mock fixture on `port`."""

    env = dict(
        os.environ,
        BOT_MOCK="1",
        BOT_API_PORT=str(port),
        BOT_MOCK_FIXTURE=fixture_selector,
    )
    return subprocess.Popen(  # noqa: S603 — fixed local command
        ["node", str(bot_entry)],
        cwd=str(bot_entry.parent.parent),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _await_mock_health(port: int, timeout_s: float = 30.0) -> dict[str, Any]:
    """Poll /health until the fresh adapter reports mock mode; fail closed."""

    url = f"http://127.0.0.1:{port}/health"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as response:
                health = json.loads(response.read().decode("utf-8"))
            if health.get("status") == "ok" and health.get("mode") == "mock":
                return health
        except (OSError, ValueError):
            pass
        time.sleep(0.25)
    raise RuntimeError(
        f"mock bot adapter on port {port} did not report mock health within "
        f"{timeout_s}s"
    )


def _campaign_env(results_dir: Path, stores: dict[str, str]) -> dict[str, str]:
    """Subprocess environment: campaign-local results AND backend stores.

    `VECTOR_DB_PATH` / `MEM0_QDRANT_PATH` are pinned inside the campaign
    directory so no run ever reads or writes the user's historical stores.
    """

    env = dict(os.environ)
    env["RESULTS_DIR"] = str(results_dir)
    env["VECTOR_DB_PATH"] = stores["vector_db_path"]
    env["MEM0_QDRANT_PATH"] = stores["mem0_qdrant_path"]
    return env


def _invoke_run(
    command: list[str],
    *,
    results_dir: Path,
    stdout_log: str,
    stderr_log: str,
    stores: dict[str, str],
) -> int:
    """Run one controlled CLI invocation, retaining both output streams."""

    Path(stdout_log).parent.mkdir(parents=True, exist_ok=True)
    with (
        open(stdout_log, "wb") as stdout,
        open(stderr_log, "wb") as stderr,
    ):
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            env=_campaign_env(results_dir, stores),
            check=False,
            stdout=stdout,
            stderr=stderr,
        )
    return completed.returncode


def _stop_bot(process: Any) -> None:
    """Terminate the per-run adapter process (best-effort, then kill)."""

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _validate_run_result(
    entry: dict[str, Any],
    produced: list[Path],
    *,
    expected_provenance: dict[str, Any] | None = None,
) -> str | None:
    """Fail-closed per-run evidence validation (TASK-014 §5).

    Returns None when exactly one new result file exists and its JSON agrees
    with the pre-registered entry; otherwise a human-readable reason.
    """

    if len(produced) != 1:
        return f"expected exactly 1 new result file, found {len(produced)}"
    path = produced[0]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"result file {path.name} is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return f"result file {path.name} is not a JSON object"

    for field, expected in (
        ("scenario", entry["scenario"]),
        ("seed", entry["seed"]),
        ("memory_backend", entry["backend"]),
        ("campaign_mode", "controlled"),
        ("params", entry["effective_params"]),
    ):
        actual = data.get(field)
        if actual != expected:
            return f"result {field} mismatch: {actual!r} != {expected!r}"

    fairness = data.get("fairness")
    if not isinstance(fairness, dict):
        return "result carries no fairness record"
    if fairness.get("valid") is not True:
        return f"fairness invalid: {fairness.get('invalid_reason')!r}"
    for field, expected in (
        ("scenario", entry["scenario"]),
        ("scenario_params", entry["effective_params"]),
        ("run_seed", entry["seed"]),
        ("campaign_mode", "controlled"),
        ("fixture_selector", entry["fixture_selector"]),
        ("fixture_identity", entry["fixture_identity"]),
    ):
        actual = fairness.get(field)
        if actual != expected:
            return f"fairness {field} mismatch: {actual!r} != {expected!r}"
    if expected_provenance is not None:
        for fairness_field, provenance_field in (
            ("source_tree_fingerprint", "source_tree_fingerprint"),
            ("source_file_count", "source_file_count"),
            ("git_available", "git_available"),
            ("git_commit", "git_commit"),
            ("git_dirty", "git_dirty"),
            ("git_status_fingerprint", "git_status_fingerprint"),
        ):
            expected = expected_provenance.get(provenance_field)
            actual = fairness.get(fairness_field)
            if actual != expected:
                return (
                    f"fairness {fairness_field} provenance mismatch: "
                    f"{actual!r} != {expected!r}"
                )
    return None


def _failure_evidence_fingerprints(
    path: Path,
) -> tuple[tuple[str, str] | None, str | None]:
    """Fingerprint the two separately audited TASK-020 causal inputs.

    Injected events are normalized only for the isolation `episode_id`.
    Source ActionResult evidence drops only volatile action/time identifiers
    (plus the WorldState observation timestamp); action/status/result/error
    and the complete entity/equipped state remain in the fingerprint.
    """

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"cannot fingerprint failure evidence: {exc}"

    injected = data.get("injected_events")
    if not isinstance(injected, list) or not injected:
        return None, "failure-learning v2 result has no injected event stream"
    normalized_events: list[dict[str, Any]] = []
    for event in injected:
        if not isinstance(event, dict):
            return None, "failure-learning v2 injected event is not an object"
        normalized = dict(event)
        normalized["episode_id"] = "<episode>"
        normalized_events.append(normalized)
    if sum(event.get("event_type") == "task_failed" for event in normalized_events) != 1:
        return None, "failure-learning v2 must inject exactly one task_failed event"

    observed = data.get("observed_action_results")
    if not isinstance(observed, list) or len(observed) != 1:
        return None, "failure-learning v2 must carry exactly one source ActionResult"
    if not isinstance(observed[0], dict):
        return None, "failure-learning v2 source ActionResult is not an object"
    source = {
        key: value
        for key, value in observed[0].items()
        if key not in {"action_id", "started_at", "finished_at"}
    }
    state_after = source.get("state_after")
    if not isinstance(state_after, dict):
        return None, "failure-learning v2 source ActionResult has no state_after"
    normalized_state = dict(state_after)
    normalized_state.pop("timestamp", None)
    source["state_after"] = normalized_state

    def digest(payload: Any) -> str:
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    return (digest(normalized_events), digest(source)), None


def run_campaign(
    manifest_path: Path,
    manifest: dict[str, Any],
    *,
    spawn_bot: Callable[..., Any] | None = None,
    await_health: Callable[[int], dict[str, Any]] | None = None,
    invoke_run: Callable[..., int] | None = None,
    bot_entry: Path = DEFAULT_BOT_ENTRY,
) -> int:
    """Execute the manifest's schedule one run at a time; stop on failure.

    The manifest on disk always reflects reality: written fully-pending before
    the first run and updated after every run. Per-run stdout/stderr logs are
    pre-registered and retained, every produced scenario JSON is linked (even
    for failed runs), and a zero-returncode run still must pass the strict
    result/fairness validation. Returns 0 when every run succeeded.

    Dependencies are late-bound (A-REVIEW-014): None resolves to the CURRENT
    module functions at call time, so monkeypatching the module attributes
    before a normal `main()` call is effective; explicit kwargs still win.
    """

    expected_provenance: dict[str, Any] | None = None
    if manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION:
        raw_provenance = manifest.get("provenance")
        if not isinstance(raw_provenance, dict):
            print(
                f"campaign preflight failed: {MANIFEST_SCHEMA_VERSION} requires "
                "a complete provenance object",
                file=sys.stderr,
            )
            return 2
        try:
            expected_provenance = SourceProvenance.model_validate(
                raw_provenance
            ).model_dump(mode="json")
        except ValueError as exc:
            print(
                f"campaign preflight failed: invalid provenance: {exc}",
                file=sys.stderr,
            )
            return 2

    if spawn_bot is None:
        spawn_bot = _spawn_bot
    if await_health is None:
        await_health = _await_mock_health
    if invoke_run is None:
        invoke_run = _invoke_run

    results_dir = Path(manifest["results_dir"])
    stores = manifest["stores"]
    failure_evidence_by_treatment: dict[tuple[int, str], tuple[str, str]] = {}
    write_manifest(manifest_path, manifest)  # fully-pending, before execution

    for entry in manifest["runs"]:
        port = _free_port()
        entry["bot_port"] = port
        # The command embeds the placeholder; substitute the real per-run URL.
        entry["command"] = [
            f"http://127.0.0.1:{port}" if part == _BOT_URL_PLACEHOLDER else part
            for part in entry["command"]
        ]
        process = None
        try:
            fixture_selector = entry.get(
                "fixture_selector", CONTROLLED_FIXTURE_SELECTOR
            )
            # Preserve the injectable two-argument seam used by historical
            # canonical campaign tests; non-canonical fixtures receive their
            # explicit selector as the third argument.
            if fixture_selector == CONTROLLED_FIXTURE_SELECTOR:
                process = spawn_bot(bot_entry, port)
            else:
                process = spawn_bot(bot_entry, port, fixture_selector)
            health = await_health(port)
            entry["health_mode"] = health.get("mode")
            before = set(results_dir.glob("scenario_*.json"))
            returncode = invoke_run(
                entry["command"],
                results_dir=results_dir,
                stdout_log=entry["log_stdout"],
                stderr_log=entry["log_stderr"],
                stores=stores,
            )
            entry["returncode"] = returncode
            produced = sorted(set(results_dir.glob("scenario_*.json")) - before)
            entry["result_files"] = [str(path) for path in produced]
            if returncode != 0:
                entry["status"] = "failed"
            else:
                validation_error = _validate_run_result(
                    entry,
                    produced,
                    expected_provenance=expected_provenance,
                )
                if (
                    validation_error is None
                    and entry["scenario"] == "failure_learning"
                    and entry["effective_params"].get("failure_semantics_version")
                    == "observed_precondition_v2"
                ):
                    fingerprints, evidence_error = _failure_evidence_fingerprints(
                        produced[0]
                    )
                    if evidence_error is not None:
                        validation_error = evidence_error
                    else:
                        assert fingerprints is not None
                        entry["input_stream_fingerprint"] = fingerprints[0]
                        entry["source_evidence_fingerprint"] = fingerprints[1]
                        treatment_key = (
                            entry["seed"],
                            json.dumps(
                                entry["effective_params"],
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        )
                        reference = failure_evidence_by_treatment.setdefault(
                            treatment_key, fingerprints
                        )
                        if fingerprints[0] != reference[0]:
                            validation_error = (
                                "failure-learning injected event stream differs "
                                "across backends for the same treatment"
                            )
                        elif fingerprints[1] != reference[1]:
                            validation_error = (
                                "failure-learning source ActionResult evidence "
                                "differs across backends for the same treatment"
                            )
                if validation_error is None:
                    entry["status"] = "ok"
                else:
                    entry["status"] = "failed"
                    entry["error"] = validation_error
        except Exception as exc:  # noqa: BLE001 — record, then stop
            entry["status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if process is not None:
                _stop_bot(process)
        write_manifest(manifest_path, manifest)
        if entry["status"] != "ok":
            print(
                f"campaign STOPPED at run {entry['index']} "
                f"({entry['scenario']}/{entry['backend']}/{entry['cell']}/"
                f"seed={entry['seed']}): "
                f"{entry.get('error') or 'returncode=' + str(entry['returncode'])}"
                f" — logs: {entry['log_stdout']}, {entry['log_stderr']}",
                file=sys.stderr,
            )
            return 1
        print(
            f"run {entry['index'] + 1}/{len(manifest['runs'])} ok: "
            f"{entry['backend']}/{entry['cell']}/seed={entry['seed']}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    plan, error = prepare_campaign(args)
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        return 2

    try:
        provenance: SourceProvenance = capture_source_provenance(REPO_ROOT)
    except (OSError, ValueError) as exc:
        print(f"error: cannot capture source provenance: {exc}", file=sys.stderr)
        return 2

    clean_source_error = source_freeze_error(
        provenance,
        require_clean=args.require_clean_source,
    )
    if clean_source_error is not None:
        print(
            "error: --require-clean-source rejected the campaign because "
            f"{clean_source_error}; no output was created",
            file=sys.stderr,
        )
        return 2

    results_dir = Path(args.results_dir)

    # Fail closed BEFORE writing anything: a campaign output path must be
    # absent or a completely empty directory. Never mix with, overwrite, or
    # delete an existing campaign's evidence.
    if results_dir.exists():
        if not results_dir.is_dir() or any(results_dir.iterdir()):
            print(
                f"error: campaign output directory {results_dir} already "
                "exists and is not empty; refusing to mix with or overwrite "
                "an existing campaign. Choose a fresh directory.",
                file=sys.stderr,
            )
            return 2

    # Campaign-local backend stores, pre-registered so no invocation touches
    # the user's historical vector/mem0 data.
    stores = {
        "vector_db_path": str(results_dir / "stores" / "memory_vector.db"),
        "mem0_qdrant_path": str(results_dir / "stores" / "mem0_qdrant"),
    }

    schedule = build_schedule(
        cells=plan["cells"],
        backends=plan["backends"],
        seeds=plan["seeds"],
        python=args.python,
        results_dir=results_dir,
        scenario=plan["scenario"],
    )
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "provenance": provenance.model_dump(mode="json"),
        "mode": "controlled",
        "scenario": plan["scenario"],
        "semantics_version": plan["semantics_version"],
        "results_dir": str(results_dir),
        "stores": stores,
        "seeds": plan["seeds"],
        "backends": plan["backends"],
        "cells": plan["cells"],
        "fixtures": sorted(
            {
                (entry["fixture_selector"], entry["fixture_identity"])
                for entry in schedule
            }
        ),
        "runs": schedule,
    }
    manifest_path = results_dir / "campaign_manifest.json"
    return run_campaign(
        manifest_path, manifest, bot_entry=Path(args.bot_entry)
    )


if __name__ == "__main__":
    sys.exit(main())
