# B-COMPLETION-009 — TASK-009 event-time semantics + template fingerprint

Date: 2026-08-08
Author: Agent B (main developer)
Task: `docs/agents/tasks/TASK-009.md` (per A-FINAL-008)
Status: **COMPLETE — awaiting A/C review.**

No campaign run, no git operations; `docs/protocol.md`, `results/`,
`minecraft/`, backend algorithms, scenario facts/goal/success rule, model,
temperature, and tools all untouched.

## Implementation

1. **Event timestamp restored in the prompt view** —
   `agent/planner.py::memory_view_for_prompt` now emits the semantic
   `ExperienceEvent.timestamp` (as `isoformat()` JSON value) inside the
   `event` object. Still excluded: `item_id`, event `event_id`,
   `episode_id`, `score`, `created_at`, `metadata`, `raw_events`. Retrieval
   order preserved. In Controlled Mode these timestamps are deterministic
   across backends, so "learned ... at the start of this episode" is
   resolvable from equal semantic data.
2. **Deterministic template fingerprint** — new
   `agent/planner.py::PLANNER_USER_TEMPLATE_HASH`: SHA-256 over
   `{user_section_labels, memory_view_fields}` (sorted-keys JSON of the
   static material). The section-label constants `_USER_SECTION_LABELS` are
   what `_build_user_message` actually uses, and
   `memory_view_for_prompt` builds its view from `MEMORY_VIEW_FIELDS`, so
   any template/schema change flips the hash; no dynamic goal, state,
   transcript, memory, id, wall time, or secret is hashed.
3. **Fairness population** — `FairnessRecord.planner_user_template_hash:
   str | None = None` (optional, backward-compatible), populated from the
   constant in `_base_record` on every new run. Existing
   `system_prompt_hash` / `tool_set_hash` untouched.
4. No other behavior changed.

## Modified files

- `benchmark/minemembench/agent/planner.py`
- `benchmark/minemembench/core/fairness.py`
- `benchmark/tests/test_planner.py` (view test updated for timestamp;
  +2 fingerprint tests)
- `benchmark/tests/test_fairness.py` (populated-hash assertion; +1
  backward-compat test)

## Exact test output

- Focused: `pytest benchmark/tests/test_planner.py test_fairness.py
  test_controlled_mode.py test_run_loop.py` — **50 passed in 2.45s**.
- Full Python: `.venv/Scripts/python -m pytest -q -p no:cacheprovider` —
  **259 passed in 90.75s** (256 + 3 new).
- TypeScript: not run — `minecraft/` untouched.

## Acceptance mapping

- Prompt-view test proves `timestamp` present (`isoformat()` value) and all
  banned fields absent (`test_memory_view_for_prompt_strips_all_nonsemantic_fields`).
- Hash stability: recompute-from-material equality, 64-hex
  (`test_planner_user_template_hash_is_stable_and_64_hex`); sensitivity:
  schema or label change flips it
  (`test_planner_user_template_hash_changes_with_schema_or_template`).
- Fairness: new records carry the 64-hex fingerprint; a record JSON without
  the field still validates to `None`
  (`test_fairness_record_without_template_hash_still_validates`).

## Deviations

- None against the task spec. Rounds 2/3 results untouched and unpooled, per
  A-FINAL-008; the `(200,20)` re-run belongs to C after release.
