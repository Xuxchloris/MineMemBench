"""Mem0Backend contract tests — hermetic, no mem0ai import, no network.

A `FakeMemoryClient` mirrors the installed mem0 SDK surface (add / search /
get_all / update / delete / delete_all) and is injected at the constructor
boundary, so nothing from the real mem0 package is ever imported and no model
is downloaded.
"""

from __future__ import annotations

import importlib.metadata
import json
import sys
from datetime import UTC, datetime
from typing import Any

from minemembench.core.models import EventType, ExperienceEvent
from minemembench.memory.base import MemoryQuery
from minemembench.memory.mem0_adapter import Mem0Backend
from minemembench.memory.vector_memory import _render_text

from .conftest import make_settings


def _event(
    event_id: str,
    episode_id: str,
    *,
    event_type: EventType = EventType.RESOURCE_DISCOVERED,
    target: str | None = None,
    context: dict | None = None,
    outcome: str | None = None,
) -> ExperienceEvent:
    return ExperienceEvent(
        event_id=event_id,
        episode_id=episode_id,
        timestamp=datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC),
        actor="agent",
        target=target,
        event_type=event_type,
        context=context or {},
        outcome=outcome,
    )


class FakeMemoryClient:
    """In-memory stand-in for the mem0 SDK client.

    Mirrors the signatures mem0 2.0.17 exposes (add/search/get_all/update/
    delete/delete_all) and the dict shapes it returns, so the adapter runs
    against the real contract without the package.
    """

    def __init__(self) -> None:
        self.memories: list[dict[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._next_id = 1

    def _record(self, method: str, kwargs: dict[str, Any]) -> None:
        self.calls.append((method, kwargs))

    def _matches(self, memory: dict[str, Any], filters: dict | None) -> bool:
        if not filters:
            return True
        for key, value in filters.items():
            if value == "*":
                continue  # wildcard: mem0/Qdrant skip "*" conditions
            if key in ("user_id", "agent_id", "run_id"):
                if memory.get(key) != value:
                    return False
            elif memory.get("metadata", {}).get(key) != value:
                return False
        return True

    def add(
        self,
        messages: Any,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        metadata: dict | None = None,
        timestamp: Any = None,
        expiration_date: Any = None,
        infer: bool = True,
        memory_type: str | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        self._record("add", {"messages": messages, "user_id": user_id, "metadata": metadata, "infer": infer})
        content = messages if isinstance(messages, str) else messages[0]["content"]
        memory = {
            "id": f"mem-{self._next_id}",
            "memory": content,
            "score": 0.5,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "user_id": user_id,
            "metadata": dict(metadata or {}),
        }
        self._next_id += 1
        self.memories.append(memory)
        return {"results": [{"id": memory["id"], "memory": content, "event": "ADD"}]}

    def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        filters: dict | None = None,
        threshold: float = 0.1,
        rerank: bool = False,
        explain: bool = False,
        reference_date: Any = None,
        show_expired: bool = False,
    ) -> dict[str, Any]:
        self._record("search", {"query": query, "top_k": top_k, "filters": filters, "threshold": threshold})
        results = [
            dict(memory) for memory in self.memories if self._matches(memory, filters)
        ]
        return {"results": results[:top_k]}

    def get_all(
        self,
        *,
        filters: dict | None = None,
        top_k: int = 20,
        show_expired: bool = False,
    ) -> dict[str, Any]:
        self._record("get_all", {"filters": filters, "top_k": top_k})
        results = [
            dict(memory) for memory in self.memories if self._matches(memory, filters)
        ]
        return {"results": results[:top_k]}

    def update(
        self,
        memory_id: str,
        text: str | None = None,
        metadata: dict | None = None,
        expiration_date: Any = None,
        data: str | None = None,
    ) -> dict[str, Any]:
        self._record("update", {"memory_id": memory_id, "text": text, "metadata": metadata})
        for memory in self.memories:
            if memory["id"] == memory_id:
                memory["memory"] = text or data or memory["memory"]
                if metadata:
                    memory["metadata"].update(metadata)
                memory["updated_at"] = datetime.now(UTC).isoformat()
                return {"message": "Memory updated successfully!"}
        raise ValueError(f"Memory with id {memory_id} not found")

    def delete(self, memory_id: str) -> dict[str, Any]:
        self._record("delete", {"memory_id": memory_id})
        self.memories = [m for m in self.memories if m["id"] != memory_id]
        return {"message": "Memory deleted successfully!"}

    def delete_all(
        self,
        user_id: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        self._record("delete_all", {"user_id": user_id, "agent_id": agent_id, "run_id": run_id})
        scope = {k: v for k, v in (("user_id", user_id), ("agent_id", agent_id), ("run_id", run_id)) if v}
        self.memories = [m for m in self.memories if not self._matches(m, scope)]
        return {"message": "Memories deleted successfully!"}


def _backend(fake: FakeMemoryClient | None = None, tmp_path=None) -> Mem0Backend:
    return Mem0Backend(
        settings=make_settings(mem0_qdrant_path=str(tmp_path / "mem0_qdrant") if tmp_path else "results/mem0_qdrant"),
        memory_client=fake or FakeMemoryClient(),
    )


def test_module_import_does_not_import_mem0() -> None:
    # Importing the adapter (and the package) must never pull in the mem0 SDK.
    assert "mem0" not in sys.modules


async def test_add_retrieve_stats_contract(tmp_path) -> None:
    fake = FakeMemoryClient()
    backend = _backend(fake, tmp_path)
    event = _event("e1", "ep-1", outcome="chest at the north base")
    await backend.add(event)

    # add() stores the rendered event verbatim with infer=False and the full
    # payload in metadata, scoped to the episode.
    method, kwargs = fake.calls[0]
    assert method == "add"
    assert kwargs["messages"] == _render_text(event)
    assert kwargs["user_id"] == "ep-1"
    assert kwargs["infer"] is False
    assert kwargs["metadata"]["event_id"] == "e1"
    assert json.loads(kwargs["metadata"]["event_payload"])["outcome"] == "chest at the north base"

    items = await backend.retrieve(MemoryQuery(query_text="where is the chest", episode_id="ep-1"))
    assert len(items) == 1
    assert items[0].item_id == "e1"
    assert items[0].event.outcome == "chest at the north base"
    assert items[0].event.event_id == "e1"
    assert items[0].score is not None
    assert items[0].created_at.tzinfo is not None

    stats = await backend.stats()
    assert stats.backend == "mem0"
    assert stats.item_count == 1
    assert stats.extra["avg_add_latency_ms"] is not None
    assert stats.extra["avg_retrieve_latency_ms"] is not None
    assert stats.extra["mem0_version"] == importlib.metadata.version("mem0ai")
    assert stats.extra["qdrant_path"].endswith("mem0_qdrant")


async def test_episode_scoping_in_search_filters(tmp_path) -> None:
    fake = FakeMemoryClient()
    backend = _backend(fake, tmp_path)
    await backend.add(_event("e1", "ep-1", outcome="chest at the north base"))
    await backend.add(_event("e2", "ep-2", outcome="chest at the south base"))

    scoped = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert [item.item_id for item in scoped] == ["e1"]
    search_kwargs = [kwargs for method, kwargs in fake.calls if method == "search"]
    assert search_kwargs[0]["filters"] == {"user_id": "ep-1"}

    # No episode -> the wildcard user scope spans every episode.
    unscoped = await backend.retrieve(MemoryQuery(query_text="chest"))
    assert {item.item_id for item in unscoped} == {"e1", "e2"}
    search_kwargs = [kwargs for method, kwargs in fake.calls if method == "search"]
    assert search_kwargs[1]["filters"] == {"user_id": "*"}
    assert search_kwargs[1]["top_k"] == 10  # query.limit passthrough


async def test_score_passthrough(tmp_path) -> None:
    fake = FakeMemoryClient()
    backend = _backend(fake, tmp_path)
    await backend.add(_event("e1", "ep-1", outcome="chest at the base"))
    fake.memories[0]["score"] = 0.87

    items = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert items[0].score == 0.87


async def test_update_overwrites_stale_content(tmp_path) -> None:
    fake = FakeMemoryClient()
    backend = _backend(fake, tmp_path)
    await backend.add(_event("e1", "ep-1", outcome="chest is at the north base"))
    await backend.update(_event("e1", "ep-1", outcome="chest is at the south base"))

    items = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert [item.item_id for item in items] == ["e1"]
    assert items[0].event.outcome == "chest is at the south base"
    assert (await backend.stats()).item_count == 1  # updated, never appended


async def test_update_creates_when_event_missing(tmp_path) -> None:
    fake = FakeMemoryClient()
    backend = _backend(fake, tmp_path)
    await backend.update(_event("e1", "ep-1", outcome="chest at the north base"))

    items = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert [item.item_id for item in items] == ["e1"]
    assert (await backend.stats()).item_count == 1


async def test_reset_clears_only_that_episode(tmp_path) -> None:
    fake = FakeMemoryClient()
    backend = _backend(fake, tmp_path)
    await backend.add(_event("e1", "ep-1", outcome="chest at the north base"))
    await backend.add(_event("e2", "ep-2", outcome="diamonds deep underground"))

    await backend.reset("ep-1")

    assert (await backend.stats()).item_count == 1
    items = await backend.retrieve(MemoryQuery(query_text="diamonds underground"))
    assert [item.event.episode_id for item in items] == ["ep-2"]
    reset_kwargs = [kwargs for method, kwargs in fake.calls if method == "delete_all"]
    assert reset_kwargs[-1]["user_id"] == "ep-1"


async def test_fallback_event_reconstruction_when_payload_absent(tmp_path) -> None:
    fake = FakeMemoryClient()
    backend = _backend(fake, tmp_path)
    await backend.add(_event("e1", "ep-1", outcome="chest at the base"))
    # Strip the payload metadata: the memory now carries only the text.
    fake.memories[0]["metadata"] = {"event_id": "e1"}

    items = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert items[0].item_id == "e1"  # event_id still readable from metadata
    assert items[0].event.event_type == EventType.WORLD_FACT_UPDATED
    assert items[0].event.context["text"] == _render_text(
        _event("e1", "ep-1", outcome="chest at the base")
    )
    assert items[0].event.episode_id == "ep-1"


async def test_stats_latency_fields_are_none_before_any_call(tmp_path) -> None:
    fake = FakeMemoryClient()
    backend = _backend(fake, tmp_path)
    stats = await backend.stats()
    assert stats.item_count == 0
    assert stats.extra["avg_add_latency_ms"] is None
    assert stats.extra["avg_retrieve_latency_ms"] is None
    assert "mem0_version" in stats.extra
