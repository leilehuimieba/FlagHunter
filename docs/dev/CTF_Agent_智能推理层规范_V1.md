# CTF Agent 智能推理层规范 V1

> **本文档上游**：`CTF_Agent_主干架构规范_V1.md`（组件定义）、`CTF_Agent_状态模型与接口契约_V1.md`（数据结构）  
> **本文档下游**：`CTF_Agent_分阶段开发计划_V1.md`（Phase 5.5）、`CTF_Agent_完整测试用例集_V1.md`（R 系列用例）  
> **实现约束**：`CTF_Agent_实现约束与协作规范_V1.md`

---

## 1. 为什么需要推理层

当前架构的核心瓶颈不是缺少工具，而是缺少推理的显式结构。

具体表现：

- agent 在行动前没有被迫说清楚"为什么做这一步"
- 结果出来后，任何结果都可以被事后合理化
- 失败时只调整分数，不提炼失败原因
- 停止时只说"exhausted"，不说"如果你给我 X 我还能继续"

**推理层的目标**：让 agent 在每次行动的前后都有结构化的思考记录，这些记录可被测试、可被审计、可被用于后续决策。

---

## 2. 推理层包含的五个组件

| 组件 | 对应建议 | 核心功能 |
|---|---|---|
| A. 行动前推理（Pre-Action Scratchpad） | 建议一 | 行动前强制结构化推理 |
| B. 观察-解释-假设三层模型 | 建议二 | 将 raw 观察和推断分离 |
| C. 挑战设计者视角（Adversarial Lens） | 建议三 | 识别 rabbit hole |
| D. 失败事后分析（Failure Postmortem） | 建议五 | 从失败中提炼可用经验 |
| E. 智能停止条件 | 建议七 | 停止时输出有用信息 |

---

## 3. 组件 A：行动前推理（Pre-Action Scratchpad）

### 3.1 设计目标

在每次 `Execute Strategy` 之前，agent 必须完成一次结构化推理，回答以下 4 个问题。这不是可选项，是控制流里的强制步骤。

### 3.2 数据结构

```python
@dataclass
class PreActionReasoning:
    id: str                        # "par_{experiment_id}"
    experiment_id: str             # 绑定到哪个实验
    created_at: float

    # Q1: 当前信念
    current_belief: str            # 自然语言：我现在相信什么？最强假设是什么？
    belief_evidence: list[str]     # 支持这个信念的观察 ID 列表

    # Q2: 行动理由
    action_rationale: str          # 为什么这一步是最优选择？
    alternatives_rejected: list[str]  # 考虑过哪些其他选项，为什么没选

    # Q3: 成功预期
    expected_success_signal: str   # 如果成功，期待看到什么？
    success_interpretation: str    # 看到成功信号，我会得出什么结论？

    # Q4: 失败预期（预承诺解释）
    expected_failure_signal: str   # 如果失败，期待看到什么？
    failure_interpretation: str    # 看到失败信号，我会得出什么结论？
    failure_next_action: Literal[
        "retry_with_different_payload",     # 换 payload 重试同一原语
        "escalate_to_blind_approach",       # 盲注/盲利用升级
        "pivot_to_source_leak",             # 转向源码泄露路线
        "try_next_ranked_hypothesis",       # 切换到 HypothesisEngine 下一个假设
        "trigger_adversarial_lens",         # 主动触发挑战设计者视角
        "request_user_hint",                # 向用户请求提示
        "stop_and_report",                  # 诚实停止并输出 StopReport
    ]
    # 禁止值：任何等价于"继续当前假设"的字符串
```

### 3.3 控制流位置

```
Pick Next Experiment
  -> [MANDATORY] Generate PreActionReasoning   ← 新增步骤
       input: CTFState + current Experiment
       output: PreActionReasoning（写入 CTFState.pre_action_reasonings）
  -> Execute Strategy
  -> Verify Result
  -> [MANDATORY] Evaluate against PreActionReasoning ← 新增步骤
       检查实际结果是否与 Q3/Q4 预承诺一致
```

### 3.4 预承诺评估规则（含 Surprise 判定算法）

实验完成后，按以下三步判定实际结果属于哪一类。

#### Step 1：结构化预期校验（算法 A，确定性）

