"""OpenAICompatibleProvider tests via httpx.MockTransport — no network.

Covers the verified reasoning-model quirk: `reasoning_content` must be
ignored, and `finish_reason == "length"` / empty content raise LLMError.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from minemembench.agent.llm_provider import (
    LLMError,
    LLMProvider,
    OpenAICompatibleProvider,
)

from .conftest import make_settings


def _chat_payload(
    content: str | None,
    *,
    finish_reason: str = "stop",
    reasoning: str | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return {
        "id": "chatcmpl-test",
        "model": "deepseek-v4-flash",
        "choices": [
            {"index": 0, "message": message, "finish_reason": finish_reason}
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 34},
    }


def _make_provider(
    handler: Any,
    **setting_overrides: Any,
) -> tuple[OpenAICompatibleProvider, dict[str, Any]]:
    captured: dict[str, Any] = {}

    def recording_handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return handler(request)

    transport = httpx.MockTransport(recording_handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://llm.test/v1/")
    provider = OpenAICompatibleProvider(
        make_settings(**setting_overrides), http_client=client
    )
    return provider, captured


_MESSAGES = [{"role": "user", "content": "Say hi as JSON."}]


def test_provider_is_an_llm_provider() -> None:
    provider, _ = _make_provider(
        lambda request: httpx.Response(200, json=_chat_payload("{}"))
    )
    assert isinstance(provider, LLMProvider)
    assert provider.model == "deepseek-v4-flash"
    assert provider.temperature == 0.0


async def test_happy_path_ignores_reasoning_content() -> None:
    reasoning = "Let me think step by step about what JSON to emit..."
    provider, captured = _make_provider(
        lambda request: httpx.Response(
            200, json=_chat_payload('{"action":"wait"}', reasoning=reasoning)
        )
    )

    response = await provider.chat(_MESSAGES)

    assert response.content == '{"action":"wait"}'
    assert reasoning not in response.content
    assert response.prompt_tokens == 12
    assert response.completion_tokens == 34
    assert response.latency_s >= 0.0
    assert response.model == "deepseek-v4-flash"

    # Request shape: bearer auth, configured model/temperature, generous cap.
    assert captured["url"] == "https://llm.test/v1/chat/completions"
    assert captured["authorization"] == "Bearer test-key"
    assert captured["body"]["model"] == "deepseek-v4-flash"
    assert captured["body"]["temperature"] == 0.0
    assert captured["body"]["max_tokens"] == 2048
    assert captured["body"]["messages"] == _MESSAGES


async def test_empty_content_raises_llm_error() -> None:
    provider, _ = _make_provider(
        lambda request: httpx.Response(200, json=_chat_payload(""))
    )
    with pytest.raises(LLMError, match="empty content"):
        await provider.chat(_MESSAGES)


async def test_reasoning_only_length_reply_raises_llm_error() -> None:
    # The verified quirk: reasoning consumed all tokens, content is null.
    provider, _ = _make_provider(
        lambda request: httpx.Response(
            200,
            json=_chat_payload(
                None, finish_reason="length", reasoning="still thinking..."
            ),
        )
    )
    with pytest.raises(LLMError, match="length"):
        await provider.chat(_MESSAGES)


async def test_http_500_raises_llm_error() -> None:
    provider, _ = _make_provider(
        lambda request: httpx.Response(500, json={"error": "internal"})
    )
    with pytest.raises(LLMError, match="HTTP 500"):
        await provider.chat(_MESSAGES)


async def test_thinking_param_sent_when_configured() -> None:
    # Verified against DeepSeek: thinking disabled => deterministic, cheaper.
    provider, captured = _make_provider(
        lambda request: httpx.Response(200, json=_chat_payload("{}")),
        llm_thinking="disabled",
    )

    await provider.chat(_MESSAGES)

    assert captured["body"]["thinking"] == {"type": "disabled"}


async def test_thinking_param_omitted_by_default() -> None:
    provider, captured = _make_provider(
        lambda request: httpx.Response(200, json=_chat_payload("{}"))
    )

    await provider.chat(_MESSAGES)

    assert "thinking" not in captured["body"]
