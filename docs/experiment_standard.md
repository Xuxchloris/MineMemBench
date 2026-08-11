# M15 Experiment Standard

> Status: **TASK-027 Formal V1 design ratified before run 1.** Diagnostic
> evidence remains separate. Exact Formal cells, seeds, statistics and source
> identity are frozen in `docs/preregistration_m15_formal_v1.md`.

Binding rules for every stress-benchmark experiment. C executes exactly this;
B keeps the tooling honest; A judges results against it. Changing this
standard requires an A-issued revision, never an ad-hoc decision mid-campaign.

## 1. Cells and seeds

- A **cell** = (scenario, backend, difficulty-point). Backends under test:
  `none`, `vector`, `mem0`, `letta`.
- Smoke phase: 3 runs per cell via `--runs 3 --seed 42`. The CLI derives the
  paired seed schedule `base_seed + run_index`, so the effective seeds are
  **42, 43, 44** — never the same seed three times — and each run log records
  its effective seed in `seed` and `fairness.run_seed`.
- Formal V1 uses fresh paired seeds **1001–1010**, N=10 for every backend in
  every treatment cell. Calibration seeds 42/43/44 are excluded.
- Formal V1 has exactly eight treatment cells and 320 planned runs. It never
  extends based on observed Formal outcomes; no seed, cell, backend, prompt,
  parameter, retry or replacement may be added after run 1.
- Before any formal run, the external review owner must provide a clean commit,
  the campaign must pass `--require-clean-source`, and a frozen copy of
  `docs/preregistration_template.md` must specify the exact cells, paired seeds,
  sample size, endpoints, exclusions, stopping and analysis. A source
  fingerprint is necessary provenance but does not replace the clean commit.

## 2. Difficulty ladders

| scenario | parameter(s) | ladder |
|---|---|---|
| `delayed_recall` | `recall_semantics_version`, `interference_count`, `similar_distractor_count` | Semantics version is part of the cell identity: `legacy` (rounds 1–4, semantics invalid for ranking — diagnostics only) vs `entity_key_v2` (TASK-011; the only ranking-eligible treatment). v2 ladder: (10,0) control → (50,5) → (200,20) → (500,50). **Never pool across semantics versions.** |
| `world_update` | `update_semantics_version`, `update_depth` | Semantics version is part of the cell identity: `legacy` (probe-based metrics, mixed schemas — diagnostics only) vs `temporal_chain_v2` (TASK-013; neutral chain, causal step-0 metrics, typed ground truth). v2 depth-3 diagnostic is accepted in A-FINAL-015; remaining ladder: depth 1 control → 2 → 3 → 4. **Never pool across semantics versions or Controlled/Native modes.** |
| `memory_noise_stress` | `noise_semantics_version`, `noise_count` | `legacy` remains Native compatibility only; `key_retention_v2` (TASK-016) is the only Controlled treatment and uses causal step-0 metrics + typed ground truth. Planned ladder: 0 → 10 → 50 → 100 → 200 → 500 → 1000. Counts 0/10/50 are accepted diagnostics in A-FINAL-019; installed Mem0/Letta target loss is bracketed in `(10,50]`. No further noise execution or formal Failure Point is authorized. |
| `failure_learning` | `failure_semantics_version`, `interference_count` | `legacy` is same-task retry/native compatibility only. `observed_precondition_v2` is approved in `A-APPROVAL-020`: an actual failed ActionResult supplies the only prompt-visible cause, then a different entity/task tests transfer. Counts 0/10/50 are accepted Controlled diagnostics in `A-FINAL-021`/`022`/`023`. All 27 memory runs retain the failure at rank1/top1 and prepare correctly; neutral ambient interference loads Mem0/Letta top-10 without creating a retrieval Failure Point. This ladder is stopped: no count100, wider expansion, ranking or formal claim is authorized. Any task-similar distractor treatment requires a new semantics version and separate review. The old `failure_transfer` artifact remains unregistered and invalid. |

Diagnostic calibration used three paired seeds to select the informative
band. Formal V1 now freezes delayed recall `(200,20)`, world-update depth 3,
memory-noise `10/30/50`, and composite lifetime `L1/L2/L3`. Failure-learning
v4 stays a diagnostic mechanism case study and is not pooled or ranked.

### Controlled CLI/campaign capability (TASK-014)

The Controlled CLI gate and `scripts/run_controlled_campaign.py` now share
one central scenario/version policy. Approved combinations:
`delayed_recall` + `legacy` (historical diagnostics only),
`delayed_recall` + `entity_key_v2`, and
`world_update` + `temporal_chain_v2`, and
`memory_noise_stress` + `key_retention_v2`. Everything else fails closed before
any bot contact or write. Campaign example (PowerShell; historical example
only — no new invocation is authorized by this document):

```powershell
.venv\Scripts\python scripts\run_controlled_campaign.py `
    --results-dir results\stress_controlled_wu_round1 `
    --scenario world_update `
    --seeds 42,43,44 `
    --cell '{"name":"chain3","params":{"update_depth":3,"update_semantics_version":"temporal_chain_v2"}}'
```

