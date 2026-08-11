# A-PREFLIGHT-027-ATTEMPT2 — M15 Controlled Formal V1 recovery gate

Date: 2026-08-11 Asia/Shanghai
Owner/executor: Agent A (TASK-027 single-agent authorization)
Verdict: **PASS — ready for the recovery preregistration freeze; attempt-2 runs started=0**

## Frozen candidate identity

```text
recovery_parent=7c96df88c4208e47217da984f61798be051f56da
study_id=m15-formal-v1-controlled-20260811-attempt2
source_tree_fingerprint=ebfe9172dbe83abb5d76c2f8459ef346b8888d4f8e2bafca4d09799566bad3b3
source_file_count=126
analysis_entrypoint_sha256=904ae5f90b004792afdf5321c9f2423da3af11735a50f0532e98dbdcb6086b35
protocol_sha256=7abe548a0dcd8d4b2382f70b8d0bf31d108d89bf3088db82186cf7fdbb0f7268
formal_results_dir=results/formal_m15_v1_20260811_attempt2
formal_runs_started=0
```

The exact producer commit is the clean commit containing this report and
`docs/preregistration_m15_formal_v1_attempt2.md`. It is resolved after commit
without amend, verified, pushed, and written into the pre-run study manifest.

## Recovery boundary

Attempt 1 is preserved and abandoned. Its frozen identity remains commit
`7c96df88...`, fingerprint `f21af111...`; child manifests contain 271 `ok`,
one `failed` and 48 `pending` slots, with 0 retries and 0 exclusions. The
failure log records DeepSeek DNS `getaddrinfo failed`. The frozen analyzer
rejects the old root before output. Evidence hashes and the no-splice decision
are fixed in `A-INCIDENT-027-ATTEMPT1.md`.

No attempt-1 task-success metric, pairwise comparison, Failure Point or
ranking was inspected. Attempt 2 uses a new root and fresh seed block.

## Gate evidence

| Gate | Result |
|---|---|
| Branch/local/remote recovery parent | PASS — `main`, local HEAD, `origin/main`, remote main all `7c96df88...` before recovery edits |
| Attempt-1 preservation | PASS — old root retained; four evidence hashes recorded; no deletion/retry/resume |
| Preregistration complete | PASS — exact new id/root/fingerprint, cells, seeds, configs, endpoints, policies and statistics fixed |
| Exact campaign plan | PASS — 320 planned and 320 unique `(scenario,cell,backend,seed)` slots |
| Fresh seeds | PASS — 1011–1020; no matching seed field in historical result JSON |
| Attempt-2 results root | PASS — absent/new; runs started=0 |
| Synthetic analysis/producer tests | PASS — 17 tests, including exact schedule, all integrity/statistical requirements, wrong expected count and failed-attempt accounting |
| Python full suite | PASS — 446 passed in 110.58 s |
| TypeScript suite | PASS — 40 passed |
| TypeScript build | PASS |
| Python compile/import | PASS through full suite and focused producer imports |
| `git diff --check` | PASS — line-ending notices only |
| Changed-file scope | PASS — exactly 9 expected recovery files before adding this report; no unexpected paths |
| Secret scan | PASS — no key/token/password/private-key pattern; `.env`, raw results, logs, stores, caches and builds excluded |
| `docs/protocol.md` | PASS — unchanged; SHA-256 `7abe548a...` |
| Candidate source provenance | PASS — `ebfe9172...`, 126 allowlisted files; docs-only additions do not alter it |
| Real Controlled fixtures | PASS — fresh Node `canonical` and `lifetime_route_v1` identities matched complete expected visible state |
| Reset/isolation | PASS — full fairness/backend tests plus strict live Letta completed/fresh scope both zero |
| Letta strict live | PASS — server 0.16.8 exact add/retrieve, update, reset and fresh-scope isolation |
| Backend versions | PASS — `mem0ai==2.0.17`, `letta-client==1.12.1` |
| Docker identity | PASS — Letta and Ollama containers use the exact preregistered image digests |
| DNS stability check | PASS — 10/10 consecutive A-record resolutions |
| Planner live preflight | PASS — `deepseek-v4-flash`, temperature 0.0, thinking disabled; 3/3 connectivity calls succeeded (0.590/0.597/0.840 s) |
| Backend/scenario registry | PASS — Formal allowlist none/vector/mem0/letta; Graphiti and failure-learning excluded; exact four scenarios |

## Integrity decisions

- The attempt-2 code change does not alter scenarios, prompt, planner,
  MemoryBackend behavior, backend settings, treatment parameters, endpoints or
  statistics. It changes only study identity/seeds/root and producer audit
  accounting required after the stopped attempt.
- Root `actual_runs` counts producer-ok evidence; root `started_runs` counts
  both producer-ok and producer-failed slots. A stop now records an explicit
  reason. The analyzer requires explicit `expected_runs=320`.
- Calibration, diagnostics, attempt 1 and attempt 2 are separate roots and
  identities. The attempt-2 analyzer reads only the path supplied to it.
- No retry, replacement, result-based extension or exclusion path exists.
- Exact McNemar, paired risk difference, deterministic paired-bootstrap CI,
  Holm family and non-interpolated Failure Points remain unchanged from the
  prospective attempt-1 design.
- Dashboard and `docs/protocol.md` are unchanged.

## Release decision

The candidate may receive the TASK-027 recovery freeze commit and push. After
the exact commit and unchanged candidate source fingerprint pass strict clean
verification, local/remote identity is synchronized, repeated DNS/planner
checks remain green, and the attempt-2 root is still absent, the one-shot
320-run producer may execute once. Any failed post-commit gate cancels that
permission; no Formal run may start until all gates pass again.
