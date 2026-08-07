"""The scenario engine: a reproducible, seeded episode with distinct phases.

A `Scenario` owns one benchmark episode's full lifecycle
(setup -> experience -> interference -> test -> evaluate). It is the M7
harness that turns a memory backend into a measurable treatment: the only
independent variable across runs remains the injected backend, and every
phase is driven by a fixed `seed` so runs are byte-identical.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..agent.llm_provider import LLMProvider
from ..core.client import BotClient
from ..core.config import Settings
from ..core.runner import AgentRunner, RunLog
from ..memory.base import MemoryBackend


class PhaseRecord(BaseModel):
    """One structured entry in a scenario's phase log."""

    model_config = ConfigDict(validate_assignment=True)

    phase: str
    started_at: datetime
    finished_at: datetime | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class ScenarioContext:
    """Everything a scenario phase needs, wired by the harness.

    `bot` is a live bridge (or a fake in tests), `memory` the injected
    backend under test, `runner` the goal-directed agent loop with the same
    `memory`, `llm` the shared planner provider, and `settings` the process
    configuration. `records` accumulates structured `PhaseRecord` entries.
    """

    bot: BotClient
    memory: MemoryBackend
    runner: AgentRunner
    llm: LLMProvider
    settings: Settings
    seed: int
    episode_id: str
    records: list[PhaseRecord] = field(default_factory=list)


class ScenarioResult(BaseModel):
    """The measured outcome of one scenario run.

    Values are never fabricated: anything unmeasured is None, which
    serializes as `null` and is reported as N/A downstream.
    """

    model_config = ConfigDict(validate_assignment=True)

    scenario: str
    episode_id: str
    seed: int
    memory_backend: str
    success: bool
    metrics: dict[str, float | int | str | None] = Field(default_factory=dict)
    run_log: RunLog | None = None

    def to_json(self) -> str:
        """Serialize the scenario result for the results directory."""

        return self.model_dump_json(indent=2)


class Scenario(ABC):
    """A reproducible benchmark episode.

    Subclasses implement the five phases; `run()` orchestrates them in order
    and records each phase into `ctx.records` so the harness can report a
    structured phase log.
    """

    name: ClassVar[str]

    @abstractmethod
    async def setup(self, ctx: ScenarioContext) -> None:
        """Read the world and fix the episode's controlled variables."""

    @abstractmethod
    async def experience_phase(self, ctx: ScenarioContext) -> None:
        """The memory-worthy experience is written to the backend."""

    @abstractmethod
    async def interference_phase(self, ctx: ScenarioContext) -> None:
        """Seeded, unrelated noise between learning and testing."""

    @abstractmethod
    async def test_phase(self, ctx: ScenarioContext) -> None:
        """Run the goal-directed episode that probes memory."""

    @abstractmethod
    async def evaluate(self, ctx: ScenarioContext) -> ScenarioResult:
        """Measure the outcome; anything unmeasured stays None."""

    async def run(self, ctx: ScenarioContext) -> ScenarioResult:
        """Execute the phases in order and return the measured result."""

        for phase_name in (
            "setup",
            "experience_phase",
            "interference_phase",
            "test_phase",
        ):
            await self._record(ctx, phase_name, getattr(self, phase_name)(ctx))
        return await self._record(ctx, "evaluate", self.evaluate(ctx))

    async def _record(
        self, ctx: ScenarioContext, phase_name: str, pending: Any
    ) -> Any:
        """Await one phase, appending its PhaseRecord (error or not)."""

        started = datetime.now(UTC)
        try:
            value = await pending
        except Exception as exc:
            ctx.records.append(
                PhaseRecord(
                    phase=phase_name,
                    started_at=started,
                    finished_at=datetime.now(UTC),
                    error=str(exc),
                )
            )
            raise
        ctx.records.append(
            PhaseRecord(
                phase=phase_name,
                started_at=started,
                finished_at=datetime.now(UTC),
            )
        )
        return value
