# TASK-014 — Generalize Controlled CLI/campaign for world-update v2

Issued by: Agent A  
Assignee: Agent B  
Independent verifier: Agent C  
Status: implementation and hermetic tests authorized; live/campaign execution
is not authorized

## Objective

Generalize the already-audited Controlled execution plumbing from
`delayed_recall` to the approved `world_update` `temporal_chain_v2` treatment.
The result must remain fail-closed and auditable, preserve delayed-recall
behavior, and make it impossible to accidentally produce a legacy or mixed
world-update campaign.

This is orchestration only. TASK-013 Scenario semantics and metrics are frozen.
Do not run a campaign in this task.

## Binding boundaries

- Read `AGENTS.md`, `HANDOFF.md`, `A-APPROVAL-013.md`, `QA-013.md`, README,
  protocol, current diff, `cli.py`, `run_controlled_campaign.py`, fairness,
  registry, Controlled helpers and related tests before editing.
- Do not modify protocol, planner, runner, fairness implementation, memory
  backends, Scenario implementations, registry, TypeScript, results, `.env`,
  services or git state.
- No Docker, live bot/Minecraft, live LLM, Letta, Mem0 service or campaign.
  Tests must be hermetic and use fakes.
- Never branch on memory-backend name in planner/runner/scenario code. The
  campaign runner may validate its explicitly approved backend set as an
  orchestration safety gate.

Allowed production files:

- `benchmark/minemembench/cli.py`;
- `scripts/run_controlled_campaign.py`.

Allowed tests/docs:

- `benchmark/tests/test_controlled_mode.py` and/or one focused new Python test;
- `docs/experiment_standard.md` (in-place status/usage update only);
- `docs/agents/reviews/B-COMPLETION-014.md`.

Stop and report if another production file appears necessary.

## 1. One central Controlled scenario policy

The CLI and campaign runner must use one shared validation function/policy,
implemented in one of the two allowed production files (the runner may import
it; do not duplicate two allowlists).

Approved combinations:

- `delayed_recall` + `recall_semantics_version=legacy` (historical
  reproducibility/diagnostics);
- `delayed_recall` + `recall_semantics_version=entity_key_v2`;
- `world_update` + `update_semantics_version=temporal_chain_v2` only.

All other registered scenarios and version values are rejected. Controlled
`world_update` with the version omitted is the legacy default and must be
rejected before contacting the bot or writing results. `--runs` remains
exactly 1 for every direct Controlled CLI call.

The Scenario's own `apply_params` validation remains authoritative for names,
types and ranges. The policy consumes the Scenario's **full effective params**,
not raw user input. TASK-013's Scenario-level fail-closed gate remains defense
in depth.

## 2. Campaign interface and backward compatibility

Add `--scenario` to `scripts/run_controlled_campaign.py` with choices limited
to the two approved scenario names and default `delayed_recall`. Therefore all
existing delayed-recall command lines that omit `--scenario` retain their
behavior, schedule order, log naming and event identity. Never edit historical
manifests/results.

For each input cell, retain both:

- the exact requested parameter dict (for command reconstruction/audit);
- the full effective parameter dict after Scenario validation/defaults.

The CLI subprocess command should carry the requested overrides so old
delayed-recall commands remain semantically identical. Manifest cells and run
entries must additionally carry the full effective params. Result JSON and
fairness already record effective params and must match them exactly.

Controlled event identity remains:

- full effective params for `world_update` v2 and delayed-recall v2;
- the frozen two-parameter legacy delayed-recall namespace already implemented
  in the Scenario, to preserve historical ids.

Add a manifest schema/version marker and top-level selected semantics version.
Every run entry must record the scenario, cell, seed, backend, requested params,
effective params, command, expected mock mode, canonical fixture identity,
logs, result files and status.

## 3. Cell/campaign preflight — fail before the first write

Parse and validate the complete campaign before creating a manifest, store or
log:

- each `--cell` is a JSON object with exactly a non-empty safe `name` and a
  `params` object; reject malformed JSON, extra/missing keys and duplicate
  names cleanly with exit code 2 (no traceback);
- cell names must be safe single path components (letters/digits plus
  `._-`, bounded length; no separators or traversal);
- every cell validates through the selected Scenario;
- all cells share one semantics version; delayed legacy and v2 may not be
  mixed in one output directory;
