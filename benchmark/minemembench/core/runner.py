"""The agent loop: observe -> decide -> act -> log, until success or budget.

Controlled variables are recorded in the RunLog (memory backend name, model,
temperature) so runs stay comparable; the only independent variable is the
injected memory backend. The working transcript passed to the planner is
backend-independent short-term context (see agent.planner).
"""

from __future__ import annotations

import math
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..agent.llm_provider import LLMProvider
from ..agent.planner import Planner, TranscriptEntry
from ..memory.base import MemoryBackend
from .client import BotClient
from .models import ActionStatus, Position

#: A goal position counts as reached within this euclidean distance (blocks).
SUCCESS_RADIUS_BLOCKS = 2.0


class RunStep(BaseModel):
    """One observe-decide-act iteration of the agent loop."""

    model_config = ConfigDict(validate_assignment=True)

    index: int = Field(ge=0)
    position: Position
    retrieved_memory_count: int = Field(ge=0)
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str
    action_status: ActionStatus
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    latency_s: float = Field(ge=0.0)


class RunLog(BaseModel):
    """Complete record of one goal-directed run."""

    model_config = ConfigDict(validate_assignment=True)

    run_id: str
    memory_backend: str
    goal: str
    model: str
    temperature: float
    steps: list[RunStep] = Field(default_factory=list)
    llm_calls: int = Field(ge=0)
    total_prompt_tokens: int = Field(ge=0)
    total_completion_tokens: int = Field(ge=0)
    success: bool

    def to_json(self) -> str:
        """Serialize the run for the results directory."""

        return self.model_dump_json(indent=2)


def _distance(a: Position, b: Position) -> float:
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


class AgentRunner:
    """Runs a single goal against the bot bridge with an injected backend."""

    def __init__(
        self, bot: BotClient, memory: MemoryBackend, llm: LLMProvider
    ) -> None:
        self._bot = bot
        self._memory = memory
        self._llm = llm
        self._planner = Planner(bot, memory, llm)

    async def run_goal(
        self,
        goal: str,
        *,
        max_steps: int = 10,
        success_at: Position | None = None,
    ) -> RunLog:
        """Loop until `success_at` is reached or `max_steps` is exhausted.

        Each executed action appends one TranscriptEntry, so the planner sees
        a growing working transcript on every step. Without `success_at` the
        loop always runs to `max_steps` and `success` stays False — there is
        no positional finish line to check. Token totals cover the final call
        of each decision; retried calls are counted in `llm_calls` but their
        usage is not available.
        """

        backend_stats = await self._memory.stats()

        steps: list[RunStep] = []
        transcript: list[TranscriptEntry] = []
        llm_calls = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        success = False

        for index in range(max_steps):
            state = await self._bot.get_state()
            decision = await self._planner.decide(goal, state, transcript)
            llm_calls += 1 + decision.retries
            total_prompt_tokens += decision.llm.prompt_tokens
            total_completion_tokens += decision.llm.completion_tokens

            result = await self._bot.execute(
                decision.action.action.value, decision.action.arguments
            )
            position = (
                result.state_after.position
                if result.state_after is not None
                else state.position
            )

            steps.append(
                RunStep(
                    index=index,
                    position=position,
                    retrieved_memory_count=len(decision.retrieved_memories),
                    action=decision.action.action.value,
                    arguments=decision.action.arguments,
                    reason=decision.action.reason,
                    action_status=result.status,
                    prompt_tokens=decision.llm.prompt_tokens,
                    completion_tokens=decision.llm.completion_tokens,
                    latency_s=decision.llm.latency_s,
                )
            )
            transcript.append(
                TranscriptEntry(
                    index=index,
                    action=decision.action.action.value,
                    arguments=decision.action.arguments,
                    reason=decision.action.reason,
                    status=result.status,
                    position_after=position,
                )
            )

            if (
                success_at is not None
                and _distance(position, success_at) <= SUCCESS_RADIUS_BLOCKS
            ):
                success = True
                break

        return RunLog(
            run_id=uuid.uuid4().hex,
            memory_backend=backend_stats.backend,
            goal=goal,
            model=self._llm.model,
            temperature=self._llm.temperature,
            steps=steps,
            llm_calls=llm_calls,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
            success=success,
        )
