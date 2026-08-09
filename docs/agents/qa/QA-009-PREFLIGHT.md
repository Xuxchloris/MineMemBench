# QA-009-PREFLIGHT — Temporal-semantic audit of round-3 raw retrievals

Date: 2026-08-08
QA: Agent C (independent evidence verification; no production-code/results/
protocol change, no campaign, no git)
Task: TASK-009 is being implemented by B; this records what the pre-fix round-3
raw retrievals actually show about the temporal cue named by the goal
("learned ... at the start"), per A-FINAL-008 High.
Data: `results/stress_controlled_round3_decontaminated_200_20/` (12 logs; 9
real-backend runs).

## Verdict

- **PASS** — every temporal evidence item verified from raw event ids and
  timestamps. No FAIL, no N/A.
- Behavioral implications are stated **only as hypotheses**, never as results.

## 1. Cross-backend timestamp identity per seed (equal events)

For every seed, the ordered 221 injected events carry **identical timestamps
across all four backends** (as expected from the equal-event invariant; here
confirmed directly):

| seed | timestamps identical across none/vector/mem0/letta |
|---|---|
| 42 | True |
| 43 | True |
| 44 | True |

## 2. Correct fact is always the earliest target candidate

The correct fact is `injected_events[0]` (written first, in the experience
phase, before the interference flood). Its logical timestamp is
`2026-01-01T00:00:00Z`; all distractors are `2026-01-02T03:50:0xZ`. In **12/12
runs** the correct fact is the earliest of the 11 injected target candidates
(`subject=target_chest`) by event timestamp. So "learned at the start" has an
unambiguous, deterministic, backend-independent timestamp signature.

## 3. Per-run temporal audit (step-0 retrieval, 9 real-backend runs)

Re-derived ranks exactly match the logged `fact_retrieval_rank`
(vector `[1,1,1]`, mem0 `[2,N/A,N/A]`, letta `[3,7,9]`), confirming the correct
fact is identified correctly.

| backend | seed | correct present | correct rank | correct = earliest retrieved target | first-ranked = correct | first-ranked = earliest | earliest-rule picks correct |
|---|---|---|---|---|---|---|---|
| vector | 42 | yes | 1 | yes | **yes** | **yes** | yes |
| vector | 43 | yes | 1 | yes | **yes** | **yes** | yes |
| vector | 44 | yes | 1 | yes | **yes** | **yes** | yes |
| mem0 | 42 | yes | 2 | yes | no | no | yes |
| mem0 | 43 | **no** | N/A | n/a | no | no | **no** |
| mem0 | 44 | **no** | N/A | n/a | no | no | **no** |
| letta | 42 | yes | 3 | yes | no | no | yes |
| letta | 43 | yes | 7 | yes | no | no | yes |
| letta | 44 | yes | 9 | yes | no | no | yes |

Notes:
- **vector**: the first-ranked item is the correct fact AND the earliest
  (correct_ts == first_item_ts == `2026-01-01T00:00:00Z`) on every seed — i.e.,
  vector's rank-1 coincides with the temporal rule. This matches A-FINAL-008's
  score-tie + stable-oldest-insertion diagnostic.
- **letta**: correct fact retrieved but never first (rank 3/7/9); its
  timestamp is the earliest retrieved target timestamp; the first-ranked item
  is a later distractor (`2026-01-02T03:50:0xZ`).
- **mem0**: correct fact at rank 2 on seed 42 (earliest retrieved target) but
  **absent from the top-10 entirely on seeds 43 and 44** (a retrieval-level
  miss, not an ordering issue).

## 4. Behavioral implications (HYPOTHESES only, not results)

- **H1 — a timestamp-aware planner would help letta and mem0-seed-42.**
  If the unchanged LLM resolved "learned ... at the start" as "choose the
  earliest-timestamp target candidate", an earliest-rule over the retrieved set
  picks the correct fact for vector (unchanged), letta (rank 3/7/9 → correct),
  and mem0 seed 42 (rank 2 → correct). Under that rule, letta's observed 0/3
  would plausibly become 3/3. Whether the LLM actually uses the restored
  timestamp this way is **unmeasured**; the round-3 logs contain no timestamp
  in the prompt (`planner.memory_view_for_prompt` strips it).
- **H2 — restoring timestamps cannot fix mem0 seeds 43/44.** There the correct
  fact is absent from the retrieved top-10, so no prompt-level temporal rule can
  recover it. A genuine retrieval recall miss remains regardless of the
  TASK-009 prompt change.
- **H3 — vector is unaffected.** Its rank-1 already equals the earliest rule,
  so adding the timestamp is not expected to change vector behavior.
- These are hypotheses about a future run; they are not supported by the
  round-3 data alone, which was produced with no timestamp in the prompt.

## 5. Post-fix QA checklist (TASK-009)

1. **Prompt-view unit test**: `memory_view_for_prompt` emits the semantic
   `timestamp` as a JSON value; still excludes item id, event id, episode id,
   score, `created_at`, metadata, raw events; retrieval order preserved.
2. **Fingerprint tests**: planner user-template/memory-view fingerprint is
   stable for an identical template/schema and changes on a schema/template
   change, without depending on dynamic goal/state/transcript/memories/ids/
   wall time/secrets.
3. **Fairness**: every new run records a 64-hex planner-template fingerprint;
   old result JSONs without it still load (`backward-compatible` optional
   field); system/tool hashes unchanged.
4. **Fresh Controlled re-run** `(200,20)` in a new directory (never pooled
   with rounds 2 or 3; treatments differ): 12/12 runs; injected_events equal
   across backends per seed except `episode_id` (timestamps included);
   step-0 WorldState equal except raw timestamp; prompt (unit-captured)
   contains timestamps and no ids/scores/created_at/metadata/raw_events;
   fairness valid/reset/fixture/model/temperature/hashes + new fingerprint;
   NoMemory empty retrieval; per-cell metrics re-derived; N/A correct; no
   failed run excluded; no residual mock listener; historical results
   unchanged.
5. **Regression**: full Python green; TypeScript only if touched; strict letta
   live `--require-live` PASS.
6. Output `docs/agents/qa/QA-009.md` comparing only the corrected round with
   round 3, and explicitly re-checking whether the H1/H2/H3 hypotheses hold.
