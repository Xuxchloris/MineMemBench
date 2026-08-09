# QA-024 — Requirement-by-requirement completion audit of the Letta Live + M15 plan

Issued by: Agent C (independent QA / research-audit agent)
Date: 2026-08-08
Mode: **offline / immutable-on-disk audit only** — no code/results/parameter
edits, no `.env` access, no network/live calls, no git mutations, no campaign
runs, no protocol changes. The only repo artifact created is this report.

Scope: audit the ORIGINAL explicit requirements of the Letta Live + M15 plan
against current source/tests/config, the accepted A final reviews and C QA
reports, and the on-disk manifests/results. This is a completion audit, not a
new experiment. Green tests are treated as necessary-but-not-sufficient;
documentation drift and unexecuted branches are called out explicitly.

> **Correction note (Agent C, 2026-08-08, after Agent A raw review against the
> delayed-recall manifests and A-FINAL-012 / experiment_standard.md).** This
> report was corrected in place; all unchanged requirement labels and findings
> elsewhere in the document are preserved. The corrected points are:
>
> 1. The cells `(10,0)` / `(50,5)` / `(200,20)` are **NOT one
>    semantics-consistent executed ladder**. `stress_controlled_round1`
>    (`(10,0)`, `(50,5)`) is a **legacy** Controlled diagnostic; rounds 2–4 are
>    legacy/invalid/decontamination treatments; the **only accepted
>    `entity_key_v2` executed point is round 5 `(200,20)`**. These cannot be
>    pooled. Both difficulty parameters are fully implemented, but
>    semantics-consistent **v2 empirical ladder coverage is partial**: the v2
>    control `(10,0)`, the `(50,5)` intermediate and the `(500,50)` maximum are
>    unexecuted under v2 unless raw evidence proves otherwise.
> 2. Delayed-recall is **not permanently "stopped at (200,20)"**: it is
>    **gated** — no further cell is currently authorized pending an immutable
>    reviewed revision / A-issued task. The planned `(500,50)` remains
>    unexecuted, but it is **not de-authorized in the same way** as memory-noise
>    count100+ (A-FINAL-019).
> 3. A **source-tree fingerprint improves provenance** but does **NOT** by itself
>    turn a dirty worktree clean, make existing results formal, or replace an
>    external review-agent commit. It is **one required recorder/gate** toward
>    immutable reproduction, not a substitute for the review owner's clean
>    revision.

---

## 0. Method and evidence read

Read completely: `AGENTS.md`, `README.md`, `docs/protocol.md`,
`docs/experiment_standard.md`, `docs/agents/HANDOFF.md`, `docs/agents/README.md`,
`docs/letta_live.md`, `docs/stress_design.md`,
`docs/agents/reviews/A-AUDIT-002.md`, `A-FINAL-005/006/008/012/015/017/018/019/021/022/023.md`,
`A-APPROVAL-009/013/014/016/020.md`,
`docs/agents/qa/QA-002/010/011/012/015/016/017/018/019/020/021/022/023.md`;
the source modules `memory/base.py`, `memory/letta_adapter.py`,
`memory/registry.py`, `scenarios/delayed_recall.py`, `scenarios/world_update.py`,
`scenarios/memory_noise_stress.py`, `scenarios/failure_learning.py`,
`scenarios/controlled.py`, `scenarios/base.py`, `scenarios/registry.py`,
`agent/planner.py`, `core/runner.py`, `core/fairness.py`, `core/config.py`,
`cli.py`, `scripts/verify_letta_live.py`, `docker-compose.letta.yml`; and the
on-disk evidence under `results/` (120 classic + 10 pilot + 24 Native round1 +
12 Controlled campaign directories, each with manifest + 12 results + 24 logs).

Commands run (all read-only):
- `git rev-parse HEAD` / `git status --porcelain` / `git log --oneline -5`
- `.venv\Scripts\python.exe -m pytest -q` → **357 passed in 111.12s**
- Directory/file audits of `results/` (manifest schema, run counts, result/log
  counts per campaign, root-matrix backend counts, pilot, report)
- Hermetic Python one-offs (reading result JSON structure, backend-name-branch
  scan, test network-import scan, README ladder/roadmap checks)

