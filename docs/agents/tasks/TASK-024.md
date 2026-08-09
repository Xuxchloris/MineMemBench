# TASK-024 — Source provenance gate and documentation freeze

Issued by: Agent A  
Executor: Agent A (B unavailable); Agent C independently audits  
Status: **authorized implementation; no campaign authorized**

## Purpose

Close the highest-value reproducibility gap identified by corrected
`QA-024-COMPLETION-AUDIT`: future evidence must identify the exact producer
source tree and fail if the tree changes mid-campaign. At the same time, align
the public/current planning documents with the accepted M15 evidence.

A source fingerprint improves provenance but does not make a dirty tree clean,
formalize existing results, or replace the external review agent's commit.

## Implementation requirements

1. Add a deterministic source-provenance utility under the Python core.
   It must hash a documented, sorted set of runtime, adapter, test, dependency,
   compose, configuration-schema and wire-contract files using SHA-256.
   It must include relative path + content digest, reject missing required
   anchors, and exclude `.env`, results, stores, caches, build output and
   user/runtime data.
2. Record read-only git provenance when available: commit, dirty state and a
   normalized status fingerprint. Git absence must be explicit, never guessed.
3. Add optional backward-compatible provenance fields to `FairnessRecord`.
   Every new CLI scenario run must populate them.
4. Bump new Controlled manifests to `controlled-campaign/v4` and pre-register
   the complete provenance record before run 1. Every produced result must
   match the manifest source fingerprint/file count/git fields; mismatch stops
   the campaign and preserves partial evidence.
5. Add `--require-clean-source` to the campaign runner. It must fail before
   creating the output directory when git is unavailable or the tree is dirty.
   Default diagnostic behavior may run dirty but must record that fact.
6. Add a formal-study pre-registration template. It must freeze scenario and
   semantics version, cells, backends, paired seeds, sample size, primary and
   secondary endpoints, exclusion/N/A/retry/stopping rules, analysis plan,
   commit and expected source fingerprint. The template does not authorize a
   formal run.
7. Repair current documentation drift without changing research decisions:
   create `docs/development_plan.md`; update README M2/M3/M15 status and current
   v2 scenario/evidence boundaries; update `docs/stress_design.md`; make CLI
   help list the actual registered backends/scenarios. Do not create
   `framework_registry.yaml` in this task.

## Safety and compatibility

- Do not change `docs/protocol.md`.
- Do not read/record `.env` or secrets.
- No network in tests and no campaign execution.
- Old result JSON and manifests remain readable.
- No backend-name branches in planner/scenario/runner.
- No git add/commit/push.

## Acceptance

- Unit tests prove fingerprint determinism, one-byte/file mutation sensitivity,
  stable ordering, exclusion of forbidden paths, explicit git-unavailable
  behavior, old FairnessRecord compatibility, manifest/result matching and
  fail-closed mismatch/clean-source behavior.
- Full Python suite passes; TypeScript tests/build pass if touched.
- C independently inspects scope and reruns the relevant/full test suites.
- A performs final architectural/research review before any later campaign.
