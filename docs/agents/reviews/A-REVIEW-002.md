# A-REVIEW-002 — TASK-002 implementation review

Date: 2026-08-08
Reviewer: Agent A
Decision: **REWORK — do not release Agent C yet**

## Independent gates

- Python: **PASS**, `230 passed in 89.61s`.
- TypeScript: **PASS**, `31 passed` in 3 files.
- Letta strict live against 0.16.8: **PASS**, add/retrieve, update, and reset.
- `docs/protocol.md`: unchanged.
- `results/`: unchanged.
- Git operations by B: none.

## Findings

### High — `fact_retrieval_rank` ranks the first target-like fact, not the correct fact

- Location: `benchmark/minemembench/scenarios/delayed_recall.py`,
  `compute_recall_metrics` rank loop (around lines 190-195).
- Cause: the rank loop accepts every id in `relevant_ids`, which contains the
  correct event and all known wrong/stale lookalikes.
- Effect on conclusions: **yes**. If a wrong distractor is rank 1 and the
  correct fact is rank 2, the reported rank is 1. A backend that prioritizes a
  stale/wrong memory can therefore look better than it is, directly weakening
  the planned stress comparison and failure-point interpretation.
- Minimum fix: define `fact_retrieval_rank` as the 1-based rank of
  `target_event_id` only; return N/A when the correct event is absent. Add a
  regression with wrong rank 1 / correct rank 2, plus a wrong-only case.

### Medium — live verifier labels a partial comparison as an exact event round-trip

- Location: `scripts/verify_letta_live.py`,
  `_event_identity_mismatches` (around lines 101-122).
- Cause: it omits `timestamp`, `location`, and `raw_events`, although the
  adapter contract and completion report claim the complete original
  `ExperienceEvent` round-trips.
- Effect on conclusions: **not on the current rank calculation**, but it leaves
  the Letta evidence contract under-verified and could hide future information
  loss in event fields used by another scenario.
- Minimum fix: compare the complete `ExperienceEvent` model in the live check
  and make the verifier fixture contain at least a non-null `location`; retain
  a useful mismatch message. A raw-event fixture is optional if equality still
  covers the field.

## Accepted parts

The paired seed schedule, completed-episode reset audit, per-decision retrieval
snapshots, id-based correct/wrong classification, Letta server-backed payload
tag, strict availability mode, full raw retrieval evidence, and
`failure_transfer` safety gate are architecturally acceptable. No backend-name
conditional was introduced into planner, runner, or scenario behavior.

