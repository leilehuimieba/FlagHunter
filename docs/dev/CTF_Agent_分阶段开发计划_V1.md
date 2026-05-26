# CTF Agent 分阶段开发计划 V1

---

## 1. 计划目标

将当前项目从：

> 增强型 deterministic solver

逐步演化为：

> hypothesis-driven CTF agent

本计划强调：

- 先收主干
- 再迁逻辑
- 最后扩题型

而不是相反。

---

## 2. 当前基线

当前已具备：

- `/ctf` 命令入口
- `ctf_planner.py`
- `ctf_dispatcher.py`
- 局部 wrong-flag 恢复
- SQLi / source leak / PHP unserialize acceptance 覆盖

当前主要缺口：

1. 状态未独立
2. 验证器未独立
3. 恢复控制器未独立
4. 假设引擎未独立
5. 仍然过度依赖链路分发

---

## 3. 开发阶段

---

### Phase 0：规范冻结（当前阶段）

目标：

- 冻结文档口径
- 冻结后续开发边界

产物：

- 本文档包

完成标准：

- 文档齐备
- 文档口径一致
- 后续改动有明确入口

---

### Phase 0.5：最小可行实战（live solve proof）

目标：

- 在进入主干改造之前，用当前系统至少跑通一道真实 CTF 题目（或明确定位到当前系统的最早卡点）
- 找出"当前系统遇到真实题目时，哪一步最先失效"
- 把卡点直接翻译成 Phase 1–N 的优先级输入

产物：

- 至少 1 道题的解题记录（截图 / session log / flag 截图）
- 一份结构化"卡点列表"：卡在哪 → 原因 → 对应哪个开发阶段

完成标准：

- 拿到真实 flag，**或** 明确定位到 agent 最早失效的环节
- 卡点已同步进入后续各阶段的"完成标准"或"禁止事项"

禁止行为：

- 用"系统还不完善"作为跳过 live solve 的理由
- 跳过本阶段直接进入 Phase 1

---

#### Phase 0.5 实战记录（已完成）

**测试题 1**：`[极客大挑战 2019]PHP`
- 结果：**成功（solved）**
- 路径：`backup_source_leak` → 下载 `www.zip` → 源码 PHP 反序列化 → runtime 确认 flag
- 记忆写入：`StrategyMemoryEntry` 写入，`winning_hypothesis_kinds = ["backup_source_leak", "php_unserialize_magic_method"]`

**测试题 2**：`[护网杯 2018]easy_tornado`  
- 结果：**失败（unsolved）**
- 目标 URL：`http://<buuoj>/node5/...`，输入：仅 URL，无类型提示
- 页面结构：`/file?filename=...&filehash=...`、`/hints.txt`、`/welcome.txt`、`/flag.txt`
- 实际卡点：

| 卡点 | 直接原因 | 对应规范修改 |
|---|---|---|
| 假设选错（`backup_source_leak` 排名第一） | `backup_clue = False` 但 memory bonus 仍施加 | 能力层 §3.6.1 三步检查；状态模型 §9.5 |
| 假设空间太窄（未长出 `hash_guarded_file_read`、`hint_chain_followup`） | 缺少结构感知假设生成映射 | 状态模型 §9.1 结构感知映射表 |
| 探索中止太早（`/hints.txt`、`/file?...` 未充分分析） | 无 `ExplorationAgenda` 机制，无进展直接停止 | 状态模型 §3.8、§9.6；主干架构 §4 |
| 类型识别太粗（仅 `detected_type = web`） | `ChallengeFingerprint` 无 `web_subtype` | 能力层 §3.2 `web_subtype` 标签 |

- 结论：当前系统是"agent 雏形"，有状态/假设/实验/记忆骨架，但**探索深度不足 + 记忆误导 + 假设空间太窄**，不满足"强自治 agent"标准
- 规范更新：上述 4 个卡点已全部翻译进对应文档，本 Phase 视为完成

---

### Phase 1：状态主干落地

目标：

- 引入独立 `CTFState`
- 不再让 dispatcher 私有变量承担全部状态语义

建议文件：

- `pentestagent/agents/pa_agent/ctf_state.py`

产物：

- `CTFState` 数据结构
- state update helper
- 最小 contract tests

完成标准：

- 当前 `candidate/runtime/rejected flag`
- `artifacts`
- `hypotheses`（即使先是轻量版）
- 都可在结构化状态中表达

---

### Phase 2：验证器落地

目标：

