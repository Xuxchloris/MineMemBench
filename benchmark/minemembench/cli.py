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
from pathlib import Path
from typing import Any

import httpx

from .agent.llm_provider import LLMError, OpenAICompatibleProvider
from .agent.planner import PlannerError
from .core.client import BotBridgeError, BotClient
from .core.config import Settings
from .core.fairness import FairnessChecker
from .core.ids import new_run_id
from .core.models import ActionResult, HealthResponse, Position, WorldState
from .core.runner import AgentRunner, RunLog
from .evaluation.metrics import aggregate, load_results
from .evaluation.reporter import write_charts, write_csv, write_markdown
from .events.collector import EventCollector
from .memory.registry import MemoryRegistryError, create_memory_backend
from .scenarios.base import ScenarioContext, ScenarioResult
from .scenarios.registry import ScenarioRegistryError, create_scenario


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
        help="Memory backend name (none, vector, or mem0).",
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
        help="Scenario name, e.g. delayed_recall; runs the scenario harness.",
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
        help="Seeded RNG driving scenario phases (default 42).",
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


def _cmd_run(args: argparse.Namespace, settings: Settings) -> int:
    scenario_params: dict[str, Any] = {}
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


async def _run_scenario_async(
    args: argparse.Namespace,
    settings: Settings,
    scenario_params: dict[str, Any],
) -> list[ScenarioResult]:
    memory = create_memory_backend(args.memory, settings)
    llm = OpenAICompatibleProvider(settings)
    fairness_checker = FairnessChecker(settings, llm)

    async with BotClient(args.bot_url or settings.bot_url) as bot:
        health = await bot.health()
        if not health.connected:
            raise BotBridgeError(
                "bot adapter is reachable but not connected to a Minecraft server"
            )
        print(f"bot: {health.username} ({health.mode.value} mode)")

        results: list[ScenarioResult] = []
        previous_result: ScenarioResult | None = None
        previous_episode: str | None = None
        for run_index in range(args.runs):
            episode_id = new_run_id()
            await memory.reset(episode_id)
            collector = EventCollector(bot, memory)
            runner = AgentRunner(bot, memory, llm, event_collector=collector)
            ctx = ScenarioContext(
                bot=bot,
                memory=memory,
                runner=runner,
                llm=llm,
                settings=settings,
                seed=args.seed,
                episode_id=episode_id,
            )
            scenario = create_scenario(args.scenario)
            scenario.apply_params(scenario_params)
            result = await scenario.run(ctx)

            leak_probe_query = None
            if previous_result is not None and previous_result.run_log is not None:
                leak_probe_query = (
                    f"{previous_result.scenario} {previous_result.run_log.goal}"
                )
            result.fairness = await fairness_checker.check(
                memory=memory,
                scenario=scenario.name,
                scenario_params=scenario.params,
                previous_episode=previous_episode,
                next_episode=episode_id,
                leak_probe_query=leak_probe_query,
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
            previous_result = result
            previous_episode = episode_id
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
