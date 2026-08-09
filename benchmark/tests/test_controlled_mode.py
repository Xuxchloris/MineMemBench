"""Controlled Mode tests (TASK-004): deterministic campaign inputs, canonical
fixture enforcement, normalized planner state, and the campaign runner
lifecycle — all hermetic (fakes only, no network, no real LLM API).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_controlled_campaign as campaign  # noqa: E402

from minemembench import cli  # noqa: E402
from minemembench.agent.planner import Planner  # noqa: E402
from minemembench.core.client import BotBridgeError  # noqa: E402
from minemembench.core.models import BotMode, EventType, HealthResponse  # noqa: E402
from minemembench.core.runner import AgentRunner  # noqa: E402
from minemembench.memory.no_memory import NoMemoryBackend  # noqa: E402
from minemembench.memory.base import MemoryQuery  # noqa: E402
from minemembench.memory.vector_memory import VectorMemoryBackend  # noqa: E402
from minemembench.scenarios.base import ScenarioContext  # noqa: E402
from minemembench.scenarios.delayed_recall import DelayedRecallScenario  # noqa: E402
from minemembench.scenarios.registry import create_scenario  # noqa: E402

from .conftest import FakeBotClient, SmartFakeLLM, make_settings, make_world_state  # noqa: E402

from .test_run_loop import FakeBridge, RecordingBackend  # noqa: E402


async def _run_controlled(
    memory,
    *,
    seed: int = 42,
    episode_id: str,
    params: dict | None = None,
):
    from minemembench.memory.base import EventRecordingBackend

    scenario = DelayedRecallScenario()
    if params:
        scenario.apply_params(params)
    llm = SmartFakeLLM()
    bot = FakeBotClient()
    recording = EventRecordingBackend(memory)
    runner = AgentRunner(bot, recording, llm)
    ctx = ScenarioContext(
        bot=bot,
        memory=recording,
        runner=runner,
        llm=llm,
        settings=make_settings(),
        seed=seed,
        episode_id=episode_id,
        campaign_mode="controlled",
    )
    result = await scenario.run(ctx)
    # Mirror the CLI: the result carries the complete offered event sequence.
    result.injected_events = list(recording.offered_events)
    return result


def _semantic_stream(result):
    """The injected event sequence minus the isolation episode id."""

    return [
        (
            event.event_id,
            event.timestamp,
            event.actor,
            event.target,
            event.event_type,
            event.location,
            event.context,
            event.outcome,
        )
        for event in result.injected_events
    ]


# --- deterministic semantic events -------------------------------------------


async def test_controlled_events_identical_across_backends_and_scopes(tmp_path) -> None:
    """Same (seed, params) → identical event ids, logical timestamps,
    actor/type/context/outcome and order; only episode_id differs."""

    params = {"interference_count": 10, "similar_distractor_count": 5}
    first = await _run_controlled(
        VectorMemoryBackend(str(tmp_path / "a.db")),
        episode_id="ep-a",
        params=params,
    )
    second = await _run_controlled(
        NoMemoryBackend(),
        episode_id="ep-b",
        params=params,
    )

    assert first.injected_events
    assert _semantic_stream(first) == _semantic_stream(second)
    assert {e.episode_id for e in first.injected_events} == {"ep-a"}
    assert {e.episode_id for e in second.injected_events} == {"ep-b"}
    # Deterministic identity: no uuid4/wall-clock artifacts.
    assert all(e.event_id.startswith("ctrl-") for e in first.injected_events)
    timestamps = [e.timestamp for e in first.injected_events]
    assert timestamps == sorted(timestamps)  # logical clock is monotone


async def test_controlled_events_repeat_for_same_seed_and_params(tmp_path) -> None:
    first = await _run_controlled(
        VectorMemoryBackend(str(tmp_path / "a.db")), episode_id="ep-a"
    )
    second = await _run_controlled(
        VectorMemoryBackend(str(tmp_path / "b.db")), episode_id="ep-b"
    )
    assert _semantic_stream(first) == _semantic_stream(second)


async def test_native_mode_keeps_uuid_events(tmp_path) -> None:
    """Native mode is unchanged: uuid4 ids, no ctrl- prefix."""

    from minemembench.memory.base import EventRecordingBackend

    scenario = DelayedRecallScenario()
    llm = SmartFakeLLM()
    bot = FakeBotClient()
    recording = EventRecordingBackend(VectorMemoryBackend(str(tmp_path / "mem.db")))
    ctx = ScenarioContext(
        bot=bot,
        memory=recording,
        runner=AgentRunner(bot, recording, llm),
        llm=llm,
        settings=make_settings(),
        seed=42,
        episode_id="ep-native",
    )
    result = await scenario.run(ctx)
    assert result.injected_events == []  # scenario result filled by the CLI
    assert recording.offered_events
    assert not any(e.event_id.startswith("ctrl-") for e in recording.offered_events)


async def test_nomemory_input_events_are_retained(tmp_path) -> None:
    result = await _run_controlled(NoMemoryBackend(), episode_id="ep-none")
    assert result.memory_backend == "none"
    # 1 target fact + 10 noise facts at default params — all offered, even
    # though NoMemory stores nothing.
    assert len(result.injected_events) == 11


async def test_run_step_retains_the_raw_world_state(tmp_path) -> None:
    result = await _run_controlled(
        VectorMemoryBackend(str(tmp_path / "mem.db")), episode_id="ep-ws"
    )
    assert result.run_log is not None
    step = result.run_log.steps[0]
    assert step.world_state is not None
    assert step.world_state.timestamp is not None  # raw, unnormalized
    assert step.world_state.username == "BenchBot"
    assert step.world_state.mode.value == "mock"
    # The pre-action observation, not the post-action position.
    assert step.world_state.model_dump(mode="json")["timestamp"]


# --- planner WorldState normalization ----------------------------------------


def test_planner_prompt_excludes_volatile_timestamp() -> None:
    planner = Planner(FakeBotClient(), NoMemoryBackend(), SmartFakeLLM())
    state = make_world_state()
    earlier = state.model_copy(
        update={"timestamp": datetime(2020, 1, 1, tzinfo=UTC)}
    )

    msg_a = planner._build_user_message("goal", state, [], [])
    msg_b = planner._build_user_message("goal", earlier, [], [])

    assert msg_a == msg_b  # wall time never reaches the planner
    state_section = msg_a.split("Current world state (JSON):\n", 1)[1].split(
        "\n\n", 1
    )[0]
    assert "timestamp" not in state_section
    assert '"time_of_day": 6000' in state_section  # content is preserved


# --- CLI controlled-mode gates -------------------------------------------------


class CanonicalBridge(FakeBridge):
    """A fake bridge serving the complete canonical mock fixture state."""

    async def get_state(self):
        return cli.canonical_fixture_state().model_copy(
            update={"timestamp": datetime.now(UTC), "position": self._position}
        )


def _controlled_args(**overrides):
    argv = [
        "run",
        "--scenario",
        overrides.pop("scenario", "delayed_recall"),
        "--memory",
        "recording",
        "--runs",
        str(overrides.pop("runs", 1)),
        "--seed",
        "42",
        "--campaign-mode",
        "controlled",
    ]
    return cli._build_parser().parse_args(argv)


def test_controlled_rejects_multiple_runs(capsys) -> None:
    code = cli.main(
        [
            "run",
            "--scenario",
            "delayed_recall",
            "--campaign-mode",
            "controlled",
            "--runs",
            "3",
        ]
    )
    assert code == 2
    assert "--runs must be 1" in capsys.readouterr().err


def test_controlled_rejects_other_scenarios(capsys) -> None:
    """world_update without an explicit v2 version is legacy-by-default and
    must be rejected by the central policy BEFORE any bot contact."""

    code = cli.main(
        ["run", "--scenario", "world_update", "--campaign-mode", "controlled"]
    )
    assert code == 2
    assert "update_semantics_version" in capsys.readouterr().err


async def test_controlled_fails_closed_on_native_health(
    monkeypatch, tmp_path
) -> None:
    """A non-mock adapter in Controlled Mode is a hard error, never a run."""

    class NativeBridge(FakeBridge):
        async def health(self) -> HealthResponse:
            return HealthResponse(
                status="ok",
                mode=BotMode.MINECRAFT,
                connected=True,
                username="BenchBot",
                uptime_s=1.0,
            )

    monkeypatch.setattr(cli, "BotClient", NativeBridge)
    monkeypatch.setattr(
        cli, "create_memory_backend", lambda name, settings: RecordingBackend()
    )
    monkeypatch.setattr(cli, "OpenAICompatibleProvider", lambda settings: SmartFakeLLM())

    with pytest.raises(BotBridgeError, match="mock"):
        await cli._run_scenario_async(
            _controlled_args(), make_settings(results_dir=str(tmp_path)), {}
        )


async def test_controlled_fails_closed_on_drifted_fixture(
    monkeypatch, tmp_path
) -> None:
    """A mock adapter whose state is not the canonical fixture is rejected."""

    class DriftedBridge(CanonicalBridge):
        def __init__(self, base_url: str) -> None:
            super().__init__(base_url)
            self._position = self._position.__class__(x=5.0, y=64.0, z=-3.0)

    monkeypatch.setattr(cli, "BotClient", DriftedBridge)
    monkeypatch.setattr(
        cli, "create_memory_backend", lambda name, settings: RecordingBackend()
    )
    monkeypatch.setattr(cli, "OpenAICompatibleProvider", lambda settings: SmartFakeLLM())

    with pytest.raises(BotBridgeError, match="not canonical"):
        await cli._run_scenario_async(
            _controlled_args(), make_settings(results_dir=str(tmp_path)), {}
        )


async def test_controlled_fixture_gate_covers_inventory_and_entities(
    monkeypatch, tmp_path
) -> None:
    """The gate compares the COMPLETE normalized state: a drift that leaves
    position/time intact (here: missing inventory) is still caught."""

    class InventoryDriftBridge(CanonicalBridge):
        async def get_state(self):
            state = await super().get_state()
            return state.model_copy(update={"inventory": []})

    monkeypatch.setattr(cli, "BotClient", InventoryDriftBridge)
    monkeypatch.setattr(
        cli, "create_memory_backend", lambda name, settings: RecordingBackend()
    )
    monkeypatch.setattr(cli, "OpenAICompatibleProvider", lambda settings: SmartFakeLLM())

    with pytest.raises(BotBridgeError, match="inventory"):
        await cli._run_scenario_async(
            _controlled_args(), make_settings(results_dir=str(tmp_path)), {}
        )


async def test_controlled_run_records_mode_fixture_and_inputs(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(cli, "BotClient", CanonicalBridge)
    monkeypatch.setattr(
        cli, "create_memory_backend", lambda name, settings: RecordingBackend()
    )
    monkeypatch.setattr(cli, "OpenAICompatibleProvider", lambda settings: SmartFakeLLM())

    results = await cli._run_scenario_async(
        _controlled_args(), make_settings(results_dir=str(tmp_path / "res")), {}
    )
    assert len(results) == 1
    result = results[0]
    assert result.campaign_mode == "controlled"
    assert result.injected_events
    assert all(e.event_id.startswith("ctrl-") for e in result.injected_events)
    fairness = result.fairness
    assert fairness is not None
    assert fairness.campaign_mode == "controlled"
    assert fairness.fixture_selector == cli.CONTROLLED_FIXTURE_SELECTOR
    assert fairness.fixture_identity == cli.CONTROLLED_FIXTURE_IDENTITY
    assert fairness.valid is True
    assert fairness.source_tree_fingerprint is not None
    assert len(fairness.source_tree_fingerprint) == 64
    assert fairness.source_file_count is not None
    assert fairness.source_file_count > 0
    assert fairness.git_available is not None
    if fairness.git_available:
        assert fairness.git_commit is not None
        # The test worktree may be clean or dirty; either way it is measured.
        assert fairness.git_dirty is not None
        assert fairness.git_status_fingerprint is not None
    else:
        assert fairness.git_commit is None
        assert fairness.git_dirty is None
        assert fairness.git_status_fingerprint is None
    # The raw-stream collector is skipped in Controlled Mode.
    assert result.run_log is not None
    assert result.run_log.collected_event_count == 0


# --- campaign runner schedule and lifecycle ------------------------------------


def _cells(scenario: str = "delayed_recall"):
    if scenario == "world_update":
        cells = [
            {
                "name": "chain1",
                "params": {
                    "update_depth": 1,
                    "update_semantics_version": "temporal_chain_v2",
                },
            },
            {
                "name": "chain3",
                "params": {
                    "update_depth": 3,
                    "update_semantics_version": "temporal_chain_v2",
                },
            },
        ]
    elif scenario == "memory_noise_stress":
        cells = [
            {
                "name": "noise0",
                "params": {
                    "noise_count": 0,
                    "noise_semantics_version": "key_retention_v2",
                },
            },
            {
                "name": "noise50",
                "params": {
                    "noise_count": 50,
                    "noise_semantics_version": "key_retention_v2",
                },
            },
        ]
    else:
        cells = [
            {"name": "control", "params": {"interference_count": 10, "similar_distractor_count": 0}},
            {"name": "stress", "params": {"interference_count": 50, "similar_distractor_count": 5}},
        ]
    for cell in cells:
        validated = create_scenario(scenario)
        validated.apply_params(cell["params"])
        cell["effective_params"] = validated.params
    return cells


def _valid_result_payload(
    entry: dict, provenance: dict | None = None
) -> dict:
    """A result JSON agreeing with the pre-registered manifest entry."""

    payload = {
        "scenario": entry["scenario"],
        "seed": entry["seed"],
        "memory_backend": entry["backend"],
        "campaign_mode": "controlled",
        "params": entry["effective_params"],
        "fairness": {
            "valid": True,
            "scenario": entry["scenario"],
            "scenario_params": entry["effective_params"],
            "run_seed": entry["seed"],
            "campaign_mode": "controlled",
            "fixture_selector": entry["fixture_selector"],
            "fixture_identity": entry["fixture_identity"],
        },
    }
    if provenance is not None:
        for field in (
            "source_tree_fingerprint",
            "source_file_count",
            "git_available",
            "git_commit",
            "git_dirty",
            "git_status_fingerprint",
        ):
            payload["fairness"][field] = provenance[field]
    return payload


def test_counterbalanced_order_rotates_through_every_position() -> None:
    backends = ["none", "vector", "mem0", "letta"]
    orders = [campaign.counterbalanced_order(backends, i) for i in range(4)]
    for order in orders:
        assert sorted(order) == sorted(backends)
    for position in range(4):
        # Every backend occupies every position exactly once per rotation.
        assert {order[position] for order in orders} == set(backends)


def test_schedule_is_seed_major_counterbalanced_and_precomputed() -> None:
    schedule = campaign.build_schedule(
        cells=_cells(),
        backends=["none", "vector", "mem0", "letta"],
        seeds=[42, 43, 44],
        python="py",
        results_dir=Path("out"),
    )
    assert len(schedule) == 3 * 4 * 2
    # Seed-major: all seed-42 runs precede seed-43, etc.
    assert [entry["seed"] for entry in schedule] == [42] * 8 + [43] * 8 + [44] * 8
    # Backend order rotates per seed.
    first_seed_backends = [e["backend"] for e in schedule[:8]]
    second_seed_backends = [e["backend"] for e in schedule[8:16]]
    assert first_seed_backends[:4] != second_seed_backends[:4]
    # Cell order alternates so control does not always precede stress.
    control_first = sum(
        1
        for i in range(0, 8, 2)
        if schedule[i]["cell"] == "control" and schedule[i + 1]["cell"] == "stress"
    )
    assert 0 < control_first < 4
    # Commands are fully precomputed and carry the controlled identity.
    for entry in schedule:
        assert entry["status"] == "pending"
        assert "--campaign-mode" in entry["command"]
        assert "controlled" in entry["command"]
        assert "--runs" in entry["command"]


class _FakeProc:
    def __init__(self) -> None:
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout=None) -> int:
        return 0

    def kill(self) -> None:
        pass


def _stores(tmp_path: Path) -> dict[str, str]:
    return {
        "vector_db_path": str(tmp_path / "stores" / "memory_vector.db"),
        "mem0_qdrant_path": str(tmp_path / "stores" / "mem0_qdrant"),
    }


def _manifest(tmp_path: Path, n_seeds: int = 1) -> dict:
    cells = _cells()
    return {
        "schema_version": "controlled-campaign/v3",
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "controlled",
        "scenario": "delayed_recall",
        "semantics_version": "legacy",
        "results_dir": str(tmp_path),
        "stores": _stores(tmp_path),
        "seeds": [42, 43][:n_seeds],
        "backends": ["none", "vector"],
        "cells": cells,
        "runs": campaign.build_schedule(
            cells=cells,
            backends=["none", "vector"],
            seeds=[42, 43][:n_seeds],
            python="py",
            results_dir=tmp_path,
        ),
    }


def test_campaign_lifecycle_through_fakes(tmp_path) -> None:
    """Fresh process per run, manifest pending before the first invocation,
    every run recorded ok with its logs and result files, every process
    terminated."""

    manifest = _manifest(tmp_path)
    manifest_path = tmp_path / "campaign_manifest.json"
    spawned: list[_FakeProc] = []
    invoked: list[list[str]] = []

    def spawn_bot(entry, port):
        proc = _FakeProc()
        spawned.append(proc)
        return proc

    def invoke_run(command, *, results_dir, stdout_log, stderr_log, stores):
        invoked.append(command)
        if len(invoked) == 1:
            pending = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert all(e["status"] == "pending" for e in pending["runs"])
            # Log paths are pre-registered before any run executes.
            assert all(e["log_stdout"] for e in pending["runs"])
            assert all(e["log_stderr"] for e in pending["runs"])
        # Simulate the CLI producing a VALID, agreeing scenario JSON.
        entry = manifest["runs"][len(invoked) - 1]
        (results_dir / f"scenario_fake_{len(invoked)}.json").write_text(
            json.dumps(_valid_result_payload(entry))
        )
        return 0

    rc = campaign.run_campaign(
        manifest_path,
        manifest,
        spawn_bot=spawn_bot,
        await_health=lambda port: {"mode": "mock"},
        invoke_run=invoke_run,
    )

    assert rc == 0
    assert len(spawned) == len(manifest["runs"]) == len(invoked)
    assert all(proc.terminated for proc in spawned)
    final = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert all(e["status"] == "ok" for e in final["runs"])
    # The placeholder was substituted with the real per-run bot URL.
    assert all("BOT_URL_PLACEHOLDER" not in " ".join(c) for c in invoked)
    # Each entry links exactly the scenario JSON its own run produced.
    for i, entry in enumerate(final["runs"]):
        assert len(entry["result_files"]) == 1
        assert entry["result_files"][0].endswith(f"scenario_fake_{i + 1}.json")


def test_campaign_stops_on_failure_and_keeps_partial_state(tmp_path) -> None:
    manifest = _manifest(tmp_path)
    manifest_path = tmp_path / "campaign_manifest.json"
    spawned: list[_FakeProc] = []

    def spawn_bot(entry, port):
        proc = _FakeProc()
        spawned.append(proc)
        return proc

    def invoke_run(command, *, results_dir, stdout_log, stderr_log, stores):
        if len(spawned) == 1:
            entry = manifest["runs"][0]
            (results_dir / "scenario_fake_1.json").write_text(
                json.dumps(_valid_result_payload(entry))
            )
            return 0
        return 1  # second run fails

    rc = campaign.run_campaign(
        manifest_path,
        manifest,
        spawn_bot=spawn_bot,
        await_health=lambda port: {"mode": "mock"},
        invoke_run=invoke_run,
    )

    assert rc == 1
    assert len(spawned) == 2  # stopped immediately after the failure
    final = json.loads(manifest_path.read_text(encoding="utf-8"))
    statuses = [e["status"] for e in final["runs"]]
    assert statuses[0] == "ok"
    assert statuses[1] == "failed"
    assert all(status == "pending" for status in statuses[2:])
    assert final["runs"][1]["returncode"] == 1
    # The failed run's pre-registered log paths stay linked for audit.
    assert final["runs"][1]["log_stdout"]
    assert final["runs"][1]["log_stderr"]


def test_campaign_rejects_non_empty_output_dir_without_mutation(tmp_path) -> None:
    """An existing manifest or scenario log is rejected before ANY write."""

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    sentinel = occupied / "scenario_old.json"
    sentinel.write_text('{"old": true}', encoding="utf-8")

    rc = campaign.main(
        [
            "--results-dir",
            str(occupied),
            "--cell",
            '{"name":"control","params":{"interference_count":10,"similar_distractor_count":0}}',
        ]
    )
    assert rc == 2
    assert sentinel.read_text(encoding="utf-8") == '{"old": true}'
    assert not (occupied / "campaign_manifest.json").exists()

    # A path that exists as a FILE is rejected the same way.
    file_path = tmp_path / "afile"
    file_path.write_text("x", encoding="utf-8")
    rc = campaign.main(
        [
            "--results-dir",
            str(file_path),
            "--cell",
            '{"name":"control","params":{}}',
        ]
    )
    assert rc == 2
    assert file_path.read_text(encoding="utf-8") == "x"


def test_campaign_env_pins_campaign_local_stores(tmp_path) -> None:
    stores = _stores(tmp_path)
    env = campaign._campaign_env(tmp_path, stores)
    assert env["RESULTS_DIR"] == str(tmp_path)
    assert env["VECTOR_DB_PATH"] == stores["vector_db_path"]
    assert env["MEM0_QDRANT_PATH"] == stores["mem0_qdrant_path"]
    # Campaign-local: inside the campaign dir, never the historical stores.
    assert str(tmp_path) in env["VECTOR_DB_PATH"]
    assert str(tmp_path) in env["MEM0_QDRANT_PATH"]


def test_invoke_run_retains_stdout_and_stderr(tmp_path) -> None:
    """The real _invoke_run redirects both streams to the registered logs."""

    stores = _stores(tmp_path)
    stdout_log = tmp_path / "logs" / "run.stdout.log"
    stderr_log = tmp_path / "logs" / "run.stderr.log"
    rc = campaign._invoke_run(
        [
            sys.executable,
            "-c",
            "import os, sys; print('out-' + os.environ['RESULTS_DIR']); "
            "print('err-' + os.environ['VECTOR_DB_PATH'], file=sys.stderr)",
        ],
        results_dir=tmp_path,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
        stores=stores,
    )
    assert rc == 0
    assert f"out-{tmp_path}" in stdout_log.read_text(encoding="utf-8")
    assert stores["vector_db_path"] in stderr_log.read_text(encoding="utf-8")


# --- TASK-007: neutral Controlled distractors, full raw snapshots --------------


async def test_controlled_target_candidates_are_structurally_identical(tmp_path) -> None:
    """Competing target-location facts share the learned fact's actor, event
    type, and context key set; no correctness/staleness labels; distinct
    coordinates; stable ctrl- ids and logical timestamps in raw evidence."""

    params = {"interference_count": 10, "similar_distractor_count": 8}
    result = await _run_controlled(
        VectorMemoryBackend(str(tmp_path / "mem.db")),
        episode_id="ep-neutral",
        params=params,
    )

    target_facts = [
        event
        for event in result.injected_events
        if event.context.get("subject") == "target_chest"
    ]
    # 1 learned fact + kinds 2/3 twice per 4-cycle at count 8 = 4 candidates.
    assert len(target_facts) == 5
    for event in target_facts:
        assert event.actor == "scenario-instructor"
        assert event.event_type is EventType.LOCATION_DISCOVERED
        assert set(event.context) == {"subject", "x", "y", "z"}
        assert event.event_id.startswith("ctrl-")
    # Distinct deterministic coordinates; order is the only cue.
    coords = {
        (event.context["x"], event.context["y"], event.context["z"])
        for event in target_facts
    }
    assert len(coords) == len(target_facts)
    # No semantic answer labels anywhere in the candidate content.
    banned = ("wrong", "used to be", "stale", "old", "former", "decoy", "correct")
    for event in target_facts:
        rendered = json.dumps(event.context).lower() + event.actor.lower()
        assert not any(label in rendered for label in banned)


async def test_controlled_distractor_labels_survive_in_native_mode(tmp_path) -> None:
    """Native mode is unchanged: distractors keep their notes and the
    environment actor (the neutralization is Controlled-only)."""

    scenario = DelayedRecallScenario()
    scenario.apply_params({"similar_distractor_count": 4})
    llm = SmartFakeLLM()
    bot = FakeBotClient()
    memory = VectorMemoryBackend(str(tmp_path / "mem.db"))
    ctx = ScenarioContext(
        bot=bot,
        memory=memory,
        runner=AgentRunner(bot, memory, llm),
        llm=llm,
        settings=make_settings(),
        seed=42,
        episode_id="ep-native-labels",
    )
    await scenario.run(ctx)
    items = await memory.retrieve(
        MemoryQuery(query_text="target chest", episode_id="ep-native-labels", limit=50)
    )
    target_distractors = [
        item
        for item in items
        if item.event.context.get("subject") == "target_chest"
        and item.event.actor == "environment"
    ]
    assert target_distractors  # native distractors keep the environment actor
    notes = [str(item.event.context.get("note", "")) for item in target_distractors]
    assert any("wrong location" in note or "used to be" in note for note in notes)


async def test_run_step_retrieved_items_keep_full_snapshot(tmp_path) -> None:
    """The neutral prompt view never reaches the audit trail: RunStep keeps
    the complete raw snapshot (ids, episode, timestamps, score, metadata)."""

    result = await _run_controlled(
        VectorMemoryBackend(str(tmp_path / "mem.db")), episode_id="ep-snap"
    )
    assert result.run_log is not None
    step0_items = result.run_log.steps[0].retrieved_items
    assert step0_items
    item = step0_items[0]
    assert item.item_id
    assert item.event.event_id
    assert item.event.episode_id == "ep-snap"
    assert item.event.timestamp is not None
    assert item.created_at is not None
    assert hasattr(item, "score")
    assert hasattr(item, "metadata")
    # And the full snapshot still re-derives the headline metrics.
    assert result.metrics["recall_accuracy"] == 1


# --- TASK-014 Q1: central Controlled policy ------------------------------------


def test_q1_policy_approves_the_four_combinations() -> None:
    legacy = create_scenario("delayed_recall")
    legacy.apply_params({})
    assert cli.validate_controlled_policy("delayed_recall", legacy.params) is None

    v2 = create_scenario("delayed_recall")
    v2.apply_params({"recall_semantics_version": "entity_key_v2"})
    assert cli.validate_controlled_policy("delayed_recall", v2.params) is None

    wu = create_scenario("world_update")
    wu.apply_params({"update_semantics_version": "temporal_chain_v2"})
    assert cli.validate_controlled_policy("world_update", wu.params) is None

    noise = create_scenario("memory_noise_stress")
    noise.apply_params({"noise_semantics_version": "key_retention_v2"})
    assert cli.validate_controlled_policy("memory_noise_stress", noise.params) is None


def test_q1_policy_rejects_unapproved_combinations() -> None:
    wu_legacy = create_scenario("world_update")  # missing version => legacy
    reason = cli.validate_controlled_policy("world_update", wu_legacy.params)
    assert reason is not None and "update_semantics_version" in reason

    noise = create_scenario("memory_noise_stress")  # missing version => legacy
    reason = cli.validate_controlled_policy("memory_noise_stress", noise.params)
    assert reason is not None and "noise_semantics_version" in reason

    noise_bogus = create_scenario("memory_noise_stress")
    reason = cli.validate_controlled_policy(
        "memory_noise_stress", {**noise_bogus.params, "noise_semantics_version": "v3"}
    )
    assert reason is not None and "noise_semantics_version" in reason

    fl = create_scenario("failure_learning")
    assert cli.validate_controlled_policy("failure_learning", fl.params) is not None


def test_q1_cli_gate_fails_before_any_bot_or_backend(monkeypatch) -> None:
    """Policy rejection happens before BotClient/LLM/backend construction."""

    constructed = []
    monkeypatch.setattr(
        cli, "create_memory_backend", lambda name, settings: constructed.append(name)
    )

    code = cli.main(
        ["run", "--scenario", "memory_noise_stress", "--campaign-mode", "controlled"]
    )
    assert code == 2
    code = cli.main(
        ["run", "--scenario", "world_update", "--campaign-mode", "controlled"]
    )
    assert code == 2
    code = cli.main(
        [
            "run",
            "--scenario",
            "delayed_recall",
            "--campaign-mode",
            "controlled",
            "--runs",
            "2",
        ]
    )
    assert code == 2
    assert constructed == []  # nothing was ever built


# --- TASK-014 Q2: normalization / preflight -------------------------------------


def _campaign_args(tmp_path: Path, cells: list[str], **overrides):
    argv = ["--results-dir", str(tmp_path / "out")]
    for raw in cells:
        argv += ["--cell", raw]
    for key, value in overrides.items():
        argv += [f"--{key.replace('_', '-')}", str(value)]
    return campaign._build_parser().parse_args(argv)


def test_q2_legacy_cell_requested_vs_effective_params(tmp_path) -> None:
    """An old delayed cell (no version) keeps requested params byte-for-byte;
    effective params gain defaults + legacy; the command carries only the
    requested overrides."""

    requested = {"interference_count": 50, "similar_distractor_count": 5}
    args = _campaign_args(tmp_path, [json.dumps({"name": "stress", "params": requested})])
    plan, error = campaign.prepare_campaign(args)
    assert error is None
    cell = plan["cells"][0]
    assert cell["params"] == requested  # untouched
    assert cell["effective_params"] == {
        "interference_count": 50,
        "similar_distractor_count": 5,
        "recall_semantics_version": "legacy",
    }
    assert plan["semantics_version"] == "legacy"

    schedule = campaign.build_schedule(
        cells=plan["cells"],
        backends=["none"],
        seeds=[42],
        python="py",
        results_dir=tmp_path / "out",
    )
    command = schedule[0]["command"]
    overrides = [
        command[i + 1]
        for i, part in enumerate(command)
        if part == "--scenario-param"
    ]
    assert sorted(overrides) == [
        "interference_count=50",
        "similar_distractor_count=5",
    ]
    assert "recall_semantics_version" not in " ".join(command)


def test_q2_world_v2_cell_records_requested_and_effective(tmp_path) -> None:
    requested = {"update_semantics_version": "temporal_chain_v2"}
    args = _campaign_args(
        tmp_path,
        [json.dumps({"name": "chain1", "params": requested})],
        scenario="world_update",
    )
    plan, error = campaign.prepare_campaign(args)
    assert error is None
    cell = plan["cells"][0]
    assert cell["params"] == requested
    assert cell["effective_params"] == {
        "update_depth": 1,
        "update_semantics_version": "temporal_chain_v2",
    }
    assert plan["scenario"] == "world_update"
    assert plan["semantics_version"] == "temporal_chain_v2"


def _assert_preflight_rejects(tmp_path: Path, cells: list[str], **overrides) -> None:
    args = _campaign_args(tmp_path, cells, **overrides)
    plan, error = campaign.prepare_campaign(args)
    assert plan is None
    assert error  # clean message, no traceback
    # And through main(): exit 2, output path never created.
    argv = ["--results-dir", str(tmp_path / "out")]
    for raw in cells:
        argv += ["--cell", raw]
    for key, value in overrides.items():
        argv += [f"--{key.replace('_', '-')}", str(value)]
    assert campaign.main(argv) == 2
    assert not (tmp_path / "out").exists()


def test_q2_preflight_rejects_bad_cells_and_inputs(tmp_path) -> None:
    good = json.dumps({"name": "ok", "params": {}})
    _assert_preflight_rejects(tmp_path / "a", ["not-json"])
    _assert_preflight_rejects(tmp_path / "b", [json.dumps({"name": "x"})])
    _assert_preflight_rejects(
        tmp_path / "c", [json.dumps({"name": "x", "params": {}, "extra": 1})]
    )
    for bad_name in ("a/b", "..", "a b", "", "x" * 65):
        _assert_preflight_rejects(
            tmp_path / f"n{len(bad_name)}{abs(hash(bad_name)) % 997}",
            [json.dumps({"name": bad_name, "params": {}})],
        )
    _assert_preflight_rejects(  # duplicate cell names
        tmp_path / "d", [good, good]
    )
    _assert_preflight_rejects(  # invalid params (scenario validation)
        tmp_path / "e",
        [json.dumps({"name": "ok", "params": {"interference_count": -1}})],
    )
    _assert_preflight_rejects(  # mixed delayed semantics in one campaign
        tmp_path / "f",
        [
            json.dumps({"name": "a", "params": {}}),
            json.dumps(
                {"name": "b", "params": {"recall_semantics_version": "entity_key_v2"}}
            ),
        ],
    )
    world = {"update_depth": 3}
    _assert_preflight_rejects(  # world cell missing the explicit v2 version
        tmp_path / "g",
        [json.dumps({"name": "w", "params": world})],
        scenario="world_update",
    )
    _assert_preflight_rejects(  # world cell explicitly legacy
        tmp_path / "h",
        [
            json.dumps(
                {"name": "w", "params": {"update_semantics_version": "legacy"}}
            )
        ],
        scenario="world_update",
    )
    _assert_preflight_rejects(tmp_path / "i", [good], seeds="42,42")  # dup seeds
    _assert_preflight_rejects(tmp_path / "j", [good], seeds="x,y")  # non-int
    _assert_preflight_rejects(tmp_path / "k", [good], backends="")  # empty
    _assert_preflight_rejects(tmp_path / "l", [good], backends="none,none")  # dup
    _assert_preflight_rejects(tmp_path / "m", [good], backends="none,graphiti")




# --- TASK-014 Q3: scheduling -----------------------------------------------------


def test_q3_world_update_schedule_preserves_invariants(tmp_path) -> None:
    cells = _cells("world_update")
    schedule = campaign.build_schedule(
        cells=cells,
        backends=["none", "vector", "mem0", "letta"],
        seeds=[42, 43, 44],
        python="py",
        results_dir=tmp_path,
        scenario="world_update",
    )
    assert len(schedule) == 3 * 4 * 2
    assert [entry["seed"] for entry in schedule] == [42] * 8 + [43] * 8 + [44] * 8
    first_seed_backends = [e["backend"] for e in schedule[:8]]
    second_seed_backends = [e["backend"] for e in schedule[8:16]]
    assert first_seed_backends[:4] != second_seed_backends[:4]
    chain1_first = sum(
        1
        for i in range(0, 8, 2)
        if schedule[i]["cell"] == "chain1" and schedule[i + 1]["cell"] == "chain3"
    )
    assert 0 < chain1_first < 4
    for entry in schedule:
        assert entry["scenario"] == "world_update"
        assert entry["requested_params"]["update_semantics_version"] == (
            "temporal_chain_v2"
        )
        assert entry["effective_params"]["update_depth"] in (1, 3)
        assert entry["fixture_identity"] == cli.CONTROLLED_FIXTURE_IDENTITY
        command = entry["command"]
        assert command[command.index("--scenario") + 1] == "world_update"
        assert command[command.index("--runs") + 1] == "1"


def test_q3_default_delayed_schedule_names_delayed_recall(tmp_path) -> None:
    """Backward compatibility: no scenario argument => delayed_recall."""

    schedule = campaign.build_schedule(
        cells=_cells(),
        backends=["none"],
        seeds=[42],
        python="py",
        results_dir=tmp_path,
    )
    assert schedule[0]["scenario"] == "delayed_recall"
    command = schedule[0]["command"]
    assert command[command.index("--scenario") + 1] == "delayed_recall"


# --- TASK-014 Q4: per-run result validation ---------------------------------------


def _run_once(tmp_path: Path, invoke_run) -> dict:
    manifest = _manifest(tmp_path)
    manifest["runs"] = manifest["runs"][:1]
    manifest_path = tmp_path / "campaign_manifest.json"
    rc = campaign.run_campaign(
        manifest_path,
        manifest,
        spawn_bot=lambda entry, port: _FakeProc(),
        await_health=lambda port: {"mode": "mock"},
        invoke_run=invoke_run,
    )
    return {
        "rc": rc,
        "entry": json.loads(manifest_path.read_text(encoding="utf-8"))["runs"][0],
    }


def test_q4_zero_or_two_result_files_fail_closed(tmp_path) -> None:
    def zero(command, *, results_dir, stdout_log, stderr_log, stores):
        return 0  # rc 0 but NO result file

    outcome = _run_once(tmp_path / "zero", zero)
    assert outcome["rc"] == 1
    assert outcome["entry"]["status"] == "failed"
    assert "exactly 1" in outcome["entry"]["error"]

    def two(command, *, results_dir, stdout_log, stderr_log, stores):
        manifest_now = json.loads(
            (tmp_path / "two" / "campaign_manifest.json").read_text(encoding="utf-8")
        )
        payload = _valid_result_payload(manifest_now["runs"][0])
        (results_dir / "scenario_a.json").write_text(json.dumps(payload))
        (results_dir / "scenario_b.json").write_text(json.dumps(payload))
        return 0

    outcome = _run_once(tmp_path / "two", two)
    assert outcome["rc"] == 1
    assert outcome["entry"]["status"] == "failed"
    assert "exactly 1" in outcome["entry"]["error"]
    # Both files are still linked as evidence.
    assert len(outcome["entry"]["result_files"]) == 2


def test_q4_invalid_json_fails_closed(tmp_path) -> None:
    def bad_json(command, *, results_dir, stdout_log, stderr_log, stores):
        (results_dir / "scenario_broken.json").write_text("{not json")
        return 0

    outcome = _run_once(tmp_path, bad_json)
    assert outcome["rc"] == 1
    assert outcome["entry"]["status"] == "failed"
    assert "not valid JSON" in outcome["entry"]["error"]
    assert outcome["entry"]["result_files"]


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda p: p.update(scenario="world_update"), "scenario mismatch"),
        (lambda p: p.update(seed=999), "seed mismatch"),
        (lambda p: p.update(memory_backend="vector"), "memory_backend mismatch"),
        (lambda p: p.update(campaign_mode="native"), "campaign_mode mismatch"),
        (lambda p: p.update(params={}), "params mismatch"),
        (lambda p: p.pop("fairness"), "no fairness record"),
        (
            lambda p: p["fairness"].update(valid=False, invalid_reason="leak"),
            "fairness invalid",
        ),
        (lambda p: p["fairness"].update(run_seed=999), "run_seed mismatch"),
        (
            lambda p: p["fairness"].update(fixture_identity="bogus"),
            "fixture_identity mismatch",
        ),
        (lambda p: p["fairness"].update(scenario_params={}), "scenario_params mismatch"),
        (
            lambda p: p["fairness"].update(scenario="world_update"),
            "fairness scenario mismatch",
        ),
        (
            lambda p: p["fairness"].update(campaign_mode="native"),
            "fairness campaign_mode mismatch",
        ),
    ],
)
def test_q4_result_mismatches_fail_closed(tmp_path, mutate, expected) -> None:
    def invoke(command, *, results_dir, stdout_log, stderr_log, stores):
        manifest_now = json.loads(
            (tmp_path / "campaign_manifest.json").read_text(encoding="utf-8")
        )
        payload = _valid_result_payload(manifest_now["runs"][0])
        mutate(payload)
        (results_dir / "scenario_fake.json").write_text(json.dumps(payload))
        return 0

    outcome = _run_once(tmp_path, invoke)
    assert outcome["rc"] == 1
    assert outcome["entry"]["status"] == "failed"
    assert expected in outcome["entry"]["error"]


# --- TASK-014 Q5: hermetic CLI world-update integration ----------------------------


async def test_q5_controlled_world_update_v2_cli_path(monkeypatch, tmp_path) -> None:
    from minemembench.scenarios.base import TemporalChainGroundTruth

    monkeypatch.setattr(cli, "BotClient", CanonicalBridge)
    monkeypatch.setattr(
        cli, "create_memory_backend", lambda name, settings: RecordingBackend()
    )
    monkeypatch.setattr(cli, "OpenAICompatibleProvider", lambda settings: SmartFakeLLM())

    args = cli._build_parser().parse_args(
        [
            "run",
            "--scenario",
            "world_update",
            "--memory",
            "recording",
            "--runs",
            "1",
            "--seed",
            "42",
            "--campaign-mode",
            "controlled",
            "--scenario-param",
            "update_depth=3",
            "--scenario-param",
            "update_semantics_version=temporal_chain_v2",
        ]
    )
    results = await cli._run_scenario_async(
        args,
        make_settings(results_dir=str(tmp_path / "res")),
        {"update_depth": 3, "update_semantics_version": "temporal_chain_v2"},
    )
    assert len(results) == 1
    result = results[0]
    assert result.scenario == "world_update"
    assert result.campaign_mode == "controlled"
    assert result.params == {
        "update_depth": 3,
        "update_semantics_version": "temporal_chain_v2",
    }
    fairness = result.fairness
    assert fairness is not None
    assert fairness.valid is True
    assert fairness.campaign_mode == "controlled"
    assert fairness.run_seed == 42
    assert fairness.fixture_selector == cli.CONTROLLED_FIXTURE_SELECTOR
    assert fairness.fixture_identity == cli.CONTROLLED_FIXTURE_IDENTITY
    assert fairness.scenario_params == result.params

    assert result.injected_events
    assert all(e.event_id.startswith("ctrl-") for e in result.injected_events)
    ground_truth = result.evaluation_ground_truth
    assert isinstance(ground_truth, TemporalChainGroundTruth)
    assert len(ground_truth.stale_event_ids) == 3
    assert ground_truth.current_event_id
    assert (
        result.metrics["retrieval_evidence_source"]
        == "run_log.steps[0].retrieved_items"
    )


# --- TASK-020 failure-learning fixture/campaign integration ------------------


def _failure_campaign_args(tmp_path: Path, params: dict) -> object:
    return campaign._build_parser().parse_args(
        [
            "--results-dir",
            str(tmp_path),
            "--scenario",
            "failure_learning",
            "--seeds",
            "42,43,44",
            "--backends",
            "none,vector,mem0,letta",
            "--cell",
            json.dumps({"name": "failure-v2", "params": params}),
        ]
    )


def _failure_result_payload(
    entry: dict,
    *,
    event_error: str = "gold_nugget must be equipped",
    source_error: str = "gold_nugget must be equipped",
) -> dict:
    payload = _valid_result_payload(entry)
    payload["injected_events"] = [
        {
            "event_id": "ctrl-failure",
            "episode_id": f"ep-{entry['backend']}",
            "timestamp": "2026-01-01T00:00:00Z",
            "actor": "agent",
            "target": "zombie",
            "event_type": "task_failed",
            "location": {"x": 3, "y": 64, "z": 4},
            "context": {
                "task_family": "warded_hostile",
                "entity": "zombie",
                "action": "attack_entity",
                "status": "failed",
                "error": event_error,
                "equipped_before": None,
            },
            "outcome": "failed",
            "raw_events": [],
        }
    ]
    payload["observed_action_results"] = [
        {
            "action_id": f"volatile-{entry['backend']}",
            "action": "attack_entity",
            "status": "failed",
            "started_at": "2026-08-08T12:00:00Z",
            "finished_at": "2026-08-08T12:00:00Z",
            "result": None,
            "error": source_error,
            "state_after": {
                "timestamp": "2026-08-08T12:00:00Z",
                "equipped": {"hand": None},
                "nearby_entities": [
                    {"id": 1001, "name": "zombie"},
                    {"id": 1002, "name": "skeleton"},
                ],
            },
        }
    ]
    return payload


def test_q20_failure_campaign_requires_explicit_v2_before_outputs(tmp_path) -> None:
    plan, error = campaign.prepare_campaign(
        _failure_campaign_args(tmp_path, {"interference_count": 0})
    )
    assert plan is None
    assert error is not None
    assert "explicitly request" in error
    assert "failure_semantics_version=observed_precondition_v2" in error
    assert list(tmp_path.iterdir()) == []


def test_q20_failure_schedule_selects_and_records_warded_fixture(tmp_path) -> None:
    requested = {
        "failure_semantics_version": "observed_precondition_v2",
        "interference_count": 0,
    }
    plan, error = campaign.prepare_campaign(
        _failure_campaign_args(tmp_path, requested)
    )
    assert error is None
    assert plan is not None
    schedule = campaign.build_schedule(
        cells=plan["cells"],
        backends=plan["backends"],
        seeds=plan["seeds"],
        python="py",
        results_dir=tmp_path,
        scenario=plan["scenario"],
    )
    assert len(schedule) == 12
    assert {entry["fixture_selector"] for entry in schedule} == {
        cli.CONTROLLED_WARDED_FIXTURE_SELECTOR
    }
    assert {entry["fixture_identity"] for entry in schedule} == {
        cli.CONTROLLED_WARDED_FIXTURE_IDENTITY
    }
    assert all(
        "failure_semantics_version=observed_precondition_v2" in entry["command"]
        for entry in schedule
    )


def test_q20_failure_campaign_threads_fixture_and_validates_fairness(tmp_path) -> None:
    requested = {
        "failure_semantics_version": "observed_precondition_v2",
        "interference_count": 0,
    }
    scenario = create_scenario("failure_learning")
    scenario.apply_params(requested)
    cells = [
        {
            "name": "failure-v2",
            "params": requested,
            "effective_params": scenario.params,
        }
    ]
    schedule = campaign.build_schedule(
        cells=cells,
        backends=["none"],
        seeds=[42],
        python="py",
        results_dir=tmp_path,
        scenario="failure_learning",
    )
    manifest = {
        "schema_version": "controlled-campaign/v3",
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "controlled",
        "scenario": "failure_learning",
        "semantics_version": "observed_precondition_v2",
        "results_dir": str(tmp_path),
        "stores": _stores(tmp_path),
        "seeds": [42],
        "backends": ["none"],
        "cells": cells,
        "fixtures": [[
            cli.CONTROLLED_WARDED_FIXTURE_SELECTOR,
            cli.CONTROLLED_WARDED_FIXTURE_IDENTITY,
        ]],
        "runs": schedule,
    }
    spawned: list[tuple[Path, int, str]] = []

    def spawn_bot(entry: Path, port: int, fixture_selector: str):
        spawned.append((entry, port, fixture_selector))
        return _FakeProc()

    def valid(command, *, results_dir, stdout_log, stderr_log, stores):
        entry = manifest["runs"][0]
        (results_dir / "scenario_fake.json").write_text(
            json.dumps(_failure_result_payload(entry)), encoding="utf-8"
        )
        return 0

    manifest_path = tmp_path / "campaign_manifest.json"
    rc = campaign.run_campaign(
        manifest_path,
        manifest,
        spawn_bot=spawn_bot,
        await_health=lambda port: {"mode": "mock"},
        invoke_run=valid,
    )
    assert rc == 0
    assert spawned[0][2] == cli.CONTROLLED_WARDED_FIXTURE_SELECTOR
    recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert recorded["runs"][0]["status"] == "ok"
    assert recorded["runs"][0]["fixture_selector"] == (
        cli.CONTROLLED_WARDED_FIXTURE_SELECTOR
    )

    # The same result fails closed when fairness claims a different selector.
    bad_dir = tmp_path / "bad"
    bad_schedule = campaign.build_schedule(
        cells=cells,
        backends=["none"],
        seeds=[42],
        python="py",
        results_dir=bad_dir,
        scenario="failure_learning",
    )
    bad_manifest = {
        **manifest,
        "results_dir": str(bad_dir),
        "stores": _stores(bad_dir),
        "runs": bad_schedule,
    }

    def invalid(command, *, results_dir, stdout_log, stderr_log, stores):
        payload = _failure_result_payload(bad_manifest["runs"][0])
        payload["fairness"]["fixture_selector"] = "canonical"
        (results_dir / "scenario_fake.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        return 0

    bad_path = bad_dir / "campaign_manifest.json"
    rc = campaign.run_campaign(
        bad_path,
        bad_manifest,
        spawn_bot=spawn_bot,
        await_health=lambda port: {"mode": "mock"},
        invoke_run=invalid,
    )
    assert rc == 1
    failed = json.loads(bad_path.read_text(encoding="utf-8"))["runs"][0]
    assert "fixture_selector mismatch" in failed["error"]


@pytest.mark.parametrize(
    "second_payload,expected",
    [
        ({"event_error": "different event error"}, "event stream differs"),
        ({"source_error": "different source error"}, "ActionResult evidence differs"),
    ],
)
def test_q20_campaign_cross_backend_evidence_fails_closed(
    tmp_path, second_payload: dict, expected: str
) -> None:
    requested = {
        "failure_semantics_version": "observed_precondition_v2",
        "interference_count": 0,
    }
    scenario = create_scenario("failure_learning")
    scenario.apply_params(requested)
    cells = [
        {
            "name": "failure-v2",
            "params": requested,
            "effective_params": scenario.params,
        }
    ]
    schedule = campaign.build_schedule(
        cells=cells,
        backends=["none", "vector"],
        seeds=[42],
        python="py",
        results_dir=tmp_path,
        scenario="failure_learning",
    )
    manifest = {
        "schema_version": "controlled-campaign/v3",
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "controlled",
        "scenario": "failure_learning",
        "semantics_version": "observed_precondition_v2",
        "results_dir": str(tmp_path),
        "stores": _stores(tmp_path),
        "seeds": [42],
        "backends": ["none", "vector"],
        "cells": cells,
        "runs": schedule,
    }
    invoked = 0

    def invoke(command, *, results_dir, stdout_log, stderr_log, stores):
        nonlocal invoked
        entry = manifest["runs"][invoked]
        overrides = second_payload if invoked == 1 else {}
        payload = _failure_result_payload(entry, **overrides)
        (results_dir / f"scenario_fake_{invoked}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        invoked += 1
        return 0

    rc = campaign.run_campaign(
        tmp_path / "campaign_manifest.json",
        manifest,
        spawn_bot=lambda entry, port, fixture: _FakeProc(),
        await_health=lambda port: {"mode": "mock"},
        invoke_run=invoke,
    )
    assert rc == 1
    assert invoked == 2
    assert expected in manifest["runs"][1]["error"]


# --- A-REVIEW-014 repairs --------------------------------------------------------


def test_q2_preflight_rejects_semantically_duplicate_cells(tmp_path) -> None:
    """Same raw params under two names = one treatment; reject, naming both."""

    args = _campaign_args(
        tmp_path,
        [
            json.dumps({"name": "alpha", "params": {"interference_count": 50}}),
            json.dumps({"name": "beta", "params": {"interference_count": 50}}),
        ],
    )
    plan, error = campaign.prepare_campaign(args)
    assert plan is None
    assert "alpha" in error and "beta" in error
    assert "duplicate" in error


def test_q2_preflight_rejects_omitted_vs_explicit_default_duplicate(tmp_path) -> None:
    """Omitted-vs-explicit-default equivalence: identical effective params."""

    args = _campaign_args(
        tmp_path,
        [
            json.dumps({"name": "alpha", "params": {}}),
            json.dumps(
                {
                    "name": "beta",
                    "params": {
                        "interference_count": 10,
                        "similar_distractor_count": 0,
                        "recall_semantics_version": "legacy",
                    },
                }
            ),
        ],
    )
    plan, error = campaign.prepare_campaign(args)
    assert plan is None
    assert "alpha" in error and "beta" in error


def test_q2_distinct_effective_cells_are_accepted(tmp_path) -> None:
    args = _campaign_args(
        tmp_path,
        [
            json.dumps({"name": "control", "params": {"interference_count": 10}}),
            json.dumps({"name": "stress", "params": {"interference_count": 50}}),
        ],
    )
    plan, error = campaign.prepare_campaign(args)
    assert error is None
    assert [cell["name"] for cell in plan["cells"]] == ["control", "stress"]


def test_q4_schedule_run_identities_are_unique(tmp_path) -> None:
    """Accepted schedules contain one run per distinct
    (scenario, canonical effective params, seed, backend) tuple."""

    for scenario in ("delayed_recall", "world_update", "memory_noise_stress"):
        schedule = campaign.build_schedule(
            cells=_cells(scenario),
            backends=["none", "vector", "mem0", "letta"],
            seeds=[42, 43, 44],
            python="py",
            results_dir=tmp_path,
            scenario=scenario,
        )
        identities = set()
        for entry in schedule:
            signature = json.dumps(
                {
                    "scenario": entry["scenario"],
                    "effective_params": entry["effective_params"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            identity = (signature, entry["seed"], entry["backend"])
            assert identity not in identities
            identities.add(identity)
        assert len(identities) == len(schedule)


def test_q4_main_with_module_level_monkeypatch_runs_only_fakes(
    tmp_path, monkeypatch
) -> None:
    """Late binding: monkeypatching the module helpers BEFORE a normal
    `campaign.main` call is effective — no real process/network executes."""

    spawned: list[_FakeProc] = []
    invoked: list[list[str]] = []

    def fake_spawn(entry, port):
        proc = _FakeProc()
        spawned.append(proc)
        return proc

    def fake_health(port):
        return {"mode": "mock"}

    def fake_invoke(command, *, results_dir, stdout_log, stderr_log, stores):
        invoked.append(command)
        manifest_now = json.loads(
            (results_dir / "campaign_manifest.json").read_text(encoding="utf-8")
        )
        payload = _valid_result_payload(
            manifest_now["runs"][len(invoked) - 1],
            manifest_now["provenance"],
        )
        (results_dir / f"scenario_fake_{len(invoked)}.json").write_text(
            json.dumps(payload)
        )
        return 0

    monkeypatch.setattr(campaign, "_spawn_bot", fake_spawn)
    monkeypatch.setattr(campaign, "_await_mock_health", fake_health)
    monkeypatch.setattr(campaign, "_invoke_run", fake_invoke)

    results_dir = tmp_path / "camp"
    rc = campaign.main(
        [
            "--results-dir",
            str(results_dir),
            "--seeds",
            "42",
            "--backends",
            "none",
            "--cell",
            json.dumps(
                {"name": "control", "params": {"interference_count": 10}}
            ),
        ]
    )

    assert rc == 0
    assert len(spawned) == 1 and len(invoked) == 1
    assert spawned[0].terminated
    final = json.loads(
        (results_dir / "campaign_manifest.json").read_text(encoding="utf-8")
    )
    assert final["runs"][0]["status"] == "ok"
    assert final["runs"][0]["health_mode"] == "mock"
    assert final["runs"][0]["result_files"]
    assert final["schema_version"] == "controlled-campaign/v4"
    assert final["provenance"]["source_tree_fingerprint"]
    assert final["provenance"]["source_file_count"] > 0


def test_q24_result_provenance_mismatch_fails_closed(tmp_path) -> None:
    entry = campaign.build_schedule(
        cells=_cells()[:1],
        backends=["none"],
        seeds=[42],
        python="py",
        results_dir=tmp_path,
    )[0]
    provenance = {
        "source_tree_fingerprint": "a" * 64,
        "source_file_count": 3,
        "git_available": True,
        "git_commit": "b" * 40,
        "git_dirty": False,
        "git_status_fingerprint": "c" * 64,
    }
    path = tmp_path / "scenario_fake.json"
    payload = _valid_result_payload(entry, provenance)
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert (
        campaign._validate_run_result(
            entry, [path], expected_provenance=provenance
        )
        is None
    )
    payload["fairness"]["source_tree_fingerprint"] = "d" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    reason = campaign._validate_run_result(
        entry, [path], expected_provenance=provenance
    )
    assert reason is not None and "provenance mismatch" in reason


@pytest.mark.parametrize(
    ("git_available", "git_dirty"),
    [(True, True), (False, None)],
)
def test_q24_require_clean_source_fails_before_output(
    tmp_path, monkeypatch, git_available, git_dirty
) -> None:
    from minemembench.core.provenance import SourceFileDigest, SourceProvenance

    dirty = SourceProvenance(
        source_tree_fingerprint="a" * 64,
        source_file_count=1,
        source_files=(SourceFileDigest(path="source.py", size=1, sha256="d" * 64),),
        git_available=git_available,
        git_commit="b" * 40 if git_available else None,
        git_dirty=git_dirty,
        git_status_fingerprint="c" * 64 if git_available else None,
    )
    monkeypatch.setattr(campaign, "capture_source_provenance", lambda root: dirty)
    results_dir = tmp_path / "must-not-exist"
    rc = campaign.main(
        [
            "--results-dir",
            str(results_dir),
            "--seeds",
            "42",
            "--backends",
            "none",
            "--cell",
            json.dumps(
                {"name": "control", "params": {"interference_count": 10}}
            ),
            "--require-clean-source",
        ]
    )
    assert rc == 2
    assert not results_dir.exists()


def test_q24_campaign_stops_on_result_provenance_mismatch(tmp_path) -> None:
    manifest = _manifest(tmp_path)
    manifest["schema_version"] = campaign.MANIFEST_SCHEMA_VERSION
    provenance = {
        "schema_version": "minemembench-source/v1",
        "digest_algorithm": "sha256",
        "source_tree_fingerprint": "a" * 64,
        "source_file_count": 1,
        "source_files": [
            {"path": "source.py", "size": 1, "sha256": "d" * 64}
        ],
        "git_available": True,
        "git_commit": "b" * 40,
        "git_dirty": False,
        "git_status_fingerprint": "c" * 64,
    }
    manifest["provenance"] = provenance
    manifest_path = tmp_path / "campaign_manifest.json"

    def invoke(command, *, results_dir, stdout_log, stderr_log, stores):
        payload = _valid_result_payload(manifest["runs"][0], provenance)
        payload["fairness"]["source_tree_fingerprint"] = "e" * 64
        (results_dir / "scenario_fake.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        return 0

    rc = campaign.run_campaign(
        manifest_path,
        manifest,
        spawn_bot=lambda entry, port: _FakeProc(),
        await_health=lambda port: {"mode": "mock"},
        invoke_run=invoke,
    )
    final = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert rc == 1
    assert final["runs"][0]["status"] == "failed"
    assert "provenance mismatch" in final["runs"][0]["error"]


def test_q24_v4_manifest_without_provenance_fails_before_write(tmp_path) -> None:
    manifest = _manifest(tmp_path)
    manifest["schema_version"] = campaign.MANIFEST_SCHEMA_VERSION
    manifest_path = tmp_path / "campaign_manifest.json"

    rc = campaign.run_campaign(manifest_path, manifest)

    assert rc == 2
    assert not manifest_path.exists()


# --- TASK-016: memory-noise v2 campaign eligibility ------------------------------


def test_q16_preflight_accepts_memory_noise_v2_cells(tmp_path) -> None:
    """Requested params stay byte-for-byte; effective params gain the
    defaults; the campaign records scenario + semantics version identity."""

    noise0 = {"noise_count": 0, "noise_semantics_version": "key_retention_v2"}
    noise50 = {"noise_count": 50, "noise_semantics_version": "key_retention_v2"}
    args = _campaign_args(
        tmp_path,
        [
            json.dumps({"name": "noise0", "params": noise0}),
            json.dumps({"name": "noise50", "params": noise50}),
        ],
        scenario="memory_noise_stress",
    )
    plan, error = campaign.prepare_campaign(args)
    assert error is None
    assert plan["scenario"] == "memory_noise_stress"
    assert plan["semantics_version"] == "key_retention_v2"
    assert [cell["params"] for cell in plan["cells"]] == [noise0, noise50]
    assert [cell["effective_params"] for cell in plan["cells"]] == [noise0, noise50]


def test_q16_preflight_rejects_memory_noise_without_explicit_v2(tmp_path) -> None:
    v2 = {"noise_count": 10, "noise_semantics_version": "key_retention_v2"}
    # Missing the version entirely (legacy by default).
    _assert_preflight_rejects(
        tmp_path / "a",
        [json.dumps({"name": "n", "params": {"noise_count": 10}})],
        scenario="memory_noise_stress",
    )
    # Explicitly legacy.
    _assert_preflight_rejects(
        tmp_path / "b",
        [json.dumps({"name": "n", "params": {"noise_semantics_version": "legacy"}})],
        scenario="memory_noise_stress",
    )
    # Mixed semantics versions in one campaign.
    _assert_preflight_rejects(
        tmp_path / "c",
        [
            json.dumps({"name": "a", "params": v2}),
            json.dumps(
                {"name": "b", "params": {"noise_semantics_version": "legacy"}}
            ),
        ],
        scenario="memory_noise_stress",
    )
    # Semantically duplicate cells (same effective params, two names).
    _assert_preflight_rejects(
        tmp_path / "d",
        [
            json.dumps({"name": "alpha", "params": v2}),
            json.dumps({"name": "beta", "params": v2}),
        ],
        scenario="memory_noise_stress",
    )
    # Invalid difficulty value still fails via scenario validation.
    _assert_preflight_rejects(
        tmp_path / "e",
        [
            json.dumps(
                {
                    "name": "n",
                    "params": {"noise_count": -1, "noise_semantics_version": "key_retention_v2"},
                }
            )
        ],
        scenario="memory_noise_stress",
    )


def test_q16_memory_noise_schedule_preserves_invariants(tmp_path) -> None:
    cells = _cells("memory_noise_stress")
    schedule = campaign.build_schedule(
        cells=cells,
        backends=["none", "vector", "mem0", "letta"],
        seeds=[42, 43, 44],
        python="py",
        results_dir=tmp_path,
        scenario="memory_noise_stress",
    )
    assert len(schedule) == 3 * 4 * 2
    assert [entry["seed"] for entry in schedule] == [42] * 8 + [43] * 8 + [44] * 8
    first_seed_backends = [e["backend"] for e in schedule[:8]]
    second_seed_backends = [e["backend"] for e in schedule[8:16]]
    assert first_seed_backends[:4] != second_seed_backends[:4]
    for entry in schedule:
        assert entry["scenario"] == "memory_noise_stress"
        assert entry["requested_params"]["noise_semantics_version"] == (
            "key_retention_v2"
        )
        assert entry["effective_params"]["noise_count"] in (0, 50)
        assert entry["fixture_identity"] == cli.CONTROLLED_FIXTURE_IDENTITY
        command = entry["command"]
        assert command[command.index("--scenario") + 1] == "memory_noise_stress"
        assert command[command.index("--runs") + 1] == "1"
        assert "noise_semantics_version=key_retention_v2" in command


def _memory_noise_manifest(tmp_path: Path) -> dict:
    cells = _cells("memory_noise_stress")[:1]
    return {
        "schema_version": "controlled-campaign/v3",
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "controlled",
        "scenario": "memory_noise_stress",
        "semantics_version": "key_retention_v2",
        "results_dir": str(tmp_path),
        "stores": _stores(tmp_path),
        "seeds": [42],
        "backends": ["none"],
        "cells": cells,
        "runs": campaign.build_schedule(
            cells=cells,
            backends=["none"],
            seeds=[42],
            python="py",
            results_dir=tmp_path,
            scenario="memory_noise_stress",
        ),
    }


def _run_memory_noise_once(tmp_path: Path, invoke_run) -> dict:
    manifest = _memory_noise_manifest(tmp_path)
    manifest_path = tmp_path / "campaign_manifest.json"
    rc = campaign.run_campaign(
        manifest_path,
        manifest,
        spawn_bot=lambda entry, port: _FakeProc(),
        await_health=lambda port: {"mode": "mock"},
        invoke_run=invoke_run,
    )
    return {
        "rc": rc,
        "entry": json.loads(manifest_path.read_text(encoding="utf-8"))["runs"][0],
    }


def test_q16_memory_noise_lifecycle_and_result_validation(tmp_path) -> None:
    """A valid, agreeing memory-noise v2 result passes; any pre-registration
    mismatch fails closed and stops the campaign."""

    def valid(command, *, results_dir, stdout_log, stderr_log, stores):
        manifest_now = json.loads(
            (tmp_path / "ok" / "campaign_manifest.json").read_text(encoding="utf-8")
        )
        payload = _valid_result_payload(manifest_now["runs"][0])
        (results_dir / "scenario_fake.json").write_text(json.dumps(payload))
        return 0

    outcome = _run_memory_noise_once(tmp_path / "ok", valid)
    assert outcome["rc"] == 0
    assert outcome["entry"]["status"] == "ok"
    assert outcome["entry"]["scenario"] == "memory_noise_stress"

    def mismatched(command, *, results_dir, stdout_log, stderr_log, stores):
        manifest_now = json.loads(
            (tmp_path / "bad" / "campaign_manifest.json").read_text(encoding="utf-8")
        )
        payload = _valid_result_payload(manifest_now["runs"][0])
        payload["params"] = {"noise_count": 0}  # missing the version
        (results_dir / "scenario_fake.json").write_text(json.dumps(payload))
        return 0

    outcome = _run_memory_noise_once(tmp_path / "bad", mismatched)
    assert outcome["rc"] == 1
    assert outcome["entry"]["status"] == "failed"
    assert "params mismatch" in outcome["entry"]["error"]

    def unfair(command, *, results_dir, stdout_log, stderr_log, stores):
        manifest_now = json.loads(
            (tmp_path / "unfair" / "campaign_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        payload = _valid_result_payload(manifest_now["runs"][0])
        payload["fairness"]["valid"] = False
        payload["fairness"]["invalid_reason"] = "leak"
        (results_dir / "scenario_fake.json").write_text(json.dumps(payload))
        return 0

    outcome = _run_memory_noise_once(tmp_path / "unfair", unfair)
    assert outcome["rc"] == 1
    assert outcome["entry"]["status"] == "failed"
    assert "fairness invalid" in outcome["entry"]["error"]


async def test_q16_controlled_memory_noise_v2_cli_path(monkeypatch, tmp_path) -> None:
    """End-to-end hermetic CLI: a Controlled memory-noise v2 run produces the
    typed ground truth, deterministic ctrl- identities, and a valid fairness
    record."""

    from minemembench.scenarios.base import KeyRetentionGroundTruth

    monkeypatch.setattr(cli, "BotClient", CanonicalBridge)
    monkeypatch.setattr(
        cli, "create_memory_backend", lambda name, settings: RecordingBackend()
    )
    monkeypatch.setattr(cli, "OpenAICompatibleProvider", lambda settings: SmartFakeLLM())

    args = cli._build_parser().parse_args(
        [
            "run",
            "--scenario",
            "memory_noise_stress",
            "--memory",
            "recording",
            "--runs",
            "1",
            "--seed",
            "42",
            "--campaign-mode",
            "controlled",
            "--scenario-param",
            "noise_count=10",
            "--scenario-param",
            "noise_semantics_version=key_retention_v2",
        ]
    )
    results = await cli._run_scenario_async(
        args,
        make_settings(results_dir=str(tmp_path / "res")),
        {"noise_count": 10, "noise_semantics_version": "key_retention_v2"},
    )
    assert len(results) == 1
    result = results[0]
    assert result.scenario == "memory_noise_stress"
    assert result.campaign_mode == "controlled"
    assert result.params == {
        "noise_count": 10,
        "noise_semantics_version": "key_retention_v2",
    }
    fairness = result.fairness
    assert fairness is not None
    assert fairness.valid is True
    assert fairness.campaign_mode == "controlled"
    assert fairness.run_seed == 42
    assert fairness.fixture_identity == cli.CONTROLLED_FIXTURE_IDENTITY
    assert fairness.scenario_params == result.params

    assert len(result.injected_events) == 11
    assert all(e.event_id.startswith("ctrl-") for e in result.injected_events)
    ground_truth = result.evaluation_ground_truth
    assert isinstance(ground_truth, KeyRetentionGroundTruth)
    assert len(ground_truth.noise_event_ids) == 10
    assert ground_truth.target_event_id
    assert (
        result.metrics["retrieval_evidence_source"]
        == "run_log.steps[0].retrieved_items"
    )
