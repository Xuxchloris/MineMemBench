# TASK-002 — Delayed-recall discriminative smoke, measurement-validity gate

Issued by: Agent A
Status: B implementation first; C must wait for A's implementation review.

## One research objective

Can `delayed_recall` with similar distractors create an interpretable difference
among `none`, `vector`, `mem0`, and `letta` when behavior is linked to the exact
retrieval that caused it?

No other scenario or new framework is in scope.

## Agent B — implementation task

The worktree contains an interrupted four-file draft from B. Inspect it; keep
only pieces that satisfy this task. Do not discard unrelated user work.

### Required behavior

1. **Paired independent seeds:** `--seed S --runs N` uses `S..S+N-1`; each
   result and fairness record carries the effective seed. Add a CLI-level test
   proving 42/43/44 for three runs and the same schedule across backends.
2. **Real reset audit:** create per-run backend counters, reset the completed
   episode after its metrics are captured, probe the reset scope and a fresh
   scope, and preserve an invalid run record on cleanup/probe failure. Update
   all old fairness tests to the new contract.
3. **Behavior-causing retrieval evidence:** every `RunStep` stores the actual
   retrieved `MemoryItem` snapshots returned by the planner for that decision,
   not only a count. Do not store secrets or API keys. Delayed-recall headline
   retrieval metrics must use the first decision's recorded retrieval, not a
   second evaluation-time retrieve call. A separately labelled diagnostic
   probe may remain but cannot feed the headline metric.
4. **Backend-neutral ground truth:** retain the correct event id and the known
   target-like distractor ids in `DelayedRecallScenario`. Compute correct rank,
   recall accuracy, wrong-fact rate, and retrieval precision from ids. Empty
   retrieval is a measured miss (`recall_accuracy=0`), while undefined rates
   may be N/A. Do not branch on backend names.
5. **Letta semantic round-trip:** finish or replace the interrupted passage-tag
   design so live Letta 0.16.8 reconstructs the exact original
   `ExperienceEvent` without a process-local cache and without changing the
   embedded human-readable text. Update fake-boundary tests and add a live
   assertion covering event type/context/id equality.
6. **Strict live verifier:** add an explicit strict/acceptance option to
   `verify_letta_live.py` that exits non-zero if the server is unavailable.
7. **Raw evidence schema:** keep full MemoryItem/ExperienceEvent fields in any
   retrieval probe and in per-step retrieval evidence; update consumers/tests.
8. **Safety gate:** remove `failure_transfer` from the public scenario registry
   for now and document it as research-invalid/N/A pending a real observed
   failure cause. Do not redesign it in this task. `docs/protocol.md` is frozen.

### Acceptance

- Full Python suite and TypeScript suite pass.
- Strict Letta live verifier passes against server 0.16.8.
- Focused tests prove: seed schedule; completed-id reset; invalid cleanup is
  logged; NoMemory actual retrieval is empty; metric ids work with both exact
  and text-shaped events; planner retrieval saved equals metric input; exact
  Letta event round-trip.
- No backend-name conditional in planner/runner/scenario logic.
- No formal experiment, git add, commit, or push.
- Write `docs/agents/reviews/B-COMPLETION-002.md` with files, exact test output,
  live output, and deviations/blockers; then stop for A review.

## Agent C — independent QA task (PENDING A release)

After A approves B's implementation, independently run:

1. Full Python and TypeScript tests.
2. Strict Letta live verification; Letta HTTP health; bot health; Minecraft
   TCP; Docker compose/container health if the CLI is available, otherwise N/A.
3. Isolation checks for none/vector/mem0/letta and exact ExperienceEvent input
   equivalence at the adapter boundary.
4. Isolated smoke directory `results/stress_round1/` only:
   - control `(interference_count=10, similar_distractor_count=0)`;
   - stress `(interference_count=50, similar_distractor_count=5)`;
   - backends `none vector mem0 letta`;
   - `--runs 3 --seed 42` per cell, expected effective seeds 42/43/44;
   - exactly 24 retained run logs. Do not expand.
5. Audit run ids, episode ids, fairness validity, reset fields, params, model,
   temperature, prompt/tool hashes, per-step retrieved items, missing/error
   logs, and N/A handling.
6. Write `docs/agents/qa/QA-002.md` with PASS/FAIL/N/A, reproduction details,
   raw log locations, and per-cell success/token/latency/retrieval summary.
   Do not modify production code or perform git operations.
