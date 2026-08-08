"""GraphitiBackend contract tests — hermetic, no graphiti_core import, no network.

A `FakeGraphitiClient` mirrors the installed graphiti-core 0.29.3 surface used
by the adapter (add_episode / search / retrieve_episodes / remove_episode, plus
a `driver.execute_query` for the stats fact count) and is injected at the
constructor boundary, so nothing from the real graphiti package is ever imported
and no LLM call, graph server, or model download happens.
"""

from __future__ import annotations

import importlib.metadata
import sys
from datetime import UTC, datetime
from typing import Any

from minemembench.core.models import EventType, ExperienceEvent
from minemembench.memory.base import MemoryQuery
from minemembench.memory.graphiti_adapter import GraphitiBackend
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


class FakeGraphitiDriver:
    """In-memory stand-in for the graphiti graph driver.

    The adapter only reaches through the client's `driver` to count distilled
    facts for stats(); the fake mirrors the `execute_query` response shape of
    the real KuzuDriver (a list of row dicts).
    """

    provider = "fake"

    def __init__(self, fake: FakeGraphitiClient) -> None:
        self._fake = fake

    async def execute_query(self, cypher_query_: str, **kwargs: Any) -> Any:
        self._fake.calls.append(
            ("driver.execute_query", {"cypher": cypher_query_})
        )
        if "count(*)" in cypher_query_:
            return [{"c": len(self._fake.edges)}], None, None
        return [], None, None


class FakeGraphitiClient:
    """In-memory stand-in for the graphiti-core `Graphiti` client.

    Mirrors the surface the adapter uses (add_episode / search /
    retrieve_episodes / remove_episode / driver.execute_query) and the dict
    shapes graphiti returns. Each `add_episode` distills exactly one fact edge
    carrying the episode body as its `fact`, so retrieval and stats are
    predictable. Search returns no score unless `force_score` is set.
    """

    def __init__(self) -> None:
        self.episodes: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.force_score: float | None = None
        self.driver = FakeGraphitiDriver(self)
        self._next_episode_id = 1
        self._next_edge_id = 1

    async def add_episode(
        self,
        name: str,
        episode_body: str,
        source_description: str,
        reference_time: Any,
        source: Any = None,
        group_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "add_episode",
                {
                    "name": name,
                    "episode_body": episode_body,
                    "source_description": source_description,
                    "reference_time": reference_time,
                    "source": source,
                    "group_id": group_id,
                },
            )
        )
        now = datetime.now(UTC)
        episode_uuid = f"ep-{self._next_episode_id}"
        self._next_episode_id += 1
        self.episodes.append(
            {
                "uuid": episode_uuid,
                "name": name,
                "group_id": group_id,
                "source": getattr(source, "value", source),
                "content": episode_body,
                "created_at": now.isoformat(),
                "valid_at": reference_time.isoformat(),
            }
        )
        edge_uuid = f"edge-{self._next_edge_id}"
        self._next_edge_id += 1
        self.edges.append(
            {
                "uuid": edge_uuid,
                "group_id": group_id,
                "name": "relates_to",
                "fact": episode_body,
                "created_at": now.isoformat(),
                "valid_at": reference_time.isoformat(),
                "invalid_at": None,
                "expired_at": None,
                "episodes": [episode_uuid],
                "source_node_uuid": f"node-a-{group_id}",
                "target_node_uuid": f"node-b-{group_id}",
            }
        )
        return {"episode": {"uuid": episode_uuid}}

    async def search(
        self,
        query: str,
        center_node_uuid: str | None = None,
        group_ids: list[str] | None = None,
        num_results: int = 10,
        search_filter: Any = None,
        driver: Any = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            ("search", {"query": query, "group_ids": group_ids, "num_results": num_results})
        )
        results = [dict(edge) for edge in self.edges]
        if group_ids:
            results = [edge for edge in results if edge["group_id"] in group_ids]
        results = results[:num_results]
        if self.force_score is not None:
            for edge in results:
                edge["score"] = self.force_score
        return results

    async def retrieve_episodes(
        self,
        reference_time: Any,
        last_n: int = 10,
        group_ids: list[str] | None = None,
        source: Any = None,
        driver: Any = None,
        saga: Any = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            ("retrieve_episodes", {"group_ids": group_ids, "last_n": last_n})
        )
        results = [
            dict(episode)
            for episode in self.episodes
            if not group_ids or episode["group_id"] in group_ids
        ]
        return results[:last_n]

    async def remove_episode(self, episode_uuid: str, **kwargs: Any) -> None:
        self.calls.append(("remove_episode", {"episode_uuid": episode_uuid}))
        self.episodes = [
            episode
            for episode in self.episodes
            if episode["uuid"] != episode_uuid
        ]
        self.edges = [
            edge for edge in self.edges if edge["episodes"][0] != episode_uuid
        ]


