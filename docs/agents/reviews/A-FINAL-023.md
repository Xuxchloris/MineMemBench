# A-FINAL-023 — Final research review of the failure-learning 0/10/50 curve

Date: 2026-08-08 23:29 Asia/Shanghai  
Reviewer: Agent A  
Inputs: TASK-021/022/023 manifests, results and logs; QA-021/022/023  
Verdict: **ACCEPTED as Controlled diagnostic evidence; stop this ladder**

## Findings by severity

### Critical

None. C independently reproduced 81/81 count-50 checks, and the paired
count-0/count-10/count-50 evidence is complete. There are no missing or
duplicate runs, silent exclusions, retries, reset leaks, control-variable
changes, stream mismatches, result-registration gaps, or fabricated values.

### High

1. **No framework ranking or formal Failure Point is supported.** This is a
   three-seed smoke on a dirty, non-immutable worktree. All memory backends
   retain the target at rank 1 through count 50, so the tested ladder never
   observes a retrieval failure point.
2. **The interference treatment has a retrieval-quality ceiling.** The fifty
   distractors are deliberately neutral ambient facts with no answer leakage
   or task-token overlap. They load Mem0/Letta's returned top-10 but never
   compete with the source failure for rank. Increasing the same construct to
   count 100 is unlikely to add decision-relevant stress and is not authorized.

Both findings constrain the conclusions but do not invalidate the diagnostic
campaigns.

### Medium

1. Mem0/Letta retrieval becomes fully interference-saturated by count 50
   (target + nine interference items), while Vector returns only the target.
   This is a real backend response to the same offered ExperienceEvent stream,
   not a fairness violation; nevertheless, target rank/top-1/preparation stay
   identical, so it is loading evidence rather than quality degradation.
2. Vector success moves 2/3 → 2/3 → 1/3 despite byte-identical retrieval
   quality. Its two count-50 failures correctly retrieve and equip gold, then
   re-equip the stone sword. Executed success therefore contains planner
   action-selection variance and must remain separate from retrieval and
   preparation endpoints.
3. Planner-visible memory raises Mem0/Letta prompt tokens from about 4.3k to
   about 7.3k. Vector retrieval latency grows from about 2 ms to 14 ms to 70 ms
   as the SQLite implementation scans 1/11/51 stored rows. Initialization and
   internal memory costs are not normalized; none of these figures support an
   efficiency ranking.
4. The non-positional goal continues for four steps after transfer completion.
   Ordered first-relevant-action endpoints are valid, but post-success tails
   are not useful cost or behavior evidence.

### Low

- Mem0 emits the known optional spaCy/fastembed warnings; no run crashes.
- The normalized raw ActionResult fingerprint is seed-invariant because its
  schema omits attacked-entity arguments. Deterministic events and typed
  ground truth preserve the seed-specific entity identity.

## Accepted descriptive curve

| backend | transfer success at 0 / 10 / 50 | preparation at 0 / 10 / 50 | target rank at 0 / 10 / 50 |
|---|---|---|---|
| none | 0/3 · 0/3 · 0/3 | 0/3 · 0/3 · 0/3 | N/A · N/A · N/A |
| vector | 2/3 · 2/3 · 1/3 | 3/3 · 3/3 · 3/3 | 1,1,1 · 1,1,1 · 1,1,1 |
| mem0 | 2/3 · 3/3 · 3/3 | 3/3 · 3/3 · 3/3 | 1,1,1 · 1,1,1 · 1,1,1 |
| letta | 2/3 · 3/3 · 3/3 | 3/3 · 3/3 · 3/3 | 1,1,1 · 1,1,1 · 1,1,1 |

Across all 27 memory-backed runs, the source failure is retrieved at rank 1
and gold is equipped before the first transfer attack. Across all nine
NoMemory runs, no long-term item is retrieved, gold is never prepared first,
and the hidden-precondition failure is repeated. This is valid diagnostic
evidence that observed failure memory changes preparation behavior in this
Controlled construct. It is not evidence that one memory framework is better.

## Decision

Accept counts 0, 10 and 50 as the complete diagnostic ladder for
`failure_learning / observed_precondition_v2`. Do not run count 100 or widen
the seed sample on this construct. Do not publish a framework ranking, formal
effect size, Failure Point, cost-efficiency result, or Native Minecraft claim.

If later research requires framework discrimination under failure transfer,
pre-register a new semantics version with causally plausible, answer-neutral
but task-similar failure distractors. That is a redesign decision, not an
extension of this ladder, and requires immutable code plus a separate A review.
