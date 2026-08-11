# MineMemBench M15 Controlled Formal V1 preregistration — attempt 2

Status: **FROZEN CANDIDATE — no Formal run may start until the containing Git
freeze is clean, pushed, and every attempt-2 preflight gate passes.**

This document fixes the complete attempt-2 study and analysis before run 1.
It does not modify the treatment definitions, primary endpoint or statistical
plan frozen for attempt 1. Attempt 1 stopped on an external planner-DNS
producer failure and is permanently abandoned; its raw evidence is retained
but never retried, resumed, pooled, analyzed, or used to select attempt-2
parameters. The incident is recorded in
`docs/agents/reviews/A-INCIDENT-027-ATTEMPT1.md`.

## 1. Study identity

- Study id: `m15-formal-v1-controlled-20260811-attempt2`
- Campaign mode: `controlled` only; Native is out of scope.
- Formal results root: `results/formal_m15_v1_20260811_attempt2`
- Expected producer source fingerprint:
  `ebfe9172dbe83abb5d76c2f8459ef346b8888d4f8e2bafca4d09799566bad3b3`
- Expected producer source-file count: `126`
- Review-owner source commit: the exact clean commit containing this
  preregistration and `A-PREFLIGHT-027-ATTEMPT2.md`, created with message
  `research: freeze M15 formal v1 attempt 2`. A commit cannot contain its own
  SHA, so the SHA is resolved once without amend, verified by
  `verify_source_freeze.py`, and written before run 1 into
  `formal_study_manifest.json`; every campaign and result must repeat it.
- Recovery parent: attempt-1 freeze commit
  `7c96df88c4208e47217da984f61798be051f56da`.
- Immutable TASK-026 baseline:
  `592e4ab72193fa541a1a536a1eab2752b03acad6`.
- Worktree requirement: clean at freeze and every campaign boundary.
- Analysis entry point: `scripts/analyze_formal_m15.py`
- Analysis entry-point SHA-256:
  `904ae5f90b004792afdf5321c9f2423da3af11735a50f0532e98dbdcb6086b35`
- Analysis implementation: `benchmark/minemembench/evaluation/formal_m15.py`,
  included in the producer source fingerprint.
- Wire contract SHA-256:
  `7abe548a0dcd8d4b2382f70b8d0bf31d108d89bf3088db82186cf7fdbb0f7268`;
  `docs/protocol.md` is unchanged.

The producer manifest is authoritative for commit, source fingerprint, source
count, Git clean/status identity, preregistration hash, analysis entry-point
hash, expected/successful/started run counts and stop reason. Any mismatch
stops the complete attempt.

## 2. Recovery boundary

Attempt 1 (`m15-formal-v1-controlled-20260811`) used seeds 1001–1010 and
stopped with 271 producer-ok, one producer-failed and 48 pending slots. Its
analyzer failed closed before outputs. No attempt-1 task outcome, comparison,
effect, Failure Point or ranking was inspected or used for this design.

Attempt 2 is a new prospective study, not a continuation:

- new identity, root, preregistration, producer commit and source fingerprint;
- fresh paired seeds 1011–1020, absent from all historical JSON evidence at
  freeze-candidate audit time;
- the same eight treatment cells, N=10, four backends and Controlled fixtures;
- no attempt-1 result file is discoverable by the attempt-2 analyzer;
- attempt-1 evidence remains untouched under its original root.

## 3. Research question, hypotheses and scope

Primary question: in the current frozen MineMemBench configuration and
Controlled Formal V1, how do the configured long-term-memory backends affect
strict embodied task success under scenario-specific memory stress?

- Null hypothesis for each preregistered active-backend pair and cell: paired
  strict task-success probability is equal.
- Alternative: paired probabilities differ (two-sided).
- Formal backends: `none`, `vector`, `mem0`, `letta`.
- Primary active-backend pairs: vector–mem0, vector–letta, mem0–letta.
- `none` is a descriptive no-long-term-memory baseline and is not in the
  active-backend multiplicity family.
- Graphiti, failure-learning v4, Native Minecraft, historical results,
  calibration and attempt 1 are excluded.
- No global “best memory framework” leaderboard is planned. Interpretation is
  scenario-, difficulty-, version- and configuration-specific.
- Lifetime is composite difficulty; no event-count-only causal claim is
  permitted.
