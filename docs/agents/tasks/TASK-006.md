# TASK-006 — Controlled delayed-recall next ladder point

Issued by: Agent A
Assignee: Agent C
Implementation: already complete; no B code change required

## Objective

Test whether the pre-registered delayed-recall point `(interference_count=200,
similar_distractor_count=20)` removes the vector/mem0/letta behavioral ceiling.

## Execution

Run the Controlled campaign runner exactly once into the new absent directory
`results/stress_controlled_round2_200_20/`:

- one cell named `stress_200_20` with params `(200,20)`;
- default backends `none,vector,mem0,letta`;
- seeds `42,43,44`;
- exactly 12 scheduled/logged runs.

No retry/resume, no extra cell/seed/framework, no production/protocol/git
change. On any failure retain partial evidence and stop.

Audit the same manifest/result/log, actual input-event equivalence, normalized
WorldState, NoMemory, fairness/reset, N/A, and per-cell metrics as QA-005.
Write `docs/agents/qa/QA-006.md`; explicitly compare round 2 with Controlled
round 1 only, never Native.
