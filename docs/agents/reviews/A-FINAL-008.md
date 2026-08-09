# A-FINAL-008 — Decontaminated round-3 research review

Date: 2026-08-08
Reviewer: Agent A
Decision: **DATA VALID; REWORK TEMPORAL SEMANTICS BEFORE FORMAL USE**

## Independent evidence gate

A re-derived the campaign directly from the manifest and 12 scenario JSONs:

- 12/12 manifest entries are `ok`; 12 unique run ids and 12 unique episode
  ids;
- for every seed, all four backends receive the same ordered 221
  ExperienceEvents after replacing only `episode_id`;
- step-0 WorldState is identical per seed after excluding only its raw
  observation timestamp;
- all target candidates share one actor/event-type/context-key shape and have
  no correctness/staleness label;
- metric ranks exactly match event-id re-derivation from the causal step-0
  retrieval;
- fairness is valid 12/12 and both post-reset probes are zero 12/12;
- every memory-backed first action moves to the coordinates of retrieval item
  1. No backend or scenario directly selects the action.

Agent C independently reached the same result in `QA-008.md`. The data in
`results/stress_controlled_round3_decontaminated_200_20/` are valid for the
narrow diagnostic performed.

## Narrow supported result

- NoMemory: 0/3, empty retrieval.
- Vector: 3/3; correct rank `[1,1,1]`.
- Mem0: 0/3; correct rank `[2,N/A,N/A]`.
- Letta: 0/3; correct rank `[3,7,9]`.

This confirms that removing the leaked labels exposes a real difference in
backend ordering/recall. It does **not** yet establish general framework
superiority or a formal Failure Point.

## Findings

### High — the planner cannot observe the temporal cue named by the goal

- Location: the goal says "learned ... at the start of this episode", while
  `agent/planner.py::memory_view_for_prompt()` removes the ExperienceEvent
  timestamp. Controlled target candidates otherwise differ only by
  coordinates and retrieval position.
- Cause: TASK-007 grouped semantic event time with backend-specific storage
  internals. That was too broad. `created_at`, score and backend metadata are
  backend-specific; `ExperienceEvent.timestamp` is part of the equal event
  treatment and, in Controlled mode, is deterministic across backends.
- Effect on conclusions: **yes**. The LLM has no content-level basis for
  identifying "at the start" and consistently follows item 1. Vector's win is
  explained by exact score ties plus stable oldest-insertion ordering. This is
  a useful top-1 diagnostic, not yet a semantically complete delayed-recall
  result.
- Minimum fix: restore the event timestamp in the backend-neutral semantic
  prompt view while continuing to strip item/event ids, episode id, score,
  storage time, metadata and raw events. Do not expose a correctness label or
  change retrieval order.

### Medium — planner user-template changes are not fingerprinted

- Location: `core/fairness.py::FairnessRecord` records only the system prompt
  and tool hashes.
- Effect on conclusions: pre/post prompt schemas can share the same recorded
  hashes, so formal reproduction is incomplete.
- Minimum fix: add a stable planner-prompt/template hash that covers the user
  section template and allowed memory-view schema. Make the field optional on
  model input for backward compatibility, but populate it for every new run.

## Decision

Proceed to TASK-009. Do not run `(500,50)`, add a framework, or enlarge n.
After code/QA approval, repeat only `(200,20)` in a new directory. Never pool
rounds 2, 3, and 4 because their prompt/scenario treatments differ.

