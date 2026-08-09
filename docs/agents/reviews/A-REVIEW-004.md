# A-REVIEW-004 — TASK-004 implementation review

Date: 2026-08-08
Reviewer: Agent A
Decision: **REWORK — C remains blocked**

The Controlled core is accepted in principle: deterministic delayed-recall
events, actual offered-event retention, normalized planner state, raw
WorldState snapshots, mode identity, one-run CLI gate, fresh mock lifecycle,
and counterbalanced precomputed order are the right architecture.

## Findings

### Critical — a second invocation can silently mix with/overwrite an existing campaign

- Location: `scripts/run_controlled_campaign.py`, `main()` / `run_campaign()`.
- Cause: `write_manifest()` overwrites `campaign_manifest.json`, and no gate
  requires a new empty output directory. Existing `scenario_*.json` files
  remain, so rerunning the same command can create 48 logs under a manifest
  that describes only the newest 24.
- Effect on conclusions: **yes**. Duplicate/old runs can silently enter the
  dataset and destroy the pre-registered schedule.
- Minimum fix: fail before writing anything unless the output path is absent or
  an existing directory is completely empty. Never auto-delete or resume.
  Add a test proving an existing manifest or scenario log is rejected without
  mutation.

### High — Vector and Mem0 campaign stores are not isolated

- Location: `scripts/run_controlled_campaign.py::_invoke_run`.
- Cause: only `RESULTS_DIR` is overridden. `VECTOR_DB_PATH` and
  `MEM0_QDRANT_PATH` can therefore resolve to the user's historical stores.
- Effect on conclusions: **potentially yes**, especially when testing the reset
  and episode-isolation contract the benchmark is supposed to measure.
- Minimum fix: pre-register campaign-local store paths in the manifest and set
  both environment variables for every invocation. Do not use or modify the
  historical stores.

### High — failed-run diagnostics are printed but not retained

- Location: `scripts/run_controlled_campaign.py::_invoke_run` and manifest
  entry update.
- Cause: subprocess stdout/stderr inherit the terminal. The manifest records a
  return code but no durable command log or result-file link.
- Effect on conclusions: **yes for data completeness**. A crash/error cannot be
  independently reproduced or audited after the terminal is gone.
- Minimum fix: pre-register per-run stdout/stderr log paths, redirect both
  streams there, and record the produced scenario JSON path(s) after each run.
  On error, preserve logs and stop; never retry.

### Medium — fixture identity is stronger than the check performed

- Location: `cli.py::CONTROLLED_FIXTURE_IDENTITY` and
  `_assert_controlled_fixture`.
- Cause: identity claims fixed inventory/entities and a canonical state, while
  the gate checks only position, dimension, time, and rain.
- Effect on conclusions: **not with the current unmodified mock**, but future
  fixture drift could pass while changing the planner prompt.
- Minimum fix: compare the complete normalized initial WorldState (everything
  except observation timestamp) against the canonical fixture, including mode,
  username/vitals/orientation/inventory/equipment/entities/players.

