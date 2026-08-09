# A-FINAL-018 — memory-noise v2 count-0 control and paired diagnostic audit

Date: 2026-08-08  
Reviewer: Agent A  
Evidence: corrected QA-017, QA-018, raw count0/count50 manifests/results/logs  
Decision: **count0 control and paired diagnostic accepted; formal noise Failure Point not approved**

## Critical

None.

## High

### H-1 — Both cells remain non-immutable smoke evidence

- **Location:** HEAD `cbaa276` with 81 dirty entries; count0/count50 result
  directories.
- **Reason:** no clean reviewed revision/code fingerprint represents the exact
  producer state; agents may not stage, commit or push.
- **Impact on conclusions:** **Yes.** The paired pattern is diagnostic only,
  without publication-level reproducibility, confidence intervals or a formal
  Failure Point.
- **Minimum repair:** owner-created clean reviewed revision followed by a
  pre-registered paired formal sample. Keep current rounds labeled smoke.

## Medium

### M-1 — Three paired seeds locate a signal, not a stable threshold

- **Location:** count0/count50 cells, seeds 42/43/44.
- **Reason:** Mem0 and Letta each change from target-present/success 3/3 at
  count0 to 1/3 at count50. This is internally consistent and paired, but the
  sample is too small to estimate a population rate or apply the formal <80%
  Failure Point rule.
- **Impact on conclusions:** **Yes.** Count50 is an informative stress point,
  not an approved framework failure threshold.
- **Minimum repair:** smoke the pre-planned count10 point next to bracket the
  transition, then A pre-registers a larger paired sample on the informative
  band after an immutable revision exists.

### M-2 — Installed backend configuration and exact-key construct bound generality

- **Location:** key-retention v2 events/goal; Mem0 optional spaCy/BM25 warnings.
- **Reason:** the treatment measures exact opaque-key top10 retention under
  homogeneous volume, and Mem0 runs without optional lexical features.
- **Impact on conclusions:** **Yes for broad framework claims; no for the
  observed installed-configuration contrast.**
- **Minimum repair:** disclose/pin features and combine later with other valid
  scenario constructs; treat any feature change as a new configuration.

### M-3 — Latency cannot be compared as efficiency

- **Location:** count0/count50 add/retrieve/end-to-end latency.
- **Reason:** one-add count0 is initialization dominated, while count50
  averages initialization over 51 adds; internal LLM/embedding work is not
  decomposed.
- **Impact on conclusions:** **Yes for efficiency comparisons, no for causal
  recall/behavior.**
- **Minimum repair:** separate initialization and per-operation costs before
  formal cost claims.

## Low

- Uniform scenario-name prefix in reset/fairness probe query is cosmetic and
  feeds no headline metric.
- Corrected QA-017 must remain the source for count50 summaries; the original
  Mem0 2/3 arithmetic typo is superseded and must not propagate.

## Accepted paired finding

TASK-018 ran once and produced 12/12 valid count0 results. C verified identical
per-seed streams, fairness/reset isolation, typed ground truth, causal step0
metrics, logs and N/A handling with zero mismatches. Count0 outcomes:

- NoMemory: empty retrieval, 0/3 success;
- vector, Mem0 and Letta: target rank1/top1 in every run, each 3/3 success.

Paired against the corrected count50 raw results:

| backend | count0 target present / success | count50 target present / success |
|---|---|---|
| vector | 3/3 / 3/3 | 3/3 / 3/3 |
| mem0 | 3/3 / 3/3 | 1/3 / 1/3 |
| letta | 3/3 / 3/3 | 1/3 / 1/3 |
| none | 0/3 / 0/3 | 0/3 / 0/3 |

Across both cells, all 14 memory-backed target-present runs succeeded and all
four target-absent memory runs failed. The planned manipulation changed only
noise volume within the same versioned treatment; model, temperature,
prompt/tools/template, fixture, seeds and backend identities remained fixed.

The narrow supported conclusion is: **for this three-seed Controlled
diagnostic, adding 50 homogeneous key-to-location facts is associated with
loss of the target from causal top10 for Mem0 and Letta on seeds 42/43, while
vector retains it; behavior continues to track target availability exactly.**
This is preliminary paired evidence of noise sensitivity in the installed
configurations, not a framework ranking, statistical effect estimate or
Failure Point.

## Next decision

The next useful point is the pre-planned count10 smoke, which can tell whether
the observed transition occurs at the first non-control step or between 10 and
50. Do not run count100/200/500/1000 or a formal sample before that bounded
task is separately specified and released.
