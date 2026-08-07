"""Pydantic v2 models mirroring docs/protocol.md (Bot Bridge Protocol v1).

Field names match the JSON wire format one-to-one; no aliases are needed.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    """Base model: validate assignment and reject nothing extra silently.

    The protocol is versioned explicitly, so unknown fields are tolerated
    (forward compatibility) but never mutated by the parser.
    """

    model_config = ConfigDict(validate_assignment=True)


class BotMode(str, Enum):
    """Adapter operating mode, per protocol `mode` fields."""

    MINECRAFT = "minecraft"
    MOCK = "mock"


class EntityKind(str, Enum):
    """Classification of a nearby entity."""

    HOSTILE = "hostile"
    PASSIVE = "passive"
    PLAYER = "player"
    ITEM = "item"
    OTHER = "other"


class ActionStatus(str, Enum):
    """Terminal status of an executed action (HTTP 200 even when failed)."""

    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class RawEventKind(str, Enum):
    """Kinds of raw, uninterpreted game events from the /events stream."""

    CHAT = "chat"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    ENTITY_HURT = "entity_hurt"
    ENTITY_DEAD = "entity_dead"
    HEALTH = "health"
    DEATH = "death"
    ITEM_DROPPED = "item_dropped"
    MESSAGE = "message"


class Position(_StrictModel):
    x: float
    y: float
    z: float


class InventoryItem(_StrictModel):
    slot: int
    name: str
    display_name: str
    count: int


class HeldItem(_StrictModel):
    """Item held in the bot's hand (protocol: `equipped.hand`)."""

    name: str
    display_name: str


class Equipped(_StrictModel):
    """Currently equipped items. `hand` may be null per protocol."""

    hand: HeldItem | None = None


class NearbyEntity(_StrictModel):
    """A non-player entity within 32 blocks, sorted by distance ascending."""

    id: int
    name: str
    display_name: str
    kind: EntityKind
    position: Position
    distance: float


class NearbyPlayer(_StrictModel):
    username: str
    position: Position
    distance: float


class WorldState(_StrictModel):
    """Snapshot returned by `GET /state`."""

    timestamp: datetime
    mode: BotMode
    username: str
    health: float
    food: int
    saturation: float
    oxygen: int
    position: Position
    yaw: float
    pitch: float
    dimension: str
    time_of_day: int
    is_raining: bool
    experience_level: int
    inventory: list[InventoryItem] = Field(default_factory=list)
    equipped: Equipped = Field(default_factory=Equipped)
    nearby_entities: list[NearbyEntity] = Field(default_factory=list)
    nearby_players: list[NearbyPlayer] = Field(default_factory=list)


class HealthResponse(_StrictModel):
    """Response of `GET /health`. `username` is null when not connected."""

    status: str
    mode: BotMode
    connected: bool
    username: str | None
    uptime_s: float


class ActionRequest(_StrictModel):
    """Request body of `POST /action`."""

    action: str
    # Action arguments are action-specific (see protocol table); they are
    # validated server-side, so a free-form JSON object is unavoidable here.
    arguments: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = Field(default=30000, gt=0, le=120000)


class ActionResult(_StrictModel):
    """Response of `POST /action` (HTTP 200 even when `status` is failed).

    `result` is null on failure; `error` is a human-readable string or null.
    """

    action_id: str
    action: str
    status: ActionStatus
    started_at: datetime
    finished_at: datetime
    result: dict[str, Any] | None = None
    error: str | None = None
    state_after: WorldState | None = None


class RawGameEvent(_StrictModel):
    """One raw, uninterpreted game event from the `/events` WebSocket.

    Semantic interpretation into ExperienceEvent happens on the Python side;
    the TS adapter must not annotate meaning.
    """

    event_id: str
    timestamp: datetime
    kind: RawEventKind
    data: dict[str, Any] = Field(default_factory=dict)


class ServerHello(_StrictModel):
    """First message sent by the server on WebSocket connect."""

    type: Literal["hello"] = "hello"
    mode: BotMode
    username: str | None


class EventEnvelope(_StrictModel):
    """WebSocket envelope wrapping a RawGameEvent."""

    type: Literal["event"] = "event"
    event: RawGameEvent


class EventType(str, Enum):
    """Semantic event types produced by the Python event layer (M5+)."""

    PLAYER_SHARED_RESOURCE = "player_shared_resource"
    PLAYER_ATTACKED_AGENT = "player_attacked_agent"
    PLAYER_HELPED_AGENT = "player_helped_agent"
    AGENT_DIED = "agent_died"
    TASK_SUCCEEDED = "task_succeeded"
    TASK_FAILED = "task_failed"
    LOCATION_DISCOVERED = "location_discovered"
    RESOURCE_DISCOVERED = "resource_discovered"
    WORLD_FACT_UPDATED = "world_fact_updated"


class ExperienceEvent(_StrictModel):
    """A semantically interpreted experience, the unit stored by memory backends.

    Records what happened — never how the agent should feel about it.
    """

    event_id: str
    episode_id: str
    timestamp: datetime
    actor: str
    target: str | None = None
    event_type: EventType
    location: Position | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    outcome: str | None = None
    raw_events: list[RawGameEvent] = Field(default_factory=list)
