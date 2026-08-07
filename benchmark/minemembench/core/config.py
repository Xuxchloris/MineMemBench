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
