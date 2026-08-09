# QA-020-WIP — Independent WIP audit of TASK-020 (failure_learning / observed_precondition_v2)

Issued by: Agent C (independent QA & experiment agent)
Subject: Agent B's TASK-020 implementation, **WIP**
Date: 2026-08-08
Mode: hermetic / offline only (no network, no live Minecraft/Letta/LLM, no campaigns, no service start/stop, no `.env`, no git mutations)
Report file: `docs/agents/qa/QA-020-WIP.md` (only file created/modified by this audit)

## 0. Scope and process

Per instructions: read `AGENTS.md`, `docs/agents/HANDOFF.md`, `docs/agents/tasks/TASK-020.md`, and the
current working-tree diff of the TASK-020-touched files; then verify/falsify items 1–12 and run the
prescribed test suites.

### Process failure (recorded, not a product assertion)

- **`docs/agents/reviews/B-COMPLETION-020.md` does not exist.** TASK-020 §Deliverable requires it
  (exact file list, focused/full Python and TS outputs, hermeticity evidence, deviations). Its absence is
  the documented process failure that makes this a WIP audit. No product behavior is asserted from it.
- `HANDOFF.md` (line 111-115) and `docs/experiment_standard.md` (line 33) both state TASK-020 /
  `observed_precondition_v2` is implementation/QA pending and no campaign is authorized — consistent with WIP.

### Verification evidence base

| check | command / input | result |
|---|---|---|
| Focused legacy failure-learning tests | `.venv\Scripts\python -m pytest -q benchmark/tests/test_failure_learning.py` | 5 passed (0.71s) |
| Full Python suite | `.venv\Scripts\python -m pytest -q` | **332 passed** (81.94s), 0 failed |
| TypeScript tests | `npm test` (minecraft/) | **31 passed** (3 files) |
| TypeScript build | `npm run build` (minecraft/) | success (tsc) |
| Live warded-fixture behavior (throwaway script on `dist/`) | see §3 | all behavioral assertions PASS |
| CLI canonical gate vs warded state (throwaway script) | see §10 | **gate rejects the warded fixture** |
| Behavior-metric math (7 synthetic RunStep cases) | throwaway script | 7/7 PASS |
| Retrieval-metric math (4 synthetic cases) | throwaway script | all PASS |
| Historical result JSON load (round1 / round5 / noise-count10) | `ScenarioResult.model_validate` | 16 files load unchanged |
| `docs/protocol.md` | `git diff -- docs/protocol.md` + `git status` | unchanged (no diff, not dirty) |

No network was used; no campaign ran; no services were started/stopped; `.env` was not read; no git
stage/commit/push was performed.

## 1. Item-by-item PASS / FAIL / N/A

| # | Item | Verdict | Severity |
|---|---|---|---|
| 1 | legacy failure_learning default compatibility + v2 semantics/configuration | **PASS** (implementation), coverage **partial** | — |
| 2 | standard mock fixture unchanged; scenario-specific v2 fixture selector/identity | **FAIL** (identity not wired into Python gate/campaign; no TS tests) | **Critical** |
| 3 | source ActionResult failure evidence equality, stable nonempty error, entity remains | **PASS** (implementation, live-verified); **untested** in repo | High |
| 4 | exactly one TASK_FAILED event; no authored solution/requirement event | **PASS** (code analysis); **untested** | Medium |
| 5 | source/transfer entities and tasks/checkpoints distinct and deterministic | **PASS** (verified); **untested** | Medium |
| 6 | transfer goal contains no item/equip/error/answer leakage | **PASS** (string inspection); **untested** | Medium |
| 7 | raw result serialization backward compatibility | **PASS** (verified on historical JSON) | — |
| 8 | step-0 retrieval metrics and typed GT without prompt leakage | **PASS** (math verified); **untested** | Medium |
| 9 | behavior metrics incl. FlipFlop / eventual recovery | **PASS** (function math, 7/7); **no committed tests, no FlipFlopBackend** | High |
| 10 | Controlled campaign policy/fixture/preflight/result/fairness integration | **FAIL** — v2 fixture cannot pass the CLI gate, campaign cannot select it | **Critical** |
| 11 | identical ExperienceEvent stream across backends; no backend-name branches | **PASS** (code analysis); **untested** for v2 | Medium |
| 12 | `docs/protocol.md` unchanged | **PASS** | — |

