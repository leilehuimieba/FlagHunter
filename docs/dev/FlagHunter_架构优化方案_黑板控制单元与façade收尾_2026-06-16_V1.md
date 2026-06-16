# FlagHunter 架构优化方案：黑板控制单元 + façade 收尾（V1）

> 日期：2026-06-16
> 适用范围：`pentestagent/agents/pa_agent/`（dispatcher / coordinator / executor）与 `pentestagent/harness/`、`pentestagent/knowledge/session_context.py`
> 文档性质：**设计说明 + 逐项实施清单**，不改主干语义、不推倒重写。是 [`FlagHunter_Harness优化方案_借鉴Cairn_V1.md`](FlagHunter_Harness优化方案_借鉴Cairn_V1.md) 的收尾续作。

---

## 0. 一句话结论

**架构已经不差：黑板思维（blackboard-lite）该补的壳已经落地。** 当前缺的不是"更多模块"，而是两件没收尾的事：

1. `ctf_dispatcher.py` 仍是 **9892 行**上帝对象，façade 拆分只做了一半（coordinator 抽出来了，但回调 dispatcher 自身方法）。
2. 有"黑板"（事件账本 ledger），但还缺真正的**控制单元（control unit）**——它现在是写多读少的审计日志，不是驱动决策的黑板。

---

## 1. 仓库真实状态核对（2026-06-16 实测）

| 计划项 | 文档要求 | 实际状态 | 证据 |
|---|---|---|---|
| Harness 层（ledger/artifact/checkpoint/audit/session_context） | Cairn 方案 Phase A | ✅ **已实现且接线，有单测** | `pentestagent/harness/*.py`（54–79 行/模块）；被 dispatcher / coordinator / web_server / mcp_tools / context_assembler 引用；`tests/unit/harness/*` |
| 权限门禁 | roadmap P1 | ✅ 已存在 | `pentestagent/runtime/permission_enforcer.py` |
| 子代理 | roadmap P2 | ✅ 已存在 | `pentestagent/agents/subagent.py` |
| dispatcher 收缩为 façade | Cairn 方案 §6.1 / Phase B | ⚠️ **只做一半** | `ctf_dispatcher.py` 仍 9892 行；`_phase_recon` 等仍在内（`ctf_dispatcher.py:1563`） |
| 黑板驱动决策 | 隐含目标 | ❌ **未做** | `SessionContextView` 仅在 `pa_agent.py:501` 被读来拼 prompt 上下文（取最近 5 条事件），无控制器读黑板**决定下一步动作** |

**头号证据 —— 循环委托（`ctf_dispatcher.py:374`）：**

```python
return await self.coordinator.execute(self, **kwargs)
```

coordinator 把 `self`（dispatcher 本体）传回去，再回调 dispatcher 自己的 `_phase_*`。这正是 Cairn 方案承认的 **"coordinator↔dispatcher 循环委托 + 14 个 `_ready` 标志位"**。coordinator 目前是空壳，真正逻辑还在 dispatcher 里 —— façade 没收尾，循环依赖就拆不掉，黑板控制器也没法干净地长上去。

---

## 2. 研究依据（黑板思维 + 获奖作品）

### 2.1 正统 Blackboard = 黑板 + Agent 组 + **控制单元**

