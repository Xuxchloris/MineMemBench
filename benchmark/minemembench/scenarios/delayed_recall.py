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

Measurement validity (TASK-002): the headline retrieval metrics
(`fact_retrieval_rank`, `recall_accuracy`, `wrong_fact_rate`,
`retrieval_precision`) are computed from the EXACT retrieval that caused the
first planner decision (`run_log.steps[0].retrieved_items`), identified by
stable event ids — the learned fact's id and the ids of the known wrong
lookalikes — never from backend-specific context parsing or a second
evaluation-time retrieval. An empty first-step retrieval is a measured miss
(`recall_accuracy = 0`); rates that are undefined without retrieved items are
N/A. The evaluation-time retrieval probe is preserved in
`result.retrieval_probes` as diagnostic raw evidence (phase
`evaluate-diagnostic`) and feeds no metric.

Controlled Mode (TASK-004): when `ctx.campaign_mode == "controlled"`, every
generated event gets a deterministic id and logical timestamp derived from
(seed, effective params, phase, ordinal) — actor/type/context/outcome and
event order are then identical across backends for the same (seed, params),
and only the isolation `episode_id` differs. Native mode is unchanged
(uuid4 ids, wall-clock timestamps).

Controlled Mode distractor neutrality (TASK-007): competing target-location
distractors carry the learned fact's exact actor, event type, and context key
set with unlabeled wording — no "wrong location" / "used to be located here"
notes — so the planner cannot reject them by hand-authored labels. They
differ only in coordinates and retrieval order; their ids remain out-of-band
metric ground truth (`wrong_fact_ids`), never prompt content.

