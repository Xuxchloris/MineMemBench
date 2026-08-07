"""The `letta` memory backend: an adapter over the letta-client Python SDK.

Letta is a stateful-agent server (self-hosted `letta/letta` on port 8283, or
Letta Cloud). This is the M9 "stateful agent" framework condition: instead of
an inert store, memories live as archival-memory passages of a dedicated Letta
agent. Episodes map 1:1 to agents, so `reset()` deletes the episode's agent
(removing all of its archival memory). Everything goes through the
`MemoryBackend` plugin contract, so the planner never sees letta.

Design notes (all verified against the installed letta_client 1.12.1 source):

* The SDK is imported lazily, only inside `_build_letta_client()`, so this
  module and the whole package import cleanly when letta-client is absent.
* Construction is lazy too: with no injected client, the real client is built
  from `settings.letta_base_url` on first use. Building performs no I/O, so
  `LettaBackend(settings)` succeeds even when no server is configured; only an
  actual call fails, with a clear error pointing at the base URL.
* Every blocking SDK call runs inside `asyncio.to_thread(...)`; the async
  `MemoryBackend` methods never block the event loop.
* Episode scoping: one agent per `episode_id`. `_agents` caches
  `episode_id -> agent_id`; the agent is created on first use with
  `client.agents.create(name=...)`. The SDK's `AgentCreateParams` is a
  `total=False` TypedDict (letta_client/types/agent_create_params.py), so
  `name` is the only field we supply — model/embedding are omitted and would be
  defaulted server-side (never run inference).
* Passages do NOT support metadata at insert: the archival-memory insert
  endpoint accepts only `text`/`created_at`/`tags`
  (letta_client/types/agents/passage_create_params.py). So the `event_id` is
  prefixed into the stored text in a parseable form — `[event_id=...] ` — and
  parsed back out on retrieval. If a passage ever carries an `event_payload`
  metadata (e.g. inserted through a metadata-capable path), that is preferred.
* The agent-scoped archival search (`client.agents.passages.search`) returns
  results with only `id`/`content`/`timestamp`/`tags` and NO relevance score
  (letta_client/types/agents/passage_search_response.py). `MemoryItem.score`
  is therefore `None` when the client returns none — we never invent a score.
* There is no in-place passage update endpoint (the archival-memory resource
  only exposes create/list/search/delete), so `update()` locates the passage
  carrying the `event_id` and deletes + re-inserts it.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

from ..core.config import Settings
from ..core.models import EventType, ExperienceEvent
from .base import MemoryBackend, MemoryItem, MemoryQuery, MemoryStats
from .vector_memory import _render_text

logger = logging.getLogger(__name__)

#: Metadata keys used when a passage carries an event payload (see docstring:
#: the standard archival insert does not support metadata, so this is only
#: exercised by metadata-capable insert paths / injected fakes).
_PAYLOAD_KEY = "event_payload"
#: Prefix carrying the ExperienceEvent's id in the stored passage text.
_PREFIX = "[event_id={event_id}] {text}"
#: Parser for the `[event_id=...] ` prefix (event ids contain no `]`).
_PREFIX_RE = re.compile(r"^\[event_id=(?P<event_id>[^\]]+)\] (?P<text>.*)$", re.DOTALL)
#: Upper bound for `list` used by stats() to count every passage of an agent.
_COUNT_LIMIT = 10_000
#: How many passages update() is willing to scan to find the event_id.
_FIND_LIMIT = 1_000


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Read a field from either a dict (fake) or a pydantic SDK object."""

    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _letta_version() -> str | None:
    """Installed letta-client version, or None when the package is absent.

    Uses `importlib.metadata` only — never imports the letta package, so the
    version is reported even when a fake client is injected.
    """

    try:
        return importlib.metadata.version("letta-client")
    except importlib.metadata.PackageNotFoundError:
        return None


