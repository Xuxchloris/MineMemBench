# TASK-013 — Controlled world-update temporal-chain v2 core

Issued by: Agent A  
Assignee: Agent B  
Independent verifier: Agent C  
Status: scenario/core implementation authorized; CLI/campaign/live execution
is not authorized

## Objective

Implement a semantically explicit and causally measurable world-update
A→B→C→D treatment. The same supply cache changes location over semantic time;
the latest event is the current truth and prior events are temporally stale.

This task changes only the Scenario core and hermetic tests. Controlled CLI
and campaign generalization belongs to a later task after A/C approve these
semantics.

## Binding constraints

- Read `AGENTS.md`, `docs/agents/HANDOFF.md`, `A-FINAL-012.md`, README,
  protocol, current diff, `world_update.py`, `delayed_recall.py`,
  `scenarios/base.py`, planner memory view and relevant tests before editing.
- Do not modify planner, runner, CLI, fairness, memory backends, registry,
  `scenarios/controlled.py`, campaign scripts, TypeScript, protocol,
  historical results, git state or `.env`.
- No live service, Docker, LLM or campaign. Unit tests are hermetic.
- No backend-name branches. Scenario events record facts and temporal updates,
  never trust/priority/mood/action advice.
- Preserve legacy native behavior/metrics and old result loading. Do not
  reinterpret prior world-update outputs.

## 1. Explicit version and mode gate

Add `update_semantics_version` to `WorldUpdateScenario.default_params`:

- `legacy` — default; current native behavior remains available;
- `temporal_chain_v2` — the new neutral temporal treatment.

Reject any other value. Effective params must be logged in results. A
`ScenarioContext` with `campaign_mode="controlled"` must fail closed unless
the effective value is `temporal_chain_v2`; no research-invalid legacy
Controlled run may be produced. Native legacy tests remain valid and old JSON
without the new field must load.

## 2. Temporal-chain semantics

For v2, `update_depth=3` means four locations A→B→C→D; D is current.
Location generation remains seeded and prefix-stable across depths.

Every chain candidate must have:

- actor `scenario-instructor`;
- event type `WORLD_FACT_UPDATED` (including A, for a common schema);
- context exactly `{"subject":"supply_cache","x":...,"y":...,"z":...}`;
- a unique coordinate and a strictly increasing semantic timestamp.

Only coordinates, event id and semantic timestamp may differ. Remove
planner-visible `moved=True`, update index, `initial/current/stale/latest`, or
any correctness/priority label from v2 candidates. The temporal sequence is
legitimately encoded by semantic timestamps; all A/B/C/D assertions are true
at their event time, with the unique maximum timestamp defining current D.

The v2 goal is static and coordinate-free:

`Retrieve the supply cache at its current location.`

Legacy keeps the existing `GOAL` and event structures unchanged.

## 3. Controlled identity

In v2 Controlled mode, every chain and noise event must use
`controlled_event_identity` with full effective params and per-phase ordinals,
so the complete offered stream is identical across backends except
`episode_id`. A is the experience event; B/C/D and noise occur during
interference with strictly monotone timestamps. Native v2 may use UUID/wall
time; native legacy must remain unchanged.

Do not modify `scenarios/controlled.py`. Tests must compare actual event
streams across NoMemory/Vector recording wrappers for seeds 42/43/44 after
normalizing only `episode_id`.

## 4. Typed ground-truth union

Refactor the current delayed-recall-specific ground-truth type into a strongly
typed discriminated union without changing serialized round-5 data:

- entity-key member, discriminator `entity_key_v2`, with the existing target
  key/event and distractor ids;
- temporal-chain member, discriminator `temporal_chain_v2`, with
  `entity_key="supply_cache"`, ordered `stale_event_ids` (A/B/C) and
  `current_event_id` (D).

`ScenarioResult.evaluation_ground_truth` remains optional/default `None`.
Update delayed-recall only as required to instantiate the renamed typed member;
its behavior, JSON shape, metrics and tests must not change. Prove all actual
round-4 and round-5 JSON files still load.

Ground truth is written only to `ScenarioResult` after the action-producing
run. It must never enter memory events, goal, diagnostic query, WorldState,
planner view or action path.

## 5. Causal v2 metric contract

