# FlagHunter 架构优化方案：黑板控制单元 + façade 收尾（V1）

> 日期：2026-06-16
> 适用范围：`pentestagent/agents/pa_agent/`（dispatcher / coordinator / executor）与 `pentestagent/harness/`、`pentestagent/knowledge/session_context.py`
> 文档性质：**设计说明 + 逐项实施清单**，不改主干语义、不推倒重写。是 [`FlagHunter_Harness优化方案_借鉴Cairn_V1.md`](FlagHunter_Harness优化方案_借鉴Cairn_V1.md) 的收尾续作。

---

## 0. 一句话结论

**架构已经不差：黑板思维（blackboard-lite）该补的壳已经落地。** 当前缺的不是"更多模块"，更不是"更重的控制平面"，而是两件事：

1. `ctf_dispatcher.py` 仍是 **9892 行**上帝对象，façade 拆分只做了一半（coordinator 抽出来了，但回调 dispatcher 自身方法）——这本身就是**过度 Harness**，把人类流程强加给模型。
2. 有"黑板"（事件账本 ledger），但它是写多读少的审计日志，不是模型读写的共享黑板。**方向是"补协议而非补控制"**：升级成 Fact/Intent/Hint 极简协议、把决策权还给模型（依据 §2.3 Cairn 作者复盘"补能力不补信心"），而不是加一个替模型决策的打分控制器。

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

### 2.3 Cairn 作者复盘：状态/行动/控制三层闭环 + "补能力不补信心"