`PreActionReasoning` 生成时，Q3/Q4 必须包含结构化字段，不是只有自然语言：

```python
@dataclass
class ExpectedSignal:
    pattern_type: Literal[
        "status_code",        # 例如 200, 302, 500
        "response_regex",     # 正则匹配 response body
        "timing_threshold",   # 响应时间阈值（秒）
        "url_redirect",       # 重定向到指定 URL pattern
        "header_present",     # 响应头包含某字段
        "body_contains",      # body 包含指定子串
        "error_pattern",      # 匹配已知错误模板
    ]
    pattern_value: str | int | float
    match_threshold: float    # 0.0 ~ 1.0，多少相似度算"符合"
```

Step 1 用确定性规则检查实际结果是否匹配 Q3 或 Q4 的结构化信号。输出：
- `clear_q3`：明确匹配 Q3
- `clear_q4`：明确匹配 Q4
- `ambiguous`：都不明确匹配

#### Step 2：语义兜底判定（算法 B，LLM）

仅当 Step 1 输出 `ambiguous` 时触发：

```
Prompt:
  实验目标：{Q1 current_belief}
  预期成功信号：{Q3 自然语言描述}
  预期失败信号：{Q4 自然语言描述}
  实际观察到的结果：{结果摘要 ≤ 500 字}

  请判定：matches_q3 / matches_q4 / surprise
  并用一句话说明理由（不超过 50 字）。
```

LLM 调用必须使用低温度（temperature ≤ 0.2）和 JSON 输出格式。

#### Step 3：结果分类与动作

| Step 1 结果 | Step 2 结果 | 最终分类 | 动作 |
|---|---|---|---|
| `clear_q3` | 跳过 | 成功 | 按 `success_interpretation` 更新；confidence 提升 +0.2 |
| `clear_q4` | 跳过 | 失败 | 按 `failure_interpretation` 更新；执行 `failure_next_action` |
| `ambiguous` | `matches_q3` | 弱成功 | 按 success，confidence 提升 +0.1（减半） |
| `ambiguous` | `matches_q4` | 弱失败 | 按 failure，但 hypothesis 不直接 exhausted |
| `ambiguous` | `surprise` | **意外** | 触发 Surprise Flag 流程 |
| `ambiguous` | LLM 失败 | 默认按弱失败处理 | 见 §9.X 容错策略 |

#### Surprise Flag 处理流程

1. 记录意外结果到 `CTFState.surprises`，schema 见下
2. 额外调用 LLM 解释"为什么结果出乎意料"（独立于 Step 2 的判定调用）
3. 该解释写入 `Retrospective`（即使假设未失败）
4. 重新排序所有 active 假设
5. 单题累计 Surprise 次数 ≥ 3 时，强制触发一次 AdversarialLens

```python
@dataclass
class SurpriseEvent:
    id: str
    experiment_id: str
    pre_action_reasoning_id: str
    actual_result_summary: str
    step1_output: str           # "ambiguous"
    step2_output: str           # "surprise"
    llm_explanation: str        # 为什么意外
    triggered_at: float
```

### 3.5 实现约束

- PreActionReasoning 必须在 `Execute Strategy` 之前完成，不允许跳过
- 禁止让 LLM 在推理后才倒填 Q3/Q4（必须先填后执行）
- Q4 的 `failure_next_action` 不允许是"继续当前假设"

### 3.6 预期效果

- agent 被迫在行动前明确自己的推理，防止漫无目的的探索
- 意外结果被系统性捕获，而不是被忽略
- 开发者可以通过 `pre_action_reasonings` 回溯 agent 的每一步思考

---

## 4. 组件 B：观察-解释-假设三层模型

### 4.1 问题描述

当前模型只有两层：`observations` → `hypotheses`。

问题：同一个 observation 可能有多种解释，而解释可以被推翻。如果解释和假设混在一起，推翻一个解释会错误地否定一个假设，或者相反。

### 4.2 三层模型

```
Layer 1: Observation（原始事实，不可修改）
  "HTTP 500, body: 'You have an error in your SQL syntax'"

Layer 2: Interpretation（可修订推断，绑定到 Observation）
  "这是 error-based SQLi 的错误回显"

Layer 3: Hypothesis（方向级判断，绑定到 Interpretation）
  kind: "auth_form_sqli"
  route: "error_based" （优先于 blind）
```

