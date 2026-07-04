# FlagHunter CTF Solver Gap Report v0.1

- 日期：2026-07-02
- 状态：Draft / 作为 `FlagHunter_CTF_Solver_Spec_v0.1_2026-07-02.md` 的首版差距分析
- 对照规格：[FlagHunter_CTF_Solver_Spec_v0.1_2026-07-02.md](./FlagHunter_CTF_Solver_Spec_v0.1_2026-07-02.md)
- 适用范围：FlagHunter 当前 CTF 单体主线、blackboard loop、verifier、ledger/checkpoint、crew 并行能力

---

## 0. 结论先行

当前 FlagHunter 的 CTF 主线已经具备一条清晰的骨架：

`AgentSession -> CTFCoordinator -> CTFTaskDispatcher -> blackboard solve loop -> CTFVerifier -> SessionLedger / Checkpoint / StrategyMemory`

但它距离 `FlagHunter CTF Solver Spec v0.1` 的目标态，仍有 4 个关键收敛缺口：

1. **没有统一 Claim 模型**
   事实散落在 `observations / artifacts / hypotheses / flags / notes` 多套结构里。
2. **没有正式 SolveNode / 求解树**
   当前有阶段、agenda、hypothesis，但没有可审计的子问题树与节点状态机。
3. **没有正式 TaskBrief / Receipt**
   当前存在 handoff 与上下文契约，但不是正式交接物，也没有统一落盘格式。
4. **Trace 仍是半成品**
   工具、验证、checkpoint 记录较强，但 `model_call`、`state_transition`、正式 `handoff` 等并未形成 100% 覆盖。

所以总体判断是：

- **结构骨架：中上**
- **控制面收敛：中上**
- **数据纪律：中**
- **验证纪律：中上**
- **全链路溯源：中下**

---

## 1. 评估方法

本报告按 spec 的核心主干逐项对照，给出三态判断：

- `已符合`：已有实现与 spec 目标高度一致，可直接沿用
- `部分符合`：已有近似实现，但语义、边界或覆盖率未达标
- `缺失`：当前没有对应结构，或只有零散片段，不足以视为实现

本报告强调两条原则：

1. 只按代码真相判定，不按愿景或 README 表述判定
2. “部分符合”不等于“可以不改”，它通常意味着后续最大结构债

---

## 2. 总体符合性矩阵

| 组件 / 条款 | 状态 | 结论摘要 |
|---|---|---|
| 入口装配统一化 | 已符合 | `AgentSession` 已经是单一装配入口 |
| 顶层 CTF Orchestrator | 部分符合 | 已有 coordinator，但不是 SolveNode 树裁决器 |
| Solver 主循环 | 部分符合 | 已有 blackboard loop，但未以 TaskBrief/Receipt 为中心 |
| 统一 Claim 模型 | 缺失 | 当前没有全系统统一 Claim 原子 |
| 事实分级纪律 | 部分符合 | flag 分级已存在，但未推广到所有事实 |
| “只有验证层能写 verified” | 部分符合 | 对 flag 基本成立，对一般事实尚未制度化 |
| Verifier 作为独立验证层 | 部分符合 | 验证器较强，但几乎只覆盖 flag |
| Blackboard 作为共享事实面 | 部分符合 | 已有 read-model blackboard，但不是真正持久化事实面 |
| Solve tree / SolveNode 状态机 | 缺失 | 无正式求解树、无节点预算与状态迁移 |
| TaskBrief / Receipt 交接物 | 缺失 | 有 handoff，但没有正式数据结构与落盘纪律 |
| Trace Store 只增日志 | 部分符合 | ledger 已是 append-only JSONL |
| Trace 覆盖率 100% | 缺失 | 缺 model_call、formal handoff、state_transition 等完整 trace |
| Checkpoint / Resume | 部分符合 | 已有 run 级恢复，但不是 node/task 级恢复 |
| 预算治理与终止纪律 | 部分符合 | 已有 phase budget / stop rule，但不是全局-节点-Solver 分层预算 |
| Strategy Memory 只作历史参考 | 部分符合 | 现实上大致如此，但缺少统一的“assumption/reference”语义 |
| Crew 的并行与隔离 | 部分符合 | worker 隔离已做，但共享纪律未收敛到 verified-only |

