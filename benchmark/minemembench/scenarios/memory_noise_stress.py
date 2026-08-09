"""Scenario D — Memory Noise Stress (M15B).

The agent learns exactly one key memory (the target chest's location), then N
unrelated ExperienceEvents are written to memory before the test goal, with N
parameterized by `noise_count` (levels 0 / 10 / 50 / 100 / 200 / 500 / 1000).
The stress is pure retrieval robustness: as memory fills with irrelevant
facts, do the relevant memories survive, and does retrieval slow down or cost
more tokens?

`noise_count` defaults to 0 — the ceiling-control run with no noise at all.

Phase-1 simplification: the target chest is VIRTUAL; we measure navigation
correctness to the remembered location. The noise events are deliberately
free of the target's high-frequency tokens, so only a real retrieval signal
(semantic / vector) can keep the key memory ahead.

Seed usage (legacy): `random.Random(seed)` drives the target offset in
`setup`; `random.Random(seed + 1)` drives the noise facts, keeping every
phase deterministic and phase-independent.

Semantics v2 (TASK-016, `noise_semantics_version="key_retention_v2"`): the
learned fact maps one opaque, seeded, fixed-width entity key (e.g.
`cache-7f3a9c2e`) to the target location, and every noise event maps an
INDEPENDENTLY derived opaque key to its OWN unique seeded location — all
facts are simultaneously true, so this axis measures retrieval volume, never
lexical similarity (one-character near-miss keys belong to delayed recall).
All events share one neutral actor/type/context schema
(`{"entity_key", "x", "y", "z"}`) with no target/noise/correctness/priority
labels; the v2 goal names the target key and no coordinates. The target key
is derived from the seed in a dedicated namespace BEFORE and independently of
`noise_count` and noise generation; noise prefixes are stable (for a fixed
seed, cells N and M share the same first N noise keys/coordinates when
N < M). Headline v2 metrics (`target_retrieval_rank`, `target_recall`,
`target_retrieval_precision`, `noise_retrieval_rate`, `target_top1`,
`retrieved_item_count`) are computed from the typed out-of-band
`evaluation_ground_truth` plus the causal step-0 retrieval snapshot
(`run_log.steps[0].retrieved_items`), never a second probe; the
evaluation-time probe is preserved as `evaluate-diagnostic` raw evidence and
feeds no metric. Legacy compatibility: the legacy retrieval-semantics keys
(`relevant_memory_precision`, `irrelevant_retrieval_rate`) are subject-parsing
metrics that are semantically invalid for v2 and stay N/A — no compatibility
mirror redefines them. Legacy remains the default: its goal text, event
semantics, metrics, and result JSON shape are unchanged, and old result JSON
stays loadable.

Controlled Mode (TASK-016): only `key_retention_v2` is Controlled-approved
(the central policy in cli.py and the fail-closed gate in `setup`); generated
events then get deterministic ids/logical timestamps derived from (seed,
full effective params, phase, ordinal), so the offered stream is semantically
identical across backends and only the isolation `episode_id` differs.
"""

from __future__ import annotations

import hashlib
import random
import time
from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from typing import Any, ClassVar

from ..core.fairness import CAMPAIGN_MODE_CONTROLLED
from ..core.ids import new_event_id
from ..core.models import EventType, ExperienceEvent, Position
from ..core.runner import RunLog
from ..memory.base import MemoryItem, MemoryItemSnapshot
from .base import (
    KeyRetentionGroundTruth,
    Scenario,
    ScenarioContext,
    ScenarioParamError,
    ScenarioResult,
    run_retrieval_probe,
)
from .controlled import controlled_event_identity
from .delayed_recall import _NOISE_FACTS

#: Deliberately free of any coordinates: recall must come from memory.
GOAL = "Return to the target chest you learned about at the start of this episode."

#: Accepted values of the `noise_semantics_version` parameter (TASK-016).
SEMANTICS_LEGACY = "legacy"
SEMANTICS_KEY_RETENTION_V2 = "key_retention_v2"


def target_entity_key(seed: int) -> str:
    """The v2 target key: opaque, fixed-width, derived from the scenario seed
    in a DEDICATED namespace — before and independently of `noise_count` and
    any noise generation (TASK-016)."""

    digest = hashlib.sha256(
        f"memory_noise_stress/key_retention_v2/target/{seed}".encode("utf-8")
    ).hexdigest()
    return f"cache-{digest[:8]}"


def _is_near_miss(candidate: str, reference: str) -> bool:
    """Whether two equal-width keys differ in at most one character."""

    return sum(a != b for a, b in zip(candidate, reference, strict=True)) <= 1


