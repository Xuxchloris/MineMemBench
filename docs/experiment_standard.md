# M15 Experiment Standard

> Status: **DRAFT — prepared by B**, pending A ratification. A (Codex) owns
> this standard; B's draft encodes the difficulty ladders and failure-point
> rule discussed for M15B.

Binding rules for every stress-benchmark experiment. C executes exactly this;
B keeps the tooling honest; A judges results against it. Changing this
standard requires an A-issued revision, never an ad-hoc decision mid-campaign.

## 1. Cells and seeds

- A **cell** = (scenario, backend, difficulty-point). Backends under test:
  `none`, `vector`, `mem0`, `letta`.
- Smoke phase: 3 runs per cell, seed 42 (LLM nondeterminism provides the
  within-cell variance).
- Formal phase: 10 runs per cell, one invocation per seed, seeds **42–51**
  (matching the classic 120-run matrix protocol). Never `--runs 10` in one
  invocation: the runner reuses the seed across `--runs`, so a formal cell is
  ten separate `--runs 1 --seed <s>` invocations.
- The same seed set is used for every backend in a cell (paired design).
- If a formal cell's success rate lands in (0.2, 0.8) or run-to-run variance
  is visibly high, extend that cell to 20–30 seeds (52+). Do not expand cells
  that are already 0% or 100% — that burns API for no information.

## 2. Difficulty ladders

| scenario | parameter(s) | ladder |
|---|---|---|
| `delayed_recall` | `interference_count`, `similar_distractor_count` | (10,0) control → (50,5) → (200,20) → (500,50) |
| `world_update` | `update_depth` | 1 control → 2 → 3 → 4 |
| `memory_noise_stress` | `noise_count` | 0 control → 10 → 50 → 100 → 200 → 500 → 1000 |
| `failure_transfer` | `transfer_count`, `noise_fact_count` | (2,5) control → (2,20) → (3,20) → (3,50) |

Campaign order: smoke the full ladder once (3 runs/cell) → A picks the
informative difficulty band per scenario → formal 10 seeds on the band →
extend only contested cells.

## 3. Failure Point (definition)

A backend's **failure point** on a scenario is the lowest ladder level where
its formal-phase **task success rate < 80%**. Interpolation between ladder
levels is never allowed; a backend that fails at the lowest non-control level
is marked "fails at first step". No outcome is pre-assumed: the table is
computed from logs only.

## 4. Contamination guards (checked per run, audited per campaign)

- Every run log must carry `fairness.valid == true` (controlled variables
  fingerprint + episode-leakage probe). A run with `valid == false` is
  excluded from statistics **and the exclusion is reported** — never silently
  dropped.
- Stress runs write to an isolated `RESULTS_DIR` (e.g.
  `results/stress_smoke/`, `results/stress_formal/`), never into the classic
  matrix directory.
- `none` must retrieve nothing in every cell; if it ever returns a memory,
  that is a Critical contamination finding.
- Identical planner model, temperature, system-prompt hash, tool-set hash,
  scenario version and params across backends in a cell — read from the
  fairness records, not assumed.

## 5. N/A rules

- Retrieval-layer structured-fact metrics (`current_fact_accuracy`,
  `fact_retrieval_rank`, `recall_accuracy`, `wrong_fact_rate`,
  `retrieval_precision`, `stale_memory_rate`, `obsolete_fact_retrieval_rate`)
  are **structurally N/A for `letta`** (archival passages round-trip text
  only; see A-REVIEW-001 M-1). Report N/A; never count as failure; the
  cross-backend comparison on those metrics excludes letta by design.
- Behavioral metrics (`task_success`, `stale_action`, `adaptation_success`,
  `transfer_success_rate`, `preparation_rate`, `failure_repetition_rate`) are
  the primary endpoints and are valid for all backends.

## 6. Reporting

All numbers come from run logs; nothing is hand-filled. Required outputs per
campaign: per-cell success/token/latency tables, the failure-point table
(backend × scenario → first failing level), and charts generated from the
logs: success vs noise, recall vs interference, stale rate vs update depth,
token cost vs memory size, retrieval latency vs memory size, transfer success
rate, success vs cost, failure point by backend.