---

## 3. 分项分析

### 3.1 入口装配统一化

**状态：已符合**

**证据**

- [agent_session.py](/D:/webstudy/FlagHunter/flaghunter/session/agent_session.py:1)
- [agent_session.py](/D:/webstudy/FlagHunter/flaghunter/session/agent_session.py:62)
- [agent_session.py](/D:/webstudy/FlagHunter/flaghunter/session/agent_session.py:157)

**分析**

`AgentSession.create()` 已经承担了 spec 中 `Entry / Session Assembly` 的角色：

- 统一通过 composition root 构建组件
- 暴露统一 `EventBus`
- 提供统一 `run()` 程序化入口

这意味着：

- 顶层入口统一化不是当前主要矛盾
- 后续 CTF solver 改造应尽量挂在这条单一装配路径上

**结论**

这部分可直接沿用，不需要重构，只需要让后续 CTF 特化控制面继续通过它装配。

---

### 3.2 顶层 CTF Orchestrator

**状态：部分符合**

**证据**

- [coordinator.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/coordinator.py:1454)
- [coordinator.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/coordinator.py:1482)
- [coordinator.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/coordinator.py:1590)

**分析**

`CTFCoordinator.execute()` 已经承担不少顶层职责：

- 归一化 target / goal / challenge context
- bootstrap dispatcher
- 应用 resume / verified flag / runtime signal 等前置契约
- 执行 recon、post-recon、strategy memory、hypothesis 合同
- 最终把控制权交给 `_run_solve_loop`

但它距离 spec 里的 `Orchestrator` 还有几个差距：

- 没有显式 `SolveNode` 树
- 没有“节点级预算切分”
- 没有正式 `TaskBrief` 派发
- 没有围绕 `Claim dependency` 的统一污染回退

**结论**

当前 coordinator 是“过程协调器”，还不是“求解树裁决器”。

---

### 3.3 Solver 主循环

**状态：部分符合**

**证据**

- [ctf_dispatcher.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/ctf_dispatcher.py:485)
- [ctf_dispatcher.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/ctf_dispatcher.py:534)
- [llm_executor.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/llm_executor.py:376)

**分析**

当前 CTF 主循环已从旧链路 harness 收敛到 `blackboard loop`：

- 模型根据 blackboard intents 决定下一步
- 工具执行结果写回状态
- 终止会经过 verifier / recovery / finalize

这比“单纯的 while + plan list”强很多，已经具有 solver loop 雏形。

但仍不满足 spec 的几条关键约束：

- Solver 没有通过 `TaskBrief` 接任务
- Solver 没有通过 `Receipt` 交回结果
- “候选结论”并没有统一包装成 Claim
- 自验存在，但没有统一可审计协议

**结论**

这是当前最接近 spec 的部分之一，但还缺正式交接物和正式数据纪律。

---

### 3.4 统一 Claim 模型

**状态：缺失**

**证据**

- [ctf_state.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/ctf_state.py:171)
- [ctf_state.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/ctf_state.py:175)
- [blackboard_adapter.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/blackboard_adapter.py:138)

**分析**

当前“事实”被拆成多套结构：

- `observations`
- `artifacts`
- `hypotheses`
- `candidate_flags`
- `runtime_flags`
- `verified_flags`
- `rejected_flags`

此外，`record_fact()` 只是把内容写成 `model_fact` observation，并未形成可依赖的正式结论对象。

这导致：

- 无法统一表达“普通事实”与“flag 事实”
- 无法统一表达 `depends_on`
- 无法统一表达 `superseded_by / retracted`
- 无法统一执行“只有 verifier 才能升级事实”

**结论**

这是当前 CTF 主线的第一大结构缺口，也是后续改造的首要对象。

---

### 3.5 事实分级纪律

**状态：部分符合**

**证据**

- [ctf_state.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/ctf_state.py:366)
- [verifier.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/verifier.py:191)
- [recovery.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/recovery.py:138)

**分析**

对 flag 而言，当前已经存在较强的分级体系：

- `candidate`
- `runtime`
- `verified`
- `rejected`

而且 `RecoveryController` 会据此执行不同裁决：

- runtime 未验证 -> `wait_for_verification`
- source-only candidate -> `stop_candidate_only`
- verified -> 可成功收束

