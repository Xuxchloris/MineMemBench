# Stress Layer Design Note (M15B)

> Current status (2026-08-08): versioned Controlled implementations are
> complete and bounded diagnostic cells have been audited. No formal sample,
> framework ranking or Failure Point is approved. `docs/experiment_standard.md`
> and `docs/development_plan.md` are the execution/status authorities.

The Phase-1 scenarios (A/B/C) produced ceiling effects among several
memory-backed treatments at their default difficulty, which hides framework
differences. The NoMemory baseline is not assumed to share that ceiling. The
stress layer answers the research
question: *as experience accumulates, similar facts multiply, and the world
keeps changing, where does each memory framework start to fail?*

This note records the design decisions so the layer stays methodologically
sound. The wire contract (`docs/protocol.md`) is unchanged.

## Difficulty from the CLI, recorded into every log

Difficulty is a per-run *parameter*, not new code:

```bash
python -m minemembench run --scenario delayed_recall --memory vector \
  --scenario-param interference_count=200 --scenario-param similar_distractor_count=20 \
  --runs 30
```

- `--scenario-param KEY=VALUE` is repeatable; values coerce to bool/int/float
  and otherwise stay strings. Unknown keys and out-of-range values are rejected
  (`ScenarioParamError`) before any bot connection, so a typo never wastes a
  run.
- Each scenario declares `default_params`; `apply_params()` merges overrides.
  **Defaults reproduce the Phase-1 behavior exactly** (10 noise facts, 0
  distractors; `update_depth=1`; the new scenarios default to their ceiling
  control level). The 120-run matrix is therefore untouched.
- `ScenarioResult.params` carries the *effective* (defaults + overrides) dict,
  and the fairness record repeats it, so a run's difficulty is auditable from
  its log alone.

## Why the metrics are retrieval-side, not just task-side

`task_success` measures navigation to a remembered coordinate; it is the
behavioral headline. But with similar distractors the agent can be *misled* (it
reaches a lookalike location) while the correct fact is still retrievable. So
the stress scenarios add retrieval-side metrics computed from the same real
`retrieve()` result used by the planner:

- `delayed_recall`: `recall_accuracy` (is the correct fact present among
  retrieved items), `wrong_fact_rate` (fraction of retrieved items that are
  wrong facts about the target), `retrieval_precision` (fraction of retrieved
  items that concern the target at all).
- `world_update`: `stale_memory_rate` (of the retrieved cache facts, how many
  are at a stale location), `obsolete_fact_retrieval_rate` (of all retrieved
  items, how many are obsolete cache facts), plus the existing
  `current_fact_accuracy`.

All new metrics are computed from real run data; anything unmeasured stays
`None` and renders as `N/A`.

## delayed_recall semantics v2 (`recall_semantics_version=entity_key_v2`, TASK-011)

Rounds 3–4 showed the legacy treatment is not semantically valid: identical
later facts about the *same* `target_chest` contradict the hidden "earliest
location is correct" oracle. The v2 treatment replaces it with an explicit
**entity-key-to-location lookup**:

- The goal names one opaque seeded key (e.g. `cache-7f3a9c2e`) and no
  coordinates: "Return to cache-… whose location you learned during the
  initial briefing." The key is derived from the seed in a dedicated
  namespace, before and independently of distractor generation.
- The learned fact maps that key to the target location; each of the N
  similar distractors maps a UNIQUE one-character mutation of the key to its
  OWN unique location. All facts are simultaneously true; correctness is the
  key association, never timestamp, insertion order, or update semantics.
- Every candidate shares one neutral actor / event type / context schema
  (`{"entity_key", "x", "y", "z"}`); no correctness/staleness labels.
- v2 metrics: `fact_retrieval_rank`, `target_recall` (empty retrieval = 0),
  `target_retrieval_precision`, `off_target_retrieval_rate` (N/A on empty).
  Legacy keys remain for schema compatibility: `recall_accuracy` mirrors
  `target_recall`; `wrong_fact_rate` and legacy `retrieval_precision` are
  **N/A** — true off-target entities are never called wrong.
