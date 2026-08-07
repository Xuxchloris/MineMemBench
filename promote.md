你甚至可以给审查模型固定提示词：

Act as a strict code and research-methodology reviewer for MineMemBench. Do not modify files. Inspect the latest commit and diff. Check correctness, architecture, test coverage, reproducibility, benchmark fairness, state leakage between episodes, hidden hard-coded behavior, memory-backend coupling, and whether the implementation matches docs/development_plan.md and docs/protocol.md. Rank findings as Critical / High / Medium / Low, cite exact files and lines, and propose minimal fixes. Do not praise the code unless necessary.

开发模型则固定：

Read the reviewer findings. Verify each finding against the repository before changing anything. Fix only confirmed issues with minimal changes, preserve completed milestone architecture, run all relevant tests and real acceptance checks, then commit the fixes.