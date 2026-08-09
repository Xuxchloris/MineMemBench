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

Two execution identities are explicit in every result. **Native Mode** is for
exploratory/live Minecraft behavior. **Controlled Mode** starts a fresh,
versioned mock fixture per run and uses deterministic semantic events for
causal backend comparisons. Native and Controlled evidence is never pooled.

Phase 1 comparison backends: `none` (baseline), `vector` (simple local
baseline), `mem0`, `letta`. A `graphiti` adapter is implemented, but live
acceptance is N/A under the controlled DeepSeek extractor and it is excluded
from the four-backend Controlled matrix. Reserved for later: ReMe, Text2Mem,
A-Mem and Generative-Agents-style memory.

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

Phase 1's easy scenarios often saturate, so the stress layer exposes versioned,
configurable difficulty treatments. Every
difficulty knob is settable from the CLI with repeatable `--scenario-param
KEY=VALUE` (no code changes), and the effective parameter dict is recorded into
every run log for the fairness audit. Legacy defaults remain loadable for
historical Native results; ranking-eligible Controlled treatments use the
explicit v2 semantics below.

| Scenario / Controlled semantics | Difficulty parameter(s) | Current evidence boundary |
|---|---|---|
| `delayed_recall / entity_key_v2` | `(interference_count, similar_distractor_count)` planned as (10,0)/(50,5)/(200,20)/(500,50) | v2 (200,20) diagnostic only; legacy rounds are non-poolable |
| `world_update / temporal_chain_v2` | `update_depth` 1–4; depth 3 is A→B→C→D | depth-3 diagnostic accepted; remaining curve gated |
| `memory_noise_stress / key_retention_v2` | `noise_count` 0/10/50/100/200/500/1000 | 0/10/50 diagnostics accepted, then stopped; no formal Failure Point |
| `failure_learning / observed_precondition_v2` | `interference_count` | real failed ActionResult → different-entity transfer; 0/10/50 diagnostics accepted, then stopped |
| `failure_transfer` | — | **SUSPENDED / unregistered**: fabricated causal failure, invalid for claims |

Configuration example only (not an experiment authorization):

```bash
.venv/Scripts/python -m minemembench run --scenario delayed_recall --memory vector \
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

New Controlled manifests use `controlled-campaign/v4`: before run 1 they record
a deterministic SHA-256 fingerprint of the allowlisted producer source/test/
config tree plus read-only git commit/dirty state. Each result repeats the
compact provenance in its fairness record, and a mismatch stops the campaign.
`--require-clean-source` rejects a dirty/unavailable git tree before creating
output. This provenance does not replace a reviewed commit or formal
preregistration; see `docs/development_plan.md` and
`docs/preregistration_template.md`.

After the external review owner creates a clean candidate commit, verify it
without starting a campaign or creating output:

```powershell
.venv\Scripts\python scripts\verify_source_freeze.py --require-clean `
  --expected-source-fingerprint <A-approved-sha256> `
  --expected-git-commit <reviewed-commit-sha>
```

The verifier prints compact hashes/counts/booleans only. Diagnostic mode
without `--require-clean` may inspect a dirty tree but does not authorize it.

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
- Current M15 Controlled evidence uses three paired seeds per cell on versioned
  mock fixtures. It is diagnostic, not a formal ranking, effect size, Failure
  Point, Native-Minecraft result, or cost-efficiency comparison.
- The working evidence revision is currently dirty. Formal campaigns require a
  clean externally reviewed commit, frozen preregistration and
  `--require-clean-source`; source fingerprints alone do not make old evidence
  formal.
- High-level actions only — this benchmarks memory, not motor control.
- Mem0/Letta adapters depend on those projects' evolving APIs; adapters pin and
  document the versions they were verified against.
- Letta runs live via `docker-compose.letta.yml` (letta/letta:0.16.8 with
  embedded PG15+pgvector, plus an ollama service for `nomic-embed-text`
  embeddings); see docs/letta_live.md and scripts/verify_letta_live.py
  (`--require-live` for strict acceptance runs). Every archival passage
  carries the full `ExperienceEvent` JSON in an `event_payload=` tag
  (round-trips verbatim, never embedded — verified live against 0.16.8), so
  retrieval reconstructs the exact recorded event and the retrieval-layer
  structured-fact metrics are measured for letta too; the earlier text-only
  limitation no longer applies. Letta add/retrieve latency is ~200 ms per
  call (HTTP + ollama embedding) vs single-digit ms for the local backends,
  and the agent-scoped archival search returns no relevance score
  (`MemoryItem.score` stays `None`).
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
- [x] M2 Mineflayer bot: login, state, move/chat
- [x] M3 Python ↔ bot bridge
- [x] M4 NoMemory + LLM planner (agent loop)
- [x] M5 Event semantic layer (ExperienceEvent)
- [x] M6 Vector memory baseline
- [x] M7 Scenario A (Delayed Fact Recall) end-to-end
- [x] M8 Mem0 adapter (against current official docs)
- [x] M9 Letta adapter (against current official docs)
- [x] M10 Scenarios B + C
- [x] M11 Reports: CSV / Markdown / charts
- [x] M15A Letta Docker live memory-only integration
- [x] M15B versioned stress scenarios + Controlled diagnostic infrastructure
- [ ] Formal preregistered M15 study on a clean reviewed revision
- [ ] Later: Graphiti, ReMe, Text2Mem, A-Mem, Generative Agents memory
