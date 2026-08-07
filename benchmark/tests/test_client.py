"""BotClient tests against an in-memory httpx.MockTransport bridge."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from minemembench.core.client import (
    BotClient,
    BotNotConnectedError,
    InvalidActionError,
)
from minemembench.core.models import (
    ActionStatus,
    BotMode,
    WorldState,
)

from .conftest import load_fixture

BASE_URL = "http://bridge.test"


def _make_handler(mode: str = "happy"):
    """Build a MockTransport handler emulating the protocol endpoints."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if mode == "disconnected":
            # Bot not connected: protocol says 503 for state/action.
            if path in ("/state", "/action"):
                return httpx.Response(
                    503, json={"error": "bot is not connected to a server"}
                )
        if path == "/health":
            return httpx.Response(200, json=load_fixture("health.json"))
        if path == "/state":
            return httpx.Response(200, json=load_fixture("world_state.json"))
        if path == "/action":
            body: Any = json.loads(request.content)
            if body.get("action") == "invalid_action":
                return httpx.Response(
                    400, json={"error": "unknown action: 'invalid_action'"}
                )
            return httpx.Response(200, json=load_fixture("action_result.json"))
        return httpx.Response(404, json={"error": f"no such route: {path}"})

    return handler


def _make_client(mode: str = "happy") -> BotClient:
    transport = httpx.MockTransport(_make_handler(mode))
    http_client = httpx.AsyncClient(transport=transport, base_url=BASE_URL)
    return BotClient(BASE_URL, client=http_client)


async def test_health() -> None:
    async with _make_client() as client:
        health = await client.health()
    assert health.status == "ok"
    assert health.mode is BotMode.MOCK
    assert health.connected is True
    assert health.username == "BenchBot"
    assert health.uptime_s == 12.3


async def test_get_state() -> None:
    async with _make_client() as client:
        state = await client.get_state()
    assert isinstance(state, WorldState)
    assert state.username == "BenchBot"
    assert state.position.y == 64.0
    assert len(state.nearby_entities) == 1


async def test_execute_happy_path() -> None:
    async with _make_client() as client:
        result = await client.execute(
            "move_to", {"x": 10, "y": 64, "z": 10}, timeout_ms=15000
        )
    assert result.status is ActionStatus.COMPLETED
    assert result.action == "move_to"
    assert result.result is not None
    assert result.state_after is not None


async def test_execute_sends_request_body() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=load_fixture("action_result.json"))

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url=BASE_URL)
    async with BotClient(BASE_URL, client=http_client) as client:
        await client.execute("chat", {"message": "hi"})

    assert captured == {
        "action": "chat",
        "arguments": {"message": "hi"},
        "timeout_ms": 30000,
    }


async def test_execute_400_raises_invalid_action() -> None:
    async with _make_client() as client:
        with pytest.raises(InvalidActionError, match="unknown action"):
            await client.execute("invalid_action", {})


async def test_execute_503_raises_not_connected() -> None:
    async with _make_client(mode="disconnected") as client:
        with pytest.raises(BotNotConnectedError, match="not connected"):
            await client.execute("chat", {"message": "hi"})


async def test_get_state_503_raises_not_connected() -> None:
    async with _make_client(mode="disconnected") as client:
        with pytest.raises(BotNotConnectedError, match="not connected"):
            await client.get_state()
