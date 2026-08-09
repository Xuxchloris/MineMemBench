# A-FINAL-015 — world-update v2 depth-3 Controlled diagnostic audit

Date: 2026-08-08  
Reviewer: Agent A  
Evidence: TASK-013/014/015, QA-013/014/015, raw campaign JSON/logs  
Decision: **Controlled diagnostic accepted; Native/live-Minecraft evidence and formal ranking not approved**

## Critical

None.

## High

### H-1 — The evidence is not tied to an immutable reviewed revision

- **Location:** repository HEAD `cbaa276` with 72 dirty porcelain entries;
  `results/stress_controlled_world_update_v2_depth3_round1/`.
- **Reason:** the exact code that produced the 12 results is not represented by
  a clean commit SHA. The repository rules prohibit development agents from
  staging, committing or pushing.
- **Impact on conclusions:** **Yes.** This is auditable smoke evidence, not a
  reproducible formal comparison, publication result, confidence interval or
  Failure Point.
- **Minimum repair:** have the repository owner create a clean reviewed
  revision, record its SHA/code fingerprint, and pre-register a paired formal
  sample before making formal claims. Never retroactively relabel this round.

## Medium

### M-1 — This campaign is Controlled mock-fixture evidence, not Native Minecraft evidence

- **Location:** `docs/agents/tasks/TASK-015.md` (fresh mock adapter per run),
  `scripts/run_controlled_campaign.py:_spawn_bot`, manifest
  `runs[*].health_mode == "mock"`.
- **Reason:** the runner intentionally launched a fresh `BOT_MOCK=1` adapter
  for each cell. The live bot on 8081 and Minecraft on 25565 were only health
  checked and left untouched. This is the correct design for isolating the
  memory treatment, but the phrase "real evidence" means real measured
  Controlled data, not a real-world Minecraft execution.
- **Impact on conclusions:** **Yes for external validity; no for the accepted
  Controlled causal audit.** The round cannot establish behavior under Native
  Minecraft dynamics.
- **Minimum repair:** retain this round unchanged and run a separately named,
  pre-registered Native/live-Minecraft confirmation only after the Controlled
  ladder is stable. Never pool Controlled and Native results.

### M-2 — Current-fact recall already has a ceiling at depth 3

- **Location:** all nine memory-backed result JSONs in the campaign.
- **Reason:** vector, Mem0 and Letta retrieved current event D in 9/9 runs
  (`current_fact_recall=1`), while task success was only 5/9 and D rank ranged
  from 1 to 4. Every memory-backed retrieval also contained all four chain
  facts (`stale_memory_rate=0.75`). Thus availability of D is not sufficient
  for successful behavior, and depth 3 cannot locate a recall Failure Point.
- **Impact on conclusions:** **Yes.** The data show non-ceiling behavior at the
  action endpoint, but cannot distinguish the backends by current-fact recall
  or define a failure threshold.
- **Minimum repair:** after code/QA approval, smoke a pre-registered depth
  ladder with paired seeds and keep rank/top-1/stale action as causal
  endpoints. Do not expand sample size at depth 3 alone.

### M-3 — Cross-backend stale-fact rates have different denominators

- **Location:** `stale_fact_retrieval_rate` and retrieval-set sizes in the 12
  JSONs; vector returns 4 items, Mem0 8, Letta 9.
- **Reason:** all memory backends returned the same three stale chain events,
  but `stale_fact_retrieval_rate` divides by all retrieved items. Its values
  0.75/0.375/0.3333 mainly reflect backend top-k/result-set size, not stronger
  stale suppression. `stale_memory_rate=0.75` is the comparable within-chain
  quantity and is identical here.
- **Impact on conclusions:** **Yes if the raw rate is used to rank stale-memory
  handling; no for per-run metric correctness.**
- **Minimum repair:** report retrieved count and the two rates together; use
  rank/top-1 and within-chain stale rate for interpretation. Normalize the
  retrieval budget before any cross-framework precision claim.

### M-4 — Latency remains configuration-descriptive, not cost-normalized

- **Location:** campaign `avg_add_latency_ms` / `avg_retrieve_latency_ms`;
  Mem0 optional-feature stderr warnings.
- **Reason:** backend initialization, embeddings and internal service work are
  not decomposed; Mem0 ran without optional spaCy/BM25 features.
- **Impact on conclusions:** **Yes for efficiency and general deployment
  claims; no for event/input equality or behavioral measurements.**
- **Minimum repair:** pin and disclose the feature set, then record init,
  embedding/LLM and operation wall time separately before comparing cost.

## Low

### L-1 — CLI stdout uses stale display keys

- **Location:** campaign stdout logs, for example
  `logs/run_001_vector_depth3_temporal_chain_v2_seed42.stdout.log`.
- **Reason:** the human-readable summary prints legacy metric names and `??`
  labels although the JSON and manifest contain correct v2 fields.
- **Impact on conclusions:** **No.** C re-derived the JSON metrics with zero
  mismatches; this is a usability/audit-friction issue only.
- **Minimum repair:** B should make the summary scenario-aware in a later
  bounded maintenance task; do not rerun this campaign for display text.

## Accepted evidence

C executed the exact TASK-015 command once. The manifest contains 12/12 `ok`
runs with no retry, exclusion or duplicate. For each seed, the complete
nine-event stream is identical across backends after normalizing only
`episode_id`; reset/isolation, model, temperature, prompt/tool/template hashes
and fixture identity agree. C independently re-derived every causal retrieval
and behavioral metric from typed ground truth and the step-0 snapshot with
zero mismatches and found no cross-episode contamination.

Observed three-seed pattern (descriptive only):

| backend | current-D ranks | success | stale-memory rate |
|---|---|---:|---:|
| none | N/A / N/A / N/A | 0/3 | N/A |
| vector | 4 / 4 / 4 | 1/3 | 0.75 / 0.75 / 0.75 |
| mem0 | 4 / 3 / 1 | 2/3 | 0.75 / 0.75 / 0.75 |
| letta | 4 / 1 / 3 | 1/3 | 0.75 / 0.75 / 0.75 |

The narrow supported conclusion is: **under the depth-3 temporal-chain v2
Controlled treatment, memory availability changes the causal planner input,
but all three memory backends retrieved both the current and all stale chain
facts; correct-current recall alone did not guarantee correct behavior.** The
treatment avoids the earlier ceiling at the behavioral endpoint, but this
single 3-seed cell supports neither framework superiority nor a Failure Point.

The accidental TASK-014 QA calls remain excluded non-evidence. Legacy
world-update and delayed-recall rounds remain separate and must not be pooled.

## Next decision

TASK-015 is closed with no production-code repair. Continue M15 coverage by
redesigning `memory_noise_stress` into a Controlled, versioned treatment with
deterministic event identity, typed ground truth and causal step-0 metrics
before authorizing any noise ladder. The current legacy implementation is not
eligible for a Controlled campaign.
