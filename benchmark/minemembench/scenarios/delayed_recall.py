"""Scenario A — Delayed Fact Recall (M15B stress extension).

The agent learns one location fact (a virtual "target chest"), is flooded
with unrelated world facts and real bot actions, then must return to the
learned location using long-term memory alone — the test goal deliberately
contains no coordinates.

M15B difficulty parameters (defaults reproduce the original behavior exactly):
  - `interference_count` (default 10): how many unrelated noise facts are
    written between learning and testing. Levels: 10 / 50 / 200 / 500.
  - `similar_distractor_count` (default 0): how many SIMILAR facts about the
    same kind of target compete with the true fact (other colored chests,
    same-color objects, the target at wrong / stale locations). Levels:
    0 / 5 / 20 / 50. With distractors, retrieval precision and wrong-fact
    rate become measurable.

Phase-1 simplification: the chest is VIRTUAL. There is no block to open and
no item to collect; we measure navigation correctness to the remembered
location, not block interaction. The interference actions move the bot a few
blocks away from spawn, so reaching the target genuinely requires recalling
its coordinates from memory.

Seed usage: `random.Random(seed)` drives the target offset in `setup`;
`random.Random(seed + 1)` drives the interference actions and noise facts;
`random.Random(seed + 2)` drives the similar distractors — every phase
deterministic and phase-independent.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime
from typing import Any, ClassVar

from ..core.ids import new_event_id
from ..core.models import EventType, ExperienceEvent, Position
from ..core.runner import RunLog
from ..memory.base import MemoryItem
from .base import Scenario, ScenarioContext, ScenarioResult, run_retrieval_probe
from .offsets import seeded_offset

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

#: Colors / object kinds for the similar-fact distractors (M15B).
_COLORS = ("blue", "green", "gold", "silver", "black")
_OBJECTS = ("bed", "barrel", "boat", "furnace")


def _context_coords(context: dict[str, Any]) -> tuple[Any, Any, Any]:
    """The (x, y, z) triple in an event context, or all-None when absent."""

    return (context.get("x"), context.get("y"), context.get("z"))


def build_similar_distractors(
    target: Position, spawn: Position, rng: random.Random, count: int
) -> list[dict[str, Any]]:
    """Deterministic 'similar fact' distractors about the same kind of target.

    Each distractor is a plausible-but-wrong fact in the target's world,
    cycling through four kinds so a large count does not repeat itself:
      0: another chest (blue/green/...) at a seeded offset,
      1: another object in the target's color (red bed / red barrel),
      2: the target chest at the WRONG location,
      3: a stale 'used to be located here' target-chest location.
    """

    result: list[dict[str, Any]] = []
    for index in range(count):
        kind = index % 4
        offset = seeded_offset(spawn, rng)
        if kind == 0:
            result.append(
                {
                    "subject": f"{rng.choice(_COLORS)}_chest",
                    "x": offset.x,
                    "y": offset.y,
                    "z": offset.z,
                }
            )
        elif kind == 1:
            result.append(
                {
                    "subject": f"red_{rng.choice(_OBJECTS)}",
                    "x": offset.x,
                    "y": offset.y,
                    "z": offset.z,
                }
            )
        elif kind == 2:
            result.append(
                {
                    "subject": "target_chest",
                    "x": offset.x,
                    "y": offset.y,
                    "z": offset.z,
                    "note": "wrong location",
                }
            )
        else:
            result.append(
                {
                    "subject": "target_chest",
                    "x": offset.x,
                    "y": offset.y,
                    "z": offset.z,
                    "note": "used to be located here",
                }
            )
    return result


def compute_recall_metrics(
    items: list[MemoryItem], target: Position
) -> dict[str, float | int | None]:
    """Recall-side metrics of the delayed-recall stress.

    - `fact_retrieval_rank`: 1-based position of the first target-chest memory.
    - `recall_accuracy`: 1 when the CORRECT target fact is among the retrieved
      items, 0 when only wrong lookalikes are, None when nothing was retrieved.
    - `wrong_fact_rate`: fraction of retrieved items that are wrong facts about
      the target (target-chest memories at a location other than the true one).
    - `retrieval_precision`: fraction of retrieved items that are about the
      target fact at all (the correct fact or a wrong-location lookalike).
    """

    target_coords = (target.x, target.y, target.z)
    relevant = [
        item
        for item in items
        if item.event.context.get("subject") == "target_chest"
    ]
    wrong = [
        item for item in relevant if _context_coords(item.event.context) != target_coords
    ]
    correct_present = any(
        _context_coords(item.event.context) == target_coords for item in relevant
    )
    rank: int | None = None
    for index, item in enumerate(items):
        if item.event.context.get("subject") == "target_chest":
            rank = index + 1
            break
    if not items:
        return {
            "fact_retrieval_rank": None,
            "recall_accuracy": None,
            "wrong_fact_rate": None,
            "retrieval_precision": None,
        }
    return {
        "fact_retrieval_rank": rank,
        "recall_accuracy": 1 if correct_present else 0,
        "wrong_fact_rate": round(len(wrong) / len(items), 4),
        "retrieval_precision": round(len(relevant) / len(items), 4),
    }


class DelayedRecallScenario(Scenario):
    """Scenario A: learn a location, survive an interference flood, recall it."""

    name: ClassVar[str] = "delayed_recall"
    default_params: ClassVar[dict[str, Any]] = {
        "interference_count": 10,
        "similar_distractor_count": 0,
    }

    def __init__(self) -> None:
        self.target: Position | None = None
        self.spawn: Position | None = None
        self.run_log: RunLog | None = None

    def _validate_params(self) -> None:
        self._require_int_param("interference_count", 0)
        self._require_int_param("similar_distractor_count", 0)

    async def setup(self, ctx: ScenarioContext) -> None:
        """Fix the virtual target = bot spawn + seeded horizontal offset."""

        spawn = (await ctx.bot.get_state()).position
        self.spawn = spawn
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
        """Three real bot actions plus an interference flood in memory.

        The flood has `interference_count` unrelated world facts and
        `similar_distractor_count` similar facts about the same kind of target.
        At default parameters (10 noise, 0 distractors) this is byte-identical
        to the pre-stress behavior.
        """

        rng = random.Random(ctx.seed + 1)
        pos = (await ctx.bot.get_state()).position

        dx = rng.choice((-1, 1)) * rng.randint(1, 3)
        dz = rng.choice((-1, 1)) * rng.randint(1, 3)
        await ctx.bot.execute(
            "move_to", {"x": pos.x + dx, "y": pos.y, "z": pos.z + dz}
        )
        await ctx.bot.execute("chat", {"message": rng.choice(_FLAVOR_LINES)})
        await ctx.bot.execute("wait", {"seconds": 1})

        for _ in range(self.params["interference_count"]):
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

        distractor_count = self.params["similar_distractor_count"]
        if distractor_count:
            assert self.target is not None
            assert self.spawn is not None
            distractor_rng = random.Random(ctx.seed + 2)
            for context in build_similar_distractors(
                self.target, self.spawn, distractor_rng, distractor_count
            ):
                await ctx.memory.add(
                    ExperienceEvent(
                        event_id=new_event_id(),
                        episode_id=ctx.episode_id,
                        timestamp=datetime.now(UTC),
                        actor="environment",
                        event_type=EventType.WORLD_FACT_UPDATED,
                        context=context,
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

        items, probe = await run_retrieval_probe(
            ctx, phase="evaluate", query_text="target chest location"
        )
        recall = compute_recall_metrics(items, self.target)

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
            "fact_retrieval_rank": recall["fact_retrieval_rank"],
            "recall_accuracy": recall["recall_accuracy"],
            "wrong_fact_rate": recall["wrong_fact_rate"],
            "retrieval_precision": recall["retrieval_precision"],
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
            params=self.params,
            retrieval_probes=[probe],
        )
