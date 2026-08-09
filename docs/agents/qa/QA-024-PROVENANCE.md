# QA-024 — Independent audit of TASK-024 (source provenance gate + documentation freeze)

Issued by: Agent C (independent QA / research-audit agent)
Date: 2026-08-09
Mode: **offline / immutable-on-disk audit only** — no `.env` access, no network,
no live Letta/LLM/Minecraft, no campaign runs, no code/test/result/parameter
edits, no git mutations. All audit scripts ran from the OS temp dir
(`C:\Users\30573\AppData\Local\Temp\opencode\`). The only repo artifact created
is this report.

Scope: TASK-024 (`docs/agents/tasks/TASK-024.md`), A-APPROVAL-024,
corrected `docs/agents/qa/QA-024-COMPLETION-AUDIT.md`, and the full TASK-024
code/test/documentation diff (the working tree at HEAD `cbaa276`, which carries
TASK-002..024 uncommitted).

## 0. Method and evidence read

Read completely: `AGENTS.md`, `README.md`, `docs/protocol.md`,
`docs/development_plan.md`, `docs/preregistration_template.md`,
`docs/experiment_standard.md`, `docs/stress_design.md`,
`docs/agents/HANDOFF.md`, `docs/agents/reviews/A-APPROVAL-024.md`,
`docs/agents/qa/QA-024-COMPLETION-AUDIT.md`; the source modules
`core/provenance.py`, `core/fairness.py`, `cli.py`,
`scripts/run_controlled_campaign.py`, `scenarios/controlled.py`,
`scenarios/base.py`, `scenarios/registry.py`, `memory/base.py`,
`memory/registry.py`, `agent/planner.py`, `core/runner.py`; the test files
`test_provenance.py`, `test_controlled_mode.py`, `test_run_loop.py`,
`test_fairness.py`, `test_scenario_params.py`; and the on-disk result manifests
(schema `controlled-campaign/v2` and `/v3` and schema-less) plus result JSON.

Commands run (all read-only on the repo):
- `git rev-parse HEAD`, `git status --porcelain`, `git log --oneline -5`
- `git diff --check` → clean (exit 0; only CRLF warnings, no whitespace errors)
- `.venv\Scripts\python -m pytest -q` → **368 passed** (run 3×)
- Focused suites → **108 passed** (provenance+controlled_mode+run_loop+fairness+scenario_params); **65 passed** for `test_controlled_mode.py` alone
- `cd minecraft; npm test` → **34 passed**; `npm run build` → OK
- Independent recomputation script (`qa024_provenance.py`, OS temp dir) → **47 checks passed, 0 failed**
- Hermetic Python probes for backend-name-branch scan, network-import scan, old-result load, old-manifest schema, junction/symlink escape behavior

Blockers / non-actions: no campaign run (forbidden); `verify_letta_live.py` not
run (network/live call forbidden). TypeScript was not modified by TASK-024, so
the A baseline (34 passed / build OK) is cited — and independently reproduced.

---

## 1. Summary

**Verdict: PASS.** All seven TASK-024 implementation requirements are met, the
acceptance tests are present and green, no protocol/planner/backend-behavior
change was introduced, and no campaign/ranking/Failure Point is authorized.

| Requirement | Verdict |
|---|---|
| R1 deterministic source-provenance utility + documented allowlist | **PASS** |
| R2 read-only git provenance (commit/dirty/status fp; explicit absence) | **PASS** |
| R3 optional backward-compatible `FairnessRecord` provenance fields; populated on new CLI runs | **PASS** |
| R4 `controlled-campaign/v4` manifest pre-registers full provenance before run 1; result mismatch stops campaign | **PASS** |
| R5 `--require-clean-source` fails before output creation on dirty/unavailable git | **PASS** |
| R6 formal-study pre-registration template | **PASS** |
| R7 documentation drift repair (dev plan, README M2/M3/M15, stress_design, CLI help) | **PASS** |
| No protocol diff / no backend-name branch / no planner-action change / no secret-path leakage | **PASS** |

Findings: **0 Critical, 0 High, 0 Medium, 2 Low — both RESOLVED** (see §5;
post-fix verification §7).

---

## 2. Requirement-by-requirement audit

### R1 — Deterministic source-provenance utility — PASS

- `benchmark/minemembench/core/provenance.py` hashes a documented allowlist
  (`SOURCE_GLOBS` + `SOURCE_FILES`): runtime/adapters
  (`benchmark/minemembench/**/*.py`), tests + fixtures
  (`benchmark/tests/**/*.py`, `benchmark/tests/fixtures/**/*.json`), the TS
  adapter (`minecraft/src/**/*.ts`, `minecraft/test/**/*.ts`), dependency
  manifests (`pyproject.toml`, `minecraft/package.json`,
  `minecraft/package-lock.json`), compose (`docker-compose.yml`,
  `docker-compose.letta.yml`), configuration schema (`.env.example`,
  `minecraft/tsconfig.json`, `minecraft/Dockerfile`), wire contract
  (`docs/protocol.md`), and the two producer scripts
  (`scripts/run_controlled_campaign.py`, `scripts/verify_letta_live.py`).
- **Independent recomputation matched exactly** (`qa024_provenance.py`):
  module fingerprint == independent recomputation
  `e3b95ba22b89e90e0488db51a92a0609ab56431edce5aa3784dd508dcb23a49d`, 104
  files, and every `(path, size, sha256)` record byte-identical.
- Determinism: repeated capture identical; glob-order reversal does not change
  the fingerprint (paths sorted ascending by relative posix path).
- Mutation sensitivity: one-byte change in a hashed file and adding one file
  both change the fingerprint and the file count.
- Missing anchor: a required allowlist file that does not exist raises
  `FileNotFoundError("required provenance input is missing: …")`.
- Forbidden-path exclusion proven both independently and by
  `test_current_repo_provenance_never_includes_forbidden_inputs`: `.env`,
  `results`, `stores`, `dist`, `node_modules`, `server` (Minecraft worlds),
  `.venv`, `__pycache__` appear in no hashed path; a glob that reaches a
  forbidden part raises `ValueError`.
- `.env` specifically: name-excluded and never present in the allowlist result;
  `.env.example` (the documented template) is the intended schema anchor.
- Symlink/junction behavior: the code rejects symlinks
  (`is_symlink()` → `ValueError`) and rejects any path whose `resolve()` leaves
  the repository root. On Windows, directory **junctions** are *not* seen by
  `is_symlink()`; an escaping junction is still caught by the
  `resolve().relative_to(root)` check (verified). **Low finding L-1** below.

### R2 — Read-only git provenance — PASS

- `core/provenance.py::_git_provenance` runs `git -C root rev-parse HEAD` and
  `git status --porcelain=v1 --untracked-files=all`; failures (git absent,
  not-a-repo, or status failing) return `git_available=False` with
  `git_commit/git_dirty/git_status_fingerprint` all `None` — absence is
  explicit, never guessed. A commit with an unreadable worktree state is also
  treated as unavailable (fail-closed), never as clean.
- Normalized status: CRLF/CR normalized to LF before the SHA-256 status
  fingerprint, so the hash is platform-stable.
- Independent verification in a temp git repo: available+clean
  (`git_available=True`, `git_dirty=False`, 40-char commit, 64-hex status fp);
  dirty after an edit (`git_dirty=True`, status fp changes, commit stable);
  plain non-git dir → `git_available=False`, all git fields `None`.
- Current repo capture: `git_available=True`, commit
  `cbaa276709a4f5de9ba7efedbb9db2a142ca0d49`, `git_dirty=True`
  (correct — the worktree is dirty), status fp
  `0ea2ab9eff0d10020a997ca9fff34e1864f4ed9070f849ff99a901537da68125`.
- No git mutation: only read-only `rev-parse`/`status` subprocesses.

### R3 — FairnessRecord optional provenance fields — PASS

- `core/fairness.py::FairnessRecord` adds optional (`= None`) fields
  `source_tree_fingerprint`, `source_file_count`, `git_available`,
  `git_commit`, `git_dirty`, `git_status_fingerprint`. All default to `None`,
  so pre-TASK-024 JSON validates unchanged
  (`test_old_fairness_json_without_provenance_still_loads`); confirmed against
  9 on-disk result files (v2/v3 and schema-less) which load with these fields
  `None`.
- Every new CLI scenario run populates them: `FairnessChecker.__init__`
  defaults to `capture_source_provenance()`, and `_base_record` copies all six
  fields into the record. Exercised end-to-end by
  `test_controlled_run_records_mode_fixture_and_inputs` (asserts
  `source_tree_fingerprint`, `source_file_count` non-None, and the git fields
  consistent with `git_available`).

### R4 — `controlled-campaign/v4` pre-registration + fail-closed mismatch — PASS

- `scripts/run_controlled_campaign.py::MANIFEST_SCHEMA_VERSION =
  "controlled-campaign/v4"`.
- `main()` captures the complete `SourceProvenance` and embeds
  `"provenance": provenance.model_dump(mode="json")` in the manifest **before
  any run**; `run_campaign` writes the fully-pending manifest to disk before
  the first invocation (`test_campaign_lifecycle_through_fakes` asserts the
  manifest is written pending before run 1; `test_q4_main_…` asserts v4 schema
  and provenance presence).
- Every produced result is validated against the manifest provenance in
  `_validate_run_result(…, expected_provenance=manifest["provenance"])`: the
  result's `fairness` must match the manifest on
  `source_tree_fingerprint`, `source_file_count`, `git_available`,
  `git_commit`, `git_dirty`, `git_status_fingerprint`. Any mismatch sets
  `status=failed` with a human-readable reason and **stops the campaign** —
  no retry, no replacement (`test_q24_campaign_stops_on_result_provenance_mismatch`,
  `test_q24_result_provenance_mismatch_fails_closed`). Partial evidence is
  preserved (manifest rewritten after every run, result files and logs left
  in place).

### R5 — `--require-clean-source` — PASS

- `main()` checks `--require-clean-source` immediately after capturing
  provenance and **before** the output-directory validation, the schedule
  build, and any write: it fails with exit 2 and a reason
  ("git provenance is unavailable" / "the git worktree is dirty") when git is
  unavailable or `git_dirty is not False`.
- `test_q24_require_clean_source_fails_before_output` covers both the dirty
  (`git_available=True, git_dirty=True`) and unavailable (`git_available=False`)
  cases and asserts the output directory was never created.
- Default diagnostic behavior runs dirty but records the fact: provenance
  carries `git_dirty=True` into the manifest and every fairness record.

### R6 — Pre-registration template — PASS

- `docs/preregistration_template.md` freezes: study identity + commit SHA +
  expected `source_tree_fingerprint` + worktree-clean flag + campaign mode +
  scenario + semantics version + fixture identity; hypotheses; design before
  run 1 (backends/versions, cells with every effective parameter, paired seeds,
  runs per cell, counterbalancing, planner model/temp/prompt/template/tool
  hashes, fixture/world version + seed, retrieval limit/query contract);
  primary/secondary/diagnostic endpoints + exact Failure-Point rule + N/A
  definitions; data integrity (valid-run definition, isolation gate, missing
  log/crash/retry=none/exclusion/early-stop/extension/multiple-comparison);
  frozen analysis (tests, effect sizes/CI, aggregation unit, ranking rule,
  sensitivity, tables/figures, script path + expected fingerprint);
  authorization block (A decision, C preflight, review-owner clean revision,
  explicit results directory).
- Header: "Template only. … Filling this file does not authorize a run." No
  formal run is authorized by the template or by this task.

### R7 — Documentation drift repair — PASS

- `docs/development_plan.md` created (replaces the stale root
  `docsdevelopment_plan.md`, which is explicitly flagged as archival).
- README: `[x] M2`, `[x] M3`, `[x] M15A`, `[x] M15B`; the M15B section now
  states the v2 evidence boundaries (delayed-recall v2 `(200,20)` diagnostic
  only, non-poolable legacy; world-update depth-3 accepted, curve gated;
  noise 0/10/50 accepted then stopped; failure-learning 0/10/50 accepted then
  stopped; `failure_transfer` suspended/unregistered), `controlled-campaign/v4`
  provenance, and `--require-clean-source`. The ladder example is labeled
  "Configuration example only (not an experiment authorization)".
- `docs/stress_design.md` updated with the TASK-024 provenance section
  (allowlist scope, `.env`/results/stores/caches/build/worlds excluded,
  "A fingerprint is not a clean commit").
- `docs/experiment_standard.md`: §1 now requires clean commit +
  `--require-clean-source` + frozen preregistration for formal runs, and states
  "A source fingerprint is necessary provenance but does not replace the clean
  commit"; §2 ladder rows are semantics-version-typed with explicit
  never-pool rules and the de-authorization of noise >50 and failure-learning
  >50.
- CLI help lists the **actual** registered backends and scenarios
  (`python -m minemembench run --help` → backends `graphiti, letta, mem0,
  none, vector`; scenarios `delayed_recall, failure_learning,
  memory_noise_stress, world_update`), matching `memory/registry.py` and
  `scenarios/registry.py`.
- `framework_registry.yaml` was **not** created (verified absent).

---

## 3. Cross-cutting safety / compatibility checks — PASS

- **No protocol diff:** `git diff --stat -- docs/protocol.md` → 0 lines.
- **No backend-name branches:** grep over `agent/planner.py`,
  `core/runner.py`, `scenarios/*.py`, `core/provenance.py` finds no
  `if backend == "mem0"/"letta"/…` logic; only the bookkeeping
  fields `memory_backend`/`stats.backend` and allowlist filenames.
- **No planner/action behavior change:** planner.py contains no provenance
  references; TASK-024 touches only provenance/fairness/CLI-campaign/docs/tests.
- **No secret/path leakage in manifest fields:** manifest carries
  `results_dir`/`stores`/log paths (user-specified output locations, pre-existing
  behavior), relative source paths + sizes + SHA-256 (no content), and git
  commit/hash fields. No `.env` value, API key, or absolute source path is
  recorded.
- **No network in tests:** new tests use fakes; the only `httpx` usage in the
  suite is `httpx.MockTransport` (existing tests).
- **Old evidence stays readable:** old manifests (schema-less and v2/v3) and
  result JSON load without the new fields.

---

## 4. Test matrix

| Suite | Command | Result |
|---|---|---|
| Full Python | `.venv\Scripts\python -m pytest -q` | **368 passed** (×3 runs, 0 skipped) |
| Provenance | `test_provenance.py` | 6 passed |
| Campaign runner + controlled mode | `test_controlled_mode.py` | 65 passed |
| CLI loop | `test_run_loop.py` | 4 passed |
| Fairness | `test_fairness.py` | green |
| Scenario params | `test_scenario_params.py` | green |
| Focused combined | provenance+controlled_mode+run_loop+fairness+scenario_params | 108 passed |
| TypeScript | `cd minecraft; npm test` | **34 passed** |
| TypeScript build | `cd minecraft; npm run build` | OK |
| Whitespace | `git diff --check` | exit 0, no errors |
| Independent recompute | temp-dir `qa024_provenance.py` | 47 checks, 0 failures |

---

## 5. Findings

### Critical — none

### High — none

### Medium — none

### Low

- **L-1 (provenance.py, junction-in-repo bypass of forbidden-path filter).**
  `_is_forbidden` filters on the *relative* path parts only, and Windows
  directory **junctions** are invisible to `Path.is_symlink()`. A junction
  planted *inside* the allowlist glob scope pointing at `results/` (or another
  forbidden dir) is not rejected: its relative path contains no forbidden part,
  `is_symlink()` is `False`, and `resolve()` stays inside the repo, so the
  junctioned file's content is hashed. Verified in a temp tree:
  `capture_source_provenance(tree, globs=("src/**/*.py",), …)` accepted
  `src/evil/evil.py` → `results/evil.py`. Not exploitable in the current repo
  (no junctions exist; `server`/`stores`/`.env` are excluded by the same check
  and the real globs cannot reach them), so **severity Low**.
  Minimal repair for A: after computing `resolved`, also run `_is_forbidden`
  on `resolved.relative_to(root)` (and/or reject any path whose resolved
  target contains a forbidden part). **Status: RESOLVED (2026-08-09 post-fix
  verification §7).**
- **L-2 (cosmetic).** `docs/development_plan.md` lines 3–4 end with trailing
  whitespace (Markdown hard line breaks). Harmless; `git diff --check` does not
  flag new untracked files. Optional cleanup. **Status: RESOLVED (2026-08-09
  post-fix verification §7).**

---

## 6. Files read / created

Files read (all, read-only): see §0 list; plus on-disk campaign manifests and
result JSON under `results/`.

Only repo artifact created: `docs/agents/qa/QA-024-PROVENANCE.md`.

Minimal repair handed to A if any defect is accepted: apply L-1's resolved-path
forbidden check; nothing else.

---

## 7. Post-fix verification (2026-08-09)

Agent A accepted both Low findings from §5 and applied the minimal repairs.
This section is an independent post-fix re-verification of the changed source
tree (same mode as §0: offline, read-only on the repo, no `.env`/network/git
mutation/campaign). Commands and results:

### Evidence read for the exact latest diff

- `benchmark/minemembench/core/provenance.py` `_discover_source_paths`
  (lines 161–168): after computing `resolved`, the code now re-runs
  `_is_forbidden(resolved.relative_to(root))` and raises
  `ValueError("resolved provenance input reaches forbidden path: …")` — exactly
  the minimal repair L-1 proposed. The pre-existing symlink rejection and
  `resolve().relative_to(root)` escape check are unchanged.
- `benchmark/tests/test_provenance.py`
  `test_resolved_directory_alias_cannot_tunnel_into_forbidden_tree`
  (lines 92–127): builds `src/alias` as a real directory **junction** on Windows
  (`cmd /c mklink /J`) pointing at `results/`, then asserts
  `capture_source_provenance(…, required_files=("anchor.txt", "src/alias/hidden.py"))`
  raises `ValueError` matching "resolved provenance input reaches forbidden".
  On non-Windows it falls back to a directory symlink (also rejected, via the
  symlink check); on junction/symlink creation failure it skips rather than
  fails spuriously.
- `docs/development_plan.md`: trailing-whitespace scan
  (`Select-String -Pattern '[ \t]+$'`) returns **0 matching lines** (was 2).

### Independent junction reproduction (temp dir, no repo writes)

Script `qa024_postfix_junction.py` (OS temp dir
`C:\Users\30573\AppData\Local\Temp\opencode\`) planted a real Windows junction
`src/evil -> results/` inside a temp tree, then ran
`capture_source_provenance(tree, globs=("src/**/*.py",), required_files=("anchor.txt",))`.
Result: `ValueError: resolved provenance input reaches forbidden path:
results/evil.py` — the junctioned file is **not** hashed. The probe also
confirmed `is_symlink() == False` for the junction, so the resolved-path
re-check (not the symlink guard) is what closes L-1.

### Test runs on the changed tree (no prior-run reuse)

| Suite | Command | Result |
|---|---|---|
| Provenance (incl. new junction test) | `.venv\Scripts\python -m pytest -q benchmark/tests/test_provenance.py` | **7 passed** (was 6) |
| Focused TASK-024 (provenance + controlled_mode + run_loop + fairness + scenario_params) | `.venv\Scripts\python -m pytest -q benchmark/tests/test_provenance.py benchmark/tests/test_controlled_mode.py benchmark/tests/test_run_loop.py benchmark/tests/test_fairness.py benchmark/tests/test_scenario_params.py` | **109 passed** (was 108) |
| Full Python suite | `.venv\Scripts\python -m pytest -q` | **369 passed** in 102.87s (was 368) |

### Static checks

- `git diff --check` → **exit 0, no whitespace errors** (only pre-existing CRLF
  conversion warnings). Combined with the §7 zero-match scan of
  `docs/development_plan.md`, L-2's trailing spaces are confirmed removed even
  though `git diff --check` does not inspect untracked files.
- `git diff --stat -- docs/protocol.md` → **empty** (0 lines changed); the wire
  contract is untouched by the repairs.
- No production/test/result file was modified by this verification; the only
  repo artifact changed is this report. No `.env` access, no network, no git
  mutation, no campaign.

### Final status

Both §5 Low findings are **RESOLVED and verified**:

- **L-1** — fixed in source (resolved-path forbidden re-check) and locked by a
  junction regression test; independently reproduced (junction tunneling now
  raises `ValueError`).
- **L-2** — `docs/development_plan.md` trailing whitespace removed (0 matches).

Full suite is green on the repaired tree. No new findings from the re-run;
the §1 verdict (PASS) is unchanged.
