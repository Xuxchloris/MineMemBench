# TASK-023 — Failure-learning v2 count-50 stress probe

Issued by: Agent A  
Executor: Agent A; Agent C independently audits  
Status: **authorized diagnostic execution**

Run exactly one fresh Controlled campaign:

- scenario `failure_learning`
- `failure_semantics_version=observed_precondition_v2`
- `interference_count=50`
- backends `none,vector,mem0,letta`
- paired seeds `42,43,44`
- 12 runs total
- output `results/stress_controlled_failure_learning_v2_count50_round1/`

Use the unchanged TASK-020 implementation and campaign runner. The output
directory must not exist before launch. Use campaign-local stores and one fresh
`warded_hostiles_v1` fixture per run. Stop on the first failure; perform no
retry, replacement, exclusion, parameter adjustment, or code change during the
campaign. Preserve the manifest, all result JSON, and stdout/stderr logs.

Agent C must independently re-derive campaign integrity, fairness, event-stream
and source-evidence fingerprints, ground-truth leakage guards, step-0 failure
rank/recall/top-1/precision/interference rate, ordered preparation/failure
repetition/transfer completion, tokens, latency, errors, and cross-episode
isolation. C must compare count 50 descriptively with the accepted paired count
0 and count 10 campaigns.

Stop after C reports. This task does not authorize count 100 or any wider
sample, ranking, effect size, cost-efficiency claim, Native Minecraft claim, or
formal Failure Point.