def _backend(fake: FakeGraphitiClient | None = None) -> GraphitiBackend:
    return GraphitiBackend(
        settings=make_settings(graphiti_kuzu_path="results/graphiti_kuzu"),
        graphiti_client=fake or FakeGraphitiClient(),
    )


def test_module_import_does_not_import_graphiti() -> None:
    # Importing the adapter (and the package) must never pull in the graphiti SDK.
    assert "graphiti_core" not in sys.modules


async def test_add_retrieve_stats_contract() -> None:
    fake = FakeGraphitiClient()
    backend = _backend(fake)
    event = _event("e1", "ep-1", outcome="chest at the north base")
    await backend.add(event)

    # add() distills one episode into the event's group_id partition, carrying
    # the faithfully rendered event text as the episode body.
    method, kwargs = fake.calls[0]
    assert method == "add_episode"
    assert kwargs["name"] == "e1"
    assert kwargs["episode_body"] == _render_text(event)
    assert kwargs["group_id"] == "ep-1"
    assert kwargs["source"] == "text"  # EpisodeType.text, not the SDK default
    assert kwargs["reference_time"] == event.timestamp

    items = await backend.retrieve(
        MemoryQuery(query_text="where is the chest", episode_id="ep-1")
    )
    assert len(items) == 1
    # Graphiti returns a distilled fact, so the reconstructed event is minimal:
    # the fact text in context, neutral type, scored by the client (None here).
    assert items[0].item_id.startswith("edge-")
    assert items[0].event.event_id == items[0].item_id
    assert items[0].event.event_type == EventType.WORLD_FACT_UPDATED
    assert items[0].event.context["text"] == _render_text(event)
    assert items[0].event.context["name"] == "relates_to"
    assert items[0].event.episode_id == "ep-1"
    assert items[0].score is None  # Graphiti.search() returns no score
    assert items[0].created_at.tzinfo is not None
    assert items[0].metadata["source_node_uuid"].startswith("node-a-")

    stats = await backend.stats()
    assert stats.backend == "graphiti"
    assert stats.item_count == 1
    assert stats.extra["avg_add_latency_ms"] is not None
    assert stats.extra["avg_retrieve_latency_ms"] is not None
    assert stats.extra["graphiti_version"] == importlib.metadata.version("graphiti-core")
    assert stats.extra["driver_mode"] == "fake"
    assert "facts" in stats.extra["item_count_scope"]


async def test_episode_scoping_in_search_filters() -> None:
    fake = FakeGraphitiClient()
    backend = _backend(fake)
    await backend.add(_event("e1", "ep-1", outcome="chest at the north base"))
    await backend.add(_event("e2", "ep-2", outcome="chest at the south base"))

    scoped = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert [item.event.context["text"] for item in scoped] == [
        _render_text(_event("e1", "ep-1", outcome="chest at the north base"))
    ]
    search_kwargs = [kwargs for method, kwargs in fake.calls if method == "search"]
    assert search_kwargs[0]["group_ids"] == ["ep-1"]
    assert search_kwargs[0]["num_results"] == 10  # query.limit passthrough

    unscoped = await backend.retrieve(MemoryQuery(query_text="chest"))
    assert len(unscoped) == 2
    search_kwargs = [kwargs for method, kwargs in fake.calls if method == "search"]
    assert search_kwargs[1]["group_ids"] is None  # no episode -> every partition


