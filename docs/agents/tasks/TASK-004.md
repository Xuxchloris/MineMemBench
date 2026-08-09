# TASK-004 — Controlled delayed-recall campaign harness

Issued by: Agent A
Assignee: Agent B
Status: implementation; C is blocked until A review

Read `docs/agents/reviews/A-RESEARCH-REVIEW-004.md`. Implement the smallest
Controlled Mode that makes the delayed-recall comparison auditable. Do not
modify `docs/protocol.md` and do not redesign other scenarios.

## Required behavior

1. Add an explicit campaign mode identity to raw results/fairness. Native and
   Controlled outputs must not be mixable silently.
2. Controlled delayed-recall uses a **fresh mock bot adapter process for every
   individual run**, so the initial fixture is canonical `(0,64,0)` with fixed
   mock inventory/weather/time. Fail closed if health reports any mode other
   than `mock`.
3. Remove the volatile observation `timestamp` from the WorldState JSON sent to
   the planner (the raw state remains logged). This normalization is identical
   for every backend and documented; do not hand-code actions.
4. Store the exact WorldState used for every planner decision in `RunStep`.
5. In Controlled Mode only, delayed-recall generates deterministic event ids
   and logical timestamps for a given `(seed, effective params, phase,
   ordinal)`. Actor/type/context/outcome and event order must be identical
   across backends; only the isolation `episode_id` may differ.
6. Retain the complete sequence of events offered to `memory.add/update` in the
   ScenarioResult, including NoMemory runs, so C can compare actual campaign
   inputs rather than a separate harness.
7. Add a campaign runner under `scripts/` that owns the fresh mock process,
   runs exactly the requested cells one run at a time, and writes a manifest
   before execution. Use a seed-major, precomputed counterbalanced order across
   `none/vector/mem0/letta`; record order, commands, health mode, seed, params,
   and output directory. A partial/error run must remain auditable and the
   runner must stop rather than replace it silently.
8. Unit tests (no network) must prove: fresh-process lifecycle through fakes;
   fail-closed native health; counterbalanced schedule; deterministic semantic
   events across backend scopes; exact normalized planner WorldState equality;
   NoMemory input events retained; RunStep raw state retained.

## Scope and acceptance

- Do not touch native `results/stress_round1/`.
- Do not run the 24-cell campaign; C owns it after A review.
- A small fake/mock process smoke may use a temporary results directory only.
- Full Python and TypeScript suites green; no backend-name conditional in
  planner/scenario/runner behavior; no git operations.
- Write `docs/agents/reviews/B-COMPLETION-004.md` and stop.
