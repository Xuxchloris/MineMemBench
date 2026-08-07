"""Shared pytest helpers: JSON fixtures mirroring docs/protocol.md examples,
plus hermetic fakes (no network, no real LLM API) for the M4 agent layer."""

from __future__ import annotations

import json
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from minemembench.agent.llm_provider import LLMProvider, LLMResponse
from minemembench.core.config import Settings
from minemembench.core.models import BotMode, Position, WorldState

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Load a JSON fixture by file name (e.g. 'world_state.json')."""

    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture()
def world_state_payload() -> Any:
    return load_fixture("world_state.json")


@pytest.fixture()
def health_payload() -> Any:
    return load_fixture("health.json")


@pytest.fixture()
def action_result_payload() -> Any:
    return load_fixture("action_result.json")


@pytest.fixture()
def raw_event_payload() -> Any:
    return load_fixture("raw_event.json")


@pytest.fixture()
def experience_event_payload() -> Any:
    return load_fixture("experience_event.json")


def make_settings(**overrides: Any) -> Settings:
    """Hermetic settings: .env and process env are bypassed for LLM fields."""

    values: dict[str, Any] = {
        "llm_base_url": "https://llm.test/v1",
        "llm_api_key": "test-key",
        "llm_model": "deepseek-v4-flash",
        "llm_temperature": 0.0,
        "bot_url": "http://bridge.test",
        "results_dir": "results",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_world_state(x: float = 0.0, y: float = 64.0, z: float = 0.0) -> WorldState:
    """A minimal valid WorldState at the given position."""

    return WorldState(
        timestamp=datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC),
        mode=BotMode.MOCK,
        username="BenchBot",
        health=20.0,
        food=20,
        saturation=5.0,
        oxygen=20,
        position=Position(x=x, y=y, z=z),
        yaw=0.0,
        pitch=0.0,
        dimension="minecraft:overworld",
        time_of_day=6000,
        is_raining=False,
        experience_level=0,
    )


class FakeLLM(LLMProvider):
    """Scripted LLM: pops one prepared output per chat call.

    An output is either the response content string or an Exception to raise.
    """

    def __init__(self, outputs: list[str | Exception]) -> None:
        self._outputs: deque[str | Exception] = deque(outputs)
        self.calls: list[list[dict[str, str]]] = []

    @property
    def model(self) -> str:
        return "fake-model"

    @property
    def temperature(self) -> float:
        return 0.0

    async def chat(
        self, messages: list[dict[str, str]], *, max_tokens: int = 2048
    ) -> LLMResponse:
        self.calls.append(list(messages))
        output = self._outputs.popleft()
        if isinstance(output, Exception):
            raise output
        return LLMResponse(
            content=output,
            prompt_tokens=10,
            completion_tokens=5,
            latency_s=0.01,
            model=self.model,
        )
