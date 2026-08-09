# Dashboard and Deterministic Replay Design

Status: TASK-026 Phase B design. The dashboard is a read-only observability
consumer. Raw result JSON and campaign manifests remain the source of truth.

## 1. Non-interference boundary

The dependency direction is one way:

```text
raw results/manifests -> index -> replay/compare models -> local HTTP API -> UI
```

Runner, planner, scenarios, memory adapters, bot bridge and campaign producer
must not import dashboard modules. The dashboard has no endpoint or Python
callable that starts/stops/retries a campaign, invokes an LLM, contacts
Minecraft, calls a MemoryBackend, edits params or writes evidence. A dashboard
crash therefore cannot affect a producer process.

The supported command is:

```powershell
.venv\Scripts\python -m minemembench.dashboard --results-dir results
```

Defaults: bind `127.0.0.1`, choose a documented local port, and open no browser
unless explicitly requested. The MVP adds no web-framework dependency: use the
stdlib threaded HTTP server plus packaged HTML/CSS/JavaScript.

## 2. Files and modules

```text
benchmark/minemembench/dashboard/
  __init__.py
  __main__.py
  index.py
  models.py
  replay.py
  compare.py
  server.py
  static/
    index.html
    app.css
    app.js
```

The static client never reads the filesystem directly. All API responses are
JSON generated from validated, sanitized models.

## 3. Read-only result index

`ResultIndex(results_dir)` recursively discovers only:

- `scenario_*.json`
- `campaign_manifest.json`

It ignores stores, databases, `.env`, logs, reports, caches, server worlds and
symlinks that escape the resolved results root. It never follows a path
provided by an HTTP client.

### Cache

Each known file is keyed by resolved path and `(mtime_ns, size)`. An unchanged
file is not reparsed. A changed valid file replaces its cached parsed model.
Deleted files disappear from the next snapshot without being deleted by the
dashboard.

For a changed file that is temporarily invalid JSON:

- retain the last-good parsed value, if any;
- mark it `partial=true`, `stale=true`, and expose a short parse category;
- never expose file contents or a traceback;
- retry on the next poll.

If no last-good value exists, expose a pending/partial file record but no fake
run. Schema-invalid complete JSON is marked invalid, not coerced.

### Historical compatibility

Manifest adapters support:

- legacy manifests with no `schema_version` and `scenario_params` per run;
- `controlled-campaign/v2`;
- `controlled-campaign/v3`;
- current `controlled-campaign/v4` and backward-compatible optional fields.

Missing fields are null/unknown. The index never writes an upgraded manifest.
Historical ScenarioResult JSON continues through the existing Pydantic model
because new multi-run/phase fields have empty defaults.

### Stable ids and revisions

Run/API ids are SHA-256-derived opaque ids from the result-root-relative path,
not raw absolute paths. Snapshot revision is a digest of sorted relative path,
mtime, size and parse state. It changes only when indexed evidence changes.

## 4. API

All endpoints are GET-only except unsupported methods return 405.

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | service status and current index revision |
| `GET /api/snapshot` | campaigns, run cards, aggregate counts, partial/invalid files |
| `GET /api/runs/{opaque_id}` | validated run detail and evidence summaries |
| `GET /api/replay/{opaque_id}` | deterministic replay timeline and 2D trajectory |
| `GET /api/compare?...` | same-seed backend comparison and fairness verdict |
| `GET /api/events` | server-sent events containing revision/status only |

`/api/events` polls the index at a small configurable interval and emits only
when revision changes, plus occasional SSE keepalive comments. Filesystem
polling is the canonical source; SSE is merely a UI notification channel. A
disconnected client is discarded without affecting indexing or producers.

No endpoint serves arbitrary raw paths, stdout/stderr files, environment
variables, request headers, backend databases or source files. Unknown ids and
path traversal return 404.

## 5. Dashboard views

### Campaign Overview

Show:

- campaign id, scenario/version/mode, git commit and source fingerprint
- scheduled/completed/failed/pending/remaining/partial/invalid/error counts,
  progress percentage and explicit N/A ETA
