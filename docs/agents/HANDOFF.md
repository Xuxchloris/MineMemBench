# MineMemBench unified handoff

Updated: 2026-08-09 09:59 Asia/Shanghai
Owner: Agent A
Status: **TASK-025 read-only freeze preflight is accepted; formal experiments
await a clean externally frozen revision**

This is the single handoff/source-of-truth document for the next task. Update
this file in place; do not create parallel handoff/project-status documents.

## 1. Binding operating constraints

- Read `AGENTS.md`, this file, `README.md`, `docs/protocol.md`, current git
  status/diff, tests and raw logs before acting.
- `docs/development_plan.md` is now the current plan. The root-level
  `docsdevelopment_plan.md` is historical M4-era context only.
- Agent B is unavailable because its quota is exhausted. Until restored, A
  freezes the task and performs implementation, C independently tests, and A
  performs final review. Repository rules still prohibit every agent from
  staging, committing, or pushing.
- Repo rule remains: no `git add`, commit or push; do not read/print `.env`,
  change `docs/protocol.md`, fabricate results, or run network unit tests.
- Do not add another memory framework. First make one stress scenario
  semantically valid and discriminative.

## 2. Repository/runtime snapshot

- Branch/HEAD: `main` at `cbaa276` (`origin/main`), but the worktree is heavily
  dirty with TASK-002..025 changes uncommitted. Current full status has 31
  modified tracked paths and 107 untracked files at A-025 finalization;
  preserve all of it and never reset or overwrite.
- Tests on the accepted TASK-025 tree: Agent A and C independently reached
  **378 Python passed**. TypeScript baseline: **34 passed**, `npm run build`
  successful (TASK-025 did not touch TypeScript).
- Letta strict live verifier: PASS for exact add/retrieve, update, reset and
  fresh-scope isolation. Server `letta/letta:0.16.8`; Python client 1.12.1.
- Installed memory packages: mem0ai 2.0.17; graphiti-core 0.29.3.
- Expected user-owned live stack (leave running unless asked): real bot 8081,
  Letta 8283, Minecraft 25565. No stray mock bot remained after campaigns.
- Current registered backends: `none`, `vector`, `mem0`, `letta`, `graphiti`.
  Graphiti adapter exists but Controlled live acceptance is N/A: DeepSeek
  extraction produced zero/near-zero graph facts (documented in README).
- Current registered scenarios: `delayed_recall`, `world_update`,
  `failure_learning`, `memory_noise_stress`. `failure_transfer` is deliberately
  removed because it fabricates the failure and solution.

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
  over 106 files. `--require-clean-source` rejects the current dirty worktree
  before creating output. TASK-025 also adds a standalone read-only
  `scripts/verify_source_freeze.py`; a fingerprint does not replace a clean
  commit.

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

## 6. One next task (external review owner, then A/C)

TASK-025 is accepted in `docs/agents/reviews/A-FINAL-025.md`; C independently
verified every requirement. No new campaign is authorized. The external review
owner must now review and freeze the complete worktree in a clean git commit,
then run:

```powershell
.venv\Scripts\python scripts\verify_source_freeze.py --require-clean `
  --expected-source-fingerprint 8606370026c2bde49737ccb945c9b69ed4aa9cb64090aa06df6cb7c23e24e55f `
  --expected-git-commit <new-clean-commit-sha>
```

After that external transition, A recaptures provenance and freezes one exact
preregistration, C performs preflight, and A decides whether to authorize that
formal sample.

## 7. Other open gaps, ordered

- **High — immutable reproducibility:** TASK-024 now records exact producer
  provenance and rejects dirty formal runs, but the external review owner has
  not yet created the required clean reviewed commit. Current dirty data remain
  diagnostic evidence only.
- **Resolved — documentation drift:** `docs/development_plan.md`, README,
  stress design and experiment standard now describe the current M2/M3/M15
  state and evidence boundaries.
- **High — formal statistics:** no formal n>=10 cell or Failure Point is
  approved. The draft experiment standard still says pending A ratification.
- **High — core coverage:** the world-update depth ladder, memory-noise curve,
  cross-session persistence and real observed failure transfer still need
  Controlled validation. Failure transfer remains N/A.
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

- Latest implementation completion: `docs/agents/reviews/A-IMPLEMENTATION-025.md`
- Latest independent code QA: `docs/agents/qa/QA-025.md`
- Latest A final review: `docs/agents/reviews/A-FINAL-025.md`
- Latest experiment QA: `docs/agents/qa/QA-023.md`
- Latest raw evidence: `results/stress_controlled_failure_learning_v2_count50_round1/`
- Contamination review: `docs/agents/reviews/A-FINAL-006.md`
- Semantic-time review: `docs/agents/reviews/A-FINAL-008.md`
- Letta deployment/verification: `docs/letta_live.md`,
  `scripts/verify_letta_live.py`

End state: Letta Live and M15 diagnostic infrastructure are implemented;
memory-noise is diagnostically bracketed in `(10,50]`; failure-learning
0/10/50 is accepted and stopped; TASK-024 provenance and TASK-025 read-only
freeze preflight are accepted. No new campaign, formal ranking, or formal
Failure Point is approved until a clean external revision and frozen
preregistration exist.
