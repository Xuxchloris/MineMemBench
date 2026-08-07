"""SemanticMapper tests: pure mechanical mapping of RawGameEvent -> ExperienceEvent.

Covers every phase-1 rule in the milestone spec; the fixtures are shaped like
docs/protocol.md's raw `/events` payloads.
"""

from __future__ import annotations

from datetime import UTC, datetime

from minemembench.core.models import (
    EventType,
    Position,
    RawEventKind,
    RawGameEvent,
)
from minemembench.events.mapper import SemanticMapper

BOT = "BenchBot"
TS = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)


def _raw(
    kind: RawEventKind, event_id: str, data: dict | None = None
) -> RawGameEvent:
    return RawGameEvent(event_id=event_id, timestamp=TS, kind=kind, data=data or {})


def _map(
    raw: RawGameEvent, bot_username: str = BOT, episode_id: str = "ep-1"
) -> object:
    return SemanticMapper().map_event(
        raw, bot_username=bot_username, episode_id=episode_id
    )


async def test_death_maps_to_agent_died() -> None:
    raw = _raw(
        RawEventKind.DEATH,
        "r-death",
        {"position": {"x": 1.0, "y": 64.0, "z": 2.0}},
    )

    event = _map(raw)

    assert event is not None
    assert event.event_type is EventType.AGENT_DIED
    assert event.actor == BOT
    assert event.target is None
    assert event.location == Position(x=1.0, y=64.0, z=2.0)
    assert event.episode_id == "ep-1"
    assert event.event_id
    assert event.raw_events == [raw]


async def test_death_without_position_has_no_location() -> None:
    event = _map(_raw(RawEventKind.DEATH, "r-death-2"))

    assert event is not None
    assert event.event_type is EventType.AGENT_DIED
    assert event.location is None


async def test_entity_hurt_by_player_maps_to_attacked() -> None:
    raw = _raw(
        RawEventKind.ENTITY_HURT,
        "r-hurt",
        {"victim": BOT, "attacker": "Steve"},
    )

    event = _map(raw)

    assert event is not None
    assert event.event_type is EventType.PLAYER_ATTACKED_AGENT
    assert event.actor == "Steve"
    assert event.target == BOT
    assert event.raw_events == [raw]


async def test_entity_hurt_with_null_attacker_is_none() -> None:
    raw = _raw(
        RawEventKind.ENTITY_HURT, "r-hurt-null", {"victim": BOT, "attacker": None}
    )

    assert _map(raw) is None


async def test_entity_hurt_with_mob_attacker_is_none() -> None:
    raw = _raw(
        RawEventKind.ENTITY_HURT,
        "r-hurt-mob",
        {"victim": BOT, "attacker": "zombie", "attacker_is_player": False},
    )

    assert _map(raw) is None


async def test_entity_hurt_victim_not_the_bot_is_none() -> None:
    raw = _raw(
        RawEventKind.ENTITY_HURT,
        "r-hurt-other",
        {"victim": "Alex", "attacker": "Steve"},
    )

    assert _map(raw) is None


async def test_entity_hurt_with_the_bot_as_attacker_is_none() -> None:
    raw = _raw(
        RawEventKind.ENTITY_HURT,
        "r-hurt-self",
        {"victim": BOT, "attacker": BOT},
    )

    assert _map(raw) is None


async def test_item_dropped_by_player_maps_to_shared_resource() -> None:
    raw = _raw(
        RawEventKind.ITEM_DROPPED,
        "r-drop",
        {"dropper": "Steve", "item": "oak_log", "count": 3},
    )

    event = _map(raw)

    assert event is not None
    assert event.event_type is EventType.PLAYER_SHARED_RESOURCE
    assert event.actor == "Steve"
    assert event.target is None
    assert event.context == {"item": "oak_log", "count": 3}
    assert event.raw_events == [raw]


async def test_item_dropped_by_the_bot_is_none() -> None:
    raw = _raw(
        RawEventKind.ITEM_DROPPED,
        "r-drop-self",
        {"dropper": BOT, "item": "dirt", "count": 1},
    )

    assert _map(raw) is None


async def test_unmappable_kinds_map_to_none() -> None:
    for kind, data in [
        (RawEventKind.CHAT, {"username": "Steve", "message": "take this bread"}),
        (RawEventKind.MESSAGE, {"from": "Steve", "text": "hi"}),
        (RawEventKind.PLAYER_JOINED, {"username": "Steve"}),
        (RawEventKind.PLAYER_LEFT, {"username": "Steve"}),
        (RawEventKind.HEALTH, {"health": 10}),
        (RawEventKind.ENTITY_DEAD, {"name": "zombie"}),
    ]:
        assert _map(_raw(kind, f"r-{kind.value}", data)) is None, kind


async def test_mapping_is_deterministic_per_episode() -> None:
    raw = _raw(
        RawEventKind.ITEM_DROPPED,
        "r-drop-2",
        {"dropper": "Alex", "item": "apple", "count": 1},
    )

    event = _map(raw, episode_id="ep-42")

    assert event is not None
    assert event.episode_id == "ep-42"
