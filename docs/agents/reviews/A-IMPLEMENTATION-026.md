# A-IMPLEMENTATION-026 — corrected M15.1 implementation audit

Date: 2026-08-09
Owner: Agent A (implementation takeover while Agent B is unavailable)
Independent verifier: Agent C (current corrected-tree review in progress)
Status: **implementation complete; C QA, replacement v4 calibration and A
final review PASS; Git freeze is not yet authorized/completed**

## Objective re-audit and correction

The first TASK-026 implementation and review incorrectly treated
`observed_precondition_multi_v3` as satisfying the multi-relevant-failure
objective. V3 used several real failed ActionResults, but every failure shared
the same gold-nugget prerequisite. It measured repetition, not the required
retrieve → distinguish → infer applicable → prepare → act chain. The first
Dashboard UI also omitted parts of the required Campaign matrix, run evidence,
seek/jump replay and four-way behavioral comparison.

Those earlier implementation/final-review conclusions are superseded. The raw
v3 runs remain honest but are non-poolable diagnostic history.

## Corrected implemented scope

- `long_lived_memory / lifetime_v1` remains intact: shared long-term episode,
  fresh working transcript per session, real early route observation and
  locate/collect/return/deliver strict endpoint.
- `failure_learning_multi / observed_precondition_applicability_v4` uses three
  real environment prerequisite families: alpha/iron, beta/string and
  gamma/gold. Opaque labels plus a non-ordinal family/resource permutation
  prevent common-sense and authored-position answer leakage.
  Each 2–3-source run contains exactly one source paired with the transfer
  family and 1–2 similar but inapplicable real failures. Seeds 42/43/44 rotate
  target family and relevant-source chronology.
- Every v4 source event derives one-to-one from a failed `attack_entity`
  ActionResult. Only the raw adapter error reveals the required item. No
  planner-visible event contains `required_item`, applicability or an authored
  policy answer.
- Evaluation-only typed ground truth partitions the real failure ids into one
  relevant and 1–2 irrelevant ids. Campaign validation fails closed unless
  this partition exactly covers the observed `TASK_FAILED` stream and all
  same-treatment backends receive equal normalized events/source evidence.
- Historical v3 result JSON still validates; v2 code, fixture and semantics are
  unchanged. V3 is no longer an approved runnable Controlled treatment.
- New scenarios use an optional backend-neutral terminal RunStep predicate:
  lifetime stops at recorded completed delivery and v4 stops at the completed
  target attack. The predicate is evaluation-only and never enters prompt,
  query, memory event or action selection. This closes post-completion
  wait/attack contamination found during raw replay review.
- The read-only Dashboard now provides live Campaign progress/provenance,
  cell×backend matrix, token/latency aggregates, complete run evidence,
  memory history, real WorldState/inventory, ground truth and observed source
  actions.
- Replay is deterministic and seekable (first/prev/play/next/last, slider,
  semantic jump, 0.5×/1×/2×), with MEMORY/RETRIEVE/DECIDE/ACTION/OUTCOME/
  EVALUATION timeline events and evidence-only trajectory target/entity/action/
  failure/success markers. It explicitly does not reconstruct terrain.
- Same-seed Compare displays None/Vector/Mem0/Letta retrieved top-k, first
  action/reason, preparation, repeated failure, steps, success, tokens,
  separately labeled latency and side-by-side replay timelines under the
  existing fail-closed fairness audit.
- Live SSE/index refresh is atomic under an `RLock`. This closes a real HTTP
  smoke finding where concurrent refresh briefly cleared the run-id map and
  produced transient 404 responses.
- Producer modules do not import Dashboard modules. `docs/protocol.md` remains
  unchanged; the Dashboard adds no producer dependency or mutation endpoint.

## Final verification

```text
Python full suite (A and C): 429 passed
Final C focused terminal/replay/scenario suite: 52 passed
TypeScript adapter tests: 40 passed
TypeScript build: PASS
JavaScript syntax check: PASS
git diff --check: exit 0 (line-ending notices only)
live read-only index: 15 manifests / 419 results / 0 partial / 0 invalid
live Run Detail + Replay + Compare API: PASS
replay sample: 12 frames / 74 semantic events / 27 markers / 20 offered events
strict Docker Letta verifier: PASS
terminal-corrected v4 calibration: 24/24 producer ok, C DATA QA PASS
```

The in-app browser control runtime returned an environment-owned missing-path
error before any page command could execute. Static controls, HTTP endpoints,
real result data and JavaScript syntax are verified; browser-runtime recovery
will be retried before final review and otherwise recorded as N/A with the
exact non-product blocker. This does not convert HTTP checks into a claimed
visual-browser PASS.

## Remaining gate

Implementation, C QA, bounded v4 calibration and A final review are complete.
The accepted source fingerprint is
`86c625f9a130be3b5a81c3ed7ca48db9eb128493eb703ac98ca905a2bb9fd3f6`
over 122 files on the dirty development tree. A new clean freeze still
requires explicit project-owner Git authorization. No formal campaign or
preregistration is authorized here.
