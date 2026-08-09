# TASK-020 — Failure-learning observed-precondition transfer v2

Issued by: Agent A  
Implementer: Agent B  
Independent verifier after B: Agent C  
Status: **implementation only; no campaign authorized**

## Objective

Replace the invalid transfer construct with a versioned Controlled treatment
where a real failed bot `ActionResult` reveals a hidden environmental
precondition, and the agent must transfer that experience to a different
entity/task. Preserve legacy/native `failure_learning` behavior. Keep the
suspended `failure_transfer` artifact unregistered; do not revive it.

## Frozen treatment identity

Add `failure_semantics_version`:

- `legacy` default: existing same-crate retry remains loadable/native and is
  explicitly ineligible for transfer claims;
- `observed_precondition_v2`: the only Controlled-approved value.

Add configurable `interference_count: int >= 0` (default 0 for v2 smoke;
legacy behavior remains its existing five facts unless explicitly versioned
without changing historical defaults). All effective params are logged.

## Scenario-specific Controlled fixture

Implement a scenario-specific mock fixture selected only for Controlled
`failure_learning/observed_precondition_v2`; the canonical default fixture and
all prior scenarios/tests/results must remain unchanged.

The v2 fixture must provide:

- two distinct hostile entities (`zombie` and `skeleton`) at distinct visible
  positions;
- one non-obvious but available inventory item `gold_nugget`;
- a hidden environmental rule: attacking either warded hostile without
  `gold_nugget` equipped returns a real protocol `ActionResult` with
  `status="failed"`, `result=null`, and a stable nonempty error explaining
  that `gold_nugget` must be equipped; the entity remains alive;
- after successfully equipping `gold_nugget`, attacking either entity returns
  `status="completed"` and removes that entity.

Do not change `docs/protocol.md`. Use the existing ActionResult schema. Select
the fixture through explicit process configuration recorded in the campaign
manifest/fairness path; do not infer it from backend name. The fixture's
visible state and selector must have a versioned identity. Standard mock mode
must preserve its current inventory/entities/attack behavior byte-for-byte.

## Source failure: observed, not authored

For each seed, choose source and transfer entities deterministically and
oppositely (e.g. even seed zombie→skeleton, odd skeleton→zombie), so the
transfer task is never an identical retry.

During v2 experience phase:

1. capture pre-action state (hand must be unequipped);
2. execute one actual `attack_entity` against the source entity without
   equipping the item;
3. fail closed unless the returned ActionResult is genuinely `failed`, has a
   nonempty error, leaves the source entity present, and the error is stable
   across backends for the same seed;
4. preserve the exact ActionResult as raw result evidence;
5. create exactly one `TASK_FAILED` ExperienceEvent derived from that observed
   result. Prompt-visible context may contain factual task-family/source
   entity/action/status/raw error/equipped-before fields, but must not add a
   second solution/requirement event, a trust score, a policy, or text such as
   “next time equip …”. The only required-item information visible to memory
   must be the actual environment error.

In Controlled mode the failure event (and any configured interference events)
uses deterministic ids/logical timestamps from the full effective treatment.
Every backend, including NoMemory, must be offered the identical event stream
after only `episode_id` normalization.

## Transfer task

The test goal must identify the other entity and a different checkpoint/task,
share a neutral `warded hostile` task-family cue for retrieval, and contain no
item name, tool/equip instruction, source entity, error text or answer. It is
one transfer attempt, not a retry.

Run the normal unchanged planner/tools/model against the transfer entity.
Primary behavioral endpoints are derived from ordered real RunSteps:

- `prepared_before_first_transfer_attack`: completed `equip_item(gold_nugget)`
  occurs before the first attack on the transfer entity;
- `failure_repeated`: the first transfer attack occurs before preparation and
  fails;
- `transfer_attack_completed`: a completed attack removes the transfer entity;
- `transfer_success`: preparation precedes a completed transfer attack.

The result may still log eventual recovery, but recovery after repeating the
failure is not `transfer_success`. No scenario code may directly choose the
planner's action.

## Raw evidence, ground truth and causal retrieval

- Add a backward-compatible optional `observed_action_results` field (or an
  equivalently typed general raw-evidence field) to ScenarioResult and store
  the exact source ActionResult. Old JSON must load unchanged.
- Add optional `action_error` and `action_result` fields to RunStep so failed
  transfer actions are auditable; do not change existing planner prompt or
  transcript semantics in this task.
- Add typed discriminated ground truth
  `semantics_version: Literal["observed_precondition_v2"]` with at least:
  source failure event id, source/transfer entity, required item, expected
  source action/status/error and task-family identifier. It is evaluation-only
  and never enters memory/query/prompt/action.
- Headline retrieval metrics use only typed GT plus
  `run_log.steps[0].retrieved_items`: failure-event rank/recall/precision/top1
  and retrieved-item count. Empty retrieval is recall 0; undefined rates N/A.
- A diagnostic probe may be logged but feeds no headline or behavior metric.

## Controlled policy/campaign/fairness

- Approve only `failure_learning + observed_precondition_v2` in the central
  Controlled policy. Missing/legacy/unknown version fails before bot/LLM/
  backend/output/process construction.
- Campaign preflight requires the version explicitly in requested params,
  uses the failure fixture for every scheduled backend/seed, records fixture
  selector/identity, preserves counterbalancing, semantic-duplicate rejection,
  campaign-local stores, strict result/fairness validation, stop-on-first-
  failure and late-bound test dependencies.
- Fairness must verify the v2 visible fixture and record its versioned identity.
  Source observed evidence and injected ExperienceEvent equality are audited
  separately; do not normalize away status/error/entity/equipped state.
- Never branch on backend name in planner/scenario/runner code.

## Required falsification tests

At minimum, hermetically prove:

1. legacy/native behavior and old JSON remain compatible;
2. standard mock fixture is unchanged; v2 TS fixture has two entities/item and
   produces the real failed→equip→completed action sequence for each entity;
3. Controlled legacy/unknown version fails before all side effects;
4. source/transfer tasks differ for every seed while sharing only the hidden
   fixture precondition/task family;
5. the source failure event exactly matches the raw ActionResult and contains
   no authored solution event/rule; source failure must fail closed if the
   bot unexpectedly succeeds, returns empty error, changes entity state, or
   starts equipped;
6. complete event streams and normalized source evidence match across
   NoMemory/Vector/fake backends for seeds42/43/44;
7. ground truth never enters memory, query, planner prompt, WorldState or
   action; transfer goal contains none of the banned answer fields;
8. exact retrieval metric math for empty/absent/rank>1/unknown-top and a
   FlipFlopBackend whose diagnostic probe differs;
9. behavior metric sequence cases: prepared-before-attack success; attack-
   then-prepare failure repetition; wrong item; wrong entity; failed equip;
   completed preparation + failed attack; eventual recovery remains primary
   failure;
10. campaign fixture selection/manifest identity/preflight/result/fairness
    fail closed without real process/network calls;
11. Python focused/full tests, TypeScript build/tests all pass with no network.

If the fixture cannot be implemented without changing the wire contract,
stop and report; do not edit `docs/protocol.md`.

## Deliverable

Modify the smallest necessary Python/TypeScript/tests/docs files. Do not run a
campaign or real LLM/Letta/Minecraft call; do not touch existing results,
services, `.env` or git. Write
`docs/agents/reviews/B-COMPLETION-020.md` with exact file list, focused/full
Python and TS outputs, hermeticity evidence and deviations; stop for C.
