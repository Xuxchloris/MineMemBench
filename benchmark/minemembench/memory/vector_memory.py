"""The `vector` memory backend: SQLite + pure-Python hashed embeddings.

A zero-dependency baseline (stdlib `sqlite3` only) that persists every
ExperienceEvent verbatim and retrieves the events whose rendered text is most
cosine-similar to the query. It is the M6 "vector" control condition: no
external vector DB, no numpy/FAISS, no network. `update()` overwrites the row
with the same `event_id`, so a corrected belief replaces the stale one rather
than being appended.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from ..core.models import ExperienceEvent
from .base import MemoryBackend, MemoryItem, MemoryQuery, MemoryStats
from .embeddings import Embedder, HashEmbedder, cosine_similarity

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    episode_id   TEXT NOT NULL,
    event_id     TEXT PRIMARY KEY,
    text         TEXT NOT NULL,
    vector_json  TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at   TEXT NOT NULL
)
"""

_UPSERT_SQL = """
INSERT INTO memories
    (episode_id, event_id, text, vector_json, payload_json, created_at)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(event_id) DO UPDATE SET
    episode_id    = excluded.episode_id,
    text          = excluded.text,
    vector_json   = excluded.vector_json,
    payload_json  = excluded.payload_json
"""

_SELECT_COLUMNS = "event_id, vector_json, payload_json, created_at"


def _render_text(event: ExperienceEvent) -> str:
    """A compact, searchable rendering of one experience event.

    `event_type + actor + target`, then the context key/value fields and the
    outcome string, space-joined. This is what gets embedded, so retrieval is
    grounded in the interaction facts the event layer recorded.
    """

    parts = [event.event_type.value, event.actor]
    if event.target is not None:
        parts.append(event.target)
    if event.context:
        parts.append(
            " ".join(f"{key}={value}" for key, value in sorted(event.context.items()))
        )
    if event.outcome is not None:
        parts.append(event.outcome)
    return " ".join(parts)


class VectorMemoryBackend(MemoryBackend):
    """SQLite-backed cosine-similarity memory with pure-Python vectors."""

    def __init__(self, db_path: str, embedder: Embedder | None = None) -> None:
        self._db_path = db_path
        self._embedder: Embedder = embedder or HashEmbedder()
        self._conn: sqlite3.Connection | None = None
        self._add_latency_s = 0.0
        self._add_calls = 0
        self._retrieve_latency_s = 0.0
        self._retrieve_calls = 0

    def _connect(self) -> sqlite3.Connection:
        """Open the SQLite file lazily; the table is created on first use."""
        if self._conn is None:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            conn.execute(_SCHEMA)
            conn.commit()
            self._conn = conn
        return self._conn

    def _upsert(self, event: ExperienceEvent) -> None:
        """Render, embed, and write one row, keeping `created_at` on conflict."""
        rendered = _render_text(event)
        vector = self._embedder.embed(rendered)
        conn = self._connect()
        conn.execute(
            _UPSERT_SQL,
            (
                event.episode_id,
                event.event_id,
                rendered,
                json.dumps(vector),
                event.model_dump_json(),
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()

    async def add(self, event: ExperienceEvent) -> None:
        """Store a new experience event (upsert by `event_id`)."""
        start = time.perf_counter()
        try:
            self._upsert(event)
        finally:
            self._add_calls += 1
            self._add_latency_s += time.perf_counter() - start

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        """Return the `query.limit` most cosine-similar events, best first.

        Rows are filtered by `query.episode_id` (None = every episode). Score
        is the raw cosine similarity; rows with zero overlap (score <= 0.0)
        are dropped, so unrelated memories never crowd out the relevant ones.
        `query.filters` is not supported by this backend.
        """

        start = time.perf_counter()
        try:
            query_vector = self._embedder.embed(query.query_text)
            conn = self._connect()
            if query.episode_id is None:
                rows = conn.execute(
                    f"SELECT {_SELECT_COLUMNS} FROM memories"
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT {_SELECT_COLUMNS} FROM memories WHERE episode_id = ?",
                    (query.episode_id,),
                ).fetchall()
            scored = [
                (cosine_similarity(query_vector, json.loads(row["vector_json"])), row)
                for row in rows
            ]
            scored = [pair for pair in scored if pair[0] > 0.0]
            scored.sort(key=lambda pair: pair[0], reverse=True)
            return [
                MemoryItem(
                    item_id=row["event_id"],
                    event=ExperienceEvent.model_validate(json.loads(row["payload_json"])),
                    score=score,
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for score, row in scored[: query.limit]
            ]
        finally:
            self._retrieve_calls += 1
            self._retrieve_latency_s += time.perf_counter() - start

    async def update(self, event: ExperienceEvent) -> None:
        """Re-render and re-embed the row with the same `event_id` (upsert)."""
        self._upsert(event)

    async def reset(self, episode_id: str) -> None:
        """Drop all memories belonging to one episode."""
        conn = self._connect()
        conn.execute("DELETE FROM memories WHERE episode_id = ?", (episode_id,))
        conn.commit()

    async def stats(self) -> MemoryStats:
        """Report backend name, item count, and backend-specific extras."""
        conn = self._connect()
        count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        return MemoryStats(
            backend="vector",
            item_count=count,
            extra={
                "db_path": self._db_path,
                "embedder": self._embedder.name,
                "avg_add_latency_ms": self._avg_ms(
                    self._add_latency_s, self._add_calls
                ),
                "avg_retrieve_latency_ms": self._avg_ms(
                    self._retrieve_latency_s, self._retrieve_calls
                ),
            },
        )

    @staticmethod
    def _avg_ms(total_s: float, calls: int) -> float | None:
        """Average latency in ms over `calls` samples; None when unmeasured."""
        return round(total_s / calls * 1000.0, 3) if calls else None
