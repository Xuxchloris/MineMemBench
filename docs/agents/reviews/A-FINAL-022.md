# A-FINAL-022 — Final research review of the count-10 failure-learning smoke

Date: 2026-08-08 23:13 Asia/Shanghai  
Reviewer: Agent A  
Inputs: TASK-022 manifest/results/logs and corrected `docs/agents/qa/QA-022.md`  
Verdict: **ACCEPTED as diagnostic evidence; authorize one count-50 probe only**

## Findings by severity

### Critical

None. The complete 12-run grid is present, every run is valid, and C
independently reproduced the campaign, stream, source-evidence, fairness,
retrieval, behavior, and file-integrity checks.

### High

None for this bounded diagnostic. All backends received the same source
ActionResult-derived failure event and ten neutral interference events within
each paired seed. NoMemory retrieved nothing, resets/scopes were clean, the
warded fixture and planner controls were identical, and no evaluation answer
entered the planner-visible goal, state, or memory view.

### Medium

1. Count 10 is not an observed retrieval threshold. All nine memory-backed
   runs retained the source failure at rank 1/top-1 with recall 1 and prepared
   correctly before the first transfer attack. A formal Failure Point or
   framework ranking is unsupported.
2. Mem0 and Letta returned interference-saturated lists (7–10 and 10 items),
   while Vector returned only the target. The target nevertheless remained
   top-1. This is valid backend behavior under an equal offered stream, but it
   roughly doubled Mem0/Letta planner prompt tokens and makes the cell
   unsuitable for cost-efficiency conclusions.
3. Transfer success remains noisier than retrieval/preparation. The count-10
   Vector/42 failure equipped gold, re-equipped stone, then failed; it matches
   the failure pattern of count-0 Vector/44, not the successful count-0
   Vector/42 run. Per-seed success flips must not be described as an
   interference benefit or harm.
4. The non-positional goal still consumes the full four-step budget after
   transfer completion. Primary ordered causal endpoints remain valid, but
   post-success action/token tails are not efficiency evidence.

### Low

- C's initial report compared the Vector/42 failure to the wrong count-0 seed.
  C re-read both raw results and corrected every affected sentence plus a
  correction note. No metric or verdict changed.
- The source ActionResult fingerprint is seed-invariant because the raw result
  omits attacked-entity arguments; seed identity remains explicit in the
  deterministic event and typed ground truth.

## Accepted paired descriptive result

| backend | count | transfer success | prep before first attack | failure repeated | step-0 failure rank |
|---|---:|---:|---:|---:|---|
| none | 0 | 0/3 | 0/3 | 3/3 | N/A, N/A, N/A |
| none | 10 | 0/3 | 0/3 | 3/3 | N/A, N/A, N/A |
| vector | 0 | 2/3 | 3/3 | 0/3 | 1, 1, 1 |
| vector | 10 | 2/3 | 3/3 | 0/3 | 1, 1, 1 |
| mem0 | 0 | 2/3 | 3/3 | 0/3 | 1, 1, 1 |
| mem0 | 10 | 3/3 | 3/3 | 0/3 | 1, 1, 1 |
| letta | 0 | 2/3 | 3/3 | 0/3 | 1, 1, 1 |
| letta | 10 | 3/3 | 3/3 | 0/3 | 1, 1, 1 |

The change in Mem0/Letta executed success is not a retrieval improvement:
their target retrieval and preparation were already perfect at count 0. With
three seeds and planner action variance, it is descriptive noise.

## Decision

Accept count 10 as one valid Controlled diagnostic. Because ten interference
events load Mem0/Letta retrieval without displacing the target, authorize one
next probe only: `interference_count=50`, unchanged four backends and paired
seeds 42/43/44, in a fresh results directory. This probe asks whether the
source failure loses rank/availability or whether preparation degrades; it
does not authorize count 100, formal seeds, ranking, cost comparison, Native
Minecraft claims, or a formal Failure Point. Stop after C's independent QA and
A's raw review.