def noise_entity_keys(seed: int, target_key: str, count: int) -> list[str]:
    """`count` unique opaque noise keys, deterministic and count-independent.

    Key i is derived from (seed, i) in a dedicated noise namespace with a
    deterministic rejection loop, so the first N keys are identical for every
    requested count >= N (prefix stability). No noise key is a one-character
    near-miss of the target key: this axis measures volume, not lexical
    similarity.
    """

    keys: list[str] = []
    for index in range(count):
        attempt = 0
        while True:
            digest = hashlib.sha256(
                f"memory_noise_stress/key_retention_v2/noise/{seed}/{index}/{attempt}".encode(
                    "utf-8"
                )
            ).hexdigest()
            candidate = f"cache-{digest[:8]}"
            if candidate not in keys and not _is_near_miss(candidate, target_key):
                keys.append(candidate)
                break
            attempt += 1
    return keys


def noise_positions(
    spawn: Position, target: Position, seed: int, count: int
) -> list[Position]:
    """`count` unique seeded noise coordinates, none equal to the target.

    Drawn in order from a single `random.Random(seed + 1)` stream over a wide
    horizontal range (the narrow 8–20 block offset space cannot supply 1000
    unique positions), so the first N positions are identical for every
    requested count >= N (prefix stability).
    """

    rng = random.Random(seed + 1)
    positions: list[Position] = []
    seen = {(target.x, target.y, target.z)}
    while len(positions) < count:
        candidate = Position(
            x=spawn.x + rng.randint(-512, 512),
            y=spawn.y,
            z=spawn.z + rng.randint(-512, 512),
        )
        key = (candidate.x, candidate.y, candidate.z)
        if key in seen:
            continue
        seen.add(key)
        positions.append(candidate)
    return positions


def compute_key_retention_metrics(
    items: Sequence[MemoryItem | MemoryItemSnapshot],
    target_event_id: str,
    noise_event_ids: Collection[str],
) -> dict[str, float | int | None]:
    """v2 (key_retention_v2) retrieval metrics, by stable event id (TASK-016).

    Every stored fact is simultaneously TRUE; noise items are merely
    off-target. Ground truth is the out-of-band `evaluation_ground_truth`
    ids, never prompt-visible content; the input is the causal step-0
    retrieval snapshot, never a second probe.

    - `target_retrieval_rank`: 1-based position of the target event itself;
      None when the target is absent.
    - `target_recall`: 1 when the target is among the retrieved items,
      0 otherwise — an empty retrieval is a measured miss, not N/A.
    - `target_retrieval_precision`: target items / retrieved items;
      None (N/A) on empty retrieval.
    - `noise_retrieval_rate`: known noise items / retrieved items;
      None (N/A) on empty retrieval.
    - `target_top1`: 1 when the top item is the target, 0 when it is a known
      noise item, None otherwise.
    - `retrieved_item_count`: number of retrieved items the metrics describe.
    """

    if not items:
        return {
            "target_retrieval_rank": None,
            "target_recall": 0,
            "target_retrieval_precision": None,
            "noise_retrieval_rate": None,
            "target_top1": None,
            "retrieved_item_count": 0,
        }

    noise_ids = set(noise_event_ids)
    retrieved_ids = [item.event.event_id for item in items]
    target_count = sum(1 for event_id in retrieved_ids if event_id == target_event_id)
    noise_count = sum(1 for event_id in retrieved_ids if event_id in noise_ids)
    rank: int | None = None
    for index, event_id in enumerate(retrieved_ids):
        if event_id == target_event_id:
            rank = index + 1
            break
    top1: int | None = None
    if retrieved_ids[0] == target_event_id:
        top1 = 1
    elif retrieved_ids[0] in noise_ids:
        top1 = 0
    return {
        "target_retrieval_rank": rank,
        "target_recall": 1 if target_count else 0,
        "target_retrieval_precision": round(target_count / len(items), 4),
        "noise_retrieval_rate": round(noise_count / len(items), 4),
        "target_top1": top1,
        "retrieved_item_count": len(items),
    }


