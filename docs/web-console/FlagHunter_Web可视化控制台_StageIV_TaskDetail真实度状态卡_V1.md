# FlagHunter Web 可视化控制台 Stage IV · Task Detail 真实度状态卡 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 归属阶段：Stage IV / Milestone 3
- 结论：**已完成 Task Detail 来源可信度增强**

---

## 1. 本轮完成项

1. 后端不再在“期望 session_id 缺失文件”时误回退到旧 snapshot
2. `Task Detail` 的 `detailSource` 已补充：
   - `messagesConfidence`
   - `sessionMatchedBy`
   - `sessionExpectedId`
   - `sessionBlockedReason`
   - `metricsSessionId`
   - `taskSessionId`
   - `sessionMismatch`
3. 前端 Task Detail 顶部来源卡已能明确区分：
   - `observed session transcript`
   - `metrics-derived summary`
   - `synthetic fallback transcript`
4. 右侧 side panel 的 observed sources 也同步显示 message source / confidence / expected session

---

## 2. 本轮解决的核心问题

此前当某个 task 只有 `metrics_session_id`，但对应 session 文件缺失时，后端仍可能按 target/time 误命中旧 snapshot。

本轮修补后：

- 若存在明确期望的 session id，但文件不存在
- 后端会直接阻断 heuristic snapshot 误命中
- Task Detail 改为回落到 `metrics_observed`
- UI 明确显示：
  - `session = —`
  - `expected session = <metrics_session_id>`
  - `blocked = expected session file missing`

---

## 3. 本轮验证结论

### 3.1 metrics_observed 案例

验证任务：

- `task_260527023937_7b56`

结果：

- 现在不再错误显示 `loot/sessions/5dd13913fdf7.json`
- 已切换为：
  - `messages = metrics_observed`
  - `session = —`
  - `expected session = bb4eb7261ad3`
  - `blocked = expected session file missing`

### 3.2 session_snapshot 案例

验证任务：

- `task_260527022218_d4b1`

结果：

- 继续正确命中：
  - `messages = session_snapshot`
  - `sessionMatchedBy = explicit_session_id`
  - `confidence = high`
  - `session = loot/sessions/38b53849c4d5.json`

### 3.3 synthetic_fallback

本轮 live 数据集中未找到稳定 synthetic fallback 样本，因此未做浏览器级展示验证。  
但前端与后端路径已具备明确文案与可信度标记。

---

## 4. 当前残余边界

1. `synthetic_fallback` 本轮仅做代码路径增强，未做 live 样本验证
2. Task Detail 的消息真实性已提升，但 message 内容仍可能受 metrics 摘要粒度限制
3. Trace Detail 与 Task Detail 共用部分 session 选择逻辑，因此后续若再收敛，需要统一考虑

---

## 5. 下一步建议

Milestone 3 已可视为完成。  
建议直接进入 Stage IV / Milestone 4：

- **Knowledge usage 可视分析增强**

