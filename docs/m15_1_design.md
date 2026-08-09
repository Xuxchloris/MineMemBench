# M15.1 Difficulty Upgrade Design

Status: TASK-026 Phase B design. This document defines implementation and
calibration acceptance criteria; it does not authorize a formal campaign.

Baseline: the immutable M15 stable baseline is git commit
`9fdced8fa9967a6df7b856b035485b41e84c06dc`, source fingerprint
`8606370026c2bde49737ccb945c9b69ed4aa9cb64090aa06df6cb7c23e24e55f`.
M15.1 must receive a different reviewed freeze only after implementation,
independent QA and A's final review.

## 1. Research objective

M15.1 tests whether a memory backend can preserve and causally expose useful
experience when memory lifetime, semantic interference, repeated failure
evidence and embodied action horizon increase. It does not change the planner,
model, temperature, prompt, tools, protocol or scenario parameters by backend.

The accepted M15 axes remain intact:

- Volume: `memory_noise_stress / key_retention_v2`
- Similarity: `delayed_recall / entity_key_v2`
- Temporal supersession: `world_update / temporal_chain_v2`
- Single observed-failure transfer: `failure_learning /
  observed_precondition_v2`

`failure_transfer` remains unregistered and research-invalid.

## 2. New treatment: long_lived_memory / lifetime_v1

### 2.1 Parameters

| Parameter | Type/range | Meaning |
|---|---:|---|
| `lifetime_event_count` | integer >= 2 | Total events offered during the lifetime, including the early key event |
| `session_count` | integer >= 1 | Number of intervening semantic sessions before the final task |
| `relevant_update_count` | integer >= 0 | Later observed status events about the target that do not repeat its location |
| `similar_event_count` | integer >= 0 | True session-waypoint events with similar archive/field vocabulary but distinct entities |
| `lifetime_semantics_version` | `lifetime_v1` | Explicit treatment identity |

Validation fails closed unless:

```text
lifetime_event_count - 1 >= session_count
relevant_update_count + similar_event_count <= lifetime_event_count - 1
```

Every session therefore has at least one event. Remaining events are neutral,
observed session-activity facts. Parameters enter deterministic event identity
and are recorded in the result and fairness record.

Initial smoke defaults are deliberately small:

```json
{
  "lifetime_event_count": 20,
  "session_count": 4,
  "relevant_update_count": 2,
  "similar_event_count": 5,
  "lifetime_semantics_version": "lifetime_v1"
}
```

These defaults are implementation smoke values, not a formal treatment grid.

### 2.2 Controlled fixture

Add `lifetime_route_v1` without changing `docs/protocol.md`.

- Visible initial WorldState is the canonical fixture.
- A dropped `lifetime_token` exists at `(40, 64, 0)`, outside the 32-block
  initial observation radius.
- Steve remains at `(1, 64, 2)`.
- `collect_item` and `give_item` keep their existing protocol semantics.
- The fixture identity explicitly records the hidden dropped item. Fixture
  selection depends only on scenario semantics, never memory backend.

### 2.3 Early experience and ground-truth firewall

The scenario may know the fixture specification for evaluation, but it must
not author the route into memory. The experience phase performs backend-neutral
real actions:

1. capture the initial WorldState and observed Steve location;
2. execute a fixed backend-independent two-waypoint survey path that was
   defined before any observation;
3. require a completed survey ActionResult's `state_after` to contain the dropped
   `lifetime_token`;
4. derive one `RESOURCE_DISCOVERED` event from that observation;
5. return to the initial position without collecting the token.

The event contains factual semantic fields only: resource name, observed
resource position, recipient name and the recipient position observed in step
1. It contains no action sequence, trust score, recommendation or “next time”
rule. Both ActionResults are preserved in `observed_action_results`.

If the item or recipient is not actually observed, status is not completed, or
the item moves/disappears, the run fails closed and writes no valid result.

Typed out-of-band ground truth `LifetimeGroundTruth` contains:

- `semantics_version = lifetime_v1`
- target event id
- item, pickup position, recipient and recipient position
- relevant-update ids, similar-event ids and neutral-event ids

This object is evaluation-only. It never enters goal, prompt, MemoryQuery,
ExperienceEvent, fixture WorldState or action selection.

### 2.4 Semantic sessions and transcript reset

Each session has three parts:

1. a one-step planner activity run with a seeded, explicit survey waypoint;
2. a backend-neutral `move_to` observation that establishes the session's
   actual position even if planner behavior diverged;
