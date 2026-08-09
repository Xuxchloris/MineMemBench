# A-FINAL-017 — memory-noise v2 count-50 Controlled diagnostic audit

Date: 2026-08-08  
Reviewer: Agent A  
Evidence: TASK-016/017, B-COMPLETION-016, QA-016/017, raw manifest/results/logs  
Decision: **count-50 diagnostic accepted; noise effect, ranking and Failure Point not established**

## Critical

None.

## High

### H-1 — The evidence is not tied to an immutable reviewed revision

- **Location:** HEAD `cbaa276` plus 79 dirty entries;
  `results/stress_controlled_memory_noise_v2_count50_round1/`.
- **Reason:** the exact code state is not represented by a clean commit or code
  fingerprint; agents are prohibited from staging/committing/pushing.
- **Impact on conclusions:** **Yes.** This remains bounded diagnostic evidence,
  not a formal comparison, confidence interval or Failure Point.
- **Minimum repair:** repository owner creates a clean reviewed revision before
  a pre-registered formal sample; never relabel this smoke retroactively.

### H-2 — QA initially reported the Mem0 aggregate incorrectly (corrected)

- **Location:** `docs/agents/qa/QA-017.md` initial aggregate paragraphs.
- **Reason:** its correct detailed table had Mem0 `False/False/True`, but prose
  stated 2/3. A detected the arithmetic inconsistency; C re-read all 12 raw
  JSONs and corrected every conclusion-bearing aggregate to **1/3**, adding a
  correction note. No campaign/data/metric changed.
- **Impact on conclusions:** **Yes if uncorrected.** It would overstate Mem0
  success and corrupt downstream summaries. The accepted revision is correct.
- **Minimum repair:** **Completed.** Downstream work must use raw JSON plus the
  corrected QA revision; automated report aggregation remains preferable.

## Medium

### M-1 — Count 50 has no key-retention v2 control baseline yet

- **Location:** the single `noise_count=50` cell.
- **Reason:** target absence for Mem0/Letta could be caused by 50 noise facts,
  or could already occur at `noise_count=0` under this new opaque-key query and
  installed backend configuration. Historical delayed-recall cells are a
  different treatment and cannot serve as the control.
- **Impact on conclusions:** **Yes.** This round establishes behavior at count
  50, not degradation caused by added noise.
- **Minimum repair:** run the pre-planned `key_retention_v2/noise_count=0`
  three-seed control on the same backends and audit it separately before
  selecting the next ladder point.

### M-2 — The treatment measures exact opaque-key retention under volume

- **Location:** v2 goal and homogeneous key-to-coordinate event schema.
- **Reason:** the design cleanly isolates whether an exact key survives top-10
  retrieval as memory volume grows, but does not measure semantic similarity
  robustness or memory quality broadly.
- **Impact on conclusions:** **Yes for external validity only.**
- **Minimum repair:** report the construct by name and combine it later with
  delayed-recall/world-update/failure-learning evidence.

### M-3 — Backend feature and retrieval-budget differences remain disclosed

- **Location:** Mem0 stderr warnings; all memory backends return top 10 in this
  cell; raw add/retrieve latency fields.
- **Reason:** Mem0 optional spaCy/BM25 features are absent, and latency combines
  backend-internal work/initialization. Equal returned count helps this cell's
  rates, but installed configurations are not all possible framework setups.
- **Impact on conclusions:** **Potentially for general framework and efficiency
  claims; no for input equality or the observed installed-config behavior.**
- **Minimum repair:** pin/disclose features and normalize cost components before
  formal efficiency claims.

## Low

### L-1 — Fairness probe query has a uniform scenario-name prefix

- **Location:** `fairness.probe_query` in all 12 results.
- **Reason:** uniform pre-existing convention; diagnostic/reset probe only.
- **Impact on conclusions:** **No.** It is identical across backends and feeds
  no headline metric.
- **Minimum repair:** optional documentation cleanup; no rerun.

## Accepted evidence

The exact campaign ran once and produced 12/12 valid, linked results with no
retry, exclusion, contamination or missing log. For every seed, all 51 events
are identical across backends after normalizing only `episode_id`; controls,
reset/isolation and prompt/tool/model/template fingerprints match. C
independently re-derived every causal metric with zero mismatches. A also
recounted success directly from the raw results.

| backend | target rank by seed 42/43/44 | target recall | success |
|---|---|---|---:|
| none | N/A / N/A / N/A | 0 / 0 / 0 | 0/3 |
| vector | 1 / 1 / 1 | 1 / 1 / 1 | 3/3 |
| mem0 | N/A / N/A / 1 | 0 / 0 / 1 | 1/3 |
| letta | N/A / N/A / 4 | 0 / 0 / 1 | 1/3 |

Across memory-backed runs, target-present causal top-10 snapshots succeeded
**5/5**; target-absent snapshots failed **4/4**. NoMemory had empty retrieval
and failed 3/3. Letta seed44 succeeded with the target at rank4 despite a noise
item at top1, again showing the planner can use a below-top1 relevant fact.

The narrow supported conclusion is: **at key-retention v2 count50, whether the
target key-to-location event is available in the causal top10 perfectly tracks
behavior in these nine memory-backed runs.** This validates the scenario's
discriminative signal. It does not establish that noise caused the misses,
does not rank frameworks, and does not define a Failure Point.

Raw latency is descriptive only: vector add ~4.8ms/retrieve ~45.4ms; Mem0 add
~1008.9ms/retrieve ~14.8ms; Letta add ~337.1ms/retrieve ~216.8ms. Initialization
and backend-internal cost are not normalized.

## Next decision

Do not increase noise yet. Run exactly one separately released v2
`noise_count=0` three-seed control, then compare paired availability/behavior
to count50. No formal sample or other ladder point is authorized before A
reviews that control.
