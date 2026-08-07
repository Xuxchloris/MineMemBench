你现在继续开发项目：

# MineMemBench
Benchmarking Long-Term Memory Frameworks for Embodied LLM Agents in Minecraft

当前状态：

M1 ✅ 仓库骨架、README、protocol、Docker、配置
M2 ✅ Minecraft 1.20.4 + Mineflayer Bot
M3 ✅ Python ↔ TypeScript Bot Bridge

当前已经验证：

- Minecraft 真实服务器可启动
- BenchBot 可真实登录
- Python 可以读取 WorldState
- Python 可以发送 chat / move_to
- Mineflayer 可以真实寻路
- TS / Python 测试全部通过
- 当前代码已经 push 到 GitHub

不要重构 M1-M3。
不要重复下载已经存在的依赖。
从 M4 开始。

==================================================
总原则
==================================================

项目研究问题：

在固定 LLM、固定 Minecraft 环境、固定工具和固定任务的情况下：

“不同长期记忆框架如何影响 Embodied LLM Agent 的长期行为？”

重点不是：

“它有没有记住一句话”

而是：

“过去经验是否通过不同 Memory Framework 影响未来行为和任务表现？”

控制变量：

- 同一个 Minecraft version
- 同一个 world seed
- 同一个 LLM
- 同一个 system prompt
- 同一个 tool set
- 同一个 temperature
- 同一个 benchmark scenario

唯一主要变量：

Memory Backend

禁止：

- 人为写死“某事件 → 某行为”
- if previous_failure: prepare_armor()
- 把行为结果硬编码进 Memory
- 伪造 benchmark 结果
- 第一阶段加入人格、情绪、trust 数值
- 第一阶段加入多 Agent
- 第一阶段加入视觉/多模态
- 为了 Demo 绕过真实 Agent Loop

==================================================
M4 — LLM Agent Loop
==================================================

目标：

实现：

WorldState
↓
NoMemoryBackend
↓
LLM Planner
↓
Structured Action
↓
Mineflayer
↓
New WorldState

第一阶段只使用：

NoMemoryBackend

不接 Mem0 / Letta。

--------------------------------
LLM Provider
--------------------------------

实现统一接口，例如：

class LLMProvider(ABC):

    async def complete(
        self,
        messages,
        response_schema=None
    ):
        ...

使用 OpenAI-compatible API。

环境变量：

LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
LLM_TEMPERATURE

API KEY：

只允许从 .env 加载。

不得：

- 写入代码
- 写入日志
- commit
- 打印完整 key

当前默认模型使用我配置好的 DeepSeek 模型。

如果 SDK/API 参数不确定：

查询当前官方 API 文档。

不要凭记忆猜接口。

--------------------------------
Planner
--------------------------------

输入：

1. Current Goal
2. Current WorldState
3. Retrieved Memory
4. Available Tools

输出严格 JSON：

{
  "action": "move_to",
  "arguments": {
    "x": 10,
    "y": -60,
    "z": 20
  },
  "reason": "..."
}

使用 Pydantic 验证。

必须：

- JSON invalid → retry
- unknown action → reject
- invalid arguments → reject
- retry 有最大次数

--------------------------------
Trace
--------------------------------

每次决策保存：

run_id
episode_id
step
goal
world_state
retrieved_memory
prompt
llm_response
parsed_action
action_result
new_world_state
latency
token_usage

--------------------------------
M4真实验收
--------------------------------

必须启动真实 Minecraft。

测试：

Goal：
移动到指定坐标并发送一句聊天。

要求：

LLM自己选择正确 Tool。

完成：

WorldState
→ LLM
→ Action
→ Minecraft
→ New WorldState

保存完整 Trace。

验收完成后：

运行 TS + Python tests。

创建 commit：

feat: add embodied LLM agent loop

不要立即进入 M5。
先总结：

- 修改文件
- 测试数量
- 真实验收结果
- 一条完整 trace

==================================================
M5 — Minecraft Semantic Event Layer
==================================================

目标：

把 Minecraft 低级事件转换成 Memory Framework 可以理解的统一 ExperienceEvent。

不要把每一个 tick 存成 Memory。

--------------------------------
ExperienceEvent Schema
--------------------------------

至少：

{
  "event_id": "...",
  "episode_id": "...",
  "timestamp": "...",
  "event_type": "...",
  "actor": "...",
  "target": "...",
  "location": {...},
  "context": {...},
  "outcome": {...},
  "source_events": [...]
}

已有 EventType 可以扩展。

第一版支持至少：

PLAYER_SHARED_RESOURCE
PLAYER_ATTACKED_AGENT
PLAYER_HELPED_AGENT

