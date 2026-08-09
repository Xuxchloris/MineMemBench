# A-IMPLEMENTATION-024 — Source provenance gate completion

Date: 2026-08-09 00:28 Asia/Shanghai
Owner: Agent A (technical/research lead; implementation takeover while Agent B is unavailable)
Independent verifier: Agent C
Status: **implementation complete and independently verified; no campaign authorized**

## Outcome

TASK-024 closes the identified producer-source provenance gap without changing
planner behavior, scenario semantics, the memory plugin boundary, or the
Python↔TypeScript wire contract. New Controlled campaigns pre-register the
producer source tree before run 1, every result carries a compact matching
record, and a mismatch stops the campaign while preserving partial evidence.

The gate deliberately does not turn a dirty tree into formal evidence. The
current worktree is correctly recorded as dirty, and
`--require-clean-source` rejects it before creating an output directory.

## Implemented scope

- `core/provenance.py` deterministically hashes 104 explicitly allowlisted
  runtime, adapter, test, dependency, compose, configuration-schema,
  wire-contract and producer-script files using SHA-256.
- `.env`, results, stores, caches, build output, dependencies and runtime/world
  data are excluded. Missing anchors, forbidden paths, symlinks, escaping
  aliases and Windows junctions into forbidden trees fail closed.
- Read-only git provenance records availability, commit, dirty state and a
  normalized status fingerprint; unavailable state is explicit.
- `FairnessRecord` gained optional backward-compatible provenance fields, and
  all new CLI runs populate them.
- New Controlled manifests use `controlled-campaign/v4`, contain the full
  provenance record before run 1 and validate every result against it.
- `--require-clean-source` rejects dirty or git-unavailable sources before any
  campaign output is created.
- `docs/preregistration_template.md`, the current development plan and public
  M15 documentation now state the formal evidence gates and accepted
  diagnostic boundaries.

Current producer-source fingerprint after the accepted repair:
`50e9a9961eee9337883f3a2d19d19e81cb06a5714c04bd9d7b3f640a0d9448a2`
(104 files). This identifies the current source content; it is not a commit.

## Main files created/modified

- `benchmark/minemembench/core/provenance.py` (new)
- `benchmark/minemembench/core/fairness.py`
- `benchmark/minemembench/cli.py`
- `scripts/run_controlled_campaign.py` (new)
- `benchmark/tests/test_provenance.py` (new)
- `benchmark/tests/test_controlled_mode.py`
- `benchmark/tests/test_scenario_params.py`
- `docs/preregistration_template.md` (new)
- `docs/development_plan.md` (new current plan)
- `README.md`
- `docs/experiment_standard.md`
- `docs/stress_design.md`

## Verification

Agent A:

```text
.venv\Scripts\python -m pytest -q
369 passed in 105.28s

.venv\Scripts\python scripts\verify_letta_live.py --require-live
PASS: exact add/retrieve, update, reset and fresh-scope isolation

cd minecraft; npm test
34 passed

cd minecraft; npm run build
tsc success

git diff --check
exit 0 (CRLF conversion warnings only)

git diff -- docs/protocol.md
empty
```

Agent C independently reproduced the repaired tree:

```text
benchmark/tests/test_provenance.py: 7 passed
focused TASK-024 suites: 109 passed
full Python suite: 369 passed in 102.87s
real Windows junction probe: rejected with ValueError
```

The complete independent evidence is in
`docs/agents/qa/QA-024-PROVENANCE.md`.

## Deviations and remaining gate

No requirement deviation remains. C found two Low issues (a Windows junction
route into a forbidden in-repository tree and cosmetic trailing whitespace);
A applied the minimal fixes and C independently verified both as resolved.

No campaign was run under TASK-024. Formal execution still requires an
external review owner to freeze this source in a clean reviewed commit, after
which A can bind a preregistration to that commit and exact fingerprint.
