# B-COMPLETION-007 — TASK-007 planner-leakage removal complete

Date: 2026-08-08
Author: Agent B (main developer)
Task: `docs/agents/tasks/TASK-007.md` (per A-FINAL-006)
Status: **COMPLETE — awaiting A review.**

No campaign run, no git operations, `docs/protocol.md` / `results/` /
`minecraft/` untouched (TS suite therefore not re-run — no TS changes; last
full TS run 31 passed under TASK-005).

## Implementation

1. **Backend-neutral planner memory serializer** — new
   `agent/planner.py::memory_view_for_prompt(item)`: each retrieved memory
   reaches the prompt as `{"event": {actor, target, event_type, location,
   context, outcome}}` — semantic event fields only, in retrieved order.
   Excluded: `item_id`, `score`, `created_at`, `metadata`, event
   `event_id`, `episode_id`, `timestamp`, `raw_events`. Used for every
   backend and every mode (shared serializer, no backend-name branching).
   `RunStep.retrieved_items` still records the exact full
   `MemoryItemSnapshot`; the neutral view never feeds metrics.
2. **Controlled distractor neutralization** — in
   `delayed_recall.interference_phase`, when `campaign_mode == "controlled"`,
   target-location distractors are written with the learned fact's exact
   actor (`scenario-instructor`), event type (`location_discovered`), and
   context key set (`{subject, x, y, z}`); the `wrong location` /
   `used to be located here` notes are dropped. Candidates differ only in
   coordinates and retrieval order.
3. **Ground truth unchanged** — `target_event_id` / `wrong_fact_ids` remain
   out-of-band id ground truth; metrics re-derive from logged snapshots; ids
   never reach the prompt (verified by test).
4. **Native mode preserved** — the neutralization is gated on Controlled
   mode; native distractors keep their environment actor and notes
   (regression-tested). The shared prompt serializer applies to native too,
   as the task permits ("required for fairness").

## Modified files

- `benchmark/minemembench/agent/planner.py` (serializer + prompt wiring)
- `benchmark/minemembench/scenarios/delayed_recall.py` (controlled
  neutralization + docstring)
- `benchmark/tests/test_planner.py` (updated happy-path assertions; +2 tests:
  exact neutral view fields/banned keys, retrieved-order preservation)
- `benchmark/tests/test_controlled_mode.py` (+3 tests: controlled candidates
  structurally identical/unlabeled/distinct-coords/stable-ids, native labels
  preserved, RunStep full raw snapshot retained)

## Exact test output

- Focused (planner + controlled + all scenario suites): **77 passed in
  14.09s**.
- Full Python: `.venv/Scripts/python -m pytest -q -p no:cacheprovider` —
  **256 passed in 88.23s** (251 + 5 new).
- TypeScript: not run — `minecraft/` untouched (suite was 31 passed at
  TASK-005; no TS changes since).

## Deviations

- The prompt's memory JSON shape changed for ALL modes (shared neutral
  serializer), so native-mode prompts lose ids/scores/timestamps too — this
  is the fairness-required part the task explicitly allows; scenario
  semantics, goals, success rules, and backend algorithms are unchanged.
- The pre-fix round (`results/stress_controlled_round2_200_20/`) was not
  touched; per A-FINAL-006 it stays as ceiling evidence, never pooled with
  the corrected version.
- Stopping for A review; no `(200,20)` re-run performed (C owns it after
  release).
