"""LettaBackend contract tests — hermetic, no letta_client import, no network.

A `FakeLettaClient` mirrors the installed letta-client 1.12.1 surface used by
the adapter (agents.create/delete and agents.passages.create/list/search/
delete) and is injected at the constructor boundary, so nothing from the real
letta package is ever imported and no server is contacted.
"""

from __future__ import annotations

import importlib.metadata
import json
import sys
from datetime import UTC, datetime
from typing import Any

from minemembench.core.models import EventType, ExperienceEvent
from minemembench.memory.base import MemoryQuery
from minemembench.memory.letta_adapter import LettaBackend
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


class FakePassages:
    """In-memory stand-in for `client.agents.passages`.

    Mirrors the archival-memory surface of letta_client 1.12.1: create / list /
    search / delete. Search returns the agent-level result shape
    (id/content/timestamp/tags) with no score unless `fake.force_score` is set.
    """

    def __init__(self, fake: FakeLettaClient) -> None:
        self._fake = fake

    def create(
        self,
        agent_id: str,
        *,
        text: str,
        created_at: Any = None,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self._fake.calls.append(
            ("passages.create", {"agent_id": agent_id, "text": text, "tags": list(tags or [])})
        )
        passage = {
            "id": f"passage-{self._fake._next_passage_id}",
            "text": text,
            "metadata": {},
            "created_at": (created_at or datetime.now(UTC)).isoformat(),
            "tags": list(tags or []),
        }
        self._fake._next_passage_id += 1
        self._fake.passages.setdefault(agent_id, []).append(passage)
        return [dict(passage)]

    def list(
        self,
        agent_id: str,
        *,
        after: Any = None,
        ascending: Any = None,
        before: Any = None,
        limit: int | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        self._fake.calls.append(("passages.list", {"agent_id": agent_id, "limit": limit}))
        passages = [dict(p) for p in self._fake.passages.get(agent_id, [])]
        if search is not None:
            passages = [p for p in passages if search in p["text"]]
        if limit is not None:
            passages = passages[:limit]
        return passages

    def delete(self, memory_id: str, *, agent_id: str) -> Any:
        self._fake.calls.append(
            ("passages.delete", {"memory_id": memory_id, "agent_id": agent_id})
        )
        store = self._fake.passages.get(agent_id, [])
        self._fake.passages[agent_id] = [p for p in store if p["id"] != memory_id]
        return {}

    def search(
        self,
        agent_id: str,
        *,
        query: str,
        end_datetime: Any = None,
        start_datetime: Any = None,
        tag_match_mode: Any = None,
        tags: list[str] | None = None,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        self._fake.calls.append(
            ("passages.search", {"agent_id": agent_id, "query": query, "top_k": top_k})
        )
        passages = [dict(p) for p in self._fake.passages.get(agent_id, [])]
        if top_k is not None:
            passages = passages[:top_k]
        results = [
            {
                "id": p["id"],
                "content": p["text"],
                "timestamp": p["created_at"],
                "tags": p["tags"],
                "metadata": p["metadata"],
            }
            for p in passages
        ]
        if self._fake.force_score is not None:
            for result in results:
                result["score"] = self._fake.force_score
        return {"count": len(results), "results": results}


class FakeAgents:
    """In-memory stand-in for `client.agents` (create / delete)."""

    def __init__(self, fake: FakeLettaClient) -> None:
        self._fake = fake
        self.passages = FakePassages(fake)

    def create(self, *, name: str | None = None, **kwargs: Any) -> dict[str, Any]:
        self._fake.calls.append(("agents.create", {"name": name}))
        agent_id = f"agent-{self._fake._next_agent_id}"
        self._fake._next_agent_id += 1
        self._fake.agent_names[agent_id] = name
        return {"id": agent_id, "name": name}

    def delete(self, agent_id: str, **kwargs: Any) -> Any:
        self._fake.calls.append(("agents.delete", {"agent_id": agent_id}))
        self._fake.agent_names.pop(agent_id, None)
        self._fake.passages.pop(agent_id, None)
        return {}


class FakeLettaClient:
    """In-memory stand-in for the letta-client SDK client.

    Mirrors the agent / archival-memory surface the adapter uses, so the
    adapter runs against the real contract without the package.
    """

    def __init__(self) -> None:
        #: adapter-facing resource object (client.agents.create/delete/...)
        self.agents = FakeAgents(self)
        #: agent_id -> name (created by the fake, for test assertions)
        self.agent_names: dict[str, str] = {}
        #: agent_id -> list of passage dicts
        self.passages: dict[str, list[dict[str, Any]]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.force_score: float | None = None
        self._next_agent_id = 1
        self._next_passage_id = 1

    def agent_id_for(self, episode_id: str) -> str:
        """The agent id created for an episode (by its `mem-<episode>` name)."""

        matches = [
            agent_id
            for agent_id, name in self.agent_names.items()
            if name == f"mem-{episode_id}"
        ]
        assert matches, f"no agent created for episode {episode_id!r}"
        return matches[0]


def _backend(fake: FakeLettaClient | None = None) -> LettaBackend:
    return LettaBackend(
        settings=make_settings(letta_base_url="http://letta.test:8283"),
        client=fake or FakeLettaClient(),
    )


def test_module_import_does_not_import_letta() -> None:
    # Importing the adapter (and the package) must never pull in the letta SDK.
    assert "letta_client" not in sys.modules


async def test_add_retrieve_stats_contract() -> None:
    fake = FakeLettaClient()
    backend = _backend(fake)
    event = _event("e1", "ep-1", outcome="chest at the north base")
    await backend.add(event)

    # add() creates one agent per episode and stores the rendered event with a
    # parseable [event_id=...] prefix in the episode's archival memory, plus
    # the full event JSON in an `event_payload=` tag (tags are never part of
    # the embedded text).
    create_kwargs = [kwargs for method, kwargs in fake.calls if method == "agents.create"]
    assert create_kwargs == [{"name": "mem-ep-1"}]
    passage_kwargs = [
        kwargs for method, kwargs in fake.calls if method == "passages.create"
    ]
    assert passage_kwargs[0]["text"].startswith("[event_id=e1] ")
    assert passage_kwargs[0]["text"].endswith(_render_text(event))
    assert passage_kwargs[0]["tags"] == ["event_payload=" + event.model_dump_json()]
    assert passage_kwargs[0]["agent_id"] == fake.agent_id_for("ep-1")

    items = await backend.retrieve(MemoryQuery(query_text="where is the chest", episode_id="ep-1"))
    assert len(items) == 1
    # The payload tag round-trips the EXACT recorded event: every identifying
    # field equals what was written, without any process-local side channel.
    assert items[0].item_id == "e1"
    assert items[0].event == event
    assert items[0].score is None  # agent-level search returns no score
    assert items[0].created_at.tzinfo is not None

    stats = await backend.stats()
    assert stats.backend == "letta"
    assert stats.item_count == 1
    assert stats.extra["avg_add_latency_ms"] is not None
    assert stats.extra["avg_retrieve_latency_ms"] is not None
    assert stats.extra["letta_version"] == importlib.metadata.version("letta-client")
    assert stats.extra["base_url"] == "http://letta.test:8283"
    assert "client boundary" in stats.extra["item_count_scope"]


async def test_episode_scoping_one_agent_per_episode() -> None:
    fake = FakeLettaClient()
    backend = _backend(fake)
    await backend.add(_event("e1", "ep-1", outcome="chest at the north base"))
    await backend.add(_event("e2", "ep-2", outcome="chest at the south base"))

    # Exactly one agent per episode, each storing only its own events.
    assert len(fake.agent_names) == 2
    assert set(fake.agent_names.values()) == {"mem-ep-1", "mem-ep-2"}
    assert len(fake.passages[fake.agent_id_for("ep-1")]) == 1
    assert len(fake.passages[fake.agent_id_for("ep-2")]) == 1

    scoped = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert [item.item_id for item in scoped] == ["e1"]
    search_kwargs = [
        kwargs for method, kwargs in fake.calls if method == "passages.search"
    ]
    assert search_kwargs[0]["agent_id"] == fake.agent_id_for("ep-1")
    assert search_kwargs[0]["top_k"] == 10  # query.limit passthrough

    # No episode -> best-effort union across the process's cached agents.
    unscoped = await backend.retrieve(MemoryQuery(query_text="chest"))
    assert {item.item_id for item in unscoped} == {"e1", "e2"}


async def test_score_none_when_client_returns_none() -> None:
    fake = FakeLettaClient()
    backend = _backend(fake)
    await backend.add(_event("e1", "ep-1", outcome="chest at the base"))

    items = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert items[0].score is None  # never invent a score Letta did not return


async def test_score_passthrough_when_client_returns_one() -> None:
    fake = FakeLettaClient()
    backend = _backend(fake)
    await backend.add(_event("e1", "ep-1", outcome="chest at the base"))
    fake.force_score = 0.87

    items = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert items[0].score == 0.87


async def test_update_replaces_content_not_appends() -> None:
    fake = FakeLettaClient()
    backend = _backend(fake)
    await backend.add(_event("e1", "ep-1", outcome="chest is at the north base"))
    await backend.update(_event("e1", "ep-1", outcome="chest is at the south base"))

    # No in-place update exists: the old passage is deleted then re-inserted.
    delete_kwargs = [
        kwargs for method, kwargs in fake.calls if method == "passages.delete"
    ]
    assert delete_kwargs[0]["agent_id"] == fake.agent_id_for("ep-1")
    assert (await backend.stats()).item_count == 1  # updated, never appended

    items = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert [item.item_id for item in items] == ["e1"]
    # Exact round-trip: the retrieved event IS the updated event.
    assert items[0].event.outcome == "chest is at the south base"


async def test_legacy_passage_without_payload_tag_falls_back_to_prefix() -> None:
    """A passage written without an `event_payload=` tag (older versions,
    external tooling) still reconstructs minimally from the text prefix:
    the stable event_id survives, the body is stashed as context text."""

    fake = FakeLettaClient()
    backend = _backend(fake)
    await backend.add(_event("e1", "ep-1", outcome="chest at the base"))
    agent_id = fake.agent_id_for("ep-1")
    fake.passages[agent_id][0]["tags"] = []  # simulate a pre-payload passage

    items = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert items[0].item_id == "e1"
    assert items[0].event.event_id == "e1"
    assert items[0].event.event_type == EventType.WORLD_FACT_UPDATED
    assert items[0].event.context["text"].endswith("chest at the base")


async def test_update_creates_when_event_missing() -> None:
    fake = FakeLettaClient()
    backend = _backend(fake)
    await backend.update(_event("e1", "ep-1", outcome="chest at the north base"))

    items = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert [item.item_id for item in items] == ["e1"]
    assert (await backend.stats()).item_count == 1


async def test_reset_deletes_only_that_episode_agent() -> None:
    fake = FakeLettaClient()
    backend = _backend(fake)
    await backend.add(_event("e1", "ep-1", outcome="chest at the north base"))
    await backend.add(_event("e2", "ep-2", outcome="diamonds deep underground"))

    ep1_agent = fake.agent_id_for("ep-1")
    await backend.reset("ep-1")

    assert (await backend.stats()).item_count == 1
    assert ep1_agent not in fake.agent_names  # agent gone -> archival memory gone
    delete_kwargs = [
        kwargs for method, kwargs in fake.calls if method == "agents.delete"
    ]
    assert delete_kwargs[-1]["agent_id"] == ep1_agent

    items = await backend.retrieve(MemoryQuery(query_text="diamonds underground"))
    assert [item.event.episode_id for item in items] == ["ep-2"]


async def test_reset_unknown_episode_is_noop() -> None:
    fake = FakeLettaClient()
    backend = _backend(fake)
    await backend.reset("ep-never-seen")

    assert [m for m, _ in fake.calls] == []
    assert (await backend.stats()).item_count == 0


async def test_payload_metadata_reconstruction_when_available() -> None:
    fake = FakeLettaClient()
    backend = _backend(fake)
    event = _event("e1", "ep-1", outcome="chest at the base")
    await backend.add(event)
    # Simulate a metadata-capable insert path: the passage now carries the
    # full event payload, so retrieval must reconstruct the exact event.
    agent_id = fake.agent_id_for("ep-1")
    fake.passages[agent_id][0]["metadata"] = {
        "event_id": "e1",
        "event_payload": event.model_dump_json(),
    }

    items = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert items[0].item_id == "e1"
    assert items[0].event.event_type == EventType.RESOURCE_DISCOVERED
    assert items[0].event.outcome == "chest at the base"


async def test_stats_latency_fields_are_none_before_any_call() -> None:
    fake = FakeLettaClient()
    backend = _backend(fake)
    stats = await backend.stats()
    assert stats.item_count == 0
    assert stats.extra["avg_add_latency_ms"] is None
    assert stats.extra["avg_retrieve_latency_ms"] is None
    assert stats.extra["letta_version"] == importlib.metadata.version("letta-client")


async def test_construction_with_no_client_is_lazy() -> None:
    # No injected client and no server configured: construction must succeed
    # and only build the real client on first use.
    backend = LettaBackend(settings=make_settings(letta_base_url="http://letta.test:8283"))
    assert backend._client is None
    assert backend._agents == {}
    assert "letta_client" not in sys.modules
