# A-FINAL-006 — Controlled round-2 research review

Date: 2026-08-08
Reviewer: Agent A
Decision: **DATA VALID; STOP LADDER — benchmark contamination detected**

## Evidence gate

Agent C's raw-artifact audit supports the integrity of
`results/stress_controlled_round2_200_20/`:

- 12/12 scheduled runs completed and bind one-to-one to unique result files;
- every `(seed, params)` has 221 equal injected events across all four
  backends after replacing only the episode isolation id;
- step-0 WorldState is equal per seed after excluding the raw observation
  timestamp, which is not sent to the planner;
- Controlled fixture, model, temperature, prompt/tool hashes, reset evidence,
  run ids, ports, and logs are complete;
- NoMemory retrieves nothing and fails 0/3; no failed run was excluded.

The round is valid as a Controlled smoke. It does not validate the current
scenario as a behavioral backend discriminator.

## Supported conclusions

1. At `(200,20)`, vector's correct fact degrades to rank 6 on all three seeds,
   while mem0 and letta retain rank 1.
2. Retrieval load is severe: each real backend returns 9 known wrong target
   facts among 10 items, yet all three backends remain 3/3 behaviorally.
3. NoMemory remains 0/3, so memory is necessary, but this version of the
   stress is not behaviorally discriminative among memory backends.
4. No Failure Point, framework superiority, or formal latency-efficiency
   claim is supported.

## Findings

### High — distractors disclose their incorrectness to the planner

- Location: `benchmark/minemembench/scenarios/delayed_recall.py`,
  `build_similar_distractors()` and `interference_phase()`.
- Cause: target-location distractors carry literal notes `wrong location` or
  `used to be located here`. They also use actor `environment` and event type
  `world_fact_updated`, whereas the correct fact uses actor
  `scenario-instructor` and event type `location_discovered`.
- Effect on conclusions: **yes**. The planner can reject wrong facts using
  hand-authored labels/structure even when they outrank the correct fact. The
  observed vector rank-6 + behavior-3/3 pattern is exactly compatible with
  that leakage. Increasing only the number of similarly labelled distractors
  would measure prompt filtering, not memory quality.
- Minimum fix: in the Controlled behavioral stress, make all competing
  target-location facts use the same neutral actor, event type, context
  schema, and unlabeled wording. They may differ only in coordinates and
  retrieval order. Keep correct/wrong event ids solely as out-of-band metric
  ground truth; never expose labels such as wrong, stale, former, old, decoy,
  or correct to the planner.

### High — planner prompt exposes backend-specific retrieval internals

- Location: `benchmark/minemembench/agent/planner.py::_build_user_message()`.
- Cause: every full `MemoryItem` is serialized into the prompt, including
  backend-specific item id, score scale, storage time, metadata, and the
  ExperienceEvent's event id, episode id, timestamp, and raw fields.
- Effect on conclusions: **yes**. Backends receive the same events but do not
  expose comparable score/id/metadata representations. The LLM may exploit
  these non-treatment-semantic fields, so behavior is not attributable only
  to retrieved content and order.
- Minimum fix: serialize an ordered, backend-neutral memory view containing
  only semantic event fields needed for action. Strip item/event ids, episode
  id, timestamps, score, created_at, metadata, and raw events from the planner
  prompt. Preserve the exact raw `MemoryItemSnapshot` in `RunStep` for audit
  and metrics. Apply the same normalization to every backend without
  branching on backend name.

### Medium — latency metric still includes process/model initialization

- Location: round-2 `avg_add_latency_ms`, especially mem0 seed 42 versus
  seeds 43/44.
- Effect on conclusions: no effect on the behavioral decision, but blocks
  per-write efficiency claims.
- Minimum future fix: report initialization and operation totals separately
  before formal performance comparison.

## Decision

Do **not** run `(500,50)` on the contaminated scenario. Proceed to TASK-007.
After implementation and A code approval, repeat only `(200,20)` in a fresh
directory. The pre-fix round remains evidence of the discovered ceiling and
must never be overwritten or pooled with the corrected version.

