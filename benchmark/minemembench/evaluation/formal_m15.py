"""Frozen, fail-closed analysis contract for M15 Controlled Formal V1.

The module deliberately accepts data from one explicitly supplied Formal
results directory.  It never discovers calibration or historical campaigns.
All primary comparisons are paired on the pre-registered seed, and any
identity, schedule, fairness, reset, completeness, or isolation mismatch
raises :class:`FormalIntegrityError` before an analysis artifact is written.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from pydantic import ValidationError

from ..core.models import Position
from ..scenarios.base import ScenarioResult
from ..scenarios.long_lived_memory import compute_lifetime_behavior_metrics

FORMAL_STUDY_SCHEMA = "minemembench-formal-study/v1"
STUDY_ID = "m15-formal-v1-controlled-20260811-attempt2"
FORMAL_RESULTS_RELATIVE = Path("results/formal_m15_v1_20260811_attempt2")
FORMAL_BACKENDS = ("none", "vector", "mem0", "letta")
ACTIVE_BACKEND_PAIRS = (
    ("vector", "mem0"),
    ("vector", "letta"),
    ("mem0", "letta"),
)
FORMAL_SEEDS = tuple(range(1011, 1021))
BOOTSTRAP_SEED = 20260811
BOOTSTRAP_RESAMPLES = 10_000
PRIMARY_ALPHA = 0.05
RETRIEVAL_LIMIT = 10


class FormalIntegrityError(ValueError):
    """Formal evidence does not match the frozen study contract."""


@dataclass(frozen=True)
class FormalCell:
    """One pre-registered scenario treatment."""

    name: str
    scenario: str
    semantics_param: str
    semantics_version: str
    params: Mapping[str, Any]
    order: int
    ladder: str | None = None
    level: str | None = None

    def plan_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "scenario": self.scenario,
            "semantics_param": self.semantics_param,
            "semantics_version": self.semantics_version,
            "params": dict(self.params),
            "order": self.order,
            "ladder": self.ladder,
            "level": self.level,
        }


FORMAL_CELLS = (
    FormalCell(
        name="delayed_200_20",
        scenario="delayed_recall",
        semantics_param="recall_semantics_version",
        semantics_version="entity_key_v2",
        params={
            "interference_count": 200,
            "similar_distractor_count": 20,
            "recall_semantics_version": "entity_key_v2",
        },
        order=0,
    ),
    FormalCell(
        name="world_update_depth3",
        scenario="world_update",
        semantics_param="update_semantics_version",
        semantics_version="temporal_chain_v2",
        params={
            "update_depth": 3,
            "update_semantics_version": "temporal_chain_v2",
        },
        order=1,
    ),
    FormalCell(
        name="noise_10",
        scenario="memory_noise_stress",
        semantics_param="noise_semantics_version",
        semantics_version="key_retention_v2",
        params={"noise_count": 10, "noise_semantics_version": "key_retention_v2"},
        order=2,
        ladder="memory_noise_stress",
        level="10",
    ),
    FormalCell(
        name="noise_30",
        scenario="memory_noise_stress",
        semantics_param="noise_semantics_version",
        semantics_version="key_retention_v2",
        params={"noise_count": 30, "noise_semantics_version": "key_retention_v2"},
        order=3,
        ladder="memory_noise_stress",
        level="30",
    ),
    FormalCell(
        name="noise_50",
        scenario="memory_noise_stress",
        semantics_param="noise_semantics_version",
        semantics_version="key_retention_v2",
        params={"noise_count": 50, "noise_semantics_version": "key_retention_v2"},
        order=4,
        ladder="memory_noise_stress",
        level="50",
    ),
    FormalCell(
        name="lifetime_l1",
        scenario="long_lived_memory",
        semantics_param="lifetime_semantics_version",
        semantics_version="lifetime_v1",
        params={
            "lifetime_event_count": 8,
            "session_count": 2,
            "relevant_update_count": 1,
            "similar_event_count": 1,
            "lifetime_semantics_version": "lifetime_v1",
        },
        order=5,
        ladder="long_lived_memory",
        level="L1",
    ),
    FormalCell(
        name="lifetime_l2",
        scenario="long_lived_memory",
        semantics_param="lifetime_semantics_version",
        semantics_version="lifetime_v1",
        params={
            "lifetime_event_count": 20,
            "session_count": 4,
            "relevant_update_count": 2,
            "similar_event_count": 5,
            "lifetime_semantics_version": "lifetime_v1",
        },
        order=6,
        ladder="long_lived_memory",
        level="L2",
    ),
    FormalCell(
        name="lifetime_l3",
        scenario="long_lived_memory",
        semantics_param="lifetime_semantics_version",
        semantics_version="lifetime_v1",
        params={
            "lifetime_event_count": 50,
            "session_count": 8,
            "relevant_update_count": 4,
            "similar_event_count": 15,
            "lifetime_semantics_version": "lifetime_v1",
        },
        order=7,
        ladder="long_lived_memory",
        level="L3",
    ),
)


@dataclass(frozen=True)
class FormalStudySpec:
    """Injectable study spec; production uses :data:`DEFAULT_SPEC` only."""

    study_id: str
    backends: tuple[str, ...]
    seeds: tuple[int, ...]
    cells: tuple[FormalCell, ...]

    @property
    def expected_runs(self) -> int:
        return len(self.backends) * len(self.seeds) * len(self.cells)

    @property
    def scenarios(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(cell.scenario for cell in self.cells))

    def plan_dict(self) -> dict[str, Any]:
        return {
            "backends": list(self.backends),
            "seeds": list(self.seeds),
            "cells": [cell.plan_dict() for cell in self.cells],
            "expected_runs": self.expected_runs,
        }


DEFAULT_SPEC = FormalStudySpec(
    study_id=STUDY_ID,
    backends=FORMAL_BACKENDS,
    seeds=FORMAL_SEEDS,
    cells=FORMAL_CELLS,
)


@dataclass(frozen=True)
class FormalRun:
    """One validated producer result bound to its pre-registered cell."""

    cell: FormalCell
    result: ScenarioResult
    result_path: Path
    retrieval_present: bool
    retrieval_rank: int | None
    attribution: str

    @property
    def success(self) -> bool:
        return self.result.success


@dataclass(frozen=True)
class FormalDataset:
    """Validated study manifest plus all expected formal runs."""

    root: Path
    manifest: dict[str, Any]
    runs: tuple[FormalRun, ...]
    integrity: dict[str, Any]


def canonical_json(value: Any) -> str:
    """Stable JSON encoding used for treatment and stream identity."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_file(path: Path) -> str:
    """SHA-256 of one file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FormalIntegrityError(f"invalid JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FormalIntegrityError(f"expected a JSON object at {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FormalIntegrityError(message)


def _cell_signature(scenario: str, params: Mapping[str, Any]) -> str:
    return canonical_json({"scenario": scenario, "params": dict(params)})


def _normalized_events(result: ScenarioResult) -> str:
    events: list[dict[str, Any]] = []
    for event in result.injected_events:
        value = event.model_dump(mode="json")
        value["episode_id"] = "<episode>"
        events.append(value)
    return canonical_json(events)


def _all_steps(result: ScenarioResult) -> list[Any]:
    """All distinct RunSteps, avoiding the lifetime primary-log duplicate."""

    if result.run_logs:
        return [step for entry in result.run_logs for step in entry.run_log.steps]
    return list(result.run_log.steps) if result.run_log is not None else []


def _primary_steps(result: ScenarioResult) -> list[Any]:
    return list(result.run_log.steps) if result.run_log is not None else []


def _ground_truth_dict(result: ScenarioResult) -> dict[str, Any]:
    _require(result.evaluation_ground_truth is not None, "result has no evaluation ground truth")
    return result.evaluation_ground_truth.model_dump(mode="json")


def _target_event_id(result: ScenarioResult) -> str:
    truth = _ground_truth_dict(result)
    if result.scenario == "world_update":
        return str(truth["current_event_id"])
    return str(truth["target_event_id"])


def retrieval_evidence(result: ScenarioResult) -> tuple[bool, int | None]:
    """Independently derive the scenario's causal relevant-memory evidence."""

    target_id = _target_event_id(result)
    steps = _primary_steps(result)
    if result.scenario == "long_lived_memory":
        for step in steps:
            for index, item in enumerate(step.retrieved_items, start=1):
                if item.event.event_id == target_id:
                    return True, index
        return False, None
    if not steps:
        return False, None
    for index, item in enumerate(steps[0].retrieved_items, start=1):
        if item.event.event_id == target_id:
            return True, index
    return False, None


