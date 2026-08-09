# A-REVIEW-013 — TASK-013 final technical/research review

Date: 2026-08-08  
Reviewer: Agent A  
Inputs: `TASK-013.md`, `B-COMPLETION-013.md`, `QA-013.md`, current code,
tests, diff, and the 24 local round-4/round-5 result files  
Decision: **REJECT pending two minimal repairs; no campaign authorized**

## Executive decision

The temporal-chain v2 treatment is methodologically sound in the reviewed
scope. The offered event stream is backend-independent in Controlled Mode,
the prompt receives only neutral semantic facts and timestamps, ground truth
is out of band, and the headline retrieval metrics are derived from the exact
step-0 causal snapshot rather than the later diagnostic probe. Legacy native
world-update behavior remains compatible. These properties are independently
supported by C's 90 focused / 279 full Python tests, 31 TypeScript tests, and
manual validation of all 24 historical result files.

TASK-013 is nevertheless not approvable as written because two binding
acceptance criteria fail. Neither finding invalidates prior results or the
temporal-chain design, but both must be repaired before CLI/campaign work.

## Findings

### High — portable pytest suite depends unconditionally on gitignored data

- Location: `benchmark/tests/test_world_update_v2.py`,
  `test_p6_round4_and_round5_result_files_still_load` (around line 506).
- Cause: the test always asserts that both local result directories contain
  exactly 12 scenario JSON files. `results/` is gitignored, so a clean
  checkout has zero files and fails the normal unit suite. This contradicts
  the explicit TASK-013 clarification separating portable unit tests from
  the strict current-workspace evidence gate.
- Experimental conclusion impact: **No**. C independently loaded all 12+12
  local files successfully; the defect is CI/reviewer reproducibility.
- Minimum repair: if both evidence sets are absent, explicitly
  `pytest.skip`; if either set is partially present, retain the exact 12/12
  assertions and fail. Keep a separate strict current-workspace command in
  the completion/reverification report that requires and validates all 24
  files. Do not copy or fabricate result fixtures.

### Medium — temporal-chain entity key is not type-enforced

- Location: `benchmark/minemembench/scenarios/base.py`,
  `TemporalChainGroundTruth.entity_key` (around line 117).
- Cause: `entity_key: str = "supply_cache"` accepts any string, despite the
  frozen ground-truth member requiring exactly `supply_cache`.
- Experimental conclusion impact: **No**. The production scenario currently
  writes the correct value and metric derivation uses event ids, but invalid
  result JSON can pass validation.
- Minimum repair: use
  `entity_key: Literal["supply_cache"] = "supply_cache"` and add a negative
  validation test proving another value raises Pydantic `ValidationError`.

### Low — native v2 wall-clock timestamps are not formally collision-proof

- Location: `benchmark/minemembench/scenarios/world_update.py`,
  `_next_event_identity` native branch.
- Cause: consecutive `datetime.now(UTC)` calls can theoretically collide on
  a low-resolution clock. Controlled research runs use the deterministic
  logical clock and are strictly monotone, and TASK-013 explicitly permits
  wall time for native v2.
- Experimental conclusion impact: **No** for Controlled research runs.
- Minimum repair: none in this repair cycle. Track when native-v2 hardening is
  scheduled; do not expand TASK-013 scope.

## Repair authorization for B

B is authorized to change only:

- `benchmark/minemembench/scenarios/base.py`;
- `benchmark/tests/test_world_update_v2.py`;
- `docs/agents/reviews/B-COMPLETION-013.md` (append repair evidence).

Required verification:

1. focused TASK-013 suite;
2. full `.venv/Scripts/python -m pytest -q` in the current workspace;
3. a portable absence-path test that does not move/delete local results;
4. a strict local command validating all 24 historical JSON files;
5. C independent re-verification.

Do not touch production semantics beyond the Literal type, run live services
or a campaign, modify results, or perform any git operation. World-update
Controlled CLI/campaign generalization remains unauthorized until A issues a
separate approval.
