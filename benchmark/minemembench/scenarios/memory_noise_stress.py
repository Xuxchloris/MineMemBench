"""Scenario D — Memory Noise Stress (M15B).

The agent learns exactly one key memory (the target chest's location), then N
unrelated ExperienceEvents are written to memory before the test goal, with N
parameterized by `noise_count` (levels 0 / 10 / 50 / 100 / 200 / 500 / 1000).
The stress is pure retrieval robustness: as memory fills with irrelevant
facts, do the relevant memories survive, and does retrieval slow down or cost
more tokens?

`noise_count` defaults to 0 — the ceiling-control run with no noise at all.

Phase-1 simplification: the target chest is VIRTUAL; we measure navigation
correctness to the remembered location. The noise events are deliberately
free of the target's high-frequency tokens, so only a real retrieval signal
(semantic / vector) can keep the key memory ahead.

Seed usage: `random.Random(seed)` drives the target offset in `setup`;
`random.Random(seed + 1)` drives the noise facts, keeping every phase
deterministic and phase-independent.
"""

from __future__ import annotations

import random
import time
from datetime import UTC, datetime
from typing import Any, ClassVar

from ..core.ids import new_event_id
from ..core.models import EventType, ExperienceEvent, Position
from ..core.runner import RunLog
from .base import Scenario, ScenarioContext, ScenarioResult, run_retrieval_probe
from .delayed_recall import _NOISE_FACTS

#: Deliberately free of any coordinates: recall must come from memory.
GOAL = "Return to the target chest you learned about at the start of this episode."


class MemoryNoiseStressScenario(Scenario):
    """Scenario D: does one key memory survive an ever-growing noise flood?"""

    name: ClassVar[str] = "memory_noise_stress"
    default_params: ClassVar[dict[str, Any]] = {"noise_count": 0}

    def __init__(self) -> None:
        self.target: Position | None = None
        self.run_log: RunLog | None = None
        self._started_at: float | None = None

    def _validate_params(self) -> None:
        self._require_int_param("noise_count", 0)

    async def setup(self, ctx: ScenarioContext) -> None:
        """Fix the virtual target = bot spawn + seeded horizontal offset."""

        self._started_at = time.perf_counter()
        spawn = (await ctx.bot.get_state()).position
        rng = random.Random(ctx.seed)
        dx = rng.choice((-1, 1)) * rng.randint(8, 20)
        dz = rng.choice((-1, 1)) * rng.randint(8, 20)
        self.target = Position(x=spawn.x + dx, y=spawn.y, z=spawn.z + dz)

    async def experience_phase(self, ctx: ScenarioContext) -> None:
        """Store exactly one key memory: the target chest's location."""

        assert self.target is not None
        await ctx.memory.add(
            ExperienceEvent(
                event_id=new_event_id(),
                episode_id=ctx.episode_id,
                timestamp=datetime.now(UTC),
                actor="scenario-instructor",
                event_type=EventType.LOCATION_DISCOVERED,
                context={
                    "subject": "target_chest",
                    "x": self.target.x,
                    "y": self.target.y,
                    "z": self.target.z,
                },
            )
        )

    async def interference_phase(self, ctx: ScenarioContext) -> None:
        """Flood memory with `noise_count` unrelated world-fact events."""

        rng = random.Random(ctx.seed + 1)
        for _ in range(self.params["noise_count"]):
            await ctx.memory.add(
                ExperienceEvent(
                    event_id=new_event_id(),
                    episode_id=ctx.episode_id,
                    timestamp=datetime.now(UTC),
                    actor="environment",
                    event_type=EventType.WORLD_FACT_UPDATED,
                    context={"subject": "world", "fact": rng.choice(_NOISE_FACTS)},
                )
            )

    async def test_phase(self, ctx: ScenarioContext) -> None:
        """Return to the chest using memory alone (no coordinates in the goal)."""

        assert self.target is not None
        self.run_log = await ctx.runner.run_goal(
            goal=GOAL, success_at=self.target, max_steps=3,
            episode_id=ctx.episode_id,
        )

    async def evaluate(self, ctx: ScenarioContext) -> ScenarioResult:
        """Measure retrieval robustness, cost, and end-to-end latency."""

        assert self.target is not None
        assert self.run_log is not None

        task_success = 1 if self.run_log.success else 0

        items, probe = await run_retrieval_probe(
            ctx, phase="evaluate", query_text="target chest location"
        )
        retrieved_count = len(items)
        relevant = [
            item for item in items if item.event.context.get("subject") == "target_chest"
        ]
        relevant_memory_precision = (
            round(len(relevant) / retrieved_count, 4) if retrieved_count else None
        )
        irrelevant_retrieval_rate = (
            round((retrieved_count - len(relevant)) / retrieved_count, 4)
            if retrieved_count
            else None
        )

        stats = await ctx.memory.stats()
        metrics: dict[str, float | int | str | None] = {
            "task_success": task_success,
            "relevant_memory_precision": relevant_memory_precision,
            "irrelevant_retrieval_rate": irrelevant_retrieval_rate,
            "retrieval_latency_ms": stats.extra.get("avg_retrieve_latency_ms"),
            "token_cost": (
                self.run_log.total_prompt_tokens + self.run_log.total_completion_tokens
            ),
            "total_prompt_tokens": self.run_log.total_prompt_tokens,
            "total_completion_tokens": self.run_log.total_completion_tokens,
            "llm_calls": self.run_log.llm_calls,
            "end_to_end_latency_s": (
                round(time.perf_counter() - self._started_at, 3)
                if self._started_at is not None
                else None
            ),
            "avg_add_latency_ms": stats.extra.get("avg_add_latency_ms"),
        }

        return ScenarioResult(
            scenario=self.name,
            episode_id=ctx.episode_id,
            seed=ctx.seed,
            memory_backend=stats.backend,
            success=task_success == 1,
            metrics=metrics,
            run_log=self.run_log,
            params=self.params,
            retrieval_probes=[probe],
        )
