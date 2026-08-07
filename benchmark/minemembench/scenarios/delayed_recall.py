"""Scenario A — Delayed Fact Recall.

The agent learns one location fact (a virtual "target chest"), is flooded
with ten unrelated world facts and three real bot actions, then must return
to the learned location using long-term memory alone — the test goal
deliberately contains no coordinates.

Phase-1 simplification: the chest is VIRTUAL. There is no block to open and
no item to collect; we measure navigation correctness to the remembered
location, not block interaction. The interference actions move the bot a few
blocks away from spawn, so reaching the target genuinely requires recalling
its coordinates from memory.

Seed usage: `random.Random(seed)` drives the target offset in `setup`;
`random.Random(seed + 1)` drives the interference actions and noise facts,
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

#: Deliberately free of any coordinates: recall must come from memory.
GOAL = "Return to the target chest you learned about at the start of this episode."

#: Seeded flavor lines for the interference chat action.
_FLAVOR_LINES = (
    "Ah, what a lovely day for a stroll.",
    "I wonder what the villagers are up to.",
    "The river sounds nice this time of year.",
)

#: Seeded, plausible-but-unrelated world facts (weather / mob sightings /
#: crop growth). Deliberately terse and free of the test goal's high-frequency
#: tokens ("the", "at", "to", ...): under the crude hash embedder any shared
#: stopword inflates a noise event's similarity and can crowd out the chest
#: fact. None mention the chest or any coordinates, so a backend that cannot
#: recall the chest fact has nothing to fall back on.
_NOISE_FACTS = (
    "rain",
    "thunderstorm",
    "fog",
    "clear sky",
    "warm breeze",
    "hail",
    "wolves howling",
    "sheep grazing",
    "spider in cave",
    "endermen wandering forest",
    "pigs rooting",
    "creeper nearby",
    "zombie groaning",
    "wheat tall",
    "carrots harvested",
    "pumpkins growing",
    "potatoes ripe",
    "melons spread",
)


class DelayedRecallScenario(Scenario):
    """Scenario A: learn a location, survive an interference flood, recall it."""

    name: ClassVar[str] = "delayed_recall"

    def __init__(self) -> None:
        self.target: Position | None = None
        self.run_log: RunLog | None = None

    async def setup(self, ctx: ScenarioContext) -> None:
        """Fix the virtual target = bot spawn + seeded horizontal offset."""

        spawn = (await ctx.bot.get_state()).position
        rng = random.Random(ctx.seed)
        dx = rng.choice((-1, 1)) * rng.randint(8, 20)
        dz = rng.choice((-1, 1)) * rng.randint(8, 20)
        self.target = Position(x=spawn.x + dx, y=spawn.y, z=spawn.z + dz)

    async def experience_phase(self, ctx: ScenarioContext) -> None:
        """Store exactly one fact: the target chest's coordinates."""

        assert self.target is not None
        event = ExperienceEvent(
            event_id=new_event_id(),
            episode_id=ctx.episode_id,
            timestamp=datetime.now(UTC),
            actor="scenario-instructor",
            event_type=EventType.LOCATION_DISCOVERED,
            context={
                "subject": "target_chest",
                "x": self.target.x,
                "y": self.target.y,
                "z": self.target.z,
            },
        )
        await ctx.memory.add(event)

    async def interference_phase(self, ctx: ScenarioContext) -> None:
        """Three real bot actions plus ten unrelated world-fact memories."""

        rng = random.Random(ctx.seed + 1)
        pos = (await ctx.bot.get_state()).position

        dx = rng.choice((-1, 1)) * rng.randint(1, 3)
        dz = rng.choice((-1, 1)) * rng.randint(1, 3)
        await ctx.bot.execute(
            "move_to", {"x": pos.x + dx, "y": pos.y, "z": pos.z + dz}
        )
        await ctx.bot.execute("chat", {"message": rng.choice(_FLAVOR_LINES)})
        await ctx.bot.execute("wait", {"seconds": 1})

        for _ in range(10):
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
        """Return to the chest using memory alone (no coordinates in the goal)."""

        assert self.target is not None
        self.run_log = await ctx.runner.run_goal(
            goal=GOAL, success_at=self.target, max_steps=3,
            episode_id=ctx.episode_id,
        )

    async def evaluate(self, ctx: ScenarioContext) -> ScenarioResult:
        """Measure recall, navigation, cost, and memory latency."""

        assert self.target is not None
        assert self.run_log is not None

        task_success = 1 if self.run_log.success else 0

        items = await ctx.memory.retrieve(
            MemoryQuery(query_text="target chest location", episode_id=ctx.episode_id)
        )
        fact_retrieval_rank: int | None = None
        for index, item in enumerate(items):
            if item.event.context.get("subject") == "target_chest":
                fact_retrieval_rank = index + 1
                break

        last_pos = (
            self.run_log.steps[-1].position
            if self.run_log.steps
            else (await ctx.bot.get_state()).position
        )
        final_distance = math.dist(
            (last_pos.x, last_pos.y, last_pos.z),
            (self.target.x, self.target.y, self.target.z),
        )

        stats = await ctx.memory.stats()
        metrics: dict[str, float | int | str | None] = {
            "task_success": task_success,
            "fact_retrieval_rank": fact_retrieval_rank,
            "final_distance_to_target": round(final_distance, 3),
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
