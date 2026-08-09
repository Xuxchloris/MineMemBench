# A-RESEARCH-REVIEW-004 — QA-002 research-validity review

Date: 2026-08-08
Reviewer: Agent A
Decision: **REWORK — integration PASS, controlled research conclusion FAIL**

## What the data does support

The 24 retained runs are real and internally complete. They establish that the
stress mechanism can produce candidate signals: vector's correct-fact rank
moves from 1 to 2 at `(50,5)`, and letta has one retained behavioral failure
despite correct retrieval. They do **not** yet support a causal comparison of
memory backends.

## Findings

### Critical — actual campaign did not hold the planner WorldState constant

- Location: `benchmark/minemembench/scenarios/delayed_recall.py`, `setup()`
  (around lines 227-235); raw logs in `results/stress_round1/`.
- Cause: every episode defines its spawn from the bot's current position. The
  previous run moves the same live Minecraft bot, and no fixture reset occurs
  before the next run.
- Evidence: for control seed 42, the correct targets are approximately
  `(55.5,-60,317.5)` for vector, `(50.5,-60,302.5)` for mem0, and
  `(45.5,-60,287.5)` for letta. Thus paired seeds did not produce the same
  absolute geometry or planner WorldState across backends. The none logs do not
  retain target ground truth, so their equivalence cannot even be re-derived.
- Effect on conclusions: **yes, critical**. Terrain/pathfinding and the state
  serialized into the planner prompt vary with run order; memory backend is not
  the only changed variable.
- Minimum correction: classify these 24 logs as native exploratory evidence,
  then run Controlled Mode with a fresh canonical bot state for every run and
  retain the exact planner-input WorldState in the log.

### Critical — boundary equivalence was tested, but actual scenario inputs were not identical

- Location: `benchmark/minemembench/scenarios/delayed_recall.py` event creation
  (around lines 240, 279, 299); `core/ids.py`.
- Cause: actual campaign events use random event ids, wall-clock timestamps,
  drifting absolute coordinates, and run-specific scope. C proved that each
  adapter can round-trip one canonical test event, but did not prove that the
  four actual campaign cells received semantically identical event sequences.
- Effect on conclusions: **yes**. Retrieval order can respond to coordinate and
  timestamp text differences, confounding the backend comparison.
- Minimum correction: Controlled Mode must generate stable event ids, logical
  timestamps, actors/types/contexts/outcomes, and order for each
  `(difficulty, seed)`; only `episode_id` may differ for isolation. Retain the
  injected events in every result, including NoMemory.

### High — block execution order is confounded with backend and wall time

- Location: QA-002 reproduction and execution order.
- Cause: all three runs for one backend were completed before the next backend;
  control cells all preceded stress cells.
- Effect on conclusions: **yes for a formal comparison**. Live LLM/service and
  world drift are aliased with backend order.
- Minimum correction: a seed-major, pre-recorded counterbalanced backend order;
  fresh controlled fixture per run. Do not silently reshuffle after seeing
  outcomes.

### Medium — fairness metadata cannot reproduce the native world

- Location: all 24 `fairness` records.
- Cause: `minecraft_version="unknown"` and `world_seed=null`.
- Effect on conclusions: **not the direct source of the observed retrieval
  signal**, but it prevents independent reproduction and verification that the
  world stayed fixed.
- Minimum correction: strict controlled acceptance must fail when required
  environment identity is missing; mock Controlled Mode must record its fixed
  fixture identity/version explicitly.

### Low — QA report has reporting-only omissions

- Location: `docs/agents/qa/QA-002.md`, smoke table and reproduction block.
- Cause: add-latency values exist in JSON but are rendered as em dashes for
  vector/mem0/letta; the reproduction command uses bare `python`; the verdict
  says N/A none while describing missing world metadata.
- Effect on conclusions: **no**, raw JSON remains intact.
- Minimum correction: fix on the next C report revision; do not rerun for this
  reporting issue alone.

## Research decision

- QA-002 remains a successful three-agent integration/live-system test.
- `results/stress_round1/` is **Native Exploratory**, not Controlled Mode and
  not evidence for backend superiority or a Failure Point.
- Do not add another memory framework or expand seed counts.
- Agent B receives TASK-004; Agent C waits for a new release.

