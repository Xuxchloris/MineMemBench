"""The `none` memory backend: the Phase-1 baseline that remembers nothing.

This is the control condition of the benchmark — the planner receives an
empty memory context on every step, so any behavioral difference vs. a real
backend is attributable to memory alone.
"""

from __future__ import annotations

from ..core.models import ExperienceEvent
from .base import MemoryBackend, MemoryItem, MemoryQuery, MemoryStats


class NoMemoryBackend(MemoryBackend):
    """Baseline backend: stores nothing, retrieves nothing."""

    async def add(self, event: ExperienceEvent) -> None:
        """No-op: experiences are deliberately discarded."""

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        """Always empty: the agent acts without any memory context."""

        return []

    async def update(self, event: ExperienceEvent) -> None:
        """No-op."""

    async def reset(self, episode_id: str) -> None:
        """No-op: there is nothing to clear."""

    async def stats(self) -> MemoryStats:
        return MemoryStats(backend="none", item_count=0)
