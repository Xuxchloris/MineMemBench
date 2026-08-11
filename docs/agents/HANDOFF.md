# MineMemBench unified handoff

Updated: 2026-08-11 Asia/Shanghai
Owner: Agent A
Status: **TASK-027 attempt 1 was clean-frozen/pushed at `7c96df88...` and
stopped fail-closed on an external planner-DNS producer failure; it is
abandoned with no retry. Attempt 2 preregistration/recovery is in progress and
its Formal runs started=0.**

This is the single handoff/source-of-truth document for the next task. Update
this file in place; do not create parallel handoff/project-status documents.

## 1. Binding operating constraints

- Read `AGENTS.md`, this file, `README.md`, `docs/protocol.md`, current git
  status/diff, tests and raw logs before acting.
- `docs/development_plan.md` is now the current plan. The root-level
  `docsdevelopment_plan.md` is historical M4-era context only.
- TASK-027 authorizes gated research freezes and requires a new commit, study
  identity, preregistration and empty root after a stopped integrity attempt.
  This does not authorize unrelated Git operations, retries, splicing, amend,
  force-push or history rewriting.
- Do not read/print `.env`,
  change `docs/protocol.md`, fabricate results, or run network unit tests.
- Do not add another memory framework or optimize Dashboard in TASK-027.

## 2. Repository/runtime snapshot

- Current stable branch/HEAD: local `main`, `origin/main` and remote
  `refs/heads/main` are synchronized at attempt-1 freeze
  `7c96df88c4208e47217da984f61798be051f56da`. Its clean source fingerprint is
  `f21af111b86926aca18e77846e3b37f52d7b235facdc242daf0977a314ffc38a`
  over 126 allowlisted files; strict verification passed before and after the
  stop. Never amend or rewrite TASK-025/TASK-026/attempt-1 history.
- Tests on the accepted TASK-025 tree: Agent A and C independently reached
  **378 Python passed** and the TypeScript baseline was **34 passed**. Current
  corrected TASK-026 candidate independently passes **429 Python** and
  **40 TypeScript** tests plus TypeScript build and Dashboard JS syntax.
- Letta strict live verifier: PASS for exact add/retrieve, update, reset and
  fresh-scope isolation. Server `letta/letta:0.16.8`; Python client 1.12.1.
- Installed memory packages: mem0ai 2.0.17; graphiti-core 0.29.3.
- Expected user-owned live stack (leave running unless asked): real bot 8081,
  Letta 8283, Minecraft 25565. No stray mock bot remained after campaigns.
- Current registered backends: `none`, `vector`, `mem0`, `letta`, `graphiti`.
  Graphiti adapter exists but Controlled live acceptance is N/A: DeepSeek
  extraction produced zero/near-zero graph facts (documented in README).
- Current registered scenarios: `delayed_recall`, `world_update`,
  `failure_learning`, `failure_learning_multi`, `memory_noise_stress`, and
  `long_lived_memory`. `failure_transfer` is deliberately removed because it
  fabricates the failure and solution.

## 3. Completed, verified infrastructure

- `MemoryBackend` plugin boundary remains intact; planner/scenario/runner do
  not branch on backend name.
- Letta is a memory-only Docker backend and round-trips the complete
  ExperienceEvent through payload tags.
- Controlled Mode starts a fresh canonical `BOT_MOCK=1` process per run,
  rejects incomplete fixtures, normalizes volatile WorldState time, uses
  deterministic event ids/logical timestamps, campaign-local stores,
  seed-major cyclic counterbalancing, fail-closed output directories and
  durable per-run stdout/stderr.
- Every backend, including NoMemory, records its actual injected events.
  RunStep keeps the exact causal retrieval snapshot; metrics use stable event
  ids from that retrieval, not a second probe.
- Fairness verifies cleanup of the completed episode and a fresh scope.
- The LLM prompt now sees a backend-neutral semantic memory view
  (`actor,target,event_type,location,context,outcome,timestamp`) in retrieval
  order. It does not see item/event/episode ids, scores, storage timestamps,
  backend metadata or raw events.
- New runs record planner user-template/schema fingerprint
  `988e01277f199fc0b8f48b1f57f7efe7da8bafd4ebd36267f509fc2af8b0df39`;
  old results load with this optional field as `None`.
