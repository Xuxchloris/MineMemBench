# A-APPROVAL-009 — Event-time and prompt-fingerprint code gate

Date: 2026-08-08
Reviewer: Agent A
Decision: **PASS FOR FINAL CORRECTED 3-RUN SMOKE**

## Verification

- B's change is confined to `agent/planner.py`, `core/fairness.py`, and their
  tests; it does not change backends, retrieval, scenario facts, success,
  protocol, model, tools, Minecraft, or old results.
- A independently reviewed the code and ran the focused suite: **50 passed in
  2.22s**.
- B full suite: **259 passed**. C independently reproduced focused **50**,
  full Python **259**, TypeScript **31** plus build, Letta 0.16.8 health, and
  strict live add/retrieve/update/reset PASS.
- C loaded a pre-TASK-009 round-3 JSON with the current `ScenarioResult`; its
  absent optional fingerprint correctly becomes `None`.
- New fairness records populate the 64-hex planner-template hash
  `988e01277f199fc0b8f48b1f57f7efe7da8bafd4ebd36267f509fc2af8b0df39`.
- The planner view contains deterministic semantic event time while all item
  ids, event/episode ids, scores, storage times, metadata and raw events stay
  absent.

No Critical/High issue remains for the requested diagnostic smoke. Formal
experiments still require a clean immutable code revision and more than three
runs per cell.

## Release

Proceed to TASK-010 exactly once. Do not run any other cell or difficulty.