### 4.3 数据结构

```python
@dataclass
class Interpretation:
    id: str
    observation_ids: list[str]    # 基于哪些 observations
    content: str                  # 解释的自然语言描述
    confidence: float             # 0.0 ~ 1.0
    status: Literal["active", "retracted", "superseded"]
    retraction_reason: str | None # 如果被撤销，为什么
    hypothesis_ids: list[str]     # 这个解释支撑了哪些假设
    created_at: float
    retracted_at: float | None
```

### 4.4 撤销规则

当某个 `Interpretation` 被撤销时（`status = "retracted"`）：

1. 所有仅依赖该 interpretation 的假设，`confidence` 降低 0.3
2. 不自动 reject 假设（假设可能有其他支撑）
3. 撤销原因必须写入 `retraction_reason`
4. 在 `Retrospective` 里记录这次撤销事件

### 4.5 生成时机

| 触发事件 | 动作 |
|---|---|
| 新 Observation 入库 | 系统尝试为其生成 Interpretation（规则层优先，LLM 兜底） |
| Interpretation 支撑的 Hypothesis 被 rejected | 检查 Interpretation 是否应被撤销 |
| PreActionReasoning Q4 预期的失败出现 | 检查触发失败的 Interpretation 是否有误 |

---

## 5. 组件 C：挑战设计者视角（Adversarial Lens）

### 5.1 设计目标

CTF 题目是被人设计来迷惑解题者的。agent 必须主动建模"出题人的意图"，才能识别 rabbit hole，而不是被动等 confidence 降到 0。

### 5.2 触发时机

在以下情况下，强制触发 Adversarial Lens 分析：

1. 新题目开始，完成初始 recon 之后
2. 某条假设在 3 次实验后仍是 `weak progress`
3. 发现"过于明显"的线索（如首页直接提示"试试 SQL 注入"）

### 5.3 数据结构

```python
@dataclass
class MetaReasoning:
    id: str
    trigger: str           # "initial_recon" | "stuck_hypothesis" | "obvious_hint"
    trigger_ref: str       # 触发它的假设 ID 或 observation ID

    # 挑战设计者视角分析
    intended_challenge_type: str    # "最可能的考点是什么原语"
    likely_red_herrings: list[str]  # "哪些线索可能是迷惑项"
    trust_assessment: dict[str, float]  # {observation_id: 可信度}，key 是 obs ID

    # 对假设排序的影响
    hypothesis_adjustments: dict[str, float]  # {hypothesis_id: confidence_delta}

    rationale: str          # 推理过程的自然语言摘要
    created_at: float
```

### 5.4 LLM Prompt 模板

```
你正在分析一道 CTF 题目。

当前观察到的事实：
{observations_summary}

当前最强假设：
{top_hypothesis}

请以"出题人视角"分析：
1. 这道题的核心考点最可能是什么利用原语？
2. 上面的观察里，哪些可能是出题人设置的迷惑项？请说明理由。
3. 当前最"显眼"的线索（{most_obvious_clue}）可信度如何？
4. 建议对哪些假设的置信度进行调整？

输出格式：JSON，符合 MetaReasoning schema。
```

### 5.5 影响范围

`MetaReasoning.hypothesis_adjustments` 输出的 confidence_delta 会在下一轮 HypothesisEngine 排序时叠加到基础分数上，但权重不超过 0.2（防止单次 meta-reasoning 主导排序）。

---

## 6. 组件 D：失败事后分析（Failure Postmortem）

### 6.1 触发条件

以下任一情况触发：

- 某假设状态变为 `exhausted`
- 某假设状态变为 `rejected`
- `wrong_flag` 被明确拒绝
- `no_progress_count` 达到阈值

### 6.2 数据结构