- New runs also record deterministic source provenance. Controlled manifests
  use `controlled-campaign/v4`, pre-register the complete source record before
  run 1 and stop on any result mismatch. The accepted current fingerprint is
  `8606370026c2bde49737ccb945c9b69ed4aa9cb64090aa06df6cb7c23e24e55f`
  over 106 files for the immutable TASK-025 baseline. The final reviewed
  TASK-026 dirty-tree identity is
  `86c625f9a130be3b5a81c3ed7ca48db9eb128493eb703ac98ca905a2bb9fd3f6`
  over 122 files; its replacement v4 calibration is diagnostic only.
  `--require-clean-source` rejects a dirty
  worktree before creating output. TASK-025 also adds a standalone read-only
  `scripts/verify_source_freeze.py`; a fingerprint does not replace a clean
  commit.
- Earlier dirty candidates and the first A-FINAL-026 conclusion are
  superseded. The replacement `A-FINAL-026.md` accepts the corrected tree for
  a separately authorized freeze after closing the heterogeneous construct,
  Dashboard and objective-terminal-action gaps.
- TASK-026 now adds `lifetime_v1` and heterogeneous
  `observed_precondition_applicability_v4`, complete typed phase/run evidence,
  and a loopback-only read-only dashboard with live campaign matrix, complete
  run evidence, seekable semantic replay, trajectory markers and exact
  same-seed four-backend compare. Producer modules never import dashboard
  modules. Replay uses stored raw evidence only and labels utilization Unknown
  unless a deterministic retrieved-event/action rule supports it.
- New lifetime/v4 runs stop only when recorded environment evidence proves
  completed delivery/target attack. The backend-neutral predicate never enters
  prompt, memory query/event or action selection.

## 4. Raw experiment evidence (never pool these rounds)

All paths contain real runs. Rounds differ in treatment and must remain
separate.