Blockers / non-actions: `verify_letta_live.py` was NOT re-run (network/live call
forbidden by task); the strict live PASS is cited from QA-002 §2, QA-011 §4,
A-APPROVAL-009, A-AUDIT-002. `npm test` not re-run (no `minecraft/` changes).
Docker container status not re-checked (docker CLI not on PATH; container health
historically verified via full path in QA-002).

---

## 1. Summary table

| # | Requirement | Label | Key evidence |
|---|---|---|---|
| R1 | Docker Letta live, memory-only, unchanged DeepSeek planner, isolation | **COMPLETE** | docker-compose.letta.yml, letta_adapter.py, docs/letta_live.md, verify_letta_live.py, QA-002/011, A-APPROVAL-009 |
| R2 | MemoryBackend plugin boundary | **COMPLETE** | memory/base.py, memory/registry.py, grep (no backend-name branch), test_memory_base.py |
| R3 | Controlled vs Native distinction | **COMPLETE** | fairness.py, cli.py, controlled.py, stress_round1 (Native, rejected) vs stress_controlled_* |
| R4 | delayed_recall interference_count + similar_distractor_count | **PARTIAL** | delayed_recall.py; both params implemented; executed cells **not poolable**: legacy (10,0)/(50,5) round1, legacy (200,20) rounds 2–4, **only v2 point = (200,20) round5**; **v2 control (10,0), v2 (50,5), (500,50) unexecuted** |
| R5 | world_update A→B→C→D | **PARTIAL** | world_update.py; depth-3 Controlled run; **depth 1/2/4 Controlled never run** |
| R6 | memory_noise ladder 0/10/50/100/200/500/1000 | **PARTIAL** | memory_noise_stress.py; **only 0/10/50 executed; 100–1000 never executed** |
| R7 | failure_learning transfer (not exact retry) | **COMPLETE** (v2) | failure_learning.py v2; failure_transfer unregistered; counts 0/10/50 accepted |
| R8 | Parameters configurable | **COMPLETE** | cli.py --scenario-param, base.py apply_params, stress_design.md |
| R9 | Equal ExperienceEvent streams | **COMPLETE** | controlled.py; QA-012/015/017–023 byte-identical streams |
| R10 | Reset / no cross-episode leakage | **COMPLETE** | fairness.py; fairness.valid 12/12 everywhere; letta check C |
| R11 | No direct memory-to-action path | **COMPLETE** | planner.py memory_view_for_prompt, runner.py RunStep; A-FINAL-021 |
| R12 | Fairness controls | **COMPLETE** | fairness.py FairnessRecord; verified in every campaign |
| R13 | Real evidence / log completeness | **COMPLETE** (executed) | results/ manifests+results+logs; QA audits; no fabrication |
| R14 | Smoke vs formal status | **COMPLETE** (status); formal **MISSING by design** | experiment_standard.md §1; HANDOFF §7 |
| R15 | Failure Point definition / actual evidence | definition **COMPLETE**; actual evidence **INVALID FOR CLAIM** (none exists) | experiment_standard.md §3; A-FINAL-017/018/019/023 |

No requirement is fully MISSING. Three are PARTIAL because their planned ladders
were only partially executed. One is INVALID FOR CLAIM as actual evidence (R15
formal Failure Point). Full reasoning and citations below.

---

## 2. Requirement-by-requirement audit

### R1 — Docker Letta live memory-only integration, unchanged DeepSeek planner, isolation — COMPLETE

- **Integration (official Docker):** `docker-compose.letta.yml` pins
  `letta/letta:0.16.8` with an embedded PG15+pgvector, plus `ollama/ollama`
  serving `nomic-embed-text` for embeddings; health-gated `depends_on`;
  `letta-client` 1.12.1 in the venv (docs/letta_live.md:8–17).
- **Memory-only:** `letta_adapter.py` creates one agent per episode with
  `name` only (no model/embedding supplied, line 22–25); the server-side
  `LETTA_DEFAULT_LLM_HANDLE`/`LETTA_DEFAULT_EMBEDDING_HANDLE` exist only so
  `name`-only creation validates (docker-compose.letta.yml:63–69); the adapter
  only ever uses archival passages (create/search/delete/list) and never runs
  inference. Full ExperienceEvent round-trips via `event_payload=` passage tags
  (adapter docstring, lines 27–46; verified live against 0.16.8 per QA-011 §4).
