"""M15.1 long-lived memory with real session boundaries and a route task.

``lifetime_v1`` keeps one backend episode scope across multiple semantic
sessions.  Every AgentRunner call owns a fresh working transcript, while the
long-term MemoryBackend persists until the post-result fairness reset.

The key route fact is derived from a real observation of the
``lifetime_route_v1`` fixture.  Later events are true observed session facts;
similar distractors never assert a false location for the target resource.
"""

from __future__ import annotations

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
    LifetimeGroundTruth,
    Scenario,
    ScenarioContext,
    ScenarioParamError,
    ScenarioResult,
    ScenarioRunLog,
    run_retrieval_probe,
)
from .controlled import controlled_event_identity

SEMANTICS_LIFETIME_V1 = "lifetime_v1"
ITEM_NAME = "lifetime_token"
RECIPIENT = "Steve"
# Backend-independent exploration path used only in the experience phase. The
# route is fixed before any observation; evaluation truth is constructed from
# whichever real dropped item is actually encountered.
EXPERIENCE_SURVEY_WAYPOINTS = (
    Position(x=20.0, y=64.0, z=0.0),
    Position(x=40.0, y=64.0, z=0.0),
)
FINAL_GOAL = (
    "Recover the lifetime token from the old field cache and deliver it to Steve."
)
FINAL_MAX_STEPS = 8
_POSITION_TOLERANCE = 2.0


class LifetimeObservationError(RuntimeError):
    """The fixture did not produce the real observation required by v1."""


def _distance(a: Position, b: Position) -> float:
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def compute_lifetime_retrieval_metrics(
    first_items: Sequence[MemoryItem | MemoryItemSnapshot],
    all_steps: Sequence[RunStep],
    *,
    target_event_id: str,
    similar_event_ids: Collection[str],
) -> dict[str, float | int | None]:
    """Causal retrieval endpoints for the final route run."""

    first_ids = [item.event.event_id for item in first_items]
    target_rank: int | None = None
    for index, event_id in enumerate(first_ids):
        if event_id == target_event_id:
            target_rank = index + 1
            break

    first_target_count = sum(event_id == target_event_id for event_id in first_ids)
    similar_ids = set(similar_event_ids)
    similar_count = sum(event_id in similar_ids for event_id in first_ids)
    all_known_ids = {target_event_id, *similar_ids}
    irrelevant_count = sum(event_id not in all_known_ids for event_id in first_ids)

    first_target_step: int | None = None
    for step in all_steps:
        if any(
            item.event.event_id == target_event_id for item in step.retrieved_items
        ):
            first_target_step = step.index
            break

    denominator = len(first_ids)
    return {
        "target_recall_first_decision": 1 if first_target_count else 0,
        "target_retrieval_rank_first_decision": target_rank,
        "target_recall_any_decision": 1 if first_target_step is not None else 0,
        "first_target_retrieval_step": first_target_step,
        "target_retrieval_precision": (
            round(first_target_count / denominator, 4) if denominator else None
        ),
        "similar_retrieval_rate": (
            round(similar_count / denominator, 4) if denominator else None
        ),
        "irrelevant_retrieval_rate": (
            round(irrelevant_count / denominator, 4) if denominator else None
        ),
        "retrieved_item_count": denominator,
    }


