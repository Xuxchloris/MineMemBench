# TASK-005 — Controlled runner fail-closed corrections

Issued by: Agent A
Assignee: Agent B
Status: REWORK

Read `docs/agents/reviews/A-REVIEW-004.md`. Make only its four minimum fixes:

1. Reject a non-empty/existing campaign output without writing or deleting it.
2. Use and manifest campaign-local Vector/Mem0 stores.
3. Retain per-run stdout/stderr and link produced scenario JSON in the
   manifest; preserve failure evidence and stop without retry.
4. Verify the complete normalized canonical mock WorldState, not a partial
   subset.

Add hermetic tests for each behavior, run full Python/TS, and append a
TASK-005 section to `B-COMPLETION-004.md`. Do not touch protocol/results, run
the campaign, or perform git operations. Stop for A review.
