# Stress Layer Design Note (M15B)

The Phase-1 scenarios (A/B/C) saturate: at their default difficulty every
backend under test (`none`, `vector`, `mem0`, `letta`) scores near 100%, which
is a ceiling effect, not a signal. The stress layer answers the research
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

## world_update: update chains and raw retrieval logging

`update_depth=d` chains `d` location updates (A→B→C→…), with the final location
the current answer and every earlier location a stale fact. Each location is
drawn from its own seeded RNG (`seed + 100*k`), so a deeper chain never perturbs
a shallower one. **M15B requires the raw retrieved items of every retrieval
probe to be preserved**: the scenario records each probe's full raw items into
`ScenarioResult.retrieval_probes`, so a reviewer can re-derive the retrieval
metrics from the log without re-running.

## memory_noise_stress

One key memory, then N unrelated `ExperienceEvent`s. As N grows, only a real
retrieval signal keeps the key memory ahead. Metrics: `task_success`,
`relevant_memory_precision`, `irrelevant_retrieval_rate`, `retrieval_latency`,
`token_cost`, `end_to_end_latency`. The noise facts reuse Scenario A's
stopword-free pool, so the crude hash embedder scores them zero — the stress is
meaningful only for real embedders, which is the point.

## failure_transfer: no hard-coded adaptation

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

## Fairness audit and the episode-leakage probe

`core/fairness.py` records every run's controlled variables: Minecraft version,
world seed, planner model, temperature, SHA-256 of the system prompt, SHA-256 of
the action/tool set, and the scenario name + parameter dict. Between consecutive
runs it also runs an episode-leakage probe: the next run's planner retrieves
memories scoped to its own `episode_id`, so the previous episode's memories must
never surface under that scope. The probe asks exactly that question with a
query drawn from the previous run's goal; if previous-episode memories come
back, the run is marked `valid=False` in its log.

## Reporting

New stress metrics are stored per-run in the `scenario_*.json` logs (raw and
verifiable). The M11 aggregator/report keeps aggregating the classic
cross-scenario metrics so existing report tests and column layout are stable;
stress analysis reads the per-run logs (grouped by scenario + parameter level).