| evidence | validity and narrow result |
|---|---|
| `results/stress_round1/` | Native exploratory only; rejected for causal comparison because world state/run order drifted and events differed across backends. |
| `results/stress_controlled_round1/` | Valid Controlled smoke: 24 runs. NoMemory 0/3; memory backends 3/3 at (10,0) and (50,5). Retrieval changed but behavior had a ceiling. |
| `results/stress_controlled_round2_200_20/` | 12 valid executions but the Scenario was contaminated: wrong facts literally said `wrong location` / `used to be located here`, used different actor/type, and full backend internals reached the LLM. Vector rank 6 vs mem0/letta rank 1 is not a valid framework claim. |
| `results/stress_controlled_round3_decontaminated_200_20/` | 12 valid decontamination diagnostics. Vector 3/3 rank 1; mem0 0/3 ranks 2/N/A/N/A; letta 0/3 ranks 3/7/9. Planner always chose retrieval item 1. Useful top-1 ordering evidence only. |
| `results/stress_controlled_round4_temporal_200_20/` | 12 valid temporal-complete diagnostics; template hash/fairness/input equality all pass. Results exactly repeat round 3. Event time did not change behavior; all nine memory-backed actions still chose item 1. QA: `docs/agents/qa/QA-010.md`. |
| `results/stress_controlled_round5_entity_key_v2_200_20/` | 12/12 valid v2 diagnostics with explicit simultaneously-true entity-key associations and causal metrics. NoMemory 0/3; vector 3/3 ranks 1/1/1; mem0 2/3 ranks 1/absent/1; letta 1/3 ranks absent/absent/4. All six target-present memory runs succeeded; all three target-absent memory runs failed. Three seeds only, not a ranking. QA: `docs/agents/qa/QA-012.md`; A audit: `docs/agents/reviews/A-FINAL-012.md`. |
| `results/stress_controlled_world_update_v2_depth3_round1/` | 12/12 valid Controlled mock-fixture diagnostics for temporal-chain v2 depth 3. NoMemory 0/3; vector 1/3; mem0 2/3; Letta 1/3. All nine memory runs retrieved current D and all A/B/C stale facts; current recall therefore has a ceiling while behavior does not. Three seeds only, not a ranking or Native Minecraft result. QA: `docs/agents/qa/QA-015.md`; A audit: `docs/agents/reviews/A-FINAL-015.md`. |
| `results/stress_controlled_memory_noise_v2_count50_round1/` | 12/12 valid key-retention v2 count-50 Controlled diagnostics. NoMemory 0/3; vector 3/3 ranks 1/1/1; Mem0 1/3 target absent/absent/rank1; Letta 1/3 target absent/absent/rank4. Target-present memory runs succeeded 5/5 and target-absent failed 4/4. No same-treatment count-0 baseline yet, so no noise-effect or ranking claim. Corrected QA: `docs/agents/qa/QA-017.md`; A audit: `docs/agents/reviews/A-FINAL-017.md`. |
| `results/stress_controlled_memory_noise_v2_count0_round1/` | 12/12 valid key-retention v2 control diagnostics. NoMemory 0/3; vector/Mem0/Letta each 3/3 with target rank1/top1. Paired with count50, Mem0/Letta target availability and success fall from 3/3 to 1/3 while vector stays 3/3; diagnostic signal only, no formal Failure Point. QA: `docs/agents/qa/QA-018.md`; A audit: `docs/agents/reviews/A-FINAL-018.md`. |
| `results/stress_controlled_memory_noise_v2_count10_round1/` | 12/12 valid diagnostics. NoMemory 0/3; vector 3/3 rank1; Mem0 3/3 ranks 4/5/1; Letta 3/3 ranks 1/7/1. Together with count0/count50, rank degradation appears by 10 and target loss is bracketed in `(10,50]` for installed Mem0/Letta configs. Diagnostic only, not a formal Failure Point. QA: `docs/agents/qa/QA-019.md`; A audit: `docs/agents/reviews/A-FINAL-019.md`. |
| `results/stress_controlled_failure_learning_v2_count0_round1/` | 12/12 valid observed-precondition v2 diagnostics. NoMemory 0/3; Vector/Mem0/Letta each 2/3. All nine memory-backed runs retrieved the source failure at rank1/top1 and equipped gold before the first transfer attack; the three memory failures switched back to the stone sword before attacking. Diagnostic only, no ranking/cost claim. QA: `docs/agents/qa/QA-021.md`; A audit: `docs/agents/reviews/A-FINAL-021.md`. |
| `results/stress_controlled_failure_learning_v2_count10_round1/` | 12/12 valid paired diagnostics. NoMemory 0/3; Vector 2/3; Mem0/Letta 3/3. Every memory run retained the failure at rank1/top1 and prepared with gold. Mem0/Letta retrieval became interference-saturated without target displacement; success flips are action-selection noise. Diagnostic only. Corrected QA: `docs/agents/qa/QA-022.md`; A audit: `docs/agents/reviews/A-FINAL-022.md`. |
| `results/stress_controlled_failure_learning_v2_count50_round1/` | 12/12 valid paired diagnostics. NoMemory 0/3; Vector 1/3; Mem0/Letta 3/3. All nine memory runs still retrieve the failure at rank1/top1 and prepare with gold; Vector failures are post-retrieval wrong re-equips. Mem0/Letta top-10 is fully interference-saturated without target displacement. Diagnostic ladder stops here. QA: `docs/agents/qa/QA-023.md`; A audit: `docs/agents/reviews/A-FINAL-023.md`. |
| `results/calibration_task026_lifetime_v1_20260809/` | 36/36 terminal runs; three paired seeds across 8/20/50-event lifetime cells. NoMemory 0/9; Mem0/Letta 9/9; Vector 1/9 with six target-retrieval failures and two strict invalid-give recoveries. Dirty-source diagnostic only. |
| `results/calibration_task026_failure_multi_v3_20260809/` | 24/24 terminal runs, but all failures share one gold rule. Retained as superseded homogeneous diagnostic history; it does **not** satisfy the multi-relevant applicability construct and must never pool with v4. |
| `results/calibration_task026_noise_v2_20260809/` | 36/36 terminal runs. Noise10 is active-backend ceiling; noise30 discriminates via one Mem0 retrieval failure; noise50 is a shared Mem0/Letta retrieval-loss region. Smallest-set rule stops before 20/40/60. Dirty-source diagnostic only. |
| `results/calibration_task026_failure_applicability_v4_20260809/` | 24/24 honest runs but superseded: successful tasks continued after target completion and polluted horizon/token/latency. Never pool with the replacement. |
| `results/calibration_task026_failure_applicability_v4_terminal_v1_20260809/` | 24/24 accepted bounded diagnostics under `86c625f9a130be3b5a81c3ed7ca48db9eb128493eb703ac98ca905a2bb9fd3f6`: None 0/3 both cells; Vector 2/3 at two failures and 3/3 at three; Mem0/Letta 3/3. All active relevant events rank 1; one Vector planning failure recovers but remains strict primary failure. No ranking or monotone Failure Point. |

