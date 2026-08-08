"""Benchmark-core configuration, read from environment variables / .env file.

Field names map case-insensitively to the env vars documented in .env.example
(e.g. `bot_url` reads `BOT_URL`).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the benchmark core."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Minecraft bot adapter (HTTP + WebSocket bridge) ---
    bot_url: str = "http://localhost:8081"

    # --- LLM provider (OpenAI-compatible); defaults mirror .env.example ---
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    # Reasoning on/off switch for endpoints that support it (e.g. DeepSeek's
    # `thinking: {"type": "disabled"}`). None = omit the field entirely.
    llm_thinking: str | None = None

    # --- Output location for benchmark results ---
    results_dir: str = "results"

    # --- Pre-run fairness audit (M15B) ---
    # Controlled variables recorded into every run log so a run's comparability
    # can be audited from the log alone. Minecraft version defaults to "unknown"
    # (it is not exposed by the bridge protocol); set it in .env for real runs.
    minecraft_version: str = "unknown"
    world_seed: int | None = None

    # --- Mem0 backend ---
    # HF model name or local path for the mem0 embedder (a local path lets
    # acceptance runs work without HuggingFace access).
    mem0_embedder_model: str = "all-MiniLM-L6-v2"

    # --- Memory backends ---
    # SQLite file backing the `vector` memory backend (M6).
    vector_db_path: str = "results/memory_vector.db"
    # On-disk Qdrant directory backing the `mem0` memory backend (M8).
    # Mem0 runs Qdrant in local path mode here: no server, no network.
    mem0_qdrant_path: str = "results/mem0_qdrant"

    # --- Letta backend (M9) ---
    # Base URL of a Letta server: a self-hosted `letta/letta` container on
    # 8283, or the Letta Cloud endpoint. Empty means the letta-client SDK
    # falls back to its own defaults (see letta_client/_client.py). An API
    # key is read by the SDK from the `LETTA_API_KEY` env var when present.
    letta_base_url: str = "http://localhost:8283"

    # --- Graphiti backend (M10) ---
    # On-disk directory backing the embedded Kuzu graph (`graphiti` backend).
    # Kuzu runs in embedded no-server mode here: no network to a graph server.
    graphiti_kuzu_path: str = "results/graphiti_kuzu"
    # HF model name or local path for the graphiti embedder. Graphiti wraps it
    # with sentence-transformers (a local path lets acceptance runs work without
    # HuggingFace access).
    graphiti_embedder_model: str = "all-MiniLM-L6-v2"