- Cost efficiency, cross-environment generalization, multi-agent behavior and
  framework-wide superiority are out of scope.

## 4. Frozen design

### Backends and configurations

All access uses the unchanged `MemoryBackend` plugin contract. Planner,
scenario, fixture, prompt, temperature, tools, seeds and event stream are held
fixed within a treatment.

| backend | frozen configuration |
|---|---|
| `none` | `NoMemoryBackend`; accepts offered events but stores/retrieves none |
| `vector` | `VectorMemoryBackend`; campaign-local SQLite; deterministic 4096-dimension `HashEmbedder`; cosine top-k |
| `mem0` | `mem0ai==2.0.17`; `infer=False`; exact ExperienceEvent payload; HuggingFace `all-MiniLM-L6-v2`, 384 dimensions; campaign-local on-disk Qdrant collection `mem0`; telemetry disabled |
| `letta` | `letta-client==1.12.1`; `letta/letta:0.16.8@sha256:aa66c3eeee13d2dfc40c650d709b550237ee31bfc91942a52fa488a13fa8c102`; agent-scoped archival passages; exact ExperienceEvent payload tag; `ollama/ollama:latest@sha256:b88c73ace3e115f8ec53dc8761ae1c0aabfa675406e3681786b98757ce050f42`; `ollama/nomic-embed-text:latest`; Letta is memory-only |

Each run receives a fresh backend instance. Vector/Mem0 stores live in the new
campaign directory. Letta receives a fresh episode-scoped agent, and the
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
  evaluator ground truth or backend-specific filter.
- Planner memory view: actor, target, event type, location, context, outcome
  and semantic timestamp in backend retrieval order. IDs, score, backend
  metadata and evaluator-only fields are excluded.

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

The fixture gate compares complete visible WorldState except its volatile
timestamp. Every run has a fresh process. Recorded Minecraft version is
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

- Fresh paired seeds: `1011,1012,1013,1014,1015,1016,1017,1018,1019,1020`.
- N=10 per backend×cell.
- Expected runs: 8 cells × 4 backends × 10 seeds = `320`.
- Identical seeds are used for all four backends in each cell.
- Candidate audit found no historical JSON record with seeds 1011–1020.
- The producer computes the complete seed-major schedule before run 1, uses
  cyclic backend counterbalancing and alternates cell order.
- Sample size never expands based on outcomes.

## 5. Endpoints and evidence chain

Primary endpoint: strict `task_success`, derived by the objective scenario
evaluator from ordered WorldState/action/ActionResult evidence. The LLM never
judges its own success.

Secondary retrieval/behavior endpoints use existing versioned contracts:

- delayed recall: target recall/rank/precision and off-target retrieval rate;
- world update: current-fact recall/rank/precision/top-1, stale-fact retrieval
  and stale action;
- memory noise: target recall/rank/precision/top-1 and noise retrieval rate;
- lifetime: first/any target recall, rank, retrieval mix, route utilization,
  ordered locate→collect→return→deliver evidence, invalid attempts and recovery;
- all cells: planner tokens/calls, memory add/retrieve latency and planner
  decision latency, descriptively only.

The retained causal chain is:

```text
Memory retrieval snapshot → planner/action selection → ActionResult → strict task outcome
```

Four retrieval/behavior combinations are reported: retrieval+success,
retrieval+failure, retrieval-absent+failure and retrieval-absent+success.

## 6. Validity, crash, retry and stopping policy

A valid run must satisfy all of the following:

- exact study commit/fingerprint/source count and clean Git identity;
- Controlled mode, registered backend/scenario and exact preregistered cell;
- exact seed, planner model, temperature, prompt/template/tool hashes;
- exact fixture selector/identity and complete fixture gate;
- producer status `ok`, return code 0 and one linked parseable ScenarioResult;
- `fairness.valid=true`, completed-episode reset without error,
  post-reset items=0 and fresh-scope items=0;
- unique manifest key, episode id, run id and physical result file;
- same normalized ExperienceEvent stream across all backends for one
  seed/treatment;
- NoMemory has no causal or diagnostic long-term retrieval;
- stored retrieval and strict-success metrics independently recompute.

A normal `task_success=0` with a valid producer/fairness record is a valid
outcome, not an invalid run.

- Missing result/log, duplicate/unexpected evidence, source mismatch,
  contamination, reset leakage or fixture/prompt mismatch: stop the study.