class MemoryNoiseStressScenario(Scenario):
    """Scenario D: does one key memory survive an ever-growing noise flood?"""

    name: ClassVar[str] = "memory_noise_stress"
    default_params: ClassVar[dict[str, Any]] = {
        "noise_count": 0,
        # TASK-016: "legacy" (default; native behavior/metrics unchanged) or
        # "key_retention_v2" (the neutral key-retention treatment). Controlled
        # mode fails closed unless the value is "key_retention_v2".
        "noise_semantics_version": SEMANTICS_LEGACY,
    }

    def __init__(self) -> None:
        self.target: Position | None = None
        self.spawn: Position | None = None
        self.run_log: RunLog | None = None
        self._started_at: float | None = None
        #: v2 (key_retention_v2): the opaque target key, the target event id,
        #: and the ORDERED noise event ids — out-of-band evaluation ground
        #: truth, never planner-visible.
        self.target_entity_key: str | None = None
        self.target_event_id: str | None = None
        self.noise_event_ids: list[str] = []
        #: Controlled Mode: per-phase ordinal counters for deterministic
        #: event identity (native runs ignore this).
        self._controlled_ordinals: dict[str, int] = {}

    def _is_v2(self) -> bool:
        return self.params["noise_semantics_version"] == SEMANTICS_KEY_RETENTION_V2

    def _goal(self) -> str:
        """The run's goal: the static legacy text, or the v2 key naming text.

        The v2 goal names exactly the target entity key and no coordinates;
        it contains no correctness/priority/retrieval hint.
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
        self._require_int_param("noise_count", 0)
        version = self._params["noise_semantics_version"]
        if version not in (SEMANTICS_LEGACY, SEMANTICS_KEY_RETENTION_V2):
            raise ScenarioParamError(
                f"{self.name}: parameter 'noise_semantics_version' must be "
                f"{SEMANTICS_LEGACY!r} or {SEMANTICS_KEY_RETENTION_V2!r}, "
                f"got {version!r}"
            )

    async def setup(self, ctx: ScenarioContext) -> None:
        """Fix the virtual target = bot spawn + seeded horizontal offset.

        Fail closed: a Controlled run may only ever use the v2 treatment —
        legacy Controlled memory-noise is research-invalid (TASK-016) and
        must never be produced. v2 additionally derives the opaque target
        entity key HERE — before and independently of any noise generation.
        """

        if ctx.campaign_mode == CAMPAIGN_MODE_CONTROLLED and not self._is_v2():
            raise ScenarioParamError(
                f"{self.name}: Controlled mode requires "
                f"noise_semantics_version={SEMANTICS_KEY_RETENTION_V2!r}, "
                f"got {self.params['noise_semantics_version']!r}"
            )
        self._started_at = time.perf_counter()
        spawn = (await ctx.bot.get_state()).position
        self.spawn = spawn
        rng = random.Random(ctx.seed)
        dx = rng.choice((-1, 1)) * rng.randint(8, 20)
        dz = rng.choice((-1, 1)) * rng.randint(8, 20)
        self.target = Position(x=spawn.x + dx, y=spawn.y, z=spawn.z + dz)
        if self._is_v2():
            self.target_entity_key = target_entity_key(ctx.seed)

    async def experience_phase(self, ctx: ScenarioContext) -> None:
        """Store exactly one key memory: the target chest's location.

        v2 stores the neutral entity-key mapping instead:
        `{"entity_key": <target key>, "x": ..., "y": ..., "z": ...}` — the
        same actor/type/context schema every v2 noise event shares.
        """

        assert self.target is not None
        if self._is_v2():
            assert self.target_entity_key is not None
            event_id, timestamp = self._next_event_identity(ctx, "experience")
            event = ExperienceEvent(
                event_id=event_id,
                episode_id=ctx.episode_id,
                timestamp=timestamp,
                actor="scenario-instructor",
                event_type=EventType.LOCATION_DISCOVERED,
                context={
                    "entity_key": self.target_entity_key,
                    "x": self.target.x,
                    "y": self.target.y,
                    "z": self.target.z,
                },
            )
            await ctx.memory.add(event)
            self.target_event_id = event.event_id
            return
        await ctx.memory.add(
            ExperienceEvent(
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
        )

    async def interference_phase(self, ctx: ScenarioContext) -> None:
        """Flood memory with `noise_count` unrelated world-fact events.

        v2 (TASK-016): N simultaneously-true key-to-location facts. Every key
        is independently derived (never a one-character near-miss of the
        target key); every location is unique; all facts share the target
        fact's exact actor/type/context schema. No labels.
        """

        if self._is_v2():
            assert self.target is not None
            assert self.spawn is not None
            assert self.target_entity_key is not None
            noise_count = self.params["noise_count"]
            self.noise_event_ids = []
            keys = noise_entity_keys(ctx.seed, self.target_entity_key, noise_count)
            positions = noise_positions(self.spawn, self.target, ctx.seed, noise_count)
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
                self.noise_event_ids.append(event.event_id)
            return

        rng = random.Random(ctx.seed + 1)
        for _ in range(self.params["noise_count"]):
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
            goal=self._goal(), success_at=self.target, max_steps=3,
            episode_id=ctx.episode_id,
        )

    async def evaluate(self, ctx: ScenarioContext) -> ScenarioResult:
        """Measure retrieval robustness, cost, and end-to-end latency.

        Legacy: retrieval metrics come from the evaluation-time probe via
        `subject` parsing — unchanged. v2 (TASK-016): headline metrics come
        from the typed out-of-band ground truth plus the CAUSAL step-0
        retrieval snapshot; the evaluation-time probe (queried with the v2
        goal) is diagnostic raw evidence only and feeds no metric.
        """

        assert self.target is not None
        assert self.run_log is not None

        task_success = 1 if self.run_log.success else 0
        if self._is_v2():
            return await self._evaluate_v2(ctx, task_success)
        return await self._evaluate_legacy(ctx, task_success)

    async def _evaluate_legacy(
        self, ctx: ScenarioContext, task_success: int
    ) -> ScenarioResult:
        """The pre-TASK-016 evaluation path, unchanged."""

        items, probe = await run_retrieval_probe(
            ctx, phase="evaluate", query_text="target chest location"
        )
        retrieved_count = len(items)
        relevant = [
            item for item in items if item.event.context.get("subject") == "target_chest"
        ]
        relevant_memory_precision = (
            round(len(relevant) / retrieved_count, 4) if retrieved_count else None
        )
        irrelevant_retrieval_rate = (
            round((retrieved_count - len(relevant)) / retrieved_count, 4)
            if retrieved_count
            else None
        )

        stats = await ctx.memory.stats()
        metrics: dict[str, float | int | str | None] = {
            "task_success": task_success,
            "relevant_memory_precision": relevant_memory_precision,
            "irrelevant_retrieval_rate": irrelevant_retrieval_rate,
            "retrieval_latency_ms": stats.extra.get("avg_retrieve_latency_ms"),
            "token_cost": (
                self.run_log.total_prompt_tokens + self.run_log.total_completion_tokens
            ),
            "total_prompt_tokens": self.run_log.total_prompt_tokens,
            "total_completion_tokens": self.run_log.total_completion_tokens,
            "llm_calls": self.run_log.llm_calls,
            "end_to_end_latency_s": (
                round(time.perf_counter() - self._started_at, 3)
                if self._started_at is not None
                else None
            ),
            "avg_add_latency_ms": stats.extra.get("avg_add_latency_ms"),
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
        self, ctx: ScenarioContext, task_success: int
    ) -> ScenarioResult:
        """Causal v2 evaluation: typed ground truth + step-0 snapshot."""

        assert self.run_log is not None
        assert self.target_event_id is not None
        assert self.target_entity_key is not None

        first_step_items = (
            self.run_log.steps[0].retrieved_items if self.run_log.steps else []
        )
        ground_truth = KeyRetentionGroundTruth(
            semantics_version=SEMANTICS_KEY_RETENTION_V2,
            target_event_id=self.target_event_id,
            target_entity_key=self.target_entity_key,
            noise_event_ids=list(self.noise_event_ids),
        )
        retrieval = compute_key_retention_metrics(
            first_step_items, self.target_event_id, self.noise_event_ids
        )

        # Diagnostic raw evidence only: feeds no headline or behavioral metric.
        _diagnostic_items, diagnostic_probe = await run_retrieval_probe(
            ctx, phase="evaluate-diagnostic", query_text=self._goal()
        )

        stats = await ctx.memory.stats()
        metrics: dict[str, float | int | str | None] = {
            "task_success": task_success,
            "target_retrieval_rank": retrieval["target_retrieval_rank"],
            "target_recall": retrieval["target_recall"],
            "target_retrieval_precision": retrieval["target_retrieval_precision"],
            "noise_retrieval_rate": retrieval["noise_retrieval_rate"],
            "target_top1": retrieval["target_top1"],
            "retrieved_item_count": retrieval["retrieved_item_count"],
            "retrieval_evidence_source": "run_log.steps[0].retrieved_items",
            # Legacy retrieval-semantics keys are subject-parsing metrics,
            # semantically invalid for v2: they stay N/A (no mirror redefines
            # them).
            "relevant_memory_precision": None,
            "irrelevant_retrieval_rate": None,
            # Behavioral/cost metrics from the real run (no latency
            # normalization claimed).
            "retrieval_latency_ms": stats.extra.get("avg_retrieve_latency_ms"),
            "token_cost": (
                self.run_log.total_prompt_tokens + self.run_log.total_completion_tokens
            ),
            "total_prompt_tokens": self.run_log.total_prompt_tokens,
            "total_completion_tokens": self.run_log.total_completion_tokens,
            "llm_calls": self.run_log.llm_calls,
            "end_to_end_latency_s": (
                round(time.perf_counter() - self._started_at, 3)
                if self._started_at is not None
                else None
            ),
            "avg_add_latency_ms": stats.extra.get("avg_add_latency_ms"),
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
