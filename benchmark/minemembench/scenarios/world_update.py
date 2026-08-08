"""Scenario B — World State Update (belief updating, M15B stress extension).

The agent learns one resource fact (a virtual "supply cache" at location A),
is told mid-episode that the cache *moved* to new locations, then must
retrieve the cache using memory alone — the test goal deliberately contains no
coordinates.

M15B difficulty parameter (default reproduces the original A -> B exactly):
  - `update_depth` (default 1): the number of location updates chained before
    the test. Depth 1 is the classic A -> B; depth 3 chains A -> B -> C -> D,
    so the current location (the final answer) is D and every earlier location
    is a stale fact.

This scenario measures BELIEF UPDATING: each fact change is written as a NEW
event (a fresh event_id), not as an `update()` call on the old one, so both
the stale facts and the current fact coexist in memory. A correct
belief-updating backend should surface the current fact; a naive vector
baseline is EXPECTED to return a stale fact first on score ties (stable
insertion order) because the rendered texts are near-identical. That stale
recall is the phenomenon under study, not a bug.

M15B requires the raw retrieved items of every retrieval probe to be saved
into the run log: `evaluate()` records the probe that drives the retrieval
metrics in `result.retrieval_probes`.

Phase-1 simplification: the supply cache is VIRTUAL. There is no block to
open and no item to collect; we measure navigation correctness to the
CURRENT location rather than a stale one.

Seed usage: location k is drawn from `random.Random(seed + 100 * k)` so a
higher depth never perturbs shallower locations (depth 1 reproduces the
classic A/B exactly); `random.Random(seed + 1)` drives the interference
action and noise facts, keeping every phase deterministic and phase-independent.
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
from .delayed_recall import _NOISE_FACTS
from .offsets import seeded_offset  # re-exported for backward compatibility

#: Deliberately free of any coordinates: the current location must come from memory.
GOAL = "Retrieve the supply cache."

#: Distance (blocks) within which a first move counts as heading for a location.
_BEELINE_RADIUS_BLOCKS = 2.0


def build_update_chain(spawn: Position, seed: int, depth: int) -> list[Position]:
    """Return `depth + 1` distinct cache locations for an update chain.

    Index 0 is the initial location A; index `depth` is the current location
    (the final answer after `depth` updates). Location k is drawn from its own
    seeded RNG (`seed + 100 * k`), so depth 1 reproduces the classic A -> B
    exactly; collisions are resolved deterministically by bumping the seed.
    """

    locations: list[Position] = []
    for k in range(depth + 1):
        seed_k = seed + 100 * k
        candidate = seeded_offset(spawn, random.Random(seed_k))
        bump = 1
        while any(_same_xy(candidate, other) for other in locations) and bump < 1000:
            candidate = seeded_offset(spawn, random.Random(seed_k + 10_000 * bump))
            bump += 1
        locations.append(candidate)
    return locations


def _same_xy(a: Position, b: Position) -> bool:
    return (a.x, a.y, a.z) == (b.x, b.y, b.z)


def _context_coords(context: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (context.get("x"), context.get("y"), context.get("z"))


def compute_update_metrics(
    items: list[MemoryItem], current: Position, stale: list[Position]
) -> dict[str, float | int | None]:
    """Belief-updating metrics of the world_update stress.

    - `current_fact_accuracy`: 1 when the top retrieved cache fact is at the
      CURRENT location, 0 when it is at any stale location, None otherwise.
    - `stale_memory_rate`: fraction of the retrieved cache facts that are
      outdated (at a stale location). None when no cache fact was retrieved.
    - `obsolete_fact_retrieval_rate`: fraction of ALL retrieved items that are
      outdated cache facts. None when nothing was retrieved.
    """

    if not items:
        return {
            "current_fact_accuracy": None,
            "stale_memory_rate": None,
            "obsolete_fact_retrieval_rate": None,
        }

    current_coords = (current.x, current.y, current.z)
    stale_coords = {(p.x, p.y, p.z) for p in stale}

    cache_facts = [
        item for item in items if item.event.context.get("subject") == "supply_cache"
    ]
    stale_cache = [
        item for item in cache_facts if _context_coords(item.event.context) in stale_coords
    ]

    top_coords = _context_coords(items[0].event.context)
    if top_coords == current_coords:
        current_fact_accuracy: int | None = 1
    elif top_coords in stale_coords:
        current_fact_accuracy = 0
    else:
        current_fact_accuracy = None

    return {
        "current_fact_accuracy": current_fact_accuracy,
        "stale_memory_rate": (
            round(len(stale_cache) / len(cache_facts), 4) if cache_facts else None
        ),
        "obsolete_fact_retrieval_rate": round(len(stale_cache) / len(items), 4),
    }


class WorldUpdateScenario(Scenario):
    """Scenario B: does stale memory get used after a fact changes?

    A naive vector baseline is EXPECTED to retrieve a stale location ahead of
    the current location: they render to near-identical text and score the
    same cosine similarity, so the stable sort returns them in insertion order
    (the initial location was learned first). That stale recall is the
    phenomenon this scenario measures — not a backend bug.
    """

    name: ClassVar[str] = "world_update"
    default_params: ClassVar[dict[str, Any]] = {"update_depth": 1}

    def __init__(self) -> None:
        self.locations: list[Position] = []
        self.run_log: RunLog | None = None

    def _validate_params(self) -> None:
        self._require_int_param("update_depth", 1)

    async def setup(self, ctx: ScenarioContext) -> None:
        """Fix the stale (earlier) and current cache locations, seeded."""

        spawn = (await ctx.bot.get_state()).position
        self.locations = build_update_chain(spawn, ctx.seed, self.params["update_depth"])

    async def experience_phase(self, ctx: ScenarioContext) -> None:
        """Store exactly one fact: the cache discovered at location A."""

        location_a = self.locations[0]
        await ctx.memory.add(
            ExperienceEvent(
                event_id=new_event_id(),
                episode_id=ctx.episode_id,
                timestamp=datetime.now(UTC),
                actor="scenario-instructor",
                event_type=EventType.RESOURCE_DISCOVERED,
                context={
                    "subject": "supply_cache",
                    "x": location_a.x,
                    "y": location_a.y,
                    "z": location_a.z,
                },
            )
        )

    async def interference_phase(self, ctx: ScenarioContext) -> None:
        """The cache moves: `update_depth` NEW current-fact events, plus noise/action."""

        for location in self.locations[1:]:
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
                        "x": location.x,
                        "y": location.y,
                        "z": location.z,
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

        current = self.locations[-1]
        self.run_log = await ctx.runner.run_goal(
            goal=GOAL, success_at=current, max_steps=3,
            episode_id=ctx.episode_id,
        )

    async def evaluate(self, ctx: ScenarioContext) -> ScenarioResult:
        """Measure belief updating, navigation, cost, and memory latency.

        The raw retrieved items of the retrieval probe are saved into
        `result.retrieval_probes` (M15B requirement).
        """

        assert self.locations
        assert self.run_log is not None

        task_success = 1 if self.run_log.success else 0
        current = self.locations[-1]
        stale = self.locations[:-1]

        items, probe = await run_retrieval_probe(
            ctx, phase="evaluate", query_text="supply cache location"
        )
        update = compute_update_metrics(items, current, stale)

        stale_action = 0
        for step in self.run_log.steps:
            if step.action == "move_to":
                destination = (
                    step.arguments["x"],
                    step.arguments["y"],
                    step.arguments["z"],
                )
                if any(
                    math.dist(
                        destination,
                        (position.x, position.y, position.z),
                    )
                    <= _BEELINE_RADIUS_BLOCKS
                    for position in stale
                ):
                    stale_action = 1
                break

        last_pos = (
            self.run_log.steps[-1].position
            if self.run_log.steps
            else (await ctx.bot.get_state()).position
        )
        final_distance_to_b = math.dist(
            (last_pos.x, last_pos.y, last_pos.z),
            (current.x, current.y, current.z),
        )

        stats = await ctx.memory.stats()
        metrics: dict[str, float | int | str | None] = {
            "task_success": task_success,
            "current_fact_accuracy": update["current_fact_accuracy"],
            "stale_memory_rate": update["stale_memory_rate"],
            "obsolete_fact_retrieval_rate": update["obsolete_fact_retrieval_rate"],
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
            params=self.params,
            retrieval_probes=[probe],
        )