2025 两篇 arxiv（[LbMAS, 2507.01701](https://arxiv.org/abs/2507.01701)；[数据科学黑板系统, 2510.01285](https://arxiv.org/abs/2510.01285)）核心结论：黑板架构相对强基线有 **13%–57% 端到端成功率提升，且 token 更省**。三件套缺一不可：

- **黑板**：FlagHunter 已有 → `session_ledger`（append-only 事件）。
- **Agent 组（知识源）**：已有 → `hypothesis_engine` / `strategy_registry` / `verifier` / `recovery`。
- **控制单元**：**缺**。FlagHunter 现在是 coordinator 写死的 `observe→reason→explore→verify→recover` 顺序流，不是"读黑板态再挑动作"。

### 2.2 获奖作品的反直觉结论：别急着堆多 Agent

XBOW 基准（[Aaron Brown 架构复盘](https://medium.com/data-science-collective/building-the-leading-open-source-pentesting-agent-architecture-lessons-from-xbow-benchmark-f6874f932ca4)、[MAPTA, 2508.20816](https://arxiv.org/html/2508.20816v1)）：**单一 meta-agent（单决策者）达 84.62%，打平/超过多数多 Agent 方案**。与 Anthropic 工程观点一致——多 Agent 价值在"并行探索 + 上下文隔离"，不在模仿人类岗位分工。

> **对 FlagHunter 的含义**：crew 模式（已冻结）保持冻结是对的；优化预算花在**单 agent 的控制环质量**上，不要再切角色。

---

## 3. 推荐改造（按性价比排序）

### 🥇 工作流 A：收尾 façade 拆分（高收益 / 中风险 / 可量化）

**目标**：把执行体真正搬出 dispatcher，让 coordinator 不再回调 dispatcher、消灭 14 个 `_ready` 标志与循环委托。

**实施清单**：

1. 新建 `pentestagent/agents/pa_agent/recon_executor.py`，把 `_phase_recon`（`ctf_dispatcher.py:1563`，约 319 行）及其纯依赖搬入 `ReconExecutor`；dispatcher 侧保留 1 行委托。
2. 新建 `explore_executor.py`，搬 explore/strategy 执行体与 `verify` 调用编排。
3. coordinator 改为**持有** `ReconExecutor`/`ExploreExecutor`/`Verifier`/`Recovery` 实例并直接驱动，**不再接收 dispatcher 本体**——把 `coordinator.execute(self, ...)` 改为 `coordinator.execute(state, deps)`。
4. 逐个删除 `_ready` 标志位，改由 executor 返回值/状态对象表达就绪态。
5. dispatcher 退化为对外兼容入口（CLI/MCP/Web 旧调用路径适配）。

**验收指标（客观可量化）**：
- `ctf_dispatcher.py` 行数 **9892 → < 3000**。
- `coordinator.py` 中对 dispatcher 本体的回调 **= 0**（`grep self.dispatcher / coordinator.execute(self` 归零）。
- `_ready` 标志位 **14 → 0**。
- 全量 `pytest` 相对当前 HEAD **零新增失败**（基线：5 条预先存在失败，详见 §5）。

**风险控制**：每搬一个执行体就 `git stash` 对比验证"疑似新失败"是否在搬迁前 HEAD 同样复现；分多个小 commit，每个 commit 后 push。

---

### 🥈 工作流 B：给黑板装控制单元（最贴近"黑板思维"、直接提解题率）

> **前置依赖：工作流 A 必须先完成**（控制器没法长在循环委托的 dispatcher 上）。

**目标**：新增轻量 `BlackboardController`，把 ledger 从"审计日志"升级成真正驱动决策的黑板，并闭合 **"验证失败 → 切候选链"** 回馈环（Cairn 方案承认现在缺这个闭环）。

**实施清单**：

1. 新建 `pentestagent/agents/pa_agent/blackboard_controller.py`：
   - 输入：`SessionContextView.build_run_context(run_id)`（事实 / 待验证假设 / 最近失败事件）。
   - 输出：`ControlAction`（`continue_chain | switch_candidate | escalate_recon | request_verify | stop`）。
   - 打分：按"未验证假设数 × 置信度 − 近 N 轮失败惩罚"挑当前最高价值动作。
2. coordinator 主循环每轮调用 `controller.decide(context)`，替代写死的 `phase` 顺序流。
3. 接入回馈环：`verifier` 返回 `rejected` → 写 `verification_decision` 事件 → 下一轮 controller 读到失败 → 输出 `switch_candidate`，自动切到 `StrategyRegistry` 的下一条候选链。
4. 所有 `ControlAction` 写 `build_control_action_started/completed_event`（audit_events 已有这两个 builder，直接复用）。

**验收指标**：
- candidate→verified 转化率相对基线提升（基线见 §5）。
- wrong-flag / verification-rejected 后能**自动切候选链**而非停在原链（新增端到端用例覆盖）。
- 平均 prompt context 长度不增（黑板按需切片，不是全量灌入）。

---

### 🥉 工作流 C：先量化基线（低风险，可与 A 并行）

**目标**：修通 4 条预先存在的验收链失败，拿到改造前的解题率基线，让 A/B 的收益可对比。

**实施清单**：
1. 复现并定位：`easy_tornado` SSTI（×2）、`php_object_injection` 提权、`profile_photo_poisoning`。
2. 这是文档自评"agent 真正会判断仅 50–60%"的实证样本——逐链分析卡在 observe / hypothesis / verify 哪一步。
3. 记录 candidate→verified 转化率、wrong-flag 恢复成功率两项基线数。

---

## 4. 明确不做的事

1. **不重写 crew / 不再切多 Agent 角色**——研究证据（§2.2）显示单 meta-agent 更优，crew 保持冻结。
2. **不引入 Cairn 的 `Fact/Intent/Hint` 术语替换**——保留现有 `Hypothesis/Verification/Artifact` 语义与测试基础。
3. **不拆双进程 server/dispatcher**——当前痛点是状态主线 + 循环委托，不是进程数。
4. **不用数据库替代 JSONL**——append-only ledger 已够用。

---

## 5. 测试基线（改造前必须先记录）

当前 `main` 上 **5 条预先存在失败**（非回归，改造时作为基线对照）：
- `test_ctf_dispatcher_llm7_blocks_external_domain_request`（allowlist）
- easy_tornado SSTI 验收链 ×2
- php_object_injection 提权链
- profile_photo_poisoning 链

任何重构后 `pytest` 必须与此基线逐条对齐，**零新增失败**才允许 commit + push。

---

## 6. 建议执行顺序

```
C（量化基线，可并行） → A（façade 收尾） → B（黑板控制单元） → 复测 candidate→verified 转化率
```

推荐先 A：风险可控、收益用行数客观验证，且是 B 的硬前置。

---

## 7. 来源清单

### 本仓库
- `pentestagent/agents/pa_agent/ctf_dispatcher.py`（9892 行，:374 循环委托，:1563 `_phase_recon`）
- `pentestagent/agents/pa_agent/coordinator.py`（1627 行）
- `pentestagent/harness/*.py` + `tests/unit/harness/*`
- `pentestagent/knowledge/session_context.py`（:501 被 pa_agent 消费）
- [`FlagHunter_Harness优化方案_借鉴Cairn_V1.md`](FlagHunter_Harness优化方案_借鉴Cairn_V1.md)
- [`agent-intelligence-roadmap.md`](../agent-intelligence-roadmap.md)

### 外部研究
- [LbMAS：Exploring Advanced LLM Multi-Agent Systems Based on Blackboard Architecture, arxiv 2507.01701](https://arxiv.org/abs/2507.01701)
- [LLM-Based Multi-Agent Blackboard System for Information Discovery, arxiv 2510.01285](https://arxiv.org/abs/2510.01285)
- [Building the Leading Open-Source Pentesting Agent: Architecture Lessons from XBOW Benchmark（Aaron Brown）](https://medium.com/data-science-collective/building-the-leading-open-source-pentesting-agent-architecture-lessons-from-xbow-benchmark-f6874f932ca4)
- [MAPTA: Multi-Agent Penetration Testing AI for the Web, arxiv 2508.20816](https://arxiv.org/html/2508.20816v1)
- Anthropic — Multi-agent research system / Managed agents（解耦 brain 与 hands、并行探索 + 上下文隔离）