```python
@dataclass
class Retrospective:
    id: str
    trigger: Literal["hypothesis_exhausted", "hypothesis_rejected",
                     "wrong_flag", "no_progress_threshold", "surprise_flag"]
    hypothesis_id: str | None
    experiment_ids: list[str]       # 这次失败涉及的实验列表

    # 核心分析（LLM 生成，但必须对照 PreActionReasoning 来写）
    failure_root_cause: str         # 工具问题 / 观察误读 / 初始判型错误 / 其他
    earliest_wrong_turn: str        # "如果从头来过，哪一步会做不同选择？"
    collateral_impact: list[str]    # 这次失败对其他假设的影响（hypothesis_id 列表）

    # 对后续决策的输出
    learned_rule: str | None        # 可提炼的规则（如"这类错误信息不可信"）
    strategy_memory_update: bool    # 是否应该写入跨题 StrategyMemory

    created_at: float
```

### 6.3 分析流程

```
1. 收集失败假设的全部 Experiments + PreActionReasonings
2. 对比每次 PreActionReasoning 的 Q4 预期与实际结果
3. 找到第一次"实际结果与 Q4 预期不一致但 agent 没有修正"的点
4. 将该点标记为 earliest_wrong_turn
5. 生成 learned_rule（如果有可泛化的规律）
6. 评估是否写入 StrategyMemory
```

### 6.4 Learned Rule 约束

`learned_rule` 必须是原语级别，不能是题目级别：

允许：
- `"error-based SQLi 提示出现在首页注释里时，可信度降低 0.3"`
- `"若 /admin 返回 404 而非 403，说明路由不存在而非权限不足"`

禁止：
- `"这道题的 SQL 注入是假的"`
- `"BUU 平台的 PHP 题不会真的有 SQLi"`

---

## 7. 组件 E：智能停止条件

### 7.1 问题描述

当前停止逻辑：`所有假设 exhausted → 停止`。

问题：
- 停止时 agent 不说明"差什么就能继续"
- 停止时不区分"真的没有路"和"当前能力不足但路还在"
- 用户无法根据停止报告决定下一步

### 7.2 数据结构

```python
@dataclass
class StopReport:
    reason: Literal[
        "flag_verified",           # 正常成功
        "all_hypotheses_exhausted", # 所有路线走完
        "capability_ceiling",       # 能力不足，但路线存在
        "max_iterations_reached",   # 超过最大迭代次数
        "explicit_user_stop"        # 用户主动停止
    ]

    # 当前状态快照
    verified_flags: list[str]
    candidate_flags: list[str]      # 未被验证的候选（停止后可手动验证）
    rejected_flags: list[str]

    # 为什么停止
    stop_rationale: str

    # 最强的未穷尽假设（如果有）
    strongest_remaining_hypothesis: Hypothesis | None
    why_not_pursued: str | None     # 为什么没继续追这条线

    # 给用户的建议
    user_next_steps: list[str]      # "如果你手动做 X，agent 可能有新的路线"
    missing_capabilities: list[str] # "如果有 Y 工具，可以继续"

    total_experiments: int
    total_iterations: int
    elapsed_seconds: float
```

### 7.3 生成规则

`StopReport` 在任何停止事件发生时必须生成，并且：

1. 如果有 `candidate_flags`，必须在 `user_next_steps` 里说明"手动验证这些候选"
2. 如果 `reason == "capability_ceiling"`，必须列出 `missing_capabilities`
3. 如果 `strongest_remaining_hypothesis` 不为空，必须说明 `why_not_pursued`
4. `user_next_steps` 至少有 1 条，不允许为空列表

### 7.4 TUI 输出格式

停止时 TUI 必须显示：

```
[CTF Agent 停止]
原因：{stop_rationale}

候选 Flag（未验证）：{candidate_flags}
建议下一步：
  1. {user_next_steps[0]}
  2. {user_next_steps[1]}

如需工具支持：{missing_capabilities}
```

---

## 8. 推理层与其他模块的接口

```
CTFCoordinator
  ├── 调用 PreActionReasoning        before Execute Strategy
  ├── 评估 Surprise Flag             after Verify Result
  ├── 调用 AdversarialLens           on trigger conditions
  ├── 调用 Failure Postmortem        on hypothesis exhausted/rejected
  └── 调用 StopReport generator      on any stop condition

ReasoningLayer → CTFState
  writes: pre_action_reasonings, interpretations, meta_reasonings,
          retrospectives, surprises, stop_report

ReasoningLayer → HypothesisEngine
  reads: hypothesis list
  writes: confidence adjustments via MetaReasoning.hypothesis_adjustments

ReasoningLayer → StrategyMemory（见 能力层与记忆模型）
  writes: learned_rule（when Retrospective.strategy_memory_update == True）
```

