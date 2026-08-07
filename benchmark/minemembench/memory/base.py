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
