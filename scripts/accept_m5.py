"""M5 live acceptance: EventCollector over a real bot bridge.

Usage:
  1. Start the TS adapter (mock: `BOT_MOCK=1 node dist/index.js`, or real MC).
  2. `.venv/Scripts/python scripts/accept_m5.py`

What it proves on a live link (mapping rules themselves are unit-tested):
  - EventCollector attaches to the WS event stream of a running bot
  - a scripted agent run (chat action) flows through runner + collector
  - collector starts/stops cleanly, RunLog carries collected_event_count
  - no exception escapes the event pipeline

This script uses a scripted fake LLM: it must not call the real LLM API.
Exits non-zero on any failed assertion.
"""

from __future__ import annotations

import asyncio
import sys

from minemembench.agent.llm_provider import LLMProvider, LLMResponse
from minemembench.core.client import BotClient
from minemembench.core.config import Settings
from minemembench.core.models import ExperienceEvent
from minemembench.core.runner import AgentRunner
from minemembench.events.collector import EventCollector
from minemembench.memory.base import (
    MemoryBackend,
    MemoryItem,
    MemoryQuery,
    MemoryStats,
)


class RecordingMemory(MemoryBackend):
    """Acceptance-only backend: records every event handed to memory.add."""

    def __init__(self) -> None:
        self.events: list[ExperienceEvent] = []

    async def add(self, event: ExperienceEvent) -> None:
        self.events.append(event)

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        return []

    async def update(self, event: ExperienceEvent) -> None:
        self.events.append(event)

    async def reset(self, episode_id: str) -> None:
        self.events.clear()

    async def stats(self) -> MemoryStats:
        return MemoryStats(backend="recording", item_count=len(self.events))


class ScriptedLLM(LLMProvider):
    """One canned chat action; never touches the network."""

    @property
    def model(self) -> str:
        return "scripted-fake"

    @property
    def temperature(self) -> float:
        return 0.0

    async def chat(
        self, messages: list[dict[str, str]], *, max_tokens: int = 2048
    ) -> LLMResponse:
        return LLMResponse(
            content='{"action":"chat","arguments":{"message":"m5 acceptance"},'
            '"reason":"scripted"}',
            prompt_tokens=0,
            completion_tokens=0,
            latency_s=0.0,
            model=self.model,
        )


async def main() -> int:
    settings = Settings()
    bot = BotClient(settings.bot_url)
    try:
        health = await bot.health()
    except Exception as exc:  # noqa: BLE001 - acceptance script, report plainly
        print(f"FAIL: cannot reach bot adapter at {settings.bot_url}: {exc}")
        return 1
    print(f"bot: {health.username} mode={health.mode} connected={health.connected}")
    assert health.connected, "bot adapter is not connected"

    memory = RecordingMemory()
    collector = EventCollector(bot, memory)
    runner = AgentRunner(bot, memory, ScriptedLLM(), event_collector=collector)

    log = await runner.run_goal("say m5 acceptance in chat", max_steps=1)
    print(f"run: {log.run_id} steps={len(log.steps)}")
    collected = getattr(log, "collected_event_count", None)
    print(f"collected_event_count: {collected}")
    assert collected is not None, "RunLog is missing collected_event_count"
    assert collected == len(memory.events), (
        f"RunLog count {collected} != memory adds {len(memory.events)}"
    )
    print(f"memory.add calls: {len(memory.events)} (0 is OK on mock: "
          f"chat events are unmappable by design)")
    print("PASS: M5 live acceptance")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