- 独立出 `Verifier`
- 统一 candidate/runtime/verified/rejected 规则

建议文件：

- `pentestagent/agents/pa_agent/verifier.py`

产物：

- flag 分级验证逻辑
- source-only 不提前 stop
- wrong-flag rejected 统一入口

完成标准：

- 策略层不再直接宣布 verified success

---

### Phase 3：假设引擎落地

目标：

- 独立假设生成与排序
- 为 RecoveryController（Phase 4）提供"可切换假设"的结构化基础

> 调整说明：假设引擎先于恢复控制器落地，因为恢复本质上是"降权失败假设 + 选出下一最强假设"，没有独立的假设排序就无法做有意义的恢复。

建议文件：

- `pentestagent/agents/pa_agent/hypothesis_engine.py`

产物：

- hypothesis 数据结构
- 轻量排序器（confidence 加权 + evidence count）
- 最小信息增益规则

完成标准：

- dispatcher 不再只按题型选链，而能基于状态选下一实验
- RecoveryController 可从 HypothesisEngine 拿到排序后的备选假设列表

---

### Phase 4：恢复控制器落地

目标：

- 独立处理 no-progress / wrong-flag / missing-tool / exploit failure
- 基于 HypothesisEngine 的排序结果，降权失败路径并选出下一实验方向

建议文件：

- `pentestagent/agents/pa_agent/recovery.py`

产物：

- 恢复动作枚举
- 恢复优先级规则
- 工具缺失时的安装探测流程
- 恢复 acceptance tests

完成标准：

- 恢复逻辑不再散落在 dispatcher 各处
- 任何恢复动作执行前都必须经过 HypothesisEngine 重新排序

---

### Phase 5：策略注册表落地

目标：

- 把现有策略迁移成统一策略接口

第一批迁移建议：

1. `auth_form_sqli`
2. `backup_source_leak`
3. `php_unserialize_magic_method`

建议文件：

- `pentestagent/agents/pa_agent/strategy_registry.py`
- 可选 `strategies/`

完成标准：

- 每个策略都能回答：
  - 前提
  - 最小实验
  - 成功信号
  - 失败信号
  - 升级条件

---

### Phase 5.5：智能推理层与能力记忆层落地

目标：

- 落地推理层五个组件（PreActionReasoning、Interpretation、AdversarialLens、Postmortem、StopReport）
- 落地能力层（CapabilityRegistry + 降质路由）
- 落地记忆层（StrategyMemory + FAISS）

> 调整说明：推理层和能力层在 StrategyRegistry 之后实现，因为需要足够多的策略样本来验证推理层的有效性。

建议文件：

- `pentestagent/agents/pa_agent/reasoning.py`
- `pentestagent/agents/pa_agent/capability_registry.py`
- `pentestagent/agents/pa_agent/strategy_memory.py`
- `loot/strategy_memory.json`
- `loot/strategy_memory.faiss`

产物：

- 推理层五个组件（详见 `CTF_Agent_智能推理层规范_V1.md`）
- CapabilityRegistry 含降质路由
- StrategyMemory 的保存和检索
- R1-R5、C1-C4、M1-M4 用例通过

完成标准：

- 任意实验执行记录都有 PreActionReasoning Q1-Q4
- 任意假设失败都有 Retrospective
- sqlmap 缺失时自动降质到 manual_payload，不进入安装流
- 连跑两道相似题，第二道 HypothesisEngine 初始排序受第一道影响

Phase 5.5 禁止：

- 推理层输出绕过 schema 验证直接存裸文本
- AdversarialLens 主导假设排序（权重 > 0.2）
- StrategyMemory 存储题目名特判

---

### Phase 5.7：LLM-driven 自由探索兜底（新增）

> 详见独立文档：`CTF_Agent_自由探索与LLM驱动兜底_V1.md`

目标：

- 当所有预注册策略 precondition 均不满足或耗尽时，agent 必须能退到"LLM 自由调工具"的兜底通道
- 让单 agent 在**全新未知题型**上不再直接 stop_no_progress
- LLM-driven 动作仍然走 PreActionReasoning → ToolGuard → Verifier 闭环

建议文件：

- `pentestagent/agents/pa_agent/ctf_state.py`（LLMStepLog + llm_exploration_steps）
- `pentestagent/agents/pa_agent/reasoning.py`（PreActionReasoning Q1~Q4 强化）
- `pentestagent/agents/pa_agent/capability_registry.py`（三路决策树）
- `pentestagent/agents/pa_agent/ctf_dispatcher.py`（`_run_llm_driven_exploration`）
- `pentestagent/agents/pa_agent/strategy_registry.py`（注册 `llm_driven_exploration` StrategyDefinition）

