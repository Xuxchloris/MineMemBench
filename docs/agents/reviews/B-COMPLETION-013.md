# B-COMPLETION-013 — TASK-013 world-update temporal-chain v2 complete

Date: 2026-08-08
Author: Agent B (main developer)
Task: `docs/agents/tasks/TASK-013.md` (per A-FINAL-012)
Status: **COMPLETE — awaiting C independent QA. No campaign executed.**

Boundaries respected: planner, runner, CLI, fairness, memory backends,
registry, `scenarios/controlled.py`, campaign scripts, TS, protocol, and
`results/` untouched; no git operations; no Docker/live LLM/campaign; all
new tests hermetic. Production scope stayed inside the allowed three files.

## Files changed

Production:
- `benchmark/minemembench/scenarios/base.py` — `EvaluationGroundTruth`
  refactored into a discriminated union on `semantics_version`:
  `EntityKeyGroundTruth` (`entity_key_v2`, serialized shape identical to
  round 5) + `TemporalChainGroundTruth` (`temporal_chain_v2`:
  `entity_key="supply_cache"`, ordered `stale_event_ids`,
  `current_event_id`). Field stays optional/default None.
- `benchmark/minemembench/scenarios/delayed_recall.py` — typed-member rename
  only (`EntityKeyGroundTruth`); no behavior/JSON/metric change.
- `benchmark/minemembench/scenarios/world_update.py` — v2 treatment
  (params, mode gate, neutral chain events, controlled identity, causal
  metrics, v2 evaluate path).

Tests: `benchmark/tests/test_world_update_v2.py` (new, 10 tests);
`benchmark/tests/test_scenario_params.py` and
`benchmark/tests/test_stress_scenarios.py` (params dicts now include
`update_semantics_version`).

Docs: `docs/stress_design.md`, `docs/experiment_standard.md` (in place).

## Requirement mapping

1. **Version + mode gate** — `update_semantics_version`: `legacy` default /
   `temporal_chain_v2`; other values rejected with `ScenarioParamError`.
   `setup()` fails closed when `campaign_mode="controlled"` and the value is
   not v2 (test: `test_controlled_mode_fails_closed_for_legacy`). Effective
   params logged in `result.params`.
2. **Temporal-chain semantics** — depth 3 → A→B→C→D, prefix-stable seeded
   locations; all candidates: actor `scenario-instructor`, type
   `WORLD_FACT_UPDATED` (including A), context exactly
   `{"subject":"supply_cache","x","y","z"}`, unique coordinates, strictly
   increasing semantic timestamps; no `moved`/index/stale/current labels.
   v2 goal: "Retrieve the supply cache at its current location."
3. **Controlled identity** — chain and noise events use
   `controlled_event_identity` with full effective params + per-phase
   ordinals; `scenarios/controlled.py` untouched. Stream equality across
   NoMemory/Vector proven for seeds 42/43/44 modulo `episode_id`
   (`test_controlled_v2_streams_identical_across_backend_scopes`).
4. **Typed union** — as above; round-4 (12 files) load with
   `evaluation_ground_truth=None`, round-5 (12 files) load with
   `EntityKeyGroundTruth` (`test_p6_round4_and_round5_result_files_still_load`).
   Ground truth is written to the result after the run only; never enters
   memory/goal/query/prompt/action paths (P3 asserts prompt views carry no
   bookkeeping fields).
5. **Causal v2 metrics** — `compute_temporal_chain_metrics` from typed
   ground truth + `run_log.steps[0].retrieved_items`:
   `current_fact_retrieval_rank`, `current_fact_recall` (empty=0),
   `current_fact_retrieval_precision`, `stale_fact_retrieval_rate`,
   `current_fact_top1`, `stale_memory_rate`; compat mirrors
   `current_fact_accuracy` (=top1) and `obsolete_fact_retrieval_rate`
   (=stale rate); `retrieval_evidence_source` logged; behavior metrics
   `stale_action` / `final_distance_to_current`; diagnostic probe uses the
   v2 goal and feeds no metric. Legacy `compute_update_metrics` and legacy
   evaluate path byte-identical in behavior.
6. **Falsification tests (P1–P6)** —
   - P1 `test_p1_temporal_validity_across_seeds_and_depths` (42/43/44 ×
     depths 1–4: unique coords, common schema/actor/type, strictly
     increasing unique timestamps, ordered stale ids + current id, no
     banned labels).
   - P2 `test_p2_oracle_selects_unique_newest_as_current` (test-only oracle
     over exact `memory_view_for_prompt` views picks the unique max
     timestamp = declared current location, seeds 42/43/44, depth 3).
   - P3 `test_p3_oracle_time_is_the_only_cue` (permutation/reversal
     invariance; equal timestamps → ambiguity None; a different candidate
     given the unique newest timestamp is selected; no ids/scores/metadata
     in views).
   - P4 `test_p4_metrics_rederive_exactly_from_result_json` (JSON
     round-trip exact recompute: vector depth-3 stale-top-1 and NoMemory
     empty cases) + `test_p4_metric_math_rank1_absent_and_noise_only`
     (rank 1, D absent with stale, noise-only).
   - P5 `test_p5_metrics_come_from_causal_snapshot_not_probe`
     (FlipFlopBackend: probe sees nothing, logged metrics still describe
     the causal snapshot — rank 4, recall 1, stale_action 1).
   - P6 `test_p6_legacy_behavior_unchanged` (legacy goal/metrics/no ground
     truth) + round-4/5 file loading above; delayed-recall suite intact
     (full run below).

