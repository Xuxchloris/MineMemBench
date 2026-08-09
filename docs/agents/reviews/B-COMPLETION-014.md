# B-COMPLETION-014 — TASK-014 Controlled CLI/campaign generalization complete

Date: 2026-08-08
Author: Agent B (main developer)
Task: `docs/agents/tasks/TASK-014.md` (after A-APPROVAL-013)
Status: **COMPLETE — awaiting C independent QA. NOT an A approval; no
campaign was or may be run.**

Explicit confirmation: no process was spawned, no campaign executed, nothing
written under `results/`, no service/Docker/LLM contact, no git operation,
no `.env` access. TASK-013 Scenario semantics untouched (frozen).

## Files changed (TASK-014 only)

- `benchmark/minemembench/cli.py` — central policy
  (`CONTROLLED_VERSION_PARAM`, `CONTROLLED_APPROVED_VERSIONS`,
  `validate_controlled_policy`); the Controlled gate now runs the policy on
  the scenario's FULL EFFECTIVE params before any bot/LLM/backend contact;
  `--runs 1` rule unchanged.
- `scripts/run_controlled_campaign.py` — `--scenario` (default
  `delayed_recall`, backward compatible); `prepare_campaign` fail-closed
  preflight (cell shape/safe names/duplicates, scenario validation,
  world-update explicit-v2 requirement, single semantics version, unique
  seeds, approved backend subset); `build_schedule` parameterized by
  scenario with requested+effective params and fixture identity per entry;
  manifest `schema_version="controlled-campaign/v2"` + top-level
  `semantics_version`; `_validate_run_result` strict per-run validation
  (exactly one result file; scenario/seed/backend/mode/effective params;
  fairness valid + scenario/params/run_seed/mode/fixture identity), linked
  evidence on failure, stop-without-retry unchanged.
- `benchmark/tests/test_controlled_mode.py` — updated 4 existing tests to
  the new manifest/result contract; +21 Q1–Q5 falsification tests.
- `docs/experiment_standard.md` — in-place capability statement +
  PowerShell example; explicitly no world-update campaign authorized.
- `docs/agents/reviews/B-COMPLETION-014.md` — this report.

## Q1–Q6 mapping

- **Q1 (CLI policy)**: `test_q1_policy_approves_the_three_combinations`
  (delayed legacy, delayed v2, world v2 pass), 
  `test_q1_policy_rejects_unapproved_combinations` (world legacy/missing,
  noise, failure_learning rejected),
  `test_q1_cli_gate_fails_before_any_bot_or_backend` (exit 2 with zero
  backend constructions), plus updated
  `test_controlled_rejects_other_scenarios` and the pre-existing `--runs`
  gate test.
- **Q2 (normalization/preflight)**:
  `test_q2_legacy_cell_requested_vs_effective_params` (requested
  byte-for-byte; effective gains defaults+legacy; command carries only
  requested overrides — no `recall_semantics_version` in the command),
  `test_q2_world_v2_cell_records_requested_and_effective`,
  `test_q2_preflight_rejects_bad_cells_and_inputs` (malformed/extra-key/
  unsafe/duplicate cells, invalid params, mixed delayed semantics,
  missing/legacy world version, duplicate/non-int seeds, empty/duplicate/
  unsupported backends — all exit 2, output path never created).
- **Q3 (scheduling)**: `test_q3_world_update_schedule_preserves_invariants`
  (seed-major, rotation, alternation, scenario/cell identity, fixture
  identity, `--runs 1`), `test_q3_default_delayed_schedule_names_delayed_recall`
  + pre-existing `test_schedule_is_seed_major_counterbalanced_and_precomputed`.
- **Q4 (result validation/lifecycle)**: updated
  `test_campaign_lifecycle_through_fakes` (pending manifest first, fresh
  process per run, valid result advances, links persist) and
  `test_campaign_stops_on_failure_and_keeps_partial_state`; new
  `test_q4_zero_or_two_result_files_fail_closed`,
  `test_q4_invalid_json_fails_closed`, and 10-parametrized
  `test_q4_result_mismatches_fail_closed` (scenario/seed/backend/mode/params/
  missing-fairness/valid=false/run_seed/fixture/scenario_params mismatches).
- **Q5 (hermetic CLI world-update integration)**:
  `test_q5_controlled_world_update_v2_cli_path` — full Controlled CLI path
  with canonical fake bridge/LLM/recording backend: mode, scenario, full
  effective params, fairness/fixture/run_seed, `ctrl-` injected events,
  `TemporalChainGroundTruth` (3 stale + current), causal
  `retrieval_evidence_source`.
