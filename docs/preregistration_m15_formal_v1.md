# MineMemBench M15 Controlled Formal V1 preregistration

Status: **FROZEN DESIGN — no Formal run may start until the containing
Git freeze is clean, pushed, and independently verified by the TASK-027 gate.**

This document fixes the complete study and analysis before run 1. Calibration
selected the difficulty cells only; calibration data are never read, pooled,
or counted by the Formal analyzer.

## 1. Study identity

- Study id: `m15-formal-v1-controlled-20260811`
- Campaign mode: `controlled` only; Native is out of scope.
- Formal results root: `results/formal_m15_v1_20260811`
- Expected producer source fingerprint:
  `f21af111b86926aca18e77846e3b37f52d7b235facdc242daf0977a314ffc38a`
- Expected producer source-file count: `126`
- Review-owner source commit: the exact commit containing this preregistration,
  created with message `research: freeze M15 formal v1 preregistration`.
  A Git commit cannot contain its own SHA as file content. Therefore the exact
  SHA is resolved once, without amend, by `git rev-parse HEAD`, verified by
  `verify_source_freeze.py`, and written before run 1 into
  `formal_study_manifest.json`; every campaign and result must repeat it.
- Immutable baseline parent:
  `592e4ab72193fa541a1a536a1eab2752b03acad6`.
- Worktree requirement: clean at freeze and at every campaign boundary.
- Analysis entry point: `scripts/analyze_formal_m15.py`
- Analysis entry-point SHA-256:
  `904ae5f90b004792afdf5321c9f2423da3af11735a50f0532e98dbdcb6086b35`
- Analysis implementation: `benchmark/minemembench/evaluation/formal_m15.py`,
  included in the producer source fingerprint.
- Wire contract SHA-256:
  `7abe548a0dcd8d4b2382f70b8d0bf31d108d89bf3088db82186cf7fdbb0f7268`;
  `docs/protocol.md` is unchanged.

The producer manifest is authoritative for the resolved commit, fingerprint,
source count, Git clean/status identity, preregistration hash and analysis
entry-point hash. A mismatch stops the complete study.

## 2. Research question, hypotheses and scope

Primary question: in the current frozen MineMemBench configuration and
Controlled Formal V1, how do the configured long-term-memory backends affect
strict embodied task success under scenario-specific memory stress?

- Null hypothesis for each pre-registered active-backend pair and cell: the
  paired strict task-success probability is equal.
- Alternative: the paired probabilities differ (two-sided).
- Formal backends: `none`, `vector`, `mem0`, `letta`.
- Primary active-backend pairs: vector–mem0, vector–letta, mem0–letta.
- `none` is a descriptive no-long-term-memory baseline, not part of the primary
  active-backend multiplicity family.
- Graphiti, failure-learning v4, Native Minecraft, historical results and all
  calibration directories are excluded.
- No global “best memory framework” leaderboard is planned. Interpretation is
  scenario-, difficulty-, version- and configuration-specific.
- Lifetime is a composite difficulty. No event-count-only causal claim is
  permitted.
- Cost-efficiency, cross-environment generalization, multi-agent behavior and
  framework-wide superiority are out of scope.

## 3. Frozen design

### Backends and configurations

All access uses the unchanged `MemoryBackend` plugin contract. Planner,
scenario, fixture, prompt, temperature, tools, seeds and event stream are held
fixed within a treatment.

| backend | frozen configuration |
|---|---|
| `none` | `NoMemoryBackend`; accepts offered events but stores/retrieves none |
| `vector` | `VectorMemoryBackend`; campaign-local SQLite; deterministic 4096-dimension `HashEmbedder`; cosine top-k |
| `mem0` | `mem0ai==2.0.17`; `infer=False`; exact ExperienceEvent payload; HuggingFace `all-MiniLM-L6-v2`, 384 dimensions; campaign-local on-disk Qdrant collection `mem0`; telemetry disabled |
| `letta` | `letta-client==1.12.1`; `letta/letta:0.16.8@sha256:aa66c3eeee13d2dfc40c650d709b550237ee31bfc91942a52fa488a13fa8c102`; agent-scoped archival passages; exact ExperienceEvent payload tag; embedding service `ollama/ollama:latest@sha256:b88c73ace3e115f8ec53dc8761ae1c0aabfa675406e3681786b98757ce050f42`; model `ollama/nomic-embed-text:latest`; Letta is memory-only |

Each run receives a fresh backend instance. Vector/Mem0 stores live inside the
new campaign directory. Letta receives a fresh episode-scoped agent and the
post-run audit deletes/probes both completed and fresh scopes.

### Planner and query contract

- Planner model: `deepseek-v4-flash`
- Temperature: `0.0`
- Thinking: `disabled`
- LLM base-URL SHA-256:
  `12b8deaccc34b32757dbb1497e029da0c2e7b26ffa86b9c926c08cb4692f4508`
