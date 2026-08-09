"""The memory-backend plugin contract.

Every backend (none / vector / mem0 / letta / ...) implements `MemoryBackend`.
The planner never branches on `memory_type`; backends are injected through
this interface only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..core.models import ExperienceEvent


class _ContractModel(BaseModel):
    model_config = ConfigDict(validate_assignment=True)


class MemoryQuery(_ContractModel):
    """A retrieval request against a memory backend."""

    query_text: str
    episode_id: str | None = None
    limit: int = Field(default=10, gt=0)
    filters: dict[str, str] = Field(default_factory=dict)


class MemoryItem(_ContractModel):
    """One stored memory as returned by `retrieve`."""

    item_id: str
    event: ExperienceEvent
    score: float | None = None
    created_at: datetime
    metadata: dict[str, str] = Field(default_factory=dict)


class MemoryStats(_ContractModel):
    """Backend self-report for logging and metrics."""

    backend: str
    item_count: int = Field(ge=0)
    extra: dict[str, Any] = Field(default_factory=dict)


class MemoryItemSnapshot(_ContractModel):
    """A serializable snapshot of one retrieved `MemoryItem`.

    Used wherever raw retrieval evidence must survive in a run log (per-step
    planner evidence, evaluation probes): it carries the full reconstructed
    `ExperienceEvent` (event_id, episode_id, timestamp, actor, target,
    event_type, location, context, outcome, raw_events) plus the item's score,
    creation time, and backend metadata, so every retrieval-side metric can be
    re-derived from the log alone. Memory contents only — never prompts or
    secrets.
    """

    item_id: str
    score: float | None
    created_at: datetime
    metadata: dict[str, str] = Field(default_factory=dict)
    event: ExperienceEvent

    @classmethod
    def from_item(cls, item: MemoryItem) -> MemoryItemSnapshot:
        """Snapshot one retrieved item as returned by the backend."""

        return cls(
            item_id=item.item_id,
            score=item.score,
            created_at=item.created_at,
            metadata=dict(item.metadata),
            event=item.event,
        )


class MemoryBackend(ABC):
    """Unified interface every memory backend must implement."""

    @abstractmethod
    async def add(self, event: ExperienceEvent) -> None:
        """Store a new experience event."""

    @abstractmethod
    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        """Return the memories most relevant to `query`, best first."""

    @abstractmethod
    async def update(self, event: ExperienceEvent) -> None:
        """Replace the stored event with the same `event_id` (belief updates)."""

    @abstractmethod
    async def reset(self, episode_id: str) -> None:
        """Drop all memories belonging to one episode."""

    @abstractmethod
    async def stats(self) -> MemoryStats:
        """Report backend name, item count, and backend-specific extras."""


class EventRecordingBackend(MemoryBackend):
    """A pass-through proxy that records every event offered to the backend.

    The benchmark harness wraps the per-run backend in this proxy so the run
    log can carry the COMPLETE sequence of events passed to `add`/`update` —
    the actual campaign inputs — for every backend, including `none`. The
    record is append-only: a later `reset()` does not erase it (the audit
    needs what was offered, not what survived). Retrieval/reset/stats delegate
    unchanged; no behavior differs per backend name.
    """

    def __init__(self, inner: MemoryBackend) -> None:
        self._inner = inner
        #: Every event offered to add()/update(), in offer order.
        self.offered_events: list[ExperienceEvent] = []

    async def add(self, event: ExperienceEvent) -> None:
        self.offered_events.append(event)
        await self._inner.add(event)

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        return await self._inner.retrieve(query)

    async def update(self, event: ExperienceEvent) -> None:
        self.offered_events.append(event)
        await self._inner.update(event)

    async def reset(self, episode_id: str) -> None:
        await self._inner.reset(episode_id)

    async def stats(self) -> MemoryStats:
        return await self._inner.stats()
