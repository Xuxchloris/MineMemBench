# B-COMPLETION-004 — TASK-004 Controlled Mode harness complete

Date: 2026-08-08
Author: Agent B (main developer)
Task: `docs/agents/tasks/TASK-004.md` (per A-RESEARCH-REVIEW-004)
Status: **COMPLETE — awaiting A review. C remains blocked until release.**

No changes to `docs/protocol.md`, `results/` (incl. `results/stress_round1/`),
no 24-run campaign, no new framework, no git operations. The only real
end-to-end run was a single permitted mock smoke in a temp directory.

## Required behavior → implementation

1. **Campaign mode identity** — `FairnessRecord.campaign_mode` and
   `ScenarioResult.campaign_mode` (`"native"` default / `"controlled"`), plus
   `--campaign-mode` on the CLI. Old native logs parse unchanged (defaults);
   the two outputs cannot be mixed silently.
2. **Fresh mock process per run, fail closed** —
   `scripts/run_controlled_campaign.py` starts a fresh `BOT_MOCK=1` adapter
   process (own free port) for EVERY run and terminates it afterwards; the
   CLI (`cli._assert_controlled_fixture`) refuses controlled runs unless
   health reports `mock` AND the observed initial state is the canonical
   fixture (spawn `(0,64,0)`, overworld, `time_of_day=6000`, clear). The
   fixture identity string (`cli.CONTROLLED_FIXTURE_IDENTITY`) is recorded in
   the fairness record. Controlled mode is restricted to
   `delayed_recall`, `--runs 1` (fresh process per run is owned by the
   campaign runner).
3. **Timestamp normalization** — `agent/planner.py::_build_user_message`
   serializes `WorldState` with `exclude={"timestamp"}` (identical for every
   backend/mode; documented in the docstring). No hand-coded actions.
4. **Raw state per decision** — `RunStep.world_state` stores the exact
   unnormalized observed `WorldState` (timestamp included).
5. **Deterministic controlled events** — new `scenarios/controlled.py`
   (`controlled_event_identity`): event id = SHA-256 over
   `(seed, effective params, phase, ordinal)`, logical timestamp from a fixed
   epoch + phase slot + ordinal. `DelayedRecallScenario` uses it when
   `ctx.campaign_mode == "controlled"`; actor/type/context/outcome/order are
   identical across backends, only `episode_id` differs. Native mode keeps
   uuid4 + wall clock. Controlled mode also skips the raw-stream
   `EventCollector` (its mapped events carry wall-clock/uuid identity and
   would break the identical-inputs invariant) — documented in `cli.py`.
6. **Offered-event retention** — new `memory/base.py::EventRecordingBackend`
   (pass-through proxy; no backend-name behavior) records every
   `add`/`update` event; the CLI copies it into
   `ScenarioResult.injected_events` for every run including `none`.
7. **Campaign runner** — `scripts/run_controlled_campaign.py`: precomputed
   seed-major schedule with Latin-square counterbalanced backend order and
   alternating cell order; manifest (order, commands, expected health mode,
   seeds, params, output dir) written BEFORE execution and rewritten after
   every run; on any failure the run is marked `failed` with its return code
   and the runner STOPS — no retry/replace.
8. **Unit tests** — new `benchmark/tests/test_controlled_mode.py` (15 tests):
   deterministic semantic events across backends/scopes, native mode
   unchanged, NoMemory inputs retained (11 events), RunStep raw state
   retained, planner prompt excludes timestamp (two states differing only in
   timestamp → identical prompt), CLI fail-closed on native health and on a
   drifted fixture, `--runs>1`/wrong-scenario rejection, controlled run
   records mode/fixture/inputs and skips the collector, counterbalanced
   rotation covers every position, seed-major precomputed schedule, campaign
   lifecycle through fakes (manifest all-pending before first invocation,
   per-run spawn/terminate), stop-on-failure keeps partial state.

## Files

Production: `agent/planner.py`, `cli.py`, `core/fairness.py`,
`core/runner.py`, `memory/base.py`, `scenarios/base.py`,
`scenarios/controlled.py` (new), `scenarios/delayed_recall.py`,
`scripts/run_controlled_campaign.py` (new).
Tests: `benchmark/tests/test_controlled_mode.py` (new).
No doc/spec files changed; no results touched.

## Exact verification

- Full Python: `.venv/Scripts/python -m pytest -q -p no:cacheprovider` —
  **247 passed in 86.62s** (232 + 15 new).
- TypeScript: `cd minecraft && npx vitest run` — **31 passed (3 files),
  958 ms** (TS side untouched; mock fixture already canonical per process).