3. one or more ExperienceEvents derived from the observed session activity.

Every planner activity is a separate `AgentRunner.run_goal` call using the
same scenario `episode_id`. The runner creates a new local transcript for each
call, while every MemoryBackend continues to use the same long-term episode
scope. Tests inspect the LLM messages and require the first decision of every
session to contain an empty recent-actions list.

Session events are allocated deterministically and prefix-stably:

- relevant updates: a real revisit observes that `lifetime_token` remains
  available, but the stored update deliberately omits location so it cannot
  replace the early route fact;
- similar events: real visits to distinct `archive field survey waypoint`
  entities, preserving their actual positions and distinct seeded keys;
- neutral events: actual session movement/observation facts with unrelated
  seeded activity keys.

No sleep or wall-clock aging is used. Logical timestamps and event ids derive
from seed, full effective params, phase/session and ordinal in Controlled Mode.

### 2.5 Final meaningful action horizon

Goal text:

> Recover the lifetime token from the old field cache and deliver it to Steve.

It contains no coordinates, route, item spawn state, ground-truth id or action
instructions. A maximum of eight decisions provides bounded opportunity for
the following necessary real chain:

1. navigate from the base toward the out-of-range token;
2. collect `lifetime_token`;
3. return until Steve is visible;
4. give `lifetime_token` to Steve.

The chain is meaningful because the item is initially invisible,
`collect_item` cannot reach it from base, and Steve is invisible from the item
position. Merely increasing `max_steps`, reaching one coordinate or stating
the intended plan is not success.

Primary success requires completed actions in causal order, with the first
collect attempt occurring only after approaching the observed pickup and the
first give attempt occurring only after collection and return. Eventual
recovery after an invalid early collect/give is logged separately and is not
primary success.

### 2.6 Metrics

Storage:

- `offered_event_count`
- `target_event_offered`
- counts by relevant/similar/neutral class

Retrieval (causal final-run snapshots, never a later diagnostic probe):

- `target_recall_first_decision`
- `target_retrieval_rank_first_decision`
- `target_recall_any_decision`
- `first_target_retrieval_step`
- `target_retrieval_precision`
- `similar_retrieval_rate`
- `irrelevant_retrieval_rate`

Utilization and behavior:

- `target_route_utilization` (1 only under the deterministic evidence rule)
- `approached_pickup_before_first_collect`
- `collect_completed`
- `returned_before_first_give`
- `delivery_completed`
- `invalid_collect_attempt`
- `invalid_give_attempt`
- `eventual_recovery_after_invalid_attempt`
- `meaningful_action_count`
- `task_success`

Cost/latency fields keep existing labels. Unmeasured values are null/N/A.

`target_route_utilization=1` requires the target event to have been retrieved
at or before a completed `move_to` whose destination is within two blocks of
the observed pickup position. Retrieval without such action is not
utilization; matching action without auditable retrieval is `unknown`, not 1.

## 3. New treatment: failure_learning_multi / observed_precondition_applicability_v4

### 3.1 Purpose and compatibility

`failure_learning / observed_precondition_v2` remains byte-compatible. The
separate registered `failure_learning_multi` scenario adds multiple distinct,
actually observed failures with an applicability decision; it does not revive
`failure_transfer`. Historical `observed_precondition_multi_v3` result JSON
continues to load, but v3 is no longer an approved runnable Controlled
treatment because all of its failures shared the same gold-nugget rule and
therefore could not measure discrimination.

Parameters:

| Parameter | Type/range | Meaning |
|---|---:|---|
| `failure_semantics_version` | `observed_precondition_applicability_v4` | New explicit treatment |
| `observed_failure_count` | integer 2..3 | Real source failures: exactly one applicable plus 1–2 heterogeneous distractors |
| `interference_count` | integer >= 0 | Neutral deterministic events before transfer |

Legacy, v2 and historical v3 JSON retain their interpretation. A v4 Controlled cell
must explicitly request the version.

### 3.2 Fixture and observed evidence

Add `heterogeneous_failures_v1` with three environment-owned prerequisite
families and all three available resources:

| Family | Real source failure | Transfer entity | Hidden prerequisite |
|---|---|---|---|
| alpha | `alpha_zombie` | `alpha_creeper` | equip `iron_ingot` |
| beta | `beta_skeleton` | `beta_stray` | equip `string` |
| gamma | `gamma_spider` | `gamma_cave_spider` | equip `gold_nugget` |