AGENT_DIED

TASK_STARTED
TASK_SUCCEEDED
TASK_FAILED

LOCATION_DISCOVERED
RESOURCE_DISCOVERED

WORLD_FACT_CREATED
WORLD_FACT_UPDATED

--------------------------------
原则
--------------------------------

Semantic Event Layer 只回答：

“发生了什么？”

不能回答：

“Agent应该怎么想？”

例如：

允许：

Player gave Agent food while Agent food level was low.

禁止自动变成：

Player is trustworthy.

后者应该由 Memory Framework 自己产生。

--------------------------------
事件抽取
--------------------------------

例如：

低层：

agent health low
hostile entity nearby
player attacks hostile
hostile dies
agent survives

可以组合成：

PLAYER_HELPED_AGENT

但是：

规则必须透明、可测试。

所有高层事件必须能追溯 source_events。

--------------------------------
M5验收
--------------------------------

真实 Minecraft：

制造至少三个事件。

例如：

资源发现
任务失败
玩家给予物品

确认：

Mineflayer event
→ WS
→ Python
→ ExperienceEvent

完整跑通。

增加单元测试。

commit：

feat: add semantic experience event layer

==================================================
M6 — Unified Memory Benchmark Interface
==================================================

目标：

建立所有 Memory Framework 的统一接入层。

接口例如：

class MemoryBackend(ABC):

    async def add(
        self,
        event: ExperienceEvent
    ) -> None:
        ...

    async def retrieve(
        self,
        query: MemoryQuery
    ) -> list[MemoryItem]:
        ...

    async def update(
        self,
        event: ExperienceEvent
    ) -> None:
        ...

    async def reset(
        self,
        scope: MemoryScope
    ) -> None:
        ...

    async def stats(self) -> MemoryStats:
        ...

统一返回：

MemoryItem

至少包含：

content
source
timestamp
metadata
score（如果框架提供）

禁止：

Planner里出现：

if memory_backend == "mem0"

所有框架只能通过 Adapter。

--------------------------------
实现两个 Baseline
--------------------------------

1. NoMemoryBackend

永远 retrieve = []

2. SimpleVectorMemoryBackend

功能：

ExperienceEvent
→ 文本表示
→ Embedding
→ Vector Store
→ Top-K retrieval

第一版可使用：

FAISS / 本地轻量方案

目的：

不是作为最终 Memory Framework。

只是建立一个标准 RAG Memory Baseline。

--------------------------------
验收
--------------------------------

同一 ExperienceEvent：

NoMemory：
无法召回

Vector：
能够召回

测试：

add
retrieve
reset
隔离不同 episode

commit：

feat: add memory benchmark interface and baselines

==================================================
M7 — Benchmark Scenario Engine
==================================================

目标：

不让 Agent 随机玩 Minecraft。

创建：

可重复
可 Reset
可自动跑
可评分

的实验任务。

统一接口：

class Scenario(ABC):

    async def setup(...)
    async def experience_phase(...)
    async def interference_phase(...)
    async def test_phase(...)
    async def evaluate(...)

每个 Scenario 必须支持：

seed
reset
repeat

==================================================
Scenario 1 — Delayed Fact Recall
==================================================

研究：

长期事实记忆。

Experience Phase：

让 Agent 获知一个与 Minecraft 世界相关的事实。

例如：

Target chest is located at X,Y,Z.

该信息需要通过正常交互进入 Memory。

Interference Phase：

加入多个无关事件。

例如：

移动
发现普通资源
其他任务
聊天
环境事件

Test Phase：

Agent被要求：

找到目标箱子。

评估：

是否找到正确箱子。

指标：

task_success
fact_recall_accuracy
wrong_location_rate
steps
token_cost
retrieval_latency
decision_latency

--------------------------------
关键
--------------------------------

NoMemory 应该作为真实对照。

不要人为让 NoMemory 失败。

所有 Agent 获得完全相同的当前环境信息。

==================================================
Scenario 2 — World State Update
==================================================

研究：

Memory是否能处理信息变化。

Phase 1：

Agent获知：

目标位于 A。

Phase 2：

世界事实发生真实变化：

目标现在位于 B。

Agent应该获得新的 ExperienceEvent。

Phase 3：

要求找到目标。

测试：

Memory Framework：

是否仍然使用旧信息 A。

指标：

current_fact_accuracy
stale_memory_rate
task_success

这个 Scenario 后续特别用于测试 Graphiti 等时间型 Memory。

==================================================
Scenario 3 — Experience-Guided Adaptation
==================================================

研究：

失败经验是否能改善下一次行为。

