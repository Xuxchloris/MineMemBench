# A-PREFLIGHT-027 — M15 Controlled Formal V1 gate

Date: 2026-08-11 Asia/Shanghai
Owner/executor: Agent A (TASK-027 single-agent authorization)
Verdict: **PASS — ready for the authorized preregistration freeze; Formal runs started=0**

## Frozen candidate identity

```text
parent_commit=592e4ab72193fa541a1a536a1eab2752b03acad6
source_tree_fingerprint=f21af111b86926aca18e77846e3b37f52d7b235facdc242daf0977a314ffc38a
source_file_count=126
analysis_entrypoint_sha256=904ae5f90b004792afdf5321c9f2423da3af11735a50f0532e98dbdcb6086b35
formal_results_dir=results/formal_m15_v1_20260811
formal_runs_started=0
```

The exact producer commit is the clean commit containing this report and
`docs/preregistration_m15_formal_v1.md`. It is resolved after commit without
amend, then verified and written into the pre-run Formal study manifest.

## Gate evidence

| Gate | Result |
|---|---|
| Baseline branch/local/remote sync before implementation | PASS — `main`, local HEAD, `origin/main`, and remote main all `592e4ab...` |
| Preregistration complete | PASS — exact study id, cells, seeds, configs, endpoints, policies and statistics fixed |
| Exact campaign plan | PASS — real campaign preflight accepts all 8 cells; 320 unique scheduled runs |
| Fresh seeds | PASS — no historical JSON match for seeds 1001–1010 |
| Formal results root | PASS — absent/new; runs started=0 |
| Synthetic analysis tests | PASS — 15 tests cover all required integrity/statistical cases and producer preflight |
| Python full suite | PASS — 444 passed |
| TypeScript suite | PASS — 40 passed |
| TypeScript build | PASS |
| Python analysis/producer compile | PASS |
| `git diff --check` | PASS — line-ending notices only |
| Changed-file scope | PASS — exactly 12 expected TASK-027 files; no unexpected file |
| Secret scan | PASS — no key/token/private-key pattern; `.env`, results, logs, stores, caches and build outputs excluded |
| `docs/protocol.md` | PASS — unchanged; SHA-256 `7abe548a...` |
| Source provenance | PASS — fingerprint and 126-file count match preregistration candidate |
| Real Controlled fixture smoke | PASS — fresh Node `canonical` and `lifetime_route_v1` identities matched |
| Reset/isolation | PASS — full tests plus strict live Letta old/fresh scope retrieval both zero |
| Letta strict live | PASS — server 0.16.8 exact add/retrieve, update, reset and fresh-scope isolation |
| Docker identity | PASS — Letta and Ollama images pinned by verified SHA-256 digests |
| Planner live preflight | PASS — `deepseek-v4-flash`, temperature 0.0, one connectivity call succeeded |
| Backend/scenario registry | PASS — Formal allowlist is none/vector/mem0/letta; Graphiti excluded; exact four scenarios registered |

## Integrity decisions

- Calibration and Formal are separate directories, seeds and study identities.
- Failure-learning v4 is diagnostic only and absent from the Formal matrix.
- No retry, replacement, result-based extension or exclusion path exists in
  the one-shot Formal producer.
- The analyzer fails before output on identity, completeness, uniqueness,
  fairness, reset, fixture, event-stream, retrieval or endpoint mismatch.
- Exact McNemar, paired risk difference, deterministic paired-bootstrap CI and
  Holm family were implemented and tested before run 1.
- Dashboard is unchanged except for later documentation; TASK-027 performs no
  UI/UX refactor.

## Release decision

The candidate may receive the single authorized preregistration freeze commit
and push. After the clean commit's exact SHA and unchanged source fingerprint
pass `verify_source_freeze.py --require-clean`, the one-shot 320-run producer
may start without further authorization. Any failed post-commit gate cancels
that permission and no Formal run may start.
