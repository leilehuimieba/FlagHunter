# CTF Agent 自由探索与 LLM 驱动兜底 V1

> 适用范围：`pentestagent/agents/pa_agent/` 下的策略层、假设引擎、调度器。
>
> 本文档解决一个根本问题：当没有预注册策略匹配时，agent 必须能退到"LLM 自由调工具"的兜底通道，而不是直接放弃或返回 stop_no_progress。
>
> 本文档与 `CTF_Agent_主干架构规范_V1.md`、`CTF_Agent_状态模型与接口契约_V1.md`、`CTF_Agent_能力层与记忆模型_V1.md` 配套阅读。

---

## 1. 背景：为什么要写这份文档

### 1.1 当前系统的扩展瓶颈

每出现一道新题型，当前流程是：

1. 在 `状态模型 §9.1` 加结构感知映射表条目
2. 在 `能力层 §3.2` 加 `web_subtype` 标签
3. 在 `hypothesis_engine._rule_based_hypotheses()` 加规则
4. 在 `strategy_registry.build_default()` 注册 `StrategyDefinition`
5. 在 `ctf_dispatcher` 加 `_run_xxx_strategy()` 方法
6. 在 `_WEB_STRATEGY_ORDER` 加新策略名
7. 在 `_CHAIN_BY_KIND` / `_CHAIN_NAME_FOR_HYPOTHESIS` 加映射
8. 在 `完整测试用例集` 加 ADV 用例

**这套流程对 easy_tornado 这种已知题型有效，但对真正未知的题型不可扩展。**

### 1.2 对比：codex / 裸 LLM 为什么快

codex 本质是"LLM + 一个 shell 工具 + 持续上下文"。它的解题流程：

1. LLM 看页面
2. LLM 决定下一步（curl / sqlmap / 写 python 脚本）
3. LLM 看输出
4. LLM 决定再下一步
5. ……直到拿到 flag

**它的优势是没有约束。它的劣势是没有验证、无并行、无失败切换、无记忆。**

### 1.3 我们的定位：deterministic + LLM-driven 混合

我们的优势必须是**双轨**：

- **轨道 A（高置信确定性轨道）**：已知题型走预注册策略链，可复现、可审计、有验证闭环
- **轨道 B（LLM-driven 兜底轨道）**：未知题型走 LLM 自由探索，由 ReasoningLayer 包裹，仍然写入 CTFState、走 Verifier 验证

**关键约束**：轨道 B 不绕过 CTFState、Verifier、RecoveryController。它只是把"决定下一步动作"的决策权从 deterministic precondition 移交给 LLM，但所有结果仍然进同一套状态机。

---

## 2. 总体设计

### 2.1 新策略 kind：`llm_driven_exploration`

注册一个**永远适用**（precondition 恒为 True 但置信度最低）的策略，作为 chain 的最后兜底：

```python
StrategyDefinition(
    kind="llm_driven_exploration",
    chain_name="*",                            # 通用兜底
    precondition_description="无前提；当其他策略全部不适用或耗尽时启用。",
    minimal_experiment="由 LLM 基于当前 observations 选择下一个 http_request / shell 动作。",
    success_signal="LLM 调用后返回 verified/runtime flag。",
    failure_signal="连续 N 次 LLM-driven 动作均无 progress 或被 budget 限制。",
    escalation_condition="若 LLM 给出新的结构线索（如新发现 endpoint），允许 HypothesisEngine 重排假设。",
    precondition=lambda ctx: True,
    execute=lambda ctx: ctx.dispatcher._run_llm_driven_exploration(ctx),
)
```

### 2.2 排序权重

在 `HypothesisEngine.rank()` 中：

- `llm_driven_exploration` 的 base confidence = `0.15`
- 永远排在最后（除非所有其他假设都被 reject/exhaust）
- 当 `len(applicable_other_hypotheses) == 0` 时，权重升到 `0.55`（避免直接 stop）

### 2.3 与现有 chain 执行器的衔接

`_execute_web_chain`（及 sqli/xss/lfi 等链）末尾追加：

