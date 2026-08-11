# MineMemBench Controlled Formal V1 — Final Results

Status: **COMPLETE — integrity PASS**

Study: `m15-formal-v1-controlled-20260811-attempt2`

Data as of: 2026-08-11 (Asia/Shanghai)

## 1. Scope and identities

This is the only final Formal V1 dataset. It compares the configured
`none`, `vector`, `mem0`, and `letta` memory backends under the same Controlled
fixture, DeepSeek planner, prompt, temperature, tools, scenario parameters,
and paired seeds. Graphiti, calibration, Native Mode, failure-learning v4, and
the incomplete Attempt 1 campaign are not pooled.

- Producer commit: `64c822faf2ae8e490b3da11ed86261566bd93256`
- Producer fingerprint: `ebfe9172dbe83abb5d76c2f8459ef346b8888d4f8e2bafca4d09799566bad3b3`
- Corrected publication-analyzer fingerprint: `56609462e92db5be4afb28c88811581aa6094a8798a22c17c3e4d1870cda6865`
- Preregistration: `docs/preregistration_m15_formal_v1_attempt2.md`
- Raw root: `results/formal_m15_v1_20260811_attempt2`
- Seeds: `1011–1020`, paired, N=10 per backend×cell
- Matrix: 8 cells × 4 backends × 10 seeds = 320 planned runs
- Primary endpoint: strict evaluator-derived `task_success`

The producer completed 320/320 with zero retries and zero exclusions. The
analyzer correction is disclosed in
`docs/agents/reviews/A-ANALYSIS-ERRATUM-027-ATTEMPT2.md`: the original helper
expected the optional `ExperienceEvent.location`, while all three Controlled
v2 location scenarios use their documented neutral `context.x/y/z` schema.
The correction changed only that schema read, before any successful aggregate
analysis; it did not change data, treatments, endpoints, attribution, or
statistics.

## 2. Frozen treatments

| Cell | Scenario semantics | Frozen parameters |
|---|---|---|
| `delayed_200_20` | `delayed_recall / entity_key_v2` | interference 200; similar distractors 20 |
| `world_update_depth3` | `world_update / temporal_chain_v2` | update depth 3 (A→B→C→D) |
| `noise_10` | `memory_noise_stress / key_retention_v2` | noise 10 |
| `noise_30` | `memory_noise_stress / key_retention_v2` | noise 30 |
| `noise_50` | `memory_noise_stress / key_retention_v2` | noise 50 |
| `lifetime_l1` | `long_lived_memory / lifetime_v1` | events 8; sessions 2; relevant updates 1; similar events 1 |
| `lifetime_l2` | `long_lived_memory / lifetime_v1` | events 20; sessions 4; relevant updates 2; similar events 5 |
| `lifetime_l3` | `long_lived_memory / lifetime_v1` | events 50; sessions 8; relevant updates 4; similar events 15 |

Lifetime is a composite treatment; its result cannot be attributed to event
count alone.

## 3. Data integrity

| Check | Result |
|---|---:|
| Expected / valid | 320 / 320 |
| Missing / duplicate / unexpected | 0 / 0 / 0 |
| Producer failures / invalid fairness | 0 / 0 |
| Retries / exclusions | 0 / 0 |
| Unique result paths / episode ids | 320 / 320 |
| Backends | 80 runs each |
| Cells | 40 runs each |
| Same-seed ExperienceEvent parity | 80/80 treatments PASS across four backends |
| Reset / fresh-scope isolation | 320/320 PASS |
| Position target events using typed `context.x/y/z` | 200/200 |
| Raw-evidence aggregate guard before/after analysis | unchanged: `8fce845f3333564079820a7310fc8b070ea389fcee78c652eb09ad81eaef31f9` |

The raw guard covers 985 non-analysis files and 47,378,322 bytes. Only the
nine deterministic analysis artifacts were added; no raw result, manifest,
log, or store changed.

## 4. Scenario-specific results

Each entry is `strict success / causal target retrieval`, out of 10.

