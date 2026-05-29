# Context Assembler 接入 Session Context 最小设计

日期：2026-05-29  
仓库：`D:\webstudy\FlagHunter`

---

## 目标

把前面已经落好的 harness 真相第一次喂回 agent 上下文装配链，而不是只供 UI 消费。

本轮最小目标：

1. `ContextAssembler` 支持读取 agent 上的 `run_id + project_root`
2. 通过 `SessionContextView` 生成一段简短 session summary
3. 以 `task` 类上下文源的形式并入 assemble 结果
4. `web_server._run_agent_task(...)` 创建 agent 后显式挂上这两个字段

---

## 为什么现在做

当前系统已经能记录：

- ledger
- artifacts
- checkpoints
- session context view

但如果这些信息没有被喂回 agent，本质上还是“只增强观察，不增强决策”。

所以这一步的价值是：

> 让 harness 数据第一次真正进入 agent 的上下文闭环。

---

## 最小接线方式

### 1. agent 实例附加运行标识

在：

- `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`

中，创建 `PentestAgentAgent` 后附加：

- `agent.run_id`
- `agent.project_root`

### 2. ContextAssembler 新增 session source

在：

- `D:\webstudy\FlagHunter\pentestagent\knowledge\context_assembler.py`

里新增一个最小 summary builder：

- 读取 `SessionContextView`
- 抽取：
  - recent event types
  - artifact titles
  - latest checkpoint label
  - stop reason
  - verified flags

并拼成一段简短文本。

### 3. 作为 `task` 类上下文并入

这样无需改 `_select(...)` 的优先级规则，只复用现有：

- `task`
- `high confidence`

筛选路径。

---

## 为什么先不做更重的 prompt 结构

本轮不直接做：

- 专门的 `SessionContextSection`
- 大量结构字段注入 prompt
- 多阶段不同模板

因为现在最重要的是证明：

1. agent 能拿到 run-scoped harness summary
2. 上下文装配链没有被破坏

---

## 验证口径

本轮通过标准：

1. `ContextAssembler` 单测能证明：
   - harness summary 进入 assemble 结果
   - 文本里至少包含 verified flag / stop reason / artifact / latest event

2. `web_server` 单测能证明：
   - `_run_agent_task(...)` 创建的 agent 被附加 `run_id`
   - 同时附加 `project_root`

3. 既有 `SessionContextView` / harness tests 不退化