Keep legacy `compute_update_metrics` and legacy output unchanged. Add a
separate id-based v2 computation using only the typed ground truth plus
`run_log.steps[0].retrieved_items`:

- `current_fact_retrieval_rank`: 1-based rank of D, else `None`;
- `current_fact_recall`: 1 when D is present, otherwise 0, including empty;
- `current_fact_retrieval_precision`: D count / all retrieved, `None` empty;
- `stale_fact_retrieval_rate`: known A/B/C count / all retrieved, `None` empty;
- `current_fact_top1`: 1 if top item is D, 0 if top item is A/B/C, otherwise
  `None`;
- `stale_memory_rate`: A/B/C count / all retrieved chain facts, `None` if no
  chain fact is retrieved.

For v2 retain `current_fact_accuracy` only as a compatibility mirror of
`current_fact_top1`, and `obsolete_fact_retrieval_rate` as a compatibility
mirror of `stale_fact_retrieval_rate`. Log
`retrieval_evidence_source="run_log.steps[0].retrieved_items"`.

Empty retrieval is a measured current-fact miss (recall 0); undefined rates
remain N/A. A non-empty noise-only retrieval has recall 0,
`current_fact_retrieval_precision=0.0`, `stale_fact_retrieval_rate=0.0`, and
top1/stale-memory N/A.

Behavior metrics for v2:

- `stale_action`: first `move_to` targets any A/B/C event location;
- `final_distance_to_current`: distance to D;
- existing task/token/latency metrics.

The diagnostic evaluation probe may remain as raw evidence with the v2 goal
as query, but it must feed no headline or behavior metric.

## 6. Mandatory falsification tests

- **P1 temporal validity:** seeds 42/43/44 × depths 1/2/3/4; unique
  coordinates, exact common schema/actor/type, strictly increasing unique
  timestamps, ordered stale ids + last current id, no banned labels.
- **P2 unique visible oracle:** a test-only oracle over
  `(goal, list[exact memory_view_for_prompt dict])` filters the supply-cache
  chain and selects the unique maximum semantic timestamp. It must equal the
  declared current event/location for seeds 42/43/44 at depth 3.
- **P3 no hidden cue:** oracle is invariant under permutation/reversal and has
  no ids/scores/metadata/injected position. If all chain timestamps are made
  equal, it must report ambiguity; if a different candidate is given the
  unique newest timestamp, the oracle must select that candidate. This proves
  time—not insertion order or a label—is the defined semantic cue.
- **P4 independent metric derivation:** JSON round-trip and exact recomputation
  from typed ground truth + causal step-0 snapshot. Cover D rank 1, D below
  stale items, D absent with stale items, noise-only and empty retrieval.
- **P5 causal-vs-probe:** make the diagnostic probe differ from the first
  causal snapshot and prove logged v2 metrics still equal the causal snapshot.
- **P6 compatibility:** legacy goal/events/metrics remain unchanged; actual
  round-4 and round-5 files load; delayed-recall 269-test behavior remains
  intact.

Agent A clarification: `results/` is gitignored, so actual round-4/5 loading
is a local evidence gate reported in B-COMPLETION/C QA, not an unconditional
portable unit-test dependency. The normal pytest suite must still pass in a
clean checkout where those directories are absent. A test may explicitly skip
the local-evidence check when artifacts are absent, while a separate current-
workspace command must require and validate all 24 files for this review. Do
not copy or fabricate result JSON into tracked fixtures.

Tests may define the temporal oracle locally. Do not add an oracle or
hand-coded action rule to production.

## Documentation and allowed scope

Update `docs/stress_design.md` and `docs/experiment_standard.md` in place with
the v2 semantics, causal metrics, legacy separation and “no campaign yet”
gate. Write `docs/agents/reviews/B-COMPLETION-013.md`.

Expected production files only:

- `benchmark/minemembench/scenarios/base.py`
- `benchmark/minemembench/scenarios/world_update.py`
- `benchmark/minemembench/scenarios/delayed_recall.py` (typed-member rename
  only)
- relevant Python tests and the two existing docs above

If another production file is necessary, stop and report to A instead of
expanding scope.

## Verification

Run focused world-update/base/delayed tests, then:

```powershell
.venv\Scripts\python -m pytest -q
```

Report exact files, commands/counts, P1–P6 mapping and deviations in
B-COMPLETION-013. Do not stage/commit/push or write under `results/`.
