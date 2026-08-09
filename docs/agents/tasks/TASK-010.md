# TASK-010 — Temporal-complete Controlled delayed-recall smoke

Issued by: Agent A
Assignee: Agent C
Code gate: A-APPROVAL-009

## Research question

With neutral candidate content, semantic event time visible, and backend
internals hidden, which backends retrieve enough evidence for the unchanged
LLM to resolve "learned ... at the start" at `(200,20)`?

## Execution

Run the Controlled campaign exactly once into the absent directory:

`results/stress_controlled_round4_temporal_200_20/`

- cell `stress_200_20_temporal`;
- params `(interference_count=200, similar_distractor_count=20)`;
- backends `none,vector,mem0,letta`;
- seeds `42,43,44`;
- exactly 12 scheduled runs with the existing seed-major cyclic order;
- no retry/resume, extra run/cell/framework, production/protocol/git change,
  or overwrite.

On first process failure retain partial evidence and stop.

## Audit and report

Repeat TASK-008's full manifest/log/result, input-event, normalized WorldState,
neutral-candidate, rank/metric, NoMemory, reset/isolation, N/A and listener
audit. Additionally require:

- `fairness.planner_user_template_hash` equals the approved 64-hex value in
  all 12 new results;
- every target candidate in the planner-visible semantic view has a timestamp;
  the correct event is the unique earliest candidate per seed;
- for every memory-backed step, compare the chosen coordinates with both
  retrieval item 1 and the earliest retrieved target event;
- explicitly test QA-009-PREFLIGHT hypotheses H1/H2/H3;
- compare round 4 with round 3 descriptively only; never pool rounds 2/3/4.

Write `docs/agents/qa/QA-010.md` with exact command, PASS/FAIL/N/A, raw paths,
per-seed metrics, causal action/time audit, anomalies and narrow supported
conclusion. Then stop for A's final research review.

