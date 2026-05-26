# CTF Agent 性能与预算规范 V1

> **本文档上游**：`CTF_Agent_智能推理层规范_V1.md`、`CTF_Agent_能力层与记忆模型_V1.md`  
> **本文档下游**：`CTF_Agent_完整测试用例集_V1.md`（性能用例 P 系列）  
> **目标**：防止推理层和记忆层引入后，单题成本爆炸或主循环卡死

---

## 1. 为什么需要预算规范

加入推理层（5 个组件）后，单次实验的 LLM 调用次数从 ~2 涨到 ~7：

```
原架构：generate_hypothesis(1) + verify(1) = 2 次
新架构：generate_hypothesis(1) + pre_action_reasoning(1) + execute(1) +
        verify(1) + surprise_judge?(0-1) + meta_reasoning?(0-1) +
        postmortem?(0-1) = 4-7 次
```

如果不加约束，一道复杂题可能烧掉数十万 token、跑几十分钟。这不能用。

---

## 2. 模型分层使用

不同推理组件对模型质量的需求不同，必须**按需选择**：

| 组件 | 推荐模型层 | 理由 |
|---|---|---|
| HypothesisEngine（规则层） | 不调用 LLM | 纯规则 |
| HypothesisEngine（LLM 兜底） | 主模型 | 假设质量直接影响后续路径 |
| PreActionReasoning Q1-Q4 | **轻量模型**（Haiku / Mimo / 类似） | 结构化推理，不需要顶级智力 |
| Surprise Step 2 判定 | **轻量模型** | 三分类问题 |
| AdversarialLens | 主模型 | 需要 deep reasoning 识别 rabbit hole |
| Failure Postmortem | 主模型 | 需要综合长上下文 |
| Verifier 路径判定 | 不调用 LLM | 规则匹配 |
| StopReport 生成 | 轻量模型 | 模板化输出 |

### 模型路由配置

通过 `.env` 或配置文件指定：

```
CTF_MODEL_PRIMARY=claude-sonnet-4-5
CTF_MODEL_LIGHTWEIGHT=claude-haiku-4
CTF_MODEL_EMBED=sentence-transformer-mini
```

如果 `CTF_MODEL_LIGHTWEIGHT` 未配置，自动回退到 `CTF_MODEL_PRIMARY`，但会输出 warning。

---

## 3. 快速路径（Fast-Path Bypass）

并非所有实验都需要完整推理。以下条件触发"快速路径"，跳过部分推理组件：

### 跳过 PreActionReasoning

触发条件（全部满足）：
- 当前最强假设 `confidence > 0.92`
- 该假设的连续 2 个 Experiment 均为 `progress_delta == "strong"`
- 当前 Experiment 是该假设的"延续步骤"（不是新方向）

行为：本次实验不生成 PreActionReasoning，但**仍执行 Step 1 结构化预期校验**（用上一次的 Q3/Q4 模板复用）。

### 跳过 AdversarialLens

触发条件（任一）：
- 当前题目累计 Surprise 次数 < 3
- 当前最强假设 confidence ≥ 0.7
- 距上次 AdversarialLens 调用 < 5 个 Experiment

### 跳过 Failure Postmortem

触发条件（任一）：
- 失败的假设 confidence 一直 < 0.3（本身就是低置信探索）
- 失败的假设关联的 Experiment ≤ 1

跳过时仍记录最小 Retrospective（只有 trigger + experiment_ids），不调用 LLM。

### 跳过 Interpretation 层

触发条件：
- 当前 observation 直接映射到某个已存在的 Interpretation 模板
- 模板匹配置信度 > 0.85

---

## 4. 单题硬上限

以下上限是**硬约束**，达到任一上限立刻触发 StopReport：

| 指标 | 默认上限 | 配置项 | 触发后 StopReport.reason |
|---|---|---|---|
| 单题总 token | 200,000 | `CTF_BUDGET_TOTAL_TOKENS` | `budget_exhausted_tokens` |
| 单题总耗时 | 1800 秒（30 分钟） | `CTF_BUDGET_TOTAL_SECONDS` | `budget_exhausted_time` |
| 单题总迭代轮次 | 50 | `CTF_BUDGET_MAX_ITERATIONS` | `max_iterations_reached` |
| 单 Experiment 时长 | 60 秒 | `CTF_BUDGET_EXPERIMENT_SECONDS` | 单实验超时，标记 progress_delta=none |
| 单 LLM 调用 max_tokens | 4096 | `CTF_BUDGET_LLM_MAX_TOKENS` | 调用失败，进入容错降级 |

### 警戒线（soft limit）

