"""M15.1 transfer by discriminating among heterogeneous real failures.

Every source event is derived one-for-one from a failed environment
``ActionResult``.  One failure family applies to the final transfer entity;
the other source failures are deliberately similar but require different
resources.  Applicability labels and the answer remain evaluation-only.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Sequence
from dataclasses import dataclass
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
)
from ..core.runner import RunLog, RunStep
from ..memory.base import MemoryItem, MemoryItemSnapshot
from .base import (
    ApplicabilityFailureGroundTruth,
    ObservedPreconditionApplicabilityGroundTruth,
    Scenario,
    ScenarioContext,
    ScenarioParamError,
    ScenarioResult,
    run_retrieval_probe,
)
from .controlled import controlled_event_identity
from .failure_learning import (
    ObservedPreconditionError,
    compute_transfer_behavior_metrics,
)

SEMANTICS_OBSERVED_PRECONDITION_APPLICABILITY_V4 = (
    "observed_precondition_applicability_v4"
)
TASK_FAMILY = "guarded_hostile"
_TRANSFER_MAX_STEPS = 5


@dataclass(frozen=True)
class FailureFamily:
    """Environment-visible source/transfer pair sharing one hidden rule."""

    name: str
    source_entity: str
    transfer_entity: str
    required_item: str


FAILURE_FAMILIES: tuple[FailureFamily, ...] = (
    FailureFamily("alpha", "alpha_zombie", "alpha_creeper", "iron_ingot"),
    FailureFamily("beta", "beta_skeleton", "beta_stray", "string"),
    FailureFamily("gamma", "gamma_spider", "gamma_cave_spider", "gold_nugget"),
)


def failure_applicability_plan(
    seed: int, observed_failure_count: int
) -> tuple[tuple[FailureFamily, ...], FailureFamily]:
    """Return 2-3 source families and the target family for one seed.

    Exactly one source belongs to the transfer family.  The remaining
    failures are different real prerequisite families.  Seed blocks rotate
    whether the applicable experience appears first or second so chronology
    cannot be a universal answer; increasing count from two to three is
    prefix-stable for a fixed seed.
    """

    target_index = seed % len(FAILURE_FAMILIES)
    target = FAILURE_FAMILIES[target_index]
    distractors = tuple(
        FAILURE_FAMILIES[(target_index + offset) % len(FAILURE_FAMILIES)]
        for offset in range(1, len(FAILURE_FAMILIES))
    )
    ordered = (
        (distractors[0], target, distractors[1])
        if seed % 2
        else (target, distractors[0], distractors[1])
    )
    return tuple(ordered[:observed_failure_count]), target


def source_transfer_entities_multi(
    seed: int, observed_failure_count: int
) -> tuple[tuple[str, ...], str]:
    """Backward-compatible selector surface, now backed by v4 families."""

    sources, target = failure_applicability_plan(seed, observed_failure_count)
    return tuple(family.source_entity for family in sources), target.transfer_entity


def compute_multi_failure_retrieval_metrics(
    items: Sequence[MemoryItem | MemoryItemSnapshot],
    relevant_failure_event_ids: Sequence[str],
    irrelevant_failure_event_ids: Sequence[str],
    interference_event_ids: Collection[str],
) -> dict[str, float | int | None]:
    """Measure retrieval and discrimination against evaluation-only ids."""

    retrieved_ids = [item.event.event_id for item in items]
    relevant = set(relevant_failure_event_ids)
    irrelevant = set(irrelevant_failure_event_ids)
    neutral = set(interference_event_ids)
    relevant_ranks = [
        index + 1
        for index, event_id in enumerate(retrieved_ids)
        if event_id in relevant
    ]
    irrelevant_ranks = [
        index + 1
        for index, event_id in enumerate(retrieved_ids)
        if event_id in irrelevant
    ]
    relevant_count = len(relevant_ranks)
    irrelevant_count = len(irrelevant_ranks)
    neutral_count = sum(event_id in neutral for event_id in retrieved_ids)
    item_count = len(retrieved_ids)
    failure_count = relevant_count + irrelevant_count
    metrics: dict[str, float | int | None] = {
        "relevant_failure_recall": round(relevant_count / len(relevant), 4),
        "irrelevant_failure_retrieval": irrelevant_count,
        "irrelevant_failure_retrieval_rate": (
            round(irrelevant_count / item_count, 4) if item_count else None
        ),
        "failure_rank": min(relevant_ranks) if relevant_ranks else None,
        "relevant_failure_rank": min(relevant_ranks) if relevant_ranks else None,
        "best_irrelevant_failure_rank": (
            min(irrelevant_ranks) if irrelevant_ranks else None
        ),
        "failure_retrieval_precision": (
            round(relevant_count / failure_count, 4) if failure_count else None
        ),
        "neutral_interference_retrieval_rate": (
            round(neutral_count / item_count, 4) if item_count else None
        ),
        "retrieved_failure_count": failure_count,
        "retrieved_item_count": item_count,
    }
    for index, event_id in enumerate(relevant_failure_event_ids, start=1):
        metrics[f"relevant_failure_{index}_rank"] = next(
            (
                rank
                for rank, retrieved_event_id in enumerate(retrieved_ids, start=1)
                if retrieved_event_id == event_id
            ),
            None,
        )
    for index, event_id in enumerate(irrelevant_failure_event_ids, start=1):
        metrics[f"irrelevant_failure_{index}_rank"] = next(
            (
                rank
                for rank, retrieved_event_id in enumerate(retrieved_ids, start=1)
                if retrieved_event_id == event_id
            ),
            None,
        )
    return metrics


def wrong_preparation_before_first_attack(
    steps: Sequence[RunStep],
    *,
    transfer_entity: str,
    transfer_entity_id: int,
    required_item: str,
) -> int:
    """Whether a completed wrong-item equip precedes the first attempt."""

    first_attack = next(
        (
            index
            for index, step in enumerate(steps)
            if step.action == "attack_entity"
            and (
                step.arguments.get("entity_id") == transfer_entity_id
                or step.arguments.get("name") == transfer_entity
            )
        ),
        len(steps),
    )
    return int(
        any(
            step.action == "equip_item"
            and step.action_status is ActionStatus.COMPLETED
            and step.arguments.get("item") != required_item
            for step in steps[:first_attack]
        )
    )


def is_completed_transfer_attack(
    step: RunStep, *, transfer_entity: str, transfer_entity_id: int
) -> bool:
    """Return whether raw step evidence proves the transfer target completed."""

    return (
        step.action == "attack_entity"
        and step.action_status is ActionStatus.COMPLETED
        and (
            step.arguments.get("entity_id") == transfer_entity_id
            or step.arguments.get("name") == transfer_entity
        )
    )


class FailureLearningMultiScenario(Scenario):
    """Observe heterogeneous failures and apply only the relevant one."""

    name: ClassVar[str] = "failure_learning_multi"
    default_params: ClassVar[dict[str, Any]] = {
        "failure_semantics_version": (
            SEMANTICS_OBSERVED_PRECONDITION_APPLICABILITY_V4
        ),
        "observed_failure_count": 2,
        "interference_count": 0,
    }

    def __init__(self) -> None:
        self.source_families: tuple[FailureFamily, ...] = ()
        self.target_family: FailureFamily | None = None
        self.entity_ids: dict[str, int] = {}
        self.source_results: list[ActionResult] = []
        self.source_failure_event_ids: list[str] = []
        self.relevant_failure_event_ids: list[str] = []
        self.irrelevant_failure_event_ids: list[str] = []
        self.interference_event_ids: list[str] = []
        self.transfer_log: RunLog | None = None
        self._controlled_ordinals: dict[str, int] = {}

    def _validate_params(self) -> None:
        self._require_int_param("observed_failure_count", 2)
        if self._params["observed_failure_count"] > 3:
            raise ScenarioParamError(
                f"{self.name}: observed_failure_count must be <= 3"
            )
        self._require_int_param("interference_count", 0)
        if (
            self._params["failure_semantics_version"]
            != SEMANTICS_OBSERVED_PRECONDITION_APPLICABILITY_V4
        ):
            raise ScenarioParamError(
                f"{self.name}: failure_semantics_version must be "
                f"{SEMANTICS_OBSERVED_PRECONDITION_APPLICABILITY_V4!r}"
            )

    def _next_identity(
        self, ctx: ScenarioContext, phase: str
    ) -> tuple[str, datetime]:
        if ctx.campaign_mode != CAMPAIGN_MODE_CONTROLLED:
            return new_event_id(), datetime.now(UTC)
        ordinal = self._controlled_ordinals.get(phase, 0)
        self._controlled_ordinals[phase] = ordinal + 1
        return controlled_event_identity(
            seed=ctx.seed, params=self.params, phase=phase, ordinal=ordinal
        )

    async def setup(self, ctx: ScenarioContext) -> None:
        if (
            ctx.campaign_mode == CAMPAIGN_MODE_CONTROLLED
            and self.params["failure_semantics_version"]
            != SEMANTICS_OBSERVED_PRECONDITION_APPLICABILITY_V4
        ):
            raise ScenarioParamError(
                f"{self.name}: Controlled mode requires applicability v4"
            )
        self.source_families, self.target_family = failure_applicability_plan(
            ctx.seed, self.params["observed_failure_count"]
        )
        state = await ctx.bot.get_state()
        names = [
            *(family.source_entity for family in self.source_families),
            self.target_family.transfer_entity,
        ]
        self.entity_ids = {}
        for name in names:
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
                    f"{self.name}: heterogeneous fixture missing hostile {name!r}"
                )
            self.entity_ids[name] = match.id

    async def experience_phase(self, ctx: ScenarioContext) -> None:
        assert self.target_family is not None
        self.source_results = []
        self.source_failure_event_ids = []
        self.relevant_failure_event_ids = []
        self.irrelevant_failure_event_ids = []
        for family in self.source_families:
            source_name = family.source_entity
            pre_state = await ctx.bot.get_state()
            if pre_state.equipped.hand is not None:
                raise ObservedPreconditionError(
                    f"{self.name}: source failures must start unequipped"
                )
            source = next(
                entity
                for entity in pre_state.nearby_entities
                if entity.id == self.entity_ids[source_name]
            )
            result = await ctx.bot.execute(
                "attack_entity", {"entity_id": self.entity_ids[source_name]}
            )
            state_after = result.state_after or await ctx.bot.get_state()
            if result.status is not ActionStatus.FAILED:
                raise ObservedPreconditionError(
                    f"{self.name}: source attack on {source_name!r} must fail"
                )
            if not result.error:
                raise ObservedPreconditionError(
                    f"{self.name}: source failure on {source_name!r} has no error"
                )
            if not any(
                entity.id == self.entity_ids[source_name]
                for entity in state_after.nearby_entities
            ):
                raise ObservedPreconditionError(
                    f"{self.name}: failed source {source_name!r} disappeared"
                )
            self.source_results.append(result)
            event_id, timestamp = self._next_identity(ctx, "experience")
            event = ExperienceEvent(
                event_id=event_id,
                episode_id=ctx.episode_id,
                timestamp=timestamp,
                actor="agent",
                target=source_name,
                event_type=EventType.TASK_FAILED,
                location=source.position,
                context={
                    "task_family": TASK_FAMILY,
                    "entity": source_name,
                    "action": "attack_entity",
                    "status": result.status.value,
                    "error": result.error,
                    "equipped_before": None,
                },
                outcome=result.status.value,
            )
            await ctx.memory.add(event)
            self.source_failure_event_ids.append(event.event_id)
            if family.name == self.target_family.name:
                self.relevant_failure_event_ids.append(event.event_id)
            else:
                self.irrelevant_failure_event_ids.append(event.event_id)

        if len(self.relevant_failure_event_ids) != 1:
            raise ObservedPreconditionError(
                f"{self.name}: expected exactly one applicable real failure"
            )

    async def interference_phase(self, ctx: ScenarioContext) -> None:
        self.interference_event_ids = []
        for ordinal in range(self.params["interference_count"]):
            event_id, timestamp = self._next_identity(ctx, "interference")
            digest = hashlib.sha256(
                f"failure_learning_multi/v4/{ctx.seed}/{ordinal}".encode("utf-8")
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

    def _transfer_goal(self) -> str:
        assert self.target_family is not None
        return (
            f"Eliminate the guarded hostile {self.target_family.transfer_entity} "
            "to secure the relief route."
        )

    async def test_phase(self, ctx: ScenarioContext) -> None:
        assert self.target_family is not None
        transfer_entity = self.target_family.transfer_entity
        transfer_entity_id = self.entity_ids[transfer_entity]
        self.transfer_log = await ctx.runner.run_goal(
            goal=self._transfer_goal(),
            max_steps=_TRANSFER_MAX_STEPS,
            success_when=lambda step: is_completed_transfer_attack(
                step,
                transfer_entity=transfer_entity,
                transfer_entity_id=transfer_entity_id,
            ),
            episode_id=ctx.episode_id,
        )

    async def evaluate(self, ctx: ScenarioContext) -> ScenarioResult:
        assert self.transfer_log is not None
        assert self.target_family is not None
        transfer_entity = self.target_family.transfer_entity
        required_item = self.target_family.required_item
        transfer_id = self.entity_ids[transfer_entity]
        behavior = compute_transfer_behavior_metrics(
            self.transfer_log.steps,
            transfer_entity=transfer_entity,
            transfer_entity_id=transfer_id,
            required_item=required_item,
        )
        behavior["wrong_preparation"] = wrong_preparation_before_first_attack(
            self.transfer_log.steps,
            transfer_entity=transfer_entity,
            transfer_entity_id=transfer_id,
            required_item=required_item,
        )
        behavior["preparation_before_first_attempt"] = behavior[
            "prepared_before_first_transfer_attack"
        ]
        first_items = (
            self.transfer_log.steps[0].retrieved_items
            if self.transfer_log.steps
            else []
        )
        retrieval = compute_multi_failure_retrieval_metrics(
            first_items,
            self.relevant_failure_event_ids,
            self.irrelevant_failure_event_ids,
            self.interference_event_ids,
        )
        ground_truth = ObservedPreconditionApplicabilityGroundTruth(
            semantics_version=(
                SEMANTICS_OBSERVED_PRECONDITION_APPLICABILITY_V4
            ),
            task_family=TASK_FAMILY,
            source_failures=[
                ApplicabilityFailureGroundTruth(
                    event_id=event_id,
                    entity=family.source_entity,
                    required_item=family.required_item,
                    applicable_to_transfer=(family.name == self.target_family.name),
                    expected_error=result.error or "",
                )
                for family, event_id, result in zip(
                    self.source_families,
                    self.source_failure_event_ids,
                    self.source_results,
                    strict=True,
                )
            ],
            relevant_failure_event_ids=list(self.relevant_failure_event_ids),
            irrelevant_failure_event_ids=list(self.irrelevant_failure_event_ids),
            transfer_entity=transfer_entity,
            required_item=required_item,
            expected_source_action="attack_entity",
            expected_source_status=ActionStatus.FAILED.value,
            interference_event_ids=list(self.interference_event_ids),
        )
        _items, diagnostic_probe = await run_retrieval_probe(
            ctx,
            phase="evaluate-diagnostic",
            query_text=self._transfer_goal(),
        )
        stats = await ctx.memory.stats()
        metrics: dict[str, float | int | str | None] = {
            "task_success": behavior["transfer_success"],
            **behavior,
            **retrieval,
            "observed_failure_count": len(self.source_results),
            "relevant_source_failure_count": len(
                self.relevant_failure_event_ids
            ),
            "irrelevant_source_failure_count": len(
                self.irrelevant_failure_event_ids
            ),
            "retrieval_evidence_source": (
                "run_log.steps[0].retrieved_items"
            ),
            "llm_calls": self.transfer_log.llm_calls,
            "total_prompt_tokens": self.transfer_log.total_prompt_tokens,
            "total_completion_tokens": (
                self.transfer_log.total_completion_tokens
            ),
            "token_cost": (
                self.transfer_log.total_prompt_tokens
                + self.transfer_log.total_completion_tokens
            ),
            "avg_add_latency_ms": stats.extra.get("avg_add_latency_ms"),
            "avg_retrieve_latency_ms": stats.extra.get(
                "avg_retrieve_latency_ms"
            ),
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
            observed_action_results=list(self.source_results),
        )
