# A-AUDIT-002 — Repository audit and next research gate

Date: 2026-08-08
Authority: Agent A (technical/research lead)

## Repository state

- HEAD/origin: `cbaa276`; clean-HEAD test baseline was 222 Python tests and
  31 TypeScript tests passing.
- During this audit an orphaned B process from the previous shakedown wrote a
  partial four-file change (`cli.py`, `core/fairness.py`, `letta_adapter.py`,
  `scenarios/base.py`). A stopped that exact process. The partial tree is not
  approved: a focused test run currently has 10 failures because production
  interfaces changed before tests were updated.
- `docs/development_plan.md` is missing. A stale milestone prompt is tracked at
  the accidental root path `docsdevelopment_plan.md`; it is historical input,
  not an authoritative current plan.

## Runtime evidence

- Minecraft TCP `localhost:25565`: reachable.
- Bot bridge: `status=ok`, `mode=minecraft`, `connected=true`, user `BenchBot`.
- Letta health: `status=ok`, server `0.16.8`.
- Letta live MemoryBackend probe: add/retrieve PASS, update PASS, reset PASS.
- Docker Desktop processes are running, but `docker` is absent from A's PATH;
  compose/container-level health is therefore N/A pending C.

## Memory frameworks

| backend | implementation | current evidence | controlled status |
|---|---|---|---|
| none | registered | unit + classic logs | available baseline |
| vector | registered, local SQLite | unit + classic logs | available |
| mem0 | registered, local Qdrant | unit + classic logs | available; internal LLM/embedding cost not audited |
| letta | registered, Docker server + Ollama embedding | live probe + classic logs | provisional PASS as archival-memory-only Controlled Mode |
| graphiti | registered, embedded Kuzu | fake-boundary tests + 18 MB local store; no retained raw live probe log | Controlled Mode N/A claim is plausible but evidence chain is incomplete |

No `framework_registry.yaml` exists. Native Mode is not implemented and must
not be mixed into this round.

## Scenarios

- Classic: `delayed_recall`, `world_update`, `failure_learning`.
- Stress code: parameterized delayed recall, update chains,
  `memory_noise_stress`, and `failure_transfer`.
- Cross-session persistence: missing.
- `failure_learning` is a same-task retry plus a scout location debrief; it is
  not valid evidence of cross-task failure transfer.
- `failure_transfer` fabricates a missing-tool `TASK_FAILED` event and an exact
  tool-requirement fact without an observed failed action/cause. It must not
  enter a formal campaign in its current form.

## Real data audit

- 143 parseable scenario JSON logs; zero duplicate episode ids/run ids and zero
  parse failures.
- Classic root: 120 logs = 3 scenarios × 4 backends × seeds 42–51.
  `vector`, `mem0`, and `letta` are 10/10 in every scenario; `none` is 0/10.
  This is a ceiling effect, not a framework ranking.
- Pilot: 8 mixed logs plus 9 Letta smoke logs (the smoke repeats seed 42).
- Stress: only 6 `none/delayed_recall` logs: three at `(50,5)` and three at
  `(200,20)`, all seed 42, all failures. There is no vector/mem0/letta stress
  evidence and therefore no measured failure point.
- 137/143 logs predate fairness records. The six stress logs have valid
  fairness records and probes, but their repeated seed prevents independent
  within-cell evidence.

## Current N/A

- Formal stress curves and failure points: N/A.
- Cross-session persistence: N/A.
- Memory-internal tokens/calls/cost: N/A for all framework comparisons.
- Graphiti Controlled Mode: N/A, with incomplete retained raw evidence.
- Framework registry/version matrix: missing.
- Docker compose-level status in A's shell: N/A.

## Research-critical findings

### Critical — transfer scenario writes the cause and solution

`failure_transfer.py:145-179` writes `TASK_FAILED(reason=missing_tool)` and
`requires_tool=iron_pickaxe` regardless of observed environment feedback. Any
later preparation cannot be attributed to learned failure experience.

### High — retrieval metrics are measured on a second retrieval

The runner logs only `retrieved_memory_count`; delayed/world/noise evaluation
then calls `retrieve()` again. The saved probe is not necessarily the retrieval
that caused the planner action. This breaks causal interpretation of recall,
precision, and stale-memory metrics.

### High — backend serialization is confounded with retrieval quality

Metrics inspect structured event context. Letta historically reconstructs text
only, producing false zero/N/A even when the correct event id was retrieved.
Ground truth must use stable event ids, and the adapter should reconstruct the
same ExperienceEvent without a process-local side channel.

### High — stress repetitions are pseudo-replicates

The committed CLI reuses the same seed for `--runs N`; existing stress smoke
therefore repeats seed 42. A partial uncommitted fix uses `base + run_index`
but is not tested or approved.

### High — reproducibility/cost record is incomplete

Logs omit Git SHA, framework version/config and memory-internal cost. The
reporter lacks median/std/CI and stress grouping. These remain backlog after
the first discriminative smoke; no framework ranking may use current cost data.

## Decision

Do not add another framework. Do not run a formal matrix. The next single
research objective is:

> Determine whether controlled `delayed_recall` at a pre-registered similar-
> distractor stress point produces an interpretable behavioral/retrieval
> difference among none/vector/mem0/letta, using the exact retrieval that
> caused each action and three independent paired seeds.

