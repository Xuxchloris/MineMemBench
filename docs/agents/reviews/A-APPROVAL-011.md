# A-APPROVAL-011 — delayed-recall entity-key v2 smoke gate

Date: 2026-08-08  
Reviewer: Agent A  
Decision: **APPROVED for one diagnostic smoke only**

## Evidence

- B implemented TASK-011 and the bounded A-REVIEW-011 repair.
- C independently re-verified the repair in QA-011:
  - focused Python: 72 passed;
  - full Python: 269 passed;
  - TypeScript build + 31 tests passed;
  - Letta hermetic: 13 passed; prior same-turn live 0.16.8 verifier passed;
  - legacy Controlled identity restored to
    `ctrl-6342fe1db59ccfbe969df790`;
  - v2 identity is distinct (`ctrl-5ebaf4800733a9eba327e759`);
  - P1–P4, timestamp/order invariance, old round-4 JSON loading, isolation and
    result hygiene all passed.

No Critical, High or Medium issue remains open for the bounded v2 smoke.

## Scope of approval

This approval authorizes only TASK-012: one fresh Controlled
four-backend × three-seed `(200,20)` `entity_key_v2` diagnostic smoke.
It does not authorize a formal sample, another difficulty, retry/resume,
framework ranking, Failure Point claim, production change, or git operation.

If the smoke shows a ceiling, that is a valid finding. Do not manufacture
ambiguity or change parameters during execution; A will choose the next
pre-registered common difficulty knob after auditing the raw evidence.
