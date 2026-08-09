# A-REVIEW-011 — TASK-011 final code/research review

Date: 2026-08-08  
Reviewer: Agent A  
Inputs: TASK-011, B-COMPLETION-011, QA-011, current code/tests/docs  
Decision: **CHANGES REQUIRED — do not run the v2 smoke yet**

## Overall assessment

The entity-key v2 treatment is methodologically sound in its central design.
C independently confirmed simultaneous truth, unique planner-visible
derivation, order/time-invariant oracle behavior, causal metric
re-derivation, old-result loading, backend isolation, TypeScript health and
Letta 0.16.8 live round-trip/reset behavior. No framework ranking or formal
claim is authorized yet.

There is one mandatory compatibility defect plus two small evidence/wording
repairs. B must make a bounded repair; C then reruns the focused/full gates.

## Critical

None.

## High

### H-1 — Legacy Controlled event identity changed against the frozen contract

- **Location:**
  `benchmark/minemembench/scenarios/delayed_recall.py:391`–`407`, especially
  `params=self.params` at line 406; missing regression coverage under
  `benchmark/tests/`.
- **Reason:** `recall_semantics_version="legacy"` is now part of
  `self.params`, so legacy event ids hash three parameters instead of the
  pre-TASK-011 two. C reproduced
  `ctrl-6342fe1db59ccfbe969df790` (old derivation) versus
  `ctrl-3acfc1d81dca5a4e52e99dcc` (current). This directly contradicts A's
  written TASK-011 clarification. Semantic timestamps happen to remain equal,
  but the derivation input and event ids do not.
- **Impact on experimental conclusions:** **Yes, reproducibility/audit impact.**
  It does not invalidate v2's entity-key semantics, but it breaks the declared
  legacy rerun identity and makes cross-round raw identity checks ambiguous.
  The v2 smoke cannot be released while a mandatory compatibility gate fails.
- **Minimum repair:** within `_next_event_identity`, pass only
  `interference_count` and `similar_distractor_count` for `legacy`; pass the
  full versioned params for `entity_key_v2`. Do not change
  `scenarios/controlled.py`. Add a regression test comparing an actual
  Controlled legacy experience event to `controlled_event_identity` with the
  pre-existing two-param dict, and assert v2 uses a distinct identity.

## Medium

### M-1 — Timestamp-independence is verified by C but not encoded in B's suite

- **Location:**
  `benchmark/tests/test_delayed_recall_v2.py:214`–`252`.
- **Reason:** the P3 test shuffles/reverses views and inspects allowed fields,
  but does not mutate timestamps. C independently mutated timestamps and the
  oracle stayed invariant, so the implementation currently behaves correctly;
  the required falsification property is simply missing as a regression test.
- **Impact on experimental conclusions:** **Not currently**, because C's
  independent falsification passed. It weakens future contamination defense.
- **Minimum repair:** deep-copy the exact neutral views, replace every
  timestamp with distinct values/order, and assert the test-only oracle answer
  is unchanged.

## Low

### L-1 — “Byte-for-byte unchanged” overstates legacy compatibility

- **Location:**
  `benchmark/minemembench/scenarios/delayed_recall.py:67,352`,
  `docs/stress_design.md:81`,
  `docs/agents/reviews/B-COMPLETION-011.md:17,100`–`105`, and the legacy test
  docstring near `benchmark/tests/test_delayed_recall_v2.py:372`.
- **Reason:** even after H-1 is fixed, newly serialized legacy results
  intentionally gain the explicit version in `params` and may serialize the
  optional ground-truth field as `null`. The correct guarantee is that the
  legacy goal, event semantics, metrics and Controlled event identity remain
  compatible, while old JSON remains loadable—not that the whole result JSON
  is byte-for-byte identical.
- **Impact on experimental conclusions:** **No direct numerical impact**, but
  the wording can mislead reproducibility reviews.
- **Minimum repair:** replace the overclaim with the precise guarantee above;
  amend B-COMPLETION-011 so it no longer calls the legacy ID change acceptable
  and append the repair test results.

## Release gate after repair

Required before A approval:

1. focused Python suite including `test_delayed_recall_v2.py` green;
2. full Python suite green;
3. C independently reproduces the old legacy ID, distinct v2 ID, timestamp
   mutation invariance, old round-4 JSON loading, TS build/tests and Letta
   hermetic tests;
4. no production scope expansion and no files under `results/` changed.

Only then may C execute exactly one fresh four-backend × three-seed
Controlled `(200,20)` v2 smoke in a new directory.
