# TASK-027 Attempt 2 — Formal Analysis Erratum

Date: 2026-08-11 (Asia/Shanghai)

## Status before correction

- Formal study: `m15-formal-v1-controlled-20260811-attempt2`.
- Producer commit: `64c822faf2ae8e490b3da11ed86261566bd93256`.
- Producer source fingerprint: `ebfe9172dbe83abb5d76c2f8459ef346b8888d4f8e2bafca4d09799566bad3b3`.
- Producer completed 320/320 planned runs with zero retries and zero exclusions.
- Independent integrity checks passed before analysis.
- The first frozen-analyzer invocation stopped before writing any analysis output with `target event has no auditable location`.

## Root cause

The three Controlled v2 location scenarios use their documented neutral event
schema: the target and competing facts store coordinates in
`ExperienceEvent.context` as `x`, `y`, and `z`. The optional top-level
`ExperienceEvent.location` field is intentionally unset. The frozen synthetic
analysis fixture incorrectly populated `location`, so the frozen analyzer's
`_target_position` helper accepted the synthetic fixture but rejected real
Formal evidence.

The raw Formal evidence is complete: target identity is selected by the typed
out-of-band `evaluation_ground_truth` event id, and that exact injected event
contains finite `context.x/y/z` coordinates. This is an analyzer/schema
compatibility defect, not missing or reconstructed research data.

## Authorized correction

Before any successful aggregate Formal analysis or generated result report, the
project owner explicitly chose to retain the completed Attempt 2 dataset and
authorized the minimal analysis correction. No Formal run will be retried,
replaced, deleted, or regenerated.

The correction is limited to:

1. Select the target event only through the existing typed ground-truth event id.
2. Read its position from the scenario's actual frozen neutral schema,
   `context.x/y/z`.
3. Require all three coordinates to be numeric and finite.
4. If an optional top-level `location` also exists, fail closed unless it
   exactly agrees with the typed context.
5. Replace the synthetic analysis fixture with the real event shape and add a
   contradictory-field regression test.

Unchanged: study id, producer identity, 320-run matrix, backends, scenarios,
treatments, parameters, paired seeds, primary endpoint, failure-attribution
rules, exact McNemar tests, paired risk difference, bootstrap seed/resamples,
Holm family, and Failure Point rule.

## Disclosure

Generated analysis artifacts and final research documentation must disclose
this erratum and must not describe the corrected analyzer as the original
preregistered implementation. The final Git commit and source fingerprint bind
the exact corrected implementation used for publication.

Attempt 1 and its DNS failure remain preserved historical evidence. It is not
resumed or pooled. Attempt 2 remains the sole Formal V1 analysis dataset.
