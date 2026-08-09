# B-COMPLETION-002 — TASK-002 implementation complete

Date: 2026-08-08
Author: Agent B (main developer)
Task: `docs/agents/tasks/TASK-002.md` — Agent B implementation task
Status: **COMPLETE — awaiting A review. No git add/commit/push performed;
no formal experiment matrix run; `docs/protocol.md` untouched.**

## Disposition of the interrupted four-file draft

| file | disposition |
|---|---|
| `cli.py` | **Kept** (items 1+2): paired seed schedule, per-run backend instance, post-run reset-audit wiring. |
| `core/fairness.py` | **Kept** (item 2): completed-episode reset + reset-scope/fresh-scope probes + auditable invalid records. |
| `memory/letta_adapter.py` | **Kept, trimmed** (item 5): the passage-tag payload design. The draft's `server_version` stats probe and `_client_injected` flag were **reverted** — not required by TASK-002. |
| `scenarios/base.py` | **Kept, trimmed** (item 7): full-field probe evidence. The draft's `ScenarioResult.backend_extra` field was **reverted** — not required by TASK-002. |

A's new files `A-AUDIT-002.md` / `TASK-002.md` are untouched; no shared
worktree changes were discarded.

## Required behavior → implementation

1. **Paired independent seeds** — `cli.py::_run_scenario_async`: run `i` uses
   `args.seed + i`; effective seed recorded in `ScenarioResult.seed` and
   `FairnessRecord.run_seed`. `--seed` help text documents the schedule.
2. **Real reset audit** — `core/fairness.py` rewritten: after metrics are
   captured the checker resets the COMPLETED episode id, probes the reset
   scope and a brand-new scope with the run's own content query, and
   best-effort resets both probed scopes again (drops lazily-created empty
   letta agents). Any reset error / probe error / returned item →
   `valid=False` with an auditable `invalid_reason`; the run log is always
   written. CLI now builds a **fresh backend instance per run** (latency
   counters and process scope never accumulate). Old pre-run
   cross-episode leak probe removed; all old fairness tests rewritten to the
   new contract.
3. **Behavior-causing retrieval evidence** — new
   `memory/base.py::MemoryItemSnapshot` (item_id, score, created_at,
   metadata, full `ExperienceEvent`); `RunStep.retrieved_items` snapshots the
   exact planner retrieval per decision (`core/runner.py`;
   `retrieved_memory_count` kept as summary). No prompts/secrets stored.
   delayed_recall headline metrics use `run_log.steps[0].retrieved_items`;
   the evaluation-time probe survives as `retrieval_probes` with phase
   `evaluate-diagnostic`, feeding no metric; metric
   `retrieval_evidence_source` records the source.
4. **Backend-neutral ground truth** — `DelayedRecallScenario` retains
   `target_event_id` and `wrong_fact_ids`; `compute_recall_metrics` matches
   on stable event ids only. Empty retrieval → `recall_accuracy=0` (measured
   miss); undefined rates → N/A. No backend-name branches anywhere (grep
   verified: only a docstring mention in `memory/base.py`).
5. **Letta semantic round-trip** — every passage carries
   `event_payload=<event.model_dump_json()>` as a tag (tags round-trip
   verbatim, never embedded; `[event_id=...] ` text prefix kept for
   `update()` lookup and as fallback for payload-less passages).
   Reconstruction order: tag payload → metadata payload → prefix fallback.
   Verified live against 0.16.8 (below).
6. **Strict live verifier** — `scripts/verify_letta_live.py --require-live`
   exits 2 when the server is unavailable; default lenient SKIP behavior
   unchanged (exit 0). Checks A/B now assert exact event equality
   (event_id, episode_id, actor, target, event_type, context, outcome) and
   absence of stale outcomes.
7. **Raw evidence schema** — probe items and per-step evidence share
   `MemoryItemSnapshot` (full MemoryItem + ExperienceEvent fields);
   `RetrievalProbeItem` kept as an alias. Consumers/tests updated.
8. **Safety gate** — `failure_transfer` removed from
   `scenarios/registry.py::_SCENARIOS` (not selectable via `--scenario`),
   module docstring marked SUSPENDED/research-invalid; documented N/A in
   `README.md`, `docs/experiment_standard.md`, `docs/stress_design.md`. No
   redesign attempted. `docs/protocol.md` unchanged.

## Files modified

Production: `benchmark/minemembench/cli.py`, `core/fairness.py`,
`core/runner.py`, `memory/base.py`, `memory/letta_adapter.py`,
`scenarios/base.py`, `scenarios/delayed_recall.py`,
`scenarios/failure_transfer.py` (docstring only), `scenarios/registry.py`,
`scripts/verify_letta_live.py`.

Tests: `benchmark/tests/test_fairness.py` (rewritten), `test_run_loop.py`
(new), `test_delayed_recall.py`, `test_stress_metrics.py`,
`test_letta_adapter.py`, `test_stress_scenarios.py`,
`test_memory_noise_stress.py`, `test_failure_transfer.py`.

