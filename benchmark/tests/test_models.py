"""Model round-trip tests against the docs/protocol.md example payloads."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from minemembench.core.models import (
    ActionRequest,
    ActionResult,
    ActionStatus,
    BotMode,
    EntityKind,
    EventType,
    ExperienceEvent,
    RawEventKind,
    RawGameEvent,
    WorldState,
)


def _round_trip(model: Any) -> Any:
    """Serialize to JSON and validate back; models must compare equal."""

    return type(model).model_validate_json(model.model_dump_json())


def test_world_state_round_trip(world_state_payload: Any) -> None:
    state = WorldState.model_validate(world_state_payload)
    assert _round_trip(state) == state

    assert state.mode is BotMode.MOCK
    assert state.username == "BenchBot"
    assert state.position.y == 64.0
    assert state.inventory[0].name == "stone"
    assert state.equipped.hand is not None
    assert state.equipped.hand.name == "stone_sword"
    assert state.nearby_entities[0].kind is EntityKind.HOSTILE
    assert state.nearby_players[0].username == "Steve"


def test_world_state_equipped_hand_may_be_null(
    world_state_payload: Any,
) -> None:
    world_state_payload["equipped"]["hand"] = None
    state = WorldState.model_validate(world_state_payload)
    assert state.equipped.hand is None


def test_action_result_completed_round_trip(action_result_payload: Any) -> None:
    result = ActionResult.model_validate(action_result_payload)
    assert _round_trip(result) == result

    assert result.status is ActionStatus.COMPLETED
    assert result.error is None
    assert result.result is not None
    assert result.result["position"]["x"] == 10.0
    assert result.state_after is not None
    assert result.state_after.position.x == 10.0


def test_action_result_failed_round_trip() -> None:
    payload: Any = {
        "action_id": "7aa0b1c2-3d55-4e9f-8a62-1b2c3d4e5f60",
        "action": "move_to",
        "status": "failed",
        "started_at": "2026-08-07T12:05:00Z",
        "finished_at": "2026-08-07T12:05:03Z",
        "result": None,
        "error": "Target is unreachable",
        "state_after": None,
    }
    result = ActionResult.model_validate(payload)
    assert _round_trip(result) == result

    assert result.status is ActionStatus.FAILED
    assert result.result is None
    assert result.error == "Target is unreachable"
    assert result.state_after is None


def test_raw_game_event_round_trip(raw_event_payload: Any) -> None:
    event = RawGameEvent.model_validate(raw_event_payload)
    assert _round_trip(event) == event

    assert event.kind is RawEventKind.CHAT
    assert event.data["username"] == "Steve"


@pytest.mark.parametrize("kind", list(RawEventKind))
def test_raw_game_event_every_kind(raw_event_payload: Any, kind: RawEventKind) -> None:
    raw_event_payload["kind"] = kind.value
    event = RawGameEvent.model_validate(raw_event_payload)
    assert event.kind is kind


@pytest.mark.parametrize("event_type", list(EventType))
def test_experience_event_every_event_type(
    experience_event_payload: Any, event_type: EventType
) -> None:
    experience_event_payload["event_type"] = event_type.value
    event = ExperienceEvent.model_validate(experience_event_payload)
    assert _round_trip(event) == event

    assert event.event_type is event_type
    assert event.episode_id == "ep-001"
    assert event.location is not None
    assert len(event.raw_events) == 1
    assert event.raw_events[0].kind is RawEventKind.CHAT


def test_event_type_values_are_exact() -> None:
    assert {member.value for member in EventType} == {
        "player_shared_resource",
        "player_attacked_agent",
        "player_helped_agent",
        "agent_died",
        "task_succeeded",
        "task_failed",
        "location_discovered",
        "resource_discovered",
        "world_fact_updated",
    }


def test_action_request_defaults() -> None:
    request = ActionRequest(action="chat", arguments={"message": "hi"})
    assert request.timeout_ms == 30000
    dumped = request.model_dump(mode="json")
    assert dumped == {
        "action": "chat",
        "arguments": {"message": "hi"},
        "timeout_ms": 30000,
    }


def test_action_request_timeout_max() -> None:
    with pytest.raises(ValidationError):
        ActionRequest(action="wait", arguments={"seconds": 1}, timeout_ms=120001)