来源：[两届TCH之后——AI 渗透测试 Agent 的 Harness 工程演进](https://mp.weixin.qq.com/s/pbieEet9VCR5iLhjViokIA)（Cairn 作者本人，全国第三、唯一 SOLO、**唯一 AK 全部 54 题**选手）。这篇直接提供了一套可复用的判断框架，并修正了本文 §3 原 🥈 的方向。

**判断框架——所有方案都在补同一个闭环 `状态→决策→行动→反馈→新状态`，拆成三层：**

| 层 | 解决什么 | 各队代表做法 | FlagHunter 对照 |
|---|---|---|---|
| 状态层 | 系统如何知道世界长什么样 | 绿盟 Idea/Memory Board 分"假设vs事实"；Cairn 压成 **Fact/Intent/Hint 事实图** | ✅ 有 `CTFState`+ledger+session_context；但真相分散 7 处，需"状态成为系统资产，而非模型回忆" |
| 行动层 | 系统如何可靠改变世界 | 工具网关/沙箱/C2；**Cairn/yhy 的 Meta-Tooling：agent 用 Python 代码组合工具，而非每工具封一层 MCP** | ⚠️ 你们是"每工具封一层"，缺 code-use 动作面 |
| 控制层 | 系统如何决定下一步 | 绿盟 Observer / 清华 Planner 攻击树……从 Prompt 软约束迁到代码/协议硬约束 | ⚠️ 写死 phase 顺序流 + 循环委托 |

**最尖锐的论点（必须纳入决策）：**

> **"很多控制不是在补能力，而是在补信心（信任缺失）。这种基于信任缺失的控制，会随模型进化变成冗余代码。"**

证据：Cairn 不预设攻击流程、不定义角色、不用 RAG，只给**黑板(Fact) + Dispatcher(Intent) + Kali 容器**，Harness 体现在**信息结构**而非**行为约束**上——Worker 只能通过 Fact/Intent/Hint 三对象交互，这是唯一协议，其余全交给模型。结果用全场最少工程 + 最少 Token（前十唯一消息数数十万级，别人百万级）做到唯一 AK。Anthropic《Managed Agents》佐证：Harness 编码"模型能力不足的假设"，模型变强后反成 dead weight。

> **对本文的修正**：原 §3 🥈 设计的"打分式控制器（替模型挑下一步动作）"正属于"用控制补信心"那一类（类比绿盟 Observer）。据此论点，🥈 改写为**极简协议路线**——见下。façade 收尾（🥇）则获得更强背书（"减法哲学/Less is more"）。

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

### 🥈 工作流 B：把 ledger 升级成 Fact/Intent/Hint 极简黑板协议（修订版）

> **方向修订（依据 §2.3）**：放弃原"打分式 BlackboardController（替模型挑动作）"——那是"用控制补信心"。改做**极简协议**：黑板只承载结构化事实/意图/提示，**决策权还给模型**，控制层薄到只剩"协议 + 失败回馈回路"，不做 FSM / 打分。
>
> **前置依赖：工作流 A 必须先完成**（协议没法长在循环委托的 dispatcher 上）。

**目标**：把 `session_ledger` 从"写多读少的审计日志"升级成**模型可读写的共享黑板**，用三类对象统一状态/意图/提示的流转，闭合 **"验证失败 → 模型自主切候选"** 回馈环——但不替模型决策。

**协议设计（对齐 Cairn，但复用 FlagHunter 现有语义，不做术语级迁移）**：

| 黑板对象 | FlagHunter 现有载体 | 语义 |
|---|---|---|
| **Fact** | `Observation / Artifact / VerificationResult(verified)` | 已确证的世界状态，append-only 写入 ledger |
| **Intent** | `Hypothesis / next_experiments` | 模型/规则提出的待验证意图，带置信度但**不由系统打分裁决** |
| **Hint** | 用户 hint / `challengePath` / recovery 提示 | 外部注入的引导 |

**实施清单**：

1. 在 `knowledge/session_context.py` 的 `SessionContextView` 上新增 `build_blackboard_view(run_id)`：把 ledger 事件投影成 `{facts:[...], intents:[...], hints:[...]}` 三段式**低噪声视图**（对标绿盟"假设 vs 事实"分离）。
2. coordinator 主循环不再走写死 phase 顺序：每轮把 blackboard view 注入 prompt，**让模型自己读事实、表达下一个 Intent**；系统只负责把模型产出的 Intent 与执行结果（Fact）写回 ledger。
3. 闭合回馈环（**协议级，非打分**）：`verifier` 返回 `rejected` → 写一条 `Fact(kind=refuted, target=<intent_id>)` → 下一轮该 refuted fact 出现在 blackboard view 里 → **模型自己看到失败、自己换候选**。系统不强制 `switch`，只保证失败事实对模型可见。
4. 复用 `audit_events` 的 `build_control_action_started/completed_event` 记录每次 Intent→执行，保持可审计/可回放。
5. **可丢弃性原则**：blackboard view 是纯投影，不持久化第二份真相；ledger 仍是唯一事实源。

**验收指标**：
- candidate→verified 转化率相对基线提升（基线见 §5）。
- verification-rejected 后，**模型能在不被系统强制的情况下自主切到新候选**（新增端到端用例：注入一条 refuted fact，断言下一轮模型 Intent 改变）。
- 平均 prompt context 长度**不增**（三段式低噪声视图，不是全量灌入）——可对比改造前后 token 数验证"补协议而非补控制"是否真省 token。

---

### 🆕 工作流 D（可选）：行动层引入 Meta-Tooling / code-use

**依据**：§2.3 行动层——Cairn/yhy 验证过"让 agent 用 Python 代码组合工具"优于"每工具封一层 MCP/文本"。FlagHunter 目前是后者。

**最小实施**：新增一个 `code_exec` 动作面（受 `permission_enforcer` 管控），允许模型在沙箱/Docker runtime 里写短 Python 脚本组合 browser/terminal/http/notes，而非逐个调用工具文本。**先做 PoC 验证 token 与成功率收益，再决定是否扩面**。风险较高（代码执行面），排在 A/B 之后。

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
C（量化基线，可并行） → A（façade 收尾） → B（Fact/Intent/Hint 极简黑板协议） → 复测 candidate→verified 转化率与 token
        └─（A 之后可选）→ D（Meta-Tooling / code-use PoC）
```

推荐先 A：风险可控、收益用行数客观验证，且是 B 的硬前置。B 走"补协议而非补控制"路线（§2.3），D 为可选高风险项。

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
- [两届TCH之后——AI 渗透测试 Agent 的 Harness 工程演进、防御与我的思考（Cairn 作者）](https://mp.weixin.qq.com/s/pbieEet9VCR5iLhjViokIA)——状态/行动/控制三层闭环框架、"补能力不补信心"论点、多 Agent=并行算力而非分工（本文 §2.3 即据此修订）
