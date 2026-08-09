"""Typed API models for the read-only dashboard."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DashboardModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FileDiagnostic(DashboardModel):
    file_id: str
    relative_path: str
    kind: Literal["result", "manifest"]
    partial: bool = False
    stale: bool = False
    invalid: bool = False
    error_category: str | None = None


class RunCard(DashboardModel):
    run_id: str
    relative_path: str
    scenario: str
    seed: int
    memory_backend: str
    success: bool
    campaign_mode: str
    params: dict[str, Any] = Field(default_factory=dict)
    semantics_version: str | None = None
    campaign_id: str | None = None
    producer_status: Literal[
        "ok", "failed", "pending", "standalone", "ambiguous"
    ] = "standalone"
    producer_error: str | None = None
    git_commit: str | None = None
    source_fingerprint: str | None = None
    model: str | None = None
    temperature: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    llm_latency_ms: float | None = None
    retrieval_latency_ms: float | None = None
    end_to_end_latency_ms: float | None = None
    fairness_valid: bool | None = None
    fairness_invalid_reason: str | None = None
    metrics: dict[str, float | int | str | None] = Field(default_factory=dict)
    partial: bool = False
    stale: bool = False


class CampaignCellSummary(DashboardModel):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)
    scheduled: int = 0
    completed: int = 0
    ok: int = 0
    failed: int = 0
    pending: int = 0
    success_count: int = 0
    success_rate: float | None = None
    valid_count: int = 0
    invalid_count: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    mean_llm_latency_ms: float | None = None
    mean_retrieval_latency_ms: float | None = None
    mean_end_to_end_latency_ms: float | None = None


class CampaignMatrixCell(CampaignCellSummary):
    backend: str


class CampaignCard(DashboardModel):
    campaign_id: str
    relative_path: str
    schema_version: str | None = None
    scenario: str | None = None
    semantics_version: str | None = None
    mode: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
    git_commit: str | None = None
    source_fingerprint: str | None = None
    source_file_count: int | None = None
    seeds: list[int] = Field(default_factory=list)
    backends: list[str] = Field(default_factory=list)
    cells: list[CampaignCellSummary] = Field(default_factory=list)
    matrix: list[CampaignMatrixCell] = Field(default_factory=list)
    run_count: int = 0
    completed_count: int = 0
    ok_count: int = 0
    failed_count: int = 0
    pending_count: int = 0
    invalid_count: int = 0
    error_count: int = 0
    remaining_count: int = 0
    progress_percent: float = 0.0
    status: Literal["pending", "running", "completed", "failed", "partial"] = "pending"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    mean_llm_latency_ms: float | None = None
    mean_retrieval_latency_ms: float | None = None
    mean_end_to_end_latency_ms: float | None = None
    eta_seconds: float | None = None
    partial: bool = False
    stale: bool = False


class IndexSnapshot(DashboardModel):
    revision: str
    results_dir: str
    campaigns: list[CampaignCard] = Field(default_factory=list)
    runs: list[RunCard] = Field(default_factory=list)
    diagnostics: list[FileDiagnostic] = Field(default_factory=list)
    result_file_count: int = 0
    manifest_file_count: int = 0
    partial_file_count: int = 0
    invalid_file_count: int = 0


class RetrievalEvidence(DashboardModel):
    observed: bool
    item_count: int
    items: list[dict[str, Any]] = Field(default_factory=list)


class UtilizationEvidence(DashboardModel):
    status: Literal["supported", "unknown"] = "unknown"
    rule_id: str | None = None
    event_ids: list[str] = Field(default_factory=list)
    explanation: str


class PlannerEvidence(DashboardModel):
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str
    prompt_tokens: int
    completion_tokens: int
    llm_latency_s: float


class OutcomeEvidence(DashboardModel):
    status: str
    error: str | None = None
    result: dict[str, Any] | None = None
    pre_position: dict[str, float] | None = None
    post_position: dict[str, float]


class ReplayFrame(DashboardModel):
    frame_id: str
    sequence: int
    phase: str
    session_id: str | None = None
    run_ordinal: int
    step_index: int
    retrieval: RetrievalEvidence
    utilization: UtilizationEvidence
    planner: PlannerEvidence
    outcome: OutcomeEvidence
    world_state: dict[str, Any] | None = None
    semantic_events: list[str] = Field(default_factory=list)


class TrajectoryPoint(DashboardModel):
    sequence: int
    phase: str
    session_id: str | None = None
    x: float
    z: float
    point_kind: Literal["pre", "post"]
    action: str | None = None
    status: str | None = None


class TimelineEvent(DashboardModel):
    sequence: int
    frame_sequence: int | None = None
    kind: Literal[
        "memory_offered",
        "phase",
        "retrieve",
        "decide",
        "action",
        "outcome",
        "evaluation",
    ]
    label: str
    phase: str | None = None
    session_id: str | None = None
    evidence_ref: str | None = None
    timestamp: str | None = None


class TrajectoryMarker(DashboardModel):
    sequence: int
    frame_sequence: int | None = None
    kind: Literal["target", "entity", "action", "failure", "success"]
    x: float
    z: float
    label: str
    evidence_ref: str | None = None


class ReplayDocument(DashboardModel):
    source_digest: str
    scenario: str
    seed: int
    memory_backend: str
    phases: list[dict[str, Any]] = Field(default_factory=list)
    probes: list[dict[str, Any]] = Field(default_factory=list)
    frames: list[ReplayFrame] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    trajectory: list[TrajectoryPoint] = Field(default_factory=list)
    trajectory_markers: list[TrajectoryMarker] = Field(default_factory=list)
    terrain_reconstructed: bool = False
    trajectory_disclaimer: str = (
        "Positions and markers come only from stored evidence; terrain is not reconstructed."
    )
    available_memory: list[dict[str, Any]] = Field(default_factory=list)
    attribution_counts: dict[str, int] = Field(default_factory=dict)


class FairnessFieldComparison(DashboardModel):
    field: str
    status: Literal["pass", "fail", "unknown"]
    values: dict[str, Any] = Field(default_factory=dict)


class ComparisonCell(DashboardModel):
    backend: str
    status: Literal["present", "missing", "duplicate"]
    run_ids: list[str] = Field(default_factory=list)
    success: bool | None = None
    fairness_valid: bool | None = None
    metrics: dict[str, float | int | str | None] = Field(default_factory=dict)
    retrieved_top_k: list[dict[str, Any]] = Field(default_factory=list)
    first_action: dict[str, Any] | None = None
    preparation: int | float | str | None = None
    failure_repetition: int | float | str | None = None
    steps: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    llm_latency_ms: float | None = None
    retrieval_latency_ms: float | None = None
    end_to_end_latency_ms: float | None = None
    replay_frames: list[dict[str, Any]] = Field(default_factory=list)


class SameSeedComparison(DashboardModel):
    scenario: str
    seed: int
    campaign_mode: str
    params: dict[str, Any] = Field(default_factory=dict)
    verdict: Literal["pass", "fail", "unknown"]
    cells: list[ComparisonCell] = Field(default_factory=list)
    fairness_fields: list[FairnessFieldComparison] = Field(default_factory=list)
