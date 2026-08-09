# B-COMPLETION-011 — TASK-011 entity_key_v2 treatment complete

Date: 2026-08-08
Author: Agent B (main developer)
Task: `docs/agents/tasks/TASK-011.md` (per HANDOFF §6)
Status: **COMPLETE — awaiting A/C review. No experiment executed.**

Boundaries respected: `docs/protocol.md`, planner serialization, memory
backends/algorithms, runner, fairness hashes, TS, campaign scripts, and
`results/` all untouched; no git operations; no network/Docker/live LLM;
unit tests use fakes only. No production file beyond the allowed scope
(`scenarios/base.py`, `scenarios/delayed_recall.py`) was needed.

## Implementation mapping

1. **Semantics version** — `recall_semantics_version` param on
   `delayed_recall`: `legacy` (default; legacy goal, event semantics,
   metrics, and Controlled event identity unchanged) or `entity_key_v2`; any
   other value raises `ScenarioParamError`. Effective value lands in
   `result.params` (and the fairness `scenario_params`), so outputs cannot be
   pooled silently.
2. **Target identity/goal** — `target_entity_key(seed)`: SHA-256 in a
   dedicated `delayed_recall/entity_key_v2/target/` namespace →
   `cache-<8 hex>`, computed in `setup` before/independent of distractors.
   v2 goal: `Return to cache-… whose location you learned during the initial
   briefing.` (key named, zero coordinates, no labels). Legacy `GOAL`
   unchanged. The v2 diagnostic probe queries the dynamic goal text.
3. **Simultaneously true candidates** — v2 learned fact +
   `similar_distractor_count` facts share actor `scenario-instructor`, type
   `location_discovered`, and context schema `{"entity_key", x, y, z}`.
   Distractor keys: unique deterministic one-character mutations
   (position-major, hex-replacement order; first-N prefix identical for any
   N). Coordinates: unique seeded offsets, target excluded, rejection-sampled
   deterministically. No negative/update/stale/correct/wrong content.
   `interference_count` noise unchanged.
4. **Typed out-of-band ground truth** — `EvaluationGroundTruth` model
   (`semantics_version`, `target_event_id`, `target_entity_key`, ordered
   `distractor_event_ids`) on `ScenarioResult.evaluation_ground_truth`,
   default `None` → old result JSONs validate unchanged. Populated only for
   v2; never enters prompt/memory/query/action paths (P3 test asserts the
   prompt views carry no bookkeeping fields).
5. **Versioned metrics** — `compute_entity_key_metrics` (ids from ground
   truth + causal `run_log.steps[0].retrieved_items`):
   `fact_retrieval_rank`, `target_recall` (empty = 0),
   `target_retrieval_precision` / `off_target_retrieval_rate` (None on
   empty). Legacy keys retained for schema compatibility: `recall_accuracy`
   mirrors `target_recall`; `wrong_fact_rate` and legacy
   `retrieval_precision` are `None` in v2. Legacy `compute_recall_metrics`
   untouched.

## Files changed

- `benchmark/minemembench/scenarios/delayed_recall.py` (v2 treatment)
- `benchmark/minemembench/scenarios/base.py` (`EvaluationGroundTruth` +
  optional result field)
- `benchmark/tests/test_delayed_recall_v2.py` (new, 8 tests)
- `benchmark/tests/test_scenario_params.py` (params include the version key;
  rejection test)
- `docs/stress_design.md`, `docs/experiment_standard.md` (v2 semantics,
  metric names, legacy separation, gating — in place)

## P1–P4 coverage

- **P1 simultaneous truth**: `test_p1_simultaneous_truth_across_seeds_and_levels`
  (seeds 42/43/44 × levels 0/5/20/50: unique keys, unique coordinates, one
  location per key, common neutral schema/actor/type/value types, no label
  tokens) + `test_p1_key_generators_are_deterministic_and_mutation_shaped`.
- **P2 unique visible derivation**: test-only `_oracle(goal, views)` over the
  exact `memory_view_for_prompt` output resolves exactly one location equal
  to the declared target for seeds 42/43/44
  (`test_p2_oracle_uniquely_resolves_the_declared_target`).
