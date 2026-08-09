"""Scenario C — Experience-Guided Adaptation.

Legacy treatment (`failure_semantics_version="legacy"`, the default):

The agent fails to collect a supply crate (it has no coordinates), records
that failure, receives a scout debrief pointing at the crate, and then faces
the same goal again. Adaptation is measured by whether the SECOND attempt
beelines to the crate while the first did not — with no rule anywhere telling
the agent to use the debrief; the behaviour change must come from memory
retrieval alone.

Phase-1 simplification (documented): the current toolset has no equipment
mechanics, so adaptation is measured at the information/planning level (the
agent navigates to a known location it could not know before the debrief),
not via equipment use. The legacy same-crate retry is explicitly ineligible
for transfer claims (TASK-020).

Seed usage (legacy): `random.Random(seed)` drives the crate offset in `setup`;
`random.Random(seed + 1)` drives the interference action and noise facts,
keeping every phase deterministic and phase-independent. The legacy path is
unchanged byte-for-byte, including its fixed five interference facts.

Semantics v2 (TASK-020, `failure_semantics_version="observed_precondition_v2"`,
the only Controlled-approved value): a REAL failed bot `attack_entity`
ActionResult against a warded hostile reveals the hidden environmental
precondition (gold_nugget must be equipped — the fixture's stable error is
the only required-item information memory ever sees). Exactly one derived
TASK_FAILED event enters memory — no authored solution/rule event. The
planner must then transfer that experience to the OTHER warded hostile under
a different task wording. Source/transfer entities are chosen by seed parity
(even: zombie -> skeleton; odd: skeleton -> zombie), so the transfer task is
never an identical retry. Headline retrieval metrics come from the typed
out-of-band ground truth plus the causal step-0 retrieval snapshot; behavior
metrics come from the ordered real RunSteps. The exact source ActionResult is
preserved in `ScenarioResult.observed_action_results`.

Controlled Mode: v2-only (central policy in cli.py plus the fail-closed gate
in `setup`); generated events get deterministic ids/logical timestamps from
(seed, full effective params, phase, ordinal). The scenario requires the
`warded_hostiles_v1` mock fixture, selected via explicit process
configuration (BOT_MOCK_FIXTURE), never from a backend name.
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
from ..core.models import (
    ActionResult,
    ActionStatus,
    EntityKind,
    EventType,
    ExperienceEvent,
    Position,
)
from ..core.runner import RunLog, RunStep
from ..memory.base import MemoryItem, MemoryItemSnapshot
from .base import (
    ObservedPreconditionGroundTruth,
    Scenario,
    ScenarioContext,
    ScenarioParamError,
    ScenarioResult,
    run_retrieval_probe,
)
from .controlled import controlled_event_identity
from .delayed_recall import _NOISE_FACTS
from .world_update import seeded_offset

#: Deliberately free of any coordinates: the crate location must come from memory.
GOAL = "Collect the supply crate."

#: Distance (blocks) within which a first move counts as beelining to the crate.
_BEELINE_RADIUS_BLOCKS = 2.0

#: Accepted values of the `failure_semantics_version` parameter (TASK-020).
SEMANTICS_LEGACY = "legacy"
SEMANTICS_OBSERVED_PRECONDITION_V2 = "observed_precondition_v2"

#: v2 treatment constants. The task family is the neutral retrieval cue shared
#: by the source failure event and the transfer goal; the required item is
#: evaluation-only — memory sees it solely inside the environment's error.
TASK_FAMILY = "warded_hostile"
REQUIRED_ITEM = "gold_nugget"

#: The two warded hostiles of the v2 fixture, at distinct visible positions.
_WARDED_ENTITIES = ("zombie", "skeleton")

#: Planner budget for the single transfer attempt (prepare + attack + slack).
_TRANSFER_MAX_STEPS = 4


class ObservedPreconditionError(RuntimeError):
    """Fail-closed violation of the v2 observed-failure contract.

    Raised when the environment does not produce the expected genuinely
    failed source attack (unexpected success, empty error, vanished entity,
    equipped hand, or a missing warded fixture entity) — such a run is
    research-invalid and must never produce a result.
    """


def source_transfer_entities(seed: int) -> tuple[str, str]:
    """Deterministic, opposite (source, transfer) entities for `seed`.

    Even seeds attack the zombie first and transfer to the skeleton; odd
    seeds the reverse — the transfer task is never an identical retry.
    """

    if seed % 2 == 0:
        return (_WARDED_ENTITIES[0], _WARDED_ENTITIES[1])
    return (_WARDED_ENTITIES[1], _WARDED_ENTITIES[0])


def compute_observed_precondition_metrics(
    items: Sequence[MemoryItem | MemoryItemSnapshot],
    failure_event_id: str,
    interference_event_ids: Collection[str],
) -> dict[str, float | int | None]:
    """v2 (observed_precondition_v2) retrieval metrics, by stable event id.

    Ground truth is the out-of-band `evaluation_ground_truth` ids, never
    prompt-visible content; the input is the causal step-0 retrieval snapshot,
    never a second probe. Mirrors the key_retention_v2 math:

    - `failure_retrieval_rank`: 1-based position of the source failure event;
      None when absent.
    - `failure_recall`: 1 when the failure event is retrieved, 0 otherwise —
      an empty retrieval is a measured miss, not N/A.
    - `failure_retrieval_precision`: failure items / retrieved items;
      None (N/A) on empty retrieval.
    - `interference_retrieval_rate`: known interference items / retrieved
      items; None (N/A) on empty retrieval.
    - `failure_top1`: 1 when the top item is the failure event, 0 when it is
      a known interference item, None otherwise.
    - `retrieved_item_count`: number of retrieved items the metrics describe.
    """

    if not items:
        return {
            "failure_retrieval_rank": None,
            "failure_recall": 0,
            "failure_retrieval_precision": None,
            "interference_retrieval_rate": None,
            "failure_top1": None,
            "retrieved_item_count": 0,
        }

    interference_ids = set(interference_event_ids)
    retrieved_ids = [item.event.event_id for item in items]
    failure_count = sum(1 for event_id in retrieved_ids if event_id == failure_event_id)
    interference_count = sum(
        1 for event_id in retrieved_ids if event_id in interference_ids
    )
    rank: int | None = None
    for index, event_id in enumerate(retrieved_ids):
        if event_id == failure_event_id:
            rank = index + 1
            break
    top1: int | None = None
    if retrieved_ids[0] == failure_event_id:
        top1 = 1
    elif retrieved_ids[0] in interference_ids:
        top1 = 0
    return {
        "failure_retrieval_rank": rank,
        "failure_recall": 1 if failure_count else 0,
        "failure_retrieval_precision": round(failure_count / len(items), 4),
        "interference_retrieval_rate": round(interference_count / len(items), 4),
        "failure_top1": top1,
        "retrieved_item_count": len(items),
    }


def compute_transfer_behavior_metrics(
    steps: Sequence[RunStep],
    *,
    transfer_entity: str,
    transfer_entity_id: int,
    required_item: str,
) -> dict[str, int]:
    """v2 transfer behavior endpoints from the ordered real RunSteps.

    - `prepared_before_first_transfer_attack`: a completed
      `equip_item(required_item)` occurs before the first attack on the
      transfer entity.
    - `failure_repeated`: the first transfer attack happens before
      preparation and fails.
    - `transfer_attack_completed`: a completed attack on the transfer entity
      occurred (the fixture removes the entity on completion).
    - `transfer_success`: preparation precedes a completed transfer attack.
    - `eventual_recovery_after_failure`: a completed transfer attack occurs
      even though the failure was repeated first — logged, never a success.
    """

    def is_transfer_attack(step: RunStep) -> bool:
        if step.action != "attack_entity":
            return False
        return (
            step.arguments.get("entity_id") == transfer_entity_id
            or step.arguments.get("name") == transfer_entity
        )

    def is_preparation(step: RunStep) -> bool:
        return (
            step.action == "equip_item"
            and step.arguments.get("item") == required_item
            and step.action_status == ActionStatus.COMPLETED
        )

    first_attack: int | None = None
    preparation: int | None = None
    completed_attacks: list[int] = []
    for index, step in enumerate(steps):
        if is_transfer_attack(step):
            if first_attack is None:
                first_attack = index
            if step.action_status == ActionStatus.COMPLETED:
                completed_attacks.append(index)
        if preparation is None and is_preparation(step):
            preparation = index

    prepared_before = 1 if (
        preparation is not None
        and first_attack is not None
        and preparation < first_attack
    ) else 0
    failure_repeated = 1 if (
        first_attack is not None
        and steps[first_attack].action_status == ActionStatus.FAILED
        and (preparation is None or first_attack < preparation)
    ) else 0
    # Primary success is deliberately stricter than eventual completion: the
    # learned precondition must be applied before the FIRST transfer attack.
    # An attack-first failure followed by equip + recovery remains a primary
    # failure (TASK-020), even though the recovery is logged separately.
    transfer_success = 1 if (
        prepared_before
        and preparation is not None
        and any(index > preparation for index in completed_attacks)
    ) else 0
    return {
        "prepared_before_first_transfer_attack": prepared_before,
        "failure_repeated": failure_repeated,
        "transfer_attack_completed": 1 if completed_attacks else 0,
        "transfer_success": transfer_success,
        "eventual_recovery_after_failure": 1
        if (failure_repeated and completed_attacks)
        else 0,
    }


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
    default_params: ClassVar[dict[str, Any]] = {
        # TASK-020: "legacy" (default; native behavior/metrics unchanged,
        # including the fixed five interference facts) or
        # "observed_precondition_v2" (the observed-failure transfer
        # treatment). Controlled mode fails closed unless the value is
        # "observed_precondition_v2".
        "failure_semantics_version": SEMANTICS_LEGACY,
        # v2-only knob (default 0 for the v2 smoke): neutral interference
        # events between the observed failure and the transfer task. The
        # legacy path ignores it and keeps its existing five facts.
        "interference_count": 0,
    }

    def __init__(self) -> None:
        self.crate: Position | None = None
        self.attempt_1_log: RunLog | None = None
        self.attempt_2_log: RunLog | None = None
        #: v2 (observed_precondition_v2): the transfer run log, the chosen
        #: entities, the observed raw source failure, and the out-of-band
        #: evaluation ids — never planner-visible.
        self.transfer_log: RunLog | None = None
        self.source_entity: str | None = None
        self.transfer_entity: str | None = None
        self.source_entity_id: int | None = None
        self.transfer_entity_id: int | None = None
        self.source_action_result: ActionResult | None = None
        self.source_failure_event_id: str | None = None
        self.interference_event_ids: list[str] = []
        #: Controlled Mode: per-phase ordinal counters for deterministic
        #: event identity (native runs ignore this).
        self._controlled_ordinals: dict[str, int] = {}

    def _is_v2(self) -> bool:
        return (
            self.params["failure_semantics_version"]
            == SEMANTICS_OBSERVED_PRECONDITION_V2
        )

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
        self._require_int_param("interference_count", 0)
        version = self._params["failure_semantics_version"]
        if version not in (SEMANTICS_LEGACY, SEMANTICS_OBSERVED_PRECONDITION_V2):
            raise ScenarioParamError(
                f"{self.name}: parameter 'failure_semantics_version' must be "
                f"{SEMANTICS_LEGACY!r} or {SEMANTICS_OBSERVED_PRECONDITION_V2!r}, "
                f"got {version!r}"
            )

    def _transfer_goal(self) -> str:
        """The v2 transfer goal: the OTHER warded hostile, a different task.

        Shares only the neutral `warded hostile` task-family cue with the
        source failure event; it names no item, no tool/equip instruction, no
        source entity, no error text and no answer.
        """

        assert self.transfer_entity is not None
        return (
            f"Eliminate the warded hostile {self.transfer_entity} to secure "
            f"the checkpoint."
        )

    async def setup(self, ctx: ScenarioContext) -> None:
        """Fix the episode's controlled variables.

        Fail closed: a Controlled run may only ever use the v2 treatment —
        legacy Controlled failure-learning is research-invalid for transfer
        claims (TASK-020) and must never be produced. v2 additionally
        resolves the warded fixture entities HERE and fails closed when the
        fixture does not provide them.
        """

        if ctx.campaign_mode == CAMPAIGN_MODE_CONTROLLED and not self._is_v2():
            raise ScenarioParamError(
                f"{self.name}: Controlled mode requires "
                f"failure_semantics_version={SEMANTICS_OBSERVED_PRECONDITION_V2!r}, "
                f"got {self.params['failure_semantics_version']!r}"
            )
        if self._is_v2():
            self.source_entity, self.transfer_entity = source_transfer_entities(
                ctx.seed
            )
            state = await ctx.bot.get_state()
            ids: dict[str, int] = {}
            for name in (self.source_entity, self.transfer_entity):
                match = next(
                    (
                        entity
                        for entity in state.nearby_entities
                        if entity.name == name and entity.kind is EntityKind.HOSTILE
                    ),
                    None,
                )
                if match is None:
                    raise ObservedPreconditionError(
                        f"{self.name}: the v2 fixture must expose a hostile "
                        f"{name!r}; found "
                        f"{[e.name for e in state.nearby_entities]!r}"
                    )
                ids[name] = match.id
            self.source_entity_id = ids[self.source_entity]
            self.transfer_entity_id = ids[self.transfer_entity]
            return
        # Legacy: fix the crate location = bot spawn + seeded horizontal offset.
        spawn = (await ctx.bot.get_state()).position
        self.crate = seeded_offset(spawn, random.Random(ctx.seed))

    async def experience_phase(self, ctx: ScenarioContext) -> None:
        """Store the memory-worthy experience.

        Legacy: fail at collecting, then store the failure and the scout
        debrief (unchanged). v2: execute ONE real attack on the source warded
        hostile with an unequipped hand, fail closed unless the environment
        returns a genuine failure, then store exactly one TASK_FAILED event
        derived from that observed ActionResult.
        """

        if self._is_v2():
            await self._experience_v2(ctx)
            return
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

    async def _experience_v2(self, ctx: ScenarioContext) -> None:
        """Observe the source failure from a REAL failed ActionResult.

        Fail closed unless the returned ActionResult is genuinely `failed`,
        carries a nonempty error, and leaves the source entity present — and
        unless the hand started unequipped. Exactly one TASK_FAILED event is
        derived from the observation; its context carries only factual fields
        (task family, source entity, action, status, the raw environment
        error, equipped-before) — never a second solution/requirement event,
        a trust score, a policy, or "next time ..." text.
        """

        assert self.source_entity is not None
        assert self.source_entity_id is not None
        pre_state = await ctx.bot.get_state()
        if pre_state.equipped.hand is not None:
            raise ObservedPreconditionError(
                f"{self.name}: v2 source attack must start with an unequipped "
                f"hand, got {pre_state.equipped.hand.name!r}"
            )
        source = next(
            entity
            for entity in pre_state.nearby_entities
            if entity.id == self.source_entity_id
        )
        result = await ctx.bot.execute(
            "attack_entity", {"entity_id": self.source_entity_id}
        )
        state_after = (
            result.state_after
            if result.state_after is not None
            else await ctx.bot.get_state()
        )
        if result.status is not ActionStatus.FAILED:
            raise ObservedPreconditionError(
                f"{self.name}: v2 source attack on {self.source_entity!r} must "
                f"fail (hidden precondition), got status {result.status.value!r}"
            )
        if not result.error:
            raise ObservedPreconditionError(
                f"{self.name}: v2 source attack failed with an empty error; "
                "the environment error is the only required-item evidence"
            )
        if not any(
            entity.id == self.source_entity_id
            for entity in state_after.nearby_entities
        ):
            raise ObservedPreconditionError(
                f"{self.name}: v2 source entity {self.source_entity!r} "
                "disappeared after the failed attack"
            )
        self.source_action_result = result

        event_id, timestamp = self._next_event_identity(ctx, "experience")
        event = ExperienceEvent(
            event_id=event_id,
            episode_id=ctx.episode_id,
            timestamp=timestamp,
            actor="agent",
            target=self.source_entity,
            event_type=EventType.TASK_FAILED,
            location=source.position,
            context={
                "task_family": TASK_FAMILY,
                "entity": self.source_entity,
                "action": "attack_entity",
                "status": result.status.value,
                "error": result.error,
                "equipped_before": None,
            },
            outcome=result.status.value,
        )
        await ctx.memory.add(event)
        self.source_failure_event_id = event.event_id

    async def interference_phase(self, ctx: ScenarioContext) -> None:
        """Seeded, unrelated noise between learning and testing.

        Legacy: five unrelated world facts plus one real seeded bot action
        (unchanged). v2: `interference_count` neutral ambient notes with
        deterministic content, free of the task family, entity, item and
        error tokens.
        """

        if self._is_v2():
            self.interference_event_ids = []
            for ordinal in range(self.params["interference_count"]):
                event_id, timestamp = self._next_event_identity(
                    ctx, "interference"
                )
                digest = hashlib.sha256(
                    f"failure_learning/observed_precondition_v2/interference/"
                    f"{ctx.seed}/{ordinal}".encode("utf-8")
                ).hexdigest()
                event = ExperienceEvent(
                    event_id=event_id,
                    episode_id=ctx.episode_id,
                    timestamp=timestamp,
                    actor="environment",
                    event_type=EventType.WORLD_FACT_UPDATED,
                    context={
                        "subject": "ambient",
                        "note": f"ambient-note-{digest[:8]}",
                    },
                )
                await ctx.memory.add(event)
                self.interference_event_ids.append(event.event_id)
            return

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
        """Probe memory. Legacy: retry the same goal after the failed attempt
        and the debrief (unchanged). v2: ONE transfer attempt against the
        other warded hostile with the normal unchanged planner/tools/model —
        no success_at, and no scenario-chosen actions."""

        if self._is_v2():
            self.transfer_log = await ctx.runner.run_goal(
                goal=self._transfer_goal(),
                max_steps=_TRANSFER_MAX_STEPS,
                episode_id=ctx.episode_id,
            )
            return
        assert self.crate is not None
        self.attempt_2_log = await ctx.runner.run_goal(
            goal=GOAL, success_at=self.crate, max_steps=3,
            episode_id=ctx.episode_id,
        )

    async def evaluate(self, ctx: ScenarioContext) -> ScenarioResult:
        """Measure the outcome; anything unmeasured stays None.

        Legacy: adaptation, navigation, cost, and memory latency (unchanged).
        v2: causal retrieval metrics (typed ground truth + step-0 snapshot)
        and ordered-step transfer behavior endpoints.
        """

        if self._is_v2():
            return await self._evaluate_v2(ctx)
        return await self._evaluate_legacy(ctx)

    async def _evaluate_v2(self, ctx: ScenarioContext) -> ScenarioResult:
        """Causal v2 evaluation: typed ground truth + step-0 snapshot."""

        assert self.transfer_log is not None
        assert self.source_action_result is not None
        assert self.source_action_result.error  # fail-closed in experience
        assert self.source_failure_event_id is not None
        assert self.source_entity is not None
        assert self.transfer_entity is not None
        assert self.transfer_entity_id is not None

        behavior = compute_transfer_behavior_metrics(
            self.transfer_log.steps,
            transfer_entity=self.transfer_entity,
            transfer_entity_id=self.transfer_entity_id,
            required_item=REQUIRED_ITEM,
        )
        first_step_items = (
            self.transfer_log.steps[0].retrieved_items
            if self.transfer_log.steps
            else []
        )
        retrieval = compute_observed_precondition_metrics(
            first_step_items,
            self.source_failure_event_id,
            self.interference_event_ids,
        )
        ground_truth = ObservedPreconditionGroundTruth(
            semantics_version=SEMANTICS_OBSERVED_PRECONDITION_V2,
            task_family=TASK_FAMILY,
            source_failure_event_id=self.source_failure_event_id,
            source_entity=self.source_entity,
            transfer_entity=self.transfer_entity,
            required_item=REQUIRED_ITEM,
            expected_source_action="attack_entity",
            expected_source_status=ActionStatus.FAILED.value,
            expected_source_error=self.source_action_result.error,
            interference_event_ids=list(self.interference_event_ids),
        )

        # Diagnostic raw evidence only: feeds no headline or behavioral metric.
        _diagnostic_items, diagnostic_probe = await run_retrieval_probe(
            ctx, phase="evaluate-diagnostic", query_text=self._transfer_goal()
        )

        stats = await ctx.memory.stats()
        metrics: dict[str, float | int | str | None] = {
            "task_success": behavior["transfer_success"],
            **behavior,
            **retrieval,
            "retrieval_evidence_source": "run_log.steps[0].retrieved_items",
            "llm_calls": self.transfer_log.llm_calls,
            "total_prompt_tokens": self.transfer_log.total_prompt_tokens,
            "total_completion_tokens": self.transfer_log.total_completion_tokens,
            "token_cost": (
                self.transfer_log.total_prompt_tokens
                + self.transfer_log.total_completion_tokens
            ),
            "avg_add_latency_ms": stats.extra.get("avg_add_latency_ms"),
            "avg_retrieve_latency_ms": stats.extra.get("avg_retrieve_latency_ms"),
        }

        return ScenarioResult(
            scenario=self.name,
            episode_id=ctx.episode_id,
            seed=ctx.seed,
            memory_backend=stats.backend,
            success=behavior["transfer_success"] == 1,
            metrics=metrics,
            run_log=self.transfer_log,
            params=self.params,
            retrieval_probes=[diagnostic_probe],
            evaluation_ground_truth=ground_truth,
            observed_action_results=[self.source_action_result],
        )

    async def _evaluate_legacy(self, ctx: ScenarioContext) -> ScenarioResult:
        """The pre-TASK-020 evaluation path, unchanged: adaptation,
        navigation, cost, and memory latency."""

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
