# TASK-018 — One memory-noise v2 count-0 Controlled control smoke

Issued by: Agent A  
Executor/independent auditor: Agent C  
Post-run reviewer: Agent A  
Status: **exactly one campaign invocation authorized**

## Research boundary

Run the planned `noise_count=0` control for key-retention v2 so TASK-017's
count-50 misses can eventually be interpreted against a same-treatment
baseline. This remains a 3-seed Controlled diagnostic, not a formal sample,
framework ranking or Failure Point. Do not retry/resume/expand.

## Immutable execution specification

- output: `results\stress_controlled_memory_noise_v2_count0_round1`;
- scenario: `memory_noise_stress`;
- cell: `noise0_key_retention_v2`;
- params: `noise_count=0`,
  `noise_semantics_version=key_retention_v2`;
- seeds `42,43,44`;
- backends `none,vector,mem0,letta`;
- 12 counterbalanced runs; fresh campaign-owned mock adapter per run;
- exact command once only:

```powershell
.venv\Scripts\python scripts\run_controlled_campaign.py `
  --results-dir results\stress_controlled_memory_noise_v2_count0_round1 `
  --scenario memory_noise_stress `
  --seeds 42,43,44 `
  --backends none,vector,mem0,letta `
  --cell '{"name":"noise0_key_retention_v2","params":{"noise_count":0,"noise_semantics_version":"key_retention_v2"}}'
```

## Preflight / execution

Read AGENTS, HANDOFF, A-APPROVAL-016, QA-016, TASK-017, corrected QA-017,
A-FINAL-017 and this task. Confirm the exact output path is absent, record
HEAD/dirty state, venv/dist exist, Letta 8283 healthy, no stray campaign/mock,
and leave user live services untouched. Never read/print `.env`. Failed
preflight means QA N/A and no invocation. Run the exact command once; never
retry, resume, replace or manually execute a cell.

## Mandatory audit

Write only `docs/agents/qa/QA-018.md` outside generated results.

- Audit manifest/fairness/isolation/log completeness exactly as TASK-017.
- Per seed, verify one injected target event, no noise events; streams identical
  across backends after only episode normalization; typed GT has exact target
  id and empty ordered `noise_event_ids`; neutral schema/goal/no leakage.
- Independently rederive rank/recall/precision/noise-rate/top1/retrieved count
  from GT + step0 snapshot. With nonempty target-only retrieval, noise rate
  must be 0; undefined values remain N/A.
- Report all backend/seed success/retrieval/token/latency/error facts.
- After auditing count0 on its own, add a clearly labeled paired diagnostic
  contrast to the already accepted count50 raw results for the same seeds:
  target presence, rank/top1 and success only. Do not pool cells, do not run a
  statistical test, and do not claim framework ranking/noise Failure Point.
- Detect/report any mismatch with corrected QA-017. Do not repeat its prior
  Mem0 aggregate typo; derive all aggregates programmatically from JSON.
- Confirm no mock remains; stop for A. No further ladder point.