def compute_lifetime_behavior_metrics(
    steps: Sequence[RunStep],
    *,
    target_event_id: str,
    item_name: str,
    pickup_position: Position,
    recipient: str,
) -> dict[str, int | None]:
    """Strict ordered route behavior and deterministic utilization evidence."""

    def completed(step: RunStep) -> bool:
        return step.action_status is ActionStatus.COMPLETED

    def approaches_pickup(step: RunStep) -> bool:
        if step.action != "move_to" or not completed(step):
            return False
        try:
            destination = Position(
                x=float(step.arguments["x"]),
                y=float(step.arguments["y"]),
                z=float(step.arguments["z"]),
            )
        except (KeyError, TypeError, ValueError):
            return False
        return _distance(destination, pickup_position) <= _POSITION_TOLERANCE

    def is_collect(step: RunStep) -> bool:
        return step.action == "collect_item" and step.arguments.get("name") == item_name

    def is_give(step: RunStep) -> bool:
        return (
            step.action == "give_item"
            and step.arguments.get("item") == item_name
            and step.arguments.get("username") == recipient
        )

    first_collect = next((i for i, step in enumerate(steps) if is_collect(step)), None)
    completed_collect = next(
        (i for i, step in enumerate(steps) if is_collect(step) and completed(step)),
        None,
    )
    first_give = next((i for i, step in enumerate(steps) if is_give(step)), None)
    completed_give = next(
        (i for i, step in enumerate(steps) if is_give(step) and completed(step)),
        None,
    )

    approached_before = 1 if (
        first_collect is not None
        and any(approaches_pickup(step) for step in steps[:first_collect])
    ) else 0

    recipient_visible_before_give = 0
    if first_give is not None:
        state = steps[first_give].world_state
        if state is not None and any(
            player.username == recipient for player in state.nearby_players
        ):
            recipient_visible_before_give = 1

    invalid_collect = 1 if (
        first_collect is not None
        and (approached_before == 0 or not completed(steps[first_collect]))
    ) else 0
    invalid_give = 1 if (
        first_give is not None
        and (
            completed_collect is None
            or first_give <= completed_collect
            or recipient_visible_before_give == 0
            or not completed(steps[first_give])
        )
    ) else 0

    primary_success = 1 if (
        first_collect is not None
        and completed_collect == first_collect
        and approached_before == 1
        and first_give is not None
        and completed_give == first_give
        and completed_collect < first_give
        and recipient_visible_before_give == 1
    ) else 0

    eventual_recovery = 1 if (
        (invalid_collect or invalid_give)
        and completed_collect is not None
        and completed_give is not None
        and completed_collect < completed_give
    ) else 0

    target_retrieved_through_step = False
    utilization: int | None = None
    for step in steps:
        if any(
            item.event.event_id == target_event_id for item in step.retrieved_items
        ):
            target_retrieved_through_step = True
        if approaches_pickup(step):
            utilization = 1 if target_retrieved_through_step else None
            break

    meaningful = sum(
        1
        for step in steps
        if completed(step)
        and step.action in {"move_to", "follow_player", "collect_item", "give_item"}
    )
    return {
        "target_route_utilization": utilization,
        "approached_pickup_before_first_collect": approached_before,
        "collect_completed": 1 if completed_collect is not None else 0,
        "returned_before_first_give": recipient_visible_before_give,
        "delivery_completed": 1 if completed_give is not None else 0,
        "invalid_collect_attempt": invalid_collect,
        "invalid_give_attempt": invalid_give,
        "eventual_recovery_after_invalid_attempt": eventual_recovery,
        "meaningful_action_count": meaningful,
        "task_success": primary_success,
    }


def is_completed_delivery(step: RunStep) -> bool:
    """Return whether raw step evidence proves the lifetime goal is terminal."""

    return (
        step.action == "give_item"
        and step.arguments.get("item") == ITEM_NAME
        and step.arguments.get("username") == RECIPIENT
        and step.action_status is ActionStatus.COMPLETED
    )