- **P3 no hidden cue**: oracle invariant under shuffle/reverse; views contain
  no item/event/episode ids, score, created_at, metadata, or raw events;
  target key identical for distractor counts 0/5/50
  (`test_p3_oracle_invariant_to_order_and_free_of_bookkeeping`,
  `test_p3_target_key_independent_of_distractor_count`).
- **P4 independent re-derivation**: ScenarioResult JSON round-trip +
  recomputation from `evaluation_ground_truth` + step-0 snapshot requires
  exact equality for rank-1 (vector) and empty-retrieval (none) cases;
  target-below-off-target, target-absent, and unknown-id math covered
  directly (`test_p4_metrics_rederive_exactly_from_result_json`,
  `test_p4_metric_math_target_below_off_target_and_absent`).
- Legacy: defaults/goal/metrics unchanged and old JSON loads with
  `evaluation_ground_truth=None`
  (`test_legacy_result_json_without_ground_truth_still_loads`, plus updated
  `test_scenario_params.py` assertions).

## Exact test output

- Focused (task-specified set + v2 file):
  `.venv/Scripts/python -m pytest -q benchmark/tests/test_delayed_recall.py
  benchmark/tests/test_stress_metrics.py benchmark/tests/test_scenario_params.py
  benchmark/tests/test_controlled_mode.py benchmark/tests/test_delayed_recall_v2.py`
  → **71 passed in 5.95s**.
- Full suite: `.venv/Scripts/python -m pytest -q` →
  **268 passed in 76.62s** (259 + 9 new).
- TypeScript: not run — `minecraft/` untouched.

## Deviations

- `default_params` gained `recall_semantics_version`, so `result.params` /
  fairness `scenario_params` now include it (required for pool safety); the
  three existing param-equality tests were updated accordingly.
- No research conclusion is claimed; the gated fresh `(200,20)` smoke belongs
  to C after A's code review, in a new results directory.

---

## A-REVIEW-011 repair appendix (2026-08-08)

Bounded repair only; no scope expansion, no planner/runner/fairness/backend/
protocol/TS/campaign/results/git changes.

1. **H-1 — legacy Controlled identity restored.**
   `_next_event_identity` now branches: `legacy` passes only
   `{"interference_count", "similar_distractor_count"}` to
   `controlled_event_identity` (pre-TASK-011 derivation);
   `entity_key_v2` passes the full versioned params.
   `scenarios/controlled.py` untouched. Verified: legacy 2-param derivation
   yields `ctrl-6342fe1db59ccfbe969df790` — exactly the pre-TASK-011 value
   reproduced in QA-011 §6; v2 yields the distinct
   `ctrl-5ebaf4800733a9eba327e759`.
2. **H-1 regression test** —
   `test_legacy_controlled_identity_keeps_pre_task011_derivation`
   (test_delayed_recall_v2.py): an actual Controlled legacy run's experience
   event equals `controlled_event_identity(seed, two-param dict,
   "experience", 0)` for both id and timestamp; the v2 id matches the
   versioned derivation and differs, timestamp equal.
3. **M-1 — timestamp-independence encoded.**
   `test_p3_oracle_invariant_to_order_and_free_of_bookkeeping` now
   deep-copies the exact `memory_view_for_prompt` views, rewrites every
   timestamp to distinct anti-chronological/adversarial values, and asserts
   the oracle answer is unchanged.
4. **L-1 — wording corrected** in `delayed_recall.py` (module docstring +
   params comment), `docs/stress_design.md`, the legacy test docstring, and
   this report: the guarantee is now "legacy goal text, event semantics,
   metrics, and Controlled event-identity derivation unchanged; old result
   JSON stays loadable" — not whole-file byte-for-byte identity. The earlier
   deviation calling the legacy ID change "acceptable" is removed; it was a
   defect and is now fixed.

Exact test output after repair:

- Focused: `pytest benchmark/tests/test_delayed_recall.py
  test_stress_metrics.py test_scenario_params.py test_controlled_mode.py
  test_delayed_recall_v2.py` → **72 passed in 6.40s**.
- Full: `.venv/Scripts/python -m pytest -q` → **269 passed in 73.92s**
  (268 + 1 new regression; the M-1 extension is inside an existing test).

No files under `results/` changed; no campaign run. Stopping for C
re-verification.