达到 80% 上限时，agent 必须：

1. 在主循环开始下一轮前输出警戒提示
2. 触发 AdversarialLens（不论快速路径条件）→ 检查是否在 rabbit hole 上
3. 暂停所有"探索性"实验（progress_delta 期待为 weak 的实验），优先 confidence > 0.7 的假设

---

## 5. 推理层延迟预算

| 组件 | 期望延迟 | 上限延迟 | 超时行为 |
|---|---|---|---|
| PreActionReasoning | ≤ 3 秒 | 8 秒 | 跳过本次推理，记录 degradation |
| Surprise Step 2 | ≤ 2 秒 | 5 秒 | 默认按弱失败处理 |
| AdversarialLens | ≤ 5 秒 | 12 秒 | 跳过，不调整排序 |
| Failure Postmortem | ≤ 5 秒 | 15 秒 | 仅生成最小 Retrospective |
| Verifier 路径 A-E | ≤ 0.1 秒 | 1 秒 | 失败则该路径判定不可用 |
| HypothesisEngine 排序 | ≤ 1 秒 | 5 秒 | 跳过 memory_bonus，仅用规则层 |
| StrategyMemory 检索 | ≤ 2 秒 | 5 秒 | 跳过记忆，用空 bonus |

---

## 6. Token 统计与归类

所有 LLM 调用必须打 tag：

```python
@dataclass
class LLMCallRecord:
    component: str           # "pre_action" / "verify" / "adversarial" / ...
    model: str               # 实际使用的模型
    prompt_tokens: int
    completion_tokens: int
    duration_ms: int
    success: bool
    fallback_triggered: bool  # 是否走了降级路径
    challenge_id: str        # 哪道题
```

每道题结束时，必须输出 token 使用报告：

```
[Token 使用报告]
总 token: 156,432 / 200,000 (78%)

按组件分布：
  hypothesis_generation:  42,103  (27%)
  pre_action_reasoning:   38,201  (24%)
  verify:                 12,304  (8%)
  adversarial_lens:        8,910  (6%)
  postmortem:             15,221  (10%)
  surprise_judge:          5,103  (3%)
  其他:                   34,590  (22%)

按模型分布：
  claude-sonnet-4-5:      89,103
  claude-haiku-4:         67,329
```

报告必须写入 `loot/<challenge>/token_report.json`，便于事后审计和优化。

---

## 7. 性能测试用例（P 系列，扩展 完整测试用例集）

### P1 — 单题 token 不超上限

**Given**：标准 SQLi 题目，配置默认上限

**Then**：从开始到结束，total_tokens ≤ 200,000

### P2 — 快速路径在高置信场景被触发

**Given**：confidence 持续 > 0.92 的假设

**Then**：连续 3 个 Experiment 没有触发 PreActionReasoning LLM 调用

### P3 — 警戒线触发 AdversarialLens

**Given**：token 用量达到 160,000（80%）

**Then**：下一轮主循环开始前，AdversarialLens 被强制触发一次

### P4 — 推理层超时不阻塞主循环

**Given**：PreActionReasoning 的 LLM 调用挂起 10 秒

**Then**：
1. 8 秒后超时
2. 记录 `degradation_event: pre_action_skipped`
3. 实验照常执行

### P5 — 轻量模型 fallback

**Given**：`CTF_MODEL_LIGHTWEIGHT` 不可用

**Then**：
1. PreActionReasoning 自动回退到 `CTF_MODEL_PRIMARY`
2. 输出 warning 日志
3. 不报错退出

### P6 — token 报告完整性

**Given**：任意题目结束

**Then**：`loot/<challenge>/token_report.json` 存在且包含全部 7 个组件类的统计

---

## 8. 性能不达标时的处理流程

如果连续 3 道题出现以下任一情况，必须召开"性能复盘"：

- 单题平均 token 超过 150,000（即超过默认上限的 75%）
- 单题平均耗时超过 1500 秒
- 推理层降级事件平均超过 5 次

复盘必须输出：

1. token 分布热点（哪个组件烧得最多）
2. 是否要调整快速路径条件
3. 是否要把更多组件切到轻量模型
4. 是否要调整硬上限

复盘记录写入 `docs/dev/CTF_Agent_性能复盘记录.md`（按需新建）。

---

## 9. 验收标准

1. P1-P6 全部通过
2. 任意题目结束都有 token 报告
3. 推理层任意组件超时不阻塞主循环
4. 快速路径在合适条件下被触发，可在 token 报告中验证

---

**下一步文档**：`CTF_Agent_用户操作手册_V1.md`（用户视角的使用说明）