def _target_position(result: ScenarioResult) -> tuple[float, float, float]:
    target_id = _target_event_id(result)
    for event in result.injected_events:
        if event.event_id == target_id and event.location is not None:
            return event.location.x, event.location.y, event.location.z
    raise FormalIntegrityError(
        f"{result.scenario}/{result.episode_id}: target event has no auditable location"
    )


def _arguments_position(arguments: Mapping[str, Any]) -> tuple[float, float, float] | None:
    try:
        return float(arguments["x"]), float(arguments["y"]), float(arguments["z"])
    except (KeyError, TypeError, ValueError):
        return None


def _near(a: tuple[float, float, float], b: tuple[float, float, float], radius: float = 2.0) -> bool:
    return math.dist(a, b) <= radius


def classify_failure(result: ScenarioResult, retrieval_present: bool) -> str:
    """Classify a failed run as R/P/E/Unknown from objective evidence.

    E is intentionally conservative: it requires a correct, stage-appropriate
    action whose recorded environment status is failed/timeout.  A correct
    retrieval followed by a wrong/missing action is P.  No LLM reason text is
    consulted.
    """

    if result.success:
        return "Success"
    if not retrieval_present:
        return "R"
    steps = _primary_steps(result)
    if not steps:
        return "Unknown"

    if result.scenario in {"delayed_recall", "world_update", "memory_noise_stress"}:
        target = _target_position(result)
        for step in steps:
            position = _arguments_position(step.arguments)
            if step.action == "move_to" and position is not None and _near(position, target):
                if step.action_status.value in {"failed", "timeout"}:
                    return "E"
        return "P"

    if result.scenario == "long_lived_memory":
        truth = _ground_truth_dict(result)
        pickup = tuple(float(truth["pickup_position"][axis]) for axis in ("x", "y", "z"))
        recipient = tuple(
            float(truth["recipient_position"][axis]) for axis in ("x", "y", "z")
        )
        item = str(truth["item_name"])
        user = str(truth["recipient"])
        stage = 0
        for step in steps:
            action = step.action
            status = step.action_status.value
            position = _arguments_position(step.arguments)
            correct = False
            if stage == 0 and action == "move_to" and position is not None and _near(position, pickup):
                correct = True
                if status == "completed":
                    stage = 1
            elif stage == 1 and action == "collect_item" and step.arguments.get("name") == item:
                correct = True
                if status == "completed":
                    stage = 2
            elif stage == 2 and action == "move_to" and position is not None and _near(position, recipient):
                correct = True
                if status == "completed":
                    stage = 3
            elif (
                stage == 3
                and action == "give_item"
                and step.arguments.get("item") == item
                and step.arguments.get("username") == user
            ):
                correct = True
                if status == "completed":
                    stage = 4
            if correct and status in {"failed", "timeout"}:
                return "E"
        return "P"
    return "Unknown"


def _metric_matches_retrieval(result: ScenarioResult, present: bool, rank: int | None) -> bool:
    metrics = result.metrics
    if result.scenario == "delayed_recall":
        return metrics.get("target_recall") == int(present) and metrics.get("fact_retrieval_rank") == rank
    if result.scenario == "world_update":
        return metrics.get("current_fact_recall") == int(present) and metrics.get("current_fact_retrieval_rank") == rank
    if result.scenario == "memory_noise_stress":
        return metrics.get("target_recall") == int(present) and metrics.get("target_retrieval_rank") == rank
    if result.scenario == "long_lived_memory":
        steps = _primary_steps(result)
        target_id = _target_event_id(result)
        first_items = steps[0].retrieved_items if steps else []
        first_rank = next(
            (
                index
                for index, item in enumerate(first_items, start=1)
                if item.event.event_id == target_id
            ),
            None,
        )
        first_step = next(
            (
                step.index
                for step in steps
                if any(item.event.event_id == target_id for item in step.retrieved_items)
            ),
            None,
        )
        return (
            metrics.get("target_recall_first_decision") == int(first_rank is not None)
            and metrics.get("target_retrieval_rank_first_decision") == first_rank
            and metrics.get("target_recall_any_decision") == int(present)
            and metrics.get("first_target_retrieval_step") == first_step
        )
    return False