- Mock process smoke (permitted, temp dir only):
  `scripts/run_controlled_campaign.py --results-dir $(mktemp -d) --seeds 42
  --backends none --cell '{"name":"control","params":{"interference_count":10,
  "similar_distractor_count":0}}'` → **exit 0**, one fresh node mock process
  spawned/terminated. Evidence (temp dir
  `C:\Users\30573\AppData\Local\Temp\tmp.KDQgIiNNYv`):
  `campaign_mode=controlled`, `fixture_identity=mock-fixture-v1: ...`,
  `fairness.valid=true`, `reset_performed=true`, `post_reset_items=0`,
  `fresh_scope_items=0`, `run_seed=42`; 11 `injected_events`, all
  `ctrl-` ids, logical timestamps `2026-01-01T00:00:00Z`.. monotone, all
  scoped to the run's episode; `run_log.steps[0].world_state` retained with
  raw timestamp; `retrieved_items=[]` for `none` with
  `recall_accuracy=0` (measured miss); manifest `status=ok`,
  `health_mode=mock`, real per-run port recorded.

## Deviations / blockers

- Controlled mode is deliberately restricted to `--scenario delayed_recall
  --runs 1` (fail-closed exit 2 otherwise) so every run gets a fresh
  canonical fixture; the campaign runner owns multi-run schedules.
- The raw-stream event collector is skipped in Controlled Mode only
  (identity invariant); native runs are byte-for-byte unchanged in behavior.
- ` FairnessRecord.minecraft_version/world_seed` still reflect settings
  (`unknown`/null); Controlled Mode records the explicit
  `fixture_identity` instead, per the review's minimum correction.
- No docs beyond this report were updated (the `--help` text documents the
  new flag; `docs/experiment_standard.md` revision is A's call).
- Stopping here; C waits for A's release.

---

## TASK-005 correction appendix (2026-08-08, A-REVIEW-004 rework)

Only the four A-REVIEW-004 minimum fixes were made; no campaign was run, no
protocol/results/git changes.

1. **Critical — output-dir gate.** `run_controlled_campaign.py::main` now
   fails with exit 2 BEFORE any write unless the output path is absent or a
   completely empty directory. Never auto-deletes or resumes. Regression:
   `test_campaign_rejects_non_empty_output_dir_without_mutation` (sentinel
   file and existing-file path both rejected, bytes untouched, no manifest
   written).
2. **High — campaign-local stores.** The manifest pre-registers
   `stores.vector_db_path` / `stores.mem0_qdrant_path` inside the campaign
   directory; every invocation runs with `RESULTS_DIR`, `VECTOR_DB_PATH`,
   `MEM0_QDRANT_PATH` pinned there (`_campaign_env`). Historical stores are
   never read or written. Regression: `test_campaign_env_pins_campaign_local_stores`.
3. **High — retained per-run diagnostics.** Every schedule entry
   pre-registers `log_stdout`/`log_stderr`; the real `_invoke_run` redirects
   both streams there; after each run the produced `scenario_*.json` path(s)
   are linked into `result_files`. Failure still stops the campaign, with the
   log paths printed and preserved; no retry. Regressions:
   `test_invoke_run_retains_stdout_and_stderr` (real subprocess, streams and
   env verified), lifecycle test now asserts pre-registered log paths and
   per-run result-file linking.
4. **Medium — complete fixture gate.** `cli.canonical_fixture_state()`
   mirrors `minecraft/src/mock.ts` field-for-field (captured from a live
   `BOT_MOCK=1` adapter); `_assert_controlled_fixture` now compares the
   COMPLETE normalized initial WorldState (everything except the observation
   timestamp: mode, username, vitals, orientation, inventory, equipment,
   entities, players) and reports the differing fields. Regression:
   `test_controlled_fixture_gate_covers_inventory_and_entities` (inventory
   drift caught with position/time intact), existing position-drift and
   native-health gates updated to the full comparison.

Exact verification after the corrections:

- Focused: `pytest benchmark/tests/test_controlled_mode.py` — **19 passed**
  (15 + 4 new).
- Full Python: `.venv/Scripts/python -m pytest -q -p no:cacheprovider` —
  **251 passed in 94.46s** (247 + 4).
- TypeScript: `cd minecraft && npx vitest run` — **31 passed (3 files)**.
- Real-fixture gate check (single controlled CLI run against a real
  `BOT_MOCK=1` process, temp RESULTS_DIR; NOT the campaign): exit 0,
  `fairness_valid=True` — the complete-state gate accepts the genuine fresh
  fixture. One earlier invocation of this check mis-set `RESULTS_DIR`
  (shell backgrounding), which wrote one scenario JSON into the repo root;
  it was verified untracked and deleted immediately; `results/` untouched
  throughout.

Stopping for A review; C remains blocked until release.
