# TASK-015 — One Controlled world-update v2 depth-3 diagnostic smoke

Issued by: Agent A  
Executor/independent auditor: Agent C  
Post-run reviewer: Agent A  
Status: **exactly one campaign invocation authorized**

## Research boundary

Run one small diagnostic matrix for the approved
`world_update/update_semantics_version=temporal_chain_v2` treatment at
`update_depth=3` (A→B→C→D). This is the first real evidence for this treatment.

It is not a formal sample, framework ranking or Failure Point. Do not pool it
with legacy world-update or delayed-recall data. Do not expand/retry/resume.

## Immutable execution specification

- output directory:
  `results\stress_controlled_world_update_v2_depth3_round1`;
- scenario: `world_update`;
- one cell name: `depth3_temporal_chain_v2`;
- effective/requested params:
  `update_depth=3`,
  `update_semantics_version=temporal_chain_v2`;
- seeds: `42,43,44`;
- backends: `none,vector,mem0,letta`;
- expected schedule: 12 runs, seed-major and counterbalanced;
- one fresh mock adapter per run, owned by the campaign runner;
- exactly one invocation, no manual per-run CLI calls.

Exact PowerShell command from repository root:

```powershell
.venv\Scripts\python scripts\run_controlled_campaign.py `
  --results-dir results\stress_controlled_world_update_v2_depth3_round1 `
  --scenario world_update `
  --seeds 42,43,44 `
  --backends none,vector,mem0,letta `
  --cell '{"name":"depth3_temporal_chain_v2","params":{"update_depth":3,"update_semantics_version":"temporal_chain_v2"}}'
```

## Preflight (read-only, before invocation)

1. Read AGENTS, HANDOFF, A-APPROVAL-013, A-APPROVAL-014, QA-014 and this task.
2. Confirm the exact output path is absent. If it exists for any reason, stop;
   do not delete, rename, resume or choose another directory.
3. Record HEAD/dirty status without staging/commit/push.
4. Confirm repo venv Python and `minecraft/dist/index.js` exist.
5. Confirm local Letta 8283 is reachable. Record that user-owned live bot 8081
   and Minecraft 25565 are reachable and leave them untouched; the campaign
   uses fresh dynamic-port mock adapters instead.
6. Confirm there is no stray `python -m minemembench` or mock campaign adapter.
   The pre-existing `.smoke_server.py` process and live bot are user-owned;
   leave them untouched.
7. Do not read/print `.env` or secrets.

Any failed preflight item means STOP and QA report `N/A`; do not invoke.

## Execution rules

- Execute the exact command once.
- Do not change cell name, params, order, seeds, backends, result path or code.
- Do not retry a failed run or invocation. The runner's manifest/error/logs are
  the evidence; stop and audit the partial campaign.
- Do not manually start/stop Letta, Minecraft or the live bot.
- Do not run any unrelated test/campaign during the invocation.
- After completion, confirm no campaign-owned mock adapter remains.

## Mandatory post-run audit

Write only `docs/agents/qa/QA-015.md` outside the generated campaign directory.
Do not modify code/tests/docs/results.

### E1 — manifest/run integrity

- schema `controlled-campaign/v2`, Controlled mode, exact scenario/semantics,
  cell requested/effective params, seeds/backends and 12-entry schedule;
- unique indices and `(scenario,effective params,seed,backend)` identities;
- status/returncode/error for every entry; exactly one linked result per `ok`
  entry; stdout/stderr paths exist; no missing or duplicate result link/run id;
- if stopped early, pending remainder remains pending and every partial file is
  reported — never silently excluded.

### E2 — fairness/control variables

For every result: exact scenario/seed/backend/mode/effective params; fairness
exists and matches scenario/params/run seed/Controlled fixture; `valid=true`
for an accepted run. Across backends for each seed compare model, temperature,
system prompt hash, tool hash, planner user-template hash, Minecraft version,
world seed and canonical fixture identity. N/A is not failure.

### E3 — input equality and temporal semantics

For each seed, after normalizing only `episode_id`, the complete injected
9-event stream must be identical across all four backends:

- 4 supply-cache chain events A/B/C/D with `ctrl-` ids, common actor/type/
  context schema, unique coordinates and strictly increasing timestamps;
- 5 noise events;
- no moved/stale/current/latest/correctness/priority labels;
- ground truth has ordered A/B/C stale ids, D current id and literal
  `supply_cache`; D is the unique maximum chain timestamp;
- goal exactly `Retrieve the supply cache at its current location.` and contains
  no coordinate.

### E4 — independent causal metric derivation

From each JSON's typed ground truth + `run_log.steps[0].retrieved_items`,
recompute exactly:

- current rank/recall/precision/top1;
- stale fact retrieval rate and stale memory rate;
- compatibility mirrors;
- retrieval evidence source.

Separately rederive `stale_action` from the first move and
`final_distance_to_current` from the run log/current coordinate. Confirm the
diagnostic probe may differ but feeds no headline metric. Empty retrieval is a
measured current recall miss; undefined rates stay N/A.

### E5 — data integrity and narrow summary

Report per backend/seed: success, tokens, LLM calls/latency if logged,
retrieval rank/recall/top1/stale rates, stale action, final distance, error and
crash. Check duplicate run ids, duplicate event ids outside expected
cross-backend identity, missing logs, wrong seeds, cross-episode contamination,
N/A mishandling and silently excluded failures.

Summarize only this 3-seed diagnostic. Do not claim superiority or a Failure
Point. Note the dirty-worktree/immutable-revision limitation and the earlier C
QA incident as excluded non-evidence.

## Stop condition

After QA-015 is written, stop and hand raw paths/results to A. No second
campaign, no wider depth/noise ladder and no B repair unless A reviews first.
