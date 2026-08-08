"""The scenario engine: a reproducible, seeded episode with distinct phases.

A `Scenario` owns one benchmark episode's full lifecycle
(setup -> experience -> interference -> test -> evaluate). It is the M7
harness that turns a memory backend into a measurable treatment: the only
independent variable across runs remains the injected backend, and every
phase is driven by a fixed `seed` so runs are byte-identical.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..agent.llm_provider import LLMProvider
from ..core.client import BotClient
from ..core.config import Settings
from ..core.fairness import FairnessRecord
from ..core.runner import AgentRunner, RunLog
from ..memory.base import MemoryBackend, MemoryQuery


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


class ScenarioParamError(ValueError):
    """Raised when a scenario receives an unknown or invalid difficulty parameter."""


class RetrievalProbeItem(BaseModel):
    """One raw retrieved memory as seen by a retrieval probe.

    The full `context` of the reconstructed ExperienceEvent is preserved so the
    raw retrieval results survive in the run log (M15B requirement).
    """

    model_config = ConfigDict(validate_assignment=True)

    item_id: str
    episode_id: str
    event_type: str
    score: float | None
    created_at: datetime
    context: dict[str, Any] = Field(default_factory=dict)


class RetrievalProbe(BaseModel):
    """A recorded retrieval request plus every raw item it returned."""

    model_config = ConfigDict(validate_assignment=True)

    phase: str
    probe_index: int = 0
    query_text: str
    episode_id: str | None
    limit: int
    started_at: datetime
    finished_at: datetime
    latency_ms: float | None
    items: list[RetrievalProbeItem] = Field(default_factory=list)


class ScenarioResult(BaseModel):
    """The measured outcome of one scenario run.

    Values are never fabricated: anything unmeasured is None, which
    serializes as `null` and is reported as N/A downstream. `params` carries
    the effective difficulty parameters, `fairness` the audited controlled
    variables, and `retrieval_probes` the raw retrieval results of the run.
    """

    model_config = ConfigDict(validate_assignment=True)

    scenario: str
    episode_id: str
    seed: int
    memory_backend: str
    success: bool
    metrics: dict[str, float | int | str | None] = Field(default_factory=dict)
    run_log: RunLog | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    fairness: FairnessRecord | None = None
    retrieval_probes: list[RetrievalProbe] = Field(default_factory=list)

    def to_json(self) -> str:
        """Serialize the scenario result for the results directory."""

        return self.model_dump_json(indent=2)


class Scenario(ABC):
    """A reproducible benchmark episode.

    Subclasses implement the five phases; `run()` orchestrates them in order
    and records each phase into `ctx.records` so the harness can report a
    structured phase log.

    Difficulty parameters: `default_params` declares the scenario's settable
    knobs (with default values that reproduce the pre-stress behavior), and
    `apply_params()` validates and merges CLI-provided overrides. `params`
    always returns the effective (defaults + overrides) parameter dict.
    """

    name: ClassVar[str]
    default_params: ClassVar[dict[str, Any]] = {}

    @property
    def params(self) -> dict[str, Any]:
        """The effective difficulty parameters (defaults + overrides)."""

        if not hasattr(self, "_params"):
            self._params = dict(self.default_params)
        return dict(self._params)

    def apply_params(self, params: dict[str, Any]) -> None:
        """Validate and merge `params` over the declared defaults.

        Unknown parameter names raise `ScenarioParamError`; subclass
        `_validate_params` is invoked to range/type-check the merged values.
        """

        unknown = sorted(set(params) - set(self.default_params))
        if unknown:
            raise ScenarioParamError(
                f"unknown scenario parameter(s) for {self.name!r}: "
                f"{', '.join(unknown)}. Available: "
                f"{', '.join(sorted(self.default_params)) or 'none'}."
            )
        self._params = {**self.default_params, **params}
        self._validate_params()

    def _validate_params(self) -> None:
        """Hook for subclasses to range/type-check `self._params`."""

    def _require_int_param(self, name: str, minimum: int) -> None:
        """Reject a non-int / out-of-range value for the named int parameter."""

        value = self._params[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ScenarioParamError(
                f"{self.name}: parameter {name!r} must be an integer >= "
                f"{minimum}, got {value!r}"
            )

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


async def run_retrieval_probe(
    ctx: ScenarioContext,
    *,
    phase: str,
    query_text: str,
    limit: int = 10,
    probe_index: int = 0,
) -> tuple[list[Any], RetrievalProbe]:
    """Run one memory retrieval and record its raw items into a RetrievalProbe.

    The probe is scoped to the run's episode id, mirroring what the planner
    does, and its full raw results are preserved so the run log carries exactly
    what memory returned at evaluation time.
    """

    started = datetime.now(UTC)
    perf_started = time.perf_counter()
    items = await ctx.memory.retrieve(
        MemoryQuery(query_text=query_text, episode_id=ctx.episode_id, limit=limit)
    )
    latency_ms = round((time.perf_counter() - perf_started) * 1000.0, 3)
    finished = datetime.now(UTC)
    probe = RetrievalProbe(
        phase=phase,
        probe_index=probe_index,
        query_text=query_text,
        episode_id=ctx.episode_id,
        limit=limit,
        started_at=started,
        finished_at=finished,
        latency_ms=latency_ms,
        items=[
            RetrievalProbeItem(
                item_id=item.item_id,
                episode_id=item.event.episode_id,
                event_type=item.event.event_type.value,
                score=item.score,
                created_at=item.created_at,
                context=item.event.context,
            )
            for item in items
        ],
    )
    return items, probe
