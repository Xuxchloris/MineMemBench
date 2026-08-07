# MineMemBench — Rules for Development Agents

You are a development agent working in this repo. A separate review agent
dispatches tasks to you, then runs and verifies everything itself. Follow these
rules exactly — they exist so the benchmark stays methodologically valid.

## What this project is

A reproducible benchmark for evaluating how long-term memory frameworks affect
embodied LLM agent behavior in Minecraft. NOT a Minecraft bot project.
Read `README.md` and `docs/protocol.md` before writing any code.

## Hard rules

1. **Never `git commit` / `git push` / `git add`.** The review agent owns git.
2. **Never put secrets in code or tests.** Config comes from env / `.env`
   (see `.env.example`). `.env` exists locally — never print, copy, or read it
   into source files.
3. **`docs/protocol.md` is the wire contract** between the TS bot adapter and
   the Python core. Do not change it. If a task truly requires a protocol
   change, stop and report instead of changing it.
4. **No network in unit tests.** LLM calls, HTTP, WebSockets: use fakes /
   `httpx.MockTransport`. Never call the real LLM API from tests.
5. **No fabricated results.** Anything under `results/` must come from real
   runs; unmeasured values are reported as `N/A`.
6. **Memory backends are plugins.** All access goes through
   `benchmark/minemembench/memory/base.py::MemoryBackend`. Never branch on a
   backend name in planner/scenario/runner code.
7. **The event layer records what happened, never what the agent should think
   about it.** No trust scores, moods, or hand-coded behavioral rules.

## Environment (Windows, Git Bash)

- Python: use the repo venv — `.venv/Scripts/python` (NEVER bare `python`,
  which is 3.8). Install deps: `uv pip install -e ".[dev]"`.
- Run Python tests: `.venv/Scripts/python -m pytest -q`
- TypeScript side lives in `minecraft/`: `npm run build`, `npm test`.
- The Minecraft server jar and world live in `minecraft/server/` (gitignored);
  the review agent starts/stops them — you do not need a live server; the
  TS adapter has a mock mode (`BOT_MOCK=1`).

## Code style

- Strong typing everywhere (pydantic v2 models / strict TS); no `Any` unless
  the wire format is genuinely free-form.
- Async-first, small focused modules, English comments/docstrings.
- Match the conventions of the existing modules you touch.

## Definition of done for every task

- The dispatched task's acceptance criteria are met.
- `.venv/Scripts/python -m pytest -q` is green (and `npm test` if you touched
  `minecraft/`).
- Report back: files created/modified, test output summary, and any
  deviations from the task spec.
