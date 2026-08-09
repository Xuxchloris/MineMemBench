# A-FINAL-021 — Final research review of the count-0 failure-learning smoke

Date: 2026-08-08 22:54 Asia/Shanghai  
Reviewer: Agent A  
Inputs: TASK-021 manifest/results/logs and `docs/agents/qa/QA-021.md`  
Verdict: **ACCEPTED as diagnostic evidence; no ranking/formal claim**

## Findings by severity

### Critical

None. All 12 scheduled runs are present, valid, and independently re-derived.

### High

None for the diagnostic construct. The memory manipulation produces a clear
preparation signal without direct scenario-selected actions:

- NoMemory: 0/3 transfer success; 0/3 prepared with gold before first attack;
  3/3 repeated the hidden-precondition failure.
- Vector/Mem0/Letta: each 2/3 transfer success; combined 9/9 retrieved the
  observed failure at rank1/top1 and 9/9 equipped gold before first attack.

This is three-seed evidence, not a framework comparison. The equal 2/3
success rates do not support a ranking.

### Medium

1. The three memory-backed failures (Mem0/42, Vector/44, Letta/44) are
   post-retrieval action-selection failures: the planner correctly equips
   gold, then switches to the stone sword before attacking. Retrieval metrics
   remain perfect while transfer completion fails. Future analysis must keep
   retrieval, preparation intention, and executed success separate.
2. `run_goal` consumes the full four-step budget after a completed transfer
   attack because this non-positional goal has no early-stop predicate. This
   does not change the frozen primary endpoints, which are derived from the
   ordered first relevant actions, but post-success actions make token/action
   tails unsuitable for efficiency conclusions. Do not use this smoke for
   cost ranking.
3. Mem0 add latency includes cold model load and its optional spaCy/fastembed
   features are absent. Latency is descriptive only.

### Low

- The raw source ActionResult does not encode attacked-entity arguments, so
  its fingerprint is seed-invariant. Seed-specific source identity remains
  auditable in the deterministic injected event and typed ground truth.

## Accepted descriptive result

| backend | transfer success | prep before first attack | failure repeated | step-0 failure rank |
|---|---:|---:|---:|---|
| none | 0/3 | 0/3 | 3/3 | N/A, N/A, N/A |
| vector | 2/3 | 3/3 | 0/3 | 1, 1, 1 |
| mem0 | 2/3 | 3/3 | 0/3 | 1, 1, 1 |
| letta | 2/3 | 3/3 | 0/3 | 1, 1, 1 |

## Decision

The count-0 control is accepted and the construct is sufficiently
discriminative to test mild interference. Authorize one next cell only:
`interference_count=10`, same four backends and paired seeds 42/43/44. Stop
after independent QA. No count50, larger sample, formal statistics, ranking,
Failure Point, Native Minecraft, or cost-efficiency claim is authorized.