但问题是：

- 这种分级只覆盖 flag
- 普通事实还停留在 observation / note / hypothesis 层
- 没有统一把它们纳入同一套等级体系

**结论**

有“分级思想”，但没有“全系统分级纪律”。

---

### 3.6 “只有验证层能写 verified”

**状态：部分符合**

**证据**

- [verifier.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/verifier.py:206)
- [verifier.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/verifier.py:234)
- [flag_observer.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/flag_observer.py:87)

**分析**

在 flag 维度上，verified 的产生几乎都经过 `CTFVerifier.verify_flag()`：

- runtime 证据先入 `runtime`
- 平台接受或强验证条件成立后，才升 `verified`

这已经相当接近 spec 的约束。

但仍有两点不足：

- 这种权限边界只覆盖 flag
- 没有统一 Claim 层，因此无法从代码层声明“除了 verifier，无人能把任意 Claim 升 verified”

**结论**

这是“局部成立、系统级尚未成立”的典型条目。

---

### 3.7 Verifier 作为独立验证层

**状态：部分符合**

**证据**

- [verifier.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/verifier.py:93)
- [flag_observer.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/flag_observer.py:68)
- [flag_observer.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/flag_observer.py:96)

**分析**

当前 `CTFVerifier` 已具备清晰的验证裁决职责：

- 检查格式
- 区分 runtime/source-only
- 识别 prior submit
- 触发 local auto verify
- 生成 verification decision
- 回写 notes 与 session event

这是当前代码里最成熟的“可靠性锚点”之一。

但它主要聚焦在 `flag verification`，而不是泛化到：

- credential validity
- exploit success
- endpoint reachability claim
- vulnerability成立 claim

**结论**

当前 verifier 是“flag verifier”，还不是 spec 定义的“Claim verifier”。

---

### 3.8 Blackboard 作为共享事实面

**状态：部分符合**

**证据**

- [blackboard.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/blackboard.py:1)
- [blackboard.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/blackboard.py:85)
- [blackboard_adapter.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/blackboard_adapter.py:1)

**分析**

当前 blackboard 已经明确被定义为：

- `CTFState` 的纯 read-model
- 不做 I/O
- 不是第二份真相
- 由 facts / intents / hints / attempts 组成

这与 spec 中“Blackboard 是受纪律约束的共享事实面”的方向非常接近。

但差距在于：

- 当前 blackboard 是运行态投影，不是持久化的正式事实面
- 它依赖 `CTFState` 的既有桶结构，而不是统一 Claim
- 它仍混合了承载事实与承载意图的多个历史对象

**结论**

Blackboard 方向是对的，但它还不是最终态的 canonical shared fact surface。

---

### 3.9 Solve tree / SolveNode 状态机

**状态：缺失**

**证据**

- [coordinator.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/coordinator.py:1454)
- [ctf_state.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/ctf_state.py:156)

**分析**

当前系统有很多“像树的一部分”的东西：

- hypothesis
- exploration agenda
- current phase
- phase round budget
- chain_order

但没有正式 `SolveNode`：

- 没有 `parent_id`
- 没有 `goal`
- 没有 `status`
- 没有 `claimed_by`
- 没有节点级 `budget/spent`

因此：

- 当前无法从结构上表达“子问题是如何分解出来的”
- 也无法对某个子问题单独恢复、审计、回退

**结论**

这是当前从“强求解循环”迈向“可工程治理求解树”的关键缺失。

---

### 3.10 TaskBrief / Receipt 正式交接物

**状态：缺失**

**证据**

- [coordinator.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/coordinator.py:1499)
- [ctf_dispatcher.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/ctf_dispatcher.py:449)
- `rg "TaskBrief|Receipt"` 结果为空

**分析**

当前系统并非完全没有交接：

- 有 `ingress_handoff`
- 有 structured hint / challengeContext / resumeBootstrap
- 有 MCP / Web / conversation handoff 元数据

但这些 handoff：

- 更像入口/恢复控制信息
- 不是子任务任务书
- 不是 Solver -> Orchestrator 的标准回执
- 没有统一 schema 和落盘纪律

**结论**

交接“概念存在”，交接“对象不存在”。

---

### 3.11 Trace Store 只增日志

**状态：部分符合**

