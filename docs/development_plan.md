# MineMemBench development plan

Updated: 2026-08-11
Owner: Agent A
Status: **MineMemBench Controlled Formal V1 complete. Attempt 2 is the sole
final Formal dataset: 320/320 valid, integrity PASS, frozen paired statistics
complete; the clean commit containing this plan is the final publication
identity and is synchronized to `origin/main`.**

This is the current development plan. The root-level
`docsdevelopment_plan.md` is the historical M4-era user prompt and is retained
only as archival context.

## 1. Research contract

MineMemBench evaluates how the long-term `MemoryBackend` changes an embodied
LLM agent's behavior while holding the planner, prompt, temperature, tools,
scenario parameters and initial world state fixed. Memory may reach behavior
only through backend-neutral retrieval supplied to the planner. Scenario code
must never branch on backend identity or choose an action on memory's behalf.

`docs/protocol.md` is the frozen Python↔TypeScript wire contract. Native and
Controlled results are separate treatments and must never be pooled.

## 2. Current implementation status

| area | implementation | evidence status |
|---|---|---|
| M1–M3 repository, Mineflayer adapter and Python bridge | complete | Python and TypeScript suites plus live server smoke |
| M4–M7 agent loop, event layer, vector baseline, delayed recall | complete | classic matrix and later Controlled diagnostics |
| M8 Mem0 | complete | adapter tests and Controlled diagnostics; optional spaCy/BM25 features absent |
| M9 / M15A Letta | complete | Docker `letta/letta:0.16.8`; strict live add/retrieve/update/reset isolation PASS |
| M10–M11 scenarios and reporting | complete | unit/integration tests and real result/log artifacts |
| M15B Controlled stress infrastructure | complete | deterministic streams, fixtures, campaign-local stores, causal snapshots, fairness/reset audit |
| M15 stable baseline | frozen | commit `9fdced8fa9967a6df7b856b035485b41e84c06dc`; source fingerprint `8606370026c2bde49737ccb945c9b69ed4aa9cb64090aa06df6cb7c23e24e55f`; freeze verification PASS |
| M15.1 difficulty + dashboard/replay | frozen / pushed | commit `592e4ab72193fa541a1a536a1eab2752b03acad6`; fingerprint `86c625f9a130be3b5a81c3ed7ca48db9eb128493eb703ac98ca905a2bb9fd3f6`; strict verification PASS |
| M15 Formal V1 research phase | complete | Attempt 1 preserved and excluded; Attempt 2 producer `64c822f...`, fingerprint `ebfe917...`: 320/320 valid, integrity/statistics PASS, results in `docs/formal_m15_v1_results.md` |

Current registered backends: `none`, `vector`, `mem0`, `letta`, `graphiti`.
Graphiti live acceptance remains N/A under the controlled DeepSeek extractor;
it is not part of the four-backend Controlled matrix.

## 3. M15 scenario status

| scenario / semantics | implemented ladder | executed Controlled diagnostics | decision |
|---|---|---|---|
| `delayed_recall / entity_key_v2` | `(10,0) → (50,5) → (200,20) → (500,50)` | diagnostics plus Formal `(200,20)` N=10 | Formal: Vector 10/10, Mem0 8/10, Letta 7/10; further cells are Future Work |
| `world_update / temporal_chain_v2` | depth `1 → 2 → 3 → 4`; depth 3 is A→B→C→D | diagnostic plus Formal depth 3 N=10 | active retrieval 10/10 each; behavior Vector 3/10, Mem0 6/10, Letta 4/10 |
| `memory_noise_stress / key_retention_v2` | `0/10/50/100/200/500/1000` | diagnostics 0/10/50; Formal 10/30/50 N=10 | Formal Failure Point: Vector not observed, Mem0 30, Letta 50 |
| `failure_learning / observed_precondition_v2` | configurable neutral `interference_count` | `0/10/50` | stopped at 50; target stayed rank1, transfer preparation changed vs NoMemory, no framework ranking |
| `long_lived_memory / lifetime_v1` | event/session/update/similarity counts | calibration plus Formal L1/L2/L3 N=10 | Vector 5/0/0; Mem0/Letta 10/10 throughout; lifetime is composite |
| `failure_learning_multi / observed_precondition_applicability_v4` | exactly one applicable and 1–2 heterogeneous inapplicable real failures plus neutral interference | terminal-corrected 2/3 failures × seeds 42/43/44 × four backends | accepted bounded diagnostic: None 0/3 both cells; Vector 2/3 then 3/3; Mem0/Letta 3/3; active retrieval ceiling, no monotone Failure Point |

The historical `failure_transfer` module is unregistered and research-invalid.
Failure transfer claims use only `failure_learning / observed_precondition_v2`,
which derives its source event from an actual failed `ActionResult` and tests a
different entity/task.

## 4. Evidence boundary

Historical stress/calibration evidence remains diagnostic: three paired seeds
per backend in a fresh Controlled mock fixture. It supports construct and
mechanism observations only and is never pooled with Formal V1.

