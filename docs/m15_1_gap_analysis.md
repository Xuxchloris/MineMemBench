# M15.1 Difficulty and Dashboard Gap Analysis

Status: Phase A audit retained as historical design evidence. The identified
M15.1 producer/Dashboard gaps are closed and A/C final review passes; a clean
freeze remains separately gated. This document is not experiment
authorization. The immutable M15 stable baseline is
commit `9fdced8fa9967a6df7b856b035485b41e84c06dc` with source fingerprint
`8606370026c2bde49737ccb945c9b69ed4aa9cb64090aa06df6cb7c23e24e55f`.

Post-implementation A correction (2026-08-09): the first implementation used
`observed_precondition_multi_v3`, where all source failures shared the same
gold-nugget prerequisite. Re-reading the authoritative objective showed that
mere multiplicity did not close the applicability-discrimination gap. V3 is
therefore retained only as readable diagnostic history and superseded for new
runs by heterogeneous `observed_precondition_applicability_v4`.

Final A correction (2026-08-09): raw replay then exposed post-terminal
wait/attack steps in both new scenarios. An optional backend-neutral RunStep
terminal predicate now stops only after recorded completed delivery/target
attack and is isolated from prompt, memory and action selection. The first v4
campaign is superseded; the terminal-corrected replacement passes C data QA.

## 1. Audit scope

The audit covered the benchmark protocol and plans, scenario engine, runner,
planner, MemoryBackend contract and adapters, fairness/provenance gates,
Controlled campaign lifecycle, report loader, TypeScript mock fixture, current
tests, and representative accepted raw result/manifest/log layouts for:

- `delayed_recall / entity_key_v2`
- `world_update / temporal_chain_v2`
- `memory_noise_stress / key_retention_v2`
- `failure_learning / observed_precondition_v2`

The accepted result tree currently contains historical manifests with no
schema marker, `controlled-campaign/v2`, and `controlled-campaign/v3`. The
current producer writes `controlled-campaign/v4`. A consumer must tolerate all
four shapes without rewriting any evidence.

## 2. What is already methodologically sound

### Memory isolation and controlled variables

- Planner/scenario/runner code depends on the injected `MemoryBackend`
  interface and does not branch on backend names.
- Planner-visible memory is a backend-neutral semantic projection. Scores,
  item ids, event ids, metadata and backend internals never enter the prompt.
- Controlled runs receive deterministic scenario events, a fresh versioned
  mock fixture per run, paired seeds, counterbalanced backend order, the same
  planner model/temperature/prompt/tools, and a post-run reset/leak audit.
- `EventRecordingBackend` retains the complete offered event stream even for
  `none`, enabling input-stream equality checks.
- Source provenance and git state are recorded separately. A source
  fingerprint is not treated as a substitute for a clean reviewed commit.

### Existing pressure axes

- `memory_noise_stress / key_retention_v2` varies volume with independently
  generated neutral noise and stable target identity. It does not manufacture
  false target facts.
- `delayed_recall / entity_key_v2` varies semantic similarity using distinct
  entity keys, not wrong statements about the target.
- `world_update / temporal_chain_v2` records facts that were true at their
  event times and later superseded. Current/stale endpoints use causal step-0
  retrieval evidence.
- `failure_learning / observed_precondition_v2` derives its only failure fact
  from a real failed `ActionResult`, transfers to a different hostile, and
  requires preparation before the first transfer attack for primary success.
- `failure_transfer` is correctly unregistered and suspended because it
  authors both a missing-tool cause and solution that the environment did not
  reveal.

## 3. Difficulty gaps

### Critical gap: no lifetime treatment

There is no scenario that keeps one long-term episode scope alive across
multiple semantic sessions while clearing the runner's working transcript at
each boundary. Existing scenarios contain only one short interference window
and generally a three-step final run.

Required closure:

- Add `long_lived_memory / lifetime_v1` with configurable
  `lifetime_event_count`, `session_count`, `relevant_update_count`, and
  `similar_event_count`.
- Use separate `AgentRunner.run_goal` calls with one shared `episode_id`.
  This resets the local transcript by construction while preserving the
  backend's long-term scope.
- Derive the key route fact from a real WorldState/ActionResult observation.
  Do not copy out-of-band evaluation coordinates into the goal, query, or an
  unobserved authored event.
- Make the final task a meaningful multi-action route (locate, collect,
  return, deliver), not a padded `max_steps` loop.
- Preserve every semantic-session and final-task run log so transcript reset,
  retrieval, decisions and outcomes are independently replayable.

### High gap: no discrimination among multiple plausible real failures

`observed_precondition_v2` is causally valid but observes one relevant failure.
Repeating the same environmental rule on several entities would still leave a
single answer and cannot test whether memory distinguishes applicable from
surface-similar but inapplicable real failure experiences.

Required closure:

- Add a separate versioned treatment (do not alter v2 semantics) with 2–3
  genuine source failures from different prerequisite/resource families and
  a distinct transfer hostile.
- Every source event must be derived from its own failed `ActionResult`; the
  environment error remains the only source of each required-item fact.
- Exactly one source family must apply to the transfer while 1–2 plausible
  source failures require different resources. Preserve all ActionResults and
  an evaluation-only relevant/irrelevant id partition.
- Record relevant recall/rank and irrelevant-failure retrieval separately;
  ambient interference cannot substitute for irrelevant real failures.