产物：

- `llm_driven_exploration` 策略可被所有 chain 兜底
- PreActionReasoning Q1~Q4 强制嵌入每一次 LLM-driven 动作
- CapabilityRegistry 三路决策（approved / degrade / unavailable）
- LLM1~LLM8 用例全部通过（见自由探索文档 §7）

完成标准：

- 在 easy_tornado 上移除手写策略，LLM-driven 兜底也能在 8 步内拿到 flag
- 在一道**全新未知题**上 agent 不再直接 stop_no_progress
- 所有 LLM-driven flag 仍走 Verifier 验证

Phase 5.7 禁止：

- LLM 直接修改 CTFState（必须经 dispatcher 写入接口）
- LLM 决定 flag 成立（必须过 Verifier）
- LLM 调用 CapabilityRegistry 未注册的工具
- LLM 提交已 reject 的 flag
- LLM 无 PreActionReasoning Q1~Q4 记录就执行动作

---

### Phase 5.8：多 Provider 韧性（新增）

> 详见独立文档：`CTF_Agent_多Provider韧性与多Agent协作_V1.md` Part A

目标：

- 把 `cpa_modules/m1_api_hub/` 已有的 FailoverMonitor / ProviderManager 真正接到 pa_agent 主路径
- API 额度耗尽 / 网络抖动 / 5xx / 401 各自走对应状态转换 + 自动切换
- DOWN provider 在网络恢复后被 recovery_loop 自动置回 HEALTHY

建议文件：

- `pentestagent/llm/llm.py`（`_classify_error` + provider 切换）
- `pentestagent/agents/pa_agent/ctf_dispatcher.py`（启动 FailoverMonitor）
- `cpa_modules/m1_api_hub/cost_tracker.py`（budget 阻断）
- `pentestagent/interface/cli.py` 或 tui（`/providers` 命令）
- `.env.example`（多 provider 配置示例）

产物：

- 6 类错误的状态转换规则（见韧性文档 §1.3）
- FailoverMonitor 在 pa_agent 启动时自动 start_monitoring
- `/providers` 命令显示 5 态 emoji
- PROV1~PROV6 用例全部通过

完成标准：

- 关闭主 provider API key，agent 自动切换备份 provider 完成当前任务
- 60s 内 DOWN provider 网络恢复后自动 RECOVERING → HEALTHY
- 日预算超限阻断新请求 + UI 告警

Phase 5.8 禁止：

- 把 provider 切换写在 dispatcher 内部（必须经 LLM 层 + ProviderManager）
- 跳过错误分类直接重试（必须先 _classify_error）
- 在主路径调用 ProviderManager 的私有方法

---

### Phase 6：入口与体验收口

目标：

- 把 `/ctf`、`/ctf wrong`、`/ctf hint`、`/ctf override`、`/ctf reasoning`、`/ctf memory`、`/ctf capabilities` 等命令统一挂回主干
- notes 持久化
- UI 输出（含 StopReport 展示）
- 补全 `CTF_Agent_用户操作手册_V1.md` 的 §8 待填充项

产物：

- 用户级 TUI 命令全部可用
- StopReport 在 TUI 有标准展示
- 完整的用户操作手册（含截图、walkthrough、配置项）
- 至少 1 道题的端到端 walkthrough 文档

完成标准：

- 用户能感知到 candidate / rejected / runtime 的差异
- 停止时 TUI 显示 StopReport（含候选 flag 和 next_steps）
- 用户操作手册 §8 待填充项全部勾选完成
- 新用户按手册可在 30 分钟内完成首道题尝试

---

### Phase 7：多 Agent 协作落地（新增）

> 详见独立文档：`CTF_Agent_多Provider韧性与多Agent协作_V1.md` Part B
>
> **前置条件**：Phase 5.7 + Phase 5.8 必须先验收完成。否则多 worker 也只能跑硬编码策略，并行无意义。

目标：

- 把 `agents/crew/` 已有的 CrewOrchestrator / WorkerPool / ShadowGraph 接到 CTF 路径
- 引入 `CTFCrewCoordinator` 外层包装，多 worker 共享同一 CTFState + Verifier + ProviderManager
- 并行减少端到端时延，不为了"多就是好"

建议文件：