def _validate_task_success(result: ScenarioResult) -> None:
    """Independently recompute the strict behavioral endpoint from raw steps."""

    _require(result.run_log is not None, "result has no primary run log")
    assert result.run_log is not None
    steps = list(result.run_log.steps)
    if result.scenario in {"delayed_recall", "world_update", "memory_noise_stress"}:
        target = _target_position(result)
        reached = any(
            _near((step.position.x, step.position.y, step.position.z), target)
            for step in steps
        )
        _require(result.run_log.success == reached, "runner success does not match objective position")
        _require(result.success == reached, "strict task_success does not match objective position")
        return
    if result.scenario == "long_lived_memory":
        truth = _ground_truth_dict(result)
        behavior = compute_lifetime_behavior_metrics(
            steps,
            target_event_id=str(truth["target_event_id"]),
            item_name=str(truth["item_name"]),
            pickup_position=Position.model_validate(truth["pickup_position"]),
            recipient=str(truth["recipient"]),
        )
        for key, expected in behavior.items():
            _require(
                result.metrics.get(key) == expected,
                f"stored lifetime behavior metric {key} does not recompute",
            )
        _require(result.success == bool(behavior["task_success"]), "lifetime strict success mismatch")
        return
    raise FormalIntegrityError(f"unregistered Formal scenario: {result.scenario}")


def _producer_compact(provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: provenance.get(key)
        for key in (
            "source_tree_fingerprint",
            "source_file_count",
            "git_available",
            "git_commit",
            "git_dirty",
            "git_status_fingerprint",
        )
    }


def _validate_root_manifest(root: Path, manifest: dict[str, Any], spec: FormalStudySpec) -> None:
    _require(manifest.get("schema_version") == FORMAL_STUDY_SCHEMA, "wrong formal study schema")
    _require(manifest.get("study_id") == spec.study_id, "wrong formal study id")
    _require(manifest.get("mode") == "controlled", "Formal V1 must be Controlled mode")
    _require(manifest.get("plan") == spec.plan_dict(), "formal plan differs from frozen spec")
    _require(manifest.get("expected_runs") == spec.expected_runs, "formal expected_runs mismatch")
    _require(manifest.get("status") == "complete", "formal producer status is not complete")
    _require(manifest.get("actual_runs") == spec.expected_runs, "formal actual_runs mismatch")
    _require(manifest.get("started_runs") == spec.expected_runs, "formal started_runs mismatch")
    _require(manifest.get("retries") == 0, "formal manifest reports a retry")
    _require(manifest.get("exclusions") == 0, "formal manifest reports an exclusion")
    producer = manifest.get("producer")
    _require(isinstance(producer, dict), "formal manifest has no producer identity")
    _require(producer.get("git_available") is True, "formal producer git identity unavailable")
    _require(producer.get("git_dirty") is False, "formal producer was dirty")
    commit = producer.get("git_commit")
    fingerprint = producer.get("source_tree_fingerprint")
    _require(
        isinstance(commit, str)
        and len(commit) in {40, 64}
        and all(character in "0123456789abcdef" for character in commit.lower()),
        "invalid producer commit",
    )
    _require(
        isinstance(fingerprint, str)
        and len(fingerprint) == 64
        and all(character in "0123456789abcdef" for character in fingerprint.lower()),
        "invalid source fingerprint",
    )
    _require(
        isinstance(producer.get("source_file_count"), int)
        and producer["source_file_count"] > 0,
        "invalid source file count",
    )
    planner = manifest.get("planner")
    _require(isinstance(planner, dict), "formal manifest has no planner contract")
    for field in (
        "model",
        "temperature",
        "system_prompt_hash",
        "tool_set_hash",
        "planner_user_template_hash",
    ):
        _require(planner.get(field) is not None, f"planner contract missing {field}")
    _require(planner.get("retrieval_limit") == RETRIEVAL_LIMIT, "retrieval limit mismatch")
    for section in ("preregistration", "analysis"):
        identity = manifest.get(section)
        _require(isinstance(identity, dict), f"formal manifest has no {section} identity")
        digest = identity.get("sha256")
        _require(
            isinstance(identity.get("path"), str)
            and isinstance(digest, str)
            and len(digest) == 64
            and all(character in "0123456789abcdef" for character in digest.lower()),
            f"invalid {section} identity",
        )
    campaigns = manifest.get("campaigns")
    _require(isinstance(campaigns, list), "formal manifest campaigns must be a list")
    _require({item.get("scenario") for item in campaigns if isinstance(item, dict)} == set(spec.scenarios), "formal campaign set mismatch")
    _require(len(campaigns) == len(spec.scenarios), "duplicate formal campaign declaration")
    _require(
        all(
            isinstance(item, dict)
            and item.get("status") == "complete"
            and item.get("returncode") == 0
            for item in campaigns
        ),
        "formal campaign declaration is not complete",
    )
    recorded = manifest.get("results_dir")
    _require(isinstance(recorded, str), "formal manifest has no results_dir")
    _require(Path(recorded).resolve() == root.resolve(), "formal results_dir identity mismatch")


def _validate_fairness(
    result: ScenarioResult,
    *,
    cell: FormalCell,
    manifest: dict[str, Any],
    producer: Mapping[str, Any],
    planner: Mapping[str, Any],
    seed: int,
    backend: str,
) -> None:
    fairness = result.fairness
    _require(fairness is not None, "result has no fairness record")
    assert fairness is not None
    _require(fairness.valid is True, f"fairness invalid: {fairness.invalid_reason}")
    _require(fairness.campaign_mode == "controlled", "result is not Controlled")
    _require(fairness.scenario == cell.scenario, "fairness scenario mismatch")
    _require(fairness.scenario_params == dict(cell.params), "fairness params mismatch")
    _require(fairness.run_seed == seed, "fairness seed mismatch")
    _require(fairness.reset_episode == result.episode_id, "reset episode mismatch")
    _require(fairness.reset_performed is True and fairness.reset_error is None, "reset did not complete cleanly")
    _require(fairness.post_reset_items == 0, "completed episode leaked memory")
    _require(fairness.fresh_scope_items == 0, "fresh episode scope leaked memory")
    _require(fairness.planner_model == planner["model"], "planner model mismatch")
    _require(fairness.temperature == planner["temperature"], "planner temperature mismatch")
    _require(fairness.system_prompt_hash == planner["system_prompt_hash"], "system prompt hash mismatch")
    _require(fairness.tool_set_hash == planner["tool_set_hash"], "tool hash mismatch")
    _require(fairness.planner_user_template_hash == planner["planner_user_template_hash"], "planner template hash mismatch")
    expected_producer = _producer_compact(producer)
    actual_producer = {
        "source_tree_fingerprint": fairness.source_tree_fingerprint,
        "source_file_count": fairness.source_file_count,
        "git_available": fairness.git_available,
        "git_commit": fairness.git_commit,
        "git_dirty": fairness.git_dirty,
        "git_status_fingerprint": fairness.git_status_fingerprint,
    }
    _require(actual_producer == expected_producer, "result producer provenance mismatch")
    _require(fairness.fixture_selector == manifest["fixture_selector"], "fixture selector mismatch")
    _require(fairness.fixture_identity == manifest["fixture_identity"], "fixture identity mismatch")
    if backend == "none":
        _require(
            all(not step.retrieved_items for step in _all_steps(result))
            and all(not probe.items for probe in result.retrieval_probes),
            "NoMemory returned long-term memory",
        )


