# TASK-016 — Memory-noise semantics v2 and causal Controlled core

Issued by: Agent A  
Implementer: Agent B  
Independent verifier after B: Agent C  
Status: **implementation only; no campaign authorized**

## Objective

Make `memory_noise_stress` eligible for the same auditable Controlled workflow
as delayed-recall v2 and world-update v2, without changing legacy/native
behavior. This task implements and tests the treatment; it does not run a
campaign or draw a framework conclusion.

## Current defects to remove in v2

The legacy scenario uses UUID/wall-clock event identity, has no typed
event-id ground truth, identifies relevance by parsing `subject`, and computes
retrieval metrics from a second evaluation probe rather than the retrieval
that caused the first action. Controlled policy and the campaign runner also
reject the scenario. These properties make the legacy treatment ineligible
for comparative evidence.

## Frozen v2 treatment

Add `noise_semantics_version` with:

- `legacy` as the default, preserving existing native behavior and old result
  loading;
- `key_retention_v2` as the only Controlled-approved value.

Difficulty remains `noise_count`, integer `>= 0`, with the planned ladder
`0,10,50,100,200,500,1000`; do not hard-code a campaign or run the ladder.

### Target event and goal

- Derive one opaque fixed-width target key and target coordinate
  deterministically from the seed in dedicated namespaces, independent of
  `noise_count` and noise generation. The Controlled event id still uses the
  full effective params and therefore is intentionally cell-specific.
- V2 goal names the target key but no coordinate, priority, correctness,
  retrieval hint or backend detail. Suggested form:
  `Return to <key> whose location you learned during the initial briefing.`
- Store one target event with neutral actor/type and context exactly
  `{entity_key, x, y, z}`.
- In Controlled mode derive the event id/timestamp via
  `controlled_event_identity(seed, full effective params, phase, ordinal)`.

### Noise stream

- Store exactly `noise_count` neutral, simultaneously true noise events.
- Every noise event uses the same actor, event type and context key set as the
  target event. It differs only in an independently derived opaque entity key
  and a unique seeded coordinate.
- Noise prefixes must be stable: for a fixed seed, the first N events and
  coordinates must be identical when comparing cells N and M where N < M.
- All target/noise entity keys and coordinates must be unique. Noise keys must
  not be one-character near-miss variants of the target; this axis measures
  volume, not lexical similarity (that belongs to delayed recall).
- Do not include labels such as target/noise/relevant/irrelevant/correct/
  wrong/priority/current/stale in prompt-visible events.
- Controlled streams must be identical across backends after normalizing only
  `episode_id`. Native legacy behavior remains unchanged.

### Typed ground truth and causal metrics

Add a discriminated typed ground-truth model to `ScenarioResult` for
`semantics_version: Literal["key_retention_v2"]` containing at least:

- `target_event_id`;
- `target_entity_key`;
- ordered `noise_event_ids`.

It is evaluation-only and must never enter planner prompts, retrieval queries
or stored events.

For v2 compute all headline retrieval metrics only from
`run_log.steps[0].retrieved_items` plus typed ground truth:

- `target_retrieval_rank` (1-based, N/A if absent);
- `target_recall` (empty retrieval is measured 0);
- `target_retrieval_precision` (target count / retrieved count; N/A on empty);
- `noise_retrieval_rate` (known noise ids / retrieved count; N/A on empty);
- `target_top1` (1 target, 0 known noise, N/A otherwise);
- `retrieved_item_count`.

Keep legacy metric keys loadable. In v2, any compatibility mirror must be
explicitly documented; semantically invalid legacy metrics stay N/A rather
than being silently redefined. The evaluation-time probe may remain as
`evaluate-diagnostic` raw evidence but must feed no headline or behavioral
metric.

Behavioral/cost metrics remain logged from the real run: task success, token
counts, LLM calls, add/retrieve latency and end-to-end latency. Do not claim
latency normalization.

## Controlled policy and runner

- Extend the single central Controlled policy to approve only
  `memory_noise_stress + key_retention_v2`; missing/legacy/unknown versions
  fail before bot, LLM, backend, output or process construction.
- Generalize the campaign planner only as needed to accept the scenario and
  full effective params. Preserve semantic duplicate-cell rejection,
  pre-registration, counterbalancing, campaign-local stores, result/fairness
  validation, stop-on-first-failure and late-bound test dependencies.
- Do not branch on backend name in planner/scenario/runner code and do not
  change `docs/protocol.md`.

## Required falsification tests

At minimum add hermetic tests proving:

1. legacy defaults and native result compatibility remain intact;
2. invalid params/version and Controlled legacy fail closed before side
   effects;
3. target semantic key and coordinate are independent of `noise_count`, while
   the Controlled event id remains full-treatment/cell-specific;
4. prefix stability and uniqueness at representative counts including 0 and
   1000;
5. full event-stream equality across backends after only episode normalization;
6. no banned prompt-visible labels or ground-truth leakage;
7. exact v2 metric math for empty, target absent, target below rank 1, noise
   present and a FlipFlopBackend whose second probe differs;
8. typed ground-truth serialization and old JSON loading;
9. campaign preflight/manifest identity, duplicate-cell rejection and strict
   result/fairness validation for memory-noise v2;
10. no network calls or real subprocesses in tests.

Run focused tests and the full Python suite. If production behavior would
require a wire-protocol change, stop and report instead.

## Deliverable

Modify only the smallest necessary production/tests/docs files. Do not modify
existing `results/`, run a live campaign, stage, commit or push. Report files,
focused/full test outputs and deviations in
`docs/agents/reviews/B-COMPLETION-016.md`, then stop for C.
