"""The `mem0` memory backend: an adapter over the Mem0 OSS SDK.

Mem0 is the M8 "framework memory" condition — a real long-term memory library
(LLM-powered extraction, hybrid vector/keyword search, entity linking) rather
than a hand-rolled baseline. Everything goes through the `MemoryBackend`
plugin contract, so the planner never sees mem0.

Design notes (all verified against the installed mem0ai 2.0.17 source):

* The SDK is imported lazily, only inside `_build_mem0_client()`, so this
  module and the whole package import cleanly when mem0ai is absent.
* Every blocking SDK call runs inside `asyncio.to_thread(...)`; the async
  `MemoryBackend` methods never block the event loop.
* Telemetry is disabled before the first `import mem0`
  (`MEM0_TELEMETRY=false`), so the benchmark never phones home.
* Events are stored verbatim: `add(..., infer=False)` bypasses mem0's LLM
  fact-extraction pass and stores the rendered text as one raw memory, with
  the full ExperienceEvent JSON preserved in the memory metadata. Retrieval
  reconstructs the exact recorded event from that payload.
* Episodes map 1:1 to mem0 `user_id` scopes, so `reset()` is a scoped
  `delete_all(user_id=...)`. Mem0 requires at least one entity id in every
  filter, so cross-episode queries use the `user_id: "*"` wildcard, which the
  Qdrant adapter skips (`_build_field_condition` returns None for "*").
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..core.config import Settings
from ..core.models import EventType, ExperienceEvent
from .base import MemoryBackend, MemoryItem, MemoryQuery, MemoryStats
from .vector_memory import _render_text

logger = logging.getLogger(__name__)

#: Payload key carrying the ExperienceEvent's id (used to find/update a memory).
_EVENT_ID_KEY = "event_id"
#: Payload key carrying the ExperienceEvent's full JSON so retrieval can
#: reconstruct the exact recorded event.
_PAYLOAD_KEY = "event_payload"

#: Embedding dimensions of the HuggingFace model the factory embeds with.
_EMBED_DIMS = 384
#: Qdrant collection name (mem0 default).
_COLLECTION = "mem0"
#: Upper bound for `get_all` used by stats() to count every memory.
_COUNT_LIMIT = 10_000
#: How many matching memories update() is willing to scan to find the event_id.
_FIND_LIMIT = 1_000


def _mem0_version() -> str | None:
    """Installed mem0ai version, or None when the package is absent.

    Uses `importlib.metadata` only — never imports the mem0 package, so the
    version is reported even when a fake client is injected.
    """

    try:
        return importlib.metadata.version("mem0ai")
    except importlib.metadata.PackageNotFoundError:
        return None


def _parse_dt(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp produced by mem0; None when unparseable."""

    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _build_mem0_client(settings: Settings) -> Any:
    """Construct a `mem0.Memory` from the benchmark settings.

    This is the only place the mem0 SDK is imported. The whole package must
    import without mem0ai installed, so the import lives behind this factory
    boundary. Telemetry is turned off *before* the import so the module-level
    telemetry singleton never initializes PostHog.
    """

    os.environ["MEM0_TELEMETRY"] = "false"

    try:
        import mem0  # noqa: PLC0415  (optional dependency, deliberately lazy)
    except ImportError as exc:
        raise RuntimeError(
            "the 'mem0' memory backend requires the 'mem0ai' package; "
            "install it with: uv pip install -e '.[mem0]'"
        ) from exc

    qdrant_path = Path(settings.mem0_qdrant_path)
    history_db_path = qdrant_path.parent / "mem0_history.db"

    # Config keys verified in the installed source (mem0ai 2.0.17):
    #   llm.config:       mem0/configs/llms/openai.py  (model/api_key/openai_base_url)
    #   embedder.config:  mem0/configs/embeddings/base.py  (huggingface provider keys)
    #   vector_store:     mem0/configs/vector_stores/qdrant.py  (path = local on-disk)
    return mem0.Memory.from_config(
        {
            "llm": {
                "provider": "openai",
                "config": {
                    "model": settings.llm_model,
                    "api_key": settings.llm_api_key,
                    "openai_base_url": settings.llm_base_url,
                    "temperature": settings.llm_temperature,
                },
            },
            "embedder": {
                "provider": "huggingface",
                "config": {
                    "model": settings.mem0_embedder_model,
                    "embedding_dims": _EMBED_DIMS,
                },
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": _COLLECTION,
                    "path": str(qdrant_path),
                    "embedding_model_dims": _EMBED_DIMS,
                    "on_disk": True,
                },
            },
            # Keep mem0's SQLite history under the results dir alongside the
            # Qdrant data, so the benchmark leaves no state in the home dir.
            "history_db_path": str(history_db_path),
            "version": "v1.1",
        }
    )


