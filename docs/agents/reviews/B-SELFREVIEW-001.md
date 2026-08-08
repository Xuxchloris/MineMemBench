# B-SELFREVIEW-001 — B's self-review notes on Letta live + M15B stress layer

> Status: **B's own working notes**, prepared 2026-08-08 before role
> assignment and handed to A (Codex) as input for A's first independent
> review. This is NOT an A review; A may adopt, amend, or discard any of it.

Scope: `docker-compose.letta.yml`,
`docs/letta_live.md`, `scripts/verify_letta_live.py`, the M15B stress-layer
diff (9 modified + 13 new files), report data from the 120-run classic matrix
plus the 30-run letta formal batch.

## Verdict

- Letta Docker live integration: **PASS** (verified live by independent
  re-run: A/B/C checks green, 30/30 formal runs successful, episode isolation
  holds). Limitations are documented in `docs/letta_live.md`.
- M15B stress layer: **PASS with findings** — code is committable as the
  baseline; findings below schedule follow-up work.

## Findings

### M-1 (Medium) — letta retrieval-layer metrics are structurally N/A

- Location: `benchmark/minemembench/memory/letta_adapter.py`
  (`_reconstruct_event`), metric consumers in
  `scenarios/world_update.py:162-179`, `scenarios/delayed_recall.py`
  (`compute_recall_metrics`), `scenarios/memory_noise_stress.py:120-130`.
- Cause: letta archival passages store text only; the adapter reconstructs
  events as `context={"text": ...}`, so structured `context.x/y/z/subject`
  reads never match. Every retrieval-layer structured-fact metric is N/A (or
  vacuous 0) for letta on all backends' shared scenarios.
- Affects conclusions? Partially. Behavioral endpoints (task_success,
  stale_action, adaptation, transfer) are valid for letta. Retrieval-layer
  cross-backend comparison excludes letta — this is codified in
  `docs/experiment_standard.md` §5 so nobody misreads N/A as failure.
- Minimal fix (backlog, B): embed the full event JSON as a machine-readable
  trailer line in the passage text and prefer it in `_reconstruct_event`;
  keep the human-readable rendering first so planner prompts stay clean.
  NOT a blocker for the stress campaign.

### L-1 (Low) — failure_transfer object names tuned for the hash embedder

- Location: `scenarios/failure_transfer.py:50-62` (comment is honest about
  it: "supply" token overlap is needed by the crude hash embedder).
- Affects conclusions? Minor: transfer tasks are less lexically different
  than the scenario prose implies; the measured transfer still requires
  tool-cause inference. Record as a design constraint in any write-up.
- Fix: none required now.

### L-2 (Low) — `--runs N` reuses one seed

- Location: `cli.py` run loop (seed identical across `--runs`).
- Affects conclusions? Only if a campaign misuses it; the classic matrix
  already used per-seed invocations. Codified in
  `docs/experiment_standard.md` §1 (formal cell = 10 per-seed invocations).
- Fix: none; documentation suffices.

### L-3 (Low) — letta server accumulates one agent per episode

- Location: adapter lifecycle (agents deleted only on explicit `reset()` of a
  known episode; the runner resets only fresh ids).
- Affects conclusions? No — retrieval is episode-scoped and the leakage probe
  guards correctness. Operational hygiene only: after the 30-run formal
  batch, 39 `mem-*` agents sit on the dev server.
- Minimal fix (backlog, B): a `scripts/cleanup_letta_agents.py` that deletes
  `mem-*` agents not referenced by kept logs.

## Contamination audit (this review)

- No benchmark contamination found: the 9 letta smoke logs (duplicate seed
  42) were quarantined to `results/pilot/smoke_letta/` before the classic
  report was regenerated; classic matrix = exactly 120 logs, seeds 42–51 per
  cell.
- Controlled variables: planner model/temperature/prompt/tools are constant
  across backends (M15B now records them per run via the fairness record;
  earlier matrix relied on config discipline — acceptable, now hardened).
- No memory-backend-specific branches in planner/scenario code; Letta never
  runs inference (verified at the compose + adapter level).
- Ceiling effect confirmed real (all memory backends 10/10 in all three
  classic scenarios) — the motivation for the M15B stress campaign, not a
  bug.
