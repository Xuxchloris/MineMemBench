# B-COMPLETION-016 — TASK-016 memory-noise semantics v2 and causal Controlled core complete

Date: 2026-08-08
Author: Agent B (main developer)
Task: `docs/agents/tasks/TASK-016.md` (frozen by Agent A)
Status: **COMPLETE — awaiting C independent QA. NOT an A approval; no
campaign was or may be run.**

Explicit confirmation: no campaign executed, no process spawned, nothing
written under `results/`, no service/Docker/LLM/network contact, no git
operation (no add/commit/push), no `.env` access, `docs/protocol.md`
untouched. All pre-existing dirty-worktree changes (TASK-002..015) preserved;
only the files listed below were touched. No backend-name branching was
added anywhere in planner/scenario/runner code.

## Files changed (TASK-016 only)

- `benchmark/minemembench/scenarios/memory_noise_stress.py` — the v2
  treatment. New `noise_semantics_version` param (`legacy` default,
  unchanged legacy/native behavior; `key_retention_v2` the only
  Controlled-approved value). `noise_count` int >= 0 unchanged (ladder
  0..1000 not hard-coded, no campaign run). v2 additions:
  - `target_entity_key(seed)`: opaque fixed-width `cache-<8 hex>` key,
    SHA-256 in the dedicated namespace
    `memory_noise_stress/key_retention_v2/target/<seed>` — derived in
    `setup`, before/independently of `noise_count` and noise generation.
  - v2 goal names the key only: `Return to <key> whose location you learned
    during the initial briefing.` (no coordinates, priority, correctness,
    retrieval hint, or backend detail).
  - Target event: neutral `scenario-instructor` / `LOCATION_DISCOVERED`,
    context exactly `{entity_key, x, y, z}`.
  - `noise_entity_keys` / `noise_positions`: exactly `noise_count`
    simultaneously-true noise events sharing the target's actor/type/context
    key set, differing only in an independently derived key (rejection loop
    guarantees no one-character near-miss of the target key — this axis is
    volume, not lexical similarity) and a unique seeded coordinate (wide
    ±512 stream from `random.Random(seed + 1)`; the legacy 8–20 offset space
    cannot supply 1000 unique positions). Both generators are
    count-independent: cells N and M share the same first N keys/coordinates
    for N < M. No target/noise/relevant/irrelevant/correct/wrong/priority/
    current/stale labels anywhere prompt-visible.
  - Controlled mode: event ids/logical timestamps via
    `controlled_event_identity(seed, full effective params, phase, ordinal)`;
    native keeps uuid4/wall-clock. `setup` fails closed for Controlled
    legacy before any bot/LLM/backend side effect (defense in depth behind
    the central policy).
  - `compute_key_retention_metrics`: headline v2 metrics computed ONLY from
    `run_log.steps[0].retrieved_items` + typed ground truth —
    `target_retrieval_rank` (1-based, None if absent), `target_recall`
    (empty = measured 0), `target_retrieval_precision` (None on empty),
    `noise_retrieval_rate` (None on empty), `target_top1` (1 target / 0
    known noise / None otherwise), `retrieved_item_count`.
  - Legacy compatibility documented in-code: the subject-parsing legacy keys
    `relevant_memory_precision` / `irrelevant_retrieval_rate` are
    semantically invalid for v2 and stay None (N/A) — no compatibility
    mirror redefines them. Behavioral/cost metrics still logged from the
    real run (`task_success`, token counts, `llm_calls`, add/retrieve and
    end-to-end latency; no latency normalization claimed). The
    evaluation-time probe remains as `evaluate-diagnostic` raw evidence and
    feeds no metric. Legacy evaluate path (probe + subject parsing) is
    byte-for-byte the old code.
