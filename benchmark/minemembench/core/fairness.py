"""Pre-run fairness audit for the benchmark (M15B stress layer).

Every run log carries a `FairnessRecord` with the controlled variables that
make runs comparable: Minecraft version, world seed, planner model,
temperature, a hash of the system prompt, a hash of the action/tool set, and
the scenario name plus its effective parameter dict.

The checker also runs an episode-leakage probe between consecutive runs: the
next run's planner retrieves memories scoped to its own `episode_id`, so the
previous run's memories must never surface under that scope. The probe asks
exactly that question before the next run starts; if the previous episode's
memories come back, the run is marked invalid in its log.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..agent.llm_provider import LLMProvider
from ..agent.planner import SYSTEM_PROMPT_HASH, TOOL_SET_HASH
from ..core.config import Settings
from ..memory.base import MemoryBackend, MemoryQuery

#: Fallback query for the leakage probe when no previous-run content is known.
_DEFAULT_PROBE_QUERY = "benchmark episode memory"


class FairnessRecord(BaseModel):
    """The audited controlled-variable fingerprint of one run."""

    model_config = ConfigDict(validate_assignment=True)

    checked_at: datetime
    minecraft_version: str
    world_seed: int | None
    planner_model: str
    temperature: float
    system_prompt_hash: str
    tool_set_hash: str
    scenario: str
    scenario_params: dict[str, Any] = Field(default_factory=dict)
    episode_leakage_checked: bool = False
    episode_leakage_leaked: bool | None = None
    episode_leakage_previous: str | None = None
    episode_leakage_next: str | None = None
    leak_probe_query: str | None = None
    valid: bool = True
    invalid_reason: str | None = None


class FairnessChecker:
    """Builds FairnessRecords and runs the episode-leakage probe."""

    def __init__(self, settings: Settings, llm: LLMProvider) -> None:
        self._settings = settings
        self._llm = llm

    def _base_record(
        self, *, scenario: str, scenario_params: dict[str, Any]
    ) -> FairnessRecord:
        """A record with the run's controlled variables; probe fields unset."""

        return FairnessRecord(
            checked_at=datetime.now(UTC),
            minecraft_version=self._settings.minecraft_version,
            world_seed=self._settings.world_seed,
            planner_model=self._llm.model,
            temperature=self._llm.temperature,
            system_prompt_hash=SYSTEM_PROMPT_HASH,
            tool_set_hash=TOOL_SET_HASH,
            scenario=scenario,
            scenario_params=dict(scenario_params),
        )

    async def check(
        self,
        *,
        memory: MemoryBackend,
        scenario: str,
        scenario_params: dict[str, Any],
        previous_episode: str | None,
        next_episode: str | None,
        leak_probe_query: str | None = None,
        probe_limit: int = 20,
    ) -> FairnessRecord:
        """Record the run's controlled variables and probe for episode leakage.

        `previous_episode` is the episode id of the run that just finished and
        `next_episode` the fresh id of the upcoming run. When there is no
        previous episode (first run of a process) the probe is skipped and the
        record stays valid.
        """

        record = self._base_record(scenario=scenario, scenario_params=scenario_params)
        if previous_episode is None or next_episode is None:
            return record

        probe_query = leak_probe_query or _DEFAULT_PROBE_QUERY
        leaked, _retrieved = await self.run_leakage_probe(
            memory,
            previous_episode,
            next_episode,
            probe_query,
            limit=probe_limit,
        )
        record.episode_leakage_checked = True
        record.episode_leakage_leaked = leaked
        record.episode_leakage_previous = previous_episode
        record.episode_leakage_next = next_episode
        record.leak_probe_query = probe_query
        if leaked:
            record.valid = False
            record.invalid_reason = (
                f"episode leakage: memories of previous episode "
                f"{previous_episode!r} were retrievable under the next run's "
                f"episode scope"
            )
        return record

    @staticmethod
    async def run_leakage_probe(
        memory: MemoryBackend,
        previous_episode: str,
        next_episode: str,
        probe_query: str,
        limit: int = 20,
    ) -> tuple[bool, int]:
        """Probe whether `next_episode`'s scoped retrieval leaks `previous_episode`.

        The retrieval is scoped to `next_episode` exactly as the planner will
        scope it during the upcoming run, and `probe_query` is drawn from the
        previous run's content so a leaking backend is likely to surface it.
        Returns `(leaked, retrieved_count)`.
        """

        items = await memory.retrieve(
            MemoryQuery(query_text=probe_query, episode_id=next_episode, limit=limit)
        )
        leaked = any(item.event.episode_id == previous_episode for item in items)
        return leaked, len(items)