- System prompt hash:
  `a47e68a7c02da16e223886ac00bf35b94ca1b99ffae8b1718a0dc52d1d46ee60`
- Planner user template/schema hash:
  `988e01277f199fc0b8f48b1f57f7efe7da8bafd4ebd36267f509fc2af8b0df39`
- Tool-set hash:
  `936d9372e4cb68b4dbaaaffe9a46e72ba58a33e2d1f35bfbe324ce5da553b039`
- Retrieval limit: `10`
- MemoryQuery: backend-neutral goal text, current episode id, limit 10, no
  evaluator ground truth or backend-specific filters.
- Planner memory view: actor, target, event type, location, context, outcome,
  semantic timestamp, in backend retrieval order. IDs, score, backend metadata
  and evaluator-only fields are excluded.

### Fixtures

Delayed recall, world update and memory noise use selector `canonical` and
identity:

```text
mock-fixture-v1: spawn=(0,64,0) minecraft:overworld time_of_day=6000 clear inventory=[32x stone, 1x stone_sword] entities=[zombie@(3,64,4), player Steve@(1,64,2)]
```

Long-lived memory uses selector `lifetime_route_v1` and identity:

```text
mock-fixture-lifetime-route-v1: spawn=(0,64,0) minecraft:overworld time_of_day=6000 clear inventory=[32x stone, 1x stone_sword] visible_entities=[zombie@(3,64,4), player Steve@(1,64,2)] hidden_drop=[lifetime_token@(40,64,0)]
```

The fixture gate compares the complete visible WorldState except its volatile
timestamp. The process is fresh for every run. Recorded Minecraft version is
`unknown` and world seed is `null` because Controlled mock fixtures, not a
Native server world, define the environment.

### Exact treatment cells

| order | cell | scenario / semantics | exact parameters |
|---:|---|---|---|
| 1 | `delayed_200_20` | `delayed_recall / entity_key_v2` | `interference_count=200`, `similar_distractor_count=20` |
| 2 | `world_update_depth3` | `world_update / temporal_chain_v2` | `update_depth=3` (A→B→C→D) |
| 3 | `noise_10` | `memory_noise_stress / key_retention_v2` | `noise_count=10` |
| 4 | `noise_30` | same | `noise_count=30` |
| 5 | `noise_50` | same | `noise_count=50` |
| 6 | `lifetime_l1` | `long_lived_memory / lifetime_v1` | events=8, sessions=2, relevant updates=1, similar events=1 |
| 7 | `lifetime_l2` | same | events=20, sessions=4, relevant updates=2, similar events=5 |
| 8 | `lifetime_l3` | same | events=50, sessions=8, relevant updates=4, similar events=15 |

Every semantics-version key is an explicit effective parameter. No other
scenario parameter is permitted.

### Seeds, sample size and order

- Fresh paired seeds: `1001,1002,1003,1004,1005,1006,1007,1008,1009,1010`.
- N=10 per backend×cell.
- Expected runs: 8 cells × 4 backends × 10 seeds = `320`.
- Identical seeds are used for all four backends in every cell.
- Existing result history was searched before freeze and contains no use of
  seeds 1001–1010 for these treatments.
- The existing producer computes the complete seed-major schedule before run
  1, uses cyclic backend counterbalancing, and alternates cell order.
- Sample size never expands based on Formal outcomes.

## 4. Endpoints and evidence chain

Primary endpoint: strict `task_success`, derived by the objective scenario
evaluator from ordered WorldState/action/ActionResult evidence. The LLM never
judges its own success.

Secondary retrieval/behavior endpoints use the existing versioned contracts:

- delayed recall: target recall/rank/precision and off-target retrieval rate;
- world update: current-fact recall/rank/precision/top-1, stale-fact retrieval
  and stale action;
- memory noise: target recall/rank/precision/top-1 and noise retrieval rate;
- lifetime: first/any target recall, rank, retrieval mix, route utilization,
  ordered locate→collect→return→deliver evidence, invalid attempts and recovery;
- all cells: planner tokens/calls, memory add/retrieve latency and planner
  decision latency, descriptively only.

The causal chain retained for analysis is:

```text
Memory retrieval snapshot → planner/action selection → ActionResult → strict task outcome
```

Four retrieval/behavior combinations are reported: retrieval+success,
retrieval+failure, retrieval-absent+failure, retrieval-absent+success.

## 5. Validity, crash, retry and stopping policy

A valid run must satisfy all of the following:

- exact study commit/fingerprint/source count and clean Git identity;
- Controlled mode, registered backend/scenario and exact pre-registered cell;
- exact seed, planner model, temperature, prompt/template/tool hashes;
- exact fixture selector/identity and complete fixture gate;
- producer status `ok`, return code 0, one linked parseable ScenarioResult;
- `fairness.valid=true`, completed-episode reset performed without error,
  post-reset items=0 and fresh-scope items=0;
- unique manifest key, episode id, run id and physical result file;
- same normalized ExperienceEvent stream across all backends for one
  seed/treatment;
- NoMemory has no causal or diagnostic long-term retrieval;
- stored retrieval and strict-success metrics independently recompute.

An invalid run is any failure of these conditions. A normal `task_success=0`
with a valid producer/fairness record is a valid experimental outcome, not an
invalid run.

- Missing result/log: integrity failure; stop the study.
- Duplicate or unexpected result: integrity failure; stop the study.
- LLM/backend/bot crash or producer non-zero return: retain evidence and stop
  the whole study.
- Retry/replacement policy: none. No run is retried or replaced.
- Exclusion policy: none after run 1. Invalid evidence is reported and the
  study stops; it is not silently removed from a denominator.
- Stopping rule: finish exactly 320 planned runs, or stop immediately on an
  integrity failure. Normal failures, unflattering results, significance and
  variance do not stop or extend the study.
- If an integrity defect requires a fix, the existing Formal identity is
  abandoned. A new commit, study id, preregistration and empty results root
  are required; old and new data are never spliced.

## 6. Failure attribution

Failed valid runs are classified automatically without LLM reason text:

- `R` Retrieval: the ground-truth relevant event is absent from the causal
  retrieval snapshot(s).
- `P` Planning/action selection: relevant memory is present, but no
  stage-correct objective action is selected/completed.
- `E` Environment/execution: a stage-correct objective action is selected,
  but its recorded status is failed/timeout.
- `Unknown`: evidence is insufficient for R/P/E.

Simple coordinate scenarios use the typed ground-truth event location and
ordered move actions. Lifetime uses the typed pickup/recipient truth and
ordered locate→collect→return→deliver state machine. Attribution is secondary
and conservative.

## 7. Failure Point

Failure Point is calculated only for memory noise `10→30→50` and composite
lifetime `L1→L2→L3`. It is the first tested level with strict task success
rate `<80%`. With N=10, 8/10 is not a failure and 7/10 is. No interpolation is
allowed. If all tested levels are ≥80%, report:
`Failure Point not observed within tested ladder`.

## 8. Frozen statistical analysis

- Aggregation unit: one seed-paired run per backend×cell.
- Primary active-backend comparisons per cell: vector vs mem0, vector vs
  letta, mem0 vs letta (24 comparisons total).
- Test: two-sided exact McNemar, reporting both discordant directions.
- Effect size: paired risk difference, first named backend minus second.
- 95% CI: paired percentile bootstrap, RNG reset for each comparison,
  seed `20260811`, `10,000` resamples, linear/R-7 quantiles.
- Multiplicity: Holm-Bonferroni over the full family of 24 primary pairwise
  comparisons; alpha `0.05`.
- Report success n/N, success rate, risk difference, CI, discordant pairs,
  raw exact p and Holm-adjusted p. P-values are never reported alone.
- No global ranking, outcome-dependent subgroup, seed extension, interpolation
  or post-hoc primary endpoint.
- Tokens/latency are descriptive because backend-internal work is not
  normalized. No cost-efficiency inference is allowed.

The analyzer reads only the specified Formal root, validates the study and all
raw campaign evidence fail-closed, and writes:

- `formal_summary.json`
- `formal_runs.csv`
- `formal_cells.csv`
- `formal_pairwise.csv`
- `formal_failure_points.csv`
- `formal_failure_attribution.csv`
- `formal_report.md`
- `formal_success_curves.svg`
- `formal_retrieval_curves.svg`

Synthetic tests fixed before run 1 cover all success, all failure, paired
disagreement, missing/duplicate seed, wrong commit/fingerprint/cell,
fairness-invalid evidence, R/P/E attribution, absent/first/middle Failure
Points, Holm correction, deterministic bootstrap and all required outputs.

## 9. Authorization and pre-Formal gate

TASK-027 explicitly authorizes this exact two-freeze workflow. Before run 1,
`docs/agents/reviews/A-PREFLIGHT-027.md` must record PASS for:

- completed preregistration and exact campaign plan;
- analysis implementation and synthetic tests;
- full Python tests, TypeScript tests and TypeScript build;
- `git diff --check` and secret/path audit;
- strict live Letta add/retrieve/update/reset/fresh-scope verification;
- Controlled fixture and reset/isolation tests;
- clean pushed preregistration commit and strict source-freeze verification;
- new/empty Formal root and Formal runs started=0.

Only after every item passes may `scripts/run_formal_m15_v1.py` execute once.
