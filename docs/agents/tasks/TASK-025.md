# TASK-025 — Read-only source-freeze preflight

Issued by: Agent A
Executor: Agent A (B unavailable); Agent C independently audits
Status: **authorized implementation; no campaign authorized**

## Purpose

Give the external git review owner and Agent C one safe command that proves a
candidate formal-study revision is clean and matches the A-accepted producer
source fingerprint without creating a result directory, starting services or
running a campaign.

TASK-024 enforces clean provenance inside the campaign runner, but using that
runner merely to test a clean revision risks continuing into execution. This
task adds a dedicated read-only gate; it does not relax the external-commit or
pre-registration requirements.

## Requirements

1. Add a backend-neutral source-freeze validation function in
   `core/provenance.py`. It must distinguish git unavailable, dirty tree,
   source-fingerprint mismatch and optional commit mismatch.
2. Add `scripts/verify_source_freeze.py`. It must capture the same
   `SourceProvenance`, print only non-secret compact provenance, and perform no
   filesystem, git, service or network mutation.
3. Support `--require-clean`, `--expected-source-fingerprint` and
   `--expected-git-commit`. Invalid expectations or failed checks return exit
   code 2 with an actionable reason; a matching candidate returns 0.
4. Reuse the shared validator from `run_controlled_campaign.py` so the campaign
   and standalone verifier cannot drift on clean-source semantics.
5. Include the verifier itself in the deterministic producer-source allowlist.
6. Add hermetic tests for clean, dirty, unavailable, mismatch and success
   paths, plus proof that the verifier is allowlisted and makes no writes.
7. Document the exact external freeze command. Do not claim the current dirty
   tree is formal or authorize an experiment.

## Constraints

- Do not change `docs/protocol.md`.
- Do not read or print `.env` or secrets.
- No network, service start/stop, campaign, git add/commit/push or result data.
- Preserve old result and manifest compatibility.
- Do not add backend-name branches or change benchmark behavior.

## Acceptance

- Focused and full Python tests pass.
- On the current dirty tree, diagnostic mode succeeds while reporting
  `clean=false`; `--require-clean` exits 2.
- C independently reviews source, CLI behavior and no-write/no-secret scope.
- A performs final architectural/research review before external freeze.
