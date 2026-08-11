# MineMemBench development plan

Updated: 2026-08-11
Owner: Agent A
Status: **TASK-026 is clean-frozen, verified and pushed at `592e4ab...`;
TASK-027 Formal V1 preregistration and frozen analysis are in progress;
Formal runs started=0**

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
| M15 Formal V1 research phase | preregistration implementation | fixed Controlled study: 8 treatment cells × 4 backends × fresh paired seeds 1001–1010 = 320; no run started |

Current registered backends: `none`, `vector`, `mem0`, `letta`, `graphiti`.
Graphiti live acceptance remains N/A under the controlled DeepSeek extractor;
it is not part of the four-backend Controlled matrix.

## 3. M15 scenario status

| scenario / semantics | implemented ladder | executed Controlled diagnostics | decision |
|---|---|---|---|
| `delayed_recall / entity_key_v2` | `(10,0) → (50,5) → (200,20) → (500,50)` | only v2 `(200,20)`; older cells use non-poolable legacy treatments | further cells gated pending immutable revision/A task |
| `world_update / temporal_chain_v2` | depth `1 → 2 → 3 → 4`; depth 3 is A→B→C→D | depth 3 only | construct accepted; remaining depth curve gated |
| `memory_noise_stress / key_retention_v2` | `0/10/50/100/200/500/1000` | `0/10/50` | stopped at 50; installed Mem0/Letta target loss bracketed in `(10,50]`; no formal Failure Point |
| `failure_learning / observed_precondition_v2` | configurable neutral `interference_count` | `0/10/50` | stopped at 50; target stayed rank1, transfer preparation changed vs NoMemory, no framework ranking |
| `long_lived_memory / lifetime_v1` | event/session/update/similarity counts | `(8,2,1,1)`, `(20,4,2,5)`, `(50,8,4,15)` | bounded calibration accepted; Vector target loss begins in tested 20-event cell, Mem0/Letta retain through 50; diagnostic only |
| `failure_learning_multi / observed_precondition_applicability_v4` | exactly one applicable and 1–2 heterogeneous inapplicable real failures plus neutral interference | terminal-corrected 2/3 failures × seeds 42/43/44 × four backends | accepted bounded diagnostic: None 0/3 both cells; Vector 2/3 then 3/3; Mem0/Letta 3/3; active retrieval ceiling, no monotone Failure Point |

The historical `failure_transfer` module is unregistered and research-invalid.
Failure transfer claims use only `failure_learning / observed_precondition_v2`,
which derives its source event from an actual failed `ActionResult` and tests a
different entity/task.

## 4. Evidence boundary

Accepted stress evidence is diagnostic: three paired seeds per backend in a
fresh Controlled mock fixture, with complete manifests/results/stdout/stderr.
It supports construct and mechanism observations only. It does not support a
formal framework ranking, effect size, Failure Point, Native Minecraft claim or
cost-efficiency comparison.

Formal V1 evidence requires all of the following before run 1 on the exact
producer revision being studied:

1. external review owner creates and verifies a clean reviewed commit;
2. source provenance is recorded and `--require-clean-source` passes;
3. frozen `docs/preregistration_m15_formal_v1.md` specifies hypotheses,
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
9. TASK-027 Formal V1: implement and test the fail-closed analysis and
   one-shot no-retry producer; freeze the exact preregistration; then execute
   exactly 320 planned runs in `results/formal_m15_v1_20260811`.

TASK-027 authorizes only its gated preregistration and final-publication Git
operations. It does not authorize parameter/seed changes, retries, Dashboard
refactors, new backends or history rewriting.
