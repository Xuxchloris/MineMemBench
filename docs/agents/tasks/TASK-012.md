# TASK-012 — Controlled entity-key v2 `(200,20)` diagnostic smoke

Issued by: Agent A  
Assignee: Agent C  
Release gate: `docs/agents/reviews/A-APPROVAL-011.md`  
Status: exactly one campaign invocation authorized

## Research question

After repairing delayed-recall semantics, can each memory backend retrieve
and use the explicitly named opaque entity-key-to-location association under
200 unrelated facts and 20 simultaneously true similar-key distractors?

This is a three-seed diagnostic smoke, not a framework ranking or formal
Failure Point experiment.

## Preflight

- Read `AGENTS.md`, `docs/agents/HANDOFF.md`, TASK-011, A-APPROVAL-011,
  B-COMPLETION-011 and QA-011.
- Require listeners 8081, 8283 and 25565 to be open and the output path below
  to be absent. Do not restart or stop user-owned services.
- Require no active stray campaign/mock process. Do not read or print `.env`.
- Do not modify production code, tests, protocol, campaign script, historical
  results, git state or experiment parameters.

## Exact execution

Run exactly once from the repository root:

```powershell
.venv\Scripts\python.exe scripts\run_controlled_campaign.py `
  --results-dir results\stress_controlled_round5_entity_key_v2_200_20 `
  --seeds 42,43,44 `
  --backends none,vector,mem0,letta `
  --cell '{"name":"stress_200_20_entity_key_v2","params":{"interference_count":200,"similar_distractor_count":20,"recall_semantics_version":"entity_key_v2"}}'
```

Expected schedule: exactly 12 runs, seed-major cyclic counterbalancing, one
cell, four backends, seeds 42/43/44. The campaign runner must create fresh
per-run mock bots and campaign-local Vector/Mem0 stores.

Do not retry, resume, add a run/backend/cell, reuse an output directory or
execute another command if any run process fails. Preserve the partial
manifest/logs and stop for A.

## Mandatory independent audit

Write `docs/agents/qa/QA-012.md` and include exact command, exit code, raw
paths and PASS/FAIL/N/A for all checks below.

### Manifest and run integrity

- output path was absent before execution;
- manifest schedules exactly 12 unique `(backend, seed, cell)` runs;
- seed-major cyclic order matches the precomputed scheduler;
- every scheduled run is bound one-to-one to one result JSON and stdout/stderr
  log; run/episode ids are unique; no missing/duplicate/retried/excluded run;
- `campaign_mode=controlled`, exact three scenario params, fixture identity,
  DeepSeek model/temperature/tools/template hash and normalized WorldState are
  equal across backends for each seed;
- every fairness record is valid and reset/fresh-scope probes are empty.

### Semantic and input equality

- each run offered exactly 221 events: one target, 200 unrelated noise facts,
  20 off-target entity facts;
- after replacing only `episode_id`, all offered events (including ids and
  logical timestamps) are identical across the four backends per seed;
- target/distractor keys and coordinates are unique; every candidate shares
  actor/type/context schema; Hamming distance is 1 or 2; all facts can be true;
  no correctness/staleness label exists;
- goal names exactly the out-of-band target key and no coordinate;
- `evaluation_ground_truth` has the v2 version, one target event/key and the
  ordered 20 distractor ids, none of which leak into the planner prompt;
- planner-visible memories contain only `MEMORY_VIEW_FIELDS`; backend ids,
  scores, metadata and evaluation ground truth are absent.

### Metrics and causal behavior

- independently rederive `fact_retrieval_rank`, `target_recall`,
  `target_retrieval_precision` and `off_target_retrieval_rate` solely from
  `evaluation_ground_truth` plus `run_log.steps[0].retrieved_items`;
- v2 `recall_accuracy == target_recall`; `wrong_fact_rate` and legacy
  `retrieval_precision` are N/A;
- for every run record success, step-0 retrieval count/rank, first retrieved
  candidate, chosen coordinates, whether chosen equals target/top-1, final
  distance, prompt/completion tokens, add/retrieve latency, errors and crash;
- NoMemory must have empty causal retrieval and measured target recall 0;
- distinguish target absence from N/A; do not count N/A as failure and do not
  exclude failed runs.

### Research interpretation

- compare round 5 with round 4 descriptively only; never pool them because
  their semantics differ;
- state the narrow causal conclusion supported by three seeds;
- if memory backends all succeed, label it a ceiling at this treatment—not
  proof that frameworks are equal;
- if outcomes differ, explain whether the cause is target retrieval rank,
  target absence, or planner behavior; do not claim framework superiority.

## Stop condition

After QA-012 is written, do not run another experiment or modify code. Return
the raw result path and report path to Agent A for final research audit.
