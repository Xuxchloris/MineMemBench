# A-APPROVAL-020 — Final review of TASK-020

Date: 2026-08-08 22:39 Asia/Shanghai  
Reviewer: Agent A  
Inputs: `TASK-020.md`, `A-IMPLEMENTATION-020.md`, `QA-020-WIP.md`,
`QA-020.md`, final code/test diff  
Verdict: **APPROVED for one bounded diagnostic smoke**

## Final findings

### Critical

None open. The WIP fixture/campaign blockers are resolved.

### High

None open. Attack-first eventual recovery is no longer counted as primary
transfer success, and committed tests lock that definition.

### Medium

None open for implementation acceptance. Cross-backend injected-event and
normalized source-evidence equality are separately audited by the campaign.

### Low / process

- `B-COMPLETION-020.md` is absent because B exhausted its provider quota.
  `A-IMPLEMENTATION-020.md` records the takeover and supplies the required
  implementation/test evidence. This does not affect experiment semantics.
- The repository remains a dirty, non-immutable working tree under the
  standing project constraint; smoke output is diagnostic only.

## Evidence accepted

- Agent C independently reran 80 focused and 357 full Python tests, 34
  TypeScript tests, and the TypeScript build.
- `docs/protocol.md` is unchanged and `git diff --check` passes.
- C independently falsified source evidence, one-event semantics, leakage,
  step-0 retrieval metrics, recovery behavior, fixture selection, campaign
  fairness/result checks, and fingerprint sensitivity.
- No backend-name branch exists in planner/scenario/runner.

## Authorization

Authorize exactly one fresh Controlled diagnostic campaign:

- scenario: `failure_learning`
- semantics: `observed_precondition_v2`
- `interference_count=0`
- backends: `none`, `vector`, `mem0`, `letta`
- seeds: 42, 43, 44
- total: 12 runs
- fresh output directory only

This approval does not authorize a larger matrix, ranking, formal statistics,
Failure Point, or Native Minecraft claim. Stop on first invalid run and retain
all real logs/evidence.
