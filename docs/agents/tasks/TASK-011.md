# TASK-011 — Semantically valid Controlled delayed-recall v2

Issued by: Agent A  
Assignee: Agent B  
Independent verifier: Agent C  
Status: implementation authorized; experiment execution is not authorized

## Objective

Repair the Controlled delayed-recall treatment so its declared answer follows
uniquely from the exact planner-visible semantics. The v2 task is an opaque
entity-key-to-location lookup: every candidate fact is simultaneously true,
and the goal names the target key without revealing coordinates.

This is a new, explicitly versioned treatment. It must not silently change or
reinterpret legacy runs and must never be pooled with Controlled rounds 1–4.

## Binding constraints

- Read `AGENTS.md`, `docs/agents/HANDOFF.md`, `README.md`,
  `docs/protocol.md`, the current diff, and the delayed-recall/runner/planner
  tests before editing.
- Do not change `docs/protocol.md`, planner serialization, memory backends,
  backend algorithms, retrieval limits, runner behavior, fairness hashes,
  TypeScript, campaign scripts, historical results, or git state.
- No backend-name branches. No correctness, wrongness, staleness, priority, or
  trust labels may enter events, goals, prompts, or retrieval queries.
- Do not run a live benchmark or campaign. Unit tests must use fakes and no
  network.
- Keep all old `ScenarioResult` JSON loadable. Unmeasured/undefined values are
  `None`/JSON `null`, never fabricated zeroes.

## Required design

### 1. Explicit semantics version

Add a configurable delayed-recall parameter named
`recall_semantics_version` with accepted values:

- `legacy` — default; preserves the existing behavior and metrics exactly;
- `entity_key_v2` — enables the new treatment.

Reject any other value with `ScenarioParamError`. The effective value must be
present in `result.params` so outputs cannot be pooled silently.

Agent A clarification after C preflight: adding the field to serialized
`params` is intentional, but a newly executed `legacy` run must retain the
pre-TASK-011 Controlled event-id/timestamp derivation. In
`DelayedRecallScenario._next_event_identity`, pass the pre-existing two
difficulty parameters to `controlled_event_identity` when the semantics value
is `legacy`; include the version in the identity namespace for
`entity_key_v2`. Do not modify `scenarios/controlled.py`. Add a regression
test for this property.

### 2. Deterministic target identity and goal

For `entity_key_v2`, derive one opaque fixed-width key from the scenario seed
using a dedicated target namespace before and independently of distractor
generation/order. Example shape: `cache-7f3a9c2e`.

The per-run goal must name exactly that key and no coordinates, for example:

`Return to cache-7f3a9c2e whose location you learned during the initial briefing.`

Legacy keeps the existing static `GOAL` byte-for-byte. The v2 diagnostic
retrieval query must use the same dynamic goal (or the exact target key), not
the legacy phrase `target chest location`.

### 3. Simultaneously true candidate facts

For `entity_key_v2`:

- the learned target event maps the target entity key to the target position;
- `similar_distractor_count=N` creates exactly N other entity-key-to-location
  facts;
- distractor keys are deterministic, unique, fixed-width, and highly similar
  one/two-character mutations of the target key;
- target-key generation is independent of N and distractor order;
- all candidate coordinates are unique and distinct from the target for all
  supported levels 0/5/20/50;
- every candidate uses identical actor, event type, context key set and value
  types; only the entity key and coordinates differ;
- every candidate can be true at the same time: no key maps to two locations;
- no candidate contains a negative/update/stale/correct/wrong label.

For testability, "highly similar" means the fixed-width opaque suffix has
Hamming distance 1 or 2 from the target suffix. The prefix and total key
length are identical for all candidates.

Use a neutral common schema such as
`{"entity_key": <key>, "x": ..., "y": ..., "z": ...}`. Do not put the
out-of-band oracle label or event ids into planner-visible content.

