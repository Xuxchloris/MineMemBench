"""Scenario E — Failure Transfer (M15B, upgrade of failure_learning).

**STATUS: SUSPENDED — research-invalid, removed from the public scenario
registry (TASK-002 safety gate, A-AUDIT-002 critical finding).** The scenario
writes `TASK_FAILED(reason=missing_tool)` and an exact
`requires_tool=iron_pickaxe` fact after a run that cannot actually observe
either: the current protocol/world fixture (virtual tool gates, mock/real bot
actions without equipment preconditions) produces no failed `ActionResult`
carrying a missing-tool cause. The causal failure and its solution are
authored, not observed, so no adaptation measured here can support a
failure-learning conclusion. All endpoints are N/A. Do not redesign it inside
the measurement-validity task; the module remains only as a development
artifact for a future redesign around real observed failure causes.

The first task fails because a specific tool is missing (the container is
reinforced and cannot be opened without an iron pickaxe). A second task
differs in map area, goal object and location, but shares the underlying
failure cause — the same missing-tool precondition. Adaptation must emerge
from Experience -> Memory -> Retrieve -> Planner -> Action: nothing in the
scenario tells the planner "if a task failed before, prepare the tool". The
failure is recorded only as facts (a TASK_FAILED event and a tool-requirement
fact); whether the planner prepares the tool on the transfer task is what the
metrics measure.

Tool gates are virtual (Phase-1 simplification, documented): a task succeeds
only when the run BOTH reached the goal object's location AND equipped the
required tool. The scenario evaluates this from the run log; the bot never
sees a real block or a real inventory.

Difficulty parameter:
  - `transfer_count` (default 2): total number of tasks, one initial failing
    task plus `transfer_count - 1` transfer tasks.
  - `noise_fact_count` (default 5): unrelated world facts between the failure
    and the transfers (mirrors failure_learning's interference).

Seed usage: `random.Random(seed)` drives the first task's location;
`random.Random(seed + 1000 + 100 * k)` drives transfer task k's location;
`random.Random(seed + 1)` drives the interference action and noise facts.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

from ..core.ids import new_event_id
from ..core.models import EventType, ExperienceEvent, Position
from ..core.runner import RunLog, SUCCESS_RADIUS_BLOCKS
from .base import Scenario, ScenarioContext, ScenarioResult
from .delayed_recall import _NOISE_FACTS
from .offsets import seeded_offset_distinct

#: Deliberately free of any coordinates and tool hints: the first task's goal.
FIRST_GOAL = "Collect the reinforced supply crate from the north quarry."

#: The tool whose absence caused the first failure; must transfer to the new tasks.
REQUIRED_TOOL = "iron_pickaxe"

#: Seeded map areas and goal objects for the transfer tasks. Every object is a
#: *supply* container so its goal shares substantive tokens with the recorded
#: failure/tool facts (the crude hash embedder needs the overlap to retrieve
#: them); the underlying failure cause — the same missing tool — is what must
#: transfer, and each task still differs in map area, object, and location.
_MAP_AREAS = ("east quarry", "south cavern", "west tunnel", "north ridge", "sunken hall")
_OBJECTS = (
    "sealed supply vault",
    "locked supply cache",
    "iron supply lockbox",
    "buried supply hoard",
    "walled supply vault",
)


@dataclass(frozen=True)
class TransferTask:
    """One transfer task: a NEW map area, goal object, and location."""

    index: int
    map_area: str
    object_name: str
    location: Position
    goal: str


def _prepared(run: RunLog, tool: str) -> bool:
    """True when the run equipped `tool` at some step."""

    return any(
        step.action == "equip_item" and step.arguments.get("item") == tool
        for step in run.steps
    )


def _reached(run: RunLog, location: Position) -> bool:
    """True when the run's position came within SUCCESS_RADIUS of `location`."""

    return any(
        math.dist(
            (step.position.x, step.position.y, step.position.z),
            (location.x, location.y, location.z),
        )
        <= SUCCESS_RADIUS_BLOCKS
        for step in run.steps
    )


