"""Consume the raw /events stream and persist mapped ExperienceEvents (M5).

`EventCollector` owns a run's interaction memory: it turns the bot's raw
event stream into ExperienceEvents via the SemanticMapper and stores them
through the injected MemoryBackend. Failures to persist are counted, never
fatal; a stream disconnect ends consumption cleanly.
"""

from __future__ import annotations

import asyncio
import logging

from ..core.client import BotClient
from ..core.models import ExperienceEvent
from ..memory.base import MemoryBackend
from .mapper import SemanticMapper

logger = logging.getLogger(__name__)


class EventCollector:
    """Background consumer mapping the raw event stream into memory.

    `bot_username` is resolved from the keyword argument, else from a
    `username` attribute on `bot_client`, else from the bridge's `/health`
    endpoint. The mapper needs it to tell the bot apart from other players.
    """

    def __init__(
        self,
        bot_client: BotClient,
        memory: MemoryBackend,
        mapper: SemanticMapper | None = None,
        *,
        bot_username: str | None = None,
    ) -> None:
        self._bot = bot_client
        self._memory = memory
        self._mapper = mapper or SemanticMapper()
        self._bot_username = bot_username
        self._episode_id: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._collected: list[ExperienceEvent] = []
        self._pending: list[ExperienceEvent] = []
        self._seen_raw_ids: set[str] = set()
        self._dropped_count = 0

    @property
    def dropped_count(self) -> int:
        """Number of events that failed to persist to the memory backend."""

        return self._dropped_count

    async def start(self, episode_id: str) -> None:
        """Begin consuming the bot's event stream for `episode_id`.

        Idempotent: starting an already-running collector is a no-op. A new
        start resets all per-episode state.
        """

        if self._task is not None and not self._task.done():
            return
        self._episode_id = episode_id
        self._collected = []
        self._pending = []
        self._seen_raw_ids = set()
        self._dropped_count = 0
        await self._resolve_bot_username()
        self._task = asyncio.create_task(self._consume())

    async def stop(self) -> list[ExperienceEvent]:
        """Stop collection, flush any buffered events, return everything mapped.

        Safe to call when nothing was started (returns the empty list) and
        never raises: consumer failures are logged, not propagated.
        """

        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("event collection task failed while stopping")
        self._task = None
        await self._drain()
        return self._collected

    async def _resolve_bot_username(self) -> None:
        if self._bot_username is not None:
            return
        if (username := getattr(self._bot, "username", None)) is not None:
            self._bot_username = username
            return
        health = getattr(self._bot, "health", None)
        if health is not None:
            try:
                response = await health()
            except Exception:
                logger.warning("could not resolve bot username", exc_info=True)
            else:
                if response.username is not None:
                    self._bot_username = response.username

    async def _consume(self) -> None:
        assert self._episode_id is not None
        try:
            async for raw in self._bot.iter_events():
                if raw.event_id in self._seen_raw_ids:
                    continue
                self._seen_raw_ids.add(raw.event_id)
                event = self._mapper.map_event(
                    raw,
                    bot_username=self._bot_username or "",
                    episode_id=self._episode_id,
                )
                if event is None:
                    continue
                self._collected.append(event)
                self._pending.append(event)
                await self._drain()
        except asyncio.CancelledError:
            raise
        except Exception:
            # A stream disconnect or a bad event ends collection cleanly;
            # anything still buffered is flushed by stop().
            logger.warning("event stream ended unexpectedly", exc_info=True)

    async def _drain(self) -> None:
        """Persist every buffered event, leaving failures counted, not fatal.

        On cancellation the current event stays buffered so stop() can flush
        it; on any other error the event is dropped and counted.
        """

        while self._pending:
            event = self._pending[0]
            try:
                await self._memory.add(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("dropping event %s", event.event_id)
                self._dropped_count += 1
            self._pending.pop(0)