- The typed out-of-band oracle (`ScenarioResult.evaluation_ground_truth`:
  semantics version, target event id/key, ordered distractor ids) lets any
  reviewer re-derive every v2 metric from the result JSON plus the causal
  step-0 retrieval snapshot; it never enters the prompt, memory, or query.

`legacy` stays the default: its goal text, event semantics, metrics, and
Controlled event-identity derivation (the two pre-existing difficulty params)
are unchanged, and old result JSON stays loadable; newly serialized legacy
results additionally carry the explicit version in `params` and the optional
ground-truth field as `null`, so the whole result JSON is not claimed
byte-for-byte identical. v2 results must never be pooled with legacy rounds
1–4 (different treatment). One v2 `(200,20)` smoke is accepted in
`A-FINAL-012`; any additional v2 cell or formal expansion remains gated on an
immutable reviewed revision and a separate A-issued task.

## world_update: update chains and raw retrieval logging

`update_depth=d` chains `d` location updates (A→B→C→…), with the final location
the current answer and every earlier location a stale fact. Each location is
drawn from its own seeded RNG (`seed + 100*k`), so a deeper chain never perturbs
a shallower one. **M15B requires the raw retrieved items of every retrieval
probe to be preserved**: the scenario records each probe's full raw items into
`ScenarioResult.retrieval_probes`, so a reviewer can re-derive the retrieval
metrics from the log without re-running.

### world_update semantics v2 (`update_semantics_version=temporal_chain_v2`, TASK-013)

Legacy world-update mixes actor/type schemas (`RESOURCE_DISCOVERED` vs
`WORLD_FACT_UPDATED` + `moved: True`) and computes retrieval metrics from a
second evaluation-time probe. The v2 treatment makes the temporal chain
explicit and causally measurable:

- Every chain candidate (A..D) shares actor `scenario-instructor`, event type
  `WORLD_FACT_UPDATED`, and context schema
  `{"subject": "supply_cache", "x", "y", "z"}` — no `moved` flags, update
  indices, or initial/current/stale/latest labels. All facts are true at
  their event time; the unique maximum semantic timestamp defines the current
  location D. The v2 goal is static and coordinate-free: "Retrieve the supply
  cache at its current location."
- Controlled mode **fails closed** for any other semantics version — a
  legacy Controlled world-update run is research-invalid and cannot be
  produced. In Controlled v2, chain and noise events use
  `controlled_event_identity` with the full effective params, so offered
  streams are identical across backends except `episode_id`.
- v2 headline metrics are computed from the typed out-of-band
  `evaluation_ground_truth` (ordered `stale_event_ids` A/B/C +
  `current_event_id` D, a discriminated-union member on `semantics_version`)
  plus the causal `run_log.steps[0].retrieved_items` snapshot:
  `current_fact_retrieval_rank`, `current_fact_recall` (empty = 0),
  `current_fact_retrieval_precision`, `stale_fact_retrieval_rate`,
  `current_fact_top1`, `stale_memory_rate`. `current_fact_accuracy` and
  `obsolete_fact_retrieval_rate` survive only as compatibility mirrors of
  `current_fact_top1` and `stale_fact_retrieval_rate`. The evaluation-time
  probe (v2 goal as query) is diagnostic raw evidence and feeds no metric.
- Legacy (default) keeps its goal, events, probe-based metrics, and result
  shape unchanged; old result JSON loads with `evaluation_ground_truth=None`.
  v2 results must never be pooled with legacy world-update runs.

The depth-3 v2 treatment (A→B→C→D) completed one 4-backend × 3-seed Controlled
diagnostic and was accepted in `A-FINAL-015`. Depths 1/2/4 remain unexecuted in
Controlled v2 and require a separate A task after the immutable-revision gate.
The depth-3 result is diagnostic only: current D was retrieved by every memory
run, so recall has a ceiling while executed behavior still varies.

## memory_noise_stress

One key memory, then N unrelated `ExperienceEvent`s. Legacy remains Native
compatibility only. Controlled uses
`noise_semantics_version=key_retention_v2`: a stable typed target identity,
prefix-stable noise identities/coordinates, deterministic event time and causal
step-0 retrieval metrics (`target_retrieval_rank`, `target_recall`,
`target_retrieval_precision`, `noise_retrieval_rate`, `target_top1`). The
ground truth is out-of-band and never planner-visible.