```python
# 所有预注册策略都跑完且无 progress 时，触发 LLM-driven 兜底
if not progress and self.state and self.state.is_llm_exploration_allowed():
    outcome = await self._run_llm_driven_exploration(
        self._strategy_context(target=target, page_features=page_features, hint=hint)
    )
    if outcome.flag:
        return outcome
```

`is_llm_exploration_allowed()` 是 CTFState 新方法，控制以下两条：

- 本题已消耗的 LLM-driven 动作数 < `max_llm_actions_per_task`（默认 8）
- 本会话总 LLM token 消耗 < `llm_budget_tokens`（从 Settings 读取）

---

## 3. `_run_llm_driven_exploration` 详细契约

### 3.1 输入

- `StrategyContext`（含 dispatcher、target、page_features、hint、extras）
- 通过 `ctx.dispatcher.state` 读取完整 CTFState
- 通过 `ctx.dispatcher.llm` 调用 LLM

### 3.2 流程

```
loop step in [1 .. max_llm_actions_per_task]:
    1. 装配上下文 prompt（按需，不全量）：
       - 当前 target / 已知 endpoints / raw_links（top 20）
       - 最近 5 条 observations 摘要（>200 字符的内容截断）
       - 已尝试的策略列表 + 失败原因
       - 已 reject 的 candidate flag（避免重复提交）
       - 工具白名单（http_request / shell / browser，按 CapabilityRegistry）
    2. 提示 LLM 输出结构化 next_action（JSON schema）：
       {
         "action_type": "http_request" | "shell" | "stop",
         "rationale": "<为什么这一步>",
         "payload": { 工具具体参数 },
         "expected_signal": "<期望看到什么才算 progress>",
         "next_if_fail": "<失败后转向哪个方向>"
       }
    3. PreActionReasoning.evaluate(next_action)：
       - 拒绝违反 ToolGuard 的动作
       - 拒绝重复 reject flag 的提交
       - 拒绝预算超限的动作
    4. 执行动作，收集 response
    5. _scan_and_store(response.body) → 触发 Verifier
    6. 如果 verified/runtime flag → return _ChainOutcome(flag=...)
    7. 把 (action, response, verifier_decision) 写入 state.observations
    8. Postmortem.record(step) 评估 expected_signal 是否兑现
    9. 若 next_if_fail 提示 "switch chain"，立即 break 并交回 RecoveryController
```

### 3.3 输出

- 命中 flag：`_ChainOutcome(progress=True, flag=...)`
- 无 flag 但有 progress（新 observations）：`_ChainOutcome(progress=True, reason="llm_exploration: N steps")`
- 完全无 progress：`_ChainOutcome(progress=False, reason="llm_exploration_exhausted")`

### 3.4 禁止事项

- 不允许 LLM 直接修改 CTFState（只能通过 dispatcher 的写入接口）
- 不允许 LLM 决定"flag 成立"——所有 flag 必须过 Verifier
- 不允许 LLM 调用未在 CapabilityRegistry 注册的工具
- 不允许 LLM 提交已在 `state.rejected_flags` 中的 flag
- 不允许 LLM 写入 `loot/` 目录之外的文件
- 不允许 LLM 调用 `pip install` / `apt install` 等安装命令（应通过 CapabilityRegistry 的 install 路径）

---

## 4. PreActionReasoning 强化

### 4.1 现状

`reasoning.py` 已有 `PreActionReasoning` 骨架，但只在少数路径调用。

### 4.2 目标契约

每次执行 LLM-driven 动作前，必须输出 Q1~Q4：

| 问题 | 含义 | 阻断规则 |
|---|---|---|
| Q1 这个动作要回答什么问题？ | 必须能映射到一个 hypothesis 或 information gap | 空答 → 阻断 |
| Q2 期望看到什么信号才算 progress？ | 必须是可观测的（status code / 关键词 / flag 正则） | 期望模糊（如 "看看效果"）→ 阻断 |
| Q3 如果失败转向哪？ | 必须给出 fallback chain 或 hypothesis | 无 fallback → 允许执行但记入 weak_decision_log |
| Q4 这一步是否重复了已 reject 的尝试？ | 自动检查 state.rejected_flags + 历史动作签名 | 重复 → 阻断 |

### 4.3 实现位置

