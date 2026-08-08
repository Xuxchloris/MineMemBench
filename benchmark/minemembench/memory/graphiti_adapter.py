"""The `graphiti` memory backend: an adapter over the graphiti-core SDK.

Graphiti is the temporal-knowledge-graph memory framework (Scenario-B native).
It maintains a temporal knowledge graph: each `add_episode` call runs an LLM
extraction pass that distills the rendered event into entity nodes and fact
edges, and a later episode that contradicts an earlier one *invalidates* the
stale edge (setting `invalid_at`/`expired_at`). That invalidation is graphiti's
native update semantics, so `update()` re-adds the event as a new episode rather
than overwriting in place.

Episodes map 1:1 to graphiti `group_id` partitions, so retrieval filters by
`group_ids=[episode_id]` and `reset()` removes every episode in the partition.
Everything goes through the `MemoryBackend` plugin contract, so the planner
never sees graphiti.

Design notes (all verified against the installed graphiti-core 0.29.3 source):

* The SDK is imported lazily, only inside `_build_graphiti_client()`, so this
  module and the whole package import cleanly when graphiti-core is absent.
* Graphiti's SDK is natively async, so unlike the sync mem0/letta SDKs the
  `asyncio.to_thread(...)` blocking-call bridge is NOT used here; the async
  `MemoryBackend` methods await the SDK directly.
* Retrieval uses `Graphiti.search()` (graphiti_core/graphiti.py::search), which
  returns `list[EntityEdge]` with NO per-edge relevance score, so
  `MemoryItem.score` is `None` unless the injected client returns one — never
  invented. Each edge is a *distilled fact* (edges.py::EntityEdge), not the raw
  event, so the reconstructed ExperienceEvent is minimal: the fact text in
  `context["text"]` plus the edge's `name`/`valid_at`/`invalid_at`, typed as the
  neutral WORLD_FACT_UPDATED.
* Graphiti has no in-place fact update; the temporal model supersedes a fact by
  invalidating it (edges.py::EntityEdge.invalid_at/expired_at) when a new
  episode contradicts it, so `update()` is an `add_episode` of the updated
  event — documented as graphiti's update semantics.
* `reset()` uses only the public API: `retrieve_episodes(group_ids=[episode_id])`
  followed by `remove_episode(uuid)` per episode (graphiti.py::remove_episode).
* Embedded mode runs Kuzu in-process (driver/kuzu_driver.py::KuzuDriver,
  `db` = a local directory path). Kuzu is deprecated upstream (the driver warns
  at construction) and its `build_indices_and_constraints()` is a verified
  no-op, so the factory creates the bm25 fulltext indexes search() relies on
  through the driver's `graph_ops` interface (graph_queries.py get_fulltext_indices).
* The LLM is DeepSeek via the OpenAI-compatible generic client
  (llm_client/openai_generic_client.py::OpenAIGenericClient) in `json_object`
  mode, because DeepSeek does not support native `json_schema` structured
  output. The default cross-encoder would require an OpenAI key and is never
  used by our RRF search recipe, so a no-op one is injected.
* Episodes are tagged `EpisodeType.text` — there is no `episodic` value in
  graphiti-core 0.29.3 (nodes.py::EpisodeType: message/json/text/fact_triple).
  The real client receives the resolved enum; injected fakes receive the
  `"text"` string.
* Telemetry is disabled before the first `import graphiti_core`
  (`GRAPHITI_TELEMETRY_ENABLED=false`), so the benchmark never phones home.
* In the Kuzu graph every entity edge is stored as a `RelatesToNode_` node, so
  `stats()` counts those nodes as a best-effort "distilled facts in the store"
  figure (there is no count method on the Graphiti class).
"""

from __future__ import annotations

import asyncio
import importlib.metadata
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

#: Human-readable description attached to every episode (graphiti's
#: `source_description` argument).
_SOURCE_DESCRIPTION = "minemembench episodic record, distilled by graphiti"
#: Episode source tag. Graphiti-core 0.29.3 has no `episodic` EpisodeType value
#: (nodes.py::EpisodeType), so the closest fit for a plain rendered event text
#: is `text`. The real factory resolves this into the SDK enum.
_EPISODE_SOURCE = "text"
#: Upper bound for the per-episode reset scan and the fact-count query.
_COUNT_LIMIT = 10_000
#: Kuzu stores every entity edge as a RelatesToNode_ node; counting those nodes
#: is the "facts in the store" figure for stats().
_COUNT_FACTS_CYPHER = "MATCH (e:RelatesToNode_) RETURN count(*) AS c"


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Read a field from either a dict (fake) or a pydantic SDK object."""

    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _graphiti_version() -> str | None:
    """Installed graphiti-core version, or None when the package is absent.

    Uses `importlib.metadata` only — never imports the graphiti package, so the
    version is reported even when a fake client is injected.
    """

    try:
        return importlib.metadata.version("graphiti-core")
    except importlib.metadata.PackageNotFoundError:
        return None


def _parse_dt(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp produced by graphiti; None when unparseable."""

    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


