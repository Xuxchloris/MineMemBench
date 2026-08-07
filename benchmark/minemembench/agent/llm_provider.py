"""LLM provider abstraction + an OpenAI-compatible implementation.

Verified quirk of the target deployment (DeepSeek reasoning models): the
response carries a `reasoning_content` field alongside `content`, and a low
`max_tokens` is entirely consumed by reasoning, leaving `content` EMPTY with
`finish_reason == "length"`. Hence the generous default of 2048 tokens, and
only `content` is ever read — `reasoning_content` is ignored on purpose.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ..core.config import Settings

#: Generous default: reasoning models burn tokens before producing content.
DEFAULT_MAX_TOKENS = 2048

#: Reasoning models can think for a long while before answering.
DEFAULT_TIMEOUT_S = 120.0


class LLMError(Exception):
    """Raised on HTTP errors, empty content, or truncated (length) replies."""


class LLMResponse(BaseModel):
    """One completed chat call, with cost accounting."""

    model_config = ConfigDict(frozen=True)

    content: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    latency_s: float = Field(ge=0.0)
    model: str


class LLMProvider(ABC):
    """Minimal chat interface; the planner depends only on this."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Configured model name (for run logging)."""

    @property
    @abstractmethod
    def temperature(self) -> float:
        """Configured sampling temperature (for run logging)."""

    @abstractmethod
    async def chat(
        self, messages: list[dict[str, str]], *, max_tokens: int = DEFAULT_MAX_TOKENS
    ) -> LLMResponse:
        """Complete a chat conversation and return content + usage."""


class OpenAICompatibleProvider(LLMProvider):
    """POSTs {base}/chat/completions against any OpenAI-compatible endpoint.

    `trust_env=False`: a system-level HTTP proxy must not intercept API
    calls (httpx would otherwise pick up Windows registry proxy settings).
    Inject a custom `http_client` (e.g. MockTransport) to override behavior.
    """

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._owns_client = http_client is None
        if http_client is not None:
            self._client = http_client
        else:
            # Trailing slash matters: httpx joins relative paths against it,
            # keeping the /v1 prefix of typical base URLs.
            base_url = settings.llm_base_url.rstrip("/") + "/"
            self._client = httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(DEFAULT_TIMEOUT_S),
                trust_env=False,
            )

    @property
    def model(self) -> str:
        return self._settings.llm_model

    @property
    def temperature(self) -> float:
        return self._settings.llm_temperature

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def chat(
        self, messages: list[dict[str, str]], *, max_tokens: int = DEFAULT_MAX_TOKENS
    ) -> LLMResponse:
        settings = self._settings
        payload: dict[str, Any] = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": settings.llm_temperature,
            "max_tokens": max_tokens,
        }
        if settings.llm_thinking is not None:
            # Verified on DeepSeek: disables the reasoning trace, making runs
            # deterministic and ~4x cheaper in prompt tokens.
            payload["thinking"] = {"type": settings.llm_thinking}
        headers = (
            {"Authorization": f"Bearer {settings.llm_api_key}"}
            if settings.llm_api_key
            else {}
        )

        started = time.perf_counter()
        try:
            response = await self._client.post(
                "chat/completions", json=payload, headers=headers
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        latency_s = time.perf_counter() - started

        if response.status_code != 200:
            raise LLMError(
                f"LLM endpoint returned HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

        data: Any = response.json()
        try:
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"malformed LLM response: {data!r:.500}") from exc

        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            raise LLMError(
                "LLM reply truncated (finish_reason='length'); with reasoning "
                "models this usually means max_tokens was consumed by "
                "reasoning — increase max_tokens."
            )

        # Only `content` is used. `reasoning_content` is deliberately ignored.
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMError("LLM returned empty content.")

        usage = data.get("usage") or {}
        return LLMResponse(
            content=content,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_s=latency_s,
            model=str(data.get("model", settings.llm_model)),
        )
