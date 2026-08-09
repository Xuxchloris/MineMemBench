# TASK-019 — One memory-noise v2 count-10 Controlled diagnostic smoke

Issued by: Agent A  
Executor/independent auditor: Agent C  
Post-run reviewer: Agent A  
Status: **exactly one campaign invocation authorized**

## Research boundary

Run the planned first non-control point `noise_count=10` for
`key_retention_v2`. Together with the already accepted count0 and count50
diagnostics, this locates whether the observed Mem0/Letta retrieval loss begins
at the first ladder step or between 10 and 50. This is still a 3-seed
Controlled diagnostic, not a formal sample, framework ranking or Failure
Point. No other count is authorized.

## Immutable execution specification

- output: `results\stress_controlled_memory_noise_v2_count10_round1`;
- scenario: `memory_noise_stress`;
- cell: `noise10_key_retention_v2`;
- params: `noise_count=10`,
  `noise_semantics_version=key_retention_v2`;
- seeds `42,43,44`;
- backends `none,vector,mem0,letta`;
- expected schedule: 12 seed-major, counterbalanced runs;
- one fresh campaign-owned `BOT_MOCK=1` adapter per run;
- exact command once only:

```powershell
.venv\Scripts\python scripts\run_controlled_campaign.py `
  --results-dir results\stress_controlled_memory_noise_v2_count10_round1 `
  --scenario memory_noise_stress `
  --seeds 42,43,44 `
  --backends none,vector,mem0,letta `
  --cell '{"name":"noise10_key_retention_v2","params":{"noise_count":10,"noise_semantics_version":"key_retention_v2"}}'
```

## Preflight and execution

Read AGENTS, HANDOFF, TASK-016, A-APPROVAL-016, corrected QA-017,
A-FINAL-017, QA-018, A-FINAL-018 and this task. Before invoking, verify:

1. exact output path absent — otherwise STOP, do not delete/rename/resume;
2. HEAD/dirty state recorded, no git action;
3. repo venv and `minecraft/dist/index.js` exist;
4. Letta 8283 healthy and untouched;
5. no stray campaign or `BOT_MOCK=1`; user services untouched;
6. `.env`/secrets never read or printed.

Any failure means QA N/A and no invocation. If all pass, run the exact command
once. Never retry, resume, replace, manually run a cell or add a count.

## Mandatory audit

Write only `docs/agents/qa/QA-019.md` outside generated results.

- Manifest/fairness/reset/log/data-integrity checks match TASK-017/018.
- Per seed, verify exactly 11 injected events (target first + 10 ordered
  noise), common neutral schema, unique keys/coordinates, no banned labels,
  coordinate-free goal and exact typed GT ids.
- Complete streams must match across backends after only `episode_id`
  normalization.
- Independently rederive target rank/recall/precision, noise rate, top1 and
  retrieved count from typed GT + causal step0 retrieval. Legacy metrics stay
  N/A; diagnostic probe cannot feed headline metrics.
- Programmatically report all 12 success/retrieval/token/latency/error facts.
- Programmatically read the accepted count0 and corrected count50 raw JSONs
  and produce a paired 0/10/50 table for each seed/backend: target presence,
  rank, top1 and success. Do not pool cells or run inferential statistics.
- Derive every backend aggregate from JSON, never hand-count. Explicitly
  validate count50 Mem0 is 1/3, not the superseded typo.
- State only which interval remains plausible from these three smoke points;
  no framework ranking or formal Failure Point.
- Confirm no campaign mock remains and stop for A. No additional ladder point.