Round-4 metrics: NoMemory 0/3; vector 3/3 rank `[1,1,1]`; mem0 0/3
rank `[2,N/A,N/A]`; letta 0/3 rank `[3,7,9]`. These are not a superiority
ranking or Failure Point.

## 5. Highest-priority research finding

### Accepted diagnostic — target availability mediates v2 behavior

Round 5 resolves the legacy semantic contradiction. For the three tested
seeds, every memory-backed run with the declared target event in causal top-10
succeeded (6/6), including Letta at rank 4; every target-absent memory run
failed (3/3), and NoMemory failed 3/3. This is valid causal diagnostic evidence
that retrieval availability affects behavior and that the planner is not
blindly following top-1. It is not a framework ranking or Failure Point.

Formal delayed-recall expansion remains gated on a clean immutable reviewed
revision and a pre-registered paired sample. Mem0's missing optional
spaCy/BM25 features and non-normalized latency accounting must be disclosed.

## 6. One next task

Complete the new attempt-2 preregistration and audit-accounting fix, pass every
pre-Formal gate, then clean-freeze/push the recovery producer. Only that exact
identity may execute the fixed eight-cell × four-backend × fresh seeds
1011–1020 Controlled study in the new empty root
`results/formal_m15_v1_20260811_attempt2`. Attempt-1 raw evidence remains at
`results/formal_m15_v1_20260811` and must never be resumed or pooled.

## 7. Other open gaps, ordered

- **Resolved — immutable reproducibility:** TASK-025 remains immutable and
  TASK-026 is separately frozen/pushed at `592e4ab...` with strict verification.
- **Resolved — documentation drift:** `docs/development_plan.md`, README,
  stress design and experiment standard now describe the current M2/M3/M15
  state and evidence boundaries.
- **High / resolved by abandonment — attempt-1 producer stop:** DeepSeek DNS
  resolution failed at one long-lived slot. Evidence is preserved in
  `A-INCIDENT-027-ATTEMPT1.md`; 0 retries and 0 exclusions.
- **In progress — formal statistics:** TASK-027 fixes N=10 paired seeds,
  exact McNemar, paired risk difference, deterministic bootstrap CI, Holm
  correction and non-interpolated Failure Points before run 1.
- **High — formal coverage:** M15.1 has bounded cross-session, noise and
  heterogeneous applicability-v4 diagnostics. V4 active retrieval and
  Mem0/Letta behavior have ceilings; there is no monotone active-backend
  Failure Point. Non-preregistered expansion remains gated; the exact attempt-2
  n=10 Formal sample is authorized only after its new freeze gates pass.
  Historical fabricated
  `failure_transfer` remains N/A and unregistered.
- **Medium — cost accounting:** memory-internal LLM/embedding calls and init
  time are not separated from per-operation latency. Current average add
  latency cannot support efficiency claims.
- **Medium — framework registry:** requested `framework_registry.yaml` does
  not exist. Do not add it or new frameworks until one core stress task is
  valid and discriminative.
- **Low — README/version drift:** registered Graphiti and live statuses differ
  from some roadmap wording; dependency/image versions should be pinned and
  reconciled later.

## 8. Evidence index

- Latest implementation completion: `docs/agents/reviews/A-IMPLEMENTATION-026.md`
- Latest independent code/data QA: `docs/agents/qa/QA-026.md`
- Latest TASK-026 A final review: `docs/agents/reviews/A-FINAL-026.md` — PASS
  for its historical freeze. TASK-027 attempt-2 authority and gate are recorded
  separately in `A-PREFLIGHT-027-ATTEMPT2.md`.
- Latest calibration report: `docs/difficulty-calibration.md`
- Latest raw evidence: terminal-corrected v4 replacement directory above;
  lifetime/noise remain dirty-tree diagnostics; homogeneous v3 and first v4
  are superseded.
- Contamination review: `docs/agents/reviews/A-FINAL-006.md`
- Semantic-time review: `docs/agents/reviews/A-FINAL-008.md`
- Letta deployment/verification: `docs/letta_live.md`,
  `scripts/verify_letta_live.py`

Current end state: TASK-026 is frozen, verified and pushed. TASK-027 is
preparing the independent attempt-2 producer and analysis contract. Attempt 1
is incomplete and rejected for analysis; attempt-2 runs started=0, so no valid
Formal result or conclusion exists yet.