- `benchmark/minemembench/scenarios/base.py` — new
  `KeyRetentionGroundTruth` (`semantics_version: Literal["key_retention_v2"]`,
  `target_event_id`, `target_entity_key`, ordered `noise_event_ids`),
  added to the `EvaluationGroundTruth` discriminated union. Serialized shape
  of the existing members unchanged; the field stays optional (default
  None), so pre-v2 result JSON validates unchanged. Evaluation-only: never
  enters prompts, queries, or stored events.
- `benchmark/minemembench/cli.py` — the single central Controlled policy:
  `CONTROLLED_VERSION_PARAM` gains
  `memory_noise_stress: noise_semantics_version`;
  `CONTROLLED_APPROVED_VERSIONS` gains
  `memory_noise_stress: frozenset({"key_retention_v2"})`. Missing/legacy/
  unknown versions are rejected before bot, LLM, backend, output, or process
  construction (existing gate placement unchanged).
- `scripts/run_controlled_campaign.py` — preflight generalized: the
  world-update explicit-version requirement is now a scenario-keyed mapping
  also covering `memory_noise_stress` (cells must explicitly request
  `noise_semantics_version=key_retention_v2` in the REQUESTED params).
  `--scenario` choices derive from the policy map, so the scenario is
  accepted with no further runner changes; semantic duplicate-cell
  rejection, pre-registration, counterbalancing, campaign-local stores,
  strict result/fairness validation, stop-on-first-failure, and late-bound
  test dependencies are untouched.
- `benchmark/tests/test_memory_noise_v2.py` — NEW, 18 hermetic
  falsification tests (mapping below).
- `benchmark/tests/test_controlled_mode.py` — policy tests updated to the
  four approved combinations (memory-noise legacy/missing/bogus now rejected
  via the version message, not "not approved"); `_cells` gains a
  memory-noise branch; the schedule-identity uniqueness loop now covers all
  three scenarios; +6 TASK-016 campaign tests (`test_q16_*`).
- `benchmark/tests/test_memory_noise_stress.py` — one assertion updated:
  legacy effective params now include the explicit default
  `noise_semantics_version: "legacy"` (same convention as TASK-011/013).
- `docs/agents/reviews/B-COMPLETION-016.md` — this report.

## Required-falsification mapping (TASK-016 §"Required falsification tests")

1. **Legacy defaults / native compatibility** —
   `test_legacy_defaults_and_native_behavior_unchanged` (default params,
   legacy goal/metrics/probe phase, no v2 keys, ground truth None),
   `test_old_result_json_without_v2_fields_still_loads`, plus the
   pre-existing legacy suite `test_memory_noise_stress.py` (green with one
   params-dict assertion update).
2. **Invalid params/version + Controlled legacy fail closed** —
   `test_invalid_params_and_versions_fail_closed`,
   `test_controlled_legacy_fails_closed_before_side_effects` (zero offered
   events, zero bot actions, zero LLM calls),
   `test_q1_policy_rejects_unapproved_combinations`,
   `test_q1_cli_gate_fails_before_any_bot_or_backend` (exit 2, nothing
   constructed).
3. **Target identity independent of noise_count** —
   `test_target_key_is_deterministic_fixed_width_and_seed_dependent`,
   `test_target_identity_independent_of_noise_count` (cells 0/10/1000 share
   the target key, location, actor, type).
4. **Prefix stability + uniqueness at 0 and 1000** —
   `test_noise_prefix_stability_and_uniqueness` (first-10 of the 1000-cell
   equals the 10-cell; 1001 unique keys and coordinates; empty cell has no
   noise ids),
   `test_noise_key_generator_prefix_stability_and_near_miss_rejection`.
5. **Cross-backend stream equality** —
   `test_controlled_v2_streams_identical_across_backends` (NoMemory vs
   Vector, seeds 42/43/44, identical semantic streams after only episode
   normalization, `ctrl-` ids),
   `test_native_v2_keeps_uuid_event_ids`.
6. **No banned labels / no leakage** —
   `test_no_banned_labels_or_ground_truth_leakage` (context schema exactly
   `{entity_key,x,y,z}`, no banned tokens in actor/type/context/goal, goal
   names the key but no coordinates, prompt memory views carry no
   bookkeeping fields, no injected event id appears in any planner message).
