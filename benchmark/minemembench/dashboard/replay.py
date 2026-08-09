"""Pure deterministic replay from stored ScenarioResult evidence."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from ..core.models import Position
from ..core.runner import RunStep
from ..scenarios.base import ScenarioResult, ScenarioRunLog
from .models import (
    OutcomeEvidence,
    PlannerEvidence,
    ReplayDocument,
    ReplayFrame,
    RetrievalEvidence,
    TimelineEvent,
    TrajectoryPoint,
    TrajectoryMarker,
    UtilizationEvidence,
)


def _position_dict(position: Position) -> dict[str, float]:
    return {"x": position.x, "y": position.y, "z": position.z}


def _near(arguments: dict[str, Any], target: Position, tolerance: float = 2.0) -> bool:
    try:
        point = (
            float(arguments["x"]),
            float(arguments["y"]),
            float(arguments["z"]),
        )
    except (KeyError, TypeError, ValueError):
        return False
    return math.dist(point, (target.x, target.y, target.z)) <= tolerance


def _target_spec(
    result: ScenarioResult,
) -> tuple[set[str], set[str], Position | None, str | None]:
    truth = result.evaluation_ground_truth
    if truth is None:
        return set(), set(), None, None
    version = truth.semantics_version
    if version == "entity_key_v2":
        return (
            {truth.target_event_id},
            set(truth.distractor_event_ids),
            None,
            "target-navigation",
        )
    if version == "key_retention_v2":
        return (
            {truth.target_event_id},
            set(truth.noise_event_ids),
            None,
            "target-navigation",
        )
    if version == "temporal_chain_v2":
        return (
            {truth.current_event_id},
            set(truth.stale_event_ids),
            None,
            "temporal-navigation",
        )
    if version == "observed_precondition_v2":
        return {truth.source_failure_event_id}, set(), None, "failure-preparation"
    if version == "observed_precondition_multi_v3":
        return (
            set(truth.source_failure_event_ids),
            set(truth.interference_event_ids),
            None,
            "failure-preparation",
        )
    if version == "observed_precondition_applicability_v4":
        return (
            set(truth.relevant_failure_event_ids),
            set(truth.irrelevant_failure_event_ids)
            | set(truth.interference_event_ids),
            None,
            "failure-preparation",
        )
    if version == "lifetime_v1":
        return (
            {truth.target_event_id},
            set(truth.similar_event_ids) | set(truth.neutral_event_ids),
            truth.pickup_position,
            "lifetime-route",
        )
    return set(), set(), None, None


def _utilization(
    result: ScenarioResult,
    step: RunStep,
    retrieved_so_far: set[str],
    primary_ids: set[str],
    secondary_ids: set[str],
    retrieved_locations: dict[str, Position],
    target_position: Position | None,
    rule_family: str | None,
) -> UtilizationEvidence:
    primary = sorted(retrieved_so_far & primary_ids)
    secondary = sorted(retrieved_so_far & secondary_ids)
    candidates = [*primary, *secondary]
    if not candidates or rule_family is None:
        return UtilizationEvidence(
            explanation=(
                "No deterministic retrieved-event/action alignment is available; "
                "planner reason text is not utilization proof."
            )
        )
    if rule_family == "failure-preparation":
        truth = result.evaluation_ground_truth
        required_item = getattr(truth, "required_item", None)
        if (
            primary
            and
            step.action == "equip_item"
            and step.arguments.get("item") == required_item
            and step.action_status.value == "completed"
        ):
            return UtilizationEvidence(
                status="supported",
                rule_id="failure-event-before-correct-preparation/v1",
                event_ids=primary,
                explanation="Observed failure memory preceded completed correct preparation.",
            )
    else:
        if (
            target_position is not None
            and primary
            and step.action == "move_to"
            and step.action_status.value == "completed"
            and _near(step.arguments, target_position)
        ):
            return UtilizationEvidence(
                status="supported",
                rule_id=f"{rule_family}-retrieval-before-matching-move/v1",
                event_ids=primary,
                explanation="Declared target memory preceded an objectively matching move.",
            )
        if step.action == "move_to" and step.action_status.value == "completed":
            for event_id in candidates:
                position = retrieved_locations.get(event_id)
                if position is None or not _near(step.arguments, position):
                    continue
                is_primary = event_id in primary_ids
                return UtilizationEvidence(
                    status="supported",
                    rule_id=(
                        f"{rule_family}-retrieval-before-matching-move/v1"
                        if is_primary
                        else f"{rule_family}-alternative-memory-before-matching-move/v1"
                    ),
                    event_ids=[event_id],
                    explanation=(
                        "Declared target memory preceded an objectively matching move."
                        if is_primary
                        else "A retrieved stale/distractor memory preceded its matching move."
                    ),
                )
    return UtilizationEvidence(
        event_ids=candidates,
        explanation=(
            "Relevant memory was retrieved, but this frame has no deterministic "
            "matching action; utilization remains unknown."
        ),
    )


def _ordered_logs(result: ScenarioResult) -> list[ScenarioRunLog]:
    if result.run_logs:
        return list(result.run_logs)
    if result.run_log is None:
        return []
    return [
        ScenarioRunLog(
            phase="primary_run",
            session_id=None,
            ordinal=0,
            run_log=result.run_log,
        )
    ]


def build_replay(result: ScenarioResult) -> ReplayDocument:
    """Build replay without time, network, LLM, bot or backend access."""

    source_json = result.model_dump_json()
    source_digest = hashlib.sha256(source_json.encode("utf-8")).hexdigest()
    primary_ids, secondary_ids, target_position, rule_family = _target_spec(result)
    frames: list[ReplayFrame] = []
    timeline: list[TimelineEvent] = []
    trajectory: list[TrajectoryPoint] = []
    trajectory_markers: list[TrajectoryMarker] = []
    sequence = 0
    trajectory_sequence = 0
    timeline_sequence = 0
    marker_sequence = 0

    for event in result.injected_events:
        timeline.append(
            TimelineEvent(
                sequence=timeline_sequence,
                kind="memory_offered",
                label=(
                    f"MEMORY OFFERED · {event.event_type.value} · "
                    f"{event.target or event.actor}"
                ),
                evidence_ref=event.event_id,
                timestamp=event.timestamp.isoformat(),
            )
        )
        timeline_sequence += 1
    for phase_index, phase_record in enumerate(result.phase_records):
        timeline.append(
            TimelineEvent(
                sequence=timeline_sequence,
                kind="phase",
                label=f"PHASE · {phase_record.phase}",
                phase=phase_record.phase,
                evidence_ref=f"phase_records[{phase_index}]",
                timestamp=phase_record.started_at.isoformat(),
            )
        )
        timeline_sequence += 1

    truth = result.evaluation_ground_truth
    if truth is not None and truth.semantics_version == "lifetime_v1":
        for label, position, reference in (
            ("Known pickup target", truth.pickup_position, truth.target_event_id),
            ("Known recipient", truth.recipient_position, truth.recipient),
        ):
            trajectory_markers.append(
                TrajectoryMarker(
                    sequence=marker_sequence,
                    kind="target",
                    x=position.x,
                    z=position.z,
                    label=label,
                    evidence_ref=reference,
                )
            )
            marker_sequence += 1

    seen_entities: set[tuple[int, float, float]] = set()

    for labeled in _ordered_logs(result):
        log = labeled.run_log
        # Working context does not cross AgentRunner calls. A retrieval from a
        # previous semantic session cannot be credited as utilization later.
        retrieved_so_far: set[str] = set()
        retrieved_locations: dict[str, Position] = {}
        if log.steps and log.steps[0].world_state is not None:
            start = log.steps[0].world_state.position
            trajectory.append(
                TrajectoryPoint(
                    sequence=trajectory_sequence,
                    phase=labeled.phase,
                    session_id=labeled.session_id,
                    x=start.x,
                    z=start.z,
                    point_kind="pre",
                )
            )
            trajectory_sequence += 1
        for step in log.steps:
            if step.world_state is not None:
                for entity in step.world_state.nearby_entities:
                    entity_key = (entity.id, entity.position.x, entity.position.z)
                    if entity_key in seen_entities:
                        continue
                    seen_entities.add(entity_key)
                    trajectory_markers.append(
                        TrajectoryMarker(
                            sequence=marker_sequence,
                            frame_sequence=sequence,
                            kind="entity",
                            x=entity.position.x,
                            z=entity.position.z,
                            label=f"{entity.kind.value} · {entity.name}",
                            evidence_ref=f"frame:{sequence}:world_state:entity:{entity.id}",
                        )
                    )
                    marker_sequence += 1
            step_ids = {item.event.event_id for item in step.retrieved_items}
            retrieved_so_far.update(step_ids)
            for item in step.retrieved_items:
                event = item.event
                position = event.location
                if position is None and all(
                    key in event.context for key in ("x", "y", "z")
                ):
                    try:
                        position = Position(
                            x=float(event.context["x"]),
                            y=float(event.context["y"]),
                            z=float(event.context["z"]),
                        )
                    except (TypeError, ValueError):
                        position = None
                if position is not None:
                    retrieved_locations[event.event_id] = position
            utilization = _utilization(
                result,
                step,
                retrieved_so_far,
                primary_ids,
                secondary_ids,
                retrieved_locations,
                target_position,
                rule_family,
            )
            frames.append(
                ReplayFrame(
                    frame_id=f"run-{labeled.ordinal}-step-{step.index}",
                    sequence=sequence,
                    phase=labeled.phase,
                    session_id=labeled.session_id,
                    run_ordinal=labeled.ordinal,
                    step_index=step.index,
                    retrieval=RetrievalEvidence(
                        observed=True,
                        item_count=len(step.retrieved_items),
                        items=[
                            item.model_dump(mode="json")
                            for item in step.retrieved_items
                        ],
                    ),
                    utilization=utilization,
                    planner=PlannerEvidence(
                        action=step.action,
                        arguments=dict(step.arguments),
                        reason=step.reason,
                        prompt_tokens=step.prompt_tokens,
                        completion_tokens=step.completion_tokens,
                        llm_latency_s=step.latency_s,
                    ),
                    outcome=OutcomeEvidence(
                        status=step.action_status.value,
                        error=step.action_error,
                        result=step.action_result,
                        pre_position=(
                            _position_dict(step.world_state.position)
                            if step.world_state is not None
                            else None
                        ),
                        post_position=_position_dict(step.position),
                    ),
                    world_state=(
                        step.world_state.model_dump(mode="json")
                        if step.world_state is not None
                        else None
                    ),
                    semantic_events=[
                        f"RETRIEVE · {len(step.retrieved_items)} item(s)",
                        f"DECIDE · {step.action}",
                        f"ACTION · {step.action}",
                        f"OUTCOME · {step.action_status.value}",
                    ],
                )
            )
            frame_ref = f"run-{labeled.ordinal}-step-{step.index}"
            for kind, label in (
                ("retrieve", f"RETRIEVE · {len(step.retrieved_items)} item(s)"),
                ("decide", f"DECIDE · {step.action}"),
                ("action", f"ACTION · {step.action}"),
                ("outcome", f"OUTCOME · {step.action_status.value}"),
            ):
                timeline.append(
                    TimelineEvent(
                        sequence=timeline_sequence,
                        frame_sequence=sequence,
                        kind=kind,
                        label=label,
                        phase=labeled.phase,
                        session_id=labeled.session_id,
                        evidence_ref=frame_ref,
                    )
                )
                timeline_sequence += 1
            trajectory.append(
                TrajectoryPoint(
                    sequence=trajectory_sequence,
                    phase=labeled.phase,
                    session_id=labeled.session_id,
                    x=step.position.x,
                    z=step.position.z,
                    point_kind="post",
                    action=step.action,
                    status=step.action_status.value,
                )
            )
            trajectory_markers.append(
                TrajectoryMarker(
                    sequence=marker_sequence,
                    frame_sequence=sequence,
                    kind="action",
                    x=step.position.x,
                    z=step.position.z,
                    label=f"Step {step.index} · {step.action}",
                    evidence_ref=frame_ref,
                )
            )
            marker_sequence += 1
            if step.action_status.value == "failed":
                trajectory_markers.append(
                    TrajectoryMarker(
                        sequence=marker_sequence,
                        frame_sequence=sequence,
                        kind="failure",
                        x=step.position.x,
                        z=step.position.z,
                        label=step.action_error or "Action failed",
                        evidence_ref=frame_ref,
                    )
                )
                marker_sequence += 1
            elif step.action != "wait":
                trajectory_markers.append(
                    TrajectoryMarker(
                        sequence=marker_sequence,
                        frame_sequence=sequence,
                        kind="success",
                        x=step.position.x,
                        z=step.position.z,
                        label=f"Completed · {step.action}",
                        evidence_ref=frame_ref,
                    )
                )
                marker_sequence += 1
            sequence += 1
            trajectory_sequence += 1

    timeline.append(
        TimelineEvent(
            sequence=timeline_sequence,
            kind="evaluation",
            label=f"EVALUATION · {'SUCCESS' if result.success else 'FAILURE'}",
            evidence_ref="ScenarioResult.success",
        )
    )

    supported = sum(frame.utilization.status == "supported" for frame in frames)
    attribution_counts = {
        "R": sum(frame.retrieval.item_count > 0 for frame in frames),
        "U": supported,
        "P": len(frames),
        "E": len(frames),
        "Unknown": len(frames) - supported,
    }
    return ReplayDocument(
        source_digest=source_digest,
        scenario=result.scenario,
        seed=result.seed,
        memory_backend=result.memory_backend,
        phases=[record.model_dump(mode="json") for record in result.phase_records],
        probes=[probe.model_dump(mode="json") for probe in result.retrieval_probes],
        frames=frames,
        timeline=timeline,
        trajectory=trajectory,
        trajectory_markers=trajectory_markers,
        available_memory=[
            event.model_dump(mode="json") for event in result.injected_events
        ],
        attribution_counts=attribution_counts,
    )