- world-update cells must explicitly request
  `update_semantics_version=temporal_chain_v2`; missing/legacy/mixed values
  fail closed;
- seeds are a non-empty unique integer list;
- backends are a non-empty unique subset of `none,vector,mem0,letta`;
- the output path is absent or an empty directory, as today.

Any preflight failure leaves the requested output path unchanged and starts no
process. Existing fail-closed non-empty-directory behavior remains.

## 4. Schedule and manifest invariants

Parameterize `build_schedule` by scenario (default delayed-recall for direct
backward compatibility). Preserve seed-major ordering, Latin-square backend
rotation and alternating cell order exactly. Commands must use `--runs 1`,
the selected scenario, the selected seed/backend, Controlled mode and the
fresh bot URL placeholder.

Before execution, persist the complete all-pending schedule with stable
requested/effective params and pre-registered stdout/stderr paths. A fresh
mock adapter is still spawned and stopped for every run; campaign-local
Vector/Mem0 stores remain unchanged.

The canonical fixture identity is independent of scenario parameters and must
remain exactly `CONTROLLED_FIXTURE_IDENTITY`; record it alongside the scenario
and params, never derive a new fixture per cell.

## 5. Per-run evidence must fail closed

After a subprocess returns, link every newly produced `scenario_*.json` file,
even for a failed run. A return code of zero counts as `ok` only when exactly
one new result file exists and its JSON agrees with the pre-registered entry:

- scenario, seed, memory backend and `campaign_mode=controlled`;
- full effective `params`;
- fairness exists, `valid=true`, and matches scenario, effective params,
  run seed, Controlled mode and canonical fixture identity.

Zero or multiple result files, invalid JSON, any field mismatch or invalid
fairness marks the run `failed`, records a useful error in the manifest, stops
the campaign immediately and leaves all evidence/logs untouched. Never retry,
replace, delete or silently exclude a run.

## 6. Mandatory falsification tests

### Q1 — CLI policy

- delayed legacy and entity-key v2 pass the policy;
- world temporal-chain v2 passes;
- world missing version/legacy, unsupported scenarios/versions and
  `--runs != 1` fail before BotClient/LLM/backend construction.

### Q2 — normalization/preflight

- an old delayed cell omitted version: requested params stay byte-for-byte the
  same, effective params include defaults/`legacy`, and the generated command
  retains only the requested overrides;
- a world v2 cell records requested + complete effective params;
- malformed/extra-key/unsafe/duplicate cells, invalid params, mixed delayed
  semantics, missing/legacy world version, duplicate/empty seeds/backends and
  unsupported backends all exit 2 without writing the output path or spawning.

### Q3 — scheduling

- both scenarios preserve the existing seed-major/counterbalanced/alternating
  schedule;
- every command/run entry names the selected scenario and exact cell identity;
- default delayed-recall schedule behavior remains compatible.

### Q4 — result validation/lifecycle

Using fakes only, prove: full pending manifest precedes execution; fresh
process per run; valid single result advances; stdout/stderr and result links
persist; first failure stops. Independently falsify zero results, two results,
invalid JSON, each identity/params mismatch and `fairness.valid=false`.

### Q5 — hermetic CLI world-update integration

With the canonical fake bridge, fake LLM and recording/no-memory backend, run
one direct Controlled world-update v2 CLI path. Verify result mode/scenario,
full params, fairness/fixture/seed, deterministic injected events, typed
ground truth and causal evidence-source metric. No network.

### Q6 — regressions/scope

Existing delayed-recall Controlled tests and TASK-013 tests remain green;
no Scenario/planner/runner/fairness/backend/TS/protocol/result diff. Unit tests
must not depend on gitignored results.

## 7. Documentation and completion report

Update `docs/experiment_standard.md` only to state that the approved
Controlled scenario/version combinations are CLI/campaign-capable after this task but
that **no world-update campaign is authorized yet**. Include PowerShell-valid
example syntax; do not claim results.

Write `docs/agents/reviews/B-COMPLETION-014.md` with exact files, Q1–Q6 mapping,
test commands/counts, deviations and explicit confirmation that no process,
campaign, result or git action occurred.

## Verification

Run focused Controlled/TASK-013 tests, then:

```powershell
.venv\Scripts\python -m pytest -q
```

TypeScript is N/A unless B unexpectedly touches `minecraft/` (not authorized).
Do not stage, commit or push.
