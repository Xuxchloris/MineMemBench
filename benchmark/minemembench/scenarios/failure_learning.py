"""Scenario C — Experience-Guided Adaptation.

The agent fails to collect a supply crate (it has no coordinates), records
that failure, receives a scout debrief pointing at the crate, and then faces
the same goal again. Adaptation is measured by whether the SECOND attempt
beelines to the crate while the first did not — with no rule anywhere telling
the agent to use the debrief; the behaviour change must come from memory
retrieval alone.

Phase-1 simplification (documented): the current toolset has no equipment
mechanics, so adaptation is measured at the information/planning level (the
agent navigates to a known location it could not know before the debrief),
not via equipment use.

Seed usage: `random.Random(seed)` drives the crate offset in `setup`;
`random.Random(seed + 1)` drives the interference action and noise facts,
keeping every phase deterministic and phase-independent.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime
from typing import ClassVar

from ..core.ids import new_event_id
from ..core.models import EventType, ExperienceEvent, Position
from ..core.runner import RunLog
from ..memory.base import MemoryQuery
from .base import Scenario, ScenarioContext, ScenarioResult
from .delayed_recall import _NOISE_FACTS
from .world_update import seeded_offset

#: Deliberately free of any coordinates: the crate location must come from memory.
GOAL = "Collect the supply crate."

#: Distance (blocks) within which a first move counts as beelining to the crate.
_BEELINE_RADIUS_BLOCKS = 2.0


def _first_action_beeline(run: RunLog, target: Position) -> bool:
    """True when the run's first move_to destination is within 2 blocks of `target`."""

    for step in run.steps:
        if step.action == "move_to":
            destination = (
                step.arguments["x"],
                step.arguments["y"],
                step.arguments["z"],
            )
            return (
                math.dist(destination, (target.x, target.y, target.z))
                <= _BEELINE_RADIUS_BLOCKS
            )
    return False


class FailureLearningScenario(Scenario):
    """Scenario C: does a recorded failure change later behavior?"""

    name: ClassVar[str] = "failure_learning"

    def __init__(self) -> None:
        self.crate: Position | None = None
        self.attempt_1_log: RunLog | None = None
        self.attempt_2_log: RunLog | None = None

    async def setup(self, ctx: ScenarioContext) -> None:
        """Fix the crate location = bot spawn + seeded horizontal offset."""

        spawn = (await ctx.bot.get_state()).position
        self.crate = seeded_offset(spawn, random.Random(ctx.seed))

    async def experience_phase(self, ctx: ScenarioContext) -> None:
        """Fail at collecting, then store the failure and the scout debrief."""

        assert self.crate is not None
        self.attempt_1_log = await ctx.runner.run_goal(
            goal=GOAL, success_at=self.crate, max_steps=2,
            episode_id=ctx.episode_id,
        )
        await ctx.memory.add(
            ExperienceEvent(
                event_id=new_event_id(),
                episode_id=ctx.episode_id,
                timestamp=datetime.now(UTC),
                actor="agent",
                event_type=EventType.TASK_FAILED,
                context={
                    "task": "collect_supply_crate",
                    "reason": "location_unknown",
                    "attempt": 1,
                },
            )
        )
        await ctx.memory.add(
            ExperienceEvent(
                event_id=new_event_id(),
                episode_id=ctx.episode_id,
                timestamp=datetime.now(UTC),
                actor="scout",
                event_type=EventType.WORLD_FACT_UPDATED,
                context={
                    "subject": "supply_crate_location",
                    "x": self.crate.x,
                    "y": self.crate.y,
                    "z": self.crate.z,
                    "note": "scout debrief after failed attempt",
                },
            )
        )

    async def interference_phase(self, ctx: ScenarioContext) -> None:
        """Five unrelated world facts plus one real seeded bot action."""

        rng = random.Random(ctx.seed + 1)
        pos = (await ctx.bot.get_state()).position
        dx = rng.choice((-1, 1)) * rng.randint(1, 3)
        dz = rng.choice((-1, 1)) * rng.randint(1, 3)
        await ctx.bot.execute(
            "move_to", {"x": pos.x + dx, "y": pos.y, "z": pos.z + dz}
        )

        for _ in range(5):
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
        """Retry the same goal after the failed attempt and the debrief."""

        assert self.crate is not None
        self.attempt_2_log = await ctx.runner.run_goal(
            goal=GOAL, success_at=self.crate, max_steps=3,
            episode_id=ctx.episode_id,
        )

    async def evaluate(self, ctx: ScenarioContext) -> ScenarioResult:
        """Measure adaptation, navigation, cost, and memory latency."""

        assert self.crate is not None
        assert self.attempt_1_log is not None
        assert self.attempt_2_log is not None

        attempt_1_success = 1 if self.attempt_1_log.success else 0
        attempt_2_success = 1 if self.attempt_2_log.success else 0
        adaptation = 1 if (
            _first_action_beeline(self.attempt_2_log, self.crate)
            and not _first_action_beeline(self.attempt_1_log, self.crate)
        ) else 0

        last_positions: list[tuple[float, float, float]] = []
        for log in (self.attempt_1_log, self.attempt_2_log):
            if log.steps:
                last = log.steps[-1].position
            else:
                last = (await ctx.bot.get_state()).position
            last_positions.append((last.x, last.y, last.z))

        final_distance_to_crate_1 = math.dist(
            last_positions[0], (self.crate.x, self.crate.y, self.crate.z)
        )
        final_distance_to_crate_2 = math.dist(
            last_positions[1], (self.crate.x, self.crate.y, self.crate.z)
        )

        stats = await ctx.memory.stats()
        metrics: dict[str, float | int | str | None] = {
            "attempt_1_success": attempt_1_success,
            "attempt_2_success": attempt_2_success,
            "adaptation": adaptation,
            "final_distance_to_crate_1": round(final_distance_to_crate_1, 3),
            "final_distance_to_crate_2": round(final_distance_to_crate_2, 3),
            "llm_calls": self.attempt_1_log.llm_calls + self.attempt_2_log.llm_calls,
            "total_prompt_tokens": (
                self.attempt_1_log.total_prompt_tokens
                + self.attempt_2_log.total_prompt_tokens
            ),
            "total_completion_tokens": (
                self.attempt_1_log.total_completion_tokens
                + self.attempt_2_log.total_completion_tokens
            ),
            "avg_add_latency_ms": stats.extra.get("avg_add_latency_ms"),
            "avg_retrieve_latency_ms": stats.extra.get("avg_retrieve_latency_ms"),
        }

        return ScenarioResult(
            scenario=self.name,
            episode_id=ctx.episode_id,
            seed=ctx.seed,
            memory_backend=stats.backend,
            success=attempt_2_success == 1,
            metrics=metrics,
            run_log=self.attempt_2_log,
        )