| Cell | None | Vector | Mem0 | Letta |
|---|---:|---:|---:|---:|
| Delayed 200/20 | 0/0 | **10/10** | 8/8 | 7/7 |
| World update depth 3 | 0/0 | 3/10 | **6/10** | 4/10 |
| Noise 10 | 0/0 | **10/10** | 9/9 | **10/10** |
| Noise 30 | 0/0 | **10/10** | 6/6 | **10/10** |
| Noise 50 | 0/0 | **10/10** | 5/5 | 7/7 |
| Lifetime L1 | 0/0 | 5/10 | **10/10** | **10/10** |
| Lifetime L2 | 0/0 | 0/0 | **10/10** | **10/10** |
| Lifetime L3 | 0/0 | 0/0 | **10/10** | **10/10** |

In the current frozen MineMemBench configuration and Controlled Formal V1:

- Vector was the most stable configured backend for delayed recall and the
  tested noise ladder, retaining 10/10 target retrieval and success in all
  four cells.
- Mem0 and Letta were the most stable configured backends for composite
  lifetime, each retaining and completing 10/10 at L1, L2, and L3.
- World update exposed a retrieval-to-action gap: all active backends retrieved
  the current fact in 10/10, but success was Vector 3/10, Mem0 6/10, and Letta
  4/10. Retrieval alone was not sufficient for correct action selection.
- NoMemory was 0/10 in every cell, as expected for tasks whose goals omit the
  required fact. This validates the negative control but is not a claim about
  general non-memory agent ability.

## 5. Retrieval → behavior and failure attribution

Across 320 runs:

| Causal category | Runs |
|---|---:|
| Retrieval present + behavior success | 180 |
| Retrieval present + behavior failure | 22 |
| Retrieval absent + behavior success | 0 |
| Retrieval absent + behavior failure | 118 |

The same objective evidence classified all 140 failures as 118 retrieval
failures (R) and 22 planning/action-selection failures (P); there were no
environment/execution (E) or Unknown failures. In these treatments, target
absence never produced success, but target presence was not sufficient:
17 world-update runs and five Vector L1 runs retrieved the target and still
failed behaviorally.

This is the central MineMemBench result: a retrieval benchmark alone would
miss the 22 retrieval-positive behavioral failures.

## 6. Paired statistics

The frozen analysis used two-sided exact McNemar tests, paired risk difference
(A−B), paired percentile-bootstrap 95% CIs (seed `20260811`, 10,000 resamples
per comparison), and Holm correction over all 24 active-backend comparisons.

Four comparisons rejected the Holm-adjusted 0.05 null, all in composite
lifetime L2/L3:

| Cell | Comparison | Success | Paired RD | 95% CI | exact p | Holm p |
|---|---|---:|---:|---:|---:|---:|
| L2 | Vector − Mem0 | 0/10 vs 10/10 | −1.00 | [−1.00, −1.00] | 0.001953 | 0.046875 |
| L2 | Vector − Letta | 0/10 vs 10/10 | −1.00 | [−1.00, −1.00] | 0.001953 | 0.046875 |
| L3 | Vector − Mem0 | 0/10 vs 10/10 | −1.00 | [−1.00, −1.00] | 0.001953 | 0.046875 |
| L3 | Vector − Letta | 0/10 vs 10/10 | −1.00 | [−1.00, −1.00] | 0.001953 | 0.046875 |

The other 20 comparisons did not reject after Holm correction. This includes
descriptively large differences such as Vector−Mem0 at noise 50 (RD +0.50,
bootstrap CI [0.20, 0.80], exact p 0.0625, Holm p 1.0) and Vector−Mem0/Letta at
L1 (RD −0.50, CI [−0.80, −0.20], exact p 0.0625, Holm p 1.0). A bootstrap CI
excluding zero does not override the preregistered multiplicity-adjusted
hypothesis-test decision. Non-rejection is not evidence of equivalence at
N=10.

## 7. Failure Points

Failure Point is the first tested ladder level with strict success below 80%;
8/10 is not a failure, and no interpolation is used.

| Ladder | None | Vector | Mem0 | Letta |
|---|---|---|---|---|
| Memory noise 10→30→50 | 10 | not observed | 30 | 50 |
| Composite lifetime L1→L2→L3 | L1 | L1 | not observed | not observed |

“Not observed” means only that the backend stayed at or above 80% within the
tested ladder. It does not locate a higher untested threshold.

## 8. Tokens and latency

