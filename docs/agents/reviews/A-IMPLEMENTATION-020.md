# A-IMPLEMENTATION-020 — TASK-020 repair completion for independent QA

Date: 2026-08-08 22:21 Asia/Shanghai  
Owner: Agent A (technical/research lead; implementation takeover after Agent B quota exhaustion)  
Verifier next: Agent C  
Status: **implementation complete; no campaign authorized**

## Outcome

Agent C's WIP audit (`docs/agents/qa/QA-020-WIP.md`) correctly found that
the partial implementation could not run in Controlled Mode: the CLI and
campaign still required the canonical fixture, the campaign never set
`BOT_MOCK_FIXTURE`, and no committed v2 falsification tests existed. Agent A
also found one unreported High issue: attack-first failure followed by
equip/recovery was incorrectly counted as primary `transfer_success`.

All identified implementation blockers are repaired. This document is an
implementation handoff, not final approval; Agent C must independently rerun
the checks before A can approve a smoke.

## Implemented scope

- `failure_learning/observed_precondition_v2` preserves the exact real source
  `ActionResult`, injects exactly one derived `TASK_FAILED`, uses typed
  evaluation-only ground truth, causal step-0 retrieval evidence, and ordered
  RunStep behavior metrics.
- Primary transfer success now requires successful preparation before the
  first transfer attack. Attack-first eventual recovery remains logged but is
  not primary success.
- The versioned `warded_hostiles_v1` fixture is selected explicitly from the
  scenario semantics, never the backend. Its selector and identity are stored
  in the campaign schedule/manifest and `FairnessRecord`.
- The CLI verifies the complete selected visible WorldState before any
  Controlled run. Canonical fixtures remain the default for prior scenarios.
- The campaign sets `BOT_MOCK_FIXTURE=warded_hostiles_v1`, requires an explicit
  `failure_semantics_version=observed_precondition_v2`, counterbalances as
  before, and validates fixture selector/identity in result fairness.
- Failure-learning campaigns separately fingerprint the injected event stream
  and normalized source ActionResult for the same seed/treatment across
  backends. Only isolation/action/time identifiers are removed; status, error,
  result, entities, and equipped state remain part of the audit.
- Manifest schema is bumped to `controlled-campaign/v3` for the added fixture
  and evidence fields.
- The canonical TypeScript mock path is unchanged; the warded fixture has
  committed failed -> equip -> completed tests for both hostile entities.
- No backend-name branch was added to planner/scenario/runner code.
- `docs/protocol.md` is unchanged.

## Files created/modified for TASK-020

- `benchmark/minemembench/scenarios/failure_learning.py`
- `benchmark/minemembench/scenarios/base.py`
- `benchmark/minemembench/core/runner.py`
- `benchmark/minemembench/cli.py`
- `benchmark/minemembench/core/fairness.py`
- `scripts/run_controlled_campaign.py`
- `minecraft/src/config.ts`
- `minecraft/src/index.ts`
- `minecraft/src/mock.ts`
- `minecraft/test/mock.test.ts`
- `benchmark/tests/test_failure_learning_v2.py` (new)
- `benchmark/tests/test_controlled_mode.py`
- `docs/agents/HANDOFF.md`
- `docs/experiment_standard.md`
- `docs/agents/reviews/A-IMPLEMENTATION-020.md` (new)

## Verification run by A

All checks were hermetic/offline. No real LLM, Letta, Minecraft server,
campaign, network, `.env`, service mutation, or git mutation was used.

```text
.venv\Scripts\python -m pytest -q \
  benchmark\tests\test_failure_learning_v2.py \
  benchmark\tests\test_controlled_mode.py
80 passed in 3.61s

.venv\Scripts\python -m pytest -q
357 passed in 80.55s

cd minecraft && npm test
3 files passed; 34 tests passed

cd minecraft && npm run build
tsc success

git diff --check
exit 0

git diff --exit-code -- docs/protocol.md
exit 0
```

## Acceptance mapping

1. Legacy/native default and historical result parsing: covered.
2. Canonical fixture unchanged; warded fixture/action rule per entity: covered.
3. Controlled legacy/unknown fail before side effects: covered.
4. Opposite deterministic source/transfer entities: covered for seeds 42/43/44.
5. Exact source failure and all fail-closed anomalies: covered.
6. Event streams/source evidence equal across NoMemory/Vector/fake for seeds
   42/43/44: covered; campaign cross-backend mismatch also fails closed.
7. Transfer goal and ground-truth leakage: covered.
8. Empty/absent/rank>1/unknown-top metrics and FlipFlop diagnostic: covered.
9. Behavior sequences including attack-first recovery as primary failure:
   covered.
10. Fixture preflight/schedule/process/fairness/result integration: covered
    with fakes; no real process or network.
11. Focused/full Python and TS test/build: green.

## Remaining gate

Agent C must independently review the final diff and rerun the focused/full
test matrix. No 3-seed/4-backend campaign is authorized until A receives that
QA report and performs final research review.