class Mem0Backend(MemoryBackend):
    """Mem0-backed memory. All blocking SDK calls run on worker threads."""

    def __init__(self, settings: Settings, memory_client: Any = None) -> None:
        self._settings = settings
        # Either an injected fake (tests) or the lazily-built real mem0 client.
        self._memory: Any = memory_client
        self._add_latency_s = 0.0
        self._add_calls = 0
        self._retrieve_latency_s = 0.0
        self._retrieve_calls = 0

    def _ensure_client(self) -> Any:
        """Build the real mem0 client on first use if none was injected."""

        if self._memory is None:
            self._memory = _build_mem0_client(self._settings)
        return self._memory

    async def add(self, event: ExperienceEvent) -> None:
        """Store a new experience event under the episode's user scope."""

        start = time.perf_counter()
        try:
            client = self._ensure_client()
            await asyncio.to_thread(self._add_sync, client, event)
        finally:
            self._add_calls += 1
            self._add_latency_s += time.perf_counter() - start

    def _add_sync(self, client: Any, event: ExperienceEvent) -> None:
        """Blocking add: store the rendered event verbatim for the episode."""

        client.add(
            messages=_render_text(event),
            user_id=event.episode_id,
            metadata={
                _EVENT_ID_KEY: event.event_id,
                _PAYLOAD_KEY: event.model_dump_json(),
            },
            infer=False,
        )

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        """Return the `query.limit` most relevant memories, best first.

        `query.episode_id` narrows to that episode's user scope; when unset the
        `user_id: "*"` wildcard makes mem0's filter a no-op, so the search
        spans every episode (the same semantics as the vector backend).
        """

        start = time.perf_counter()
        try:
            client = self._ensure_client()
            return await asyncio.to_thread(self._retrieve_sync, client, query)
        finally:
            self._retrieve_calls += 1
            self._retrieve_latency_s += time.perf_counter() - start

    def _retrieve_sync(self, client: Any, query: MemoryQuery) -> list[MemoryItem]:
        filters = (
            {"user_id": query.episode_id}
            if query.episode_id is not None
            else {"user_id": "*"}
        )
        results = client.search(
            query.query_text,
            top_k=query.limit,
            filters=filters,
            threshold=0.0,
        )
        return [self._to_memory_item(result) for result in results.get("results", [])]

    def _to_memory_item(self, result: dict[str, Any]) -> MemoryItem:
        """Map one mem0 search result dict to a MemoryItem.

        The full recorded event is reconstructed from the `event_payload`
        metadata when present; `score` is mem0's own hybrid score.
        """

        metadata = result.get("metadata") or {}
        event_id = metadata.get(_EVENT_ID_KEY)
        payload_json = metadata.get(_PAYLOAD_KEY)
        if payload_json:
            event = ExperienceEvent.model_validate(json.loads(payload_json))
        else:
            event = self._fallback_event(result)
        return MemoryItem(
            item_id=event_id or str(result.get("id", "")),
            event=event,
            score=result.get("score"),
            created_at=_parse_dt(result.get("created_at")) or datetime.now(UTC),
            metadata=dict(metadata),
        )

    @staticmethod
    def _fallback_event(result: dict[str, Any]) -> ExperienceEvent:
        """A minimal event reconstructed from the memory text alone.

        Used only when a memory carries no `event_payload` metadata (e.g. it
        was written by external mem0 tooling). The original episode/type are
        unknowable from the text, so the text is stashed in `context["text"]`
        and the type is the neutral WORLD_FACT_UPDATED. This is a
        reconstruction, never a recorded event.
        """

        return ExperienceEvent(
            event_id=str(result.get("id", "")),
            episode_id=str(result.get("user_id") or ""),
            timestamp=_parse_dt(result.get("created_at")) or datetime.now(UTC),
            actor="mem0",
            event_type=EventType.WORLD_FACT_UPDATED,
            context={"text": result.get("memory", "")},
        )

    async def update(self, event: ExperienceEvent) -> None:
        """Overwrite the stored event with the same `event_id`.

        mem0 keys memories by a fresh UUID per `add`, so the id cannot be
        derived from the event. We instead locate the memory whose metadata
        carries `event_id`, then use mem0's native `update(memory_id, ...)`
        (mem0/memory/main.py::update) — a single re-embed that keeps the same
        memory id and `created_at`, which is the closest match to the vector
        backend's overwrite. If no such memory exists we fall back to `add`
        (create), mirroring the vector backend's upsert semantics.
        """

        client = self._ensure_client()
        await asyncio.to_thread(self._update_sync, client, event)

    def _update_sync(self, client: Any, event: ExperienceEvent) -> None:
        found = client.get_all(
            filters={"user_id": event.episode_id, _EVENT_ID_KEY: event.event_id},
            top_k=_FIND_LIMIT,
        ).get("results", [])
        if found:
            client.update(
                memory_id=found[0]["id"],
                text=_render_text(event),
                metadata={
                    _EVENT_ID_KEY: event.event_id,
                    _PAYLOAD_KEY: event.model_dump_json(),
                },
            )
        else:
            self._add_sync(client, event)

    async def reset(self, episode_id: str) -> None:
        """Drop all memories belonging to one episode (its user scope)."""

        client = self._ensure_client()
        await asyncio.to_thread(self._reset_sync, client, episode_id)

    @staticmethod
    def _reset_sync(client: Any, episode_id: str) -> None:
        client.delete_all(user_id=episode_id)

    async def stats(self) -> MemoryStats:
        client = self._ensure_client()
        return await asyncio.to_thread(self._stats_sync, client)

    def _stats_sync(self, client: Any) -> MemoryStats:
        """Report backend name, total item count, and latency extras.

        `item_count` is read live from the store via an unscoped `get_all`
        (the `user_id: "*"` wildcard), because mem0 requires an entity scope
        on every query and `stats()` has no episode to scope by. Counts above
        `_COUNT_LIMIT` may undercount (Qdrant scroll truncation); a benchmark
        run stays far below that.
        """

        count = 0
        try:
            count = len(
                client.get_all(
                    filters={"user_id": "*"}, top_k=_COUNT_LIMIT
                ).get("results", [])
            )
        except Exception as exc:  # noqa: BLE001 — stats must never crash the run
            logger.warning(
                "mem0 stats: get_all failed, reporting item_count=0: %s", exc
            )
        return MemoryStats(
            backend="mem0",
            item_count=count,
            extra={
                "avg_add_latency_ms": self._avg_ms(self._add_latency_s, self._add_calls),
                "avg_retrieve_latency_ms": self._avg_ms(
                    self._retrieve_latency_s, self._retrieve_calls
                ),
                "mem0_version": _mem0_version(),
                "qdrant_path": self._settings.mem0_qdrant_path,
            },
        )

    @staticmethod
    def _avg_ms(total_s: float, calls: int) -> float | None:
        """Average latency in ms over `calls` samples; None when unmeasured."""

        return round(total_s / calls * 1000.0, 3) if calls else None