The campaign runner validates requested-vs-effective params per cell,
pre-registers the full schedule/manifest (new runs use schema
`controlled-campaign/v4` with producer-source/git provenance), spawns a fresh
mock adapter per run, and
validates each produced result JSON (identity, effective params, fairness,
fixture) fail-closed. The first depth-3 diagnostic is complete and accepted in
`docs/agents/reviews/A-FINAL-015.md`; any further ladder cell still requires a
separate A-issued task.

## 3. Failure Point (definition)

A backend's **failure point** on a scenario is the lowest ladder level where
its formal-phase **task success rate < 80%**. Interpolation between ladder
levels is never allowed; a backend that fails at the lowest non-control level
is marked "fails at first step". No outcome is pre-assumed: the table is
computed from logs only.

Formal V1 applies this rule only to memory noise `10→30→50` and long-lived
memory `L1→L2→L3`. With N=10, 8/10 is not a failure and 7/10 is. Lifetime is
a composite difficulty; its result is not attributed to event count alone.

## 4. Formal statistics

- Primary endpoint: strict evaluator/environment-derived `task_success`.
- Primary active-backend pairs per cell: vector–mem0, vector–letta,
  mem0–letta, paired on seed.
- Test: two-sided exact McNemar; report both discordant directions.
- Effect size: paired risk difference, first named backend minus second.
- CI: paired percentile bootstrap, seed `20260811`, 10,000 resamples, with the
  RNG reset per comparison and linear/R-7 quantiles.
- Multiplicity: Holm-Bonferroni across all 24 pre-registered active-backend
  primary comparisons.
- Report effect sizes and CIs regardless of significance; no global
  leaderboard and no equivalence claim from non-significance.

## 5. Contamination guards (checked per run, audited per campaign)

- Every run log must carry `fairness.valid == true` (controlled variables
  fingerprint + completed-episode reset verification). A run with
  `valid == false` is excluded from statistics **and the exclusion is
  reported** — never silently dropped.
- Stress runs write to an isolated `RESULTS_DIR` (e.g.
  `results/stress_smoke/`, `results/stress_formal/`), never into the classic
  matrix directory.
- `none` must retrieve nothing in every cell; if it ever returns a memory,
  that is a Critical contamination finding.
- Identical planner model, temperature, system-prompt hash, tool-set hash,
  scenario version and params across backends in a cell — read from the
  fairness records, not assumed.

## 6. N/A rules

- Retrieval-layer structured-fact metrics (`current_fact_accuracy`,
  `fact_retrieval_rank`, `recall_accuracy`, `wrong_fact_rate`,
  `retrieval_precision`, `stale_memory_rate`,
  `obsolete_fact_retrieval_rate`) are computed from stable event ids, and the
  letta adapter round-trips the exact event via passage tags (verified live
  against 0.16.8), so they are measured for every backend. An empty retrieval
  is a measured miss (`recall_accuracy = 0`), never silently N/A; a rate that
  is undefined without retrieved items is N/A.
- For `entity_key_v2` delayed-recall cells, the versioned metric set is
  `fact_retrieval_rank`, `target_recall`, `target_retrieval_precision`, and
  `off_target_retrieval_rate`; `recall_accuracy` mirrors `target_recall` for
  schema compatibility, and legacy `wrong_fact_rate` / `retrieval_precision`
  are **N/A** in v2 logs (off-target entities are true facts, never wrong).
  Every v2 metric must be re-derivable from the log's
  `evaluation_ground_truth` plus the step-0 retrieval snapshot.
- For `temporal_chain_v2` world-update cells, the versioned metric set is
  `current_fact_retrieval_rank`, `current_fact_recall` (empty = 0),
  `current_fact_retrieval_precision`, `stale_fact_retrieval_rate`,
  `current_fact_top1`, and `stale_memory_rate` (N/A when undefined);
  `current_fact_accuracy` / `obsolete_fact_retrieval_rate` are compatibility
  mirrors only. All chain facts are true at their event time — "stale" means
  temporally superseded, never wrong.
- Behavioral metrics (`task_success`, `stale_action`, `adaptation_success`,
  `transfer_success_rate`, `preparation_rate`, `failure_repetition_rate`) are
  the primary endpoints and are valid for all backends.
- `failure_transfer` endpoints are N/A for every backend until the scenario
  is redesigned around a real observed failure cause (safety gate, §2).
- N/A is neither a pass nor a failure: excluded from rates, reported as N/A.

## 7. Reporting

All numbers come from run logs; nothing is hand-filled. Required outputs per
campaign: per-cell success/token/latency tables, the failure-point table
(backend × scenario → first failing level), and charts generated from the
logs: success vs noise, recall vs interference, stale rate vs update depth,
token cost vs memory size, retrieval latency vs memory size, transfer success
rate, success vs cost, failure point by backend.
