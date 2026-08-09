# A-FINAL-019 — memory-noise v2 count-10 and 0/10/50 audit

Date: 2026-08-08  
Reviewer: Agent A  
Evidence: corrected QA-017, QA-018/019, raw count0/count10/count50 results  
Decision: **three-point diagnostic accepted; transition bracketed, formal Failure Point not approved**

## Critical

None.

## High

### H-1 — Results remain tied to a dirty, non-immutable code state

- **Location:** HEAD `cbaa276` with 83 dirty entries; three result directories.
- **Reason:** no clean reviewed revision/code fingerprint represents the exact
  producer state; agents cannot stage/commit/push.
- **Impact on conclusions:** **Yes.** These are diagnostics, not formal
  framework rankings, confidence intervals or Failure Points.
- **Minimum repair:** owner creates a clean reviewed revision before a
  pre-registered paired formal band sample.

## Medium

### M-1 — The transition is bracketed only at three smoke points

- **Location:** key-retention v2 counts 0, 10 and 50; seeds 42/43/44.
- **Reason:** Mem0 and Letta retain the target in all three count10 runs but
  lose it for seeds42/43 at count50. Three paired seeds establish a useful
  interval, not a stable rate or threshold estimate.
- **Impact on conclusions:** **Yes.** The interval `(10,50]` is a diagnostic
  bracket, not a formal failure point under the experiment standard's <80%
  rule.
- **Minimum repair:** after an immutable revision, pre-register additional
  paired seeds and, if needed, an intermediate difficulty within the approved
  band. Do not adaptively mine more points now.

### M-2 — Rank deterioration precedes target absence

- **Location:** Mem0 count10 ranks `4/5/1`; Letta `1/7/1`; both are rank1 at
  count0 and absent/absent/present at count50.
- **Reason:** binary success remains 3/3 at count10 because the planner can use
  below-top1 evidence. A success-only report would hide the early degradation.
- **Impact on conclusions:** **Yes for stress interpretation.**
- **Minimum repair:** retain rank/top1/target presence as co-primary diagnostic
  endpoints in any formal band study; never infer robustness from success
  alone.

### M-3 — Construct/configuration/cost boundaries remain

- **Location:** opaque-key treatment, Mem0 optional-feature warnings, raw
  latency metrics.
- **Reason:** the task measures exact-key top10 retention for installed
  configurations; latency mixes initialization/internal work.
- **Impact on conclusions:** **Yes for broad memory-quality and efficiency
  claims; no for this paired installed-config observation.**
- **Minimum repair:** pin/disclose features and separately account for init,
  internal model/embedding calls and per-operation time before formal claims.

## Low

- Uniform scenario-name prefix in the fairness probe is cosmetic and does not
  feed headline metrics.
- Corrected QA-017 is the only accepted count50 summary; the superseded Mem0
  2/3 typo must never be copied.

## Accepted evidence

TASK-019 ran once and produced 12/12 valid count10 results. C verified
manifest, fairness, resets, 11-event input equality, typed ground truth,
causal step0 metrics, logs and 0/10/50 aggregates programmatically with zero
mismatches.

| backend | count0 | count10 | count50 |
|---|---|---|---|
| none | 0/3, empty | 0/3, empty | 0/3, empty |
| vector | 3/3, rank 1/1/1 | 3/3, rank 1/1/1 | 3/3, rank 1/1/1 |
| mem0 | 3/3, rank 1/1/1 | 3/3, rank 4/5/1 | 1/3, rank N/A/N/A/1 |
| letta | 3/3, rank 1/1/1 | 3/3, rank 1/7/1 | 1/3, rank N/A/N/A/4 |

Across the three cells, every target-present memory run succeeded and every
target-absent memory run failed. Count10 demonstrates that the planner can use
relevant evidence below top1; count50 shows target loss from causal top10 for
Mem0/Letta on seeds42/43.

The supported conclusion is: **in this three-seed Controlled diagnostic, the
installed Mem0/Letta configurations begin showing rank degradation by count10
and target-availability/behavior loss by count50; the observed transition is
bracketed in `(10,50]`, while vector remains at rank1 through count50.** This
does not rank frameworks or define a formal Failure Point.

## Next decision

Stop expanding memory-noise. The next M15 coverage gap is a valid
failure-learning transfer treatment derived from a real failed ActionResult.
The current same-task retry and suspended fabricated-tool scenario remain
research-invalid for transfer claims.