**证据**

- [session_ledger.py](/D:/webstudy/FlagHunter/flaghunter/harness/session_ledger.py:10)
- [audit_infra.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/audit_infra.py:484)
- [audit_events.py](/D:/webstudy/FlagHunter/flaghunter/harness/audit_events.py:13)

**分析**

`SessionLedger` 已明确是 append-only JSONL。

当前已经会记录：

- dispatcher_started
- control_action_started / completed
- tool_called / tool_finished
- verification_decision
- recovery_decision
- checkpoint_written
- task_finished

这说明 trace 基础设施是存在的，而且方向正确。

**结论**

当前已经有“旁路只增日志”的真实实现，但离“全量因果链”还有距离。

---

### 3.12 Trace 覆盖率 100%

**状态：缺失**

**证据**

- [audit_events.py](/D:/webstudy/FlagHunter/flaghunter/harness/audit_events.py:13)
- `rg "model_call|state_transition|budget_event|curator_action"` 结果几乎为空
- [base_agent.py](/D:/webstudy/FlagHunter/flaghunter/agents/base_agent.py:420)

**分析**

当前 trace 的最大缺口是：

- 没有 `model_call` 事件对象
- 没有落“最终完整 prompt + 完整输出”
- 没有正式 `handoff` 事件类型
- 没有系统级 `state_transition` / `budget_event` / `curator_action`

这意味着：

- 你可以回看很多工具与验证行为
- 但你还不能完整回放“模型为什么这么决定”

**结论**

这是当前“可观测性”最大的短板，也是 spec 与现状差距最大的条目之一。

---

### 3.13 Checkpoint / Resume

**状态：部分符合**

**证据**

- [checkpoint_store.py](/D:/webstudy/FlagHunter/flaghunter/harness/checkpoint_store.py:11)
- [audit_infra.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/audit_infra.py:503)
- [coordinator.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/coordinator.py:1523)

**分析**

当前已经具备：

- append-only checkpoint store
- checkpoint_written event
- resume context / resume checkpoint contract

但恢复粒度仍偏 run 级，而不是 node/task 级。

也就是说：

- 现在能恢复“这次 solve 跑到哪了”
- 还不能优雅表达“这个子问题恢复到哪一步”

**结论**

恢复能力有实物，但还不够结构化。

---

### 3.14 预算治理与终止纪律

**状态：部分符合**

**证据**

- [ctf_state.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/ctf_state.py:201)
- [ctf_dispatcher.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/ctf_dispatcher.py:720)
- [recovery.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/recovery.py:118)

**分析**

当前已有以下较强约束：

- phase round budget
- exploit budget exhaustion stop
- runtime flag waits for verification
- source-only candidate stops false positive
- no-progress / exhausted / blocked-surface stops

这说明“什么时候停、什么时候切、什么时候等待验证”已经不是拍脑袋。

但它仍不是 spec 要求的：

- 全局预算
- 节点预算
- Solver 子预算

三层分发与回收体系。

**结论**

终止纪律已经有了，预算治理还未完全工程化。

---

### 3.15 Strategy Memory 只作历史参考

**状态：部分符合**

**证据**

- [strategy_memory.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/strategy_memory.py:84)
- [strategy_memory.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/strategy_memory.py:224)
- [llm_executor.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/llm_executor.py:303)
- [memory_facade.py](/D:/webstudy/FlagHunter/flaghunter/agents/pa_agent/memory_facade.py:133)

**分析**

当前 memory 的实际行为已经很像 spec 希望的样子：

- recall 进入 prompt 时以 advisory 文本出现
- 失败 payload 会被显式提示“不要再提”
- 历史有效链会被提示“优先考虑”
- outcome / wrong flag 会回写 memory 评分

但问题是：

- 这仍是“提示协议”
- 还不是系统级“reference-only / assumption”对象
- 还没有通过统一 Claim 层接入验证链

**结论**

语义方向基本正确，数据纪律尚未正式化。

---

### 3.16 Crew 的并行与隔离

**状态：部分符合**

**证据**

