# TASK-003 — Minimal correction before C release

Issued by: Agent A
Assignee: Agent B
Status: **REWORK**

Read `docs/agents/reviews/A-REVIEW-002.md`. Make only these corrections:

1. In delayed-recall metrics, `fact_retrieval_rank` is the rank of the correct
   `target_event_id` only, never the first wrong target-like distractor.
2. Add regression tests for (a) wrong at rank 1 and correct at rank 2, and
   (b) wrong present but correct absent.
3. Make the strict live Letta verifier compare the complete reconstructed
   `ExperienceEvent` with the event written. Ensure the live fixture exercises
   a non-null `location`; keep actionable mismatch output.
4. Run focused tests, full Python, TypeScript, and strict live Letta.
5. Append the correction and exact outputs to
   `docs/agents/reviews/B-COMPLETION-002.md`.

Do not change `docs/protocol.md`, production behavior outside these points,
scenario parameters, or `results/`. Do not run an experiment or perform any
git operation. Stop and return to A after verification.
