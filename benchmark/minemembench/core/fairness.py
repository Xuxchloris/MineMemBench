"""Post-run fairness audit for the benchmark (M15B stress layer).

Every run log carries a `FairnessRecord` with the controlled variables that
make runs comparable: Minecraft version, world seed, planner model,
temperature, a hash of the system prompt, a hash of the action/tool set, the
scenario name plus its effective parameter dict, and the run's effective seed
(`base_seed + run_index`, see the CLI).

After a run's metrics are captured, the checker resets the episode that
actually ran and then verifies the cleanup instead of trusting it:

1. `reset()` is called on the COMPLETED episode id (not on a fresh one).
2. The reset episode itself is probed — scoped exactly as the planner scopes
   retrieval. Any returned item means the reset did not clean up.
3. A brand-new episode scope is probed with a query drawn from the run's own
   content. Any returned item means episode scoping itself leaks.

A probing retrieval may lazily create an empty scope server-side (the letta
backend creates one agent per episode on first touch), so both probed scopes
are reset again best-effort afterwards, leaving no probe artifacts behind.

Any reset error, probe error, or returned item marks the run invalid — but the
run log is still written; an invalid cleanup is an auditable result, never a
silently dropped one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..agent.llm_provider import LLMProvider
from ..agent.planner import (
    PLANNER_USER_TEMPLATE_HASH,
    SYSTEM_PROMPT_HASH,
    TOOL_SET_HASH,
)
from ..core.config import Settings
from ..core.ids import new_run_id
from ..core.provenance import SourceProvenance, capture_source_provenance
from ..memory.base import MemoryBackend, MemoryQuery

#: Fallback query for the cleanup probes when no run-content query is known.
_DEFAULT_PROBE_QUERY = "benchmark episode memory"

#: Campaign modes. `native` is the exploratory live-system mode; `controlled`
#: is the auditable comparison mode (fresh canonical mock fixture per run,
#: deterministic semantic events). The identity is recorded in every result
#: and fairness record so the two outputs can never be mixed silently.
CAMPAIGN_MODE_NATIVE = "native"
CAMPAIGN_MODE_CONTROLLED = "controlled"


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
    #: Fingerprint of the planner user-message template + memory-view schema
    #: (TASK-009). Optional for backward compatibility with pre-TASK-009 logs;
    #: populated on every new run.
    planner_user_template_hash: str | None = None
    #: Exact producer-source identity (TASK-024). Optional so every historical
    #: result remains loadable; populated on every new run.
    source_tree_fingerprint: str | None = None
    source_file_count: int | None = None
    git_available: bool | None = None
    git_commit: str | None = None
    git_dirty: bool | None = None
    git_status_fingerprint: str | None = None
    scenario: str
    scenario_params: dict[str, Any] = Field(default_factory=dict)
    #: Which campaign mode produced the run ("native" or "controlled").
    campaign_mode: str = CAMPAIGN_MODE_NATIVE
    #: Controlled Mode only: explicit process selector and versioned identity
    #: of the fixed fixture the run started from, so scenario-specific worlds
    #: remain auditable without being inferred from a memory backend.
    fixture_selector: str | None = None
    fixture_identity: str | None = None
    #: The run's effective seed (base_seed + run_index).
    run_seed: int | None = None
    #: The completed episode this record's cleanup verification ran on.
    reset_episode: str | None = None
    reset_performed: bool = False
    reset_error: str | None = None
    #: Items returned when probing the reset episode after `reset()`.
    post_reset_items: int | None = None
    #: The fresh probe scope and how many items it (wrongly) returned.
    fresh_scope_episode: str | None = None
    fresh_scope_items: int | None = None
    #: The query both cleanup probes ran with (run content when available).
    probe_query: str | None = None
    valid: bool = True
    invalid_reason: str | None = None


class FairnessChecker:
    """Builds FairnessRecords and verifies the post-run episode cleanup."""

    def __init__(
        self,
        settings: Settings,
        llm: LLMProvider,
        *,
        provenance: SourceProvenance | None = None,
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._provenance = provenance or capture_source_provenance()

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
            planner_user_template_hash=PLANNER_USER_TEMPLATE_HASH,
            source_tree_fingerprint=self._provenance.source_tree_fingerprint,
            source_file_count=self._provenance.source_file_count,
            git_available=self._provenance.git_available,
            git_commit=self._provenance.git_commit,
            git_dirty=self._provenance.git_dirty,
            git_status_fingerprint=self._provenance.git_status_fingerprint,
            scenario=scenario,
            scenario_params=dict(scenario_params),
        )

    async def check(
        self,
        *,
        memory: MemoryBackend,
        scenario: str,
        scenario_params: dict[str, Any],
        episode_id: str,
        run_seed: int | None = None,
        campaign_mode: str = CAMPAIGN_MODE_NATIVE,
        fixture_selector: str | None = None,
        fixture_identity: str | None = None,
        probe_query: str | None = None,
        probe_limit: int = 20,
    ) -> FairnessRecord:
        """Reset the completed episode and verify the cleanup, in one record.

        `episode_id` is the episode of the run that just finished; its metrics
        must already be captured before this call. `run_seed` is the effective
        seed of that run (`base_seed + run_index`). A reset error, a probe
        error, or any item returned by the reset-episode or fresh-scope probe
        marks the record invalid with an auditable reason.
        """

        record = self._base_record(scenario=scenario, scenario_params=scenario_params)
        record.run_seed = run_seed
        record.campaign_mode = campaign_mode
        record.fixture_selector = fixture_selector
        record.fixture_identity = fixture_identity
        record.reset_episode = episode_id
        query = probe_query or _DEFAULT_PROBE_QUERY
        record.probe_query = query

        problems: list[str] = []

        try:
            await memory.reset(episode_id)
            record.reset_performed = True
        except Exception as exc:  # noqa: BLE001 — audit, never crash the run
            record.reset_error = f"{type(exc).__name__}: {exc}"
            problems.append(
                f"reset of completed episode {episode_id!r} failed: "
                f"{record.reset_error}"
            )

        record.post_reset_items, problem = await self._probe_scope(
            memory, episode_id, query, probe_limit,
            subject=f"reset episode {episode_id!r}",
        )
        if problem is not None:
            problems.append(problem)
        # The probe may have lazily created an empty scope (one letta agent per
        # episode): drop it again so the audit leaves nothing behind.
        await self._best_effort_reset(memory, episode_id)

        fresh_episode = new_run_id()
        record.fresh_scope_episode = fresh_episode
        record.fresh_scope_items, problem = await self._probe_scope(
            memory, fresh_episode, query, probe_limit,
            subject=f"fresh scope {fresh_episode!r}",
        )
        if problem is not None:
            problems.append(problem)
        await self._best_effort_reset(memory, fresh_episode)

        if problems:
            record.valid = False
            record.invalid_reason = "; ".join(problems)
        return record

    @staticmethod
    async def _probe_scope(
        memory: MemoryBackend,
        episode_id: str,
        query: str,
        limit: int,
        *,
        subject: str,
    ) -> tuple[int | None, str | None]:
        """Probe one episode scope; return (item_count, problem | None)."""

        try:
            items = await memory.retrieve(
                MemoryQuery(query_text=query, episode_id=episode_id, limit=limit)
            )
        except Exception as exc:  # noqa: BLE001 — audit, never crash the run
            return None, (
                f"cleanup probe of {subject} failed: "
                f"{type(exc).__name__}: {exc}"
            )
        if items:
            return len(items), (
                f"cleanup probe of {subject} returned {len(items)} item(s)"
            )
        return 0, None

    @staticmethod
    async def _best_effort_reset(memory: MemoryBackend, episode_id: str) -> None:
        """Drop any scope a probe lazily created; failures are ignored."""

        try:
            await memory.reset(episode_id)
        except Exception:  # noqa: BLE001 — best-effort cleanup only
            pass