Token and latency outputs are descriptive only. They include planner tokens
and recorded memory operations, but not a normalized accounting of every
backend-internal embedding/LLM call or initialization cost.

- Mean planner tokens ranged from 1,776–4,046 in the single-session active
  cells and 10,438–34,899 in composite lifetime active cells.
- Vector mean add latency stayed about 4.6–5.4 ms; Mem0 ranged about
  145.8–3,730.0 ms; Letta ranged about 234.9–416.4 ms across reported cells.
- Where retrieval latency was measured, Vector ranged 7.4–283.4 ms, Mem0
  13.3–21.6 ms, and Letta 170.9–232.2 ms.

These numbers do not support a cost-efficiency ranking. The complete per-cell
descriptives are in `formal_cells.csv` and the generated `formal_report.md`.

## 9. Representative paired cases

- Delayed recall, seed 1016: Vector retrieved and succeeded; Mem0 and Letta
  both lacked the target and failed (R). This is a clean retrieval-availability
  discordance under the same seed and treatment.
- Lifetime L1, seed 1012: Vector retrieved the target but failed action
  selection (P); Mem0 and Letta retrieved and succeeded. Seeds 1013, 1015, and
  1017 repeat this mechanism.
- World update is the aggregate counterexample to retrieval-only evaluation:
  all 30 active runs retrieved the current event, while 17 failed behaviorally.

Episode ids and result paths are preserved in `formal_runs.csv` and
`formal_summary.json` for exact replay.

## 10. Analysis artifacts

The corrected analyzer generated and independently reproduced byte-identical:

- `formal_summary.json`
- `formal_runs.csv`
- `formal_cells.csv`
- `formal_pairwise.csv`
- `formal_failure_points.csv`
- `formal_failure_attribution.csv`
- `formal_report.md`
- `formal_success_curves.svg`
- `formal_retrieval_curves.svg`

The summary SHA-256 is
`8f7ac5e40e5449c532bfc5afc2a98747cf59177e4c48d979b49c62f655832b5f`.

Recalculate from the existing data only:

```powershell
.venv\Scripts\python scripts\analyze_formal_m15.py `
  --results-dir results\formal_m15_v1_20260811_attempt2
```

This command is an analyzer, not an experiment producer.

## 11. Limitations

- Claims apply only to this frozen Controlled mock fixture and configured
  backend versions, not Native Minecraft or all possible framework settings.
- N=10 gives limited precision and power; non-significance is not equivalence.
- Only one planner family/configuration was tested.
- Lifetime difficulty changes four parameters together.
- No global framework leaderboard is justified; results are scenario-specific.
- Calibration, diagnostic failure-learning v4, Graphiti, and Attempt 1 are
  excluded from Formal denominators.
- The post-producer analyzer schema erratum is transparent but remains a
  deviation from the ideal of never changing analysis code after production.
- Cost accounting is incomplete and does not justify efficiency claims.

## 12. Final research conclusion

In the current frozen MineMemBench configuration and Controlled Formal V1,
memory-backend differences changed both whether the agent retrieved the
required experience and whether retrieved experience became correct action.
Vector was robust on delayed/noise retrieval but broke on the tested composite
lifetime ladder; Mem0 and Letta were robust through L3 lifetime but degraded on
the noise ladder at different points. World update showed that perfect current
fact retrieval can coexist with poor behavior. The statistically adjusted
evidence supports Vector being below Mem0 and Letta at lifetime L2/L3; other
observed differences remain descriptive under N=10 and Holm correction.

## 13. Dashboard V2 Recommendations

These are future-work recommendations only; no Dashboard code changed in
TASK-027.

1. Add an explicit Diagnostic/Formal evidence-scope badge and default filter.
2. Render Formal success and causal-retrieval curves together by scenario.
3. Show paired RD, 95% CI, discordant seeds, exact p, and Holm p in Compare.
4. Add Failure Point ladder markers with the tested-boundary caveat.
5. Surface retrieval-positive behavioral failures as a dedicated replay queue.
6. Display producer commit/fingerprint, integrity verdict, and analyzer erratum
   next to every Formal report.
7. Preserve read-only operation: no rerun, retry, or experiment-control actions
   belong in the Dashboard.