第一次任务：

Agent进入一个需要准备的环境。

例如：

需要带特定工具/资源才能成功。

第一次允许 Agent 自然失败。

系统产生：

TASK_FAILED
以及相关 ExperienceEvent。

Interference：

插入无关事件。

第二次：

给予相似但不是完全相同的任务。

观察：

Memory 是否帮助 Agent：

- 回忆失败原因
- 改变计划
- 增加必要准备
- 提高成功率

禁止：

if failed_before:
    prepare_xxx

必须：

Experience
→ Memory Framework
→ Retrieval
→ LLM Planner
→ Behavior

==================================================
M8 — Benchmark Runner
==================================================

实现 CLI：

例如：

python -m minemembench run \
    --memory vector \
    --scenario delayed_recall \
    --runs 30 \
    --seed 42

支持：

--memory
--scenario
--runs
--seed
--model
--temperature
--max-steps

支持组合：

benchmark matrix

例如：

none
vector

×

delayed_recall
world_update
experience_adaptation

自动跑。

每个 run：

独立 episode_id。

每次 Scenario：

恢复标准化世界状态。

--------------------------------
记录
--------------------------------

保存：

JSONL
CSV
SQLite

每次 run：

run_id
memory_backend
scenario
seed
model
temperature
success
steps
retrievals
memory_writes
token_input
token_output
llm_calls
memory_latency
llm_latency
total_latency

==================================================
M9 — 接入真实 Agent Memory Framework
==================================================

按顺序：

1. Mem0
2. Letta

MVP只要求这两个。

后续预留：

Graphiti / Zep
ReMe
Text2Mem
A-Mem
Generative Agents Memory

--------------------------------
非常重要
--------------------------------

接每个框架之前：

必须查看：

官方 GitHub
官方 Documentation
当前 SDK Version

不要：

根据旧教程猜接口。

每个框架：

独立 Adapter：

mem0_adapter.py
letta_adapter.py

它们只能实现：

MemoryBackend

不能修改：

Scenario
Planner
Event Layer

--------------------------------
Mem0
--------------------------------

记录：

内部额外 LLM 调用
embedding 调用
memory write latency
retrieval latency

如果 Mem0 自己需要 LLM：

记录额外成本。

--------------------------------
Letta
--------------------------------

Letta 是 Stateful Agent / Memory Runtime。

要明确：

Benchmark 不能让 Letta 接管整个 Minecraft Planner。

我们的控制变量要求：

同一个 Planner LLM。

因此：

尽量只使用 Letta Memory 能力。

如果 Letta 架构无法完全解耦 Memory 和 Agent：

必须：

在报告中明确写成 limitation。

不能为了“公平”伪装成完全相同。

--------------------------------
M9验收
--------------------------------

同一个 Scenario：

NoMemory
Vector
Mem0
Letta

全部跑成功。

每组至少 smoke test 3 runs。

commit：

feat: add mem0 and letta memory adapters

==================================================
M10 — 正式 Benchmark
==================================================

正式实验前：

冻结：

Minecraft Version
World Seed
Planner Prompt
LLM Model
Temperature
Tool Set
Scenario Config

将实验配置保存：

benchmark_config.yaml

--------------------------------
第一轮正式实验
--------------------------------

Memory：

NoMemory
Vector
Mem0
Letta

Scenario：

Delayed Fact Recall
World State Update
Experience-Guided Adaptation

建议：

每组合至少 20–30 runs。

如果 API 成本允许：

50 runs。

--------------------------------
核心指标
--------------------------------

行为层：

Task Success Rate

Behavioral Adaptation Rate

Steps to Completion

Failure Recovery Rate

--------------------------------
记忆层：

Recall Accuracy

Relevant Memory Precision

Stale Memory Rate

Memory Count

Memory Size

--------------------------------
效率层：

Prompt Token Cost

Completion Token Cost

Total Token Cost

LLM Calls

Memory Write Latency

Memory Retrieval Latency

End-to-End Decision Latency

--------------------------------
统计
--------------------------------

至少输出：

mean
median
std
95% CI（如果数据量允许）

不要只显示单次结果。

==================================================
M11 — Ablation / Fairness Check
==================================================

做至少两个公平性验证。

--------------------------------
1. Retrieval-off Test
--------------------------------

Memory正常存。

但是测试阶段不允许 retrieve。

观察性能下降。

目的是：

证明提升确实来自 Memory Retrieval。

--------------------------------
2. Memory Noise Test
--------------------------------

加入无关经历。

例如：

10
50
100
500

观察：

不同 Memory Framework 是否随 Memory 增长而退化。

指标：