- `pentestagent/agents/pa_agent/ctf_crew_coordinator.py`（新建）
- `pentestagent/agents/pa_agent/ctf_state.py`（asyncio.Lock 保护并发写）
- `pentestagent/agents/crew/swarm_bridge.py`（把 CTFCoordinator 包装成 worker）
- `pentestagent/interface/cli.py`（`/ctf crew <task>` 命令）

产物：

- CTFCrewCoordinator 可派发 Recon / Exploit / LLMExplorer / Verifier 四类 worker
- 共享 CTFState 在 100 并发 write 下不丢数据
- ShadowGraph 推荐下一轮派发任务
- CREW1~CREW6 用例全部通过

完成标准：

- `/ctf crew <task>` 可用，TUI 多 worker 并行 progress
- 在有 10+ endpoints 的题上，crew 模式端到端时延 < 单 agent 60%
- 多源 candidate flag 不被 Verifier 重复打 platform
- 任一 worker 命中 verified flag 后，其他 worker 收到 cancel 信号

Phase 7 禁止：

- 重写 CTFCoordinator
- worker 直接写 verified_flags（必须经统一 Verifier）
- worker 间不共享 CTFState
- 在 Phase 5.7 + 5.8 完成前启动

---

## 4. 每阶段禁止事项

### Phase 1 禁止

- 一边建状态，一边重写所有策略

### Phase 2 禁止

- verifier 仍依赖大量 dispatcher 内部细节

### Phase 3 禁止

- 用题名做 hypothesis kind
- 把 HypothesisEngine 实现成纯 LLM 自由生成，缺少规则层兜底

### Phase 4 禁止

- 恢复逻辑写成新的 scattered if-else
- 绕过 HypothesisEngine 直接在 recovery 里硬编码下一步动作

### Phase 5 禁止

- 迁策略时夹带题目特判

### Phase 5.5 禁止

- 推理层输出绕过 schema 验证直接存裸文本
- AdversarialLens confidence 调整单次超过 ±0.2（见 推理层规范 §5.5）
- StrategyMemory 写入含题目名/平台名的 learned_rule

### Phase 5.7 禁止

- LLM 直接修改 CTFState（必须经 dispatcher 写入接口）
- LLM 决定 flag 成立（必须过 Verifier）
- LLM 调用 CapabilityRegistry 未注册的工具
- LLM 提交已 reject 的 flag
- LLM 无 PreActionReasoning Q1~Q4 记录就执行动作

### Phase 5.8 禁止

- 把 provider 切换写在 dispatcher 内部（必须经 LLM 层 + ProviderManager）
- 跳过错误分类直接重试（必须先 _classify_error）
- 在主路径调用 ProviderManager 的私有方法

### Phase 7（多 Agent 协作，新增）禁止

- 重写 CTFCoordinator（应通过 CTFCrewCoordinator 外层包装）
- worker 直接写入 verified_flags（必须经统一 Verifier）
- worker 间不共享 CTFState（多份状态会导致 candidate flag 不收敛）
- 在 Phase 5.7 + 5.8 完成前启动 Phase 7
- PreActionReasoning 的 failure_next_action 使用枚举以外的值
- 性能层改动不同步跑 P1-P4 用例

---

## 5. 每阶段验收证据

每个阶段至少提供：

1. 文档更新
2. 文件清单
3. 相关测试列表
4. 通过结果
5. 风险说明

---

## 6. 优先级顺序

如果资源有限，必须按以下顺序开发：

1. `CTFState`
2. `Verifier`
3. `HypothesisEngine`
4. `RecoveryController`
5. `StrategyRegistry`
6. `ReasoningLayer`（PreActionReasoning → Interpretation → Postmortem → AdversarialLens → StopReport）
7. `CapabilityRegistry`（降质路由）
8. `StrategyMemory`（跨题学习）

不能把顺序倒过来。

原因：

- 没有状态和验证，策略越多，系统越脆
- 没有假设引擎，恢复控制器就无法知道"恢复到哪条路"，只能散发
- 没有足够策略，推理层的 AdversarialLens 无法用历史失败数据调校
- 没有推理层，StrategyMemory 写入的 learned_rule 质量极低

---

## 7. 成功标志

本计划真正完成，不是“又多会几道题”，而是：

1. agent 能解释自己为什么继续 / 为什么停止
2. 错 flag 不再导致主循环误终止
3. 新题型主要通过新增策略与验证规则支持，而不是改大段分支
4. 测试层围绕行为不变量稳定扩展
