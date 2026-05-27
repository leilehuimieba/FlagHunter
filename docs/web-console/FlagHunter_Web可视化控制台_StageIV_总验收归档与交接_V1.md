# FlagHunter Web 可视化控制台 Stage IV · 总验收归档与交接 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 适用阶段：Stage IV
- 当前结论：**Stage IV 4 个既定里程碑均已完成，并完成一轮 fresh verify + handoff 收口**
- 当前完成度：**100%（按 Stage IV 既定最小验收条）**
- 最新 safe rollback point：`58d6663` · `feat(web): enrich task knowledge usage view`

---

## 1. Stage IV 目标与收口范围

Stage IV 既定顺序为：

1. Settings 可写化
2. Trace Graph 真图化
3. Task Detail 会话真实度增强
4. Knowledge usage 可视分析增强

本次总验收仅覆盖上述 4 项，不扩展到新的页面重构或新能力开发。

---

## 2. 里程碑完成矩阵

| Milestone | 目标 | 状态 | 关键产物 | 对应提交 |
|---|---|---|---|---|
| M1 | Settings 可写化 | 已完成 | `/api/settings` partial live save、前端只读/可写分层 | `d6d4a3c` |
| M2 | Trace Graph 真图化 | 已完成 | Trace timeline / DAG 基于 live trace 数据而非固定 mock | `09c7c50` |
| M3 | Task Detail 会话真实度增强 | 已完成 | session / metrics / synthetic fallback 来源可信度增强 | `aae7091` |
| M4 | Knowledge usage 可视分析增强 | 已完成 | `knowledgeHits` 真实/低保真结构化、KnowledgeCard 统计化 | `58d6663` |

---

## 3. 已完成工作归档

### 3.1 Milestone 1 · Settings 可写化

已完成：

- `GET /api/settings` 返回 live 配置与 `meta.editablePaths / meta.restartRequiredPaths / meta.saveMode`
- `PUT /api/settings` 支持白名单字段落盘
- 前端只开放本轮支持字段，未支持字段保持只读
- `discard` 回到最近一次后端状态，而不是 mock

现存状态卡：

- `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageIV_Settings可写化状态卡_V1.md`
- `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageIV_Settings可写化验证证据_V1.json`

### 3.2 Milestone 2 · Trace Graph 真图化

已完成：

- Trace Detail 的 timeline / DAG 已改为消费 live trace 数据
- 真实 run 可展示 `task / plan / knowledge / tool / note / verify` 等事件类型
- Trace 页面不再依赖固定 mock graph

里程碑提交：

- `09c7c50` · `feat(web): derive trace graph from live timeline`

说明：

- 本轮未单独留下 Stage IV / Milestone 2 状态卡；总验收阶段已补 fresh verify 证据作为归档锚点

### 3.3 Milestone 3 · Task Detail 会话真实度增强

已完成：

- 明确阻断“期望 session 缺失时误命中旧 snapshot”
- `detailSource` 补充 `messagesConfidence / sessionMatchedBy / sessionExpectedId / sessionBlockedReason / metricsSessionId / taskSessionId / sessionMismatch`
- 顶部来源卡与右侧 observed sources 均能区分：
  - `observed session transcript`
  - `metrics-derived summary`
  - `synthetic fallback transcript`

现存状态卡：

- `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageIV_TaskDetail真实度状态卡_V1.md`
- `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageIV_TaskDetail真实度验证证据_V1.json`

### 3.4 Milestone 4 · Knowledge usage 可视分析增强

已完成：

- 后端 `Task Detail` 返回真实 `knowledgeHits`
- `session_snapshot / metrics_observed / unobserved` 三类知识来源已可区分
- 前端 `KnowledgeCard` 升级为：
  - `fidelity / queries / matched / no match / observed only`
  - `source × count`
  - 明细（source / result kind / query / preview / time）
- 右侧 `observed sources` 增加 knowledge 来源与可信度

现存状态卡：

- `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageIV_KnowledgeUsage可视分析状态卡_V1.md`
- `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageIV_KnowledgeUsage可视分析验证证据_V1.json`

---

## 4. Fresh Verification（本次总验收当场复验）

> 说明：以下检查均在本次归档阶段重新执行，不依赖旧截图或旧记忆。

### 4.1 Settings 可写化：通过

检查方式：

1. `GET /api/settings`
2. 将 `budget.alertAt` 从 `0.8` 临时改到 `0.81`
3. 再次 `GET /api/settings` 确认读回 `0.81`
4. 写回原值 `0.8`
5. 再次 `GET /api/settings` 确认恢复

复验结果：

- `before = 0.8`
- `mid = 0.81`
- `after = 0.8`
- 两次 `PUT` 均返回 `saved = budget.alertAt`
- `restartRequired = []`

结论：

- Stage IV / M1 的最小 live save 闭环当前仍可用，且验证后已恢复原值

### 4.2 Trace Graph 真图化：通过

检查方式：

1. `GET /api/traces`
2. `GET /api/traces/run_260527023937_5240`
3. 浏览器打开 `#/traces/run_260527023937_5240`

复验结果：

- traces list 正常返回多个真实 run
- `run_260527023937_5240` 返回：
  - `totalSteps = 6`
  - `totalToolCalls = 6`
  - `timeline.length = 8`
  - timeline 中存在真实事件类型：
    - `task.started`
    - `plan.generate_plan`
    - `knowledge.knowledge_search`
    - `tool.recon_bundle`
    - `note.notes`
    - `verifier.flag.verified`
