# A-INCIDENT-027 — Formal V1 attempt 1 producer stop

Date: 2026-08-11 Asia/Shanghai
Owner/executor: Agent A (TASK-027 single-agent authorization)
Severity: **High — the study is incomplete and cannot support Formal claims**
Disposition: **ABANDONED; retained for audit; never retry, resume, splice, or analyze as Formal V1**

## Frozen identity

```text
study_id=m15-formal-v1-controlled-20260811
results_root=results/formal_m15_v1_20260811
producer_commit=7c96df88c4208e47217da984f61798be051f56da
source_tree_fingerprint=f21af111b86926aca18e77846e3b37f52d7b235facdc242daf0977a314ffc38a
source_file_count=126
```

The producer commit was clean, pushed to `origin/main`, and passed strict
source-freeze verification before run 1. The frozen source identity still
passed after the stop; no source, configuration, prompt, treatment, seed, or
backend setting changed during the attempt.

## Stop evidence

The first three campaigns completed. The fourth campaign stopped on its 72nd
scheduled slot (zero-based manifest index 71):

```text
scenario=long_lived_memory
backend=none
cell=lifetime_l3
seed=1006
returncode=1
stderr=error: agent loop failed: LLM request failed: [Errno 11001] getaddrinfo failed
```

This was an external planner-DNS/producer failure, not a valid
`task_success=0` outcome. DNS resolution recovered after the study had
stopped, but the frozen no-retry/no-replacement policy forbids continuing the
old identity.

| evidence state | count |
|---|---:|
| producer status `ok` | 271 |
| producer status `failed` | 1 |
| still `pending` | 48 |
| retries | 0 |
| exclusions | 0 |
| scheduled slots | 320 |

The attempt-1 root manifest recorded `actual_runs=271` and
`started_runs=271`; the child manifests prove 272 started slots (271 `ok` + 1
`failed`). This undercount is an audit-accounting defect in the root producer
manifest, not a change to an experimental outcome. Attempt 2 fixes the root
accounting and adds an explicit stop reason before its new freeze.

## Immutable evidence hashes

```text
formal_study_manifest.json
  8f7798df48bf74dbdad82fdb51c80f2caee4f392a5b09f0a1ac7dac4a2ea9086
long_lived_memory/campaign_manifest.json
  e0f0e06a8e094dddf84a9034a3492d46aa4787b4b86d113eb84aef82f8ca1f12
long_lived_memory/logs/run_071_none_lifetime_l3_seed1006.stdout.log
  cc2f488ad4b2864ca73d312517e9555245d54222f4d3208a6ce9bee1dbe49b28
long_lived_memory/logs/run_071_none_lifetime_l3_seed1006.stderr.log
  07b5247ff527bb4d6ad8ea6e5b9c3eaa277c518d625449212e9d6abd175f2a13
```

Raw evidence remains under the original results root and is gitignored. It
must not be deleted or pooled with a later attempt. The frozen analyzer
correctly rejects the root with `formal producer status is not complete` and
writes no analysis outputs.

## Recovery decision

Attempt 2 must use all of the following:

- a new study id and new empty results root;
- a new preregistration and clean pushed producer commit;
- a fresh continuous paired seed block not present in historical results;
- the same eight cells, four backends, Controlled mode, planner, prompt,
  backend settings, endpoints, statistical family and sample size;
- all pre-Formal gates repeated before run 1;
- no reuse, retry, replacement, exclusion, or statistical inspection of
  attempt-1 outcomes.
