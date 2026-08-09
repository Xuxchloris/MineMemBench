# A-FINAL-024 — Final architectural and research review

Date: 2026-08-09 00:28 Asia/Shanghai
Reviewer: Agent A
Inputs: TASK-024, A-APPROVAL-024, QA-024-COMPLETION-AUDIT,
QA-024-PROVENANCE and the repaired current source tree
Verdict: **ACCEPTED as reproducibility infrastructure; no experiment authorized**

## Findings by severity

### Critical

None. The allowlist never reads `.env`, results, stores, caches, build output,
dependency trees or runtime/world data. The wire contract is unchanged.

### High

None in the accepted implementation. Source mutation during a v4 campaign
fails closed, old results/manifests remain readable, and a dirty tree cannot
pass `--require-clean-source`.

### Medium

None in TASK-024. Python dependency reproducibility is not a new defect in
this task, but exact installed package/image versions must still be captured
in every formal study alongside the source fingerprint.

### Low

None open. C's junction-tunnelling and trailing-whitespace findings were fixed
and independently reproduced on the repaired tree.

## Acceptance decision

All seven TASK-024 requirements pass:

1. deterministic, mutation-sensitive, forbidden-path-safe source hashing;
2. explicit read-only git provenance;
3. backward-compatible per-result fairness provenance;
4. pre-run v4 manifest provenance plus result matching and stop-on-mismatch;
5. zero-write clean-source rejection;
6. a complete formal-study preregistration template;
7. aligned current README/development/stress/CLI documentation.

Architectural invariants remain intact: MemoryBackend is the only memory
plugin boundary; no backend-name branch was added to planner/scenario/runner;
memory reaches action only through the backend-neutral planner retrieval view;
reset/isolation checks remain mandatory; Controlled and Native evidence stay
separate.

## Research boundary

The accepted source fingerprint is
`50e9a9961eee9337883f3a2d19d19e81cb06a5714c04bd9d7b3f640a0d9448a2`
over 104 files. The working tree is dirty, so this is diagnostic provenance,
not an immutable revision and not retroactive formalization of prior results.

No new framework ranking, Failure Point, effect size, Native Minecraft claim
or cost-efficiency claim is approved. The next valid transition is external:
the review owner must create a clean reviewed commit without altering the
accepted producer files. A must then verify the clean commit's fingerprint,
freeze one exact preregistration, ask C for preflight and only then authorize a
formal campaign.
