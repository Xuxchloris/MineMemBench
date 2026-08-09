# TASK-026 M15.1 bounded difficulty calibration

Date: 2026-08-09
Owner: Agent A
Independent audit: Agent C
Status: **complete diagnostic calibration; no formal experiment authorized**

## 1. Evidence boundary

Every accepted cell uses paired seeds `42/43/44` and backends
`none/vector/mem0/letta`. Runs are real, unretried and unexcluded. These data
select informative treatments; they do not estimate effects or rank
frameworks.

The lifetime/noise campaigns were produced by the earlier dirty TASK-026
implementation identity:

```text
commit=9fdced8fa9967a6df7b856b035485b41e84c06dc
source_tree_fingerprint=2af9dbdcaa25c8a52286b264e2532e06ea74c66eff186a45a4740dbcce38ae52
source_file_count=122
git_dirty=true
```

The accepted heterogeneous applicability campaign records the final reviewed
producer identity:

```text
commit=9fdced8fa9967a6df7b856b035485b41e84c06dc
source_tree_fingerprint=86c625f9a130be3b5a81c3ed7ca48db9eb128493eb703ac98ca905a2bb9fd3f6
source_file_count=122
git_dirty=true
planner_model=deepseek-v4-flash
temperature=0
```

Dirty-tree provenance makes every campaign diagnostic only. A clean freeze
and separately frozen preregistration are still mandatory before formal work.

## 2. Raw directories and disposition

| Treatment | Runs | Disposition |
|---|---:|---|
| `long_lived_memory / lifetime_v1` | 36 | `results/calibration_task026_lifetime_v1_20260809/`; retained pre-terminal-fix construct diagnostic |
| `memory_noise_stress / key_retention_v2` | 36 | `results/calibration_task026_noise_v2_20260809/`; accepted dirty-tree diagnostic |
| homogeneous `failure_learning_multi / observed_precondition_multi_v3` | 24 | `results/calibration_task026_failure_multi_v3_20260809/`; superseded construct, never pool with v4 |
| first applicability-v4 run | 24 | `results/calibration_task026_failure_applicability_v4_20260809/`; superseded because post-terminal actions contaminate horizon/cost |
| terminal-corrected applicability-v4 | 24 | `results/calibration_task026_failure_applicability_v4_terminal_v1_20260809/`; accepted diagnostic |

The v3 events are real failures but all share one gold prerequisite, so v3
cannot measure applicability among heterogeneous experiences. The first v4
campaign is honest and complete, but successful runs continued to the five
step budget after target completion; its success/retrieval values are useful
only for debugging and no cost/horizon result may be pooled from it.

## 3. Lifetime axis

Entries are `primary-success / target-recall / deterministic-route-use`, each
out of three.

| Cell `(events,sessions,updates,similar)` | None | Vector | Mem0 | Letta |
|---|---:|---:|---:|---:|
| `(8,2,1,1)` | `0/0/0` | `1/3/3` | `3/3/3` | `3/3/3` |
| `(20,4,2,5)` | `0/0/0` | `0/0/0` | `3/3/3` | `3/3/3` |
| `(50,8,4,15)` | `0/0/0` | `0/0/0` | `3/3/3` | `3/3/3` |

The 8-event cell is an active-backend retrieval ceiling but not a strict
behavior ceiling: two Vector runs delivered before the recipient was visible,
then recovered. At 20 and 50 events Vector loses the early target in all six
runs while Mem0/Letta retain and use it in all tested runs. This brackets a
useful lifetime discrimination treatment, not a framework ranking.

These files predate the objective terminal-step correction. Primary success,
causal retrieval and strict action-order evidence occur before terminal
delivery and remain valid construct diagnostics; their post-delivery step,
token and latency totals are superseded. Current code now stops at completed
delivery and has independent unit/C QA, but no current-source lifetime formal
claim is made.

## 4. Memory-volume axis

Entries are `primary-success / target-recall / deterministic-use`, each out
of three.

| Noise count | None | Vector | Mem0 | Letta | Region |
|---:|---:|---:|---:|---:|---|
| 10 | `0/0/0` | `3/3/3` | `3/3/3` | `3/3/3` | active-backend ceiling |
| 30 | `0/0/0` | `3/3/3` | `2/2/2` | `3/3/3` | discrimination |
| 50 | `0/0/0` | `3/3/3` | `1/1/1` | `1/1/1` | shared retrieval-failure region |

The smallest predefined set `{10,30,50}` identifies ceiling,
discrimination and shared failure regions, so the campaign correctly stopped
without burning 20/40/60 or 100–1000 cells. The observed target-loss boundary
is diagnostic, not a formal Failure Point.

## 5. Heterogeneous applicability-v4 axis