class FailureTransferScenario(Scenario):
    """Scenario E: does the failure's TOOL knowledge transfer to a new task?"""

    name: ClassVar[str] = "failure_transfer"
    default_params: ClassVar[dict[str, Any]] = {
        "transfer_count": 2,
        "noise_fact_count": 5,
    }

    def __init__(self) -> None:
        self.first_location: Position | None = None
        self.transfer_tasks: list[TransferTask] = []
        self.attempt_1_log: RunLog | None = None
        self.transfer_logs: list[RunLog] = []

    def _validate_params(self) -> None:
        self._require_int_param("transfer_count", 2)
        self._require_int_param("noise_fact_count", 0)

    async def setup(self, ctx: ScenarioContext) -> None:
        """Fix the first task's and every transfer task's location, seeded."""

        spawn = (await ctx.bot.get_state()).position
        self.first_location = seeded_offset_distinct(spawn, ctx.seed, [])
        self.transfer_tasks = []
        locations_so_far: list[Position] = [self.first_location]
        for k in range(1, self.params["transfer_count"]):
            area = _MAP_AREAS[(k - 1) % len(_MAP_AREAS)]
            obj = _OBJECTS[(k - 1) % len(_OBJECTS)]
            location = seeded_offset_distinct(
                spawn, ctx.seed + 1000 + 100 * k, locations_so_far
            )
            locations_so_far.append(location)
            self.transfer_tasks.append(
                TransferTask(
                    index=k,
                    map_area=area,
                    object_name=obj,
                    location=location,
                    goal=f"Retrieve the {obj} from the {area}.",
                )
            )

    async def experience_phase(self, ctx: ScenarioContext) -> None:
        """First attempt (no tool knowledge yet), then record the failure facts."""

        assert self.first_location is not None
        self.attempt_1_log = await ctx.runner.run_goal(
            goal=FIRST_GOAL, success_at=None, max_steps=2,
            episode_id=ctx.episode_id,
        )
        # Facts only — never a behavioral rule ("prepare the tool next time").
        await ctx.memory.add(
            ExperienceEvent(
                event_id=new_event_id(),
                episode_id=ctx.episode_id,
                timestamp=datetime.now(UTC),
                actor="agent",
                event_type=EventType.TASK_FAILED,
                context={
                    "task": "collect_reinforced_supply_crate",
                    "reason": "missing_tool",
                    "object": "reinforced_supply_crate",
                    "tool_required": REQUIRED_TOOL,
                    "attempt": 1,
                },
            )
        )
        await ctx.memory.add(
            ExperienceEvent(
                event_id=new_event_id(),
                episode_id=ctx.episode_id,
                timestamp=datetime.now(UTC),
                actor="environment",
                event_type=EventType.WORLD_FACT_UPDATED,
                context={
                    "subject": "tool_requirement",
                    "container": "supply_crate",
                    "requires_tool": REQUIRED_TOOL,
                },
            )
        )

    async def interference_phase(self, ctx: ScenarioContext) -> None:
        """Unrelated world facts plus one real seeded bot action."""

        rng = random.Random(ctx.seed + 1)
        pos = (await ctx.bot.get_state()).position
        dx = rng.choice((-1, 1)) * rng.randint(1, 3)
        dz = rng.choice((-1, 1)) * rng.randint(1, 3)
        await ctx.bot.execute(
            "move_to", {"x": pos.x + dx, "y": pos.y, "z": pos.z + dz}
        )

        for _ in range(self.params["noise_fact_count"]):
            await ctx.memory.add(
                ExperienceEvent(
                    event_id=new_event_id(),
                    episode_id=ctx.episode_id,
                    timestamp=datetime.now(UTC),
                    actor="environment",
                    event_type=EventType.WORLD_FACT_UPDATED,
                    context={"subject": "world", "fact": rng.choice(_NOISE_FACTS)},
                )
            )

    async def test_phase(self, ctx: ScenarioContext) -> None:
        """Each transfer task: store its location debrief, then run the goal.

        The location debrief is written right before the attempt so the only
        coordinates in memory are this task's — what must transfer is the tool
        knowledge, not any other task's location.
        """

        self.transfer_logs = []
        for task in self.transfer_tasks:
            subject = f"{task.object_name.replace(' ', '_')}_location"
            await ctx.memory.add(
                ExperienceEvent(
                    event_id=new_event_id(),
                    episode_id=ctx.episode_id,
                    timestamp=datetime.now(UTC),
                    actor="scout",
                    event_type=EventType.WORLD_FACT_UPDATED,
                    context={
                        "subject": subject,
                        "x": task.location.x,
                        "y": task.location.y,
                        "z": task.location.z,
                        "note": f"scout debrief for the {task.object_name} "
                        f"in the {task.map_area}",
                    },
                )
            )
            log = await ctx.runner.run_goal(
                goal=task.goal, success_at=None, max_steps=3,
                episode_id=ctx.episode_id,
            )
            self.transfer_logs.append(log)

    async def evaluate(self, ctx: ScenarioContext) -> ScenarioResult:
        """Measure tool-preparation transfer, adaptation, and repetition."""

        assert self.first_location is not None
        assert self.attempt_1_log is not None

        attempt_1_prepared = int(_prepared(self.attempt_1_log, REQUIRED_TOOL))
        attempt_1_reached = int(_reached(self.attempt_1_log, self.first_location))
        attempt_1_success = 1 if (attempt_1_prepared and attempt_1_reached) else 0

        transfer_prepared = [
            int(_prepared(log, REQUIRED_TOOL)) for log in self.transfer_logs
        ]
        transfer_success = [
            1 if (prepared and _reached(log, task.location)) else 0
            for prepared, log, task in zip(
                transfer_prepared, self.transfer_logs, self.transfer_tasks
            )
        ]

        n = len(self.transfer_tasks)
        adaptation_success = (
            1 if n and transfer_prepared[0] and not attempt_1_prepared else 0
        )
        preparation_rate = (
            round(sum(transfer_prepared) / n, 4) if n else None
        )
        failure_repetition_rate = (
            round(sum(1 - prepared for prepared in transfer_prepared) / n, 4)
            if n
            else None
        )
        transfer_success_rate = (
            round(sum(transfer_success) / n, 4) if n else None
        )

        logs = [self.attempt_1_log, *self.transfer_logs]
        token_cost = sum(
            log.total_prompt_tokens + log.total_completion_tokens for log in logs
        )

        stats = await ctx.memory.stats()
        metrics: dict[str, float | int | str | None] = {
            "attempt_1_success": attempt_1_success,
            "attempt_1_prepared": attempt_1_prepared,
            "adaptation_success": adaptation_success,
            "preparation_rate": preparation_rate,
            "failure_repetition_rate": failure_repetition_rate,
            "transfer_success_rate": transfer_success_rate,
            "transfer_tasks": n,
            "llm_calls": sum(log.llm_calls for log in logs),
            "total_prompt_tokens": sum(log.total_prompt_tokens for log in logs),
            "total_completion_tokens": sum(
                log.total_completion_tokens for log in logs
            ),
            "token_cost": token_cost,
            "avg_add_latency_ms": stats.extra.get("avg_add_latency_ms"),
            "avg_retrieve_latency_ms": stats.extra.get("avg_retrieve_latency_ms"),
        }

        return ScenarioResult(
            scenario=self.name,
            episode_id=ctx.episode_id,
            seed=ctx.seed,
            memory_backend=stats.backend,
            success=transfer_success_rate == 1.0,
            metrics=metrics,
            run_log=self.transfer_logs[0] if self.transfer_logs else self.attempt_1_log,
            params=self.params,
        )
