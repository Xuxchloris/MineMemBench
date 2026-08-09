# TASK-017 — One memory-noise v2 count-50 Controlled diagnostic smoke

Issued by: Agent A  
Executor/independent auditor: Agent C  
Post-run reviewer: Agent A  
Status: **exactly one campaign invocation authorized**

## Research boundary

Run one bounded diagnostic matrix for
`memory_noise_stress/noise_semantics_version=key_retention_v2` at
`noise_count=50`. This validates the new treatment against real memory
backends and measures a first operational cost point. It is not the full
noise ladder, a formal sample, framework ranking or Failure Point. Do not
expand, retry, resume or add a control cell.

## Immutable execution specification

- output directory:
  `results\stress_controlled_memory_noise_v2_count50_round1`;
- scenario: `memory_noise_stress`;
- one cell: `noise50_key_retention_v2`;
- requested/effective params:
  `noise_count=50`, `noise_semantics_version=key_retention_v2`;
- seeds: `42,43,44`;
- backends: `none,vector,mem0,letta`;
- expected schedule: 12 runs, seed-major and counterbalanced;
- one fresh campaign-owned `BOT_MOCK=1` adapter per run;
- exact command once, no manual run, retry, resume or expansion.

Exact PowerShell command from repository root:

```powershell
.venv\Scripts\python scripts\run_controlled_campaign.py `
  --results-dir results\stress_controlled_memory_noise_v2_count50_round1 `
  --scenario memory_noise_stress `
  --seeds 42,43,44 `
  --backends none,vector,mem0,letta `
  --cell '{"name":"noise50_key_retention_v2","params":{"noise_count":50,"noise_semantics_version":"key_retention_v2"}}'
```

## Preflight and safety

Before invoking, read AGENTS, HANDOFF, TASK-016, B-COMPLETION-016, QA-016,
A-APPROVAL-016 and this task. Confirm:

1. the exact output directory is absent; otherwise STOP without deleting,
   renaming, resuming or choosing another path;
2. HEAD/dirty state is recorded; no git action;
3. repo venv and `minecraft/dist/index.js` exist;
4. Letta 8283 is healthy; do not start/stop/reconfigure it;
5. no stray campaign or `BOT_MOCK=1` process exists; user-owned live bot,
   Minecraft and `.smoke_server.py` processes remain untouched;
6. `.env` and secrets are never read or printed.

Any failed preflight means report N/A and stop. Do not call live bot 8081 or
Minecraft as part of the campaign; Controlled mock adapters are fresh and
campaign-owned.

## Mandatory post-run audit

Write only `docs/agents/qa/QA-017.md` outside the generated directory.

- Manifest: v2 schema, exact cell/params/seeds/backends, unique identities,
  12 statuses/return codes, one linked result per ok, all logs present, no
  missing/duplicate/excluded run.
- Fairness: same model, temperature, prompt/tool/template hashes, fixture and
  seed across backends; valid reset/fresh-scope isolation every run.
- Inputs: per seed, 51 injected events identical across backends after only
  `episode_id` normalization; target first, 50 ordered noise facts; common
  actor/type/context schema; unique keys/coordinates; no banned labels; typed
  GT target/noise ids exactly match the stream; coordinate-free goal.
- Metrics: independently recompute target rank/recall/precision, noise rate,
  top-1 and retrieved count from typed GT + step-0 snapshot. Verify legacy
  metrics stay N/A, evidence source is exact, diagnostic probe feeds no
  headline metric, and task/token/call/latency fields match run logs/stats.
- Data integrity: no cross-episode event, duplicate run/event id, wrong seed,
  missing log, unreported error/crash, N/A-as-failure or silent exclusion.
- Report every backend/seed outcome and latency. Distinguish add-volume cost
  from normalized efficiency; do not rank frameworks or declare a Failure
  Point. Explicitly call this Controlled mock-fixture evidence, not Native
  Minecraft evidence.

After QA-017, confirm no campaign mock remains and stop for A. No second
campaign or B repair unless A reviews first.