Semantics v2 (TASK-011, `recall_semantics_version="entity_key_v2"`): the
learned fact maps one opaque, seeded, fixed-width entity key (e.g.
`cache-7f3a9c2e`) to the target location, and every similar distractor maps
a UNIQUE one-character mutation of that key to its OWN unique location — all
facts are simultaneously true, so correctness is the entity-key association,
never timestamp, insertion order, or update semantics. All candidates share
one neutral actor/type/context schema (`{"entity_key", "x", "y", "z"}`); the
goal names the target key and no coordinates. v2 metrics
(`target_recall`, `target_retrieval_precision`, `off_target_retrieval_rate`,
`fact_retrieval_rank`) are computed from the typed out-of-band
`evaluation_ground_truth` plus the causal step-0 retrieval snapshot; legacy
keys are kept for schema compatibility with `wrong_fact_rate` and legacy
`retrieval_precision` reported as N/A (true off-target entities are never
called "wrong"). Legacy remains the default: its goal text, event semantics,
metrics, and Controlled event-identity derivation (the two pre-existing
difficulty params) are unchanged, and old result JSON stays loadable; newly
serialized results additionally carry the explicit version in `params` and
the optional ground-truth field as `null`, so the whole result JSON is not
claimed byte-for-byte identical.
"""

from __future__ import annotations

import hashlib
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
    EntityKeyGroundTruth,
    Scenario,
    ScenarioContext,
    ScenarioParamError,
    ScenarioResult,
    run_retrieval_probe,
)
from .controlled import controlled_event_identity
from .offsets import seeded_offset

#: Deliberately free of any coordinates: recall must come from memory.
GOAL = "Return to the target chest you learned about at the start of this episode."

#: Accepted values of the `recall_semantics_version` parameter (TASK-011).
SEMANTICS_LEGACY = "legacy"
SEMANTICS_ENTITY_KEY_V2 = "entity_key_v2"

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


def target_entity_key(seed: int) -> str:
    """The v2 target key: opaque, fixed-width, derived from the scenario seed
    in a DEDICATED namespace — before and independently of any distractor
    generation, count, or order (TASK-011 P3)."""

    digest = hashlib.sha256(
        f"delayed_recall/entity_key_v2/target/{seed}".encode("utf-8")
    ).hexdigest()
    return f"cache-{digest[:8]}"


def distractor_entity_keys(target_key: str, count: int) -> list[str]:
    """`count` unique one-character mutations of `target_key`, deterministic.

    Position-major over the hex suffix, replacement characters in hex order
    (skipping the original), so the first N keys are identical for every N
    (generation is independent of the requested count). Fixed width; every
    key differs from the target key in exactly one character.
    """

    prefix, suffix = target_key.split("-", 1)
    keys: list[str] = []
    for position in range(len(suffix)):
        for replacement in "0123456789abcdef":
            if replacement == suffix[position]:
                continue
            candidate = suffix[:position] + replacement + suffix[position + 1:]
            keys.append(f"{prefix}-{candidate}")
            if len(keys) == count:
                return keys
    raise ValueError(f"cannot build {count} unique mutations of {target_key!r}")


def distractor_positions(
    spawn: Position, target: Position, rng: random.Random, count: int
) -> list[Position]:
    """`count` unique seeded offsets, none equal to the target or each other."""

    positions: list[Position] = []
    seen = {(target.x, target.y, target.z)}
    while len(positions) < count:
        candidate = seeded_offset(spawn, rng)
        key = (candidate.x, candidate.y, candidate.z)
        if key in seen:
            continue
        seen.add(key)
        positions.append(candidate)
    return positions


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
    items: Sequence[MemoryItem | MemoryItemSnapshot],
    target_event_id: str,
    wrong_fact_ids: Collection[str],
) -> dict[str, float | int | None]:
    """Recall-side metrics of the delayed-recall stress, by stable event id.

    Ground truth is identity, never backend-specific text/context parsing: the
    correct fact is the event with `target_event_id`; the known wrong
    lookalikes (the target at wrong / stale locations) are `wrong_fact_ids`.
    Ids survive even when a backend reconstructs only a text-shaped event, so
    the same math applies to exact and lossy reconstructions.

    - `fact_retrieval_rank`: 1-based position of the CORRECT fact
      (`target_event_id`) itself; None when the correct fact is absent. A
      wrong lookalike outranking the correct fact must never hide that.
    - `recall_accuracy`: 1 when the CORRECT target fact is among the retrieved
      items, 0 otherwise — an empty retrieval is a measured miss, not N/A.
    - `wrong_fact_rate`: fraction of retrieved items that are known wrong
      facts about the target; None (N/A) when nothing was retrieved.
    - `retrieval_precision`: fraction of retrieved items that are about the
      target at all; None (N/A) when nothing was retrieved.
    """

    if not items:
        return {
            "fact_retrieval_rank": None,
            "recall_accuracy": 0,
            "wrong_fact_rate": None,
            "retrieval_precision": None,
        }

    relevant_ids = {target_event_id, *wrong_fact_ids}
    retrieved_ids = [item.event.event_id for item in items]
    relevant = sum(1 for event_id in retrieved_ids if event_id in relevant_ids)
    wrong = sum(1 for event_id in retrieved_ids if event_id in wrong_fact_ids)
    rank: int | None = None
    for index, event_id in enumerate(retrieved_ids):
        if event_id == target_event_id:
            rank = index + 1
            break
    return {
        "fact_retrieval_rank": rank,
        "recall_accuracy": 1 if target_event_id in retrieved_ids else 0,
        "wrong_fact_rate": round(wrong / len(items), 4),
        "retrieval_precision": round(relevant / len(items), 4),
    }


def compute_entity_key_metrics(
    items: Sequence[MemoryItem | MemoryItemSnapshot],
    target_event_id: str,
    distractor_event_ids: Collection[str],
) -> dict[str, float | int | None]:
    """v2 (entity_key_v2) retrieval metrics, by stable event id (TASK-011).

    Every candidate fact is simultaneously TRUE, so nothing here is a "wrong
    fact": distractor items are merely OFF-TARGET (they name other entity
    keys). Ground truth is the out-of-band `evaluation_ground_truth` ids,
    never prompt-visible content.

    - `fact_retrieval_rank`: 1-based position of the target event itself;
      None when the target is absent.
    - `target_recall`: 1 when the target is among the retrieved items,
      0 otherwise — an empty retrieval is a measured miss, not N/A.
    - `target_retrieval_precision`: target items / retrieved items;
      None (N/A) on empty retrieval.
    - `off_target_retrieval_rate`: known distractor items / retrieved items;
      None (N/A) on empty retrieval.
    """

    if not items:
        return {
            "fact_retrieval_rank": None,
            "target_recall": 0,
            "target_retrieval_precision": None,
            "off_target_retrieval_rate": None,
        }

    distractor_ids = set(distractor_event_ids)
    retrieved_ids = [item.event.event_id for item in items]
    target_count = sum(1 for event_id in retrieved_ids if event_id == target_event_id)
    off_target = sum(1 for event_id in retrieved_ids if event_id in distractor_ids)
    rank: int | None = None
    for index, event_id in enumerate(retrieved_ids):
        if event_id == target_event_id:
            rank = index + 1
            break
    return {
        "fact_retrieval_rank": rank,
        "target_recall": 1 if target_count else 0,
        "target_retrieval_precision": round(target_count / len(items), 4),
        "off_target_retrieval_rate": round(off_target / len(items), 4),
    }


class DelayedRecallScenario(Scenario):
    """Scenario A: learn a location, survive an interference flood, recall it."""

    name: ClassVar[str] = "delayed_recall"
    default_params: ClassVar[dict[str, Any]] = {
        "interference_count": 10,
        "similar_distractor_count": 0,
        # TASK-011: "legacy" (default; goal, event semantics, metrics, and
        # Controlled event identity unchanged) or "entity_key_v2" (the
        # simultaneously-true entity-key lookup treatment).
        "recall_semantics_version": SEMANTICS_LEGACY,
    }

    def __init__(self) -> None:
        self.target: Position | None = None
        self.spawn: Position | None = None
        self.run_log: RunLog | None = None
        #: Id-based ground truth: the correct fact's event id and the ids of
        #: the known wrong lookalikes (target at wrong / stale locations).
        self.target_event_id: str | None = None
        self.wrong_fact_ids: set[str] = set()
        #: v2 (entity_key_v2): the opaque target key and the ORDERED
        #: distractor event ids — out-of-band evaluation ground truth.
        self.target_entity_key: str | None = None
        self.distractor_event_ids: list[str] = []
        #: Controlled Mode: per-phase ordinal counters for deterministic
        #: event identity (native runs ignore this).
        self._controlled_ordinals: dict[str, int] = {}

    def _is_v2(self) -> bool:
        return self.params["recall_semantics_version"] == SEMANTICS_ENTITY_KEY_V2

    def _goal(self) -> str:
        """The run's goal: the static legacy text, or the v2 key naming text.

        The v2 goal names exactly the target entity key and no coordinates;
        it contains no correctness/priority label.
        """

        if self._is_v2():
            assert self.target_entity_key is not None
            return (
                f"Return to {self.target_entity_key} whose location you "
                f"learned during the initial briefing."
            )
        return GOAL

    def _next_event_identity(
        self, ctx: ScenarioContext, phase: str
    ) -> tuple[str, datetime]:
        """(event_id, timestamp) for a scenario-generated event.

        Controlled Mode derives both from (seed, effective params, phase,
        ordinal) so the event stream is semantically identical across
        backends; native mode keeps uuid4 ids and wall-clock timestamps.

        Identity namespace (A-REVIEW-011 H-1): `legacy` hashes ONLY the two
        pre-existing difficulty params (`interference_count`,
        `similar_distractor_count`), preserving the exact pre-TASK-011
        derivation; `entity_key_v2` hashes the full versioned params.
        """

        if ctx.campaign_mode != CAMPAIGN_MODE_CONTROLLED:
            return new_event_id(), datetime.now(UTC)
        ordinal = self._controlled_ordinals.get(phase, 0)
        self._controlled_ordinals[phase] = ordinal + 1
        if self._is_v2():
            params = self.params
        else:
            params = {
                "interference_count": self.params["interference_count"],
                "similar_distractor_count": self.params["similar_distractor_count"],
            }
        return controlled_event_identity(
            seed=ctx.seed, params=params, phase=phase, ordinal=ordinal
        )

    def _validate_params(self) -> None:
        self._require_int_param("interference_count", 0)
        self._require_int_param("similar_distractor_count", 0)
        version = self._params["recall_semantics_version"]
        if version not in (SEMANTICS_LEGACY, SEMANTICS_ENTITY_KEY_V2):
            raise ScenarioParamError(
                f"{self.name}: parameter 'recall_semantics_version' must be "
                f"{SEMANTICS_LEGACY!r} or {SEMANTICS_ENTITY_KEY_V2!r}, "
                f"got {version!r}"
            )

    async def setup(self, ctx: ScenarioContext) -> None:
        """Fix the virtual target = bot spawn + seeded horizontal offset.

        v2 additionally derives the opaque target entity key HERE — before
        and independently of any distractor generation (TASK-011 P3).
        """

        spawn = (await ctx.bot.get_state()).position
        self.spawn = spawn
        rng = random.Random(ctx.seed)
        dx = rng.choice((-1, 1)) * rng.randint(8, 20)
        dz = rng.choice((-1, 1)) * rng.randint(8, 20)
        self.target = Position(x=spawn.x + dx, y=spawn.y, z=spawn.z + dz)
        if self._is_v2():
            self.target_entity_key = target_entity_key(ctx.seed)

    async def experience_phase(self, ctx: ScenarioContext) -> None:
        """Store exactly one fact: the target chest's coordinates.

        v2 stores the neutral entity-key mapping instead:
        `{"entity_key": <target key>, "x": ..., "y": ..., "z": ...}` — the
        same actor/type it shares with every v2 distractor candidate.
        """

        assert self.target is not None
        event_id, timestamp = self._next_event_identity(ctx, "experience")
        if self._is_v2():
            assert self.target_entity_key is not None
            context: dict[str, Any] = {
                "entity_key": self.target_entity_key,
                "x": self.target.x,
                "y": self.target.y,
                "z": self.target.z,
            }
        else:
            context = {
                "subject": "target_chest",
                "x": self.target.x,
                "y": self.target.y,
                "z": self.target.z,
            }
        event = ExperienceEvent(
            event_id=event_id,
            episode_id=ctx.episode_id,
            timestamp=timestamp,
            actor="scenario-instructor",
            event_type=EventType.LOCATION_DISCOVERED,
            context=context,
        )
        await ctx.memory.add(event)
        self.target_event_id = event.event_id

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
            event_id, timestamp = self._next_event_identity(ctx, "interference")
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

        distractor_count = self.params["similar_distractor_count"]
        if distractor_count and self._is_v2():
            # TASK-011 v2: N OTHER entity-key-to-location facts. Every key is
            # a unique one-character mutation of the target key; every
            # location is unique; all facts are simultaneously true and share
            # the target fact's exact actor/type/context schema. No labels.
            assert self.target is not None
            assert self.spawn is not None
            assert self.target_entity_key is not None
            self.distractor_event_ids = []
            keys = distractor_entity_keys(self.target_entity_key, distractor_count)
            positions = distractor_positions(
                self.spawn, self.target, random.Random(ctx.seed + 2), distractor_count
            )
            for key, position in zip(keys, positions, strict=True):
                event_id, timestamp = self._next_event_identity(ctx, "interference")
                event = ExperienceEvent(
                    event_id=event_id,
                    episode_id=ctx.episode_id,
                    timestamp=timestamp,
                    actor="scenario-instructor",
                    event_type=EventType.LOCATION_DISCOVERED,
                    context={
                        "entity_key": key,
                        "x": position.x,
                        "y": position.y,
                        "z": position.z,
                    },
                )
                await ctx.memory.add(event)
                self.distractor_event_ids.append(event.event_id)
        elif distractor_count:
            assert self.target is not None
            assert self.spawn is not None
            self.wrong_fact_ids = set()
            distractor_rng = random.Random(ctx.seed + 2)
            for context in build_similar_distractors(
                self.target, self.spawn, distractor_rng, distractor_count
            ):
                event_id, timestamp = self._next_event_identity(ctx, "interference")
                actor = "environment"
                event_type = EventType.WORLD_FACT_UPDATED
                if (
                    ctx.campaign_mode == CAMPAIGN_MODE_CONTROLLED
                    and context["subject"] == "target_chest"
                ):
                    # Controlled Mode (TASK-007): competing target-location
                    # facts must be structurally IDENTICAL to the learned
                    # target fact — same neutral actor, event type, and
                    # context key set, and no correctness/staleness labels
                    # ("wrong location", "used to be located here", ...).
                    # They differ only in coordinates and retrieval order;
                    # correctness lives solely in the out-of-band event ids.
                    context = {
                        "subject": "target_chest",
                        "x": context["x"],
                        "y": context["y"],
                        "z": context["z"],
                    }
                    actor = "scenario-instructor"
                    event_type = EventType.LOCATION_DISCOVERED
                event = ExperienceEvent(
                    event_id=event_id,
                    episode_id=ctx.episode_id,
                    timestamp=timestamp,
                    actor=actor,
                    event_type=event_type,
                    context=context,
                )
                await ctx.memory.add(event)
                # Only the target-at-a-wrong/stale-location lookalikes count
                # as wrong facts about the target; other-colored chests and
                # other objects are merely irrelevant.
                if context["subject"] == "target_chest":
                    self.wrong_fact_ids.add(event.event_id)

    async def test_phase(self, ctx: ScenarioContext) -> None:
        """Return to the learned location using memory alone (no coordinates)."""

        assert self.target is not None
        self.run_log = await ctx.runner.run_goal(
            goal=self._goal(), success_at=self.target, max_steps=3,
            episode_id=ctx.episode_id,
        )

    async def evaluate(self, ctx: ScenarioContext) -> ScenarioResult:
        """Measure recall, navigation, cost, and memory latency.

        The headline retrieval metrics are computed from the retrieval that
        CAUSED the first decision — the `retrieved_items` recorded on
        `run_log.steps[0]` — never from a second, evaluation-time retrieval.
        The evaluation-time probe below is diagnostic raw evidence only
        (labelled `evaluate-diagnostic`) and feeds no metric.
        """

        assert self.target is not None
        assert self.run_log is not None
        assert self.target_event_id is not None

        task_success = 1 if self.run_log.success else 0

        first_step_items = (
            self.run_log.steps[0].retrieved_items if self.run_log.steps else []
        )

        ground_truth: EntityKeyGroundTruth | None = None
        if self._is_v2():
            assert self.target_entity_key is not None
            recall = compute_entity_key_metrics(
                first_step_items, self.target_event_id, self.distractor_event_ids
            )
            ground_truth = EntityKeyGroundTruth(
                semantics_version=SEMANTICS_ENTITY_KEY_V2,
                target_event_id=self.target_event_id,
                target_entity_key=self.target_entity_key,
                distractor_event_ids=list(self.distractor_event_ids),
            )
        else:
            recall = compute_recall_metrics(
                first_step_items, self.target_event_id, self.wrong_fact_ids
            )

        # The diagnostic probe uses the run's own goal text: the dynamic key
        # naming goal for v2, the legacy phrase for legacy.
        _diagnostic_items, diagnostic_probe = await run_retrieval_probe(
            ctx,
            phase="evaluate-diagnostic",
            query_text=self._goal() if self._is_v2() else "target chest location",
        )

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
        shared_metrics: dict[str, float | int | str | None] = {
            "task_success": task_success,
            "fact_retrieval_rank": recall["fact_retrieval_rank"],
            "retrieval_evidence_source": "run_log.steps[0].retrieved_items",
            "final_distance_to_target": round(final_distance, 3),
            "llm_calls": self.run_log.llm_calls,
            "total_prompt_tokens": self.run_log.total_prompt_tokens,
            "total_completion_tokens": self.run_log.total_completion_tokens,
            "avg_add_latency_ms": stats.extra.get("avg_add_latency_ms"),
            "avg_retrieve_latency_ms": stats.extra.get("avg_retrieve_latency_ms"),
        }
        if self._is_v2():
            metrics: dict[str, float | int | str | None] = {
                **shared_metrics,
                "target_recall": recall["target_recall"],
                "target_retrieval_precision": recall["target_retrieval_precision"],
                "off_target_retrieval_rate": recall["off_target_retrieval_rate"],
                # Schema compatibility only: recall_accuracy mirrors
                # target_recall; the legacy wrong/precision keys are N/A for
                # v2 because off-target entities are TRUE facts, never wrong.
                "recall_accuracy": recall["target_recall"],
                "wrong_fact_rate": None,
                "retrieval_precision": None,
            }
        else:
            metrics = {
                **shared_metrics,
                "recall_accuracy": recall["recall_accuracy"],
                "wrong_fact_rate": recall["wrong_fact_rate"],
                "retrieval_precision": recall["retrieval_precision"],
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
