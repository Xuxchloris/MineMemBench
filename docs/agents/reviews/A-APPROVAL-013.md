# A-APPROVAL-013 — TASK-013 world-update temporal-chain v2 core

Date: 2026-08-08  
Reviewer: Agent A  
Decision: **APPROVED for core semantics; no experiment authorized**

## Basis

- B implemented the versioned `temporal_chain_v2` Scenario core and P1–P6
  falsification suite.
- C independently verified the original implementation, rejected two bounded
  acceptance defects, and confirmed the semantics/causal metrics themselves
  were sound (`QA-013.md`).
- A issued `A-REVIEW-013.md`; B repaired only the authorized Literal contract
  and portable evidence-test behavior.
- C independently reverified construction and assignment validation, all
  artifact absence/partial states, the strict 12+12 historical-result gate,
  scope, and test suites.
- Final independent counts: **92 focused Python passed**, **281 full Python
  passed**; prior TS regression gate **31 passed** and build succeeded. The
  repair was Python-only, so a second TS run was correctly N/A.

## Accepted properties

- Controlled `update_depth=3` represents the neutral temporal chain A→B→C→D
  for one `supply_cache`; D is current by unique maximum semantic timestamp.
- Every chain candidate uses the same actor/type/context schema and contains
  no stale/current/correctness/priority label.
- Offered streams are identical across NoMemory and Vector after normalizing
  only `episode_id` for seeds 42/43/44; event identity uses the full effective
  parameter set.
- The typed discriminated ground-truth union preserves round-5 entity-key
  JSON and loads round-4 data with `None`; temporal-chain `entity_key` is
  enforced as `Literal["supply_cache"]`.
- Headline v2 retrieval metrics are re-derivable from
  `run_log.steps[0].retrieved_items` plus out-of-band event ids. The later
  diagnostic probe is raw evidence only and cannot affect headline or
  behavior metrics.
- Ground truth does not enter memory events, prompt, goal, query, world state
  or action paths. No backend-name branch was added.
- Legacy native world-update remains separately available and compatible;
  Controlled legacy fails closed.
- Portable pytest explicitly skips local historical evidence only when both
  gitignored evidence sets are absent; partial evidence fails. The current
  workspace independently validated all 24 files.

## Remaining limits

- This approval covers Scenario/core semantics only. The current Controlled
  CLI/campaign path is still delayed-recall-specific.
- No world-update live run, smoke matrix, framework ranking, formal sample or
  Failure Point is approved by this document.
- Native v2 wall-clock timestamps are theoretically collision-prone; the
  Controlled research path uses the strictly monotone logical clock. Track as
  Low hardening, not a blocker for the next Controlled-only task.
- The repository is still heavily dirty at HEAD `cbaa276`; formal research
  claims remain gated on a clean immutable reviewed revision.

## Next authorization boundary

Agent A may issue a separate bounded task to generalize the existing
Controlled CLI/campaign runner for `world_update` while preserving the exact
delayed-recall behavior and all fairness gates. Until that task receives B
implementation, C independent QA and A approval, **no world-update campaign
may be executed**.
