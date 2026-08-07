"""Async client for the bot bridge (docs/protocol.md).

HTTP JSON for request/response (health, state, actions) plus a WebSocket
async generator for the raw event stream. Responses are validated into the
pydantic models from `core.models`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import websockets

from .models import (
    ActionRequest,
    ActionResult,
    EventEnvelope,
    HealthResponse,
    RawGameEvent,
    WorldState,
)

#: Default per-request HTTP timeout in seconds.
DEFAULT_HTTP_TIMEOUT_S = 10.0


class BotBridgeError(Exception):
    """Base error for bot-bridge failures."""


class BotNotConnectedError(BotBridgeError):
    """HTTP 503 — the bot is not connected to a Minecraft server."""


class InvalidActionError(BotBridgeError):
    """HTTP 400 — the action request body was rejected by the server."""


def _extract_error_message(response: httpx.Response) -> str:
    """Pull a human-readable message out of an error response body."""

    try:
        body: Any = response.json()
    except json.JSONDecodeError:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, str):
            return error
    return f"HTTP {response.status_code}"


class BotClient:
    """Async client for one bot-adapter instance.

    Pass an existing `client` (e.g. backed by httpx.MockTransport) to inject
    a custom transport; otherwise one is created from `base_url`.

    The self-created client uses `trust_env=False`: the bridge is always a
    direct local/LAN connection, and a system-level HTTP proxy must not
    intercept it (httpx otherwise picks up Windows registry proxy settings).
    Inject a custom `client` if proxy support is ever needed.
    """

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = DEFAULT_HTTP_TIMEOUT_S,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout_s),
            trust_env=False,
        )

    async def __aenter__(self) -> BotClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client if this instance created it."""

        if self._owns_client:
            await self._client.aclose()

    def _raise_for_bridge_errors(self, response: httpx.Response) -> None:
        """Map protocol error statuses to typed exceptions."""

        if response.status_code == 400:
            raise InvalidActionError(_extract_error_message(response))
        if response.status_code == 503:
            raise BotNotConnectedError(_extract_error_message(response))
        response.raise_for_status()

    async def health(self) -> HealthResponse:
        """GET /health."""

        response = await self._client.get("/health")
        self._raise_for_bridge_errors(response)
        return HealthResponse.model_validate(response.json())

    async def get_state(self) -> WorldState:
        """GET /state."""

        response = await self._client.get("/state")
        self._raise_for_bridge_errors(response)
        return WorldState.model_validate(response.json())

    async def execute(
        self,
        action: str,
        arguments: dict[str, Any],
        timeout_ms: int = 30000,
    ) -> ActionResult:
        """POST /action.

        The server answers HTTP 200 even when the action failed; inspect
        `result.status` for the outcome. 400/503 raise typed errors.
        """

        request_body = ActionRequest(
            action=action, arguments=arguments, timeout_ms=timeout_ms
        )
        response = await self._client.post(
            "/action", json=request_body.model_dump(mode="json")
        )
        self._raise_for_bridge_errors(response)
        return ActionResult.model_validate(response.json())

    async def iter_events(self) -> AsyncIterator[RawGameEvent]:
        """Yield raw game events from the /events WebSocket, in order.

        The server's initial `hello` message is consumed silently; only
        `event` envelopes are yielded. Reconnects are the caller's concern.
        """

        url = httpx.URL(self._base_url)
        scheme = "wss" if url.scheme == "https" else "ws"
        ws_url = f"{scheme}://{url.host}"
        if url.port is not None:
            ws_url += f":{url.port}"
        ws_url += "/events"

        async with websockets.connect(ws_url) as ws:
            async for message in ws:
                envelope = json.loads(message)
                if not isinstance(envelope, dict):
                    continue
                if envelope.get("type") == "event":
                    yield EventEnvelope.model_validate(envelope).event
                # `hello` and unknown message types are ignored on purpose.