The accepted campaign uses `interference_count=10`, one applicable real
source failure and either one or two inapplicable real failures. Opaque
families use the non-ordinal mapping alpha→iron, beta→string, gamma→gold.

All 24 runs are producer-ok, fairness/reset-valid and independently
recomputed. Six same-seed/cell groups have identical normalized
ExperienceEvent streams and source ActionResults across backends. NoMemory's
causal and diagnostic retrievals are empty. Every source failure is a real
failed environment ActionResult, and evaluation-only mapping/applicability
fields never enter planner-visible evidence.

### Primary and diagnostic outcomes

`Rel.` is the number of runs retrieving the applicable failure; every active
retrieval is rank 1. `Irr.` is the mean count of inapplicable source failures
retrieved.

| Failures | Backend | Success | Rel. | Irr. | Wrong prep | Repeat | Recovery | Mean steps |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | none | 0/3 | 0/3 | 0 | 3/3 | 3/3 | 0/3 | 5.00 |
| 2 | vector | 2/3 | 3/3 | 1 | 1/3 | 1/3 | 1/3 | 2.67 |
| 2 | mem0 | 3/3 | 3/3 | 1 | 0/3 | 0/3 | 0/3 | 2.00 |
| 2 | letta | 3/3 | 3/3 | 1 | 0/3 | 0/3 | 0/3 | 2.00 |
| 3 | none | 0/3 | 0/3 | 0 | 3/3 | 3/3 | 0/3 | 5.00 |
| 3 | vector | 3/3 | 3/3 | 2 | 0/3 | 0/3 | 0/3 | 2.00 |
| 3 | mem0 | 3/3 | 3/3 | 2 | 0/3 | 0/3 | 0/3 | 2.00 |
| 3 | letta | 3/3 | 3/3 | 2 | 0/3 | 0/3 | 0/3 | 2.00 |

All 18 completed target attacks are the final RunLog step. Seventeen are
strict primary successes. The single recovery is Vector, two-failure seed 42:
the applicable failure is retrieved at rank 1, the planner equips the wrong
item and repeats the environment failure, then equips correctly and completes
the target attack. Primary success stays false. This is the required
`retrieval correct → behavior wrong` evidence.

### Operational measurements

Measurements are descriptive pathology checks only; they do not include a
normalized accounting of backend-internal embedding/LLM work.

| Failures | Backend | Mean tokens | Mean LLM ms | Mean retrieve ms |
|---:|---|---:|---:|---:|
| 2 | none | 7,238.7 | 4,393.7 | N/A |
| 2 | vector | 4,429.3 | 2,551.0 | 10.999 |
| 2 | mem0 | 4,531.0 | 2,124.2 | 14.639 |
| 2 | letta | 4,536.3 | 2,167.4 | 187.857 |
| 3 | none | 7,221.0 | 4,532.4 | N/A |
| 3 | vector | 3,510.3 | 2,034.4 | 11.934 |
| 3 | mem0 | 4,658.3 | 1,924.6 | 13.433 |
| 3 | letta | 4,664.7 | 1,880.2 | 197.809 |

The shorter successful runs explain lower planner tokens; these values are not
framework cost-efficiency estimates.

## 6. Failure attribution

- **R — Retrieval:** NoMemory never retrieves the applicable event and fails
  all six tasks. Lifetime Vector at 20/50 events and the noise losses listed
  above are also diagnostic R failures.
- **P — Planning:** applicability-v4 Vector, failures=2 seed 42 retrieves the
  applicable event at rank 1 but chooses the wrong preparation before its
  first attack, then recovers. Lifetime smoke's premature delivery cases are
  also strict-order P failures.
- **U — Utilization:** no separately identifiable U-only failure was observed;
  the v4 wrong action is directly observable and classified P.
- **E — Environment/execution:** no adapter/backend crash or environment-root
  failure was observed.
- **Unknown:** none in the accepted v4 campaign.

## 7. Region and stopping decision

- NoMemory is a clear v4 failure/floor region.
- Active v4 backends have a relevant-retrieval ceiling and retrieve every
  inapplicable source failure; retrieval selectivity is not discriminative.
- Mem0/Letta have a behavioral ceiling in both tested v4 cells.
- Vector's two-failure 2/3 cell is a small transitional/discrimination region.
- Three failures are not harder than two in this sample; there is no monotone
  v4 transition or shared active-backend failure region.
- Temperature zero does not make an external LLM service bit-deterministic;
  the superseded and accepted campaigns differ on one Vector outcome. This is
  another reason not to rank from three runs.

The bounded plan stops here. More v4 cells would not establish a monotone
Failure Point without a new research design and preregistration. No formal
campaign, ranking, effect size, Native-Minecraft conclusion or cost claim is
authorized.