task success
retrieval precision
token cost
latency

这个实验很重要。

因为真实长期 Agent 的 Memory 会越来越多。

==================================================
M12 — Reporter
==================================================

自动生成：

results/
    raw/
    csv/
    figures/
    report.md

图表：

1. Task Success Rate by Memory Backend
2. Recall Accuracy
3. Stale Memory Rate
4. Success vs Token Cost
5. Retrieval Latency
6. Memory Size vs Performance
7. Noise Level vs Task Success

使用：

pandas
matplotlib

所有图：

必须从真实实验数据自动生成。

没有数据：

显示 N/A。

禁止填假数字。

==================================================
M13 — 可视化 Demo
==================================================

Benchmark主体继续保持无头运行。

额外提供：

可选 Viewer / Demo 模式。

不是项目核心。

Demo展示一个 Scene：

Experience Phase
↓
Memory Created
↓
Interference
↓
Memory Retrieved
↓
LLM Decision
↓
Minecraft Action

最好可以同时显示：

Minecraft画面

以及：

Memory Trace

例如：

Retrieved Memories:
1. Previous task failed because...
2. Resource was moved to...

Planner Decision:
prepare equipment

Action:
collect_item

==================================================
M14 — README / GitHub 发布
==================================================

README定位必须是：

MineMemBench is a reproducible benchmark for evaluating how long-term memory frameworks affect embodied LLM agent behavior in Minecraft.

不要定位为：

Minecraft AI Bot。

README最终至少包括：

1. Research Question
2. Why Embodied Memory Evaluation
3. Architecture
4. Supported Memory Frameworks
5. Benchmark Scenarios
6. Metrics
7. Quick Start
8. Reproduce Results
9. Add a New Memory Backend
10. Add a New Scenario
11. Results
12. Limitations
13. Related Work
14. Roadmap

--------------------------------
Related Work
--------------------------------

至少讨论：

Generative Agents

Voyager

MemGPT / Letta

Mem0

Graphiti / Zep

以及后续实际接入的：

ReMe
Text2Mem
A-Mem

只引用真实存在、实际阅读过的论文/项目。

README不能编造论文结论。

==================================================
Git工作流
==================================================

每个 Milestone：

1. git status
2. 运行测试
3. 确认无 secret
4. commit
5. push

建议 commit：

M4
feat: add embodied LLM agent loop

M5
feat: add semantic experience event layer

M6
feat: add memory benchmark interface

M7
feat: add reproducible benchmark scenarios

M8
feat: add automated benchmark runner

M9
feat: integrate mem0 and letta

M10
exp: run initial embodied memory benchmark

M12
feat: add benchmark reporting pipeline

最终：

tag v1.0.0

==================================================
Secret检查
==================================================

任何 push 前必须检查：

.env
LLM_API_KEY
GitHub Token
password
server credentials

不得 commit：

.env
server.jar
world/
logs/
node_modules/
.venv/
raw大量实验缓存

.env.example 允许提交。

==================================================
最终项目完成标准
==================================================

项目完成不是：

“Minecraft Bot可以和LLM聊天”。

而是必须达到：

1. Minecraft无头环境可自动启动
2. Agent可以真实行动
3. 游戏经历可以转换为统一ExperienceEvent
4. Memory Framework可插件式接入
5. NoMemory / Vector / Mem0 / Letta可运行
6. 至少3个标准化Scenario
7. 每个Scenario可自动Reset和重复运行
8. 同一个LLM下公平比较不同Memory
9. 自动统计行为、Memory和成本指标
10. 自动生成Benchmark报告
11. 所有结果可复现
12. GitHub用户可以接入新的MemoryBackend
13. README清晰说明实验限制
14. 不伪造任何实验结果

==================================================
重要研究原则
==================================================

永远保持：

Environment
→ Experience
→ Memory
→ Retrieval
→ LLM Decision
→ Action
→ Environment

Memory Framework的作用：

改变 Agent 可以访问的“过去”。

不要让 Memory Framework 直接决定行为。

最终我们研究的是：

“在同一个 next-token predictor / planner 下，不同长期记忆机制提供不同的过去信息，是否最终导致具身行为表现差异？”

==================================================
执行方式
==================================================

不要一次性写完 M4-M14。

严格按 Milestone 顺序。

每完成一个 Milestone：

1. 运行全部现有测试
2. 做真实验收
3. 输出修改内容
4. 输出测试结果
5. 输出已知问题
6. commit
7. push
8. 停下来等我确认

现在从：

M4 — NoMemoryBackend + LLM Planner + Real Minecraft Agent Loop

开始。

不要提前实现 M5。