- 浏览器 trace 页成功渲染 timeline 与 DAG 入口，无 console error / warn

结论：

- Stage IV / M2 当前仍是 live trace 驱动，而非退回 mock 图

### 4.3 Task Detail 会话真实度：通过

检查方式：

1. `GET /api/tasks/task_260527023937_7b56`（metrics_observed）
2. `GET /api/tasks/task_260527022218_d4b1`（session_snapshot）

复验结果：

- `task_260527023937_7b56`
  - `detailSource.messages = metrics_observed`
  - `session = null`
  - `sessionExpectedId = bb4eb7261ad3`
  - `sessionBlockedReason = expected_session_missing`
- `task_260527022218_d4b1`
  - `detailSource.messages = session_snapshot`
  - `sessionMatchedBy = explicit_session_id`
  - `session = loot\sessions\38b53849c4d5.json`

结论：

- Stage IV / M3 的来源可信度修补当前仍生效
- “明确期望 session 丢失时不误绑旧 snapshot”的关键问题已持续被阻断

### 4.4 Knowledge usage 可视分析：通过

检查方式：

1. `GET /api/tasks/task_260527023632_121e`（snapshot-backed）
2. `GET /api/tasks/task_260527023937_7b56`（metrics-observed）
3. `GET /api/tasks/task_260527022218_d4b1`（empty）
4. 浏览器分别 spot-check task detail 页面

复验结果：

- `task_260527023632_121e`
  - `detailSource.knowledge = session_snapshot`
  - `knowledgeHits.length = 1`
  - 命中项包含真实 `query` 与 `resultKind = no_match`
- `task_260527023937_7b56`
  - `detailSource.knowledge = metrics_observed`
  - `knowledgeHits.length = 1`
  - 命中项为低保真 `observed_only`
- `task_260527022218_d4b1`
  - `detailSource.knowledge = unobserved`
  - `knowledgeHits = []`
- 浏览器页面三类状态均正常渲染，console 无 error / warn

结论：

- Stage IV / M4 当前可稳定区分：
  - `snapshot-backed`
  - `metrics-observed`
  - `unobserved`

---

## 5. 验收结论对照最小 bar

| 里程碑 | 最小 bar | 当前结论 |
|---|---|---|
| M1 | Settings 支持字段 live 保存并可读回 | 通过 |
| M2 | Trace 图/时间线来自 live trace 数据 | 通过 |
| M3 | Task Detail 来源可信度明确，错误 snapshot fallback 被阻断 | 通过 |
| M4 | Knowledge usage 可区分真实命中 / 低保真 / 空态 | 通过 |

总体结论：

> **Stage IV 既定 4 个里程碑均已达到“当前实现 + 当前 live 数据”下的最小验收条。**

---

## 6. 未验证项 / 残余风险

### 6.1 未完全验证项

1. `synthetic_fallback` 仍无稳定 live 样本，当前只有代码路径与文案就位，未做独立页面级 live 验证
2. Milestone 2 未在当时单独沉淀专属状态卡，本次总验收以 fresh verify 补齐当前证据

### 6.2 残余风险

1. `metrics_observed` 本质上仍是低保真来源：
   - Task Detail message 内容受 metrics 粒度限制
   - Knowledge usage 无法伪造 query / chunk / doc 细节
2. Trace Detail 若缺少 snapshot，`tool I/O` 仍可能显示 `not captured`
3. Settings 仍是 partial save，不代表全量配置都支持热写回

---

## 7. 当前阻塞与非阻塞尾巴

### 当前阻塞

- 无阻塞项；Stage IV 可以视为完成并交接

### 非阻塞尾巴

1. 若后续恰好出现 `synthetic_fallback` live 样本，可补一条浏览器级验收证据
2. 若后续继续强化 Trace Detail，可考虑把 metrics-only 场景下的 tool I/O 低保真展示再前移一层

---

## 8. 最小恢复上下文（handoff）

若后续需要继续工作，最少只需要以下上下文：

### 当前目标状态

- Stage IV 已完成，不需要再继续打磨 Milestone 1~4

### 关键文件

- 执行计划：
  - `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageIV_执行计划_V1.md`
- Stage IV 里程碑状态卡：
  - `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageIV_Settings可写化状态卡_V1.md`
  - `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageIV_TaskDetail真实度状态卡_V1.md`
  - `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageIV_KnowledgeUsage可视分析状态卡_V1.md`
- 核心代码：
  - `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`
  - `D:\webstudy\FlagHunter\web\console\src\pages\tasks.jsx`

### 最新安全回滚点

- `58d6663` · `feat(web): enrich task knowledge usage view`

### 若继续推进的建议顺序

1. 先做 Stage IV 总归档提交
2. 然后再决定是否进入新的阶段目标；**不要回头拆改已验收的 Stage IV 卡片**

---

## 9. 工作区与清理状态

- 本次总验收过程中产生的临时 Web Console 日志可清理
- 当前根目录不应保留额外一次性调试脚本
- 本文档属于长期归档产物，应保留

---

## 10. 最终交接结论

从 verify + handoff 角度看：

- Stage IV 4 个既定里程碑 **已完成**
- 当前实现具备可复验的 live 证据
- 剩余项均为**非阻塞优化**，不影响本轮交接

因此可以将 Stage IV 标记为：

> **已总验收通过，可归档，可作为后续阶段的稳定交接基线。**