`reasoning.py::PreActionReasoning.evaluate(action_spec, state)` → 返回 `ReasoningDecision(approve: bool, reason: str, downgrade_to: Optional[str])`

### 4.4 集成点

`_run_llm_driven_exploration` 第 3 步必须调用 PreActionReasoning，决策拒绝时不执行动作。

---

## 5. CapabilityRegistry 三路决策树（详细）

### 5.1 当前差距

`capability_registry.py` 只有 `require()` 抛 ToolMissingError，没有"降质/安装/不可用"三路决策。

### 5.2 目标三路决策

```
LLM-driven 动作申请工具 tool_x：
  ├─ tool_x 在 capability_table 且 healthy → APPROVED，直接执行
  ├─ tool_x 缺失但有 fallback (e.g. sqlmap → manual_sqli_payload) → DEGRADE，
  │     PreActionReasoning 注入降质提示，让 LLM 生成 manual payload
  └─ tool_x 缺失且无 fallback：
        ├─ 用户已授权 auto_install → 走安装路径（仅限白名单）
        └─ 未授权 → UNAVAILABLE，返回 RecoveryController.on_missing_tools()
```

### 5.3 capability_table 结构

```python
@dataclass
class CapabilityEntry:
    tool_name: str
    is_available: bool
    health_state: Literal["healthy", "degraded", "down"]
    last_check_ts: float
    fallback_tool: Optional[str] = None      # 降质映射
    install_command: Optional[str] = None    # 仅白名单工具有
    requires_user_confirm: bool = True       # 安装前是否问用户
```

### 5.4 默认降质映射表

| 缺失工具 | 降质到 | 说明 |
|---|---|---|
| sqlmap | manual_sqli_payload | LLM 手工构造常见 payload |
| nmap | http_request 端口探测 | HTTP HEAD 探测 80/443/8080 等 |
| dirb / gobuster | manual_path_enumeration | LLM 给出常见路径清单 |
| burpsuite | http_request | 用 raw http 替代 |
| metasploit | (无) | UNAVAILABLE，提示用户 |

---

## 6. CTFState 新增字段

在 `ctf_state.py` 增加：

```python
@dataclass
class CTFState:
    # ... 已有字段
    llm_exploration_steps: int = 0           # 本题已消耗 LLM-driven 步数
    llm_exploration_log: list["LLMStepLog"] = field(default_factory=list)
    weak_decision_log: list[str] = field(default_factory=list)  # PreActionReasoning Q3 无 fallback

    def is_llm_exploration_allowed(self, max_steps: int = 8) -> bool:
        return self.llm_exploration_steps < max_steps

    def record_llm_step(self, log: "LLMStepLog") -> None:
        self.llm_exploration_steps += 1
        self.llm_exploration_log.append(log)


@dataclass
class LLMStepLog:
    step: int
    action_type: str
    rationale: str
    payload_summary: str    # ≤ 200 字符
    response_summary: str   # ≤ 300 字符
    verifier_decision: str  # verified / runtime / candidate / rejected / none
    expected_signal_met: bool
    timestamp: float
```

**schema_version 升到 `1.2`**，`CHANGELOG_schema.md` 记录变更。

---

## 7. 完整测试用例（追加到 `CTF_Agent_完整测试用例集_V1.md`）

| 用例 | Given | When | Then |
|---|---|---|---|
| LLM1 | 所有 web 策略 precondition 均 False，state.llm_exploration_steps=0 | `_execute_web_chain` 执行完后无 progress | 触发 `_run_llm_driven_exploration`，state.llm_exploration_steps ≥ 1 |
| LLM2 | LLM 返回 action_type=http_request, payload={url: ".../admin"} | PreActionReasoning Q2 期望信号 = "200 且 body 含 admin panel" | 执行后写入 state.observations，verifier 未触发 |
| LLM3 | LLM 重复尝试已 reject 的 flag `flag{test123}` | PreActionReasoning Q4 检测到重复 | 阻断，记入 weak_decision_log，不执行 |
| LLM4 | LLM 申请工具 `sqlmap`，capability_table 中 sqlmap.is_available=False，fallback=`manual_sqli_payload` | CapabilityRegistry 走 DEGRADE 路径 | PreActionReasoning 注入降质提示，LLM 重新输出 manual payload |
| LLM5 | state.llm_exploration_steps=8（达上限） | 再次触发 LLM 兜底 | `is_llm_exploration_allowed()` 返回 False，跳过，RecoveryController 决定 stop_no_progress |
| LLM6 | LLM 申请工具 `pip install xxxtool` | PreActionReasoning Q1 阻断 | 不执行，记 weak_decision_log |
| LLM7 | LLM 申请向 collector 之外的外部域名发请求 | ToolGuard 阻断 | 不执行 |
| LLM8 | LLM-driven 动作发现 `/admin/secret.txt` 含 flag | Verifier 路径 B：runtime flag | _ChainOutcome.flag 返回，记忆写入 |

