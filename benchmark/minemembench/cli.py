"""Command-line interface for the benchmark core.

Commands:
- `probe`: Milestone-3 acceptance tool — check the bridge to the bot adapter.
- `run`: run one goal-directed episode (M4) or a full scenario harness (M7).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from .agent.llm_provider import LLMError, OpenAICompatibleProvider
from .agent.planner import PlannerError
from .core.client import BotBridgeError, BotClient
from .core.config import Settings
from .core.fairness import (
    CAMPAIGN_MODE_CONTROLLED,
    CAMPAIGN_MODE_NATIVE,
    FairnessChecker,
)
from .core.ids import new_run_id
from .core.models import (
    ActionResult,
    BotMode,
    EntityKind,
    HealthResponse,
    InventoryItem,
    NearbyEntity,
    NearbyPlayer,
    Position,
    WorldState,
)
from .core.runner import AgentRunner, RunLog
from .evaluation.metrics import aggregate, load_results
from .evaluation.reporter import write_charts, write_csv, write_markdown
from .events.collector import EventCollector
from .memory.base import EventRecordingBackend
from .memory.registry import (
    MemoryRegistryError,
    available_backends,
    create_memory_backend,
)
from .scenarios.base import ScenarioContext, ScenarioResult
from .scenarios.registry import (
    ScenarioRegistryError,
    available_scenarios,
    create_scenario,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minemembench",
        description="MineMemBench benchmark core CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe = subparsers.add_parser(
        "probe",
        help="Check health/state of the bot adapter and optionally run one action.",
    )
    probe.add_argument(
        "--bot-url",
        default=None,
        help="Bot adapter base URL (default: BOT_URL env or http://localhost:8081).",
    )
    probe.add_argument(
        "--action",
        default=None,
        help="Optional action to execute once, e.g. --action chat.",
    )
    probe.add_argument(
        "--args",
        default="{}",
        help='JSON object of action arguments, e.g. \'{"message":"hi"}\'.',
    )
    probe.add_argument(
        "--timeout-ms",
        type=int,
        default=30000,
        help="Action timeout in milliseconds (default 30000, max 120000).",
    )
    probe.set_defaults(handler=_cmd_probe)

    run = subparsers.add_parser(
        "run",
        help="Run one goal-directed episode, or a full scenario harness.",
    )
    run.add_argument(
        "--bot-url",
        default=None,
        help="Bot adapter base URL (default: BOT_URL env or http://localhost:8081).",
    )
    run.add_argument(
        "--memory",
        default="none",
        help=f"Memory backend name ({', '.join(available_backends())}).",
    )
    run.add_argument(
        "--goal",
        default=None,
        help=(
            "Natural-language goal for the agent, e.g. 'walk to 10,64,10'. "
            "Required in plain goal mode; ignored when --scenario is set."
        ),
    )
    run.add_argument(
        "--success-at",
        default=None,
        metavar="X,Y,Z",
        help="Optional goal position; run succeeds within 2 blocks of it.",
    )
    run.add_argument(
        "--max-steps",
        type=int,
        default=10,
        help="Maximum observe-decide-act iterations (default 10).",
    )
    run.add_argument(
        "--scenario",
        default=None,
        help=(
            "Scenario name; runs the scenario harness. Available: "
            f"{', '.join(available_scenarios())}."
        ),
    )
    run.add_argument(
        "--scenario-param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Difficulty parameter for the selected scenario, repeatable, "
            "e.g. --scenario-param interference_count=200. Recorded into every "
            "run log for the fairness audit."
        ),
    )
    run.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of scenario runs (default 1).",
    )
    run.add_argument(
        "--seed",
        type=int,
        default=42,
        help=(
            "Base seed for the scenario's seeded RNG (default 42). With "
            "--runs N, run i uses seed + i (a paired schedule shared by every "
            "backend) and the effective seed is recorded in each run log."
        ),
    )
    run.add_argument(
        "--campaign-mode",
        choices=[CAMPAIGN_MODE_NATIVE, CAMPAIGN_MODE_CONTROLLED],
        default=CAMPAIGN_MODE_NATIVE,
        help=(
            "Campaign identity recorded in the run log and fairness record. "
            "'controlled' enforces a fresh canonical mock fixture "
            "(fail-closed on any other health mode), deterministic scenario "
            "events, and exactly one run per invocation; campaigns are driven "
            "by scripts/run_controlled_campaign.py."
        ),
    )
    run.add_argument("--model", default=None, help="LLM model override.")
    run.add_argument(
        "--temperature", type=float, default=None, help="LLM temperature override."
    )
    run.set_defaults(handler=_cmd_run)

    report = subparsers.add_parser(
        "report",
        help=(
            "Generate summary.csv, report.md, and charts/*.png from "
            "scenario_*.json results."
        ),
    )
    report.add_argument(
        "--results-dir",
        default=None,
        help=(
            "Directory of scenario_*.json result files "
            "(default: RESULTS_DIR env or results/)."
        ),
    )
    report.set_defaults(handler=_cmd_report)

    return parser


def _print_health(health: HealthResponse) -> None:
    print("health:")
    print(f"  status:    {health.status}")
    print(f"  mode:      {health.mode.value}")
    print(f"  connected: {health.connected}")
    print(f"  username:  {health.username}")
    print(f"  uptime_s:  {health.uptime_s}")


def _print_state_summary(state: WorldState) -> None:
    pos = state.position
    print("world state:")
    print(f"  username:        {state.username}")
    print(f"  mode:            {state.mode.value}")
    print(f"  health/food:     {state.health}/{state.food}")
    print(f"  position:        ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f})")
    print(f"  dimension:       {state.dimension}")
    print(f"  time_of_day:     {state.time_of_day}")
    print(f"  is_raining:      {state.is_raining}")
    print(f"  inventory:       {len(state.inventory)} stacks")
    print(f"  nearby_entities: {len(state.nearby_entities)}")
    print(f"  nearby_players:  {len(state.nearby_players)}")


def _print_action_result(result: ActionResult) -> None:
    print("action result:")
    print(f"  action:  {result.action}")
    print(f"  status:  {result.status.value}")
    print(f"  result:  {json.dumps(result.result)}")
    print(f"  error:   {result.error}")


async def _probe_async(args: argparse.Namespace, settings: Settings) -> int:
    base_url: str = args.bot_url or settings.bot_url
    action_args: dict[str, Any] = json.loads(args.args)
    if not isinstance(action_args, dict):
        raise ValueError("--args must be a JSON object")

    async with BotClient(base_url) as client:
        health = await client.health()
        _print_health(health)

        state = await client.get_state()
        _print_state_summary(state)

        if args.action is not None:
            result = await client.execute(
                args.action, action_args, timeout_ms=args.timeout_ms
            )
            _print_action_result(result)

    return 0


def _cmd_probe(args: argparse.Namespace, settings: Settings) -> int:
    try:
        return asyncio.run(_probe_async(args, settings))
    except json.JSONDecodeError as exc:
        print(f"error: --args is not valid JSON: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except BotBridgeError as exc:
        print(f"error: bot bridge: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        # Covers connection failures, timeouts, and non-protocol HTTP errors.
        print(f"error: cannot reach bot adapter: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: cannot reach bot adapter: {exc}", file=sys.stderr)
        return 1


def _parse_success_at(raw: str) -> Position:
    """Parse an 'x,y,z' CLI string into a Position."""

    parts = raw.split(",")
    if len(parts) != 3:
        raise ValueError(f"--success-at must be 'x,y,z', got {raw!r}")
    try:
        x, y, z = (float(part) for part in parts)
    except ValueError:
        raise ValueError(f"--success-at must be numeric 'x,y,z', got {raw!r}") from None
    return Position(x=x, y=y, z=z)


def _coerce_param_value(value: str) -> Any:
    """Parse a scenario-param string value into bool/int/float/str."""

    lowered = value.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _parse_scenario_params(entries: list[str]) -> dict[str, Any]:
    """Parse repeated `--scenario-param KEY=VALUE` entries into a dict."""

    params: dict[str, Any] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(
                f"--scenario-param must be KEY=VALUE, got {entry!r}"
            )
        key, value = entry.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"--scenario-param has an empty key in {entry!r}")
        params[key] = _coerce_param_value(value)
    return params


def _print_run_log(log: RunLog) -> None:
    print(f"run {log.run_id} — memory={log.memory_backend} model={log.model} "
          f"temperature={log.temperature}")
    print(f"goal: {log.goal}")
    for step in log.steps:
        pos = step.position
        print(
            f"  step {step.index}: {step.action}({json.dumps(step.arguments)}) "
            f"-> {step.action_status.value} "
            f"at ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f}) "
            f"[mem={step.retrieved_memory_count} "
            f"tok={step.prompt_tokens}+{step.completion_tokens} "
            f"{step.latency_s:.2f}s]"
        )
        print(f"    reason: {step.reason}")
    print("summary:")
    print(f"  success:                  {log.success}")
    print(f"  steps:                    {len(log.steps)}")
    print(f"  llm_calls:                {log.llm_calls}")
    print(f"  total_prompt_tokens:      {log.total_prompt_tokens}")
    print(f"  total_completion_tokens:  {log.total_completion_tokens}")


async def _run_async(args: argparse.Namespace, settings: Settings) -> RunLog:
    base_url: str = args.bot_url or settings.bot_url
    success_at = (
        _parse_success_at(args.success_at) if args.success_at is not None else None
    )

    memory = create_memory_backend(args.memory, settings)
    llm = OpenAICompatibleProvider(settings)

    async with BotClient(base_url) as bot:
        health = await bot.health()
        if not health.connected:
            raise BotBridgeError(
                "bot adapter is reachable but not connected to a Minecraft server"
            )
        print(f"bot: {health.username} ({health.mode.value} mode)")

        runner = AgentRunner(bot, memory, llm)
        return await runner.run_goal(
            args.goal, max_steps=args.max_steps, success_at=success_at
        )


def _cmd_report(args: argparse.Namespace, settings: Settings) -> int:
    results_dir = Path(args.results_dir or settings.results_dir)
    if not results_dir.is_dir():
        print(f"error: results directory not found: {results_dir}", file=sys.stderr)
        return 2

    results = load_results(results_dir)
    if not results:
        print(
            f"error: no scenario_*.json result files found under {results_dir}",
            file=sys.stderr,
        )
        return 2

    aggregates = aggregate(results)
    out_dir = results_dir / "report"
    charts_dir = out_dir / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    csv_path = write_csv(aggregates, out_dir / "summary.csv")
    md_path = write_markdown(aggregates, results, out_dir / "report.md")
    try:
        chart_paths = write_charts(aggregates, charts_dir)
    except ImportError:
        print(
            "error: matplotlib is not installed; install it with "
            '`uv pip install -e ".[report]"` (the `report` extra)',
            file=sys.stderr,
        )
        return 1

    print(f"summary: {csv_path}")
    print(f"report:  {md_path}")
    for chart_path in chart_paths:
        print(f"chart:   {chart_path}")
    return 0


#: Controlled Mode scenario/version policy (TASK-014): the ONLY approved
#: combinations. Both the CLI gate and the campaign runner validate through
#: this single policy — never duplicate the allowlist. The policy consumes
#: the scenario's FULL EFFECTIVE params (post `apply_params`), not raw input;
#: the scenario's own validation stays authoritative for names/types/ranges,
#: and the scenario-level fail-closed gates remain defense in depth.
CONTROLLED_VERSION_PARAM = {
    "delayed_recall": "recall_semantics_version",
    "world_update": "update_semantics_version",
    "memory_noise_stress": "noise_semantics_version",
    "failure_learning": "failure_semantics_version",
    "failure_learning_multi": "failure_semantics_version",
    "long_lived_memory": "lifetime_semantics_version",
}
CONTROLLED_APPROVED_VERSIONS = {
    # delayed_recall legacy stays approved for historical
    # reproducibility/diagnostics; world_update, memory_noise_stress and
    # failure_learning are v2-only.
    "delayed_recall": frozenset({"legacy", "entity_key_v2"}),
    "world_update": frozenset({"temporal_chain_v2"}),
    "memory_noise_stress": frozenset({"key_retention_v2"}),
    "failure_learning": frozenset({"observed_precondition_v2"}),
    "failure_learning_multi": frozenset(
        {"observed_precondition_applicability_v4"}
    ),
    "long_lived_memory": frozenset({"lifetime_v1"}),
}


def validate_controlled_policy(
    scenario_name: str, effective_params: dict[str, Any]
) -> str | None:
    """Validate one Controlled scenario/version combination.

    Returns None when approved, else a human-readable rejection reason.
    `effective_params` must be the scenario's full effective params (defaults
    merged), so a missing version override fails closed via the default.
    """

    param = CONTROLLED_VERSION_PARAM.get(scenario_name)
    if param is None:
        return (
            f"scenario {scenario_name!r} is not approved for Controlled Mode "
            f"(approved: {', '.join(sorted(CONTROLLED_VERSION_PARAM))})"
        )
    version = effective_params.get(param)
    allowed = CONTROLLED_APPROVED_VERSIONS[scenario_name]
    if version not in allowed:
        return (
            f"Controlled {scenario_name} requires {param} in "
            f"{sorted(allowed)}, got {version!r}"
        )
    return None


def _cmd_run(args: argparse.Namespace, settings: Settings) -> int:
    scenario_params: dict[str, Any] = {}
    scenario = None
    if args.scenario is not None:
        try:
            scenario = create_scenario(args.scenario)
            scenario_params = _parse_scenario_params(args.scenario_param)
            scenario.apply_params(scenario_params)
        except ScenarioRegistryError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.runs < 1:
            print("error: --runs must be >= 1", file=sys.stderr)
            return 2
    elif args.goal is None:
        print("error: --goal is required unless --scenario is given", file=sys.stderr)
        return 2

    if args.campaign_mode == CAMPAIGN_MODE_CONTROLLED:
        if args.scenario is None:
            print(
                "error: --campaign-mode controlled requires --scenario",
                file=sys.stderr,
            )
            return 2
        if args.runs != 1:
            print(
                "error: --runs must be 1 in Controlled Mode; every run needs a "
                "fresh canonical mock adapter, driven one run at a time by "
                "scripts/run_controlled_campaign.py",
                file=sys.stderr,
            )
            return 2
        # The central policy gate runs BEFORE any bot/LLM/backend contact.
        policy_error = validate_controlled_policy(args.scenario, scenario.params)
        if policy_error is not None:
            print(f"error: {policy_error}", file=sys.stderr)
            return 2

    # CLI overrides win over env/.env for this process only.
    if args.model is not None:
        settings.llm_model = args.model
    if args.temperature is not None:
        settings.llm_temperature = args.temperature

    if args.scenario is not None:
        return _run_scenario_mode(args, settings, scenario_params)
    return _run_plain_mode(args, settings)


def _run_plain_mode(args: argparse.Namespace, settings: Settings) -> int:
    try:
        log = asyncio.run(_run_async(args, settings))
    except MemoryRegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (BotBridgeError, httpx.HTTPError, OSError) as exc:
        print(f"error: cannot reach bot adapter: {exc}", file=sys.stderr)
        return 1
    except (LLMError, PlannerError) as exc:
        print(f"error: agent loop failed: {exc}", file=sys.stderr)
        return 1

    _print_run_log(log)

    results_dir = Path(settings.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    out_path = results_dir / f"{log.run_id}.json"
    out_path.write_text(log.to_json(), encoding="utf-8")
    print(f"run log written to {out_path}")

    return 0


#: Controlled Mode fixture selectors and versioned identities.  The canonical
#: fixture remains the default for every pre-TASK-020 scenario; failure
#: learning v2 selects the warded-hostiles fixture explicitly.  Selection is
#: based only on scenario semantics, never on the memory backend.
CONTROLLED_FIXTURE_SELECTOR = "canonical"
CONTROLLED_FIXTURE_IDENTITY = (
    "mock-fixture-v1: spawn=(0,64,0) minecraft:overworld time_of_day=6000 "
    "clear inventory=[32x stone, 1x stone_sword] "
    "entities=[zombie@(3,64,4), player Steve@(1,64,2)]"
)
CONTROLLED_WARDED_FIXTURE_SELECTOR = "warded_hostiles_v1"
CONTROLLED_WARDED_FIXTURE_IDENTITY = (
    "mock-fixture-warded-hostiles-v1: spawn=(0,64,0) "
    "minecraft:overworld time_of_day=6000 clear "
    "inventory=[32x stone, 1x stone_sword, 1x gold_nugget] "
    "entities=[zombie@(3,64,4), skeleton@(-4,64,3), "
    "player Steve@(1,64,2)] hidden_rule=warded-attack-v1"
)
CONTROLLED_WARDED_MULTI_FIXTURE_SELECTOR = "warded_hostiles_multi_v1"
CONTROLLED_WARDED_MULTI_FIXTURE_IDENTITY = (
    "mock-fixture-warded-hostiles-multi-v1: spawn=(0,64,0) "
    "minecraft:overworld time_of_day=6000 clear "
    "inventory=[32x stone, 1x stone_sword, 1x gold_nugget] "
    "entities=[zombie@(3,64,4), skeleton@(-4,64,3), "
    "spider@(6,64,-4), creeper@(-7,64,-5), player Steve@(1,64,2)] "
    "hidden_rule=warded-attack-v1"
)
CONTROLLED_HETEROGENEOUS_FAILURE_FIXTURE_SELECTOR = (
    "heterogeneous_failures_v1"
)
CONTROLLED_HETEROGENEOUS_FAILURE_FIXTURE_IDENTITY = (
    "mock-fixture-heterogeneous-failures-v1: spawn=(0,64,0) "
    "minecraft:overworld time_of_day=6000 clear "
    "inventory=[32x stone, 1x stone_sword, 1x gold_nugget, "
    "1x iron_ingot, 1x string] entities=[zombie@(3,64,4), "
    "alpha_zombie@(3,64,4), alpha_creeper@(-4,64,3), "
    "beta_skeleton@(6,64,-4), beta_stray@(-7,64,-5), "
    "gamma_spider@(9,64,2), gamma_cave_spider@(-10,64,1), "
    "player Steve@(1,64,2)] hidden_rules=heterogeneous-attack-v1"
)
CONTROLLED_LIFETIME_FIXTURE_SELECTOR = "lifetime_route_v1"
CONTROLLED_LIFETIME_FIXTURE_IDENTITY = (
    "mock-fixture-lifetime-route-v1: spawn=(0,64,0) minecraft:overworld "
    "time_of_day=6000 clear inventory=[32x stone, 1x stone_sword] "
    "visible_entities=[zombie@(3,64,4), player Steve@(1,64,2)] "
    "hidden_drop=[lifetime_token@(40,64,0)]"
)


def controlled_fixture_spec(
    scenario_name: str, effective_params: dict[str, Any]
) -> tuple[str, str]:
    """Return the explicit (selector, versioned identity) for one treatment.

    The central Controlled policy must already have accepted the treatment.
    Keeping this mapping beside that policy makes the fixture a controlled
    scenario variable and prevents any backend-dependent selection.
    """

    if (
        scenario_name == "failure_learning"
        and effective_params.get("failure_semantics_version")
        == "observed_precondition_v2"
    ):
        return (
            CONTROLLED_WARDED_FIXTURE_SELECTOR,
            CONTROLLED_WARDED_FIXTURE_IDENTITY,
        )
    if (
        scenario_name == "failure_learning_multi"
        and effective_params.get("failure_semantics_version")
        == "observed_precondition_applicability_v4"
    ):
        return (
            CONTROLLED_HETEROGENEOUS_FAILURE_FIXTURE_SELECTOR,
            CONTROLLED_HETEROGENEOUS_FAILURE_FIXTURE_IDENTITY,
        )
    if (
        scenario_name == "long_lived_memory"
        and effective_params.get("lifetime_semantics_version") == "lifetime_v1"
    ):
        return (
            CONTROLLED_LIFETIME_FIXTURE_SELECTOR,
            CONTROLLED_LIFETIME_FIXTURE_IDENTITY,
        )
    return CONTROLLED_FIXTURE_SELECTOR, CONTROLLED_FIXTURE_IDENTITY


def canonical_fixture_state() -> WorldState:
    """The complete initial WorldState of a fresh mock adapter process.

    Mirrors `minecraft/src/mock.ts` field-for-field (verified against a live
    `BOT_MOCK=1` adapter, 2026-08). The observation `timestamp` is the only
    volatile field and is excluded from the fixture comparison.
    """

    return WorldState(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),  # placeholder, excluded
        mode=BotMode.MOCK,
        username="BenchBot",
        health=20.0,
        food=20,
        saturation=5.0,
        oxygen=20,
        position=Position(x=0.0, y=64.0, z=0.0),
        yaw=0.0,
        pitch=0.0,
        dimension="minecraft:overworld",
        time_of_day=6000,
        is_raining=False,
        experience_level=0,
        inventory=[
            InventoryItem(slot=0, name="stone", display_name="Stone", count=32),
            InventoryItem(
                slot=1, name="stone_sword", display_name="Stone Sword", count=1
            ),
        ],
        nearby_entities=[
            NearbyEntity(
                id=1001,
                name="zombie",
                display_name="Zombie",
                kind=EntityKind.HOSTILE,
                position=Position(x=3.0, y=64.0, z=4.0),
                distance=5.0,
            )
        ],
        nearby_players=[
            NearbyPlayer(
                username="Steve",
                position=Position(x=1.0, y=64.0, z=2.0),
                distance=2.2,
            )
        ],
    )


def warded_hostiles_fixture_state() -> WorldState:
    """Complete visible state of `BOT_MOCK_FIXTURE=warded_hostiles_v1`.

    The hidden attack rule is covered by adapter action tests; this state
    fingerprint audits every planner-visible field before a Controlled run.
    """

    state = canonical_fixture_state()
    state.inventory.append(
        InventoryItem(
            slot=2,
            name="gold_nugget",
            display_name="Gold Nugget",
            count=1,
        )
    )
    state.nearby_entities.append(
        NearbyEntity(
            id=1002,
            name="skeleton",
            display_name="Skeleton",
            kind=EntityKind.HOSTILE,
            position=Position(x=-4.0, y=64.0, z=3.0),
            distance=5.0,
        )
    )
    return state


def warded_hostiles_multi_fixture_state() -> WorldState:
    """Visible state of ``warded_hostiles_multi_v1``."""

    state = warded_hostiles_fixture_state()
    state.nearby_entities.extend(
        [
            NearbyEntity(
                id=1003,
                name="spider",
                display_name="Spider",
                kind=EntityKind.HOSTILE,
                position=Position(x=6.0, y=64.0, z=-4.0),
                distance=7.2,
            ),
            NearbyEntity(
                id=1004,
                name="creeper",
                display_name="Creeper",
                kind=EntityKind.HOSTILE,
                position=Position(x=-7.0, y=64.0, z=-5.0),
                distance=8.6,
            ),
        ]
    )
    return state


def heterogeneous_failures_fixture_state() -> WorldState:
    """Visible state of ``heterogeneous_failures_v1``."""

    state = canonical_fixture_state()
    state.inventory.extend(
        [
            InventoryItem(
                slot=2,
                name="gold_nugget",
                display_name="Gold Nugget",
                count=1,
            ),
            InventoryItem(
                slot=3,
                name="iron_ingot",
                display_name="Iron Ingot",
                count=1,
            ),
            InventoryItem(
                slot=4,
                name="string",
                display_name="String",
                count=1,
            ),
        ]
    )
    specifications = [
        (1011, "alpha_zombie", 3.0, 64.0, 4.0, 5.0),
        (1012, "alpha_creeper", -4.0, 64.0, 3.0, 5.0),
        (1021, "beta_skeleton", 6.0, 64.0, -4.0, 7.2),
        (1022, "beta_stray", -7.0, 64.0, -5.0, 8.6),
        (1031, "gamma_spider", 9.0, 64.0, 2.0, 9.2),
        (1032, "gamma_cave_spider", -10.0, 64.0, 1.0, 10.0),
    ]
    state.nearby_entities.extend(
        NearbyEntity(
            id=entity_id,
            name=name,
            display_name=" ".join(part.title() for part in name.split("_")),
            kind=EntityKind.HOSTILE,
            position=Position(x=x, y=y, z=z),
            distance=distance,
        )
        for entity_id, name, x, y, z, distance in specifications
    )
    return state


def controlled_fixture_state(selector: str) -> WorldState:
    """Return the complete expected visible state for a fixture selector."""

    if selector == CONTROLLED_FIXTURE_SELECTOR:
        return canonical_fixture_state()
    if selector == CONTROLLED_WARDED_FIXTURE_SELECTOR:
        return warded_hostiles_fixture_state()
    if selector == CONTROLLED_WARDED_MULTI_FIXTURE_SELECTOR:
        return warded_hostiles_multi_fixture_state()
    if selector == CONTROLLED_HETEROGENEOUS_FAILURE_FIXTURE_SELECTOR:
        return heterogeneous_failures_fixture_state()
    if selector == CONTROLLED_LIFETIME_FIXTURE_SELECTOR:
        # The lifetime token is intentionally outside the 32-block observation
        # radius, so the complete initial visible state equals canonical.
        return canonical_fixture_state()
    raise ValueError(f"unknown Controlled fixture selector: {selector!r}")


def _normalized_state(state: WorldState) -> dict[str, Any]:
    """The state without its volatile observation timestamp."""

    return state.model_dump(mode="json", exclude={"timestamp"})


async def _assert_controlled_fixture(
    bot: BotClient,
    health: HealthResponse,
    fixture_selector: str = CONTROLLED_FIXTURE_SELECTOR,
) -> str:
    """Fail closed unless the adapter exposes the selected fresh mock fixture.

    Controlled Mode exists to hold the planner's world constant across
    backends. The gate compares the COMPLETE normalized initial WorldState
    (everything except the volatile observation timestamp — mode, username,
    vitals, orientation, inventory, equipment, entities, players) against the
    selected fixture, so any fixture drift that could change the planner
    prompt fails the run instead of producing non-comparable evidence.
    Returns the fixture identity string for the fairness record.
    """

    if health.mode is not BotMode.MOCK:
        raise BotBridgeError(
            "Controlled Mode requires a fresh mock bot adapter, but health "
            f"reports mode={health.mode.value!r}; start one with BOT_MOCK=1 "
            "(scripts/run_controlled_campaign.py owns the per-run process)"
        )
    observed = _normalized_state(await bot.get_state())
    expected_state = controlled_fixture_state(fixture_selector)
    expected = _normalized_state(expected_state)
    if observed != expected:
        differing = [
            key
            for key in expected
            if observed.get(key) != expected[key]
        ] + [key for key in observed if key not in expected]
        fixture_label = (
            "is not canonical"
            if fixture_selector == CONTROLLED_FIXTURE_SELECTOR
            else f"does not match {fixture_selector!r}"
        )
        raise BotBridgeError(
            f"Controlled Mode fixture {fixture_label} "
            "(the mock adapter must be a FRESH process); differing fields: "
            + ", ".join(differing)
        )
    identities = {
        CONTROLLED_FIXTURE_SELECTOR: CONTROLLED_FIXTURE_IDENTITY,
        CONTROLLED_WARDED_FIXTURE_SELECTOR: CONTROLLED_WARDED_FIXTURE_IDENTITY,
        CONTROLLED_WARDED_MULTI_FIXTURE_SELECTOR: (
            CONTROLLED_WARDED_MULTI_FIXTURE_IDENTITY
        ),
        CONTROLLED_HETEROGENEOUS_FAILURE_FIXTURE_SELECTOR: (
            CONTROLLED_HETEROGENEOUS_FAILURE_FIXTURE_IDENTITY
        ),
        CONTROLLED_LIFETIME_FIXTURE_SELECTOR: CONTROLLED_LIFETIME_FIXTURE_IDENTITY,
    }
    return identities[fixture_selector]


async def _run_scenario_async(
    args: argparse.Namespace,
    settings: Settings,
    scenario_params: dict[str, Any],
) -> list[ScenarioResult]:
    llm = OpenAICompatibleProvider(settings)
    fairness_checker = FairnessChecker(settings, llm)
    campaign_mode: str = args.campaign_mode

    fixture_selector: str | None = None
    if campaign_mode == CAMPAIGN_MODE_CONTROLLED:
        fixture_scenario = create_scenario(args.scenario)
        fixture_scenario.apply_params(scenario_params)
        fixture_selector, _fixture_identity = controlled_fixture_spec(
            fixture_scenario.name, fixture_scenario.params
        )

    async with BotClient(args.bot_url or settings.bot_url) as bot:
        health = await bot.health()
        if not health.connected:
            raise BotBridgeError(
                "bot adapter is reachable but not connected to a Minecraft server"
            )
        fixture_identity = None
        if campaign_mode == CAMPAIGN_MODE_CONTROLLED:
            assert fixture_selector is not None
            fixture_identity = await _assert_controlled_fixture(
                bot, health, fixture_selector
            )
        print(f"bot: {health.username} ({health.mode.value} mode)")

        results: list[ScenarioResult] = []
        for run_index in range(args.runs):
            episode_id = new_run_id()
            # Paired seed schedule: run i uses base_seed + i, identical for
            # every backend given the same base seed and run count.
            run_seed = args.seed + run_index
            # A fresh backend instance per run: latency counters and any
            # process-local scope never accumulate across runs. The recording
            # proxy captures the complete offered event sequence for the log.
            memory = EventRecordingBackend(create_memory_backend(args.memory, settings))
            # Controlled Mode skips the raw-stream collector: its mapped
            # events carry wall-clock timestamps/uuids, which would break the
            # identical-inputs invariant. Native mode is unchanged.
            collector = (
                None
                if campaign_mode == CAMPAIGN_MODE_CONTROLLED
                else EventCollector(bot, memory)
            )
            runner = AgentRunner(bot, memory, llm, event_collector=collector)
            ctx = ScenarioContext(
                bot=bot,
                memory=memory,
                runner=runner,
                llm=llm,
                settings=settings,
                seed=run_seed,
                episode_id=episode_id,
                campaign_mode=campaign_mode,
            )
            scenario = create_scenario(args.scenario)
            scenario.apply_params(scenario_params)
            result = await scenario.run(ctx)
            result.campaign_mode = campaign_mode
            result.injected_events = list(memory.offered_events)
            result.phase_records = list(ctx.records)

            # Metrics are captured; now reset the episode that ACTUALLY ran
            # and verify the cleanup (reset episode + fresh scope probes).
            probe_query = None
            if result.run_log is not None:
                probe_query = f"{result.scenario} {result.run_log.goal}"
            result.fairness = await fairness_checker.check(
                memory=memory,
                scenario=scenario.name,
                scenario_params=scenario.params,
                episode_id=episode_id,
                run_seed=run_seed,
                campaign_mode=campaign_mode,
                fixture_selector=fixture_selector,
                fixture_identity=fixture_identity,
                probe_query=probe_query,
            )
            results.append(result)

            results_dir = Path(settings.results_dir)
            results_dir.mkdir(parents=True, exist_ok=True)
            out_path = (
                results_dir
                / f"scenario_{scenario.name}_{args.memory}_{episode_id}.json"
            )
            out_path.write_text(result.to_json(), encoding="utf-8")
            fairness_valid = (
                result.fairness.valid if result.fairness is not None else True
            )
            print(
                f"run {run_index + 1}/{args.runs} "
                f"[{scenario.name} / {args.memory} / seed={ctx.seed}]: "
                f"success={result.success} "
                f"task_success={result.metrics.get('task_success')} "
                f"fact_retrieval_rank={result.metrics.get('fact_retrieval_rank')} "
                f"final_distance={result.metrics.get('final_distance_to_target')} "
                f"fairness_valid={fairness_valid}"
            )
            print(f"  scenario result written to {out_path}")
        return results


def _print_scenario_summary(
    args: argparse.Namespace, results: list[ScenarioResult]
) -> None:
    n = len(results)
    successes = sum(1 for result in results if result.success)
    rate = successes / n if n else 0.0
    print(
        f"scenario {args.scenario} — memory={args.memory} runs={n} "
        f"success_rate={successes}/{n} ({rate:.1%})"
    )


def _run_scenario_mode(
    args: argparse.Namespace, settings: Settings, scenario_params: dict[str, Any]
) -> int:
    try:
        results = asyncio.run(_run_scenario_async(args, settings, scenario_params))
    except MemoryRegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (BotBridgeError, httpx.HTTPError, OSError) as exc:
        print(f"error: cannot reach bot adapter: {exc}", file=sys.stderr)
        return 1
    except (LLMError, PlannerError) as exc:
        print(f"error: agent loop failed: {exc}", file=sys.stderr)
        return 1

    _print_scenario_summary(args, results)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    settings = Settings()
    handler = args.handler
    return int(handler(args, settings))


if __name__ == "__main__":
    sys.exit(main())
