"""Scenario B — World State Update (belief updating).

The agent learns one resource fact (a virtual "supply cache" at location A),
is told mid-episode that the cache *moved* to a new location B, then must
retrieve the cache using memory alone — the test goal deliberately contains no
coordinates.

This scenario measures BELIEF UPDATING: the fact change is written as a NEW
event (a fresh event_id), not as an `update()` call on the old one, so both
the stale fact (A) and the current fact (B) coexist in memory. A correct
belief-updating backend should surface the current fact B; a naive vector
baseline is EXPECTED to return the stale fact first on score ties (stable
insertion order) because A and B render to near-identical text. That stale
recall is the phenomenon under study, not a bug.

Phase-1 simplification: the supply cache is VIRTUAL. There is no block to
open and no item to collect; we measure navigation correctness to the
CURRENT location (B) rather than the stale one (A).

Seed usage: `random.Random(seed)` drives A in `setup`; `random.Random(seed +
100)` drives B; `random.Random(seed + 1)` drives the interference action and
noise facts, keeping every phase deterministic and phase-independent.
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

#: Deliberately free of any coordinates: the current location must come from memory.
GOAL = "Retrieve the supply cache."

#: Distance (blocks) within which a first move counts as heading for a location.
_BEELINE_RADIUS_BLOCKS = 2.0


def seeded_offset(spawn: Position, rng: random.Random) -> Position:
    """Spawn plus a seeded horizontal offset in [8, 20] blocks with random signs."""

    dx = rng.choice((-1, 1)) * rng.randint(8, 20)
    dz = rng.choice((-1, 1)) * rng.randint(8, 20)
    return Position(x=spawn.x + dx, y=spawn.y, z=spawn.z + dz)


class WorldUpdateScenario(Scenario):
    """Scenario B: does stale memory get used after a fact changes?

    A naive vector baseline is EXPECTED to retrieve the stale location A ahead
    of the current location B: A and B render to near-identical text and score
    the same cosine similarity, so the stable sort returns them in insertion
    order (A was learned first). The agent then navigates to A. That stale
    recall is the phenomenon this scenario measures — not a backend bug.
    """

    name: ClassVar[str] = "world_update"

    def __init__(self) -> None:
        self.location_a: Position | None = None
        self.location_b: Position | None = None
        self.run_log: RunLog | None = None

    async def setup(self, ctx: ScenarioContext) -> None:
        """Fix the stale (A) and current (B) cache locations, seeded."""

        spawn = (await ctx.bot.get_state()).position
        self.location_a = seeded_offset(spawn, random.Random(ctx.seed))
        self.location_b = seeded_offset(spawn, random.Random(ctx.seed + 100))
        assert (self.location_a.x, self.location_a.y, self.location_a.z) != (
            self.location_b.x,
            self.location_b.y,
            self.location_b.z,
        ), "seeded cache locations A and B must differ"

    async def experience_phase(self, ctx: ScenarioContext) -> None:
        """Store exactly one fact: the cache discovered at location A."""

        assert self.location_a is not None
        await ctx.memory.add(
            ExperienceEvent(
                event_id=new_event_id(),
                episode_id=ctx.episode_id,
                timestamp=datetime.now(UTC),
                actor="scenario-instructor",
                event_type=EventType.RESOURCE_DISCOVERED,
                context={
                    "subject": "supply_cache",
                    "x": self.location_a.x,
                    "y": self.location_a.y,
                    "z": self.location_a.z,
                },
            )
        )

    async def interference_phase(self, ctx: ScenarioContext) -> None:
        """The cache moves: a NEW current-fact event (B), plus noise and one action."""

        assert self.location_b is not None
        await ctx.memory.add(
            ExperienceEvent(
                event_id=new_event_id(),
                episode_id=ctx.episode_id,
                timestamp=datetime.now(UTC),
                actor="environment",
                event_type=EventType.WORLD_FACT_UPDATED,
                context={
                    "subject": "supply_cache",
                    "moved": True,
                    "x": self.location_b.x,
                    "y": self.location_b.y,
                    "z": self.location_b.z,
                },
            )
        )

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
        """Retrieve the cache using memory alone (no coordinates in the goal)."""

        assert self.location_b is not None
        self.run_log = await ctx.runner.run_goal(
            goal=GOAL, success_at=self.location_b, max_steps=3,
            episode_id=ctx.episode_id,
        )

    async def evaluate(self, ctx: ScenarioContext) -> ScenarioResult:
        """Measure belief updating, navigation, cost, and memory latency."""

        assert self.location_a is not None
        assert self.location_b is not None
        assert self.run_log is not None

        task_success = 1 if self.run_log.success else 0

        items = await ctx.memory.retrieve(
            MemoryQuery(query_text="supply cache location", episode_id=ctx.episode_id)
        )
        current_fact_accuracy: int | None = None
        if items:
            context = items[0].event.context
            if (context.get("x"), context.get("y"), context.get("z")) == (
                self.location_b.x,
                self.location_b.y,
                self.location_b.z,
            ):
                current_fact_accuracy = 1
            elif (context.get("x"), context.get("y"), context.get("z")) == (
                self.location_a.x,
                self.location_a.y,
                self.location_a.z,
            ):
                current_fact_accuracy = 0

        stale_action = 0
        for step in self.run_log.steps:
            if step.action == "move_to":
                destination = (
                    step.arguments["x"],
                    step.arguments["y"],
                    step.arguments["z"],
                )
                if math.dist(
                    destination,
                    (self.location_a.x, self.location_a.y, self.location_a.z),
                ) <= _BEELINE_RADIUS_BLOCKS:
                    stale_action = 1
                break

        last_pos = (
            self.run_log.steps[-1].position
            if self.run_log.steps
            else (await ctx.bot.get_state()).position
        )
        final_distance_to_b = math.dist(
            (last_pos.x, last_pos.y, last_pos.z),
            (self.location_b.x, self.location_b.y, self.location_b.z),
        )

        stats = await ctx.memory.stats()
        metrics: dict[str, float | int | str | None] = {
            "task_success": task_success,
            "current_fact_accuracy": current_fact_accuracy,
            "stale_action": stale_action,
            "final_distance_to_b": round(final_distance_to_b, 3),
            "llm_calls": self.run_log.llm_calls,
            "total_prompt_tokens": self.run_log.total_prompt_tokens,
            "total_completion_tokens": self.run_log.total_completion_tokens,
            "avg_add_latency_ms": stats.extra.get("avg_add_latency_ms"),
            "avg_retrieve_latency_ms": stats.extra.get("avg_retrieve_latency_ms"),
        }

        return ScenarioResult(
            scenario=self.name,
            episode_id=ctx.episode_id,
            seed=ctx.seed,
            memory_backend=stats.backend,
            success=task_success == 1,
            metrics=metrics,
            run_log=self.run_log,
        )
