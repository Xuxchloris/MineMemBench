# MineMemBench development plan

Updated: 2026-08-09
Owner: Agent A
Status: **Letta Live and M15 diagnostic implementation are complete; formal
experiments are gated**

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
| M15 formal research phase | not approved | requires clean reviewed commit, frozen preregistration and A-authorized sample |

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

Formal evidence requires all of the following before run 1:

1. external review owner creates a clean reviewed commit;
2. source provenance is recorded and `--require-clean-source` passes;
3. a frozen copy of `docs/preregistration_template.md` specifies hypotheses,
   cells, paired seeds, sample size, endpoints, exclusions and analysis;
4. Agent A authorizes the exact campaign; Agent C independently verifies it;
5. no retry, replacement, silent exclusion or mid-campaign parameter change.

## 5. Immediate work order

1. TASK-024 source provenance and documentation alignment: **complete**.
2. TASK-025 read-only source-freeze preflight: **PASS / accepted** in
   `QA-025.md` and `A-FINAL-025.md`; full Python suite 378 passed.
3. External review owner freezes the current worktree in git. Agents do not
   stage, commit or push under repository rules. The producer-source
   fingerprint before that freeze is
   `8606370026c2bde49737ccb945c9b69ed4aa9cb64090aa06df6cb7c23e24e55f`
   over 106 files; the clean commit must be recaptured and compared with
   `scripts/verify_source_freeze.py --require-clean` plus exact expected
   fingerprint and commit arguments.
4. Only after the clean-source gate passes may A choose one informative,
   semantics-consistent formal band and issue a separate preregistered task.

No new campaign is currently authorized.
