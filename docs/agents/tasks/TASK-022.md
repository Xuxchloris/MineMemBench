# TASK-022 — Failure-learning v2 mild-interference smoke

Issued by: Agent A  
Executor: Agent A; Agent C independently audits  
Status: **authorized diagnostic execution**

Run exactly one fresh Controlled campaign:

- scenario `failure_learning`
- `failure_semantics_version=observed_precondition_v2`
- `interference_count=10`
- backends `none,vector,mem0,letta`
- seeds `42,43,44`
- 12 runs total

Use the unchanged TASK-021 implementation and campaign runner. Fresh output
directory, campaign-local stores, one fresh warded fixture per run, stop on
first failure, no retry/replacement/exclusion. Preserve manifest/results/logs.

Agent C must re-derive all integrity/retrieval/behavior metrics and compare
the paired count-10 result descriptively with the accepted count-0 control.
No count50 or expansion is authorized by this task.
