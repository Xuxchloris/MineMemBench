"""Wire-contract and benchmark-side data models.

Every model here mirrors docs/protocol.md exactly; both sides of the bridge
validate against these schemas (zod on TS, pydantic on Python).
"""

from .client import (
    BotBridgeError,
    BotClient,
    BotNotConnectedError,
    InvalidActionError,
)
from .config import Settings
from .ids import new_event_id, new_run_id
from .models import (
    ActionRequest,
    ActionResult,
    ActionStatus,
    BotMode,
    EntityKind,
    Equipped,
    EventEnvelope,
    EventType,
    ExperienceEvent,
    HealthResponse,
    HeldItem,
    InventoryItem,
    NearbyEntity,
    NearbyPlayer,
    Position,
    RawEventKind,
    RawGameEvent,
    ServerHello,
    WorldState,
)

__all__ = [
    "ActionRequest",
    "ActionResult",
    "ActionStatus",
    "BotBridgeError",
    "BotClient",
    "BotMode",
    "BotNotConnectedError",
    "EntityKind",
    "Equipped",
    "EventEnvelope",
    "EventType",
    "ExperienceEvent",
    "HealthResponse",
    "HeldItem",
    "InvalidActionError",
    "InventoryItem",
    "NearbyEntity",
    "NearbyPlayer",
    "Position",
    "RawEventKind",
    "RawGameEvent",
    "ServerHello",
    "Settings",
    "WorldState",
    "new_event_id",
    "new_run_id",
]