Counts 0/10/50 completed paired 4-backend × 3-seed diagnostics. Installed
Mem0/Letta configurations retained the target at count 10 and lost it in some
count-50 runs, bracketing target loss in `(10,50]` diagnostically. The ladder
was stopped in `A-FINAL-019`; counts 100/200/500/1000 and a formal Failure Point
are not authorized.

## failure_learning semantics v2: observed failure transfer

`failure_semantics_version=observed_precondition_v2` replaces the invalid
fabricated failure treatment. The warded-hostile fixture first executes an
actual `attack_entity` that must fail. The complete raw `ActionResult` is
preserved, and exactly one factual `TASK_FAILED` event is derived from its
observed status/error/equipped state. The transfer task targets the other
hostile under different wording; scenario code never chooses an action.

Step-0 retrieval metrics use typed source/interference event ids. Ordered
behavior endpoints distinguish retrieval, preparation before the first
transfer attack, repeated failure, transfer completion and eventual recovery.
Counts 0/10/50 completed paired diagnostics and were stopped in
`A-FINAL-023`: all memory runs retained the source failure at rank1/top1 and
prepared gold, while NoMemory repeated the precondition failure. Executed
success contains planner re-equip variance, so the evidence supports the
transfer construct but no backend ranking or retrieval Failure Point.

## failure_transfer: no hard-coded adaptation

> **STATUS (TASK-002 safety gate): SUSPENDED — research-invalid / N/A.** The
> scenario writes the `TASK_FAILED` event and the exact tool-requirement fact
> itself; neither is derived from an observed failed action/cause (A-AUDIT-002
> critical finding). It is removed from the public scenario registry and must
> not enter any formal campaign until redesigned around a real observed
> failure cause. The description below is kept as the design intent only.

Upgrade of Scenario C. The first task fails for a missing tool; the transfer
task differs in map area, goal object, and location but shares the same
missing-tool precondition. The scenario records *facts only* — a `TASK_FAILED`
event and a tool-requirement fact. Nothing tells the planner "if a task failed
before, prepare the tool". Whether the agent equips the required tool on the
transfer task must emerge from Experience → Memory → Retrieve → Planner →
Action, and is measured by `adaptation_success`, `preparation_rate`,
`failure_repetition_rate`, `transfer_success_rate`. Tool gates are virtual
(Phase-1 simplification): a task succeeds only when the run both reached the
goal object's location and equipped the tool, evaluated from the run log.

## Fairness audit and the post-run reset verification

`core/fairness.py` records every run's controlled variables: Minecraft version,
world seed, planner model, temperature, SHA-256 of the system prompt, SHA-256 of
the action/tool set, the scenario name + parameter dict, and the run's
effective seed (`--seed S --runs N` runs seeds `S..S+N-1`, identical for every
backend). After a run's metrics are captured, the checker resets the episode
that ACTUALLY ran, then probes the reset scope and a brand-new scope with a
query drawn from the run's own content. Any reset error, probe error, or
returned item marks the run `valid=False` in its log — the log is still
written, so an invalid cleanup stays auditable. Probed scopes are reset again
best-effort, so the audit leaves no lazily-created scope (e.g. an empty letta
agent) behind. Each run also gets a fresh backend instance, so latency
counters and process-local scope never accumulate across runs.

TASK-024 adds producer provenance to new runs: the v4 campaign manifest
pre-registers a deterministic SHA-256 over an explicit source/test/config/wire
allowlist plus read-only git state, and each fairness record repeats the compact
identity. Any mismatch stops the campaign. `.env`, results, stores, caches,
build output and Minecraft worlds are outside the allowlist. A fingerprint is
not a clean commit; formal execution additionally requires
`--require-clean-source`, external review ownership and a frozen
preregistration.

## Reporting

New stress metrics are stored per-run in the `scenario_*.json` logs (raw and
verifiable). The M11 aggregator/report keeps aggregating the classic
cross-scenario metrics so existing report tests and column layout are stable;
stress analysis reads the per-run logs (grouped by scenario + parameter level).
Formal analysis must be frozen from `docs/preregistration_template.md` before
run 1; current three-seed cells remain diagnostic.