class LongLivedMemoryScenario(Scenario):
    """Cross-session lifetime pressure plus a meaningful delivery route."""

    name: ClassVar[str] = "long_lived_memory"
    default_params: ClassVar[dict[str, Any]] = {
        "lifetime_event_count": 20,
        "session_count": 4,
        "relevant_update_count": 2,
        "similar_event_count": 5,
        "lifetime_semantics_version": SEMANTICS_LIFETIME_V1,
    }

    def __init__(self) -> None:
        self.initial_position: Position | None = None
        self.recipient_position: Position | None = None
        self.pickup_position: Position | None = None
        self.target_event_id: str | None = None
        self.relevant_event_ids: list[str] = []
        self.similar_event_ids: list[str] = []
        self.neutral_event_ids: list[str] = []
        self.session_logs: list[RunLog] = []
        self.final_log: RunLog | None = None
        self.observed_results: list[ActionResult] = []
        self._controlled_ordinals: dict[str, int] = {}

    def _validate_params(self) -> None:
        for name, minimum in (
            ("lifetime_event_count", 2),
            ("session_count", 1),
            ("relevant_update_count", 0),
            ("similar_event_count", 0),
        ):
            self._require_int_param(name, minimum)
        if self._params["lifetime_semantics_version"] != SEMANTICS_LIFETIME_V1:
            raise ScenarioParamError(
                f"{self.name}: lifetime_semantics_version must be "
                f"{SEMANTICS_LIFETIME_V1!r}"
            )
        remaining = self._params["lifetime_event_count"] - 1
        if remaining < self._params["session_count"]:
            raise ScenarioParamError(
                f"{self.name}: lifetime_event_count - 1 must be >= session_count"
            )
        classified = (
            self._params["relevant_update_count"]
            + self._params["similar_event_count"]
        )
        if classified > remaining:
            raise ScenarioParamError(
                f"{self.name}: relevant_update_count + similar_event_count "
                "cannot exceed lifetime_event_count - 1"
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
            and self.params["lifetime_semantics_version"] != SEMANTICS_LIFETIME_V1
        ):
            raise ScenarioParamError(
                f"{self.name}: Controlled mode requires lifetime_v1"
            )
        state = await ctx.bot.get_state()
        recipient = next(
            (player for player in state.nearby_players if player.username == RECIPIENT),
            None,
        )
        if recipient is None:
            raise LifetimeObservationError(
                f"{self.name}: recipient {RECIPIENT!r} must be actually visible"
            )
        self.initial_position = state.position
        self.recipient_position = recipient.position

    async def experience_phase(self, ctx: ScenarioContext) -> None:
        assert self.initial_position is not None
        assert self.recipient_position is not None
        item = None
        for waypoint in EXPERIENCE_SURVEY_WAYPOINTS:
            observed = await ctx.bot.execute(
                "move_to", waypoint.model_dump(mode="json")
            )
            if (
                observed.status is not ActionStatus.COMPLETED
                or observed.state_after is None
            ):
                raise LifetimeObservationError(
                    f"{self.name}: survey observation move did not complete"
                )
            self.observed_results.append(observed)
            item = next(
                (
                    entity
                    for entity in observed.state_after.nearby_entities
                    if entity.kind is EntityKind.ITEM and entity.name == ITEM_NAME
                ),
                None,
            )
            if item is not None:
                break
        if item is None:
            raise LifetimeObservationError(
                f"{self.name}: lifetime_token was not actually observed by the survey"
            )
        self.pickup_position = item.position

        event_id, timestamp = self._next_identity(ctx, "experience")
        event = ExperienceEvent(
            event_id=event_id,
            episode_id=ctx.episode_id,
            timestamp=timestamp,
            actor="agent",
            target=ITEM_NAME,
            event_type=EventType.RESOURCE_DISCOVERED,
            location=item.position,
            context={
                "subject": "old_field_cache",
                "resource": ITEM_NAME,
                "x": item.position.x,
                "y": item.position.y,
                "z": item.position.z,
                "recipient": RECIPIENT,
                "recipient_x": self.recipient_position.x,
                "recipient_y": self.recipient_position.y,
                "recipient_z": self.recipient_position.z,
            },
            outcome="observed_available",
        )
        await ctx.memory.add(event)
        self.target_event_id = event.event_id

        returned = await ctx.bot.execute(
            "move_to", self.initial_position.model_dump(mode="json")
        )
        if returned.status is not ActionStatus.COMPLETED:
            raise LifetimeObservationError(
                f"{self.name}: could not return after route observation"
            )
        self.observed_results.append(returned)

    def _session_position(self, seed: int, session_index: int) -> Position:
        rng = random.Random(seed + 50_000 + session_index)
        return Position(
            x=float(rng.randint(-6, 6)),
            y=64.0,
            z=float(rng.randint(-6, 6)),
        )

    def _event_kinds(self) -> list[str]:
        remaining = self.params["lifetime_event_count"] - 1
        kinds = ["relevant"] * self.params["relevant_update_count"]
        kinds.extend(["similar"] * self.params["similar_event_count"])
        kinds.extend(["neutral"] * (remaining - len(kinds)))
        return kinds

    async def _add_session_event(
        self,
        ctx: ScenarioContext,
        *,
        kind: str,
        ordinal: int,
        session_index: int,
        anchor_result: ActionResult,
    ) -> None:
        assert anchor_result.state_after is not None
        position = anchor_result.state_after.position
        event_id, timestamp = self._next_identity(ctx, "interference")

        if kind == "relevant":
            assert self.pickup_position is not None
            revisit = await ctx.bot.execute(
                "move_to", self.pickup_position.model_dump(mode="json")
            )
            if revisit.status is not ActionStatus.COMPLETED or revisit.state_after is None:
                raise LifetimeObservationError(
                    f"{self.name}: relevant update revisit did not complete"
                )
            present = any(
                entity.kind is EntityKind.ITEM and entity.name == ITEM_NAME
                for entity in revisit.state_after.nearby_entities
            )
            if not present:
                raise LifetimeObservationError(
                    f"{self.name}: relevant update did not observe lifetime_token"
                )
            self.observed_results.append(revisit)
            event = ExperienceEvent(
                event_id=event_id,
                episode_id=ctx.episode_id,
                timestamp=timestamp,
                actor="agent",
                target=ITEM_NAME,
                event_type=EventType.WORLD_FACT_UPDATED,
                context={
                    "subject": "old_field_cache_status",
                    "resource": ITEM_NAME,
                    "session": session_index,
                    "observation": "still_available",
                },
                outcome="observed_available",
            )
            self.relevant_event_ids.append(event.event_id)
            await ctx.memory.add(event)
            restored = await ctx.bot.execute(
                "move_to", position.model_dump(mode="json")
            )
            if restored.status is not ActionStatus.COMPLETED:
                raise LifetimeObservationError(
                    f"{self.name}: could not restore session anchor"
                )
            return

        if kind == "similar":
            event = ExperienceEvent(
                event_id=event_id,
                episode_id=ctx.episode_id,
                timestamp=timestamp,
                actor="agent",
                target=f"survey-waypoint-{ctx.seed}-{ordinal}",
                event_type=EventType.LOCATION_DISCOVERED,
                location=position,
                context={
                    "subject": "archive_field_survey_waypoint",
                    "waypoint_key": f"survey-{ctx.seed}-{ordinal}",
                    "session": session_index,
                    "x": position.x,
                    "y": position.y,
                    "z": position.z,
                },
                outcome="visited",
            )
            self.similar_event_ids.append(event.event_id)
        else:
            event = ExperienceEvent(
                event_id=event_id,
                episode_id=ctx.episode_id,
                timestamp=timestamp,
                actor="agent",
                target=f"lifetime-session-{session_index}",
                event_type=EventType.LOCATION_DISCOVERED,
                location=position,
                context={
                    "subject": "session_activity",
                    "activity_key": f"activity-{ctx.seed}-{ordinal}",
                    "session": session_index,
                    "x": position.x,
                    "y": position.y,
                    "z": position.z,
                },
                outcome="visited",
            )
            self.neutral_event_ids.append(event.event_id)
        await ctx.memory.add(event)

    async def interference_phase(self, ctx: ScenarioContext) -> None:
        kinds = self._event_kinds()
        per_session: list[list[tuple[int, str]]] = [
            [] for _ in range(self.params["session_count"])
        ]
        for ordinal, kind in enumerate(kinds):
            per_session[ordinal % len(per_session)].append((ordinal, kind))

        self.session_logs = []
        for session_index, assignments in enumerate(per_session):
            waypoint = self._session_position(ctx.seed, session_index)
            log = await ctx.runner.run_goal(
                goal=(
                    f"Travel to survey waypoint ({waypoint.x}, {waypoint.y}, "
                    f"{waypoint.z}) for session {session_index + 1}."
                ),
                max_steps=1,
                success_at=waypoint,
                episode_id=ctx.episode_id,
            )
            self.session_logs.append(log)
            anchor = await ctx.bot.execute(
                "move_to", waypoint.model_dump(mode="json")
            )
            if anchor.status is not ActionStatus.COMPLETED or anchor.state_after is None:
                raise LifetimeObservationError(
                    f"{self.name}: session {session_index} anchor failed"
                )
            for ordinal, kind in assignments:
                await self._add_session_event(
                    ctx,
                    kind=kind,
                    ordinal=ordinal,
                    session_index=session_index,
                    anchor_result=anchor,
                )

    async def test_phase(self, ctx: ScenarioContext) -> None:
        self.final_log = await ctx.runner.run_goal(
            goal=FINAL_GOAL,
            max_steps=FINAL_MAX_STEPS,
            success_when=is_completed_delivery,
            episode_id=ctx.episode_id,
        )

    async def evaluate(self, ctx: ScenarioContext) -> ScenarioResult:
        assert self.final_log is not None
        assert self.target_event_id is not None
        assert self.pickup_position is not None
        assert self.recipient_position is not None

        first_items = (
            self.final_log.steps[0].retrieved_items if self.final_log.steps else []
        )
        retrieval = compute_lifetime_retrieval_metrics(
            first_items,
            self.final_log.steps,
            target_event_id=self.target_event_id,
            similar_event_ids=self.similar_event_ids,
        )
        behavior = compute_lifetime_behavior_metrics(
            self.final_log.steps,
            target_event_id=self.target_event_id,
            item_name=ITEM_NAME,
            pickup_position=self.pickup_position,
            recipient=RECIPIENT,
        )
        ground_truth = LifetimeGroundTruth(
            semantics_version=SEMANTICS_LIFETIME_V1,
            target_event_id=self.target_event_id,
            item_name=ITEM_NAME,
            pickup_position=self.pickup_position,
            recipient=RECIPIENT,
            recipient_position=self.recipient_position,
            relevant_update_event_ids=list(self.relevant_event_ids),
            similar_event_ids=list(self.similar_event_ids),
            neutral_event_ids=list(self.neutral_event_ids),
        )
        _items, diagnostic_probe = await run_retrieval_probe(
            ctx,
            phase="evaluate-diagnostic",
            query_text=FINAL_GOAL,
        )
        stats = await ctx.memory.stats()
        all_logs = [*self.session_logs, self.final_log]
        offered = 1 + len(self.relevant_event_ids) + len(self.similar_event_ids) + len(
            self.neutral_event_ids
        )
        metrics: dict[str, float | int | str | None] = {
            "offered_event_count": offered,
            "target_event_offered": 1,
            "relevant_update_event_count": len(self.relevant_event_ids),
            "similar_event_count": len(self.similar_event_ids),
            "neutral_event_count": len(self.neutral_event_ids),
            **retrieval,
            **behavior,
            "retrieval_evidence_source": "run_log.steps[*].retrieved_items",
            "llm_calls": sum(log.llm_calls for log in all_logs),
            "total_prompt_tokens": sum(log.total_prompt_tokens for log in all_logs),
            "total_completion_tokens": sum(
                log.total_completion_tokens for log in all_logs
            ),
            "token_cost": sum(
                log.total_prompt_tokens + log.total_completion_tokens
                for log in all_logs
            ),
            "avg_add_latency_ms": stats.extra.get("avg_add_latency_ms"),
            "avg_retrieve_latency_ms": stats.extra.get("avg_retrieve_latency_ms"),
        }
        labeled_logs = [
            ScenarioRunLog(
                phase="semantic_session",
                session_id=f"session-{index + 1}",
                ordinal=index,
                run_log=log,
            )
            for index, log in enumerate(self.session_logs)
        ]
        labeled_logs.append(
            ScenarioRunLog(
                phase="final_task",
                session_id="final",
                ordinal=len(labeled_logs),
                run_log=self.final_log,
            )
        )
        return ScenarioResult(
            scenario=self.name,
            episode_id=ctx.episode_id,
            seed=ctx.seed,
            memory_backend=stats.backend,
            success=behavior["task_success"] == 1,
            metrics=metrics,
            run_log=self.final_log,
            run_logs=labeled_logs,
            params=self.params,
            retrieval_probes=[diagnostic_probe],
            evaluation_ground_truth=ground_truth,
            observed_action_results=list(self.observed_results),
        )
