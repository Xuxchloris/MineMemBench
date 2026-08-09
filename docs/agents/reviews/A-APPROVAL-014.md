# A-APPROVAL-014 — Controlled CLI/campaign generalization

Date: 2026-08-08  
Reviewer: Agent A  
Decision: **APPROVED for orchestration; execution requires a separate task**

## Basis

- B implemented the single-source Controlled scenario/version policy,
  requested/effective cell normalization, world-update v2 scheduling,
  manifest v2 and per-run result/fairness validation.
- C reproduced the original 108 focused / 302 full suite and independently
  validated every result/fairness mismatch path, but A rejected C's initial
  identity definition.
- A-REVIEW-014 required semantic-duplicate-cell rejection and late-bound
  execution dependencies. B repaired both and narrowed preflight exceptions.
- C's safety-restricted repair re-verification reproduced **115 focused** and
  **309 full Python tests**, with no live/process/network action.

## Accepted properties

- Approved Controlled combinations are centrally defined: delayed-recall
  legacy/entity-key v2 and world-update temporal-chain v2 only.
- World-update missing/legacy version fails before bot, LLM or backend
  construction; direct Controlled calls remain one run per fresh fixture.
- Old delayed-recall commands retain requested overrides, ordering, log names
  and frozen legacy identity while manifests additionally record effective
  params.
- Campaign preflight validates all cells/seeds/backends before the first write
  or spawn; semantic duplicate cells are rejected by canonical effective
  treatment identity, regardless of label or omitted/explicit defaults.
- Schedules are seed-major, counterbalanced and unique over
  `(scenario, effective params, seed, backend)`.
- A zero return code is insufficient: exactly one new result JSON must match
  scenario/seed/backend/mode/effective params and a valid matching fairness
  record. Invalid/failed evidence remains linked and stops the campaign.
- Execution dependencies are late-bound, so hermetic module monkeypatches on
  the normal `main` path cannot silently fall through to real process/network
  functions.

## QA incident disclosure

Before the late-binding repair, C accidentally executed about seven temporary
Controlled calls while attempting a fake probe, including real LLM calls and
two Letta-backed runs. No repository `results/`, git state or persistent
process was changed; completed Letta episodes use the existing delete/reset
path. Provider billing/logs and transient service activity may remain. This
incident is excluded from research evidence and was not repeated.

## Boundary

This approval authorizes the orchestration code only. It does not authorize a
formal sample, framework ranking or Failure Point. A separate task must name
one fresh output path, exact scenario/cell/seeds/backends and stop conditions
before C may execute a world-update diagnostic campaign.