def _parse_dt(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp produced by letta; None when unparseable."""

    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _parse_prefix(text: str) -> tuple[str | None, str]:
    """Split a stored passage text into (event_id, body); both None when no
    `[event_id=...] ` prefix is present."""

    match = _PREFIX_RE.match(text)
    if match is None:
        return None, text
    return match.group("event_id"), match.group("text")


def _build_letta_client(settings: Settings) -> Any:
    """Construct a synchronous `letta_client.Client` from the settings.

    This is the only place the letta SDK is imported, so the whole package
    imports cleanly without letta-client installed. The SDK reads an optional
    `LETTA_API_KEY` env var itself (letta_client/_client.py); no I/O happens
    here, so a missing server does not surface until an actual call is made.
    """

    try:
        import letta_client  # noqa: PLC0415  (optional dependency, deliberately lazy)
    except ImportError as exc:
        raise RuntimeError(
            "the 'letta' memory backend requires the 'letta-client' package; "
            "install it with: uv pip install letta-client"
        ) from exc

    return letta_client.Client(base_url=settings.letta_base_url)


class LettaBackend(MemoryBackend):
    """Letta-backed memory. One agent per episode; blocking calls on threads."""

    def __init__(self, settings: Settings, client: Any = None) -> None:
        self._settings = settings
        # Either an injected fake (tests) or the lazily-built real letta client.
        self._client: Any = client
        #: Cache of episode_id -> Letta agent_id (agents are created lazily).
        self._agents: dict[str, str] = {}
        self._add_latency_s = 0.0
        self._add_calls = 0
        self._retrieve_latency_s = 0.0
        self._retrieve_calls = 0

    def _ensure_client(self) -> Any:
        """Build the real letta client on first use if none was injected."""

        if self._client is None:
            self._client = _build_letta_client(self._settings)
        return self._client

    def _ensure_agent_sync(self, client: Any, episode_id: str) -> str:
        """Return the agent id for `episode_id`, creating the agent on first use."""

        agent_id = self._agents.get(episode_id)
        if agent_id is not None:
            return agent_id
        try:
            state = client.agents.create(name=f"mem-{episode_id}")
        except Exception as exc:  # noqa: BLE001 — surface a clear server error
            raise RuntimeError(
                f"letta backend: cannot create the agent for episode "
                f"{episode_id!r} at {self._settings.letta_base_url!r}; is a "
                f"Letta server running? ({exc})"
            ) from exc
        agent_id = _get(state, "id")
        if not agent_id:
            raise RuntimeError(
                "letta backend: agent create returned no 'id' for episode "
                f"{episode_id!r}"
            )
        self._agents[episode_id] = agent_id
        return agent_id

    async def add(self, event: ExperienceEvent) -> None:
        """Store a new experience event as a passage of the episode's agent."""

        start = time.perf_counter()
        try:
            client = self._ensure_client()
            await asyncio.to_thread(self._add_sync, client, event)
        finally:
            self._add_calls += 1
            self._add_latency_s += time.perf_counter() - start

    def _add_sync(self, client: Any, event: ExperienceEvent) -> None:
        agent_id = self._ensure_agent_sync(client, event.episode_id)
        client.agents.passages.create(
            agent_id=agent_id,
            text=_PREFIX.format(event_id=event.event_id, text=_render_text(event)),
        )

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        """Return the `query.limit` most relevant memories, best first.

        `query.episode_id` narrows the archival search to that episode's agent.
        Without one, the search is a best-effort union over every agent this
        process has created (the client-boundary cache); the agent-scoped
        search returns no cross-agent score, so the union keeps each agent's
        internal relevance order and never invents a score.
        """

        start = time.perf_counter()
        try:
            client = self._ensure_client()
            return await asyncio.to_thread(self._retrieve_sync, client, query)
        finally:
            self._retrieve_calls += 1
            self._retrieve_latency_s += time.perf_counter() - start

    def _retrieve_sync(self, client: Any, query: MemoryQuery) -> list[MemoryItem]:
        if query.episode_id is not None:
            agent_id = self._ensure_agent_sync(client, query.episode_id)
            response = client.agents.passages.search(
                agent_id=agent_id,
                query=query.query_text,
                top_k=query.limit,
            )
            return [
                self._to_memory_item(result, query.episode_id)
                for result in _get(response, "results", [])
            ]

        items: list[MemoryItem] = []
        for episode_id, agent_id in self._agents.items():
            response = client.agents.passages.search(
                agent_id=agent_id,
                query=query.query_text,
                top_k=query.limit,
            )
            for result in _get(response, "results", []):
                items.append(self._to_memory_item(result, episode_id))
                if len(items) >= query.limit:
                    return items
        return items

    def _to_memory_item(self, result: Any, episode_id: str) -> MemoryItem:
        """Map one archival-search result to a MemoryItem.

        `score` is passed through when the client returns one and left `None`
        otherwise (the agent-scoped archival search returns no score) — never
        invented. The recorded event is reconstructed from the `event_payload`
        metadata when present, else from the `[event_id=...] ` text prefix.
        """

        metadata = {
            key: value
            for key, value in dict(_get(result, "metadata") or {}).items()
            if isinstance(value, str)
        }
        text = _get(result, "text") or _get(result, "content") or ""
        event = self._reconstruct_event(result, episode_id, text, metadata)
        return MemoryItem(
            item_id=event.event_id,
            event=event,
            score=_get(result, "score"),
            created_at=_parse_dt(_get(result, "created_at") or _get(result, "timestamp"))
            or datetime.now(UTC),
            metadata=metadata,
        )

    @classmethod
    def _reconstruct_event(
        cls,
        result: Any,
        episode_id: str,
        text: str,
        metadata: dict[str, str],
    ) -> ExperienceEvent:
        """Reconstruct the recorded event, payload metadata first, prefix next.

        Returns the exact recorded event when an `event_payload` is available;
        otherwise a minimal reconstruction from the `[event_id=...] ` prefix
        (an event's full JSON is not stored because the archival insert does
        not accept metadata).
        """

        payload_json = metadata.get(_PAYLOAD_KEY)
        if payload_json:
            try:
                return ExperienceEvent.model_validate(json.loads(payload_json))
            except (TypeError, ValueError):
                pass  # malformed payload: fall back to the prefix reconstruction
        event_id, body = _parse_prefix(text)
        return ExperienceEvent(
            event_id=event_id or str(_get(result, "id") or ""),
            episode_id=episode_id,
            timestamp=_parse_dt(_get(result, "created_at") or _get(result, "timestamp"))
            or datetime.now(UTC),
            actor="letta",
            event_type=EventType.WORLD_FACT_UPDATED,
            context={"text": body or text},
        )

    async def update(self, event: ExperienceEvent) -> None:
        """Overwrite the stored event with the same `event_id`.

        The archival-memory resource exposes no in-place update (only
        create/list/search/delete), so the passage carrying the `event_id`
        prefix is deleted and the new content re-inserted. If no such passage
        exists we fall back to `add` (create), mirroring the vector backend's
        upsert semantics.
        """

        client = self._ensure_client()
        await asyncio.to_thread(self._update_sync, client, event)

    def _update_sync(self, client: Any, event: ExperienceEvent) -> None:
        agent_id = self._ensure_agent_sync(client, event.episode_id)
        passages = client.agents.passages.list(
            agent_id=agent_id,
            limit=_FIND_LIMIT,
        )
        for passage in passages:
            passage_id = _get(passage, "id")
            prefix_event_id, _ = _parse_prefix(_get(passage, "text") or "")
            if passage_id and prefix_event_id == event.event_id:
                client.agents.passages.delete(
                    memory_id=passage_id,
                    agent_id=agent_id,
                )
                break
        self._add_sync(client, event)

    async def reset(self, episode_id: str) -> None:
        """Delete the episode's agent (removes all its archival memory)."""

        client = self._ensure_client()
        await asyncio.to_thread(self._reset_sync, client, episode_id)

    def _reset_sync(self, client: Any, episode_id: str) -> None:
        agent_id = self._agents.pop(episode_id, None)
        if agent_id is not None:
            client.agents.delete(agent_id=agent_id)

    async def stats(self) -> MemoryStats:
        client = self._ensure_client()
        return await asyncio.to_thread(self._stats_sync, client)

    def _stats_sync(self, client: Any) -> MemoryStats:
        """Report backend name, best-effort item count, and latency extras.

        `item_count` sums the passages of every agent this process has created
        (read live through the client boundary); there is no org-wide count
        endpoint in the archival-memory resource, and agents are created
        lazily per episode, so counts above the process's own cache may be
        undercounted. That scope is recorded in the extras.
        """

        count = 0
        try:
            for agent_id in self._agents.values():
                passages = client.agents.passages.list(
                    agent_id=agent_id,
                    limit=_COUNT_LIMIT,
                )
                count += len(passages)
        except Exception as exc:  # noqa: BLE001 — stats must never crash the run
            logger.warning(
                "letta stats: listing passages failed, reporting item_count=0: %s",
                exc,
            )
        return MemoryStats(
            backend="letta",
            item_count=count,
            extra={
                "avg_add_latency_ms": self._avg_ms(self._add_latency_s, self._add_calls),
                "avg_retrieve_latency_ms": self._avg_ms(
                    self._retrieve_latency_s, self._retrieve_calls
                ),
                "letta_version": _letta_version(),
                "base_url": self._settings.letta_base_url,
                "item_count_scope": "client boundary: this process's cached "
                "episode agents only",
            },
        )

    @staticmethod
    def _avg_ms(total_s: float, calls: int) -> float | None:
        """Average latency in ms over `calls` samples; None when unmeasured."""

        return round(total_s / calls * 1000.0, 3) if calls else None