7. **Exact v2 metric math** — `test_metric_math_empty_retrieval`,
   `test_metric_math_target_rank1_with_noise`,
   `test_metric_math_target_below_rank1`,
   `test_metric_math_target_absent_and_unknown_top`,
   `test_metrics_come_from_causal_snapshot_not_probe` (FlipFlopBackend:
   probe empty, metrics still describe the causal step-0 snapshot).
8. **Typed ground truth serialization / old JSON loading** —
   `test_ground_truth_serialization_and_metric_rederivation` (JSON
   round-trip, ids match the offered stream, every v2 metric re-derives
   exactly from the restored snapshot; NoMemory empty-retrieval case),
   `test_ground_truth_is_a_discriminated_union_member`,
   `test_old_result_json_without_v2_fields_still_loads`.
9. **Campaign preflight/manifest/validation** —
   `test_q16_preflight_accepts_memory_noise_v2_cells` (requested
   byte-for-byte, effective params, manifest identity),
   `test_q16_preflight_rejects_memory_noise_without_explicit_v2` (missing/
   legacy/mixed versions, semantic duplicates, invalid difficulty — all
   exit 2, output path never created),
   `test_q16_memory_noise_schedule_preserves_invariants`,
   `test_q16_memory_noise_lifecycle_and_result_validation` (valid result
   passes; params mismatch and fairness-invalid fail closed and stop),
   `test_q16_controlled_memory_noise_v2_cli_path` (hermetic end-to-end CLI:
   fairness/fixture/params, 11 `ctrl-` events, typed ground truth, causal
   evidence source), plus the extended
   `test_q4_schedule_run_identities_are_unique`.
10. **Hermeticity** — all new tests use fakes/tmp_path only
    (`FakeBotClient`, `SmartFakeLLM`, `NoMemoryBackend`, tmp-path Vector,
    `FlipFlopBackend`, monkeypatched campaign helpers); no network, no real
    subprocess, no LLM API, no `results/` dependency.

## Exact test output

- Focused:
  `.venv\Scripts\python -m pytest -q benchmark/tests/test_memory_noise_v2.py
  benchmark/tests/test_memory_noise_stress.py
  benchmark/tests/test_controlled_mode.py` → **79 passed in 9.83s**
  (`test_memory_noise_v2.py` alone: **18 passed in 3.10s**).
- Full: `.venv\Scripts\python -m pytest -q` → **332 passed in 87.07s**
  (309 accepted baseline + 23 net new).
- TypeScript: N/A — `minecraft/` untouched.

## Deviations / open issues

- **Controlled event ids hash the full effective params** (per the frozen
  spec, mirroring delayed-recall v2), so `ctrl-` event ids/timestamps differ
  across noise-count cells; cross-cell prefix stability is therefore
  specified and tested on the semantic event content (actor/type/context =
  key + coordinates), which is what backends retrieve on. The target KEY and
  target/noise keys+coordinates are fully `noise_count`-independent.
- **Noise coordinate space widened**: v2 noise offsets draw from ±512 blocks
  (`random.Random(seed + 1)` stream) because the legacy 8–20 offset space
  (676 positions) cannot supply 1000 unique coordinates. Legacy behavior is
  untouched.
- **No compatibility mirrors added in v2**: the legacy retrieval-semantics
  keys (`relevant_memory_precision`, `irrelevant_retrieval_rate`) are
  subject-parsing metrics that are semantically invalid for v2 and stay N/A,
  as the task permits; this choice is documented in the module docstring and
  pinned by tests.
- README/`docs/stress_design.md` still describe only the legacy
  memory-noise metrics; per HANDOFF §7 the documentation-drift repair is a
  separate later task and was deliberately not done here.
- No campaign run, no research conclusion, no framework claim. A release is
  required before C executes any memory-noise campaign.

Stopping for C independent verification; no A approval claimed.