## 2. Item 1 — legacy default compatibility and v2 semantics/configuration — PASS

- `FailureLearningScenario.default_params` keeps `failure_semantics_version="legacy"` and
  `interference_count=0`; legacy path (`setup`/`experience_phase`/`interference_phase`/`test_phase`/
  `_evaluate_legacy`) is byte-for-byte the pre-task code, including the fixed five `_NOISE_FACTS`
  interference facts (`benchmark/minemembench/scenarios/failure_learning.py:567-577`).
- `apply_params` merges defaults (`scenarios/base.py:243-258`); `ScenarioResult.params` carries the full
  effective params ("All effective params are logged").
- v2 version validated in `_validate_params` (`failure_learning.py:332-340`): anything outside
  `legacy`/`observed_precondition_v2` raises `ScenarioParamError`; `interference_count` is int >= 0 via
  `_require_int_param`.
- Focused legacy tests 5/5 and full suite 332/332 green — legacy behavior preserved.
- Coverage gap: no test asserts the v2 defaults, the `observed_precondition_v2` **positive** policy
  approval, or the `interference_count` v2 default-0 semantics.

## 3. Item 2 — mock fixtures — implementation PASS, identity wiring FAIL (Critical)

**TS side (works):** live verification against `minecraft/dist/mock.js` (`warded_hostiles_v1`):
- two hostiles at distinct positions (`1001:zombie`, `1002:skeleton`), `gold_nugget` in inventory, hand
  unequipped initially;
- unarmed attack → `status=failed`, `result=null`, stable nonempty error equal to
  `WARDED_ATTACK_ERROR`, entity still alive, for **both** entities;
- after `equip_item(gold_nugget)` (completed) → attack `completed`, entity removed.
- canonical fixture is byte-for-byte unchanged: inventory slots `0:stone,1:stone_sword`, entities
  `[1001:zombie]`, `equipped.hand=null`, no skeleton (checked live).
- `BOT_MOCK_FIXTURE` is explicit process configuration and is rejected at startup if unknown
  (`minecraft/src/config.ts:43-49`); `MOCK_FIXTURES` lists a versioned name `warded_hostiles_v1`.

**FAIL points:**
- No TypeScript tests cover the warded fixture or the invalid-`BOT_MOCK_FIXTURE` startup rejection
  (`minecraft/test/` has none; only `src/config.ts`, `src/index.ts`, `src/mock.ts` were modified).