- **Unchanged DeepSeek planner:** `agent/planner.py` is backend-agnostic
  (no letta/mem0/vector branch — verified by scan); the LLM is
  `OpenAICompatibleProvider(settings)` (cli.py:713) configured from `.env`
  `LLM_*` (DeepSeek). The grep across planner/runner/scenarios found no
  backend-name branch — only the bookkeeping fields `memory_backend` /
  `stats.backend`.
- **Isolation:** per-episode agent; `reset()` deletes the agent
  (letta_adapter.py:358–367); `scripts/verify_letta_live.py` checks A
  (exact add→retrieve round-trip), B (update, no stale item), C (reset isolates
  a fresh episode) — PASS against the live server (QA-002 §2, QA-011 §4,
  A-APPROVAL-009, A-AUDIT-002). All Controlled campaigns ran `letta` over live
  8283 with `fairness.valid=true`.
- **Caveat (not a defect):** `MemoryItem.score` is `None` for letta
  (agent-scoped archival search returns no relevance score); letta latency
  (~200 ms/call) includes HTTP + ollama embedding (README §9). Both disclosed.

### R2 — MemoryBackend plugin boundary — COMPLETE

- `memory/base.py` defines the abstract `MemoryBackend`
  (`add/retrieve/update/reset/stats`), `MemoryQuery/MemoryItem/MemoryStats` and
  the `EventRecordingBackend` proxy that records the complete offered event
  sequence for every backend including `none` (base.py:105–136).
- `memory/registry.py` maps name→factory; backends are injected only through
  the interface (registry.py:1–6).
- Verified: no planner/scenario/runner code branches on a backend name
  (scan of `agent/*.py`, `core/runner.py`, `scenarios/*.py` returned only field
  assignment of `memory_backend`/`stats.backend`). README §3 and AGENTS.md rule
  6 match the implementation.
- Hermetic adapter tests: `test_letta_adapter.py` (13 passed), `test_mem0_adapter.py`,
  `test_vector_memory.py`, `test_no_memory.py`, `test_memory_base.py` — all green in
  the full suite (357 passed this session).

### R3 — Controlled vs Native distinction — COMPLETE

- Enforced in code: `CAMPAIGN_MODE_NATIVE`/`CAMPAIGN_MODE_CONTROLLED`
  (fairness.py:47–52), `ScenarioResult.campaign_mode`, `ScenarioContext.campaign_mode`,
  CLI `--campaign-mode` with the central `validate_controlled_policy`
  (cli.py:397–443) failing closed before any bot/LLM/backend construction, and
  deterministic event identity in `scenarios/controlled.py`.
- The two outputs never mix: `results/stress_round1/` is Native exploratory and
  was **rejected for causal comparison** (world-state/run-order drift; A-FINAL-005
  decision; HANDOFF §4); all `stress_controlled_*` dirs are separate Controlled
  campaign outputs (manifests schema `controlled-campaign/v2` or `/v3`).
- **Scope note (not a failure of the distinction):** every Controlled run is
  mock-fixture (`BOT_MOCK=1`), not live Minecraft; A-FINAL-015 M-1 records that
  the Controlled rounds establish behavior under Controlled mock dynamics only,
  and Native/live-Minecraft v2 confirmation was never run.

### R4 — delayed_recall with interference_count + similar_distractor_count — PARTIAL

- **Implemented:** `scenarios/delayed_recall.py` `default_params =
  {interference_count: 10, similar_distractor_count: 0}`; **both difficulty
  parameters are fully implemented** and validated (`_validate_params`);
  retrieval metrics computed by stable event id (`compute_recall_metrics`, v2
  `compute_entity_key_metrics`); metrics re-derived from the causal step-0
  snapshot. Tests: `test_delayed_recall.py`, `test_delayed_recall_v2.py`,
  `test_stress_metrics.py` (green).
- **Executed cells (real Controlled runs) — NOT one semantics-consistent
  ladder:** `stress_controlled_round1` executed `(10,0)` and `(50,5)`
  (24 runs) as a **legacy** Controlled diagnostic; rounds 2/3/4 each re-ran
  `(200,20)` (12 runs each) under different **legacy** treatments — round 2
  contaminated (invalid for causal comparison, A-FINAL-006), round 3
  decontaminated, round 4 temporal; round 5 is the **only** `entity_key_v2`
  executed point, `(200,20)` (12 runs; its manifest carries
  `recall_semantics_version=entity_key_v2`). These cells **cannot be pooled**
  across semantics versions or treatments (experiment_standard.md §2;
  A-FINAL-006/008/012).