async def _build_graphiti_client(settings: Settings) -> tuple[Any, Any, str]:
    """Construct the real graphiti client from the benchmark settings.

    This is the only place the graphiti-core SDK (and its transitive imports,
    including kuzu) is imported. Telemetry is turned off *before* the import.
    Returns (graphiti, episode_source_enum, driver_mode).

    The construction order matters and was verified against graphiti-core
    0.29.3:

    * `Graphiti(graph_driver=...)` skips the Neo4j credentials path
      (graphiti.py::__init__). Without a graph_driver it would build a
      Neo4jDriver from `uri/user/password`.
    * The default `cross_encoder` (`OpenAIRerankerClient`) requires an OpenAI
      key, so a no-op one is injected — the RRF search recipe never calls it.
    * `KuzuDriver.build_indices_and_constraints()` is a verified no-op
      (driver/kuzu_driver.py), so the bm25 fulltext indexes `Graphiti.search()`
      relies on are created through the driver's `graph_ops` interface.
    * The embedder wraps a local sentence-transformers model; the heavy model
      load is deferred to the first `create`/`create_batch` call.
    """

    os.environ["GRAPHITI_TELEMETRY_ENABLED"] = "false"

    try:
        from graphiti_core.cross_encoder.client import CrossEncoderClient
        from graphiti_core.driver.kuzu_driver import KuzuDriver
        from graphiti_core.embedder.client import EmbedderClient
        from graphiti_core.graphiti import Graphiti
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.llm_client.openai_generic_client import (
            OpenAIGenericClient,
        )
        from graphiti_core.nodes import EpisodeType
    except ImportError as exc:
        raise RuntimeError(
            "the 'graphiti' memory backend requires the 'graphiti-core' and "
            "'kuzu' packages; install them with: "
            "uv pip install -e '.[graphiti]'"
        ) from exc

    class _SentenceTransformerEmbedder(EmbedderClient):
        """EmbedderClient wrapping a local sentence-transformers model.

        The model is loaded lazily on the first embedding call so constructing
        the client never downloads or loads a model; blocking `encode` calls run
        on a worker thread.
        """

        def __init__(self, model_name_or_path: str) -> None:
            self._model_name = model_name_or_path
            self._model: Any = None

        def _ensure_model(self) -> Any:
            if self._model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise RuntimeError(
                        "graphiti live embedding requires the "
                        "'sentence-transformers' package; install it with: "
                        "uv pip install -e '.[graphiti]'"
                    ) from exc
                self._model = SentenceTransformer(self._model_name)
            return self._model

        async def create(
            self, input_data: str | list[str] | Any
        ) -> list[float]:
            return await asyncio.to_thread(self._create_sync, input_data)

        def _create_sync(self, input_data: str | list[str]) -> list[float]:
            model = self._ensure_model()
            if isinstance(input_data, str):
                vector = model.encode(input_data, normalize_embeddings=True)
            else:
                vector = model.encode(list(input_data), normalize_embeddings=True)[0]
            return [float(value) for value in vector]

        async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
            return await asyncio.to_thread(self._create_batch_sync, input_data_list)

        def _create_batch_sync(self, input_data_list: list[str]) -> list[list[float]]:
            model = self._ensure_model()
            vectors = model.encode(list(input_data_list), normalize_embeddings=True)
            return [[float(value) for value in vector] for vector in vectors]

    class _NoOpCrossEncoder(CrossEncoderClient):
        """Cross-encoder placeholder — the RRF search recipe never calls it.

        Graphiti's default `OpenAIRerankerClient` would require an OpenAI key
        and uses the Responses API, neither of which applies to the DeepSeek
        setup. Our hybrid search reranks with reciprocal-rank fusion, so the
        cross-encoder is never invoked; the placeholder only satisfies the
        constructor.
        """

        async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
            return []

    kuzu_path = Path(settings.graphiti_kuzu_path)
    kuzu_path.parent.mkdir(parents=True, exist_ok=True)

    driver = KuzuDriver(db=str(kuzu_path))
    # graphiti-core 0.29.3 upstream-bug shim: add_episode/search compare
    # group_id against driver._database and may call driver.clone(database=...)
    # (graphiti.py:1079,1307). Both attributes are Neo4j-only and missing on
    # the deprecated KuzuDriver. Kuzu is single-database and group_id is stored
    # as a data field on nodes/edges, so clone() safely returns the same driver.
    driver._database = "kuzu"  # noqa: SLF001 - upstream compat shim
    driver.clone = lambda database=None: driver  # type: ignore[attr-defined]
    llm_client = OpenAIGenericClient(
        config=LLMConfig(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
        ),
        # DeepSeek does not support native json_schema structured output, so
        # the schema is injected into the prompt instead (json_object mode).
        structured_output_mode="json_object",
    )
    graphiti = Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=_SentenceTransformerEmbedder(settings.graphiti_embedder_model),
        cross_encoder=_NoOpCrossEncoder(),
    )

    # KuzuDriver.build_indices_and_constraints() is a no-op, so create the bm25
    # fulltext indexes Graphiti.search() relies on via the driver's graph_ops.
    # The CREATE_FTS_INDEX statements are not idempotent in kuzu, so tolerate
    # "already exists" on re-initialization against an existing database.
    try:
        await graphiti.driver.graph_ops.build_indices_and_constraints(graphiti.driver)
    except RuntimeError as exc:
        if "already exists" not in str(exc):
            raise

    return graphiti, EpisodeType(_EPISODE_SOURCE), "kuzu"