- per-cell and per-backend matrix over seeds
- fairness-valid/invalid counts and measured success rate
- prompt/completion/total token totals and separately labeled mean LLM,
  retrieval and end-to-end latency
- N/A for unmeasured fields

No aggregate silently drops a failed run, duplicate run, invalid fairness
record or partial file. Duplicate run keys are flagged.

### Run Detail

Show:

- scenario, seed, backend, params, campaign mode and success
- fairness/provenance fields and invalid reason
- injected event counts and typed ground-truth summary
- retrieval probes and exact retrieved-event summaries
- all phase/session RunLogs
- planner actions/reasons, environment status/error/result, tokens and labeled
  latency sources
- observed source ActionResults

The UI never labels LLM latency as memory latency.

### Replay

Replay is an instantaneous deterministic walk over stored evidence. It makes
no LLM, bot, backend, HTTP or WebSocket call and has no wall-clock sleeps.

Controls: first/previous/play/pause/next/last, a seek slider, semantic-event
jump controls and 0.5x/1x/2x speed. Speed affects only client animation. The
timeline explicitly labels memory offered, phase, retrieve, decide, action,
outcome and evaluation events. A frame's content is immutable and derived
from JSON.

### Same-seed Compare

Default columns are None, Vector, Mem0 and Letta. Missing cells are N/A.
Compare one exact `(scenario, effective params, seed, campaign mode)` key.
Duplicates are visible and invalidate automatic selection.

Every present backend column shows retrieved top-k, first action/reason,
preparation, failure repetition, steps, task success, prompt/completion/total
tokens, separately labeled latency fields and a compact side-by-side replay
timeline. Missing values are N/A.

The fairness verdict compares:

- planner model and temperature
- system prompt, tool set and planner user-template hashes
- Minecraft version and world seed
- fixture selector and identity
- scenario and full effective params
- campaign mode and run seed
- source-tree fingerprint and git commit/dirty state

Backend, episode id, run id, backend-local item ids/scores, ports and wall time
are not equality requirements. Controlled Mode has no Minecraft world seed;
when all compared runs carry the same non-empty versioned fixture selector and
identity, `world_seed=null` is explicit N/A and passes that field. Native Mode
still requires a measured world seed. A missing/incomplete historical fixture
identity or other required field produces `unknown`, never a false PASS.
`fairness.valid=false` produces FAIL.

### 2D trajectory

Plot x/z only. Each RunLog starts with the first step's pre-action
`world_state.position` when available, followed by every post-action
`RunStep.position`. Stored target positions, nearby entities, action points,
failed actions and completed actions are separate markers with evidence
references. Session boundaries and action status are annotated. The UI states
that terrain is not reconstructed.
Missing pre-state or zero-step logs render an empty/partial trajectory, not a
fabricated origin.

## 6. Replay evidence model

Replay ordering uses the explicit ordered `run_logs` list for new results and
falls back to the historical primary `run_log`. Phase records provide
boundaries but timestamps do not control playback order.

Each step frame has four independent layers:

### R — Memory Retrieval

Directly observed:

- query context (the RunLog goal and episode scope)
- retrieved item order/count
- item score when backend reported one
- complete semantic event snapshot
- direct probe latency only when the frame represents a RetrievalProbe

An empty list is a measured zero. A historical absent field is unknown.

### U — Memory Utilization

Default: `unknown`.

Supported only by deterministic scenario rules:

- entity-key/noise/lifetime: the declared target event was retrieved no later
  than an objectively matching movement/action toward the typed target;
- temporal-chain: the current event was retrieved before movement toward the
  current location, or a stale event before a stale movement;
- observed-precondition v2/historical v3/applicability v4: the declared
  applicable failure event was retrieved before correct preparation/attack
  ordering. Retrieving an inapplicable v4 failure is not utilization proof.

Every supported value includes rule id, event ids and action frame ids.
LLM reason text alone never proves utilization. If both supporting and
contradictory evidence exist, status is unknown with an explanation.

### P — Planner Decision

Directly observed action, arguments, reason, prompt/completion tokens and LLM
latency. This layer reports what the planner chose, not why it chose it.

### E — Embodied Outcome

Directly observed environment status, error/result payload, pre-state and
post-action position. If `state_after` was not stored in older RunSteps, only
the fields actually present are displayed.

