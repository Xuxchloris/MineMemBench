"""The LLM planner: goal + state + working transcript + memories -> one action.

Methodology (benchmark-critical): the planner input contains the current
episode's recent action transcript as short-term WORKING context. This is
identical for every memory backend. The pluggable MemoryBackend only
contributes *long-term* retrieved memories on top, as a separate prompt
section. Controlled variables are preserved: the only independent variable
across runs is the injected backend.

Output contract is a single JSON object validated as `PlannerAction`.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..core.client import BotClient
from ..core.models import ActionStatus, Position, WorldState
from ..memory.base import MemoryBackend, MemoryItem, MemoryQuery
from .llm_provider import LLMProvider, LLMResponse

#: Only the most recent N transcript entries are included in the prompt.
MAX_TRANSCRIPT_ENTRIES = 20

#: The 8 high-level actions of docs/protocol.md, mirrored in the prompt.
_ACTION_SPECS = """\
- move_to: {"x": number, "y": number, "z": number} — pathfind to within 1 block of the target
- follow_player: {"username": string, "distance"?: number (default 2)} — move near a visible player once
- attack_entity: {"name"?: string, "entity_id"?: integer} — one of the two is required
- collect_item: {"name": string, "max_distance"?: number (default 16)} — pick up a dropped item
- give_item: {"username": string, "item": string, "count"?: integer (default 1)} — toss items from own inventory
- equip_item: {"item": string, "destination"?: "hand" (default "hand")}
- wait: {"seconds": number} — 0.1 to 60
- chat: {"message": string} — public chat, max 256 characters"""

SYSTEM_PROMPT = f"""\
You are the planner for an embodied Minecraft agent. You receive a goal, the
current world state, a transcript of recent actions taken this episode, and
memories retrieved from the agent's long-term memory. Decide the single next
high-level action.

Respond with ONLY one JSON object — no prose, no markdown fences:
{{"action": "<action name>", "arguments": {{...}}, "reason": "<one sentence>"}}

Available actions and their argument schemas:
{_ACTION_SPECS}

Rules:
- High-level actions only; never attempt keyboard-level control.
- Exactly one action per reply; arguments must match the schemas above.
- Check the recent-actions transcript: do not repeat an action that has
  already accomplished its purpose.
- If memories contradict the current world state, trust the world state.
"""

#: SHA-256 of the system prompt, recorded by the pre-run fairness audit so a
#: run's exact planner instruction set can be verified from its log alone.
SYSTEM_PROMPT_HASH = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()

#: SHA-256 of the action/tool specification (`_ACTION_SPECS`), recorded by the
#: fairness audit so a run's tool set can be verified from its log alone.
TOOL_SET_HASH = hashlib.sha256(_ACTION_SPECS.encode("utf-8")).hexdigest()


class PlannerError(Exception):
    """Raised when the LLM fails to produce a valid action after retries."""


class ActionName(str, Enum):
    """The 8 protocol actions the planner may choose from."""

    MOVE_TO = "move_to"
    FOLLOW_PLAYER = "follow_player"
    ATTACK_ENTITY = "attack_entity"
    COLLECT_ITEM = "collect_item"
    GIVE_ITEM = "give_item"
    EQUIP_ITEM = "equip_item"
    WAIT = "wait"
    CHAT = "chat"


class PlannerAction(BaseModel):
    """The planner's structured output, parsed from the LLM's JSON reply."""

    model_config = ConfigDict(validate_assignment=True)

    action: ActionName
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str


class TranscriptEntry(BaseModel):
    """One executed action from the current episode's working transcript.

    This is short-term context maintained by the runner — it exists for every
    backend, including `none`, and is NOT part of the pluggable memory layer.
    """

    model_config = ConfigDict(validate_assignment=True)

    index: int = Field(ge=0)
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str
    status: ActionStatus
    position_after: Position


class PlannedDecision(BaseModel):
    """A validated action plus the full context that produced it."""

    model_config = ConfigDict(validate_assignment=True)

    action: PlannerAction
    retrieved_memories: list[MemoryItem]
    llm: LLMResponse
    retries: int = Field(ge=0)


def _extract_first_json_object(text: str) -> Any:
    """Parse the first complete JSON object starting at the first '{'.

    Tolerates leading prose and trailing garbage; raises ValueError when no
    complete object can be decoded.
    """

    start = text.find("{")
    if start == -1:
        raise ValueError("no '{' found in LLM output")
    obj, _end = json.JSONDecoder().raw_decode(text[start:])
    return obj


class Planner:
    """Turns (goal, world state, transcript, memories) into one action.

    `bot_client` is accepted for interface stability (future planners may
    issue probes); the current implementation only uses the passed-in state.
    """

    def __init__(
        self,
        bot_client: BotClient,
        memory: MemoryBackend,
        llm: LLMProvider,
        max_retries: int = 2,
    ) -> None:
        self._bot_client = bot_client
        self._memory = memory
        self._llm = llm
        self._max_retries = max_retries

    def _build_user_message(
        self,
        goal: str,
        state: WorldState,
        memories: list[MemoryItem],
        history: list[TranscriptEntry],
    ) -> str:
        """Labeled prompt sections: working transcript vs. long-term memories."""

        recent = history[-MAX_TRANSCRIPT_ENTRIES:]
        state_json = json.dumps(state.model_dump(mode="json"))
        transcript_json = json.dumps(
            [entry.model_dump(mode="json") for entry in recent]
        )
        memories_json = json.dumps(
            [item.model_dump(mode="json") for item in memories]
        )
        return (
            f"Goal: {goal}\n\n"
            f"Current world state (JSON):\n{state_json}\n\n"
            f"Recent actions this episode (JSON, most recent last):\n"
            f"{transcript_json}\n\n"
            f"Retrieved long-term memories (JSON):\n{memories_json}"
        )

    async def decide(
        self,
        goal: str,
        state: WorldState,
        history: list[TranscriptEntry] | None = None,
        *,
        episode_id: str | None = None,
    ) -> PlannedDecision:
        """Decide the next action.

        `history` is the episode transcript so far (most recent last); only
        the last MAX_TRANSCRIPT_ENTRIES entries reach the prompt. The list is
        never mutated. None means "no actions yet this episode".
        `episode_id` scopes retrieval to one run so runs sharing a backend
        never leak memories into each other; None retrieves across all
        episodes (legacy behavior).
        """

        history = history if history is not None else []
        memories = await self._memory.retrieve(
            MemoryQuery(query_text=goal, episode_id=episode_id)
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": self._build_user_message(goal, state, memories, history),
            },
        ]

        last_error: str = "no attempt was made"
        for attempt in range(self._max_retries + 1):
            response = await self._llm.chat(messages)
            try:
                parsed = _extract_first_json_object(response.content)
                action = PlannerAction.model_validate(parsed)
            except (ValueError, ValidationError) as exc:
                last_error = str(exc)
                if attempt >= self._max_retries:
                    break
                # Feed the failure back so the model can correct itself.
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous output was invalid: "
                            f"{last_error}\nRespond with ONLY the JSON object "
                            "described in the system prompt."
                        ),
                    }
                )
                continue
            return PlannedDecision(
                action=action,
                retrieved_memories=memories,
                llm=response,
                retries=attempt,
            )

        raise PlannerError(
            f"LLM failed to produce a valid action after "
            f"{self._max_retries + 1} attempts. Last error: {last_error}"
        )
