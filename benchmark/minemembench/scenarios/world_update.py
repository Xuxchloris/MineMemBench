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

Semantics v2 (TASK-013, `update_semantics_version="temporal_chain_v2"`): the
same supply cache changes location over semantic time. Every chain candidate
(A..D) shares one neutral actor (`scenario-instructor`), one event type
(`WORLD_FACT_UPDATED`, including A), and one context schema
(`{"subject": "supply_cache", "x", "y", "z"}`) — no `moved` flags, update
indices, or initial/current/stale/latest labels. All assertions are true at
their event time; the unique maximum semantic timestamp defines the current
location D. The v2 goal is static and coordinate-free: "Retrieve the supply
cache at its current location." Headline v2 metrics are computed from the
typed out-of-band `evaluation_ground_truth` plus the causal step-0 retrieval
snapshot — never a second probe. Controlled mode fails closed for any other
semantics version; legacy native behavior/metrics are unchanged and old
result JSON stays loadable.
"""

from __future__ import annotations

import math
import random
from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from typing import Any, ClassVar

from ..core.fairness import CAMPAIGN_MODE_CONTROLLED
from ..core.ids import new_event_id
from ..core.models import EventType, ExperienceEvent, Position
from ..core.runner import RunLog
from ..memory.base import MemoryItem, MemoryItemSnapshot
from .base import (
    Scenario,
    ScenarioContext,
    ScenarioParamError,
    ScenarioResult,
    TemporalChainGroundTruth,
    run_retrieval_probe,
)
from .controlled import controlled_event_identity
from .delayed_recall import _NOISE_FACTS
from .offsets import seeded_offset  # re-exported for backward compatibility

#: Deliberately free of any coordinates: the current location must come from memory.
GOAL = "Retrieve the supply cache."

#: v2 goal (TASK-013): static, coordinate-free, no correctness labels.
GOAL_TEMPORAL_CHAIN_V2 = "Retrieve the supply cache at its current location."

#: Accepted values of the `update_semantics_version` parameter (TASK-013).
SEMANTICS_LEGACY = "legacy"
SEMANTICS_TEMPORAL_CHAIN_V2 = "temporal_chain_v2"

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


def compute_temporal_chain_metrics(
    items: Sequence[MemoryItem | MemoryItemSnapshot],
    current_event_id: str,
    stale_event_ids: Collection[str],
) -> dict[str, float | int | None]:
    """v2 (temporal_chain_v2) retrieval metrics, by stable event id (TASK-013).

    Every chain fact is true at its event time; "stale" means temporally
    superseded, never wrong. Ground truth is the out-of-band typed
    `evaluation_ground_truth`; inputs are the causal step-0 retrieval
    snapshot, never a second probe.

    - `current_fact_retrieval_rank`: 1-based position of the current event
      (D); None when absent.
    - `current_fact_recall`: 1 when D is retrieved, else 0 — empty retrieval
      is a measured miss, not N/A.
    - `current_fact_retrieval_precision`: D items / all retrieved; None on
      empty retrieval.
    - `stale_fact_retrieval_rate`: known A/B/C items / all retrieved; None on
      empty retrieval.
    - `current_fact_top1`: 1 when the top item is D, 0 when it is A/B/C,
      None otherwise.
    - `stale_memory_rate`: A/B/C items / all retrieved CHAIN facts; None when
      no chain fact was retrieved.
    """

    if not items:
        return {
            "current_fact_retrieval_rank": None,
            "current_fact_recall": 0,
            "current_fact_retrieval_precision": None,
            "stale_fact_retrieval_rate": None,
            "current_fact_top1": None,
            "stale_memory_rate": None,
        }

    stale_ids = set(stale_event_ids)
    retrieved_ids = [item.event.event_id for item in items]
    current_count = sum(1 for event_id in retrieved_ids if event_id == current_event_id)
    stale_count = sum(1 for event_id in retrieved_ids if event_id in stale_ids)
    chain_count = current_count + stale_count

    rank: int | None = None
    for index, event_id in enumerate(retrieved_ids):
        if event_id == current_event_id:
            rank = index + 1
            break

    top1: int | None = None
    if retrieved_ids[0] == current_event_id:
        top1 = 1
    elif retrieved_ids[0] in stale_ids:
        top1 = 0

    return {
        "current_fact_retrieval_rank": rank,
        "current_fact_recall": 1 if current_count else 0,
        "current_fact_retrieval_precision": round(current_count / len(items), 4),
        "stale_fact_retrieval_rate": round(stale_count / len(items), 4),
        "current_fact_top1": top1,
        "stale_memory_rate": (
            round(stale_count / chain_count, 4) if chain_count else None
        ),
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
    default_params: ClassVar[dict[str, Any]] = {
        "update_depth": 1,
        # TASK-013: "legacy" (default; native behavior/metrics unchanged) or
        # "temporal_chain_v2" (neutral temporal-chain treatment). Controlled
        # mode fails closed unless the value is "temporal_chain_v2".
        "update_semantics_version": SEMANTICS_LEGACY,
    }

    def __init__(self) -> None:
        self.locations: list[Position] = []
        self.run_log: RunLog | None = None
        #: v2: the ordered chain event ids (A..D) — out-of-band ground truth.
        self.chain_event_ids: list[str] = []
        #: Controlled Mode: per-phase ordinal counters for deterministic
        #: event identity (native runs ignore this).
        self._controlled_ordinals: dict[str, int] = {}

    def _is_v2(self) -> bool:
        return self.params["update_semantics_version"] == SEMANTICS_TEMPORAL_CHAIN_V2

    def _goal(self) -> str:
        return GOAL_TEMPORAL_CHAIN_V2 if self._is_v2() else GOAL

    def _next_event_identity(
        self, ctx: ScenarioContext, phase: str
    ) -> tuple[str, datetime]:
        """(event_id, timestamp) for a scenario-generated event.

        Controlled (v2-only, per the mode gate) derives both from (seed, full
        effective params, phase, ordinal) so the offered stream is identical
        across backends; native keeps uuid4 ids and wall-clock timestamps.
        """

        if ctx.campaign_mode != CAMPAIGN_MODE_CONTROLLED:
            return new_event_id(), datetime.now(UTC)
        ordinal = self._controlled_ordinals.get(phase, 0)
        self._controlled_ordinals[phase] = ordinal + 1
        return controlled_event_identity(
            seed=ctx.seed, params=self.params, phase=phase, ordinal=ordinal
        )

    def _validate_params(self) -> None:
        self._require_int_param("update_depth", 1)
        version = self._params["update_semantics_version"]
        if version not in (SEMANTICS_LEGACY, SEMANTICS_TEMPORAL_CHAIN_V2):
            raise ScenarioParamError(
                f"{self.name}: parameter 'update_semantics_version' must be "
                f"{SEMANTICS_LEGACY!r} or {SEMANTICS_TEMPORAL_CHAIN_V2!r}, "
                f"got {version!r}"
            )

    async def setup(self, ctx: ScenarioContext) -> None:
        """Fix the stale (earlier) and current cache locations, seeded.

        Fail closed: a Controlled run may only ever use the v2 treatment —
        legacy Controlled world-update is research-invalid (A-FINAL-012) and
        must never be produced.
        """

        if ctx.campaign_mode == CAMPAIGN_MODE_CONTROLLED and not self._is_v2():
            raise ScenarioParamError(
                f"{self.name}: Controlled mode requires "
                f"update_semantics_version={SEMANTICS_TEMPORAL_CHAIN_V2!r}, "
                f"got {self.params['update_semantics_version']!r}"
            )
        spawn = (await ctx.bot.get_state()).position
        self.locations = build_update_chain(spawn, ctx.seed, self.params["update_depth"])

    async def experience_phase(self, ctx: ScenarioContext) -> None:
        """Store exactly one fact: the cache discovered at location A.

        v2 (TASK-013): A shares the chain's common schema — actor
        `scenario-instructor`, type `WORLD_FACT_UPDATED`, context
        `{"subject", "x", "y", "z"}` — so only coordinates, event id and
        semantic timestamp differ across the chain.
        """

        location_a = self.locations[0]
        if self._is_v2():
            event_id, timestamp = self._next_event_identity(ctx, "experience")
            event = ExperienceEvent(
                event_id=event_id,
                episode_id=ctx.episode_id,
                timestamp=timestamp,
                actor="scenario-instructor",
                event_type=EventType.WORLD_FACT_UPDATED,
                context={
                    "subject": "supply_cache",
                    "x": location_a.x,
                    "y": location_a.y,
                    "z": location_a.z,
                },
            )
            await ctx.memory.add(event)
            self.chain_event_ids = [event.event_id]
            return
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
        """The cache moves: `update_depth` NEW current-fact events, plus noise/action.

        v2 (TASK-013): B/C/D use A's exact schema with strictly increasing
        semantic timestamps and no `moved` flag or update/stale labels.
        """

        if self._is_v2():
            for location in self.locations[1:]:
                event_id, timestamp = self._next_event_identity(ctx, "interference")
                event = ExperienceEvent(
                    event_id=event_id,
                    episode_id=ctx.episode_id,
                    timestamp=timestamp,
                    actor="scenario-instructor",
                    event_type=EventType.WORLD_FACT_UPDATED,
                    context={
                        "subject": "supply_cache",
                        "x": location.x,
                        "y": location.y,
                        "z": location.z,
                    },
                )
                await ctx.memory.add(event)
                self.chain_event_ids.append(event.event_id)
        else:
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
            if self._is_v2():
                event_id, timestamp = self._next_event_identity(ctx, "interference")
            else:
                event_id, timestamp = new_event_id(), datetime.now(UTC)
            await ctx.memory.add(
                ExperienceEvent(
                    event_id=event_id,
                    episode_id=ctx.episode_id,
                    timestamp=timestamp,
                    actor="environment",
                    event_type=EventType.WORLD_FACT_UPDATED,
                    context={"subject": "world", "fact": rng.choice(_NOISE_FACTS)},
                )
            )

    async def test_phase(self, ctx: ScenarioContext) -> None:
        """Retrieve the cache using memory alone (no coordinates in the goal)."""

        current = self.locations[-1]
        self.run_log = await ctx.runner.run_goal(
            goal=self._goal(), success_at=current, max_steps=3,
            episode_id=ctx.episode_id,
        )

    async def evaluate(self, ctx: ScenarioContext) -> ScenarioResult:
        """Measure belief updating, navigation, cost, and memory latency.

        Legacy: retrieval metrics come from the evaluation-time probe, saved
        into `result.retrieval_probes` (M15B requirement) — unchanged.
        v2 (TASK-013): headline metrics come from the typed out-of-band
        ground truth plus the CAUSAL step-0 retrieval snapshot; the
        evaluation-time probe (queried with the v2 goal) is diagnostic raw
        evidence only and feeds no metric.
        """

        assert self.locations
        assert self.run_log is not None

        task_success = 1 if self.run_log.success else 0
        current = self.locations[-1]
        stale = self.locations[:-1]

        if self._is_v2():
            return await self._evaluate_v2(ctx, task_success, current, stale)
        return await self._evaluate_legacy(ctx, task_success, current, stale)

    async def _evaluate_legacy(
        self,
        ctx: ScenarioContext,
        task_success: int,
        current: Position,
        stale: list[Position],
    ) -> ScenarioResult:
        """The pre-TASK-013 evaluation path, unchanged."""

        assert self.run_log is not None
        items, probe = await run_retrieval_probe(
            ctx, phase="evaluate", query_text="supply cache location"
        )
        update = compute_update_metrics(items, current, stale)

        stale_action = self._stale_action(stale)
        final_distance = await self._final_distance(ctx, current)

        stats = await ctx.memory.stats()
        metrics: dict[str, float | int | str | None] = {
            "task_success": task_success,
            "current_fact_accuracy": update["current_fact_accuracy"],
            "stale_memory_rate": update["stale_memory_rate"],
            "obsolete_fact_retrieval_rate": update["obsolete_fact_retrieval_rate"],
            "stale_action": stale_action,
            "final_distance_to_b": round(final_distance, 3),
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

    async def _evaluate_v2(
        self,
        ctx: ScenarioContext,
        task_success: int,
        current: Position,
        stale: list[Position],
    ) -> ScenarioResult:
        """Causal v2 evaluation: typed ground truth + step-0 snapshot."""

        assert self.run_log is not None
        assert self.chain_event_ids

        first_step_items = (
            self.run_log.steps[0].retrieved_items if self.run_log.steps else []
        )
        ground_truth = TemporalChainGroundTruth(
            semantics_version=SEMANTICS_TEMPORAL_CHAIN_V2,
            entity_key="supply_cache",
            stale_event_ids=list(self.chain_event_ids[:-1]),
            current_event_id=self.chain_event_ids[-1],
        )
        chain = compute_temporal_chain_metrics(
            first_step_items,
            ground_truth.current_event_id,
            ground_truth.stale_event_ids,
        )

        _diagnostic_items, diagnostic_probe = await run_retrieval_probe(
            ctx, phase="evaluate-diagnostic", query_text=self._goal()
        )

        stale_action = self._stale_action(stale)
        final_distance = await self._final_distance(ctx, current)

        stats = await ctx.memory.stats()
        metrics: dict[str, float | int | str | None] = {
            "task_success": task_success,
            "current_fact_retrieval_rank": chain["current_fact_retrieval_rank"],
            "current_fact_recall": chain["current_fact_recall"],
            "current_fact_retrieval_precision": chain[
                "current_fact_retrieval_precision"
            ],
            "stale_fact_retrieval_rate": chain["stale_fact_retrieval_rate"],
            "current_fact_top1": chain["current_fact_top1"],
            "stale_memory_rate": chain["stale_memory_rate"],
            # Compatibility mirrors of the versioned v2 metrics.
            "current_fact_accuracy": chain["current_fact_top1"],
            "obsolete_fact_retrieval_rate": chain["stale_fact_retrieval_rate"],
            "retrieval_evidence_source": "run_log.steps[0].retrieved_items",
            "stale_action": stale_action,
            "final_distance_to_current": round(final_distance, 3),
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
            retrieval_probes=[diagnostic_probe],
            evaluation_ground_truth=ground_truth,
        )

    def _stale_action(self, stale: list[Position]) -> int:
        """1 when the first move_to heads for any stale (A/B/C) location."""

        assert self.run_log is not None
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
                    return 1
                break
        return 0

    async def _final_distance(
        self, ctx: ScenarioContext, current: Position
    ) -> float:
        """Distance from the run's final position to the current location."""

        assert self.run_log is not None
        last_pos = (
            self.run_log.steps[-1].position
            if self.run_log.steps
            else (await ctx.bot.get_state()).position
        )
        return math.dist(
            (last_pos.x, last_pos.y, last_pos.z),
            (current.x, current.y, current.z),
        )