Docs: `README.md`, `docs/experiment_standard.md`, `docs/stress_design.md`,
`docs/letta_live.md`.

## Test results (exact)

- `.venv/Scripts/python -m pytest -q -p no:cacheprovider`:
  **230 passed in 90.83s** (baseline was 222; +8 net new: run-loop contract
  tests, fairness rewrite, id-metric tests incl. text-shaped events,
  letta tag/legacy-fallback tests, first-step-evidence test).
- `cd minecraft && npm test`: **31 passed (3 files), 924 ms** — TS side
  untouched.
- Strict live (real Letta server 0.16.8, `scripts/verify_letta_live.py
  --require-live`), exit code 0:

```
letta server: http://localhost:8283 version=0.16.8
PASS  A: add then retrieve round-trips the exact event  all identifying fields equal
PASS  B: update round-trips the exact new event  all identifying fields equal; stale location-A items: none
PASS  C: reset isolates the old episode from a fresh one  reset episode retrieval: 0 item(s), fresh episode retrieval: 0 item(s)
PASS: M15A live verification
```

- Strict negative path: `LETTA_BASE_URL=http://127.0.0.1:9 ... --require-live`
  → prints SKIP + FAIL, **exit 2**; without the flag → SKIP, **exit 0**.
- The tag design was additionally probed live during development: a ~1.6 KB
  event payload round-trips byte-exact through passage tags on the real
  server; probe agents were deleted afterwards.

Focused acceptance tests (all green):
`benchmark/tests/test_run_loop.py` (seeds 42/43/44, identical schedule
across backends, fresh backend per run, completed-id reset, invalid cleanup
still audited to disk); `test_delayed_recall.py::test_no_memory_cannot_recall`
(empty actual retrieval → recall_accuracy=0);
`test_delayed_recall.py::test_headline_metrics_come_from_the_first_decisions_retrieval`
(planner retrieval saved == metric input); `test_stress_metrics.py`
(id metrics with exact and text-shaped events);
`test_letta_adapter.py` (exact tag round-trip + legacy prefix fallback).

## Deviations / blockers

- **failure_transfer endpoints: N/A (blocker confirmed).** The current
  protocol/world fixture cannot produce a real, observable missing-tool
  failure cause (virtual tool gates; no equipment precondition in
  `ActionResult`), so per the task the scenario is deregistered and its
  endpoints reported N/A rather than redesigned here.
- `world_update` / `memory_noise_stress` metric math was left unchanged
  (out of TASK-002 scope); their probes now record full-field evidence.
- Docker image pinning / compose digests (TASK-001 medium) not in TASK-002
  scope — untouched; Docker CLI remains absent from this PATH (compose
  health N/A for B, as before).
- `docs/development_plan.md` still missing; not invented.
- No `results/` logs were added, modified, or deleted.

---

## TASK-003 correction appendix (2026-08-08, A-REVIEW-002 rework)

Only the two A-REVIEW-002 findings were touched; nothing else changed.

1. **High — `fact_retrieval_rank` now ranks the correct fact only.**
   `delayed_recall.py::compute_recall_metrics`: the rank loop matches
   `target_event_id` alone (never a wrong lookalike); N/A when the correct
   event is absent. Docstring updated.
2. **Regressions added** (`test_stress_metrics.py`):
   `test_recall_metrics_rank_is_the_correct_fact_not_a_wrong_lookalike`
   (wrong rank 1 / correct rank 2 → reported rank 2) and
   `test_recall_metrics_wrong_only_is_rank_na_and_measured_miss`
   (wrong-only → rank N/A, recall 0). One existing scenario test's expected
   rank changed 1 → 2 (`test_stress_scenarios.py` distractor case), with the
   comment now stating the rank belongs to the correct fact — this is the
   behavior the finding demanded.
3. **Medium — live verifier now compares the complete event.**
   `verify_letta_live.py::_event_identity_mismatches` iterates ALL
   `ExperienceEvent` model fields (timestamp, location, raw_events included);
   the live fixture carries a non-null `location`; PASS details now read
   "complete ExperienceEvent equal".

Exact verification after the correction:

- Focused: `pytest benchmark/tests/test_stress_metrics.py
  test_delayed_recall.py test_stress_scenarios.py test_scenario_params.py
  test_run_loop.py` — **47 passed**.
- Full Python: `.venv/Scripts/python -m pytest -q -p no:cacheprovider` —
  **232 passed in 90.44s** (230 + 2 new regressions).
- TypeScript: `cd minecraft && npm test` — **31 passed (3 files)**.
- Strict live (`--require-live`, server 0.16.8), exit 0:

```
PASS  A: add then retrieve round-trips the exact event  complete ExperienceEvent equal
PASS  B: update round-trips the exact new event  complete ExperienceEvent equal; stale location-A items: none
PASS  C: reset isolates the old episode from a fresh one  reset episode retrieval: 0 item(s), fresh episode retrieval: 0 item(s)
PASS: M15A live verification
```

No changes to `docs/protocol.md`, `results/`, scenario parameters, or
unrelated production code; no experiments; no git operations. Stopping for
A's review.
