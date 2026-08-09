# A-APPROVAL-007 — TASK-007 code and QA review

Date: 2026-08-08
Reviewer: Agent A
Decision: **PASS FOR CORRECTED 3-RUN SMOKE; NOT A FORMAL RESULT**

## Independent verification

- B's implementation is confined to the planner memory view, Controlled
  delayed-recall target candidates, and tests. It does not branch on backend
  name or change the wire protocol, action success rule, backend retrieval
  algorithm, Minecraft adapter, or existing result artifacts.
- A independently ran the full Python suite: **256 passed in 90.95s**.
- C independently ran focused Python (**55 passed**), full Python (**256
  passed**), TypeScript (**31 passed**) and TypeScript build; Letta Docker
  health is 200/version 0.16.8 and the strict live add/retrieve/update/reset
  verifier passed.
- C confirmed there is no new campaign output or residual test listener and
  that the pre-fix round is untouched.
- Exact raw `MemoryItemSnapshot` evidence is still logged while the LLM sees
  only ordered semantic event content. Event ids remain metric-only ground
  truth.

## Research check

A's deterministic, no-network vector diagnostic at `(200,20)` found all ten
target candidates tied at score `0.10660035817780521`; stable insertion order
put the correct fact back at rank 1. This is important evidence that the old
rank-6 pattern was caused by the leaked distractor wording, not a robust
framework difference.

The corrected smoke is therefore needed to answer one narrow question: after
removing the contamination, what do the real mem0/letta retrievals and the
unchanged LLM behavior do? It is not licensed as a superiority experiment.

## Residual findings

### Medium — user-prompt serialization is not fingerprinted

- Location: `benchmark/minemembench/core/fairness.py::FairnessRecord` records
  the system prompt hash but not the planner user-template / memory-view
  version; campaign artifacts also do not record a code commit SHA.
- Effect on conclusions: corrected and pre-fix smoke artifacts can be kept
  separate by directory and explicit review, but this is insufficient for a
  formal reproducible comparison.
- Minimum fix before any 10+ run formal experiment: record an immutable code
  revision/dirty-state and a planner user-template/memory-view fingerprint.
  Do not block this 3-run diagnostic smoke.

### Medium — neutral candidates deliberately leave correctness to retrieval order

- Location: Controlled delayed-recall similar target candidates.
- Effect on conclusions: a backend has no planner-visible correctness label;
  behavior now measures whether its ranked retrieval puts the hidden
  ground-truth event first. This is useful for detecting the prior leakage but
  must not yet be generalized to broad memory quality or source reliability.
- Minimum next step: interpret round 3 only as decontamination validation. A
  will redesign the next difficulty axis based on its raw retrievals instead
  of automatically continuing to `(500,50)`.

## Release

TASK-007 is accepted for TASK-008. Run exactly the corrected `(200,20)` smoke
in a fresh directory, then stop for A's raw-data review.

