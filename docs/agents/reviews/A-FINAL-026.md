# A-FINAL-026 — M15.1 final research and implementation review

Date: 2026-08-09
Reviewer: Agent A
Independent verifier: Agent C
Verdict: **PASS — ready for separately authorized clean freeze; formal work is not authorized**

## Reviewed identity

```text
immutable_base_commit=9fdced8fa9967a6df7b856b035485b41e84c06dc
current_source_tree_fingerprint=86c625f9a130be3b5a81c3ed7ca48db9eb128493eb703ac98ca905a2bb9fd3f6
source_file_count=122
working_tree=dirty
```

The immutable TASK-025 commit remains unchanged. No Git add/commit/push/amend
was performed during TASK-026. `docs/protocol.md` is unchanged.

## Verification

```text
Agent A Python full suite: 429 passed
Agent C Python full suite: 429 passed
Agent C focused terminal/replay/scenario suite: 52 passed
TypeScript: 40 passed
TypeScript build: PASS
Dashboard JavaScript syntax: PASS
git diff --check: PASS (line-ending notices only)
strict Docker Letta add/retrieve/update/reset isolation: PASS
real heterogeneous Node mock fixture + identity gate: PASS
```

Agent C's final code QA and accepted replacement-campaign data QA are PASS.
The final 24-run v4 diagnostic is complete, unretried, fairness/reset-valid and
independently recomputed.

## Research validity decision

The independent variable remains only `MemoryBackend`. Planner model,
temperature, prompt/schema hashes, tools, scenario params, fixture, source
identity and same-seed ExperienceEvent/source ActionResult evidence are fixed
and audited. Scenario/runner/planner code never branches on backend name.

`long_lived_memory / lifetime_v1` creates the early route fact from a real
fixture observation, keeps one long-term episode across semantic sessions,
starts every planner call with a fresh working transcript, and objectively
scores locate→collect→return→deliver. `failure_learning_multi /
observed_precondition_applicability_v4` presents one applicable and 1–2
heterogeneous inapplicable real failed ActionResults. Opaque non-ordinal
families prevent common-sense or position shortcuts. Required-item and
applicability ground truth remain evaluator-only.

The terminal predicate is a post-action evaluator over recorded RunStep
evidence. It stops a new scenario only after objective completion and never
enters prompt, query, event or action selection. It therefore removes
post-completion contamination without changing the control variable.

Dashboard is a read-only evidence consumer. Producer imports are one-way;
GET/SSE indexing, replay and Compare do not call runner, scenario, planner or
memory. Partial/invalid/failed evidence is fail-closed, and exact same-seed
Compare is campaign-scoped.

## Findings by severity

### Critical

None open.

### High — resolved before acceptance

| Location | Finding / impact on conclusions | Minimal resolution |
|---|---|---|
| `scenarios/failure_learning.py::compute_transfer_behavior_metrics` | Correct equip could be overwritten before the first attack yet be counted as strict success; this directly polluted the primary endpoint. | Track actual ordered/current equipment at first attack; add overwrite regression. |
| `scenarios/failure_learning_multi.py`, `minecraft/src/mock.ts` | Semantic and ordinal family/resource mappings could allow NoMemory shortcuts, contaminating the memory treatment. | Opaque alpha/beta/gamma labels plus non-ordinal alpha→iron, beta→string, gamma→gold mapping and tests. |
| `cli.py::_assert_controlled_fixture` | Heterogeneous state existed but its identity return map was missing, blocking a real Controlled campaign. | Register the selector→identity pair and exercise the real gate. |
| `dashboard/index.py`, `dashboard/server.py` | Global treatment lookup mixed campaigns; failed/fairness-invalid results could enter aggregates; concurrent refresh could transiently return 404. These could corrupt comparisons and UI research summaries. | Campaign-scope anchor Compare, valid-producer-only aggregates, atomic `RLock` refresh/cache and regressions. |
| `core/runner.py`, new M15.1 scenarios | Successful runs continued to `max_steps`, adding meaningless waits/attacks and contaminating behavior horizon, tokens and latency. | Optional backend-neutral terminal RunStep predicate; stop lifetime at delivery and v4 at completed target attack; supersede the first v4 campaign and rerun it. |

### Medium — disclosed, not blockers for freeze

1. **Calibration ceiling.** In
   `docs/difficulty-calibration.md`, all active v4 backends retrieve the
   relevant failure at rank 1 and also retrieve every offered irrelevant
   failure. Mem0/Letta are 3/3 in both cells; only Vector's two-failure cell is
   transitional. This limits the formal design but does not invalidate the
   implemented construct. Minimal next step: do not call this a Failure Point;
   design a separately preregistered harder applicability ladder if needed.
2. **Cost boundary.** `ScenarioResult.metrics` records planner tokens and
   operation latencies but not normalized backend-internal embedding/LLM
   costs. This prevents cost-efficiency conclusions. Minimal next step:
   preregister a backend-neutral accounting contract before any cost claim.
3. **Historical lifetime identity.** Lifetime calibration predates the
   terminal predicate. Its primary/retrieval evidence occurs before delivery
   and remains a construct diagnostic, but post-delivery token/horizon values
   are superseded. Minimal next step: rerun the selected lifetime formal cells
   only after a clean freeze and preregistration.

### Low

The in-app visual browser-control runtime failed before page commands because
of a local missing-path error. HTTP/static/JS, real API data, SSE and concurrent
reads are verified, but visual-browser PASS is N/A. Minimal fix is external to
the repo: repair the Codex browser runtime, then perform a manual visual pass.
This does not affect producer data or replay truthfulness.

## Calibration conclusion

Accepted v4 evidence:
`results/calibration_task026_failure_applicability_v4_terminal_v1_20260809/`.
The earlier v4 directory is explicitly superseded and must not be pooled.

| Failures | None | Vector | Mem0 | Letta |
|---:|---:|---:|---:|---:|
| 2 | 0/3 | 2/3 | 3/3 | 3/3 |
| 3 | 0/3 | 3/3 | 3/3 | 3/3 |

The representative causal fork is Vector, failures=2, seed 42: relevant
failure rank 1 (**retrieval succeeds**), planner equips the wrong item and
repeats the environment failure (**planning fails**), then correctly recovers
while strict primary success remains false. No adapter/environment-root failure
occurred. With `n=3`, this is mechanism evidence only, not a ranking.

## Final gate decision

TASK-026 implementation, tests, C QA, bounded calibration and A review are
complete. The working tree is intentionally dirty, so the source is not yet a
formal candidate. The next allowed action is only a separately authorized Git
freeze: audit exact files, create a clean commit, recapture the fingerprint and
run `scripts/verify_source_freeze.py --require-clean` against that new SHA.

Until that succeeds, do not preregister or run a formal M15.1 campaign.
