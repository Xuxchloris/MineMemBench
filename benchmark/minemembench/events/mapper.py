"""Semantic mapping from raw game events to ExperienceEvents (M5, phase 1).

The event layer records what happened, never how the agent should feel about
it. `SemanticMapper` is a pure, mechanical translation of the raw `/events`
stream into the interaction facts the memory layer stores -- no trust scores,
moods, or behavioral judgments live here.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..core.ids import new_event_id
from ..core.models import (
    EventType,
    ExperienceEvent,
    Position,
    RawEventKind,
    RawGameEvent,
)


class SemanticMapper:
    """Turns raw game events into ExperienceEvents (phase-1 rules).

    Phase-1 mapping table (interaction facts only):

    * `death`                          -> AGENT_DIED (the bot itself died)
    * `entity_hurt` with victim==bot   -> PLAYER_ATTACKED_AGENT, but only
      when the attacker is a player: a non-empty name that is neither null
      nor the bot. A null or mob attacker maps to nothing.
    * `item_dropped` by a player other -> PLAYER_SHARED_RESOURCE. This is
      the phase-1 mechanical heuristic for "shared": any item a player drops
      is treated as sharing a resource, because the raw data records the
      drop but not the player's intent.
    * every other kind                 -> nothing (returns None)

    IMPORTANT: TASK_SUCCEEDED, TASK_FAILED, LOCATION_DISCOVERED,
    RESOURCE_DISCOVERED and WORLD_FACT_UPDATED are NOT derived from raw game
    events. The scenario/runner layers construct those ExperienceEvents
    directly; this mapper only owns interaction facts.
    """

    def map_event(
        self,
        raw: RawGameEvent,
        *,
        bot_username: str,
        episode_id: str,
    ) -> ExperienceEvent | None:
        """Map one raw event to an ExperienceEvent, or None when unmappable.

        Pure and mechanical: the result describes only what happened, and
        `raw` is always copied verbatim into the returned event's
        `raw_events`.
        """

        if raw.kind is RawEventKind.DEATH:
            return self._map_death(raw, bot_username, episode_id)
        if raw.kind is RawEventKind.ENTITY_HURT:
            return self._map_entity_hurt(raw, bot_username, episode_id)
        if raw.kind is RawEventKind.ITEM_DROPPED:
            return self._map_item_dropped(raw, bot_username, episode_id)
        return None

    def _map_death(
        self, raw: RawGameEvent, bot_username: str, episode_id: str
    ) -> ExperienceEvent:
        """Map the bot's own death. Location is carried when the data has it."""

        return ExperienceEvent(
            event_id=new_event_id(),
            episode_id=episode_id,
            timestamp=raw.timestamp,
            actor=bot_username,
            event_type=EventType.AGENT_DIED,
            location=_extract_position(raw.data),
            raw_events=[raw],
        )

    def _map_entity_hurt(
        self, raw: RawGameEvent, bot_username: str, episode_id: str
    ) -> ExperienceEvent | None:
        """Map a player attacking the bot, if that is what the event says.

        A player attacker is a non-empty name that is not the bot and is not
        flagged as a non-player. An attacker that is absent/null, is the bot
        itself, or is marked `attacker_is_player: false` (a mob) maps to
        nothing.
        """

        data = raw.data
        if data.get("victim") != bot_username:
            return None
        if data.get("attacker_is_player") is False:
            return None
        attacker = data.get("attacker")
        if not _is_player_name(attacker, bot_username):
            return None
        return ExperienceEvent(
            event_id=new_event_id(),
            episode_id=episode_id,
            timestamp=raw.timestamp,
            actor=attacker,
            target=bot_username,
            event_type=EventType.PLAYER_ATTACKED_AGENT,
            raw_events=[raw],
        )

    def _map_item_dropped(
        self, raw: RawGameEvent, bot_username: str, episode_id: str
    ) -> ExperienceEvent | None:
        """Map a player dropping an item to a shared-resource fact.

        Phase-1 mechanical heuristic for "shared": any item dropped by a
        player other than the bot is treated as a shared resource. The raw
        data tells us an item changed hands, not why, so the mapping stays
        deliberately crude.
        """

        data = raw.data
        dropper = data.get("dropper")
        if not _is_player_name(dropper, bot_username):
            return None
        context: dict[str, Any] = {}
        if data.get("item") is not None:
            context["item"] = data["item"]
        if data.get("count") is not None:
            context["count"] = data["count"]
        return ExperienceEvent(
            event_id=new_event_id(),
            episode_id=episode_id,
            timestamp=raw.timestamp,
            actor=dropper,
            event_type=EventType.PLAYER_SHARED_RESOURCE,
            context=context,
            raw_events=[raw],
        )


def _is_player_name(value: Any, bot_username: str) -> bool:
    """True when `value` looks like a player name other than the bot.

    Phase-1 mechanical rule: a name is a player when it is a non-empty string
    that is not the bot's own username. Non-strings (entity ids), empty
    values, and the bot itself are never players.
    """

    return isinstance(value, str) and bool(value) and value != bot_username


def _extract_position(data: dict[str, Any]) -> Position | None:
    """Pull a Position out of kind-specific data, tolerating absence."""

    for key in ("position", "location"):
        value = data.get(key)
        if isinstance(value, dict) and "x" in value and "y" in value and "z" in value:
            try:
                return Position.model_validate(value)
            except ValidationError:
                return None
    return None
