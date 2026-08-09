# A-IMPLEMENTATION-025 — Read-only source-freeze preflight completion

Date: 2026-08-09 09:59 Asia/Shanghai
Owner: Agent A (implementation takeover while Agent B is unavailable)
Independent verifier: Agent C
Status: **implementation complete and independently verified; no campaign authorized**

## Outcome

The external review owner and C now have a dedicated read-only source-freeze
command. It captures the same deterministic provenance as the Controlled
campaign, can require a clean tree and exact source/commit identities, and
cannot continue into an experiment or create a results directory.

## Implemented scope

- Added pure backend-neutral `source_freeze_error` validation to
  `core/provenance.py`.
- Replaced the campaign runner's duplicated clean-source condition with that
  shared validator.
- Added `scripts/verify_source_freeze.py` with:
  - diagnostic read-only mode;
  - `--require-clean`;
  - `--expected-source-fingerprint`;
  - `--expected-git-commit`;
  - strict digest validation and exit code 2 on failed gates.
- Compact output contains only schema/hash/count/boolean/commit fields; it
  contains no source content, absolute source paths or `.env` values.
- Added the verifier to the producer allowlist and added hermetic coverage for
  clean, dirty, unavailable, mismatch, parser and no-write paths.
- Documented the exact external freeze command in README.

## Verification

Agent A:

```text
focused provenance/source-freeze/Controlled suites: 81 passed
full Python suite after no-bytecode hardening: 378 passed in 93.87s
real dirty-tree diagnostic: exit 0, clean=false
real dirty-tree --require-clean: exit 2
git diff --check: exit 0 (CRLF warnings only)
docs/protocol.md diff: empty
```

Agent C independently reproduced:

```text
source-freeze + provenance + Controlled: 81 passed
Controlled runner: 65 passed
full Python suite after no-bytecode hardening: 378 passed in 91.30s
real diagnostic/strict/no-mutation and hermetic identity matrix: PASS
fresh bytecode-prefix probe: zero project/verifier pyc writes
```

Full C evidence: `docs/agents/qa/QA-025.md`.

## Current identity and boundary

TASK-025 intentionally changed the producer set, and A's accepted no-bytecode
hardening changed two allowlisted files once more. The final current
fingerprint is
`8606370026c2bde49737ccb945c9b69ed4aa9cb64090aa06df6cb7c23e24e55f`
over 106 files. TASK-024's `50e9…` and the pre-hardening `d69a…` remain
historical identities only.

The current tree is still dirty at HEAD `cbaa276`; diagnostic matching does not
make it formal. No service or campaign was started. The external review owner
must create a clean reviewed commit before the exact strict command can pass.