def load_formal_dataset(
    results_dir: str | Path,
    *,
    spec: FormalStudySpec = DEFAULT_SPEC,
) -> FormalDataset:
    """Load and fully validate one frozen Formal results directory."""

    root = Path(results_dir).resolve()
    _require(root.is_dir(), f"formal results directory does not exist: {root}")
    study_path = root / "formal_study_manifest.json"
    manifest = _read_json(study_path)
    _validate_root_manifest(root, manifest, spec)
    producer = manifest["producer"]
    planner = manifest["planner"]
    campaign_declarations = {item["scenario"]: item for item in manifest["campaigns"]}
    cells_by_scenario: dict[str, list[FormalCell]] = defaultdict(list)
    signature_to_cell: dict[str, FormalCell] = {}
    for cell in spec.cells:
        cells_by_scenario[cell.scenario].append(cell)
        signature_to_cell[_cell_signature(cell.scenario, cell.params)] = cell

    runs: list[FormalRun] = []
    linked_paths: set[Path] = set()
    episode_ids: set[str] = set()
    run_ids: set[str] = set()
    composite_keys: set[tuple[str, str, str, int]] = set()
    event_streams: dict[tuple[str, int], str] = {}

    for scenario in spec.scenarios:
        declaration = campaign_declarations[scenario]
        campaign_dir = (root / str(declaration["relative_dir"])).resolve()
        _require(campaign_dir.parent == root, f"campaign directory escapes formal root: {campaign_dir}")
        campaign = _read_json(campaign_dir / "campaign_manifest.json")
        _require(
            declaration.get("expected_runs")
            == len(spec.backends) * len(spec.seeds) * len(cells_by_scenario[scenario]),
            "formal campaign expected_runs mismatch",
        )
        _require(
            declaration.get("cells")
            == [cell.plan_dict() for cell in cells_by_scenario[scenario]],
            "formal campaign declaration cells mismatch",
        )
        _require(campaign.get("schema_version") == "controlled-campaign/v4", "campaign schema mismatch")
        _require(campaign.get("mode") == "controlled", "campaign mode mismatch")
        _require(campaign.get("scenario") == scenario, "campaign scenario mismatch")
        _require(Path(str(campaign.get("results_dir"))).resolve() == campaign_dir, "campaign results_dir mismatch")
        _require(campaign.get("seeds") == list(spec.seeds), "campaign seeds mismatch")
        _require(campaign.get("backends") == list(spec.backends), "campaign backends mismatch")
        expected_cells = [
            {"name": cell.name, "params": dict(cell.params), "effective_params": dict(cell.params)}
            for cell in cells_by_scenario[scenario]
        ]
        _require(campaign.get("cells") == expected_cells, "campaign cell plan mismatch")
        versions = {cell.semantics_version for cell in cells_by_scenario[scenario]}
        _require(len(versions) == 1 and campaign.get("semantics_version") in versions, "campaign semantics mismatch")
        _require(_producer_compact(campaign.get("provenance", {})) == _producer_compact(producer), "campaign producer mismatch")
        fixtures = campaign.get("fixtures")
        _require(isinstance(fixtures, list) and len(fixtures) == 1, "campaign fixture declaration mismatch")
        fixture_selector, fixture_identity = fixtures[0]
        campaign_contract = {
            "fixture_selector": fixture_selector,
            "fixture_identity": fixture_identity,
        }
        entries = campaign.get("runs")
        _require(isinstance(entries, list), "campaign runs must be a list")
        expected_count = len(spec.backends) * len(spec.seeds) * len(cells_by_scenario[scenario])
        _require(len(entries) == expected_count, f"{scenario}: manifest run count mismatch")
        entry_keys: set[tuple[str, str, int]] = set()
        for entry in entries:
            _require(isinstance(entry, dict), "campaign run entry is not an object")
            _require(entry.get("status") == "ok", f"producer failure at {scenario} run {entry.get('index')}")
            _require(entry.get("returncode") == 0, "producer returncode mismatch")
            backend = entry.get("backend")
            seed = entry.get("seed")
            _require(backend in spec.backends and seed in spec.seeds, "unexpected backend/seed")
            signature = _cell_signature(scenario, entry.get("effective_params", {}))
            cell = signature_to_cell.get(signature)
            _require(cell is not None and entry.get("cell") == cell.name, "wrong or unexpected treatment cell")
            _require(entry.get("requested_params") == dict(cell.params), "requested params mismatch")
            _require(entry.get("fixture_selector") == fixture_selector, "entry fixture selector mismatch")
            _require(entry.get("fixture_identity") == fixture_identity, "entry fixture identity mismatch")
            _require(entry.get("expected_health_mode") == "mock", "expected health mode mismatch")
            _require(entry.get("health_mode") == "mock", "observed health mode mismatch")
            entry_key = (cell.name, str(backend), int(seed))
            _require(entry_key not in entry_keys, f"duplicate manifest run {entry_key}")
            entry_keys.add(entry_key)
            files = entry.get("result_files")
            _require(isinstance(files, list) and len(files) == 1, "run must link exactly one result")
            result_path = Path(str(files[0])).resolve()
            _require(result_path.parent == campaign_dir, "result path escapes campaign directory")
            _require(result_path not in linked_paths, "one result file is linked more than once")
            linked_paths.add(result_path)
            try:
                result = ScenarioResult.model_validate_json(result_path.read_text(encoding="utf-8"))
            except (OSError, ValidationError) as exc:
                raise FormalIntegrityError(f"invalid ScenarioResult {result_path}: {exc}") from exc
            _require(result.scenario == scenario, "result scenario mismatch")
            _require(result.seed == seed, "result seed mismatch")
            _require(result.memory_backend == backend, "result backend mismatch")
            _require(result.campaign_mode == "controlled", "result mode mismatch")
            _require(result.params == dict(cell.params), "result params mismatch")
            task_success = result.metrics.get("task_success")
            _require(task_success in {0, 1}, "strict task_success is missing or invalid")
            _require(result.success == bool(task_success), "result.success and strict task_success disagree")
            _require(result.episode_id not in episode_ids, "duplicate episode_id")
            episode_ids.add(result.episode_id)
            _require(result.run_log is not None, "result has no primary run log")
            assert result.run_log is not None
            result_run_ids = [entry.run_log.run_id for entry in result.run_logs]
            _require(
                len(result_run_ids) == len(set(result_run_ids)),
                "duplicate run_id within multi-session result",
            )
            if result.run_log.run_id not in result_run_ids:
                result_run_ids.append(result.run_log.run_id)
            for result_run_id in result_run_ids:
                _require(result_run_id not in run_ids, "duplicate run_id")
                run_ids.add(result_run_id)
            composite = (scenario, cell.name, str(backend), int(seed))
            _require(composite not in composite_keys, f"duplicate formal observation {composite}")
            composite_keys.add(composite)
            _validate_fairness(
                result,
                cell=cell,
                manifest=campaign_contract,
                producer=producer,
                planner=planner,
                seed=int(seed),
                backend=str(backend),
            )
            _validate_task_success(result)
            present, rank = retrieval_evidence(result)
            _require(_metric_matches_retrieval(result, present, rank), "stored retrieval metric does not recompute")
            stream_key = (cell.name, int(seed))
            stream = _normalized_events(result)
            previous = event_streams.setdefault(stream_key, stream)
            _require(previous == stream, "same-seed ExperienceEvent stream differs across backends")
            runs.append(
                FormalRun(
                    cell=cell,
                    result=result,
                    result_path=result_path,
                    retrieval_present=present,
                    retrieval_rank=rank,
                    attribution=classify_failure(result, present),
                )
            )
        expected_entry_keys = {
            (cell.name, backend, seed)
            for cell in cells_by_scenario[scenario]
            for backend in spec.backends
            for seed in spec.seeds
        }
        _require(entry_keys == expected_entry_keys, f"{scenario}: missing or unexpected schedule entries")
        physical = {path.resolve() for path in campaign_dir.glob("scenario_*.json")}
        campaign_linked = {path for path in linked_paths if path.parent == campaign_dir}
        _require(physical == campaign_linked, f"{scenario}: missing, unlinked, or unexpected result files")

    _require(len(runs) == spec.expected_runs, "actual validated run count mismatch")
    expected_composites = {
        (cell.scenario, cell.name, backend, seed)
        for cell in spec.cells
        for backend in spec.backends
        for seed in spec.seeds
    }
    _require(composite_keys == expected_composites, "formal matrix is incomplete")
    ordered = tuple(
        sorted(
            runs,
            key=lambda run: (
                run.cell.order,
                spec.backends.index(run.result.memory_backend),
                spec.seeds.index(run.result.seed),
            ),
        )
    )
    integrity = {
        "expected": spec.expected_runs,
        "actual": len(ordered),
        "valid": len(ordered),
        "invalid": 0,
        "missing": 0,
        "duplicates": 0,
        "unexpected": 0,
        "producer_failures": 0,
        "retries": 0,
        "exclusions": 0,
        "verdict": "PASS",
    }
    return FormalDataset(root=root, manifest=manifest, runs=ordered, integrity=integrity)