The opaque family labels have no semantic association with their resources,
and the deliberately non-ordinal family/resource permutation prevents a
position-based NoMemory shortcut. The raw adapter error names the
family and required item. That actual failed
ActionResult is the only answer-bearing source. Seed selects the transfer
family and seed parity rotates whether its paired source appears first or second; the
remaining sources come from different families. Every 2-failure treatment
therefore contains one applicable and one inapplicable real failure; a
3-failure treatment contains one applicable and two inapplicable failures.
Backend never affects selection or order.

For each source entity the scenario:

- verifies the hand is unequipped;
- executes one real `attack_entity`;
- requires `status=failed`, a non-empty fixture error, and a surviving entity;
- derives exactly one `TASK_FAILED` event from that ActionResult;
- preserves the complete ActionResult.

There is no authored requirement, applicability label or solution event.
`required_item` appears in memory only inside the environment's real error.
Planner-visible events record action, status, error, equipped state, entity,
context and outcome. Typed evaluation-only
`ObservedPreconditionApplicabilityGroundTruth` partitions the real failure ids
into exactly one relevant id and 1–2 irrelevant ids, records the source
families and the transfer answer, and never enters a prompt, MemoryQuery,
ExperienceEvent or action path.

### 3.3 Transfer endpoint and metrics

The unchanged planner receives one transfer goal against a different hostile.
The task budget remains preparation + attack + bounded recovery slack. A
backend-neutral post-action predicate stops only when the recorded target
attack completes, so recovery remains observable without generating actions
after objective completion.

Primary success requires a completed equip of the correct item before the
first transfer attack and a later completed transfer attack. Metrics include:

- `relevant_failure_recall`
- `irrelevant_failure_retrieval` and its rate
- `failure_rank` / per-relevant and per-irrelevant ranks
- `failure_retrieval_precision` among retrieved failure experiences
- `preparation_before_first_attempt`
- `wrong_preparation`
- `failure_repeated`
- `transfer_attack_completed`
- `transfer_success`
- `eventual_recovery_after_failure`

All retrieval endpoints use the transfer run's causal first-decision snapshot.
The campaign audit fingerprints the normalized offered event stream and every
source ActionResult across backends for the same seed/treatment. It also
fails closed unless the evaluation-only relevant/irrelevant partition exactly
covers the real `TASK_FAILED` stream, contains exactly one applicable source,
and no answer/applicability fields leaked into planner-visible events.

The same terminal rule applies to lifetime: recorded completed delivery to the
recipient ends the final task. The predicate sees only the just-recorded
RunStep and is never included in a prompt, MemoryQuery, ExperienceEvent or bot
action. This makes every stored decision step semantically necessary up to
success or the failure budget.

## 4. Result evidence extension

No protocol model changes are required. Add these optional fields to
`ScenarioResult`:

```text
phase_records: list[PhaseRecord] = []
run_logs: list[ScenarioRunLog] = []
```

`ScenarioRunLog` is backend-neutral and typed:

```text
phase: str
session_id: str | None
ordinal: int >= 0
run_log: RunLog
```

`run_log` remains the primary final/headline log. New scenarios populate both
the primary field and the complete ordered `run_logs`; existing scenarios and
historical JSON remain valid without changes. The harness copies
`ctx.records` into `phase_records` before serialization.

## 5. Controlled Mode and campaign gates

- Register `long_lived_memory` only after its fail-closed scenario tests pass.
- Approve only `lifetime_v1` for Controlled Mode.
- Approve only v4 for `failure_learning_multi`; keep v2 approved and unchanged
  for `failure_learning`; legacy remains rejected.
- Select fixtures by scenario/version through the central mapping.
- Preflight validates full effective params before any output/process write.
- Same-seed backend inputs must have identical event ids, logical timestamps,
  content, ordering and observed source evidence after normalizing episode and
  volatile action/time ids.
- Fairness reset runs once after all lifetime sessions and final evaluation,
  then probes the completed shared episode and a fresh scope.
- Dashboard and replay are consumers only and never enter this lifecycle.

## 6. Test acceptance criteria

Python tests must cover:

