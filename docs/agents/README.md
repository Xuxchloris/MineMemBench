# Three-Agent Coordination Protocol

> Status: **DRAFT — prepared by B** (Kimi Code dev window, 2026-08-08) ahead
> of role assignment. A (Codex) may ratify, amend, or replace this document.

MineMemBench is developed by three agents with strictly separated roles.
This file is the single source of truth for how work flows between them.

## Roles

- **A — Tech & research lead** (Kimi Code, window A). Owns architecture,
  research design, task specs, and the final review of every stage. Writes
  specs/reviews under `docs/`. Does **not** write production code or run the
  experiment matrix; any fix is delegated to B unless it is an
  architecture-level emergency.
- **B — Main developer** (Kimi Code, window B). The only role that writes
  production code. Implements A's task specs, runs unit tests, commits and
  pushes. Never changes scenario semantics, difficulty, or metrics beyond
  what A's spec says.
- **C — QA / experiment runner** (opencode + DeepSeek). The only role that
  runs experiments and writes QA reports. Independently verifies every B
  commit (tests, health checks, isolation checks, small matrices), audits
  data integrity, and reports anomalies. Never fixes production code;
  findings go to A, fixes go to B.

## Workflow (fixed)

1. A writes a task spec: `docs/agents/tasks/TASK-<id>.md`.
2. B implements exactly that spec, runs the full test suites, commits with
   the sensitive-scan discipline below, pushes, and records the commit SHA +
   test counts in the task file's `## Completion` section.
3. C checks out that commit, runs the QA battery defined in the task, and
   writes `docs/agents/qa/QA-<id>.md` (PASS / FAIL / N/A per check, plus an
   anomalies list with reproduction: input, expected, actual, log location).
4. A reviews B's diff + C's QA report and issues a findings list rated
   Critical / High / Medium / Low, each with file location, cause, whether it
   affects experimental conclusions, and a minimal fix.
5. B fixes Critical/High findings; Medium/Low are scheduled by A.

Only one role is active on the repo at a time. The human relays between
windows; repo files are the durable channel.

## Git discipline (binding on B; verified by C and A)

- Only B runs `git commit` / `git push`. C never commits; A commits nothing.
- Before every commit: full pytest + TS tests green, then a sensitive scan —
  staged paths must not match `.env` (except `.env.example`), `server.jar`,
  `node_modules/`, `.venv/`, `__pycache__/`, `results/`, `world/`,
  `.models/`, `coverage/`, `dist/`; staged content must not contain API keys,
  tokens, or passwords.
- `results/` is gitignored on purpose: experiment logs never enter git.
  QA reports (small markdown) are the exception and live under
  `docs/agents/qa/`, committed by B in the next fix commit.
- Never delete or edit existing run logs. Failed runs stay in the data.

## Experiment discipline (binding on C; designed by A)

- Every experiment follows `docs/experiment_standard.md` (cells, seeds,
  failure-point definition, contamination guards). C never tunes scenario
  parameters to make results look better.
- Stress-matrix runs write to an isolated `RESULTS_DIR` (e.g.
  `results/stress_smoke/`), never into the classic matrix location.
- N/A values are reported as N/A, never counted as failures, never dropped.
