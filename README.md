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
| `letta` | implemented (M9); live server via `docker-compose.letta.yml` (see docs/letta_live.md) |
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

### M15B — Long-Term Memory Stress Layer

Phase 1's easy scenarios saturate (vector/mem0/letta all score ~100%), so the
stress layer scales the difficulty until each framework starts to fail. Every
difficulty knob is settable from the CLI with repeatable `--scenario-param
KEY=VALUE` (no code changes), and the effective parameter dict is recorded into
every run log for the fairness audit. Defaults reproduce the Phase-1 behavior
byte-for-byte, so the 120-run matrix stays reproducible.

| Scenario | Difficulty parameter(s) | New metrics |
|---|---|---|
| `delayed_recall` (A-stress) | `interference_count` 10/50/200/500, `similar_distractor_count` 0/5/20/50 | `recall_accuracy`, `wrong_fact_rate`, `retrieval_precision` (+ existing task/token/latency) |
| `world_update` (B-stress) | `update_depth` 1=A→B, higher chains A→B→C→D | `stale_memory_rate`, `obsolete_fact_retrieval_rate`, `current_fact_accuracy`; raw retrieved items of every retrieval probe saved into the run log |
| `memory_noise_stress` (D) | `noise_count` 0/10/50/100/200/500/1000 | `task_success`, `relevant_memory_precision`, `irrelevant_retrieval_rate`, `retrieval_latency`, `token_cost`, `end_to_end_latency` |
| `failure_transfer` (E) | `transfer_count`, `noise_fact_count` | `adaptation_success`, `preparation_rate`, `failure_repetition_rate`, `transfer_success_rate` |

Example CLI:

```bash
python -m minemembench run --scenario delayed_recall --memory vector \
  --scenario-param interference_count=200 --scenario-param similar_distractor_count=20 \
  --runs 30
```

Every run also carries a fairness record (Minecraft version, world seed, planner
model, temperature, system-prompt hash, tool-set hash, scenario + parameter
dict) and passes an episode-leakage probe: the next run must not be able to
retrieve the previous episode's memories — a run that can is marked invalid in
its log. See `docs/stress_design.md` for the design rationale. New stress
metrics are stored per-run in the `scenario_*.json` logs (with unmeasured values
as `N/A`); the M11 report aggregates the classic cross-scenario metrics.

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

# Letta memory server (only needed for the `letta` backend)
docker compose -f docker-compose.letta.yml up -d
.venv/Scripts/python scripts/verify_letta_live.py
```

Docker Compose (`docker-compose.yml`) wires mc-server + bot + benchmark together.
`docker-compose.letta.yml` starts the optional Letta memory server and its
ollama embedding service (see docs/letta_live.md).

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
- Letta runs live via `docker-compose.letta.yml` (letta/letta:0.16.8 with
  embedded PG15+pgvector, plus an ollama service for `nomic-embed-text`
  embeddings); see docs/letta_live.md and scripts/verify_letta_live.py.
  Because letta archival passages round-trip **text only** (no structured event
  context), the retrieval-layer structured-fact metrics are **N/A**
  (`current_fact_accuracy` in world_update, `fact_retrieval_rank` in
  delayed_recall), while the behavioral metrics (`task_success`, `stale_action`,
  `adaptation`) are fully measured. Letta add/retrieve latency is ~200 ms per
  call (HTTP + ollama embedding) vs single-digit ms for the local backends.
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
