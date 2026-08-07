"""Planner tests with a scripted FakeLLM — no network, no real API."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from minemembench.agent.planner import (
    ActionName,
    Planner,
    PlannerError,
    TranscriptEntry,
)
from minemembench.core.client import BotClient
from minemembench.core.models import (
    ActionStatus,
    EventType,
    ExperienceEvent,
    Position,
)
from minemembench.memory.base import (
    MemoryBackend,
    MemoryItem,
    MemoryQuery,
    MemoryStats,
)
from minemembench.memory.no_memory import NoMemoryBackend

from .conftest import FakeLLM, make_world_state

VALID_CHAT = '{"action":"chat","arguments":{"message":"hi"},"reason":"greet Steve"}'


class StubMemory(MemoryBackend):
    """Returns a fixed set of memories and records the queries it got."""

    def __init__(self, items: list[MemoryItem]) -> None:
        self._items = items
        self.queries: list[MemoryQuery] = []

    async def add(self, event: ExperienceEvent) -> None:
        raise NotImplementedError

    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]:
        self.queries.append(query)
        return self._items

    async def update(self, event: ExperienceEvent) -> None:
        raise NotImplementedError

    async def reset(self, episode_id: str) -> None:
        raise NotImplementedError

    async def stats(self) -> MemoryStats:
        return MemoryStats(backend="stub", item_count=len(self._items))


def _memory_item() -> MemoryItem:
    return MemoryItem(
        item_id="m1",
        event=ExperienceEvent(
            event_id="m1",
            episode_id="ep-1",
            timestamp=datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC),
            actor="agent",
            event_type=EventType.TASK_SUCCEEDED,
            context={"task": "collect stone"},
            outcome="collected 12 stone",
        ),
        score=0.9,
        created_at=datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC),
    )


def _dummy_bot_client() -> BotClient:
    """A BotClient the planner will never call (state is passed in)."""

    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    client = httpx.AsyncClient(transport=transport, base_url="http://unused.test")
    return BotClient("http://unused.test", client=client)


def _make_planner(
    llm: FakeLLM, memory: MemoryBackend | None = None, max_retries: int = 2
) -> Planner:
    return Planner(
        _dummy_bot_client(),
        memory if memory is not None else NoMemoryBackend(),
        llm,
        max_retries=max_retries,
    )


async def test_decide_happy_path_includes_memories_in_prompt() -> None:
    llm = FakeLLM([VALID_CHAT])
    memory = StubMemory([_memory_item()])
    planner = _make_planner(llm, memory)

    decision = await planner.decide("greet Steve", make_world_state())

    assert decision.action.action is ActionName.CHAT
    assert decision.action.arguments == {"message": "hi"}
    assert decision.action.reason == "greet Steve"
    assert decision.retries == 0
    assert len(decision.retrieved_memories) == 1
    assert decision.llm.content == VALID_CHAT

    # The retrieval query carries the goal text.
    assert memory.queries[0].query_text == "greet Steve"

    # User message: labeled text sections with embedded JSON payloads.
    user_message = llm.calls[0][1]["content"]
    assert "Goal: greet Steve" in user_message
    assert '"x": 0.0' in user_message  # world-state JSON is embedded
    assert "Recent actions this episode" in user_message
    assert "Retrieved long-term memories" in user_message
    assert "m1" in user_message  # the retrieved memory is serialized in

    # System prompt documents the protocol actions.
    system_message = llm.calls[0][0]["content"]
    assert "move_to" in system_message and "give_item" in system_message


async def test_decide_scopes_retrieval_to_episode() -> None:
    llm = FakeLLM([VALID_CHAT])
    memory = StubMemory([_memory_item()])
    planner = _make_planner(llm, memory)

    await planner.decide("greet Steve", make_world_state(), episode_id="ep-42")

    assert memory.queries[0].episode_id == "ep-42"


async def test_decide_defaults_to_no_episode_filter() -> None:
    llm = FakeLLM([VALID_CHAT])
    memory = StubMemory([_memory_item()])
    planner = _make_planner(llm, memory)

    await planner.decide("greet Steve", make_world_state())

    assert memory.queries[0].episode_id is None


async def test_prose_wrapped_json_is_tolerated() -> None:
    llm = FakeLLM(
        ['Sure! {"action":"wait","arguments":{"seconds":1},"reason":"pause"} — done!']
    )
    planner = _make_planner(llm)

    decision = await planner.decide("wait a moment", make_world_state())

    assert decision.action.action is ActionName.WAIT
    assert decision.action.arguments == {"seconds": 1}
    assert decision.retries == 0


async def test_invalid_json_is_retried_then_valid() -> None:
    llm = FakeLLM(["this is not json", VALID_CHAT])
    planner = _make_planner(llm)

    decision = await planner.decide("greet Steve", make_world_state())

    assert decision.retries == 1
    assert decision.action.action is ActionName.CHAT

    # The retry conversation fed the error back to the model.
    retry_messages = llm.calls[1]
    assert len(retry_messages) == 4  # system, user, assistant, user(feedback)
    assert retry_messages[2]["content"] == "this is not json"
    assert "invalid" in retry_messages[3]["content"].lower()


async def test_schema_validation_failure_is_retried() -> None:
    bad_action = '{"action":"fly","arguments":{},"reason":"I want wings"}'
    llm = FakeLLM([bad_action, VALID_CHAT])
    planner = _make_planner(llm)

    decision = await planner.decide("greet Steve", make_world_state())

    assert decision.retries == 1
    assert decision.action.action is ActionName.CHAT


async def test_exhausted_retries_raise_planner_error() -> None:
    llm = FakeLLM(["junk one", "junk two", "junk three"])
    planner = _make_planner(llm, max_retries=2)

    with pytest.raises(PlannerError, match="3 attempts"):
        await planner.decide("greet Steve", make_world_state())

    assert len(llm.calls) == 3  # initial + 2 retries


async def test_user_message_has_empty_memories_with_none_backend() -> None:
    llm = FakeLLM([VALID_CHAT])
    planner = _make_planner(llm, NoMemoryBackend())

    decision = await planner.decide("greet Steve", make_world_state())

    assert decision.retrieved_memories == []
    user_message = llm.calls[0][1]["content"]
    assert "Retrieved long-term memories (JSON):\n[]" in user_message


async def test_episode_transcript_is_included_in_prompt() -> None:
    llm = FakeLLM([VALID_CHAT])
    planner = _make_planner(llm)
    history = [
        TranscriptEntry(
            index=0,
            action="chat",
            arguments={"message": "hi"},
            reason="greet",
            status=ActionStatus.COMPLETED,
            position_after=Position(x=1.0, y=64.0, z=2.0),
        )
    ]

    await planner.decide("now move somewhere", make_world_state(), history)

    user_message = llm.calls[0][1]["content"]
    assert "Recent actions this episode" in user_message
    assert '"greet"' in user_message  # transcript entry is serialized in
