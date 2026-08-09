# TASK-021 — Bounded failure-learning v2 Controlled smoke

Issued by: Agent A  
Executor: Agent A (B unavailable); Agent C verifies after completion  
Status: **authorized diagnostic execution**

Run exactly one fresh campaign for:

- `failure_learning`
- `failure_semantics_version=observed_precondition_v2`
- `interference_count=0`
- backends `none,vector,mem0,letta`
- seeds `42,43,44`
- 12 total runs

Use `scripts/run_controlled_campaign.py`; let it select
`warded_hostiles_v1`, create campaign-local vector/Mem0 stores, start one
fresh mock process per run, and stop on the first failure. Do not retry,
replace, delete, or exclude a failed run. Do not change code/parameters during
execution. Preserve manifest, stdout/stderr logs and every produced result.

After execution, Agent C independently checks run count/status, seeds,
run_ids, fixture/fairness identity, event/evidence fingerprints, missing or
duplicate logs, retrieval/behavior metrics, crashes/errors, and descriptive
per-backend/per-seed results. Agent A performs the final research review.

This is diagnostic only: no ranking, effect-size, formal Failure Point, or
Native Minecraft claim is authorized.
