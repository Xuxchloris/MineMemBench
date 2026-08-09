# A-APPROVAL-024 — Provenance gate design approval

Date: 2026-08-08 23:39 Asia/Shanghai  
Reviewer: Agent A  
Input: corrected `docs/agents/qa/QA-024-COMPLETION-AUDIT.md`  
Verdict: **APPROVED for implementation; no experiment authorized**

## Architectural decision

The provenance recorder belongs in the Python core because both the CLI result
path and the Controlled campaign runner must derive the same backend-neutral
identity. It may inspect source/config files and read git metadata, but must not
mutate git or inspect runtime secrets.

The campaign manifest owns the pre-run provenance record. Each result's
`FairnessRecord` carries a compact compatibility copy, and the runner validates
the two. This detects a source change between scheduled runs without exposing
backend internals or affecting planner behavior.

## Research decision

The recorder is necessary provenance, not immutability. Existing dirty-tree
diagnostics remain diagnostic. Formal work still requires the external review
owner to produce a clean reviewed commit, a frozen preregistration, and an
A-authorized sample. `--require-clean-source` is an enforcement mechanism, not
authorization.

## Severity carried into implementation

- **Critical:** never hash/read `.env`, results, stores, caches or user data.
- **High:** source changes mid-campaign must fail closed; old evidence must
  remain loadable; no result may claim clean provenance from a dirty tree.
- **Medium:** dependency/wire/config inputs must be included; git-unavailable
  state must be explicit; docs must distinguish implemented, diagnostic and
  formal status.
- **Low:** update stale CLI help/test naming while preserving behavior.
