# QA-007-PREFLIGHT — Pre-fix evidence audit of delayed-recall planner leakage

Date: 2026-08-08
QA: Agent C (independent evidence verification; no production-code change, no
campaign run, no parameter change, no git)
Scope: pre-fix raw artifacts under `results/stress_controlled_round2_200_20/`
(12 logs) + current planner serialization. TASK-007 (B) is being implemented
in parallel; this file records what the contaminated evidence actually
contains so the corrected version can be verified against it.

## Verdict

- **PASS** — both A-FINAL-006 High findings are confirmed present in the raw
  artifacts and the current code, with exact counts.
- **FAIL** — none (this is a contamination audit, not a gate on pre-fix data).
- **N/A** — no correctness/staleness labels other than the two hand-authored
  notes below were found in the artifacts; the 200 noise facts are unlabelled
  but still structurally different from the correct fact.

## 1. Evidence — target-location distractors carry explicit labels

Source: `benchmark/minemembench/scenarios/delayed_recall.py`
`build_similar_distractors()` kinds 2 and 3 set `"note": "wrong location"` and
`"note": "used to be located here"`; `interference_phase()` stores them with
actor `environment`, event_type `world_fact_updated`.

Artifacts (all 12 JSONs, `injected_events`, 221 events per run =
1 correct + 200 noise + 20 distractors; sums over 3 seeds per backend):

| backend | total injected | labelled target-location distractors | structurally different from correct fact |
|---|---|---|---|
| none | 663 | 30 (10/run: 5×`wrong location` + 5×`used to be located here`) | 660 |
| vector | 663 | 30 | 660 |
| mem0 | 663 | 30 | 660 |
| letta | 663 | 30 | 660 |

## 2. Evidence — actor/event_type structural difference from the correct fact

- Correct learned fact (per run): actor `scenario-instructor`, event_type
  `location_discovered`, context keys `{subject, x, y, z}` (no `note`).
- All 220 other injected events: actor `environment`, event_type
  `world_fact_updated`, context keys `{subject, x, y, z[, note]}` — including
  the 200 noise facts and all 20 distractors (the 10 labelled target-location
  ones additionally carry a `note`).
- In step-0 retrieval of every real-backend run the retrieved set exposes both
  structures: `actors={environment, scenario-instructor}`,
  `types={location_discovered, world_fact_updated}` — the correct fact is
  structurally unique in the prompt.

## 3. Evidence — labelled items in step-0 retrieval

`run_log.steps[0].retrieved_items` (the exact retrieval fed to the planner):

| backend | retrieved | labelled (`note` present) | subject=target_chest | notes present |
|---|---|---|---|---|
| none (3 seeds) | 0 | 0 | 0 | [] |
| vector (3 seeds) | 10 | 9 | 10 | `used to be located here`, `wrong location` |
| mem0 (3 seeds) | 10 | 9 | 10 | `used to be located here`, `wrong location` |
| letta (3 seeds) | 10 | 9 | 10 | `used to be located here`, `wrong location` |

i.e. in every real-backend step, **9 of the 10 items handed to the planner
disclose their own incorrectness** via a hand-authored note, and the 10th
(correct) item is structurally distinct. The observed vector rank-6 +
behavior-3/3 pattern is consistent with the planner filtering by these labels.

## 4. Evidence — full MemoryItem fields reach the planner (code inspection)

- `benchmark/minemembench/agent/planner.py::_build_user_message()` lines
  179–180: `memories_json = json.dumps([item.model_dump(mode="json") for item in memories])` — no field exclusion (contrast line 175, which excludes only the world-state `timestamp`).
- `benchmark/minemembench/memory/base.py::MemoryItem` fields: `item_id`,
  `event`, `score`, `created_at`, `metadata`; `ExperienceEvent` adds
  `event_id`, `episode_id`, `timestamp`, `actor`, `target`, `event_type`,
  `location`, `context`, `outcome`, `raw_events`.
- Therefore the prompt exposes every TASK-007 item-1 field: item id, score,
  created_at, metadata, event id, episode id, timestamp, raw_events.
- Raw evidence in the logs confirms the same shape is retained per step
  (vector seed 42 sample):
  - labelled distractor: `item_id=ctrl-ec1f…, score=0.1417366…, created_at=…,
    metadata={}, event={event_id=ctrl-ec1f…, episode_id=…, timestamp=2026-01-02T03:50:03Z, actor=environment, event_type=world_fact_updated, context={…, note:"used to be located here"}, raw_events=[]}`;
  - correct fact: `item_id=ctrl-3afb…, score=0.1066003…, created_at=…,
    event={…, actor=scenario-instructor, event_type=location_discovered, context={subject,x,y,z}, …}`.
  - Note the labelled distractor also carries a higher `score` than the correct
    fact (0.1417 vs 0.1066) — another backend-specific field the planner can
    exploit.

## 5. Post-fix QA checklist (for the corrected TASK-007 implementation)

When B's fix lands and A approves, C will verify:

1. **Planner serializer (unit test)**: planner memory JSON for every backend
   contains ONLY semantic `ExperienceEvent` fields (actor, target, event_type,
   context, outcome; order preserved) and excludes `item_id`, `score`,
   `created_at`, `metadata`, `event_id`, `episode_id`, `timestamp`,
   `raw_events`. Applied identically to all backends — no backend-name branch.
2. **Controlled distractor semantics (unit test)**: competing target-location
   candidates use the SAME actor, event_type, and context key set as the
   learned target fact; no label token anywhere (`wrong`, `stale`, `old`,
   `former`, `decoy`, `correct`, `used to be located here`, …); distinct
   deterministic coordinates; stable out-of-band event ids / logical
   timestamps in raw evidence.
3. **Raw evidence intact**: `RunStep.retrieved_items` still carries the full
   `MemoryItemSnapshot` (ids, score, created_at, metadata, full event)
   unchanged; metrics re-derivable from logs.
4. **Native mode**: unchanged unless the shared serializer is required;
   distractor semantic changes gated to Controlled mode only.
5. **Fresh Controlled campaign** `(200,20)` in a new directory (per
   A-FINAL-006), never pooled with `stress_controlled_round2_200_20`:
   - 12/12 runs, manifest↔result↔log binding, fresh mock fixture per run,
     campaign-local stores, no retry/resume;
   - injected_events equal across four backends per seed except `episode_id`
     (221/seed) AND containing no label tokens in any context;
   - step-0 WorldState equal per seed except raw timestamp;
   - planner prompt (unit-captured) contains no ids/scores/timestamps;
   - fairness/reset/fixture/model/temperature/hashes complete; NoMemory empty
     retrieval with `recall_accuracy=0`; N/A handling intact; no failed run
     excluded.
6. **Regression**: full Python + TypeScript suites green; strict letta live
   `--require-live` PASS; `docs/protocol.md` unchanged.
7. Output: `docs/agents/qa/QA-007.md` (PASS/FAIL/N/A, per-cell summary,
   reproduction) comparing only the corrected round to Controlled round 1,
   never to the contaminated pre-fix round or Native data.
