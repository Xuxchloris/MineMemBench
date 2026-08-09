# TASK-007 — Remove delayed-recall planner leakage

Issued by: Agent A
Assignee: Agent B
Priority: High

## Objective

Make Controlled delayed-recall behavior depend on retrieval content and order,
not hand-authored correctness labels or backend-specific prompt fields.

Do not change `docs/protocol.md`, the Minecraft scenario goal/action success
rule, the MemoryBackend interface, backend retrieval algorithms, model,
temperature, tools, fixture, or result evidence schema.

## Required implementation

1. Add one backend-neutral planner-memory serializer and use it for every
   backend. Preserve retrieved order and semantic ExperienceEvent content, but
   exclude from the LLM prompt:
   - `MemoryItem.item_id`, `score`, `created_at`, `metadata`;
   - event `event_id`, `episode_id`, `timestamp`, and `raw_events`.
   The exact full retrieved items must continue to be recorded in
   `RunStep.retrieved_items` unchanged for causal audit and metric derivation.

2. In Controlled delayed-recall stress when similar distractors are requested,
   create competing target-location facts with the same neutral actor, event
   type, and context key set as the learned target fact. Remove all semantic
   answer labels, including `wrong location`, `used to be located here`,
   `stale`, `old`, `former`, `decoy`, and equivalents. Apart from coordinates,
   the candidate facts visible to the planner must be structurally identical.
   Retrieval list order is the only correctness cue.

3. Keep event ids as out-of-band ground truth so `fact_retrieval_rank`,
   `recall_accuracy`, `wrong_fact_rate`, and `retrieval_precision` remain
   re-derivable from logged snapshots. Never use those ids to choose an action
   or alter Scenario success.

4. Preserve Native mode unless a shared backend-neutral prompt serializer is
   required for fairness. Any distractor semantic change must be gated to
   Controlled mode so previous Native behavior is not silently redefined.

## Tests / acceptance criteria

- Unit test the exact planner memory JSON: no item/event ids, episode id,
  timestamps, score, created_at, metadata, or raw events; semantic fields and
  retrieval order remain.
- Unit test Controlled target candidates: identical actor/event type/context
  keys, no correctness/staleness labels, distinct deterministic coordinates,
  and stable event ids/logical timestamps in raw evidence.
- Unit test that `RunStep.retrieved_items` still retains the full raw snapshot.
- Existing Python and TypeScript suites remain green.
- Run no campaign and make no git operation. Report modified files and exact
  test output in `docs/agents/reviews/B-COMPLETION-007.md` for A review.