### Unknown attribution

When a failure cannot be isolated to R/U/P/E from stored evidence, replay and
calibration explicitly report Unknown. Categories are evidence labels, not a
forced mutually exclusive causal classifier.

## 7. Security controls

- Resolve and validate `results_dir` once at startup.
- Refuse a file outside that root, including symlink/junction escapes.
- No endpoint accepts a filesystem path.
- Serve static files from an explicit allowlist with fixed content types.
- Never load `.env`, enumerate process environment, echo request headers or
  serialize Settings.
- Do not expose manifest commands or absolute log/store paths in the API.
- Recursively redact fields whose names match secret/key/token/password/
  authorization/cookie patterns as defense in depth, while preserving known
  metric names such as `token_cost` and prompt/completion token counts.
- Bind loopback by default; no login/cloud/public bind in MVP.
- Add `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, a restrictive
  Content-Security-Policy, and no inline third-party scripts.

Tests place sentinel secrets in adjacent `.env`, logs, manifest extras and
result extras and require that no snapshot/detail/replay/compare response
contains them.

## 8. Performance and availability

- Recursive discovery filters by the two accepted filenames before reads.
- mtime/size cache avoids repeated JSON parsing.
- Snapshot aggregation reuses validated cached models and never reparses an
  unchanged result.
- Run detail/replay is built lazily from the already parsed result.
- API snapshot cards are bounded summaries; exact retrieved events remain
  frame-scoped in replay and full raw validated evidence remains in run detail.
- Refresh and run-id maps are protected by one re-entrant lock so concurrent
  SSE polling cannot expose a half-rebuilt index or transient 404.
- One invalid/partial/large file cannot prevent other runs from loading.
- Dashboard exceptions return a sanitized 500 and do not mutate the index or
  producer evidence.

Performance tests create a large synthetic result tree, assert unchanged
refresh performs no reparses, and enforce a generous local regression budget
rather than a machine-specific research threshold.

## 9. Testing

Unit/integration tests cover:

- legacy/v2/v3/v4 manifests and historical ScenarioResult JSON;
- partial JSON, last-good cache, deletion and schema-invalid files;
- recursive indexing, same-seed duplicate keys and mtime cache hits;
- deterministic identical replay output across repeated calls;
- no LLM/Minecraft/backend access during replay;
- R/U/P/E/Unknown attribution rules and contradictory evidence;
- multiple session logs and phase boundaries;
- 2D trajectory with missing pre-state/empty runs;
- same-seed PASS/FAIL/unknown fairness cases;
- N/A preservation and failed-run inclusion;
- traversal, symlink escape, static allowlist and secret sentinel tests;
- GET-only API, security headers, malformed ids and SSE revision events;
- dashboard start/stop while a fake producer independently writes partial then
  complete JSON.
- concurrent SSE-style refresh and run lookup remain atomic.

The full benchmark Python suite must remain green. Dashboard tests use only
temporary directories and local loopback; unit tests perform no external
network access.

## 10. A design review

### Critical

No dashboard data can feed planner/scenario/backend execution. The module
dependency test and API surface make this fail closed. Violation would
invalidate every observed treatment, so implementation stops if a reverse
dependency appears.

### High

Utilization is not directly recorded. The design defaults to Unknown and
permits only explicit scenario evidence rules. This prevents reason-text
overclaiming.

### High

Partial manifest/result writes are expected. Last-good caching plus visible
partial state prevents both service crashes and silent disappearance of runs.

### High

Historical fairness records omit some current fields. Missing means unknown,
not valid. This avoids silently pooling incomparable revisions.

### Medium

Serving arbitrary stdout/stderr could leak credentials in error text. The MVP
does not serve those files; it exposes only pre-registered status and sanitized
error categories.

### Medium

Recursive scans can become expensive. Filename filtering and mtime/size caches
bound steady-state work while retaining raw JSON as truth.

### Low

The stdlib server is intentionally local and minimal. It is adequate for the
single-user observability MVP; public hosting, auth, 3D, video and cloud are
out of scope.

Decision: approved for implementation under the non-interference, security and
backward-compatibility tests above.