class GraphitiBackend(MemoryBackend):
    """Graphiti-backed temporal knowledge-graph memory.

    All graphiti SDK calls are natively async, so the backend awaits them
    directly (no `asyncio.to_thread`). Construction is lazy: with no injected
    client, the real graphiti client is built from the settings on first use.
    """

    def __init__(self, settings: Settings, graphiti_client: Any = None) -> None:
        self._settings = settings
        # Either an injected fake (tests) or the lazily-built real graphiti client.
        self._graphiti: Any = graphiti_client
        #: Episode source tag passed to add_episode: the "text" string for
        #: injected fakes, the resolved graphiti EpisodeType.text for the real
        #: client (set when the factory runs).
        self._episode_source: Any = _EPISODE_SOURCE
        #: Graph driver mode for stats(): "kuzu" (real), "fake" (injected), or
        #: "uninitialized" before the client is built.
        self._driver_mode = "fake" if graphiti_client is not None else "uninitialized"
        self._add_latency_s = 0.0
        self._add_calls = 0
        self._retrieve_latency_s = 0.0
        self._retrieve_calls = 0

    async def _ensure_client(self) -> Any:
        """Build the real graphiti client on first use if none was injected."""

        if self._graphiti is None:
            self._graphiti, self._episode_source, self._driver_mode = (
                await _build_graphiti_client(self._settings)
            )
        return self._graphiti

    async def _add_episode(self, client: Any, event: ExperienceEvent) -> None:
        """Distill one event into a new episode of the event's graph partition.

        Graphiti's extraction LLM is invoked here in live mode — that is the
        framework doing its job; the rendered event text is passed through
        faithfully (reusing `_render_text`).
        """

        await client.add_episode(
            name=event.event_id,
            episode_body=_render_text(event),
            source_description=_SOURCE_DESCRIPTION,
            reference_time=event.timestamp,
            source=self._episode_source,
            group_id=event.episode_id,
        )

    async def add(self, event: ExperienceEvent) -> None:
        """Distill a new experience event into the episode's graph partition."""

        start = time.perf_counter()
        try:
            client = await self._ensure_client()
            await self._add_episode(client, event)
        finally:
            self._add_calls += 1
            self._add_latency_s += time.perf_counter() - start

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        """Return the `query.limit` most relevant distilled facts, best first.

        `query.episode_id` narrows the search to that episode's `group_id`
        partition; without one the search spans every partition (the same
        semantics as the vector backend). `Graphiti.search()` returns plain
        fact edges with no score, so `MemoryItem.score` is `None` unless the
        client returns one.
        """

        start = time.perf_counter()
        try:
            client = await self._ensure_client()
            edges = await client.search(
                query.query_text,
                group_ids=[query.episode_id] if query.episode_id else None,
                num_results=query.limit,
            )
            return [self._to_memory_item(edge) for edge in (edges or [])]
        finally:
            self._retrieve_calls += 1
            self._retrieve_latency_s += time.perf_counter() - start

    def _to_memory_item(self, edge: Any) -> MemoryItem:
        """Map one graphiti fact edge to a MemoryItem.

        Graphiti returns *distilled facts*, not the raw recorded event, so the
        reconstructed ExperienceEvent is minimal: the fact text is stashed in
        `context["text"]` alongside the edge's `name`/`valid_at`/`invalid_at`,
        and the type is the neutral WORLD_FACT_UPDATED. `score` is passed
        through when the client returns one and left `None` otherwise (the
        `Graphiti.search()` path returns no score) — never invented.
        """

        fact = _get(edge, "fact") or ""
        name = _get(edge, "name") or ""
        valid_at = _parse_dt(_get(edge, "valid_at"))
        invalid_at = _parse_dt(_get(edge, "invalid_at"))
        created_at = _parse_dt(_get(edge, "created_at")) or datetime.now(UTC)

        context: dict[str, Any] = {"text": fact}
        if name:
            context["name"] = name
        if valid_at is not None:
            context["valid_at"] = valid_at.isoformat()
        if invalid_at is not None:
            context["invalid_at"] = invalid_at.isoformat()

        metadata = {
            key: value
            for key, value in {
                "source_node_uuid": _get(edge, "source_node_uuid"),
                "target_node_uuid": _get(edge, "target_node_uuid"),
                "group_id": _get(edge, "group_id"),
            }.items()
            if isinstance(value, str) and value
        }

        edge_id = _get(edge, "uuid") or fact or str(created_at)
        event = ExperienceEvent(
            event_id=edge_id,
            episode_id=_get(edge, "group_id") or "",
            timestamp=created_at,
            actor="graphiti",
            event_type=EventType.WORLD_FACT_UPDATED,
            context=context,
        )
        return MemoryItem(
            item_id=edge_id,
            event=event,
            score=_get(edge, "score"),
            created_at=created_at,
            metadata=metadata,
        )

    async def update(self, event: ExperienceEvent) -> None:
        """Supersede the stored fact with the updated one (belief updates).

        Graphiti has no in-place fact update: a fact is superseded by adding a
        new episode that states the updated information — graphiti's extraction
        resolves the new statement against the existing edges and *invalidates*
        the stale ones (setting `invalid_at`/`expired_at`). That temporal
        invalidation IS graphiti's update semantics, so `update()` re-adds the
        event as a new episode in the same group partition.
        """

        client = await self._ensure_client()
        await self._add_episode(client, event)

    async def reset(self, episode_id: str) -> None:
        """Remove every episode in the episode's `group_id` partition.

        Graphiti exposes no "delete group" API; the closest public path is
        `retrieve_episodes(group_ids=[episode_id])` followed by
        `remove_episode(uuid)` per episode. `remove_episode` deletes the
        episode's own distilled facts and the entities only it mentions,
        preserving facts that later episodes corroborated.
        """

        client = await self._ensure_client()
        episodes = await client.retrieve_episodes(
            reference_time=datetime.now(UTC),
            last_n=_COUNT_LIMIT,
            group_ids=[episode_id],
        )
        for episode in episodes or []:
            await client.remove_episode(_get(episode, "uuid"))

    async def stats(self) -> MemoryStats:
        client = await self._ensure_client()
        count = 0
        try:
            count = await self._count_facts(client)
        except Exception as exc:  # noqa: BLE001 — stats must never crash the run
            logger.warning(
                "graphiti stats: counting facts failed, reporting item_count=0: %s",
                exc,
            )
        return MemoryStats(
            backend="graphiti",
            item_count=count,
            extra={
                "avg_add_latency_ms": self._avg_ms(self._add_latency_s, self._add_calls),
                "avg_retrieve_latency_ms": self._avg_ms(
                    self._retrieve_latency_s, self._retrieve_calls
                ),
                "graphiti_version": _graphiti_version(),
                "driver_mode": self._driver_mode,
                "item_count_scope": "distilled facts (entity edges), counted "
                "live from the graph via the driver",
            },
        )

    async def _count_facts(self, client: Any) -> int:
        """Best-effort live count of distilled facts.

        The Graphiti class exposes no count method, so the count is read from
        the graph driver: in the Kuzu schema every entity edge is a
        `RelatesToNode_` node, and counting those nodes returns the number of
        distilled facts currently in the store. It is not a count of added
        events — one event distills into several facts.
        """

        driver = _get(client, "driver")
        records, _, _ = await _get(driver, "execute_query")(_COUNT_FACTS_CYPHER)
        return records[0]["c"] if records else 0

    @staticmethod
    def _avg_ms(total_s: float, calls: int) -> float | None:
        """Average latency in ms over `calls` samples; None when unmeasured."""

        return round(total_s / calls * 1000.0, 3) if calls else None