## Exact commands and output

- Focused:
  `.venv/Scripts/python -m pytest -q benchmark/tests/test_world_update.py
  benchmark/tests/test_world_update_v2.py benchmark/tests/test_delayed_recall.py
  benchmark/tests/test_delayed_recall_v2.py benchmark/tests/test_scenario_params.py
  benchmark/tests/test_stress_scenarios.py benchmark/tests/test_stress_metrics.py
  benchmark/tests/test_controlled_mode.py` → **90 passed in 13.06s**.
- Full: `.venv/Scripts/python -m pytest -q` → **279 passed in 83.74s**
  (269 + 10 new).
- TypeScript: not run — `minecraft/` untouched.

## Deviations

- `world_update.default_params` gained `update_semantics_version`, so
  `result.params` / fairness `scenario_params` include it; the two existing
  param-equality tests were updated. Controlled `ctrl-` world-update ids are
  new (v2-only treatment; legacy Controlled is gated off), so no prior
  Controlled identity is altered.
- The v2 Controlled CLI/campaign runner remains delayed-recall-only by
  design; generalizing it is explicitly a later task — no world-update
  campaign was or may be run yet.
- No research conclusion claimed.

---

## A-REVIEW-013 repair appendix (2026-08-08, second repair cycle)

Exactly two repairs; no other production change. Prior sections unchanged.

1. **F-2 (Medium) — entity_key type-enforced.**
   `scenarios/base.py`: `TemporalChainGroundTruth.entity_key` is now
   `Literal["supply_cache"] = "supply_cache"`; any other value raises
   Pydantic `ValidationError`. No other production behavior changed
   (production already always wrote `supply_cache`; metric math never reads
   the field). Negative test added:
   `test_temporal_chain_ground_truth_enforces_entity_key` (accepts
   `"banana"` → ValidationError; default construction still yields
   `supply_cache`).
2. **F-1 (High) — portable evidence test.**
   `test_p6_round4_and_round5_result_files_still_load` now skips explicitly
   (`pytest.skip`) only when BOTH artifact sets are absent (clean checkout);
   a partial/absent single set or any count ≠ 12 still fails. Local 12+12
   validation logic unchanged. New hermetic proof:
   `test_p6_evidence_test_skips_when_both_artifact_sets_absent` monkeypatches
   `glob.glob` to empty and asserts the `Skipped` outcome — the real local
   results are never moved/deleted/copied.

Exact verification after repair:

- Focused TASK-013 set (from this report):
  `.venv/Scripts/python -m pytest -q benchmark/tests/test_world_update.py
  benchmark/tests/test_world_update_v2.py benchmark/tests/test_delayed_recall.py
  benchmark/tests/test_delayed_recall_v2.py benchmark/tests/test_scenario_params.py
  benchmark/tests/test_stress_scenarios.py benchmark/tests/test_stress_metrics.py
  benchmark/tests/test_controlled_mode.py` → **92 passed in 12.83s**.
- Full: `.venv/Scripts/python -m pytest -q` → **281 passed in 82.89s**
  (279 + 2 new).
- Hermetic absence path: included above
  (`test_p6_evidence_test_skips_when_both_artifact_sets_absent` passes inside
  both runs; uses monkeypatched glob only — no filesystem mutation of
  `results/`).
- Strict read-only current-workspace gate (requires exactly 12+12), in the
  repo's actual Windows PowerShell form:
  ```powershell
  @'
  import glob, json
  from minemembench.scenarios.base import EntityKeyGroundTruth, ScenarioResult
  r4 = sorted(glob.glob("results/stress_controlled_round4_temporal_200_20/scenario_*.json"))
  r5 = sorted(glob.glob("results/stress_controlled_round5_entity_key_v2_200_20/scenario_*.json"))
  assert len(r4) == 12 and len(r5) == 12
  for p in r4:
      assert ScenarioResult.model_validate(json.load(open(p, encoding="utf-8"))).evaluation_ground_truth is None
  for p in r5:
      gt = ScenarioResult.model_validate(json.load(open(p, encoding="utf-8"))).evaluation_ground_truth
      assert isinstance(gt, EntityKeyGroundTruth) and gt.target_event_id and gt.target_entity_key
  print("STRICT 24-FILE VALIDATION: 12 round4 (ground_truth=None) + 12 round5 (EntityKeyGroundTruth) — ALL PASS")
  '@ | .venv\Scripts\python -
  ```
  Output: `STRICT 24-FILE VALIDATION: 12 round4 (ground_truth=None) + 12
  round5 (EntityKeyGroundTruth) — ALL PASS`.

Files changed in this cycle: `benchmark/minemembench/scenarios/base.py`,
`benchmark/tests/test_world_update_v2.py`, this report. Nothing under
`results/`, no git operations, no live services/campaign. A's Low finding
(native v2 wall-clock collision) intentionally not addressed — tracked for a
later task per A-REVIEW-013.