Attempt 2 is the sole Formal evidence: eight cells × four backends × ten paired
seeds, with complete manifests/results/stdout/stderr. It supports the
scenario-specific effect sizes, adjusted paired comparisons and bounded
Failure Points in `docs/formal_m15_v1_results.md`; it does not support a global
leaderboard, Native Minecraft claim or cost-efficiency comparison.

Formal V1 satisfied the following gates before run 1 on the exact producer
revision:

1. external review owner creates and verifies a clean reviewed commit;
2. source provenance is recorded and `--require-clean-source` passes;
3. frozen `docs/preregistration_m15_formal_v1_attempt2.md` specifies hypotheses,
   cells, paired seeds, sample size, endpoints, exclusions and analysis;
4. the TASK-027 pre-Formal gates verify the exact campaign and analysis;
5. no retry, replacement, silent exclusion or mid-campaign parameter change.

## 5. Immediate work order

1. TASK-024 source provenance and documentation alignment: **complete**.
2. TASK-025 stable-baseline freeze: **PASS / complete** at
   `9fdced8fa9967a6df7b856b035485b41e84c06dc`; full Python suite 378 passed,
   source fingerprint
   `8606370026c2bde49737ccb945c9b69ed4aa9cb64090aa06df6cb7c23e24e55f`,
   freeze verification PASS, pushed to `origin/main`.
3. TASK-026 Phase A/B and first implementation: complete, followed by an A
   objective re-audit that rejected homogeneous multi-failure v3 as an
   incomplete construct.
4. Corrective implementation: `observed_precondition_applicability_v4`,
   heterogeneous fixture/evidence firewall, full Dashboard campaign/run/
   replay/compare MVP and atomic live index are implemented; protocol remains
   unchanged.
5. Full verification and C independent QA: **PASS**. Final suites are Python
   429 and TypeScript 40; terminal behavior, fixture, Dashboard, security and
   source isolation independently pass.
6. Bounded calibration: **complete**. Lifetime/noise remain diagnostics under
   their recorded source. Homogeneous v3 and the first post-terminal-contaminated
   v4 run are superseded. The accepted replacement v4 directory is
   `calibration_task026_failure_applicability_v4_terminal_v1_20260809` under
   source fingerprint
   `86c625f9a130be3b5a81c3ed7ca48db9eb128493eb703ac98ca905a2bb9fd3f6`.
7. A final review: **PASS** in `A-FINAL-026.md`.
8. TASK-026 clean freeze/push: **PASS / complete** at
   `592e4ab72193fa541a1a536a1eab2752b03acad6`; local/remote synchronized.
9. TASK-027 Formal V1 attempt 1: **stopped and abandoned**. The immutable
   evidence root `results/formal_m15_v1_20260811` contains 271 producer-ok, one
   producer-failed and 48 pending slots; no retry/exclusion occurred.
10. TASK-027 Formal V1 attempt 2: fix manifest attempt accounting without
   changing experimental behavior; freeze commit `64c822faf2ae8e490b3da11ed86261566bd93256`
   with seeds 1011–1020; execute exactly 320 planned runs in the new root
   `results/formal_m15_v1_20260811_attempt2`: **complete, 320/320 valid**.
11. Data integrity audit: **PASS** — missing/duplicate/unexpected/invalid 0;
   retries/exclusions 0; four backends each 80; eight cells each 40; reset,
   fairness, provenance, fixture and same-seed stream parity pass.
12. Frozen statistics: **PASS** — 32 cell summaries, 24 paired comparisons,
   exact McNemar, paired RD, deterministic 10,000-resample CIs, Holm family and
   eight Failure Point rows independently recomputed.
13. Analysis schema erratum: the minimum typed `context.x/y/z` compatibility
   correction is documented in `A-ANALYSIS-ERRATUM-027-ATTEMPT2.md`; no raw run
   or research design changed.
14. Final research report: **complete** at `docs/formal_m15_v1_results.md`.

TASK-027 is complete in the clean publication commit containing this plan,
after final full tests, remote synchronization and freeze verification. No
Formal experiment may be rerun. Dashboard V2 visual work is the next separate
task; new backends, scenarios, statistics and Dashboard implementation remain
out of scope.

## 6. Formal V1 result boundary

- Delayed 200/20: Vector 10/10, Mem0 8/10, Letta 7/10.
- World update depth 3: every active backend retrieves 10/10, but behavior is
  Vector 3/10, Mem0 6/10, Letta 4/10.
- Noise 10/30/50 Failure Points: Vector not observed, Mem0 30, Letta 50.
- Composite lifetime: Vector 5/10 at L1 and 0/10 at L2/L3; Mem0 and Letta
  10/10 at all levels. Vector versus Mem0/Letta at L2/L3 remains significant
  after Holm (adjusted p 0.046875).
- Across all runs: retrieval+/success 180, retrieval+/failure 22,
  retrieval−/success 0, retrieval−/failure 118.

All wording is limited to the current frozen MineMemBench configuration and
Controlled Formal V1. The other 20 active-backend comparisons do not reject
after Holm; N=10 non-rejection is not equivalence.