- **Partial semantics-consistent v2 ladder coverage:** under `entity_key_v2`
  only `(200,20)` has been executed (round 5). The planned v2 ladder is
  `(10,0) control → (50,5) → (200,20) → (500,50)`; the v2 control `(10,0)`,
  the `(50,5)` intermediate and the `(500,50)` maximum are **unexecuted under
  v2** — no raw evidence proves otherwise.
- **Missing / gated:** `(500,50)` is unexecuted in any semantics. Delayed-recall
  is **gated, not permanently stopped**: no further cell is currently authorized
  pending an immutable reviewed revision / A-issued task (A-FINAL-012 "Do not
  expand delayed-recall to formal n while H-1 remains"; experiment_standard.md
  §2 gating), so `(500,50)` remains planned but unexecuted — unlike memory-noise
  count100+, which is explicitly de-authorized (A-FINAL-019).
- Verdict: PARTIAL — both difficulty parameters are fully implemented and the
  `entity_key_v2` `(200,20)` point is evidenced, but the semantics-consistent
  v2 ladder has only that one executed point; v2 `(10,0)`, `(50,5)` and
  `(500,50)` remain unexecuted.

### R5 — world_update A→B→C→D — PARTIAL

- **Implemented:** `scenarios/world_update.py` `update_depth` (default 1, i.e.
  A→B) with `build_update_chain` (`seed + 100*k` per location); v2
  `temporal_chain_v2` builds a neutral chain where A→B→C→D = `update_depth=3`,
  current location = D by unique maximum semantic timestamp; typed
  `TemporalChainGroundTruth`; causal step-0 metrics.
- **Executed:** Controlled **depth 3 (A→B→C→D)** in
  `stress_controlled_world_update_v2_depth3_round1` — 12/12 valid diagnostics,
  accepted in QA-015 / A-FINAL-015. The classic 120-run matrix contains depth-1
  (A→B) native runs.
- **Missing:** Controlled **depth 1 control, depth 2, depth 4** were never run;
  the planned ladder (`depth 1 → 2 → 3 → 4`, experiment_standard.md §2) has a
  single data point (depth 3).
- Verdict: PARTIAL — the A→B→C→D construct is real and evidenced at depth 3, but
  the depth ladder that would locate a recall Failure Point was not executed.

### R6 — memory_noise ladder 0/10/50/100/200/500/1000 — PARTIAL

- **Implemented:** `scenarios/memory_noise_stress.py` `noise_count` (default 0);
  v2 `key_retention_v2` supports any count with prefix-stable keys/coordinates
  and no near-miss keys; hermetic generation tests cover counts 0/10/1000
  (QA-016 §3, 137 checks, 0 failures; `test_memory_noise_v2.py` green).
- **Executed (real Controlled runs): only 0/10/50**, each 12/12 valid
  (`stress_controlled_memory_noise_v2_count{0,10,50}_round1`; QA-017/018/019;
  A-FINAL-017/018/019). The transition is bracketed in `(10,50]` (diagnostic).