- Retain the strict endpoint: correct preparation must precede the first
  transfer attack. Eventual recovery after an attack-first failure remains a
  separate secondary endpoint.

### High gap: short behavior horizon

Current successful tasks can often be solved by one navigation or a two-step
equip/attack sequence. Increasing `max_steps` alone would add opportunity, not
difficulty.

Required closure:

- The lifetime final task must require at least four causally ordered actions
  in the fixture: navigate to an initially out-of-range item, collect it,
  return to the recipient, and deliver it.
- Behavioral success is derived from completed real actions in order. Merely
  reaching a coordinate, issuing an intended action, or recovering after an
  invalid first attempt is insufficient.

## 4. Observability and raw-schema gaps

### Existing evidence that can be reused

Each `RunStep` already preserves:

- pre-action raw `WorldState`
- exact retrieved memory snapshots and order
- planner action, arguments and stated reason
- environment status, error and result
- post-action position
- prompt/completion tokens and LLM decision latency

Each `ScenarioResult` already preserves effective params, fairness/provenance,
diagnostic retrieval probes, complete injected events, typed out-of-band
ground truth, and scenario-observed ActionResults.

This is sufficient for deterministic replay of existing single-run scenarios,
2D trajectory reconstruction, retrieval inspection, planner-decision display,
outcome display, and most same-seed fairness comparisons.

### Minimal backward-compatible schema extension is justified

`ScenarioContext.records` is currently never serialized, and
`ScenarioResult.run_log` can hold only one of several session runs. Encoding
session logs inside `metrics` would be untyped and would make replay
scenario-specific.

Add two optional, default-empty fields to `ScenarioResult`:

- `phase_records`: the existing backend-neutral `PhaseRecord` values.
- `run_logs`: typed records associating a `RunLog` with a phase/session label.

Keep the existing `run_log` as the primary/headline run for complete backward
compatibility. Historical JSON must continue to validate unchanged. No wire
protocol change is needed.

### Attribution limits

Retrieval, planner decision and embodied outcome are directly observed.
Memory utilization is not directly logged and must not be inferred from an
LLM-written reason alone. Replay must report utilization as `unknown` unless a
scenario-specific deterministic rule ties a retrieved ground-truth event to a
subsequent objectively matching action. The dashboard must display the rule
and evidence ids when utilization is supported.

### Latency limits

Per-step `latency_s` is LLM decision latency, not end-to-end or memory-only
latency. Retrieval probes contain direct retrieval latency; backend stats
contain aggregate add/retrieve latency. Replay and dashboard must label these
separately and show N/A when the requested latency was not measured. No value
may be reconstructed by subtraction.

## 5. Dashboard gaps and constraints

There is no interactive observability service. The current report command
writes aggregate CSV/Markdown/PNG and scans only one directory level for
`scenario_*.json`.

Required closure:

- Build a read-only recursive result index with mtime/size caching.
- Treat raw JSON as the source of truth. Never migrate, normalize in place,
  delete, retry or repair producer evidence.
- Tolerate a manifest/result while it is being rewritten. Retain a cached
  last-good parse and mark the current file partial/stale instead of crashing.
- Expose only validated/sanitized result and manifest fields. Do not serve
  arbitrary filesystem paths, environment variables, `.env`, headers, API
  keys, backend stores, raw databases or unrestricted stdout/stderr content.
- Keep producer isolation one-way: dashboard imports replay/index models;
  runner, planner, scenarios and memory backends must never import dashboard
  modules. Dashboard failure cannot affect campaign execution.
- Use a minimal local-only HTTP server and static assets. No new web framework
  dependency is required for the MVP.

## 6. Same-seed comparison validity

A comparison cell is valid only when scenario, effective params, seed,
campaign mode, planner model, temperature, system prompt hash, tool-set hash,
planner user-template hash, world identity, Minecraft version, fixture selector
and identity, and producer source identity agree. Native world identity is the
measured world seed. Controlled Mode has no Minecraft seed, so equal non-empty
versioned fixture selector+identity make null world seed explicit N/A. Backend
and episode/run ids are expected to differ. Any incomplete historical fixture
identity or other missing field is `unknown`, not equal. An invalid or
incomplete fairness record must be visibly flagged and excluded from a valid
comparison claim.

The default backend display order is `none`, `vector`, `mem0`, `letta`.
Missing cells and unmeasured values render as N/A.

## 7. Calibration evidence gap

The accepted 0/10/50 diagnostic cells show the current noise boundary but do
not authorize extrapolating directly to 100/200/500/1000. After implementation
and independent QA, calibration is limited to three paired seeds per cell.
Candidate volume cells near the observed bracket are 10/20/30/40/50/60,
subject to the new source/result audit. Calibration identifies ceiling,
discrimination and failure regions; it does not rank backends.

## 8. Documentation drift

`README.md`, `docs/development_plan.md`, and `docs/agents/HANDOFF.md` still
contain pre-freeze statements that the TASK-025 tree is dirty or awaits an
external freeze. They must be corrected in the design/documentation phase to
name the immutable baseline commit and distinguish it from the future M15.1
freeze. Historical review records remain unchanged.

## 9. Phase A gate decision

Proceed to Phase B design. No protocol change, backend-specific planner or
scenario branch, formal campaign, old-result rewrite, or revival of
`failure_transfer` is justified. The only raw-result schema changes permitted
by this audit are the optional typed multi-run/phase fields described above.