- **Q6 (regressions/scope)**: full suite green (below); TASK-013 suite
  untouched and green; unit tests do not depend on gitignored results (the
  only artifact-dependent test is the portable skip/fail one from the
  TASK-013 repair).

## Exact test output

- Focused:
  `.venv\Scripts\python -m pytest -q benchmark/tests/test_controlled_mode.py
  benchmark/tests/test_run_loop.py benchmark/tests/test_world_update.py
  benchmark/tests/test_world_update_v2.py benchmark/tests/test_delayed_recall.py
  benchmark/tests/test_delayed_recall_v2.py benchmark/tests/test_cli.py
  benchmark/tests/test_scenario_params.py` → **108 passed in 9.14s**.
- Full: `.venv\Scripts\python -m pytest -q` → **302 passed in 75.32s**
  (281 + 21 new).
- TypeScript: N/A — `minecraft/` untouched.

## Deviations

- New manifests use schema `controlled-campaign/v2` with explicit
  `requested_params`/`effective_params` entry fields (the old entry field
  `scenario_params` is replaced); historical manifests/results are untouched
  and never rewritten. Old delayed-recall command lines (no `--scenario`)
  produce identical commands, schedule order, log naming, and event identity.
- Controlled delayed-recall legacy event identity is preserved: the CLI
  policy change does not alter the Scenario's frozen two-param derivation.
- One shell heredoc append was truncated mid-file during test authoring;
  the truncation was detected immediately, the partial block removed, and
  the content re-appended with the file tools. Final file verified by the
  green focused/full runs above.
- No research conclusion claimed; A release is required before C runs any
  world-update campaign.

---

## A-REVIEW-014 repair appendix (2026-08-08, repair cycle)

Exactly the three authorized files changed: `scripts/run_controlled_campaign.py`,
`benchmark/tests/test_controlled_mode.py`, this report. No CLI policy,
scenario, results, protocol, service, or git changes. C's prior accidental
live probe was NOT repeated — every verification below is hermetic (fakes /
module monkeypatch only); no process, network, or LLM call occurred.

1. **High — semantic duplicate cells rejected.** `prepare_campaign` now
   computes a canonical signature
   `json.dumps({"scenario": ..., "effective_params": ...}, sort_keys=True,
   separators=(",", ":"))` per cell and rejects a second cell with the same
   signature, naming BOTH labels, before any write/spawn. Catches identical
   raw params and omitted-vs-explicit-default equivalence; distinct
   effective cells still pass. Tests:
   `test_q2_preflight_rejects_semantically_duplicate_cells`,
   `test_q2_preflight_rejects_omitted_vs_explicit_default_duplicate`,
   `test_q2_distinct_effective_cells_are_accepted`, plus schedule-level
   `test_q4_schedule_run_identities_are_unique` (uniqueness over
   `(scenario, canonical effective params, seed, backend)` for both
   scenarios).
2. **Medium — late-bound dependencies.** `run_campaign`'s
   `spawn_bot`/`await_health`/`invoke_run` parameters now default to None
   and resolve to the CURRENT module functions at call time, so module-level
   monkeypatching before a normal `campaign.main` is effective; explicit
   kwargs still override and production defaults are unchanged. Test:
   `test_q4_main_with_module_level_monkeypatch_runs_only_fakes` — a normal
   `main()` run with monkeypatched module helpers: exactly one fake spawn
   (terminated), one fake invoke writing a valid agreeing result, rc 0,
   manifest `status=ok`; no real process/network.
3. **Low — narrower preflight catch.** The Scenario-normalization catch is
   now `(ScenarioRegistryError, ScenarioParamError, ValueError)`; unexpected
   implementation defects crash loudly instead of masquerading as user-input
   rejections.
4. Bonus hardening (QA-014 note): the Q4 mismatch parametrization now also
   covers `fairness.scenario` and `fairness.campaign_mode` mismatches.

Exact verification after repair:

- Focused: `.venv\Scripts\python -m pytest -q benchmark/tests/test_controlled_mode.py
  benchmark/tests/test_run_loop.py benchmark/tests/test_world_update.py
  benchmark/tests/test_world_update_v2.py benchmark/tests/test_delayed_recall.py
  benchmark/tests/test_delayed_recall_v2.py benchmark/tests/test_cli.py
  benchmark/tests/test_scenario_params.py` → **115 passed in 8.96s**.
- Full: `.venv\Scripts\python -m pytest -q` → **309 passed in 77.87s**
  (302 + 7 new).
- TypeScript: not rerun — `minecraft/` untouched.

Stopping for C re-verification; no A approval claimed.