Unrelated `interference_count` noise remains unchanged. Native/legacy behavior
must remain backward-compatible.

### 4. Typed out-of-band evaluation ground truth

Extend `ScenarioResult` backward-compatibly with an optional typed
`evaluation_ground_truth` model. For this treatment it must record at least:

- `semantics_version = "entity_key_v2"`;
- `target_event_id`;
- `target_entity_key`;
- ordered `distractor_event_ids`.

It must default to `None`, so old result files validate without mutation. It
is evaluation evidence only and must never enter the planner prompt, memory
event, diagnostic query, WorldState, or action path.

### 5. Versioned metric contract

Keep `compute_recall_metrics` and legacy metric output unchanged for legacy.
Add a separate v2 computation based only on stable event ids from
`evaluation_ground_truth` and the causal
`run_log.steps[0].retrieved_items` snapshot:

- `fact_retrieval_rank`: 1-based target rank, otherwise `None`;
- `target_recall`: 1 when target is present, otherwise 0 (including empty);
- `target_retrieval_precision`: target-item count / all retrieved items,
  `None` on empty retrieval;
- `off_target_retrieval_rate`: known distractor-item count / all retrieved
  items, `None` on empty retrieval.

For v2, retain the old metric keys only for schema compatibility:
`recall_accuracy` may equal `target_recall`, but `wrong_fact_rate` and legacy
`retrieval_precision` must be `None`. Never describe true off-target entities
as wrong facts.

### 6. Required falsification tests

Add tests that fail on semantic contamination, not just happy-path tests.

- **P1 simultaneous truth:** for seeds 42/43/44 and distractor levels
  0/5/20/50, assert key uniqueness, coordinate uniqueness, one location per
  key, common neutral schema/actor/type, and absence of label tokens.
- **P2 unique visible derivation:** implement a test-only oracle that receives
  only `(goal, list[dict])`, where each dict is produced by the exact
  `memory_view_for_prompt`. It must resolve exactly one location and that
  event must equal the declared target for seeds 42/43/44.
- **P3 no hidden cue:** permute/reverse the neutral views and prove the oracle
  answer is invariant. Assert forbidden bookkeeping fields are absent and
  prove timestamps/order are not needed. Assert the target key is invariant
  when distractor count/order changes.
- **P4 independent re-derivation:** serialize/deserialize `ScenarioResult`,
  recompute every v2 retrieval metric from its ground-truth field plus the
  first causal retrieval snapshot, and require exact equality. Cover target
  rank 1, target below off-target items, target absent, and empty retrieval.
- Prove legacy defaults, goal, event structure, metrics, and old JSON loading
  remain unchanged.

Tests may define the oracle helper locally. Do not add an oracle or shortcut
to production action/planner code.

## Documentation

Update `docs/stress_design.md` and `docs/experiment_standard.md` in place to
describe the v2 semantics, metric names, legacy separation, and the fact that
formal execution remains gated. Do not create another project-status or
handoff document.

## Allowed implementation scope

Expected files:

- `benchmark/minemembench/scenarios/base.py`
- `benchmark/minemembench/scenarios/delayed_recall.py`
- relevant Python test files
- `docs/stress_design.md`
- `docs/experiment_standard.md`
- `docs/agents/reviews/B-COMPLETION-011.md`

If another production file appears necessary, stop and report the reason to A
before changing it.

## Verification and handoff

Run:

```powershell
.venv\Scripts\python -m pytest -q benchmark/tests/test_delayed_recall.py benchmark/tests/test_stress_metrics.py benchmark/tests/test_scenario_params.py benchmark/tests/test_controlled_mode.py
.venv\Scripts\python -m pytest -q
```

Write `docs/agents/reviews/B-COMPLETION-011.md` with files changed, exact test
commands/output, requirement mapping P1–P4, and deviations. Do not claim
research conclusions. Do not stage, commit, push, run Docker/live LLM, or
write anything under `results/`.
