# A-APPROVAL-016 — memory-noise key-retention v2 core

Date: 2026-08-08  
Reviewer: Agent A  
Basis: TASK-016, B-COMPLETION-016, QA-016, production/test diff  
Decision: **APPROVED for one separately specified diagnostic smoke; no formal ladder or ranking**

## Critical

None.

## High

### H-1 — Formal evidence remains gated on an immutable revision

- **Location:** repository HEAD `cbaa276` with a heavily dirty worktree.
- **Reason:** the exact reviewed implementation is not represented by a clean
  commit/code fingerprint; repository rules prohibit agents from staging,
  committing or pushing.
- **Impact on conclusions:** **Yes.** Future data from this state are bounded
  diagnostic evidence, not a reproducible formal comparison or Failure Point.
- **Minimum repair:** repository owner creates a clean reviewed revision before
  any pre-registered formal sample. Do not relabel prior smoke retroactively.

## Medium

### M-1 — The construct is opaque-key retention under volume, not broad semantic memory

- **Location:** `memory_noise_stress.py` v2 goal/events/key generation.
- **Reason:** the goal names one exact opaque key and all candidate facts share
  a neutral key-to-coordinate schema. This cleanly isolates volume/capacity and
  ranking, but exact-token retention is a narrow construct; semantic similarity
  is intentionally delegated to delayed-recall v2.
- **Impact on conclusions:** **Yes, external validity only.** It must not be
  reported as overall long-term-memory quality.
- **Minimum repair:** combine it with the independently valid delayed-recall
  and world-update treatments before any broad conclusion; keep scenario-level
  claims explicit.

### M-2 — The upper ladder is operationally expensive and not yet calibrated

- **Location:** planned `noise_count=0/10/50/100/200/500/1000` ladder;
  sequential `memory.add` loop and backend latency evidence.
- **Reason:** Mem0 has previously taken roughly 3 seconds per add in this local
  configuration. A three-seed, four-backend count-1000 cell could take hours
  before planner calls, and a full seven-level smoke would contain 84 runs.
- **Impact on conclusions:** **No for core validity; yes for unbiased execution
  if time/cost pressure causes retries, truncation or selective exclusions.**
- **Minimum repair:** start with one pre-registered count-50 diagnostic, audit
  completeness and latency, then A selects the next ladder point. No adaptive
  retry or silent truncation.

### M-3 — Retrieval rates require the retrieved-count denominator beside them

- **Location:** `target_retrieval_precision`, `noise_retrieval_rate`,
  `retrieved_item_count`.
- **Reason:** backend return-set sizes can differ, so raw rates are not directly
  comparable without the retrieved item count and target rank/top-1.
- **Impact on conclusions:** **Yes for cross-framework rate ranking; no for
  metric correctness.**
- **Minimum repair:** every report presents rank, recall, top-1, retrieved count
  and noise rate together; normalize retrieval budget before a precision claim.

## Low

### L-1 — B's report mislabels one test count

- **Location:** `B-COMPLETION-016.md` says six `test_q16_*`; five exist and the
  sixth covered test is the extended `test_q4_schedule_run_identities_are_unique`.
- **Reason / impact:** cosmetic accounting only; C reproduced all behavior.
- **Minimum repair:** none required.

## Accepted properties

- Legacy/native behavior remains the default and old JSON loads.
- Controlled mode approves only `memory_noise_stress + key_retention_v2` and
  fails before bot/LLM/backend/output construction for other versions.
- Target key/coordinate and noise semantic prefixes are count-independent;
  target plus 1000 noise facts have unique keys/coordinates and neutral common
  schema with no prompt-visible correctness labels.
- Same-cell streams are identical across backends after only `episode_id`
  normalization; Controlled ids/timestamps are deterministic and cell-specific.
- Typed ground truth is evaluation-only. Headline metrics use only ground truth
  plus the causal step-0 retrieval snapshot; a differing diagnostic probe does
  not change them.
- Campaign planning retains semantic duplicate rejection, counterbalancing,
  pre-registration, strict result/fairness validation and stop-on-first-failure.
- B: 79 focused / 332 full passed. C independently reproduced 79/332 and ran
  137 additional checks with zero failures; no live/network action occurred.

## Release boundary

Core approval does not itself run a campaign. A may issue one exact, fresh,
three-seed count-50 diagnostic over none/vector/mem0/letta. C must execute the
command once, audit all raw results, and stop for A before any second count.
