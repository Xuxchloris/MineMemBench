# A-REVIEW-014 — TASK-014 technical/research review

Date: 2026-08-08  
Reviewer: Agent A  
Inputs: `TASK-014.md`, `B-COMPLETION-014.md`, `QA-014.md`, current code,
tests and independent A probes  
Decision: **REJECT pending two bounded hardening repairs; no campaign
authorized**

## Executive decision

The central scenario/version policy, requested/effective parameter split,
world-update v2 CLI path, result/fairness validation and delayed-recall
compatibility are sound. B's 108 focused / 302 full test claims reproduced
under C, and C independently falsified every result and fairness field.

A does not accept C's Q4 identity conclusion. C defined a run identity as
`(seed, backend, cell-name)`, but the Controlled event identity and research
treatment are defined by `(scenario, effective params, seed, backend)`; a cell
name is only a label. The current preflight accepts two differently named
cells with identical effective params, allowing semantic duplicate
observations despite unique seeds/backends/names. That is a data-integrity
gate, not a cosmetic issue.

C also disclosed an independent QA-process incident: module-level monkeypatch
of `_spawn_bot`/`_invoke_run` did not replace `run_campaign`'s definition-time
default callables, so a supposed hermetic probe executed about seven real
temporary Controlled CLI calls, including real LLM calls and two Letta-backed
runs. The temporary output was outside the repository, no orphaned process or
`results/`/git mutation remains, and completed Letta runs call the existing
episode reset/delete path. Provider billing/logs and transient service
activity cannot be undone. This was not caused by B's research logic, but the
default-binding trap should be hardened before another verifier touches the
runner.

## Findings

### High — semantic duplicate cells bypass unique-observation preflight

- Location: `scripts/run_controlled_campaign.py`, `prepare_campaign`, after
  effective params are computed (around lines 115–176).
- Reproduction: submit two cells named `alpha` and `beta` whose delayed-recall
  requested dictionaries are equal (or one omits a default while the other
  explicitly supplies it). Preflight returns success. For the same
  seed/backend, both entries have identical effective params and therefore
  identical Controlled event-identity inputs; only the arbitrary label and
  fresh episode id differ.
- Expected: one campaign contains one cell per distinct effective treatment.
  Unique names must not permit duplicate semantic cells.
- Actual: duplicates are scheduled and could be counted as separate
  observations/cells.
- Experimental conclusion impact: **Yes, for future campaigns**. If pooled or
  reported as independent cells/runs, duplicated evidence can bias rates and
  sample counts. No existing result is affected because TASK-014 has not been
  released for a campaign.
- Minimum repair: compute a stable canonical signature from the selected
  scenario plus full effective params (`json.dumps(..., sort_keys=True,` with
  an unambiguous compact encoding is sufficient) and reject a second cell
  with the same signature before any write/spawn. The error must name both
  labels. Add tests for identical raw params and omitted-vs-explicit defaults,
  plus a schedule-level assertion that accepted tuples
  `(scenario, canonical effective params, seed, backend)` are unique.

### Medium — definition-time dependency defaults make hermetic main probes unsafe

- Location: `scripts/run_controlled_campaign.py`, `run_campaign` callable
  defaults (around lines 425–432).
- Cause: `_spawn_bot`, `_await_mock_health` and `_invoke_run` are captured when
  the function is defined. Monkeypatching the module attributes later does not
  affect `campaign.main()` → `run_campaign()` unless the caller replaces
  `run_campaign` itself or passes every dependency explicitly.
- Experimental conclusion impact: **No**. Production execution uses the same
  real functions either way. Operational impact is real: C's attempted fake
  probe contacted the LLM/Letta stack.
- Minimum repair: make the three dependency parameters optional (`None`) and
  resolve them to the current module functions inside `run_campaign`, or an
  equivalent late-bound design. Add a hermetic test that monkeypatches the
  module helper attributes, calls the normal `main` path with one valid temp
  cell, proves only fakes ran and no external process/network function was
  reachable. Preserve explicit dependency injection used by existing tests.

### Low — overly broad preflight exception catch

- Location: `scripts/run_controlled_campaign.py`, Scenario normalization
  around lines 142–146.
- Cause: `except Exception` can turn an implementation defect into a normal
  user-input rejection.
- Experimental conclusion impact: **No**.
- Minimum repair: while touching the function, catch the known registry/
  scenario/value exceptions only. If exact imports would require scope
  expansion, leave this Low item documented rather than expanding production
  scope.

## C QA incident disposition

- No generated file appeared under repository `results/`; HEAD and staging
  stayed unchanged; no new Node/Python process remains.
- The temporary path reported by C is no longer present when A checked.
- Letta's adapter `reset()` deletes the episode agent. Completed accidental
  runs passed the campaign result/fairness gate, so agent cleanup was invoked;
  no claim is made about provider billing or server/API logs.
- Do not run a cleanup campaign or delete broad service data. No destructive
  action is authorized.

## Repair authorization for B

B may change only:

- `scripts/run_controlled_campaign.py`;
- `benchmark/tests/test_controlled_mode.py`;
- append a repair section to `docs/agents/reviews/B-COMPLETION-014.md`.

Do not change CLI policy, scenarios, results, docs/protocol, services or git.
Run focused Controlled/TASK-013 tests and full pytest. No live process,
campaign or network call. After B reports, C must reverify using explicit
dependency injection or a monkeypatched `run_campaign` sentinel; C must not
repeat the live probe.