def exact_mcnemar_p(a_only: int, b_only: int) -> float:
    """Two-sided exact McNemar p-value from discordant-pair counts."""

    if a_only < 0 or b_only < 0:
        raise ValueError("discordant counts must be non-negative")
    discordant = a_only + b_only
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, k) for k in range(min(a_only, b_only) + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def _percentile(values: Sequence[float], probability: float) -> float:
    """R-7/NumPy-linear percentile, implemented without optional deps."""

    if not values:
        raise ValueError("cannot take a percentile of an empty sequence")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def paired_bootstrap_ci(
    a: Sequence[int],
    b: Sequence[int],
    *,
    seed: int = BOOTSTRAP_SEED,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> tuple[float, float]:
    """Percentile 95% CI for paired risk difference ``mean(a-b)``.

    Every comparison resets ``random.Random`` to the pre-registered seed, so
    output is independent of traversal order and bit-reproducible.
    """

    if len(a) != len(b) or not a:
        raise ValueError("paired bootstrap requires equal non-empty sequences")
    if resamples < 1:
        raise ValueError("resamples must be positive")
    if any(value not in {0, 1} for value in (*a, *b)):
        raise ValueError("paired outcomes must be binary")
    differences = [left - right for left, right in zip(a, b, strict=True)]
    rng = random.Random(seed)
    n = len(differences)
    samples = [
        sum(differences[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(resamples)
    ]
    return _percentile(samples, 0.025), _percentile(samples, 0.975)


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, returned in input order."""

    if any(not 0.0 <= value <= 1.0 for value in p_values):
        raise ValueError("p-values must be in [0, 1]")
    count = len(p_values)
    ranked = sorted(enumerate(p_values), key=lambda item: (item[1], item[0]))
    adjusted = [0.0] * count
    running = 0.0
    for rank, (index, value) in enumerate(ranked):
        running = max(running, min(1.0, (count - rank) * value))
        adjusted[index] = running
    return adjusted


def failure_point(
    levels: Sequence[tuple[str, int, int]],
    *,
    threshold: float = 0.8,
) -> str | None:
    """First tested level with success rate strictly below ``threshold``."""

    for level, successes, total in levels:
        if total <= 0 or not 0 <= successes <= total:
            raise ValueError("invalid failure-point numerator/denominator")
        if successes / total < threshold:
            return level
    return None


def _mean(values: Iterable[float | int | None]) -> float | None:
    present = [float(value) for value in values if isinstance(value, (int, float))]
    return sum(present) / len(present) if present else None


def _median(values: Iterable[float | int | None]) -> float | None:
    present = [float(value) for value in values if isinstance(value, (int, float))]
    return statistics.median(present) if present else None


def _tokens(result: ScenarioResult) -> tuple[int | None, int | None, int | None]:
    prompt = result.metrics.get("total_prompt_tokens")
    completion = result.metrics.get("total_completion_tokens")
    prompt_value = int(prompt) if isinstance(prompt, (int, float)) else None
    completion_value = int(completion) if isinstance(completion, (int, float)) else None
    if prompt_value is None and completion_value is None:
        total = None
    else:
        total = (prompt_value or 0) + (completion_value or 0)
    return prompt_value, completion_value, total


def _planner_latency(result: ScenarioResult) -> float | None:
    steps = _all_steps(result)
    return sum(step.latency_s for step in steps) if steps else None


def run_rows(dataset: FormalDataset) -> list[dict[str, Any]]:
    """One flat auditable row per validated Formal run."""

    rows: list[dict[str, Any]] = []
    for run in dataset.runs:
        prompt, completion, total = _tokens(run.result)
        category = (
            "retrieval_present_behavior_success"
            if run.retrieval_present and run.success
            else "retrieval_present_behavior_failure"
            if run.retrieval_present
            else "retrieval_absent_behavior_success"
            if run.success
            else "retrieval_absent_behavior_failure"
        )
        rows.append(
            {
                "study_id": dataset.manifest["study_id"],
                "scenario": run.cell.scenario,
                "cell": run.cell.name,
                "ladder": run.cell.ladder,
                "level": run.cell.level,
                "backend": run.result.memory_backend,
                "seed": run.result.seed,
                "task_success": int(run.success),
                "retrieval_present": int(run.retrieval_present),
                "retrieval_rank": run.retrieval_rank,
                "retrieval_behavior_category": category,
                "failure_attribution": run.attribution,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total,
                "llm_calls": run.result.metrics.get("llm_calls"),
                "avg_add_latency_ms": run.result.metrics.get("avg_add_latency_ms"),
                "avg_retrieve_latency_ms": run.result.metrics.get("avg_retrieve_latency_ms"),
                "planner_latency_s": _planner_latency(run.result),
                "episode_id": run.result.episode_id,
                "result_file": str(run.result_path),
            }
        )
    return rows


def cell_rows(dataset: FormalDataset, spec: FormalStudySpec = DEFAULT_SPEC) -> list[dict[str, Any]]:
    """Aggregate task/retrieval/cost outcomes at backend×treatment grain."""

    grouped: dict[tuple[str, str], list[FormalRun]] = defaultdict(list)
    for run in dataset.runs:
        grouped[(run.cell.name, run.result.memory_backend)].append(run)
    rows: list[dict[str, Any]] = []
    for cell in spec.cells:
        for backend in spec.backends:
            group = sorted(grouped[(cell.name, backend)], key=lambda run: run.result.seed)
            _require(len(group) == len(spec.seeds), "cell aggregation denominator mismatch")
            successes = sum(run.success for run in group)
            retrievals = sum(run.retrieval_present for run in group)
            categories = Counter(
                (
                    "present_success"
                    if run.retrieval_present and run.success
                    else "present_failure"
                    if run.retrieval_present
                    else "absent_success"
                    if run.success
                    else "absent_failure"
                )
                for run in group
            )
            attributions = Counter(run.attribution for run in group)
            token_values = [_tokens(run.result)[2] for run in group]
            rows.append(
                {
                    "scenario": cell.scenario,
                    "cell": cell.name,
                    "ladder": cell.ladder,
                    "level": cell.level,
                    "backend": backend,
                    "success_n": successes,
                    "n": len(group),
                    "success_rate": successes / len(group),
                    "retrieval_n": retrievals,
                    "retrieval_rate": retrievals / len(group),
                    "retrieval_present_behavior_success": categories["present_success"],
                    "retrieval_present_behavior_failure": categories["present_failure"],
                    "retrieval_absent_behavior_success": categories["absent_success"],
                    "retrieval_absent_behavior_failure": categories["absent_failure"],
                    "failure_R": attributions["R"],
                    "failure_P": attributions["P"],
                    "failure_E": attributions["E"],
                    "failure_Unknown": attributions["Unknown"],
                    "mean_total_tokens": _mean(token_values),
                    "median_total_tokens": _median(token_values),
                    "mean_add_latency_ms": _mean(
                        run.result.metrics.get("avg_add_latency_ms") for run in group
                    ),
                    "mean_retrieve_latency_ms": _mean(
                        run.result.metrics.get("avg_retrieve_latency_ms") for run in group
                    ),
                    "mean_planner_latency_s": _mean(
                        _planner_latency(run.result) for run in group
                    ),
                }
            )
    return rows


def pairwise_rows(dataset: FormalDataset, spec: FormalStudySpec = DEFAULT_SPEC) -> list[dict[str, Any]]:
    """The pre-registered 24 active-backend paired primary comparisons."""

    lookup = {
        (run.cell.name, run.result.memory_backend, run.result.seed): int(run.success)
        for run in dataset.runs
    }
    rows: list[dict[str, Any]] = []
    for cell in spec.cells:
        for backend_a, backend_b in ACTIVE_BACKEND_PAIRS:
            _require(backend_a in spec.backends and backend_b in spec.backends, "active pair missing from spec")
            a = [lookup[(cell.name, backend_a, seed)] for seed in spec.seeds]
            b = [lookup[(cell.name, backend_b, seed)] for seed in spec.seeds]
            a_only = sum(left == 1 and right == 0 for left, right in zip(a, b, strict=True))
            b_only = sum(left == 0 and right == 1 for left, right in zip(a, b, strict=True))
            low, high = paired_bootstrap_ci(a, b)
            rows.append(
                {
                    "scenario": cell.scenario,
                    "cell": cell.name,
                    "backend_a": backend_a,
                    "backend_b": backend_b,
                    "n_pairs": len(spec.seeds),
                    "success_a": sum(a),
                    "success_b": sum(b),
                    "paired_risk_difference_a_minus_b": (sum(a) - sum(b)) / len(a),
                    "a_success_b_failure": a_only,
                    "a_failure_b_success": b_only,
                    "discordant_pairs": a_only + b_only,
                    "exact_mcnemar_p": exact_mcnemar_p(a_only, b_only),
                    "bootstrap_95_ci_low": low,
                    "bootstrap_95_ci_high": high,
                    "bootstrap_seed": BOOTSTRAP_SEED,
                    "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
                }
            )
    adjusted = holm_adjust([float(row["exact_mcnemar_p"]) for row in rows])
    for row, adjusted_p in zip(rows, adjusted, strict=True):
        row["holm_adjusted_p"] = adjusted_p
        row["holm_reject_0_05"] = adjusted_p <= PRIMARY_ALPHA
    return rows


def failure_point_rows(
    cells: Sequence[dict[str, Any]],
    spec: FormalStudySpec = DEFAULT_SPEC,
) -> list[dict[str, Any]]:
    """Failure Points for the two pre-registered ladders only."""

    lookup = {(row["cell"], row["backend"]): row for row in cells}
    rows: list[dict[str, Any]] = []
    for ladder in ("memory_noise_stress", "long_lived_memory"):
        ladder_cells = [cell for cell in spec.cells if cell.ladder == ladder]
        for backend in spec.backends:
            levels = [
                (
                    str(cell.level),
                    int(lookup[(cell.name, backend)]["success_n"]),
                    int(lookup[(cell.name, backend)]["n"]),
                )
                for cell in ladder_cells
            ]
            point = failure_point(levels)
            rows.append(
                {
                    "ladder": ladder,
                    "backend": backend,
                    "threshold": "task_success < 0.80",
                    "failure_point": point,
                    "observed": point is not None,
                    "interpretation": (
                        f"Failure Point at {point}"
                        if point is not None
                        else "Failure Point not observed within tested ladder"
                    ),
                }
            )
    return rows


def failure_attribution_rows(cells: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "scenario": row["scenario"],
            "cell": row["cell"],
            "backend": row["backend"],
            "success": row["success_n"],
            "retrieval_failure_R": row["failure_R"],
            "planning_failure_P": row["failure_P"],
            "environment_failure_E": row["failure_E"],
            "unknown": row["failure_Unknown"],
        }
        for row in cells
    ]


def representative_cases(runs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic small set of same-seed discordant/mechanism examples."""

    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in runs:
        grouped[(str(row["cell"]), int(row["seed"]))].append(row)
    cases: list[dict[str, Any]] = []
    for (cell, seed), group in sorted(grouped.items()):
        active = [row for row in group if row["backend"] != "none"]
        if len({row["task_success"] for row in active}) > 1:
            cases.append(
                {
                    "cell": cell,
                    "seed": seed,
                    "kind": "active_backend_behavior_discordance",
                    "outcomes": {
                        row["backend"]: {
                            "success": row["task_success"],
                            "retrieval_present": row["retrieval_present"],
                            "failure_attribution": row["failure_attribution"],
                            "episode_id": row["episode_id"],
                        }
                        for row in active
                    },
                }
            )
        if len(cases) >= 8:
            break
    if not cases:
        for row in runs:
            if row["retrieval_behavior_category"] == "retrieval_present_behavior_failure":
                cases.append(
                    {
                        "cell": row["cell"],
                        "seed": row["seed"],
                        "kind": "retrieval_present_behavior_failure",
                        "outcomes": {
                            row["backend"]: {
                                "success": row["task_success"],
                                "retrieval_present": row["retrieval_present"],
                                "failure_attribution": row["failure_attribution"],
                                "episode_id": row["episode_id"],
                            }
                        },
                    }
                )
                break
    return cases


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    _require(bool(rows), f"refusing to write empty CSV {path.name}")
    columns = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _fmt_rate(value: float) -> str:
    return f"{value:.1%}"


def _fmt_number(value: Any, decimals: int = 3) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.{decimals}f}"


def _markdown_report(
    dataset: FormalDataset,
    cells: Sequence[dict[str, Any]],
    pairs: Sequence[dict[str, Any]],
    points: Sequence[dict[str, Any]],
    cases: Sequence[dict[str, Any]],
    spec: FormalStudySpec,
) -> str:
    producer = dataset.manifest["producer"]
    lines = [
        "# MineMemBench M15 Controlled Formal V1 Report",
        "",
        f"- Study id: `{dataset.manifest['study_id']}`",
        f"- Producer commit: `{producer['git_commit']}`",
        f"- Source fingerprint: `{producer['source_tree_fingerprint']}`",
        f"- Design: paired seeds `{spec.seeds[0]}–{spec.seeds[-1]}`, N={len(spec.seeds)} per backend×cell",
        f"- Runs: {dataset.integrity['actual']}/{dataset.integrity['expected']} valid; integrity **{dataset.integrity['verdict']}**",
        "- Primary endpoint: strict evaluator-derived `task_success`.",
        "- Scope: configured backends under this frozen Controlled fixture only; no global leaderboard.",
        "",
        "## Scenario-specific outcomes",
        "",
        "| Scenario | Cell | Backend | Success | Retrieval | R | P | E | Unknown |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in cells:
        lines.append(
            f"| {row['scenario']} | {row['cell']} | {row['backend']} | "
            f"{row['success_n']}/{row['n']} ({_fmt_rate(float(row['success_rate']))}) | "
            f"{row['retrieval_n']}/{row['n']} ({_fmt_rate(float(row['retrieval_rate']))}) | "
            f"{row['failure_R']} | {row['failure_P']} | {row['failure_E']} | "
            f"{row['failure_Unknown']} |"
        )
    lines.extend(
        [
            "",
            "## Retrieval → behavior",
            "",
            "The four categories below are derived from the causal retrieval snapshot(s) and strict task outcome; they do not use LLM reason text.",
            "",
            "| Cell | Backend | retrieval+ / success | retrieval+ / failure | retrieval− / success | retrieval− / failure |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in cells:
        lines.append(
            f"| {row['cell']} | {row['backend']} | "
            f"{row['retrieval_present_behavior_success']} | "
            f"{row['retrieval_present_behavior_failure']} | "
            f"{row['retrieval_absent_behavior_success']} | "
            f"{row['retrieval_absent_behavior_failure']} |"
        )
    lines.extend(
        [
            "",
            "## Active-backend paired comparisons",
            "",
            "Two-sided exact McNemar tests use the 10 paired seeds. Effect size is paired risk difference (A−B); 95% CIs use the frozen paired bootstrap (seed 20260811, 10,000 resamples). Holm adjustment covers all 24 pre-registered primary comparisons.",
            "",
            "| Cell | A | B | A success | B success | RD | 95% CI | Discordant | exact p | Holm p |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in pairs:
        lines.append(
            f"| {row['cell']} | {row['backend_a']} | {row['backend_b']} | "
            f"{row['success_a']}/{row['n_pairs']} | {row['success_b']}/{row['n_pairs']} | "
            f"{_fmt_number(row['paired_risk_difference_a_minus_b'])} | "
            f"[{_fmt_number(row['bootstrap_95_ci_low'])}, {_fmt_number(row['bootstrap_95_ci_high'])}] | "
            f"{row['a_success_b_failure']} / {row['a_failure_b_success']} | "
            f"{_fmt_number(row['exact_mcnemar_p'], 4)} | {_fmt_number(row['holm_adjusted_p'], 4)} |"
        )
    lines.extend(
        [
            "",
            "## Failure Points",
            "",
            "Failure Point is the first tested ladder level with strict task success <80%; 8/10 is not a failure and no interpolation is used. Lifetime is a composite treatment, not an event-count-only effect.",
            "",
            "| Ladder | Backend | Result |",
            "|---|---|---|",
        ]
    )
    for row in points:
        lines.append(f"| {row['ladder']} | {row['backend']} | {row['interpretation']} |")
    lines.extend(
        [
            "",
            "## Tokens and latency (descriptive only)",
            "",
            "These totals describe planner tokens and recorded operation latency. They do not normalize backend-internal embedding/LLM work and therefore do not support cost-efficiency claims.",
            "",
            "| Cell | Backend | mean tokens | median tokens | add ms | retrieve ms | planner seconds |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in cells:
        lines.append(
            f"| {row['cell']} | {row['backend']} | {_fmt_number(row['mean_total_tokens'], 1)} | "
            f"{_fmt_number(row['median_total_tokens'], 1)} | {_fmt_number(row['mean_add_latency_ms'])} | "
            f"{_fmt_number(row['mean_retrieve_latency_ms'])} | {_fmt_number(row['mean_planner_latency_s'])} |"
        )
    lines.extend(["", "## Representative same-seed cases", ""])
    if cases:
        for case in cases:
            outcome = ", ".join(
                f"{backend}: success={value['success']}, retrieval={value['retrieval_present']}, attribution={value['failure_attribution']}"
                for backend, value in case["outcomes"].items()
            )
            lines.append(f"- `{case['cell']}` seed {case['seed']} ({case['kind']}): {outcome}.")
    else:
        lines.append("- No active-backend discordant or retrieval-present behavior-failure case was observed.")
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "All claims must begin: ‘In the current frozen MineMemBench configuration and Controlled Formal V1…’. Controlled and Native evidence are not pooled. Failure-learning v4 remains a diagnostic mechanism case study and is absent from these ranking-eligible cells. Graphiti and calibration data are absent. Statistical non-significance is not evidence of equivalence, especially at N=10.",
            "",
        ]
    )
    return "\n".join(lines)


def _svg_curve(
    path: Path,
    rows: Sequence[dict[str, Any]],
    *,
    value_key: str,
    title: str,
    spec: FormalStudySpec,
) -> None:
    """Small dependency-free SVG for the two ordered Formal ladders."""

    width, height = 920, 420
    colors = {"none": "#777777", "vector": "#2563eb", "mem0": "#16a34a", "letta": "#dc2626"}
    lookup = {(row["cell"], row["backend"]): float(row[value_key]) for row in rows}
    panels = [
        ("Memory Noise", [cell for cell in spec.cells if cell.ladder == "memory_noise_stress"]),
        ("Long-Lived (composite)", [cell for cell in spec.cells if cell.ladder == "long_lived_memory"]),
    ]
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="20" y="28" font-family="sans-serif" font-size="20" font-weight="bold">{title}</text>',
    ]
    for panel_index, (panel_title, ladder_cells) in enumerate(panels):
        left = 55 + panel_index * 450
        top, plot_w, plot_h = 70, 340, 270
        svg.append(f'<text x="{left}" y="55" font-family="sans-serif" font-size="15">{panel_title}</text>')
        svg.append(f'<path d="M {left} {top} V {top + plot_h} H {left + plot_w}" stroke="#222" fill="none"/>')
        svg.append(f'<path d="M {left} {top + plot_h * .2} H {left + plot_w}" stroke="#bbb" stroke-dasharray="4 4" fill="none"/>')
        for tick in range(0, 6):
            y = top + plot_h - tick * plot_h / 5
            svg.append(f'<text x="{left - 38}" y="{y + 4}" font-family="sans-serif" font-size="11">{tick * 20}%</text>')
        x_positions = [left + index * plot_w / (len(ladder_cells) - 1) for index in range(len(ladder_cells))]
        for x, cell in zip(x_positions, ladder_cells, strict=True):
            svg.append(f'<text x="{x - 10}" y="{top + plot_h + 20}" font-family="sans-serif" font-size="11">{cell.level}</text>')
        for backend in spec.backends:
            points = [
                (x, top + plot_h * (1.0 - lookup[(cell.name, backend)]))
                for x, cell in zip(x_positions, ladder_cells, strict=True)
            ]
            encoded = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
            color = colors.get(backend, "#000")
            svg.append(f'<polyline points="{encoded}" fill="none" stroke="{color}" stroke-width="2"/>')
            for x, y in points:
                svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')
    legend_x = 55
    for index, backend in enumerate(spec.backends):
        x = legend_x + index * 105
        svg.append(f'<rect x="{x}" y="385" width="14" height="3" fill="{colors.get(backend, "#000")}"/>')
        svg.append(f'<text x="{x + 20}" y="390" font-family="sans-serif" font-size="12">{backend}</text>')
    svg.append("</svg>")
    path.write_text("\n".join(svg) + "\n", encoding="utf-8")


def analyze_formal(
    results_dir: str | Path,
    *,
    spec: FormalStudySpec = DEFAULT_SPEC,
) -> dict[str, Path]:
    """Validate, analyze, and write every pre-registered Formal artifact."""

    dataset = load_formal_dataset(results_dir, spec=spec)
    runs = run_rows(dataset)
    cells = cell_rows(dataset, spec)
    pairs = pairwise_rows(dataset, spec)
    points = failure_point_rows(cells, spec)
    attributions = failure_attribution_rows(cells)
    cases = representative_cases(runs)
    retrieval_behavior = Counter(row["retrieval_behavior_category"] for row in runs)
    summary = {
        "schema_version": "minemembench-formal-analysis/v1",
        "study_id": dataset.manifest["study_id"],
        "producer": dataset.manifest["producer"],
        "integrity": dataset.integrity,
        "plan": spec.plan_dict(),
        "statistics": {
            "paired_test": "two-sided exact McNemar",
            "effect_size": "paired risk difference (backend_a - backend_b)",
            "ci": "paired percentile bootstrap 95% CI (R-7 quantiles)",
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "multiplicity": "Holm-Bonferroni over 24 active-backend primary comparisons",
            "alpha": PRIMARY_ALPHA,
        },
        "cells": cells,
        "pairwise": pairs,
        "failure_points": points,
        "retrieval_behavior": dict(sorted(retrieval_behavior.items())),
        "representative_cases": cases,
    }
    root = dataset.root
    paths = {
        "summary": root / "formal_summary.json",
        "runs": root / "formal_runs.csv",
        "cells": root / "formal_cells.csv",
        "pairwise": root / "formal_pairwise.csv",
        "failure_points": root / "formal_failure_points.csv",
        "failure_attribution": root / "formal_failure_attribution.csv",
        "report": root / "formal_report.md",
        "success_curves": root / "formal_success_curves.svg",
        "retrieval_curves": root / "formal_retrieval_curves.svg",
    }
    paths["summary"].write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_csv(paths["runs"], runs)
    _write_csv(paths["cells"], cells)
    _write_csv(paths["pairwise"], pairs)
    _write_csv(paths["failure_points"], points)
    _write_csv(paths["failure_attribution"], attributions)
    paths["report"].write_text(
        _markdown_report(dataset, cells, pairs, points, cases, spec),
        encoding="utf-8",
    )
    _svg_curve(paths["success_curves"], cells, value_key="success_rate", title="Strict task-success curves", spec=spec)
    _svg_curve(paths["retrieval_curves"], cells, value_key="retrieval_rate", title="Causal relevant-retrieval curves", spec=spec)
    return paths
