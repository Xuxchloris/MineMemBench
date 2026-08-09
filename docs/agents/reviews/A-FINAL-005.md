# A-FINAL-005 — Controlled round-1 research review

Date: 2026-08-08
Reviewer: Agent A
Decision: **DATA VALID; behavioral stress insufficient**

## Evidence gate

Agent A independently re-derived the campaign from raw artifacts:

- manifest 24; scenario JSON 24; unique run ids 24; unique episode ids 24;
- manifest/result/log binding complete; zero audit issues;
- actual injected-event streams equal across the four backends for every
  `(seed, params)` after replacing only `episode_id`;
- step-0 planner WorldState equal after replacing only the raw observation
  timestamp (which is excluded from the prompt);
- controlled mode/fixture/model/temperature/hashes/fairness/reset all valid;
- Native and Controlled directories remain separate.

Therefore `results/stress_controlled_round1/` is valid Controlled smoke data.

## Supported conclusions

1. Long-term memory is behaviorally necessary in this scenario: NoMemory is
   0/3 at both cells; vector/mem0/letta are 3/3.
2. `(50,5)` is retrieval-discriminative: vector's correct fact moves from rank
   1 to rank 2 on all seeds, while mem0/letta remain rank 1. The exact
   retrieval that caused each action is retained.
3. `(50,5)` is **not behaviorally discriminative among the three memory
   backends**: all are 3/3. No backend Failure Point or superiority claim is
   supported.
4. Native letta 2/3 versus Controlled letta 3/3 confirms that the rejected
   Native result was confounded by world-state/run-order drift and must not be
   merged into the Controlled estimate.

## Findings

### High — behavioral ceiling remains at the first stress point

- Location: `results/stress_controlled_round1/`, all vector/mem0/letta stress
  logs.
- Effect on conclusions: prevents backend ranking and Failure Point claims.
- Minimum next step: keep seeds at 3 and move only to the pre-registered next
  ladder point `(200,20)`; do not add a framework or expand runs.

### Medium — `avg_add_latency_ms` confounds initialization with per-event cost

- Location: mem0 metrics (control roughly 1.9-2.1 s/add versus stress roughly
  0.36-0.45 s/add).
- Cause: each isolated CLI process pays one fixed local embedding-model load;
  the average divides that fixed cost by 11 versus 56 adds.
- Effect on conclusions: does not affect behavior/retrieval, but the current
  average cannot support a per-write efficiency claim across difficulty.
- Minimum future fix: retain total initialization and total add time separately
  before formal cost analysis. Do not block the next behavioral smoke.

## Decision

Proceed to TASK-006: exactly one new Controlled cell `(200,20)`, four
backends, seeds 42/43/44, 12 runs. Stop after it; A decides whether `(500,50)`
is needed.

