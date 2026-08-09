# TASK-009 — Restore event-time semantics and fingerprint the planner template

Issued by: Agent A
Assignee: Agent B
Priority: High

## Objective

Let the unchanged planner resolve the phrase "learned ... at the start" from
equal semantic ExperienceEvent data, while keeping backend internals hidden
and making the prompt schema auditable.

## Required implementation

1. Add `timestamp` to the semantic event object emitted by
   `memory_view_for_prompt()`. Use the ExperienceEvent timestamp exactly as a
   JSON value. Continue to exclude item id, event id, episode id, score,
   `created_at`, metadata, and raw events. Preserve retrieval order.
2. Define a deterministic planner user-template / memory-view fingerprint in
   `agent/planner.py`. It must change if the static user-message labels/order
   or allowed semantic memory field schema changes; do not hash dynamic goal,
   state, transcript, memories, ids, wall time, or secrets.
3. Add the fingerprint to `FairnessRecord` and populate it on every new run.
   Use a backward-compatible optional/default field so old result JSONs remain
   loadable. Do not rename or reinterpret the existing system/tool hashes.
4. Do not change backend algorithms, retrieval limit/order, Scenario facts,
   goal, success rule, model, temperature, tools, TS/Python wire protocol, or
   existing results.

## Acceptance

- Exact prompt-view unit test proves semantic timestamp is present and all
  banned fields remain absent.
- Hash tests prove stability for identical schema/template and sensitivity to
  a schema/template change without depending on dynamic inputs.
- Fairness tests prove new records populate a 64-hex fingerprint and old
  records without it still validate.
- Existing Python suite remains green; TypeScript is required only if touched.
- Run no campaign and perform no git operation. Write
  `docs/agents/reviews/B-COMPLETION-009.md` with files, exact tests and
  deviations, then stop for C/A review.

