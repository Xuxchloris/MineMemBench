# TASK-008 — Corrected Controlled delayed-recall smoke

Issued by: Agent A
Assignee: Agent C
Code gate: A-APPROVAL-007

## Research question

After removing answer-label and backend-metadata leakage, do vector, mem0, and
letta still differ in exact retrieval order and behavior at `(200,20)`?

## Execution

Run the Controlled campaign runner exactly once into the absent directory:

`results/stress_controlled_round3_decontaminated_200_20/`

- cell name: `stress_200_20_decontaminated`;
- params: `interference_count=200`, `similar_distractor_count=20`;
- backends: `none,vector,mem0,letta`;
- seeds: `42,43,44`;
- exactly 12 scheduled runs, seed-major cyclic counterbalance;
- no retry/resume, extra seed/cell/framework, production edit, protocol edit,
  result overwrite, or git operation.

On the first failed/crashed run, retain all partial logs and stop. Never pool
or overwrite pre-fix round 2.

## Mandatory audit

1. Manifest/log/result binding, unique run/episode ids, expected seeds,
   backends, cell, params, ports, model, temperature, fixture and hashes.
2. Full actual injected-event equality across backends for each seed after
   replacing only `episode_id`; full step-0 WorldState equality after
   excluding only raw timestamp.
3. For every Controlled result, every retrieved target candidate visible to
   the planner must have the same actor/event type/context key set and no
   wrong/stale/old/former/decoy/correct label. Raw ids/timestamps/scores remain
   in `RunStep.retrieved_items` but are not planner-visible by code path.
4. Re-derive correct fact rank, recall, wrong-fact rate, precision, task
   success, tokens, add/retrieve latency and errors from raw logs; report N/A
   correctly and retain failures.
5. Compare with pre-fix round 2 descriptively only: explicitly state the
   prompt/scenario treatment changed and never pool success/rank estimates.
6. Confirm NoMemory emptiness, reset/isolation, historical results unchanged,
   and no mock bot listener remains.

Write `docs/agents/qa/QA-008.md` with PASS/FAIL/N/A, the exact command, raw
artifact locations, per-cell table, anomalies, and the narrow supported
conclusion. Then stop for A review.