---

## 9. 实现约束

1. 推理层的每个组件都必须有独立的单元测试
2. 所有 LLM 生成的推理输出（PreActionReasoning、MetaReasoning、Retrospective）必须通过 schema 验证，不允许裸文本存储
3. 推理层不得直接修改 `hypotheses` 状态，只能通过 HypothesisEngine 接口影响排序
4. `PreActionReasoning.failure_next_action` 必须是可枚举动作之一（不能是自由文本的"继续"）
5. 推理层的 LLM 调用必须有独立的 token 计数，不与主循环混计

### 9.1 失败容错策略

推理层每个组件的 LLM 调用都可能失败。**每个组件必须有明确的降级策略**：

| 组件 | 失败情形 | 降级行为 |
|---|---|---|
| PreActionReasoning | LLM 超时（> 8 秒） | 跳过推理，记录 `degradation_event: pre_action_skipped`，正常执行实验 |
| PreActionReasoning | JSON 解析失败 | 重试 1 次，仍失败则跳过 |
| PreActionReasoning | 缺少 Q4 字段 | 强制重新生成，2 次失败则跳过 |
| Surprise Step 2（LLM） | LLM 不可用 | 默认按弱失败处理（参见 §3.4 Step 3 表） |
| Interpretation 生成 | LLM 失败 | 不生成 Interpretation，observation 直接绑定 hypothesis（退回二层模型） |
| AdversarialLens | LLM 失败 | 不生成 MetaReasoning，按原排序进行 |
| Failure Postmortem | LLM 失败 | 仅记录最小 Retrospective（trigger + experiment_ids），不生成 root_cause |
| StopReport | 生成失败 | 输出最小 StopReport（仅 reason + 已知 flags + 提示"详细分析失败"） |

### 9.2 降级事件追踪

每次降级必须记录到 `CTFState.degradation_events`：

```python
@dataclass
class DegradationEvent:
    id: str
    component: str               # "pre_action_reasoning" / "adversarial_lens" / ...
    reason: str                  # "llm_timeout" / "json_parse_failed" / "missing_field"
    fallback_applied: str        # 实际降级行为
    timestamp: float
```

### 9.3 降级阈值

单题中累计降级事件超过以下阈值时，必须触发警报：

| 累计次数 | 触发动作 |
|---|---|
| 5 次 | 输出 warning，提示用户检查 LLM 服务状态 |
| 10 次 | 强制触发一次 AdversarialLens（不受快速路径条件限制） |
| 15 次 | 退出主循环，输出 StopReport.reason = `excessive_degradation` |

### 9.4 容错原则

1. **推理层降级不阻塞主循环**：推理失败时主循环必须继续
2. **降级不应连环触发**：单次降级不应导致其他组件也失败
3. **降级必须可见**：所有降级事件出现在 StopReport 中
4. **测试覆盖**：每个降级路径必须有对应的测试用例（见 完整测试用例集 R 系列 + P 系列）

---

## 10. 推理层开发顺序

推理层内部按以下顺序实现，不允许倒置：

1. **PreActionReasoning**（最高优先，最直接提升行为可审计性）
2. **Interpretation 层**（解耦 observation 和 hypothesis）
3. **Failure Postmortem**（需要 Interpretation 层作为基础）
4. **AdversarialLens**（需要 Postmortem 提供历史失败模式）
5. **StopReport**（需要所有前置组件的输出）

---

## 11. 验收标准

本文档对应的实现，验收时必须满足：

1. 任意实验执行记录，都能在 `CTFState.pre_action_reasonings` 里找到对应的 Q1-Q4
2. 任意假设被 exhausted，都能在 `CTFState.retrospectives` 里找到对应的 `failure_root_cause`
3. 任意停止事件，都能生成包含 `user_next_steps` 的 `StopReport`
4. `MetaReasoning` 生成后，对应假设的排序分数在下一轮 HypothesisEngine 中有变化
5. `Interpretation` 被撤销后，对应假设的 `confidence` 下降

---

**下一步文档**：`CTF_Agent_能力层与记忆模型_V1.md`（工具能力建模与跨题学习）