- parameter type/range/cross-field failures;
- deterministic/prefix-stable lifetime events;
- early fact derived from real state and absent from goal/query;
- empty working transcript at each session boundary;
- same long-term episode id across sessions;
- NoMemory always returns no long-term memory;
- complete ordered multi-run/phase serialization and old JSON loading;
- long route strict order, invalid-attempt and recovery endpoints;
- objective terminal predicates stop at completed delivery/target attack,
  preserve strict recovery, and never leak into planner or memory evidence;
- v4 two/three real heterogeneous failures, exactly one applicable source,
  seed-varying order and strict relevant/irrelevant partition;
- no source event on unexpected success, empty error or vanished entity;
- v2 backward compatibility and suspended `failure_transfer`;
- same offered stream/evidence across none/vector/mem0/letta fakes;
- Controlled policy, fixture identity and campaign preflight;
- ground-truth non-leakage into goals, queries, prompts and events.

TypeScript tests must cover both new fixtures, hidden/visible radius behavior,
warded failures, collect/return/give chain, fixture parsing, and canonical/v2
fixture backward compatibility.

Full Python and TypeScript suites must pass before C receives a commit/state
for independent QA.

## 7. Bounded calibration plan

Calibration is diagnostic only and begins only after Phase G QA PASS. Use
three paired seeds per cell, all four approved backends, fresh fixture per run,
counterbalanced order and isolated stores.

Initial cells:

- lifetime smoke and two increasing lifetime/session/similarity treatments;
- multi-failure applicability v4 at failure counts 2 and 3 with bounded
  interference;
- existing volume boundary candidates 10/20/30/40/50/60 only after confirming
  the audited producer source and output directory are new and isolated.

Stop at the smallest set that identifies:

- ceiling region: all valid backends consistently succeed/retrieve;
- discrimination region: outcomes differ without systemic crashes;
- failure region: multiple non-control backends lose retrieval/utilization or
  behavior while fairness remains valid.

Do not rank backends, pool semantic versions, replace failed runs, exclude
crashes or expand to a formal sample. `difficulty-calibration.md` must report
each observed failure point and attribute it to Retrieval (R), Utilization
(U), Planning (P), Embodied execution (E), or Unknown, with raw evidence paths.

## 8. A research-method self-review

### Critical — resolved in design

**Risk:** leaking the hidden route or required item as authored ground truth
would make success scenario scripting rather than memory use.

**Resolution:** lifetime route facts derive from real state/action evidence;
v4 failure facts derive one-for-one from real heterogeneous failed
ActionResults. Applicability labels remain evaluation-only. Ground
truth remains a typed out-of-band object. Fail-closed tests scan goal, query,
prompt-visible memory and offered events.

Impact if violated: invalidates the corresponding research conclusion.

### High — resolved in design

**Risk:** using a single `run_log` would hide transcript carryover and session
behavior.

**Resolution:** optional typed multi-run and phase evidence is persisted while
the historical primary `run_log` remains unchanged.

Impact if violated: lifetime and deterministic replay claims are unsupported.

### High — resolved in design

**Risk:** longer `max_steps` could create a cosmetic horizon or permit recovery
to be misreported as primary success.

**Resolution:** the fixture enforces an out-of-range pickup and return trip;
ordered first-attempt endpoints define primary success. Recovery is separate.

Impact if violated: difficulty and behavior conclusions are inflated.

### High — controlled and observable

**Risk:** intermediate planner actions can cause backend-dependent world
trajectories.

**Resolution:** this is a legitimate downstream treatment effect, while each
session's observation anchor is a backend-neutral deterministic move and the
complete trajectory is logged. Injected semantic inputs remain identical.

Impact if violated: if event content depends on planner behavior, the run fails
the input-stream equality audit and cannot enter a comparison.

### Medium — resolved in design

**Risk:** semantic distractors could become fabricated false cache facts.

**Resolution:** similar events describe actual distinct survey waypoints and
carry distinct entity keys; they never assert an alternative target location.

Impact if violated: contaminates retrieval and may create artificial errors.

### Medium — resolved in design

**Risk:** a reason string could be mistaken for proof that memory caused an
action.

**Resolution:** utilization requires deterministic retrieved-event/action
alignment; otherwise attribution is Unknown.

Impact if violated: overstates causal memory utilization.

### Low — documentation correction required

README, development plan and handoff still describe the already frozen
TASK-025 tree as dirty/pending. Correct them during implementation docs without
rewriting historical review reports.

### Phase B decision

The design is approved for implementation subject to the listed fail-closed
tests. It does not authorize calibration before C PASS, a new freeze, a formal
preregistration or a large campaign.
