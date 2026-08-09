# A-APPROVAL-025 — Source-freeze preflight design

Date: 2026-08-09
Reviewer: Agent A
Verdict: **approved for implementation; no experiment authorized**

The validator belongs in `core/provenance.py`, next to the provenance model,
because the standalone verifier and Controlled runner must enforce one meaning
of clean source. The script is an inspection interface only: it may hash the
explicit allowlist and run read-only git status commands, but may not write a
manifest, touch results, start services or inspect `.env`.

The source fingerprint check precedes optional commit matching in diagnostics;
formal readiness requires all of: git available, worktree clean, expected
source fingerprint equal and (when frozen) expected commit equal. The compact
output may expose hashes/counts/booleans, never source content or absolute
paths.

A passing verifier is necessary but insufficient for a formal campaign. A
frozen preregistration, C preflight and explicit A authorization remain
separate gates.
