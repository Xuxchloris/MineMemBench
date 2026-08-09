# A-FINAL-012 — delayed-recall v2 diagnostic smoke research audit

Date: 2026-08-08  
Reviewer: Agent A  
Evidence: TASK-011/012, B-COMPLETION-011, QA-011/012, raw round-5 JSON/logs  
Decision: **smoke accepted as valid diagnostic evidence; formal ranking not approved**

## Critical

None.

## High

### H-1 — Evidence is not an immutable formal comparison

- **Location:** repository HEAD `cbaa276` with a heavily dirty worktree;
  `results/stress_controlled_round5_entity_key_v2_200_20/`;
  `docs/experiment_standard.md`.
- **Reason:** the campaign is three seeds per backend and the exact reviewed
  code is not represented by a clean revision/commit SHA. Repository rules
  prohibit development agents from staging, committing or pushing.
- **Impact on conclusions:** **Yes.** The data support a bounded causal
  diagnostic, not a population-level framework ranking, confidence interval,
  Failure Point or publication claim.
- **Minimum repair:** a review-owned clean immutable revision, recorded
  dirty-state/code fingerprint and a separately pre-registered paired formal
  sample. Do not retroactively relabel round 5 as formal.

## Medium

### M-1 — The treatment measures exact opaque-key retrieval, not memory broadly

- **Location:** `benchmark/minemembench/scenarios/delayed_recall.py` v2 key
  generation/goal; round-5 cell `(200,20)`.
- **Reason:** naming `cache-<8 hex>` makes the oracle semantically valid and
  removes the old contradiction, but it is a narrow identifier-association
  task. Tokenization and exact-key retention are prominent parts of the
  treatment.
- **Impact on conclusions:** **Yes, external validity only.** The result says
  whether this event enters causal top-10 and can guide action; it does not
  establish general episodic/semantic memory quality.
- **Minimum repair:** combine this task with independently valid world-update,
  noise and real failure-learning treatments before any broad claim.

### M-2 — Mem0 optional lexical features are absent

- **Location:** round-5 Mem0 stderr logs (`run_002`, `run_005`, `run_008`).
- **Reason:** spaCy models are unavailable and fastembed BM25 search is
  disabled. Runs are valid for the installed Mem0 configuration, but that
  configuration must not be silently generalized to every Mem0 deployment.
- **Impact on conclusions:** **Potentially.** Optional retrieval features could
  change exact-key recall. They did not cause a process error and all backends
  still received identical benchmark events.
- **Minimum repair:** pin and disclose the intended Mem0 feature set before
  formal execution; if it changes, treat the rerun as a new configuration.

### M-3 — Latencies are descriptive, not efficiency-normalized

- **Location:** round-5 `avg_add_latency_ms` / `avg_retrieve_latency_ms`.
- **Reason:** backend internal embedding/HTTP work and initialization are not
  decomposed into comparable cost components.
- **Impact on conclusions:** **Yes for efficiency claims, no for recall
  behavior.**
- **Minimum repair:** separately record initialization, embedding/LLM calls and
  per-operation wall time before comparing efficiency.

## Low

None that affect this smoke.

## Accepted causal finding

All mandatory validity checks passed: 12/12 processes, exact 221-event input
equality per seed, common world state/prompt/tools/model, fair reset/isolation,
neutral simultaneously true candidates, no ground-truth leakage and exact
metric re-derivation from causal step-0 snapshots.

Observed three-seed pattern:

| backend | target rank | success |
|---|---|---|
| none | N/A / N/A / N/A (empty) | 0/3 |
| vector | 1 / 1 / 1 | 3/3 |
| mem0 | 1 / absent / 1 | 2/3 |
| letta | absent / absent / 4 | 1/3 |

Across the six memory-backed runs where the target event was present in the
causal top-10, behavior succeeded 6/6. Across the three memory-backed runs
where it was absent, behavior failed 3/3; NoMemory failed 3/3. Letta seed 44
selected the correct target at rank 4 despite a distractor at rank 1, proving
the repaired planner task is not merely “follow retrieval item 1.”

This supports one narrow conclusion: **under the v2 `(200,20)` treatment,
behavior is mediated by whether the target association is available to the
planner, and the planner can resolve it below rank 1.** It does not support a
framework superiority claim. Round 4 and round 5 must never be pooled.

## Next decision

Do not expand delayed-recall to formal n while H-1 remains. Continue M15
coverage with a semantically and causally auditable Controlled
`world_update` A→B→C→D treatment. Its current implementation is not ready:
events use UUID/wall time in Controlled mode, retrieval metrics use a second
evaluation probe instead of the causal first-step snapshot, ground truth is
coordinate-inferred rather than explicit event identity, and the Controlled
CLI/campaign runner is hard-coded to delayed-recall. These are implementation
tasks for B followed by independent C QA before any world-update smoke.