**门禁规则追加**：

| 改动 | 必须通过的用例 |
|---|---|
| 改 `_run_llm_driven_exploration` | LLM1~LLM3 + LLM5 + LLM8 |
| 改 PreActionReasoning | LLM2 + LLM3 + LLM6 |
| 改 CapabilityRegistry 三路决策 | LLM4 + LLM6 |
| 改 CTFState 新增字段 | LLM5 + schema_version 升级测试 |

---

## 8. 与现有规范的关系

### 8.1 不冲突的部分

- 不修改 Verifier 5 路径算法
- 不修改 RecoveryController 现有 action 枚举
- 不修改 StrategyRegistry 已有 9 个策略

### 8.2 需要更新的部分

| 文档 | 更新点 |
|---|---|
| `CTF_Agent_主干架构规范_V1.md` | §4 主循环中加 "LLM-driven 兜底" 节点 |
| `CTF_Agent_状态模型与接口契约_V1.md` | §3 新增 LLMStepLog 字段；schema_version → 1.2 |
| `CTF_Agent_能力层与记忆模型_V1.md` | §4 三路决策树详细化（取代当前简化版） |
| `CTF_Agent_智能推理层规范_V1.md` | PreActionReasoning Q1~Q4 强制规则 |
| `CTF_Agent_分阶段开发计划_V1.md` | 新增 Phase 5.7（在 5.5 后、6 前）= LLM-driven 兜底落地 |
| `CHANGELOG_schema.md` | 记录 1.1 → 1.2 |

---

## 9. 实施顺序（给开发 agent 的硬性顺序）

| 步骤 | 文件 | 验收 |
|---|---|---|
| 1 | `ctf_state.py` 增加 LLMStepLog / llm_exploration_steps / is_llm_exploration_allowed | schema 测试通过 |
| 2 | `reasoning.py` 完成 PreActionReasoning Q1~Q4 + ReasoningDecision | LLM2/LLM3/LLM6 单元测试通过 |
| 3 | `capability_registry.py` 三路决策树 + capability_table + 默认降质映射 | LLM4/LLM6 通过 |
| 4 | `ctf_dispatcher.py` 新增 `_run_llm_driven_exploration` | LLM1/LLM5/LLM8 通过 |
| 5 | `strategy_registry.py` 注册 `llm_driven_exploration` StrategyDefinition | 注册测试通过 |
| 6 | `hypothesis_engine.py` 加 llm_driven_exploration 排序逻辑（始终最低优先） | 排序单测通过 |
| 7 | `_execute_web_chain` / `_execute_sqli_chain` 等加兜底调用 | LLM1 集成通过 |
| 8 | 更新 4 份关联规范文档 | docs 一致性检查通过 |

**禁止跨步骤合并 PR**。每步独立 commit，便于回退。

---

## 10. 验收完成标准

- [ ] 在 easy_tornado 上重跑，即使移除手写的 `hash_guarded_file_read` 策略，LLM-driven 兜底也能在 8 步内拿到 flag
- [ ] 在一道**全新未知题**（开发 agent 自选一道 BUUOJ 题目）上，agent 不再返回 `stop_no_progress`，而是触发 LLM-driven 兜底
- [ ] 所有 LLM-driven 动作都有 PreActionReasoning Q1~Q4 记录
- [ ] 所有 flag 仍然过 Verifier 5 路径
- [ ] 测试用例 LLM1~LLM8 全部通过
- [ ] 现有 860 测试全部不退化