- The fixture's "versioned identity" exists only in TS. In Python there is **no** warded-fixture identity
  constant, no state fingerprint, and the fairness record can only ever carry the canonical
  `CONTROLLED_FIXTURE_IDENTITY` (`cli.py:529-534`). Item 2 ("selector/identity recorded in the campaign
  manifest/fairness path") is not satisfied.

## 4. Item 3 — real source ActionResult failure evidence — implementation PASS, untested (High)

`_experience_v2` (`failure_learning.py:450-523`) fail-closes on: hand not unequipped; status != FAILED;
empty `result.error`; source entity missing in `state_after`. It preserves the exact ActionResult in
`ScenarioResult.observed_action_results` (`scenarios/base.py:207-211`). The mock returns the identical
`WARDED_ATTACK_ERROR` constant for every seed/backend, so error stability across backends holds (live-verified).
`RunStep.action_error`/`action_result` make transfer actions auditable (`core/runner.py:50-55,176-178`).
**Coverage gap:** no hermetic fake emulates a warded fixture, so the entire `_experience_v2` success and
fail-closed paths are never exercised by any committed test.

## 5. Item 4 — exactly one TASK_FAILED, no authored solution — PASS (code analysis)

- Exactly one `ExperienceEvent(event_type=TASK_FAILED)` is added per v2 experience phase
  (`failure_learning.py:503-522`); its context is factual only (`task_family`, `entity`, `action`,
  `status`, raw `error`, `equipped_before`) and contains no "next time equip …" text, no trust score, no
  policy. The only required-item information memory sees is the environment error.
- v2 interference events are `WORLD_FACT_UPDATED` ambient notes (`failure_learning.py:544-556`), free of
  family/entity/item/error tokens.
- In Controlled Mode `EventCollector` is disabled (`cli.py:654-659`), so no additional mapped events enter
  the stream. Untested as an invariant.

## 6. Item 5 — entity/task distinctness and determinism — PASS

`source_transfer_entities` (live): seed 42 → `(zombie, skeleton)`, 43 → `(skeleton, zombie)`, 44 →
`(zombie, skeleton)`; transfer is never an identical retry. The transfer goal names only the transfer
entity, a neutral `warded hostile` cue and "secure the checkpoint". Untested in repo.

## 7. Item 6 — transfer-goal leakage — PASS (string inspection)

Goal: `"Eliminate the warded hostile {transfer_entity} to secure the checkpoint."` Contains no item name,
no equip/tool instruction, no source entity, no error text, no answer. No committed test asserts the
banned-token absence.

## 8. Item 7 — raw result serialization backward compatibility — PASS

`ScenarioResult` new fields all carry defaults (`campaign_mode`, `injected_events`,
`evaluation_ground_truth`, `observed_action_results`); `RunStep` new fields optional (`world_state`,
`retrieved_items`, `action_error`, `action_result`). Verified: 12 round-5 `entity_key_v2` + round-1 +
noise-count-10 historical result JSONs all `model_validate` unchanged.

## 9. Item 8 — step-0 retrieval metrics and typed GT — PASS (math), untested

- Headline retrieval uses `run_log.steps[0].retrieved_items` (the causal planner retrieval snapshot,
  `failure_learning.py:627-636`), never a second probe; the diagnostic probe feeds no headline.
- `compute_observed_precondition_metrics` verified: empty retrieval → recall 0 / rank·precision·top1 N/A;
  rank 3 precision 1/3 interference 1/3 unknown-top N/A; interference top1 → 0; failure top1 → 1; absent
  among known interference → recall 0, top1 0. All correct.
- GT (`ObservedPreconditionGroundTruth`) is constructed only in `_evaluate_v2` and stored on the result;
  it never enters memory/query/planner prompt/WorldState/action. Untested.

## 10. Item 9 — behavior metrics incl. FlipFlop / eventual recovery — math PASS, coverage FAIL (High)

`compute_transfer_behavior_metrics` verified against 7 synthetic RunStep sequences:
prepared-before-success; attack-then-prepare with recovery (`failure_repeated=1`,
`eventual_recovery_after_failure=1`, `transfer_success=1`); wrong item; wrong entity; failed equip;
prepared + failed attack; name-based transfer attack. 7/7 correct.
**FAIL:** none of these are committed tests, and the required `FlipFlopBackend` (falsification #8) does not
exist anywhere in `benchmark/` (only `nBackend` in `test_memory_noise_v2.py` / `test_world_update_v2.py`).

## 11. Item 10 — Controlled campaign integration — FAIL (Critical)

- **Policy gate:** `CONTROLLED_APPROVED_VERSIONS["failure_learning"] = {observed_precondition_v2}`
  (`cli.py:409-416`); `validate_controlled_policy` fails closed for default/unknown (`cli.py:420-441`);
  gate runs before bot/LLM/backend construction (`cli.py:483`). Tested only for the **rejection** of the
  legacy default (`test_controlled_mode.py:791-792`); the v2 approval path is untested.
- **CLI fixture gate rejects the v2 fixture (verified):** `_assert_controlled_fixture`
  (`cli.py:591-622`) compares the observed WorldState against the **canonical** fixture only. A
  `warded_hostiles_v1` state differs in `inventory` and `nearby_entities` → `BotBridgeError`
  ("Controlled Mode fixture is not canonical"). A v2 Controlled run therefore **cannot pass the gate**.
  A canonical bot also fails later at `setup` (`ObservedPreconditionError`, skeleton absent). v2 is
  currently unrunnable end-to-end in Controlled Mode.
- **Campaign runner never selects the failure fixture:** `_spawn_bot` sets only `BOT_MOCK=1,
  BOT_API_PORT` (`run_controlled_campaign.py:330`); no `BOT_MOCK_FIXTURE`. Schedule hardcodes
  `fixture_identity: CONTROLLED_FIXTURE_IDENTITY` (`run_controlled_campaign.py:296`), and
  `_validate_run_result` requires `fairness.fixture_identity == CONTROLLED_FIXTURE_IDENTITY`
  (`run_controlled_campaign.py:443-452`). Both contradict "uses the failure fixture for every scheduled
  backend/seed, records fixture selector/identity".
- **Preflight explicit-version requirement:** `explicit_version_required` (`run_controlled_campaign.py:
  181-184`) does not include `failure_learning`, so the requested-params version enforcement specified by
  TASK-020 ("Campaign preflight requires the version explicitly in requested params") is not implemented
  for this scenario (only indirectly via policy failure on the legacy default).
- **Fairness v2 fixture verification:** `FairnessChecker` records whatever `fixture_identity` it is passed
  (`core/fairness.py:70,128,156`) but there is no v2 visible-fixture verification and no v2 identity to
  record — "Fairness must verify the v2 visible fixture and record its versioned identity" is unmet.

## 12. Items 11 and 12

- **Item 11 — identical event stream / no backend branching — PASS (code analysis):** v2 event ids and
  logical timestamps derive deterministically from `(seed, full effective params, phase, ordinal)`
  (`controlled.py:25-45`; `failure_learning.py:314-330`); `EventRecordingBackend` records the offered
  stream for every backend including `none` (`memory/base.py:103-133`); no planner/scenario/runner code
  branches on a backend name (checked). Not exercised by any v2 test.
- **Item 12 — `docs/protocol.md` unchanged:** confirmed (no diff, not in `git status`).

## 13. Explicit list of missing acceptance criteria (TASK-020 §"Required falsification tests")

None of the TASK-020 falsification tests exist in the repo. Specifically missing:

1. legacy/native behavior + old JSON compatibility — partially covered by existing legacy tests and my
   historical-load check; no dedicated regression test.
2. standard mock fixture unchanged **and** v2 TS fixture failed→equip→completed per entity — **missing**
   (verified only ad hoc here).
3. Controlled legacy/unknown version fails before all side effects — **partial**: legacy default
   rejection tested (`test_controlled_mode.py:791-792`); unknown `failure_semantics_version` and the
   before-any-side-effect ordering for failure_learning are untested.
4. source/transfer tasks differ for every seed while sharing only the hidden precondition/task family —
   **missing**.
5. source failure event matches raw ActionResult exactly; no authored solution event/rule; fail-closed on
   unexpected success / empty error / entity state change / pre-equipped hand — **missing**.
6. complete event streams and normalized source evidence match across NoMemory/Vector/fake backends for
   seeds 42/43/44 — **missing**.
7. ground truth never enters memory/query/planner prompt/WorldState/action; transfer goal contains none of
   the banned answer fields — **missing**.
8. exact retrieval-metric math for empty / absent / rank>1 / unknown-top, plus a FlipFlopBackend whose
   diagnostic probe differs — **missing** (no FlipFlopBackend exists).
9. behavior-metric sequence cases (prepared-before success; attack-then-prepare failure repetition; wrong
   item; wrong entity; failed equip; completed preparation + failed attack; eventual recovery) — **missing**.
10. campaign fixture selection / manifest identity / preflight / result / fairness fail-closed without real
    calls — **missing**, and the underlying fixture-selection integration is broken (§11).
11. focused/full Python + TS build/tests pass with no network — **present and green** (332 + 31 + build).

Additionally: there is **no hermetic end-to-end v2 scenario test at all** (no fake bot that emulates the
warded rule), so `setup`/`_experience_v2`/`_transfer_goal`/`_evaluate_v2` are entirely unexercised by the
suite.

## 14. Required repair list for Agent A (exact; B implements, C re-verifies)

1. **Wire the v2 fixture through the Python Controlled path.** Add a versioned warded-fixture identity +
   expected-state fingerprint (mirror `canonical_fixture_state`), parameterize `_assert_controlled_fixture`
   (`cli.py:591`) by the fixture name (from `BOT_MOCK_FIXTURE`, not from a backend name), and accept both
   canonical and `warded_hostiles_v1`. Record the fixture identity in `FairnessRecord.fixture_identity`.
2. **Campaign runner:** thread a fixture field through `prepare_campaign`/`build_schedule`/`_spawn_bot`
   (`run_controlled_campaign.py:330`), set `BOT_MOCK_FIXTURE=warded_hostiles_v1` per scheduled run, store
   the per-run fixture identity in the manifest/schedule, update `_validate_run_result`
   (`run_controlled_campaign.py:443-452`) to compare the actual fixture identity, and add `failure_learning`
   to `explicit_version_required` (`run_controlled_campaign.py:181`).
3. **Python hermetic tests** (`benchmark/tests/test_failure_learning_v2.py`): a warded-fixture fake bot;
   full v2 lifecycle; all fail-closed cases of item 5; exactly-one-TASK_FAILED; banned-token goal checks;
   GT-never-in-memory; event-stream equality across NoMemory/Vector/fake for seeds 42/43/44; retrieval
   metric math + FlipFlopBackend; the seven behavior sequences; policy approval + pre-side-effect rejection
   for failure_learning; campaign preflight/manifest/result/fairness fail-closed without real calls.
4. **TypeScript tests** (`minecraft/test/mock.test.ts` or new file): canonical byte-for-byte unchanged,
   warded failed→equip→completed per entity, stable error, invalid `BOT_MOCK_FIXTURE` startup rejection.
5. **Process:** Agent B must write `docs/agents/reviews/B-COMPLETION-020.md` (TASK-020 §Deliverable).
6. **Docs:** update `docs/experiment_standard.md:33` / README to reflect implementation status once the
   above passes C re-audit.

## 15. Log / test output summary

```
focused: 5 passed in 0.71s            (test_failure_learning.py, legacy only)
full:    332 passed in 81.94s         (0 failed, 0 skipped reported)
TS:      31 passed, 3 files           (vitest)
build:   tsc success
```
Ad-hoc hermetic checks: warded fixture 20/21 assertions PASS (the single "FAIL" line was the script's
inverted label for an expected value); canonical-vs-Python gate `MATCH`; CLI-gate-vs-warded-state
`CONFIRMED: gate would reject the warded fixture`; behavior metrics 7/7; retrieval metrics all PASS;
16 historical result JSONs load unchanged.

## 16. Verdict

**Overall: FAIL (WIP).** The v2 scenario/metrics/fixture primitives are implemented and mathematically
correct, and all existing suites are green, but the task is **not done**: (a) the Controlled campaign
cannot select or accept the failure fixture (§11) — a hard blocker; (b) none of the 11 required
falsification tests exist, including any end-to-end v2 run; (c) `B-COMPLETION-020.md` is missing
(process). Exact repair list in §14.