async def test_score_none_when_client_returns_none() -> None:
    fake = FakeGraphitiClient()
    backend = _backend(fake)
    await backend.add(_event("e1", "ep-1", outcome="chest at the base"))

    items = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert items[0].score is None  # never invent a score Graphiti did not return


async def test_score_passthrough_when_client_returns_one() -> None:
    fake = FakeGraphitiClient()
    backend = _backend(fake)
    await backend.add(_event("e1", "ep-1", outcome="chest at the base"))
    fake.force_score = 0.87

    items = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert items[0].score == 0.87


async def test_fact_temporal_fields_map_into_context() -> None:
    fake = FakeGraphitiClient()
    backend = _backend(fake)
    await backend.add(_event("e1", "ep-1", outcome="chest at the north base"))
    # Mark the distilled fact as superseded: graphiti's temporal model.
    fake.edges[0]["invalid_at"] = "2026-08-08T12:05:00+00:00"

    items = await backend.retrieve(MemoryQuery(query_text="chest", episode_id="ep-1"))
    assert items[0].event.context["valid_at"] == "2026-08-08T12:00:00+00:00"
    assert items[0].event.context["invalid_at"] == "2026-08-08T12:05:00+00:00"


async def test_update_adds_new_episode_for_belief_update() -> None:
    fake = FakeGraphitiClient()
    backend = _backend(fake)
    await backend.add(_event("e1", "ep-1", outcome="chest is at the north base"))
    await backend.update(_event("e1", "ep-1", outcome="chest is at the south base"))

    # No in-place fact update exists: graphiti supersedes facts temporally by
    # ingesting the corrected statement as a new episode.
    add_kwargs = [kwargs for method, kwargs in fake.calls if method == "add_episode"]
    assert len(add_kwargs) == 2
    assert add_kwargs[1]["group_id"] == "ep-1"
    assert add_kwargs[1]["episode_body"].endswith("chest is at the south base")
    assert len(fake.episodes) == 2
    assert (await backend.stats()).item_count == 2  # one distilled fact per episode


async def test_reset_removes_only_that_episode() -> None:
    fake = FakeGraphitiClient()
    backend = _backend(fake)
    await backend.add(_event("e1", "ep-1", outcome="chest at the north base"))
    await backend.add(_event("e2", "ep-2", outcome="diamonds deep underground"))

    ep1_uuid = fake.episodes[0]["uuid"]
    await backend.reset("ep-1")

    assert (await backend.stats()).item_count == 1
    retrieve_kwargs = [
        kwargs for method, kwargs in fake.calls if method == "retrieve_episodes"
    ]
    assert retrieve_kwargs[-1]["group_ids"] == ["ep-1"]
    remove_kwargs = [
        kwargs for method, kwargs in fake.calls if method == "remove_episode"
    ]
    assert remove_kwargs == [{"episode_uuid": ep1_uuid}]

    items = await backend.retrieve(MemoryQuery(query_text="diamonds underground"))
    assert [item.event.episode_id for item in items] == ["ep-2"]


async def test_reset_unknown_episode_is_noop() -> None:
    fake = FakeGraphitiClient()
    backend = _backend(fake)
    await backend.reset("ep-never-seen")

    remove_kwargs = [
        kwargs for method, kwargs in fake.calls if method == "remove_episode"
    ]
    assert remove_kwargs == []
    assert (await backend.stats()).item_count == 0


async def test_stats_latency_fields_are_none_before_any_call() -> None:
    fake = FakeGraphitiClient()
    backend = _backend(fake)
    stats = await backend.stats()
    assert stats.item_count == 0
    assert stats.extra["avg_add_latency_ms"] is None
    assert stats.extra["avg_retrieve_latency_ms"] is None
    assert stats.extra["graphiti_version"] == importlib.metadata.version("graphiti-core")


async def test_construction_with_no_client_is_lazy() -> None:
    # No injected client: construction must succeed and only build the real
    # client (importing graphiti-core) on first use.
    backend = GraphitiBackend(settings=make_settings())
    assert backend._graphiti is None
    assert backend._driver_mode == "uninitialized"
    assert "graphiti_core" not in sys.modules