- LLM/backend/bot crash or producer non-zero return: retain evidence and stop
  the whole study.
- Retry/replacement policy: none. No run is retried or replaced.
- Exclusion policy: none after run 1. Invalid evidence is reported, never
  silently removed from a denominator.
- Stopping rule: finish exactly 320 planned runs, or stop immediately on an
  integrity/producer failure. Normal task failures, unflattering results,
  significance and variance do not stop or extend the study.
- A stopped attempt is abandoned. Any further attempt requires a new commit,
  study id, preregistration, fresh seeds and empty root. Data are never spliced.

Root and child manifests must agree on 320 scheduled slots and separately
record producer-ok, producer-failed, pending and started counts. A producer
failure must have an explicit stop reason.

## 7. Failure attribution

Failed valid runs are classified without LLM reason text:

- `R` Retrieval: ground-truth relevant event absent from causal retrieval.
- `P` Planning/action selection: relevant memory present, but no stage-correct
  objective action is selected/completed.
- `E` Environment/execution: stage-correct action selected but recorded
  failed/timeout.
- `Unknown`: evidence insufficient for R/P/E.

Simple-coordinate scenarios use typed target location and ordered move
actions. Lifetime uses typed pickup/recipient truth and ordered
locate→collect→return→deliver state. Attribution is secondary and conservative.

## 8. Failure Point

Failure Point is calculated only for memory noise `10→30→50` and composite
lifetime `L1→L2→L3`. It is the first tested level with strict task success
rate `<80%`. With N=10, 8/10 is not a failure and 7/10 is. There is no
interpolation. If all levels are ≥80%, report:
`Failure Point not observed within tested ladder`.

## 9. Frozen statistical analysis

- Aggregation unit: one seed-paired run per backend×cell.
- Primary comparisons: vector–mem0, vector–letta and mem0–letta per cell (24).
- Test: two-sided exact McNemar with both discordant directions.
- Effect: paired risk difference, first backend minus second.
- 95% CI: paired percentile bootstrap, RNG reset per comparison, seed
  `20260811`, `10,000` resamples and linear/R-7 quantiles.
- Multiplicity: Holm–Bonferroni over all 24 primary comparisons, alpha `0.05`.
- Report success n/N, rate, risk difference, CI, discordant pairs, raw exact p
  and Holm-adjusted p. P-values are never reported alone.
- No global ranking, outcome-dependent subgroup, extension, interpolation or
  post-hoc primary endpoint.
- Tokens/latency are descriptive; no cost-efficiency inference is permitted.

The analyzer reads only the specified attempt-2 root, validates all identity,
schedule, provenance, fairness, reset, fixture, event-stream and endpoint
evidence fail-closed, and writes only after integrity PASS:

- `formal_summary.json`
- `formal_runs.csv`
- `formal_cells.csv`
- `formal_pairwise.csv`
- `formal_failure_points.csv`
- `formal_failure_attribution.csv`
- `formal_report.md`
- `formal_success_curves.svg`
- `formal_retrieval_curves.svg`

Synthetic tests fixed before run 1 cover success/failure, paired disagreement,
missing/duplicate/wrong identity/cell/fairness evidence, R/P/E, Failure Points,
Holm, deterministic bootstrap, all outputs, exact 320-run schedule, failed-run
attempt accounting and wrong-freeze rejection.

## 10. Pre-Formal gate and authorization

`docs/agents/reviews/A-PREFLIGHT-027-ATTEMPT2.md` must record PASS before run 1
for:

- this complete preregistration and exact campaign plan;
- analysis implementation and synthetic tests;
- full Python tests, TypeScript tests and TypeScript build;
- `git diff --check`, secret/path audit and unchanged `docs/protocol.md`;
- strict live Letta add/retrieve/update/reset/fresh-scope verification;
- Controlled fixtures and reset/isolation;
- repeated DNS resolution plus live planner connectivity checks;
- clean pushed attempt-2 freeze and strict source verification;
- new/empty attempt-2 root and runs started=0;
- preserved, excluded attempt-1 root and evidence hashes.

TASK-027's recovery rule requires a new commit, study identity,
preregistration and empty root after the stopped attempt. Only after every gate
passes may `scripts/run_formal_m15_v1.py` execute once for attempt 2. Failure
again stops the study without retry, resume or replacement.
