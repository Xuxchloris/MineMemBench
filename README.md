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
| `delayed_recall / entity_key_v2` | `(interference_count, similar_distractor_count)` planned as (10,0)/(50,5)/(200,20)/(500,50) | Formal (200,20): Vector 10/10, Mem0 8/10, Letta 7/10 strict success; legacy rounds are non-poolable |
| `world_update / temporal_chain_v2` | `update_depth` 1–4; depth 3 is A→B→C→D | Formal depth 3: all active backends retrieve 10/10; behavior is Vector 3/10, Mem0 6/10, Letta 4/10 |
| `memory_noise_stress / key_retention_v2` | `noise_count` 0/10/50/100/200/500/1000 | Formal 10/30/50 Failure Points: Vector not observed, Mem0 30, Letta 50 |
| `failure_learning / observed_precondition_v2` | `interference_count` | real failed ActionResult → different-entity transfer; 0/10/50 diagnostics accepted, then stopped |
| `long_lived_memory / lifetime_v1` | `lifetime_event_count`, `session_count`, `relevant_update_count`, `similar_event_count` | Formal L1/L2/L3: Vector 5/0/0; Mem0 and Letta 10/10 at every level; lifetime is composite difficulty |
| `failure_learning_multi / observed_precondition_applicability_v4` | `observed_failure_count` 2–3, `interference_count` | one applicable plus 1–2 heterogeneous inapplicable real ActionResult failures; opaque non-ordinal alpha→iron, beta→string, gamma→gold mapping; completed target attack terminates the run; historical homogeneous v3 diagnostics are superseded |
| `failure_transfer` | — | **SUSPENDED / unregistered**: fabricated causal failure, invalid for claims |

### Controlled Formal V1 results (TASK-027)

TASK-026 is frozen and synchronized at commit
`592e4ab72193fa541a1a536a1eab2752b03acad6` (source fingerprint
`86c625f9a130be3b5a81c3ed7ca48db9eb128493eb703ac98ca905a2bb9fd3f6`).
The first Formal producer identity was clean-frozen and pushed at
`7c96df88c4208e47217da984f61798be051f56da`, but its campaign stopped
fail-closed after an external planner-DNS failure (`271` producer-ok, `1`
producer-failed, `48` pending, no retry). That root is audit evidence only and
cannot support conclusions.

Formal V1 Attempt 2 is the sole final Formal dataset. Its clean producer
identity is commit `64c822faf2ae8e490b3da11ed86261566bd93256`, source
fingerprint `ebfe9172dbe83abb5d76c2f8459ef346b8888d4f8e2bafca4d09799566bad3b3`.
It completed all eight preregistered cells × four backends × paired seeds
`1011–1020`: **320/320 valid, 0 missing, 0 duplicate, 0 retry, 0 exclusion**.
Calibration seeds `42/43/44`, Attempt 1, Native Mode, Graphiti and
failure-learning v4 remain separate and are never pooled.

The primary endpoint is strict evaluator-derived `task_success`. Active
backend comparisons use exact paired McNemar tests, paired risk differences,
a deterministic paired-bootstrap 95% CI, and Holm correction across the 24
pre-registered primary comparisons. Four lifetime L2/L3 comparisons reject
after Holm correction: Vector 0/10 versus Mem0/Letta 10/10 (paired RD −1.0,
95% CI [−1.0, −1.0], adjusted p 0.046875). The other 20 comparisons do not
reject; N=10 non-rejection is not equivalence.

Across all 320 runs, causal target retrieval was present with success in 180,
present with failure in 22, absent with success in 0, and absent with failure
in 118. The 22 retrieval-positive failures—17 in world update and five Vector
L1 lifetime runs—show why MineMemBench measures behavior rather than retrieval
alone.

Formal Failure Points are: noise—None 10, Vector not observed, Mem0 30, Letta
50; composite lifetime—None L1, Vector L1, Mem0/Letta not observed within
L1–L3. Full scenario tables, paired statistics, limitations, representative
cases and Dashboard V2 recommendations are in
`docs/formal_m15_v1_results.md`.

The first analyzer invocation stopped before outputs because the real
Controlled v2 event schema stores positions in typed `context.x/y/z`, not the
optional top-level `location`. The owner-authorized minimal compatibility fix
changed no data, treatment, endpoint or statistic and is disclosed in
`docs/agents/reviews/A-ANALYSIS-ERRATUM-027-ATTEMPT2.md`.

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

For provenance, the historical one-shot producer invocation is shown below.
**Do not run it again:** Formal production is closed and Attempt 2 may only be
read or reanalyzed. The producer refuses a dirty/mismatched source or a
non-empty Formal directory and has no resume/retry path:

```powershell
.venv\Scripts\python scripts\run_formal_m15_v1.py `
  --expected-git-commit <preregistration-freeze-commit> `
  --expected-source-fingerprint <frozen-source-sha256>

.venv\Scripts\python scripts\analyze_formal_m15.py `
  --results-dir results\formal_m15_v1_20260811_attempt2
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

The local observability dashboard is a read-only consumer of existing raw
results. It never imports into the producer path and never starts a benchmark:

```powershell
.venv\Scripts\python -m minemembench.dashboard --results-dir results
```

It binds to loopback, recursively indexes historical/current manifests and
results, shows live campaign/backend/cell progress and costs, replays stored
RunSteps through a seekable semantic timeline without an LLM/bot/backend, and
compares None/Vector/Mem0/Letta for one exact same-seed treatment while failing
closed on incomplete fairness. See `docs/dashboard_replay_design.md` and
`docs/difficulty-calibration.md`.

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
- Existing seeds `42/43/44` are diagnostic calibration only, not a formal
  ranking, effect size, Failure Point, Native-Minecraft result, or
  cost-efficiency comparison. Formal V1 uses a separate fixed paired sample.
- Formal attempt 1 is an incomplete producer incident, not a pilot or partial
  result. It is retained under `results/formal_m15_v1_20260811` and excluded
  from every attempt-2 denominator and claim.
- Attempt 2 is the only final Formal dataset. Its 320 raw runs were not retried
  or modified during analysis. The post-producer typed-context analyzer
  compatibility erratum is disclosed and limits claims to the corrected,
  auditable analysis implementation.
- The M15.1 TASK-026 implementation is clean-frozen and pushed at commit
  `592e4ab72193fa541a1a536a1eab2752b03acad6`, source fingerprint
  `86c625f9a130be3b5a81c3ed7ca48db9eb128493eb703ac98ca905a2bb9fd3f6`;
  strict freeze verification passed and local `main` matched `origin/main`.
  That makes the implementation reproducible but does not turn earlier dirty
  calibration evidence into Formal data.
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
- [x] M15.1 lifetime/multi-failure difficulty plus read-only replay/dashboard
- [x] TASK-027 Formal attempt-2 freeze, fixed 320-run study, integrity audit,
  paired analysis and final research report
- [ ] Later: Graphiti, ReMe, Text2Mem, A-Mem, Generative Agents memory
