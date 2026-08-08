# TASK-001 — Integration shakedown: baseline commit + independent QA

Drafted by: B, **pending A ratification** (A may reissue it verbatim).
Purpose: exercise the A→B→C→A workflow end-to-end on a small, real piece of
work before the M15B experiment campaign starts.

## Current state (verified by A, 2026-08-08)

- The M15B stress-layer code is **already implemented and reviewed by A**
  (222 pytest green, 31 TS green). It sits **uncommitted** in the working
  tree: 9 modified files (`.env.example`, `README.md`, `cli.py`,
  `core/config.py`, `agent/planner.py`, `scenarios/base.py`,
  `scenarios/delayed_recall.py`, `scenarios/registry.py`,
  `scenarios/world_update.py`) plus new files (`core/fairness.py`,
  `scenarios/failure_transfer.py`, `scenarios/memory_noise_stress.py`,
  `scenarios/offsets.py`, 7 new test files, `docs/stress_design.md`,
  `docs/agents/**`, `docs/experiment_standard.md`).
- Infrastructure is running: MC server (port 25565), bot bridge
  (`http://localhost:8081/health`, mode `minecraft`), Letta stack
  (`docker compose -f docker-compose.letta.yml ps`: letta-server on
  127.0.0.1:8283, letta-ollama healthy).

## Part 1 — B: baseline commit

The M15B code needs no changes (A-reviewed). B's job is to verify and commit
it exactly as reviewed — this tests B's verify/scan/commit/push discipline.

1. `git status --short` — confirm the tree matches the file set above (plus
   these coordination docs). If anything unexpected appears, STOP and report
   to A instead of committing.
2. `.venv/Scripts/python -m pytest -q` → expect **222 passed**.
   `cd minecraft && npm test` → expect **31 passed**.
3. Sensitive scan: staged paths must exclude `.env` (except `.env.example`),
   `server.jar`, `node_modules/`, `.venv/`, `__pycache__/`, `results/`,
   `world/`, `.models/`; staged content must contain no API keys/tokens.
4. `git add -A`, commit: `feat: M15B long-term memory stress benchmark layer`
   and push `origin main`. Verify with `git ls-remote origin main`.
5. Record in this file's `## Completion`: commit SHA, test counts, scan
   result, push confirmation.

## Part 2 — C: independent QA battery (after B's push)

1. `git pull` and confirm HEAD equals B's reported SHA.
2. Re-run: pytest (222), TS tests (31). Any difference from B's numbers is an
   anomaly — report it.
3. Health checks: `curl http://localhost:8283/v1/health/` (letta, expect
   version 0.16.8), ollama container healthy, bot `/health` mode minecraft.
4. Backend isolation evidence: `.venv/Scripts/python scripts/verify_letta_live.py`
   (expect 3×PASS — includes the reset-isolation check C), plus
   `.venv/Scripts/python -m pytest -q -k "fairness or memory"` for the
   offline isolation/unit coverage.
5. Small experiment matrix (2 cells × 4 backends × 3 runs = 24 runs),
   with `RESULTS_DIR=results/stress_smoke` and `PYTHONIOENCODING=utf-8`:
   - `delayed_recall`, `--scenario-param interference_count=50
     --scenario-param similar_distractor_count=5`
   - `memory_noise_stress`, `--scenario-param noise_count=100`
   backends `none vector mem0 letta`, `--runs 3 --seed 42` per cell.
   Do NOT expand the matrix beyond this.
6. Data-integrity audit of the 24 logs: expected count per cell, no duplicate
   episode ids, `fairness.valid == true` in every log, N/A fields reported as
   N/A (not counted as failures), no failed run missing its log.
7. Write `docs/agents/qa/QA-001.md`: per-check PASS / FAIL / N/A, the
   anomalies list (reproduction: input / expected / actual / log location),
   and the observed success/token/latency summary per cell. C commits
   nothing; B will include the report in the next commit.

## Part 3 — A: final review

A reviews B's commit diff + C's QA-001 and issues findings
(Critical/High/Medium/Low) before the M15B formal campaign is scheduled.

## Completion

(to be filled by B, then appended by C's report reference and A's verdict)
