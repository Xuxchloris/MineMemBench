# MineMemBench

**A reproducible benchmark for evaluating how long-term memory frameworks affect
embodied LLM agent behavior in Minecraft.**

This is not "a Minecraft AI bot". The bot is only the test harness. The object of
study is the **memory backend** and its measurable effect on agent behavior.

## 1. Research Question

Not "can an agent remember a sentence", but:

> Do different long-term memory frameworks change an embodied LLM agent's actual
> behavior — task completion, adaptation, and belief updating — in a persistent
> interactive environment?

Controlled variables across all runs: same world seed, same LLM, same system
prompt, same tool set, same scenario, same temperature. The only independent
variable is the **memory backend**.

Phase 1 backends: `none` (baseline), `vector` (simple local baseline),
`mem0`, `letta`. Reserved for later: Graphiti, ReMe, Text2Mem, A-Mem,
Generative-Agents-style memory.

## 2. Architecture

```
Minecraft Server (Java Edition)
        |
Mineflayer Bot  (TypeScript adapter — minecraft/)
        |  raw game events (WebSocket) / state+actions (HTTP)
        v
Event Semantic Layer  (Python — raw events -> ExperienceEvent)
        |
Memory Backend  (pluggable, unified MemoryBackend interface)
        |  retrieved memories
        v
LLM Planner  (OpenAI-compatible provider, structured JSON actions)
        |
Mineflayer Executor  (high-level actions only — no keyboard-level control)
        |
Benchmark Logger / Metrics
```

Hard decoupling rules:

- The bot and the benchmark core are separate processes talking over a versioned
  JSON protocol (`docs/protocol.md`).
- The planner never branches on `memory_type`; backends are injected.
- The event layer records **what happened**, never how the agent should feel
  about it (no hand-coded trust/personality rules).

## 3. Memory Backends

All backends implement one abstract interface (`benchmark/minemembench/memory/base.py`):

```python
class MemoryBackend(ABC):
    async def add(self, event: ExperienceEvent) -> None: ...
    async def retrieve(self, query: MemoryQuery) -> list[MemoryItem]: ...
    async def update(self, event: ExperienceEvent) -> None: ...
    async def reset(self, episode_id: str) -> None: ...
    async def stats(self) -> MemoryStats: ...
```

| Backend | Status |
|---|---|
| `none` | implemented (M4) |
| `vector` | implemented (M6) |
| `mem0` | implemented (M8) |
| `letta` | implemented (M9); live acceptance N/A (see Limitations) |
| `graphiti` | implemented (P2); live acceptance N/A (see Limitations) |

## 4. Benchmark Scenarios

Scenarios are reproducible, seeded episodes with distinct phases
(`setup → experience → interference → test → evaluate`):

- **A — Delayed Fact Recall**: learn a fact, survive an interference flood, use
  the fact. Measures long-term retention.
- **B — World State Update**: a learned fact changes mid-episode. Measures stale
  memory rate / belief updating (designed with temporal-graph memory such as
  Graphiti in mind).
- **C — Experience-Guided Adaptation**: a real failure is stored; a similar task
  follows. Measures whether memory changes *preparation behavior* — without any
  hard-coded "learn from failure" rule.

## 5. Metrics

Task success rate · recall accuracy · stale memory rate · behavioral adaptation
rate · avg retrieved memories · prompt/total token cost · LLM calls · memory
write/retrieval latency · end-to-end decision latency.

**No fabricated numbers.** Anything not actually measured is reported as `N/A`.

## 6. Reproduction Guide

Prerequisites: Node ≥ 20, Python ≥ 3.12 (uv recommended), Java ≥ 17
(only for a real Minecraft server).

```bash
# Python core
uv venv --python 3.12 && source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
pytest

# Bot adapter
cd minecraft && npm install && npm run build && npm test

# Mock-mode smoke test (no Minecraft server needed)
BOT_MOCK=1 node dist/index.js &
python -m minemembench probe --action chat --args '{"message":"hello"}'

# Real server (accepts EULA — for local research use only)
cd minecraft/server && java -jar server.jar nogui
BOT_MOCK=0 node dist/index.js
```

Docker Compose (`docker-compose.yml`) wires mc-server + bot + benchmark together.

## 7. How to Add a New Memory Backend

1. Subclass `MemoryBackend` in `benchmark/minemembench/memory/`.
2. Register it in the backend registry (name → factory, env-configured).
3. Add adapter-level unit tests with the framework mocked at its SDK boundary.

No changes to planner, scenarios, or metrics are permitted — that is the point of
the benchmark.

## 8. How to Add a New Scenario

1. Subclass `Scenario` in `benchmark/minemembench/scenarios/`.
2. Implement `setup / experience_phase / interference_phase / test_phase / evaluate`.
3. Register a name; it becomes selectable via `--scenario`.

## 9. Limitations

- Single agent, single environment (Minecraft). No multi-agent claims.
- LLM planner behavior is stochastic; conclusions need multiple seeded runs.
- High-level actions only — this benchmarks memory, not motor control.
- Mem0/Letta adapters depend on those projects' evolving APIs; adapters pin and
  document the versions they were verified against.
- Letta live acceptance is **N/A** on the reference machine, verified
  empirically (2026-08, letta 0.16.8): no Docker is available, and the
  pip-installed `letta server` hard-requires PostgreSQL — `letta/server/db.py`
  builds a module-level PG engine and `settings.letta_pg_uri` defaults to
  `postgresql+pg8000://letta:letta@localhost:5432/letta` (additional pip
  friction: `asyncpg` missing, `mcp>=2` incompatible with `fastmcp 2.14`).
  The adapter is covered by SDK-boundary tests against letta-client 1.12.1.
- Graphiti live acceptance is **N/A** with the benchmark's controlled LLM,
  verified empirically (2026-08, graphiti-core 0.29.3 + embedded Kuzu): the
  adapter runs end-to-end (add_episode → search → reset), but graphiti's
  OpenAI-tuned extraction prompts yield empty/thin graphs from DeepSeek
  (v4-flash and v4-pro both return zero or near-zero entities and zero
  relation edges in direct extraction probes), so no retrievable facts are
  ever created. Two upstream Kuzu-driver bugs were shimmed in the adapter
  (missing `_database`/`clone`, non-idempotent FTS index creation). The
  adapter is covered by boundary tests with an injected fake client.

## 10. Roadmap

- [x] M1 repo skeleton, protocol, config
- [ ] M2 Mineflayer bot: login, state, move/chat
- [ ] M3 Python ↔ bot bridge
- [x] M4 NoMemory + LLM planner (agent loop)
- [x] M5 Event semantic layer (ExperienceEvent)
- [x] M6 Vector memory baseline
- [x] M7 Scenario A (Delayed Fact Recall) end-to-end
- [x] M8 Mem0 adapter (against current official docs)
- [x] M9 Letta adapter (against current official docs)
- [x] M10 Scenarios B + C
- [x] M11 Reports: CSV / Markdown / charts
- [ ] Later: Graphiti, ReMe, Text2Mem, A-Mem, Generative Agents memory