- **Missing / de-authorized:** counts **100/200/500/1000 were never executed**;
  A-FINAL-019 explicitly stops the noise ladder ("no count100, no further noise
  execution or formal Failure Point is authorized").
- Verdict: PARTIAL — the ladder is fully implementable and its generation logic
  is hermetically tested through 1000, but 4 of the 7 planned cells (100/200/
  500/1000) have no live evidence and are not authorized.

### R7 — failure_learning transfer rather than exact retry — COMPLETE (v2), with legacy caveat

- **v2 transfer construct:** `scenarios/failure_learning.py`
  `observed_precondition_v2` derives exactly one `TASK_FAILED` event from a REAL
  failed `attack_entity` ActionResult (fail-closed on unexpected success/empty
  error/vanished entity/pre-equipped hand); the transfer task targets the OTHER
  warded hostile (`source_transfer_entities` by seed parity) under different
  task wording — never an identical retry; no scenario-chosen actions
  (`run_goal` without `success_at`); behavior endpoints from ordered RunSteps
  (`compute_transfer_behavior_metrics`).
- **Executed:** v2 counts 0/10/50, 12/12 valid each
  (QA-021/022/023; A-FINAL-021/022/023). Across all 27 memory-backed runs the
  source failure stayed rank1/top1 and gold was equipped before the first
  transfer attack; the three seeds' success flips are planner action-selection
  variance, not interference effects.
- **Legacy exact retry:** the default `legacy` path remains a same-task retry
  plus scout debrief and is explicitly ineligible for transfer claims
  (TASK-020; A-AUDIT-002 Critical). `failure_transfer` is deliberately
  unregistered and invalid (scenarios/registry.py:26–31; experiment_standard.md
  §2 ladder row; docs/agents/HANDOFF §2).
- Verdict: the transfer requirement is met by the v2 treatment with real
  evidence. Legacy exact-retry still exists as the native default but is
  documented as non-transfer and excluded from any transfer claim.

### R8 — Parameters configurable — COMPLETE

- CLI: `--scenario-param KEY=VALUE` repeatable, type-coerced
  (`cli.py:_coerce_param_value`), merged over defaults with unknown keys and
  out-of-range values rejected (`ScenarioParamError`) **before** any bot/LLM/
  backend contact (base.py:apply_params; stress_design.md:22–29).
- Effective (defaults+overrides) params are recorded in `ScenarioResult.params`
  and repeated in `FairnessRecord.scenario_params`, so difficulty is auditable
  from a log alone. README §"M15B" and all campaign manifests carry
  requested==effective params.

### R9 — Equal ExperienceEvent streams — COMPLETE

- `scenarios/controlled.py` derives deterministic event ids and logical
  timestamps from `(seed, effective params, phase, ordinal)`; every Controlled
  scenario goes through `_next_event_identity`. Only the isolation `episode_id`
  differs between backends.
- Verified byte-level in every accepted campaign: QA-012 (221 events), QA-015
  (9 events), QA-017/018/019 (51/1/11 events), QA-021/022/023 (1/11/51 events) —
  identical across the four backends after `episode_id` normalization, with
  manifest `input_stream_fingerprint` matches.
- Scope note: equality holds in Controlled mode by construction; Native streams
  are not equal (that is why `stress_round1` was rejected for causal comparison,
  A-FINAL-005).

### R10 — Reset / no cross-episode leakage — COMPLETE

- `core/fairness.py` `FairnessChecker.check()` resets the episode that actually
  ran, probes the reset scope and a brand-new scope with a query drawn from the
  run's own content, and best-effort-cleans any lazily created scope
  (fairness.py:122–189). A reset error, probe error, or returned item marks
  `valid=False` (still written to the log — never silently dropped).
- Every result across every Controlled campaign has `fairness.valid=true`,
  `post_reset_items=0`, `fresh_scope_items=0`; per-run fresh backend instances
  (cli.py:748). Live letta isolation PASS (verify_letta_live.py check C; QA-002
  §3 four-backend isolation table).

### R11 — No direct memory-to-action path — COMPLETE

- The planner receives memories only as a backend-neutral semantic view
  (`memory_view_for_prompt`: exactly `actor,target,event_type,location,context,
  outcome,timestamp`; planner.py:146–206), never ids/scores/metadata/raw events.
- `RunStep.retrieved_items` snapshots the exact causal retrieval
  (runner.py:163–182); scenarios only set the goal and an optional `success_at`
  position — they never choose actions. The failure-learning v2 transfer runs
  with no `success_at` and no scenario-selected actions (A-FINAL-021).
- Behavioral evidence that the loop is not a hardcoded top-1 executor: letta
  seed44 succeeded with the target at rank 4 in v2 delayed-recall (QA-012 §8.2)
  and noise count-50 (A-FINAL-017), i.e., the LLM resolved evidence below rank 1.

### R12 — Fairness controls — COMPLETE

- `FairnessRecord` captures `minecraft_version`, `world_seed`, `planner_model`,
  `temperature`, `system_prompt_hash`, `tool_set_hash`,
  `planner_user_template_hash` (= documented `988e01277f…`), `scenario`,
  `scenario_params`, `campaign_mode`, `fixture_selector/identity`, `run_seed`,
  reset/probe fields and `valid`.
- Verified identical across backends within every seed in every campaign
  (QA-012 §4, QA-015 §5, QA-021–023 §3). `minecraft_version="unknown"` and
  `world_seed=null` are the documented N/A mock values, not failures.

### R13 — Real evidence / log completeness — COMPLETE (for executed runs)

- On-disk evidence: 120 classic matrix logs (3 scenarios × 4 backends × seeds
  42–51, root `results/`), 10 pilot logs, 24 Native round1 logs, and 12
  Controlled campaign directories each with `campaign_manifest.json` + 12
  `scenario_*.json` + 24 `logs/*.{stdout,stderr}.log` + campaign-local `stores/`.
- Verified in this session: every campaign dir has runs_ok == scheduled and
  results==12, logs==24; QA audits confirmed 1:1 file binding, unique
  run/episode ids, mtime windows confined to the campaign window, no orphan/
  missing/duplicate, and no fabricated values (N/A stays null).
- No unmeasured value is reported as a number; AGENTS.md rule 5 holds.

### R14 — Smoke vs formal experiment status — COMPLETE (status); formal phase MISSING by design

- `docs/experiment_standard.md` §1: smoke = 3 runs/cell (`--runs 3 --seed 42`
  → effective seeds 42/43/44); **formal phase is "not approved yet"** (sample
  size pending an A-issued immutable revision). §2: v2 execution gated; no
  formal sample is pre-registered.
- All executed cells are exactly 3 seeds/backend, labeled diagnostic/smoke
  everywhere (every QA and A-FINAL). HANDOFF §7 records "no formal n>=10 cell or
  Failure Point is approved" as an open High.
- Verdict: the *status discipline* is complete and honestly tracked; the formal
  phase is intentionally not executed. Any report that treated current data as
  formal would be invalid.

### R15 — Failure Point: definition vs actual evidence — definition COMPLETE; actual evidence INVALID FOR CLAIM

- **Definition (COMPLETE):** `docs/experiment_standard.md` §3 — a backend's
  failure point on a scenario is the lowest ladder level where its formal-phase
  task success rate < 80%; interpolation between ladder levels is never allowed;
  a backend failing at the lowest non-control level is "fails at first step";
  the table is computed from logs only.
- **Actual evidence (INVALID FOR CLAIM):** **no formal Failure Point has been
  computed for any backend/scenario**, and the existing diagnostics actively
  rule some out:
  - noise: the `(10,50]` bracket is explicitly "not a formal Failure Point"
    (A-FINAL-017/018/019); only 3 seeds × 3 counts.
  - failure-learning: the source failure never left rank1/top1 through count 50 —
    no retrieval failure point observed (A-FINAL-023).
  - world-update depth 3: current-fact recall is at ceiling (D retrieved 9/9);
    behavior differs but recall does not — no recall failure threshold
    (A-FINAL-015).
  - delayed-recall v2: failures track target *availability*, not a ladder
    threshold, and the (500,50) cell was never run.
  - Every A-FINAL carries the standing H-1: dirty, non-immutable worktree → no
    formal claim. Therefore any current statement of a "Failure Point" would be
    unsupported by the definition (which requires formal-phase success rates).
- Verdict: the definition exists and is correct; there is zero valid formal
  Failure Point evidence — label the evidence **INVALID FOR CLAIM**.

---

## 3. Documentation drift and untested branches (green tests ≠ coverage)

Documentation drift:
1. `README.md` §10 roadmap marks M2/M3 unchecked although implemented
   (HANDOFF §7 "documentation drift"; confirmed by grep: `- [ ] M2`, `- [ ] M3`).
2. `docs/development_plan.md` is missing; the tracked `docsdevelopment_plan.md`
   (repo root) is a stale M4-era prompt (HANDOFF §1/§7; confirmed absent/present
   this session).
3. `framework_registry.yaml` requested in HANDOFF §7 does not exist (confirmed
   absent).
4. README §"M15B" still presents the full noise ladder (0/10/50/100/200/500/1000)
   and delayed-recall ladder (10/50/200/500) as the active plan; the accepted
   state (experiment_standard.md, which is authoritative) **de-authorizes** noise
   above 50 (A-FINAL-019) and **gates** delayed-recall at (200,20) — no further
   delayed-recall cell is currently authorized pending an immutable reviewed
   revision / A-issued task, with (500,50) remaining planned but unexecuted (not
   de-authorized like noise count100+). README is stale relative to the accepted
   ladder endpoints.
5. Cosmetic: campaign CLI stdout prints legacy metric display keys (`??` labels)
   while JSON carries correct v2 fields (A-FINAL-015 L-1).

Untested / unexecuted branches (implementation present, no live evidence):
- `memory_noise_stress` live counts 100/200/500/1000 (generation only tested
  hermetically at 1000, QA-016 §3).
- `delayed_recall` cell (500,50).
- `world_update` Controlled depths 1/2/4 (depth 3 is the only data point).
- Native/live-Minecraft execution of any v2 treatment (all Controlled runs are
  mock-fixture).
- Mem0 optional spaCy/BM25 lexical features (absent in every run — disclosed).
- Cost accounting: backend-internal init/embedding/LLM work is not separated
  from per-operation latency (no efficiency claim possible).
- Cross-session persistence (HANDOFF §7 core-coverage gap): N/A, not implemented
  as a scenario.

---

## 4. Highest-value next bounded task for A+C (no git ownership, no B)

**Recommendation: implement + independently verify a source-tree code
fingerprint recorder and a pre-registration template (the immutable-
reproducibility gate), NOT a new campaign.**

Rationale: the recurring Critical/High across every accepted review is H-1 —
"results are tied to a dirty, non-immutable worktree; no clean code
fingerprint represents the exact producer state" (A-FINAL-012/015/017/018/019,
HANDOFF §7 High). This single gap blocks the formal phase, the Failure Point
rule, and any ranking. It is addressable without git ownership or B:

- A (taking over implementation as it did in TASK-020, with A-IMPLEMENTATION-020
  as precedent) adds a bounded change to `scripts/run_controlled_campaign.py`
  and the CLI run path: compute a source-tree digest (SHA-256 over the benchmark
  source/test/config files actually read, independent of git) plus the optional
  `git rev-parse HEAD`/dirty-state string passed via env, and record both in the
  campaign manifest and `FairnessRecord` (as an optional backward-compatible
  field), leaving `docs/protocol.md` and every result schema otherwise unchanged.
- C independently QA's it hermetically (determinism under identical trees,
  sensitivity to any single-file mutation, backward load of old manifests,
  full `pytest`), exactly the QA-016/QA-020 pattern.
- **Provenance ≠ immutability (correction):** recording a source-tree fingerprint
  improves provenance but does **NOT** by itself turn a dirty worktree clean,
  make existing results formal, or replace an external review-agent commit. It
  is **one required recorder/gate** toward immutable reproduction — a necessary
  companion to the review owner's clean revision, not a substitute for it.
- No campaign runs; no protocol change; no git mutation; no B needed.

This unblocks the "clean reviewed revision + pre-registered paired sample"
gate that experiment_standard.md §1 and every A-FINAL require before any formal
Failure Point. A second, smaller bundled item (also A+C, no B): repair the
documentation drift (README roadmap checkboxes and ladder-stop wording,
`docsdevelopment_plan.md` stale file, framework_registry note) so the docs stop
asserting unexecuted ladders. No new experiment is authorized by this audit.

---

## 5. Files read / commands / blockers

Files read (all, no modification): see §0 list plus
`docs/agents/reviews/A-APPROVAL-013/014/016/020.md`, `A-AUDIT-002.md`, and the
raw result JSON structure probes.

Commands run:
- `git rev-parse HEAD`, `git status --porcelain | Measure-Object -Line`,
  `git log --oneline -5`
- `.venv\Scripts\python.exe -m pytest -q` → **357 passed**
- PowerShell/read-only audits of `results/` manifests, result/log counts, root
  matrix backend counts, README ladder/roadmap lines, `Test-Path` for the
  missing docs, hermetic Python scans for backend-name branches and test
  network imports.

Blockers:
- No network/live calls permitted → `verify_letta_live.py` not re-run; live PASS
  cited from prior accepted evidence.
- Docker CLI not on PATH → container-level status N/A this session.
- `npm test` not run (no `minecraft/` changes); TS side untouched.
- Repository remains a dirty, non-immutable worktree at HEAD `cbaa276` (99 dirty
  porcelain entries this session) — consistent with the standing H-1; this audit
  adds no new evidence beyond the already-accepted diagnostics.

Only repo artifact created: `docs/agents/qa/QA-024-COMPLETION-AUDIT.md`.
