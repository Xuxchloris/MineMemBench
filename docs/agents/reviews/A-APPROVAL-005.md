# A-APPROVAL-005 — Release Controlled campaign to C

Date: 2026-08-08
Reviewer: Agent A
Decision: **PASS — Agent C may execute Controlled QA-005**

Independent A gates:

- Python: **251 passed in 90.70s**.
- TypeScript: **31 passed**.
- `git diff --check`: no errors; protocol/results unchanged.
- TASK-005 runner fixes inspected and accepted.
- A ran one real campaign-runner invocation in a system temp directory:
  exit 0, fresh mock health, complete fixture gate, manifest status/return
  code, retained stdout/stderr, exactly one linked scenario JSON,
  campaign-local Vector/Mem0 paths, 11 deterministic injected events, raw
  RunStep WorldState, and no bot listener left afterwards.
- Two stale mock adapters left by B's manual smoke were identified by exact
  command/PID and stopped; user Minecraft/Letta services were untouched.

## C release

C may run exactly the default 24-run Controlled delayed-recall smoke into the
new path `results/stress_controlled_round1/`, using
`scripts/run_controlled_campaign.py` with seeds 42/43/44, the four default
backends, and only control `(10,0)` plus stress `(50,5)`.

C must not rerun/resume on failure, must not touch
`results/stress_round1/`, and must audit the manifest, per-run command logs,
actual injected-event equivalence (excluding episode scope only), normalized
step-0 WorldState equality, reset/fairness, and all 24 raw results. Native and
Controlled conclusions must be reported separately.