- [worker_pool.py](/D:/webstudy/FlagHunter/flaghunter/agents/crew/worker_pool.py:158)
- [worker_pool.py](/D:/webstudy/FlagHunter/flaghunter/agents/crew/worker_pool.py:167)
- [worker_pool.py](/D:/webstudy/FlagHunter/flaghunter/agents/crew/worker_pool.py:178)
- [swarm_bridge.py](/D:/webstudy/FlagHunter/flaghunter/agents/crew/swarm_bridge.py:23)
- [orchestrator.py](/D:/webstudy/FlagHunter/flaghunter/agents/crew/orchestrator.py:141)

**分析**

当前 crew 已有很扎实的并行基础：

- worker runtime 隔离
- worker tool 白名单过滤
- depends_on 依赖等待
- worker type specialization

这比很多“伪多 agent”实现都强。

但它与 spec 仍有两个关键冲突：

1. 共享面不只 verified
   `swarm_bridge` 会传 observations、candidate_flags、runtime_flags、verified_flags、rejected_flags。
2. 共享协议与单体 CTF 主线并未完全统一
   它更像“结果桥接”，不是统一 Claim/Verifier/Blackboard 协议。

**结论**

并行机制已经成熟，但共享纪律还没收口。

---

## 4. 最大结构缺口

按后续改造价值排序，我认为最关键的 5 个差距如下。

### 4.1 缺统一 Claim

这是所有后续能力的中心缺口。

没有 Claim，就无法：

- 统一表示普通事实与 flag
- 统一做 depends_on
- 统一做 verified 权限控制
- 统一做污染传播
- 统一做 handoff 与 trace 指针

### 4.2 缺 SolveNode

没有 SolveNode，就无法把当前强大的黑板循环收敛成一棵可审计的求解树。

### 4.3 缺 TaskBrief / Receipt

没有正式交接物，就无法把“并行求解”“恢复”“子任务回放”真正工程化。

### 4.4 Trace 不全

没有 `model_call` 全量 trace，就无法实现 spec 要求的完整因果回溯。

### 4.5 Verifier 过于 flag-centric

如果 verifier 不扩展到一般事实，系统就会长期停留在“最后验答案，中间靠感觉”的状态。

---

## 5. 建议的迁移优先级

### P1. 统一 Claim 与 VerificationRecord

目标：

- 不先动 UI，不先动知识库
- 先定义全系统的事实原子

建议：

- 为 flag 与一般事实统一数据模型
- 把现有 `candidate/runtime/verified/rejected` 映射为 Claim level 子集
- 给 observation / notes / verifier 输出增加向 Claim 过渡的适配层

### P2. 扩 Trace 到 model_call / handoff / state_transition

目标：

- 让最终答案可追到模型完整 prompt 和原始工具输出

建议：

- 新增 `model_call` trace event
- 新增 `handoff` trace event
- 新增 `state_transition` / `budget_event`

### P3. 引入 SolveNode + TaskBrief + Receipt

目标：

- 把“求解过程”从隐式循环提升为显式任务树

建议：

- 单体 CTF 路线也强制走 Brief/Receipt，只是 in-process
- crew 直接复用同一对象模型

### P4. 扩展 Verifier 到一般事实

目标：

- 不再只有 flag 才有验证器

建议：

- 先覆盖 credential validity / exploit success / endpoint existence
- 再逐步扩展漏洞成立、source hint reachability 等

### P5. 统一 crew 共享纪律

目标：

- crew 与单体 CTF 共用同一 Claim / Blackboard / Verifier 纪律

建议：

- worker 之间默认只共享 verifier 允许共享的事实对象
- 把 observations / runtime flags 之类非 verified 内容改成受控共享

---

## 6. 最终判断

当前 FlagHunter 不属于“没有控制面、没有验证、没有日志”的早期原型。

相反，它已经有了一套不弱的 CTF 主线：

- 有 coordinator
- 有 blackboard loop
- 有 verifier
- 有 recovery
- 有 ledger
- 有 checkpoint
- 有 strategy memory

真正的问题不是“有没有这些块”，而是：

> 这些块还没有被统一到同一套正式的事实模型、交接模型和溯源模型里。

所以当前最合理的改造路径不是推翻重来，而是：

**保留现有 CTF 主线，优先补齐 Claim / SolveNode / TaskBrief / Receipt / Trace 这五个结构中心。**

这也是 `FlagHunter_CTF_Solver_Spec_v0.1` 后续落地的最短路径。
