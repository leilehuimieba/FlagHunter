# FlagHunter Web 可视化控制台 Stage III 首轮状态卡 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 适用项目：FlagHunter
- 目标阶段：Stage III（实时能力联调）
- 当前结论：**已完成 Stage III 首轮切入：任务详情 live 事件流与 Trace 增量时间线已接通，具备继续做真流验收的基础**

---

## 1. 本轮范围

本轮没有进入动作接口，也不回头修改 Stage I / Stage II 已收口页面，只做 Stage III 的最小首刀：

1. 后端 SSE 事件补齐运行时关联字段
2. `Task Detail` 接前端 live 事件并即时反映
3. `Trace Detail` 接前端 live 事件并追加 timeline
4. 保持 `Dashboard / Logs` 现有实时链路不回退

---

## 2. 本轮结论

当前结论：

> **Stage III 已完成第一刀“页面级实时联动”接线。**

更具体地说：

1. 后端发出的 `task_status` / `tool_call` / `task_created` / `hint` 事件现在带有更完整的 `run_id` 与时间字段
2. `Task Detail` 已不再只是静态详情页，能对 live 事件作出即时 UI 反馈
3. `Trace Detail` 已能基于 live 事件追加新的 timeline item，并更新头部指标
4. 浏览器实测中，注入 live 事件后两页都能在不报错的情况下立即渲染增量变化

因此当前阶段判断应为：

> **Stage III 首轮启动成功，下一步可以直接做“真实运行任务”的真流验收。**

---

## 3. 本轮完成项

### 3.1 后端

已修改文件：

- `D:/webstudy/FlagHunter/pentestagent/interface/web_server.py`

本轮完成：

1. 丰富 SSE 事件元信息
   - `task_status` 现在补带：
     - `run_id`
     - `t`
   - `tool_call` 现在补带：
     - `run_id`
     - `kind = tool.called`
     - `t`
   - `task_created` / `hint` 也补了运行关联字段

2. 增加标准化任务别名事件
   - 启动时会额外发：
     - `task.started`
   - 结束时会额外发：
     - `task.success` / `task.stopped` / `task.failed`

这些事件当前主要用于 Stage III 后续真流联调与更细粒度前端消费，不影响已有 Stage II 接口合同。

### 3.2 前端

已修改文件：

- `D:/webstudy/FlagHunter/web/console/src/pages/tasks.jsx`
- `D:/webstudy/FlagHunter/web/console/src/pages/traces.jsx`

本轮完成：

#### Task Detail live 化

1. 对当前 task 的 `fh:event` 已建立订阅
2. `tool_call` 到达时：
   - 会即时追加一条 live message
   - 会把摘要写入 observed feed
3. `task_status` 到达时：
   - 会即时更新 `tokensUsed` / `toolCalls` / `status`
   - 终态会追加 finish message
4. 右侧 live side panel 已补 observed feed 空态与实时观测条目

#### Trace Detail 增量化

1. 对当前 run / task 的 `fh:event` 已建立订阅
2. `tool_call` 到达时：
   - 会即时追加 timeline tool event
3. `task_status` 到达时：
   - 会更新头部 steps / toolCalls / tokens
   - 终态会追加 finish event
4. Trace 列表页也会在 `task_created / task_status` 后刷新数据源

---

## 4. 浏览器级验证结果

### 4.1 验证方式

本轮验证采用：

1. 启动 live `web_server.py`
2. 用真实浏览器打开页面
3. 在页面内主动派发 `fh:event` 事件模拟实时流入
4. 观察页面是否即时增量更新、是否出现 console/page error

说明：

> 这验证的是 **Stage III 前端实时接线是否成立**。它不是“一条真实运行中的 agent 从后端 SSE 自然流到页面”的最终验收；那是下一步要补的真流验收。

### 4.2 Task Detail

验证路由：

- `http://127.0.0.1:8087/#/tasks/task_260526145338_0466`

注入事件：

1. `tool_call`
2. `task_status`（带 `tokensUsed=321`、`toolCalls=5`）

验证结果：

- `before_messages = 6`
- `after_messages = 7`
- `live_tool_msg_present = true`
- `obs_present = true`
- `tool_calls_updated = true`
- `errors = []`

结论：

> **Task Detail live 事件已能即时推动消息区与右侧 observed feed 更新。**

### 4.3 Trace Detail

验证路由：

- `http://127.0.0.1:8087/#/traces/run_260526145338_10b6`

注入事件：

1. `tool_call`
2. `task_status`（带 `status=stopped`、`toolCalls=9`、`tokensUsed=777`）

验证结果：

- `before_events = 6`
- `after_events = 8`
- `live_tool_event_present = true`
- `finish_event_present = true`
- 头部指标已更新到：
  - `steps = 9`
  - `toolCalls = 9`
  - `tokens = 777`
- `errors = []`

结论：

> **Trace Detail 已能按 live 事件追加 timeline，并即时刷新头部指标。**

---

## 5. 本轮证据

本轮新增证据文件：

- `D:/webstudy/FlagHunter/docs/web-console/FlagHunter_Web可视化控制台_StageIII_首轮验证证据_V1.json`

本轮关键代码落点：

- `D:/webstudy/FlagHunter/pentestagent/interface/web_server.py`
- `D:/webstudy/FlagHunter/web/console/src/pages/tasks.jsx`
- `D:/webstudy/FlagHunter/web/console/src/pages/traces.jsx`

本轮基础校验：

- `D:/webstudy/FlagHunter/.venv/Scripts/python.exe -m py_compile D:/webstudy/FlagHunter/pentestagent/interface/web_server.py D:/webstudy/FlagHunter/pentestagent/agents/base_agent.py`
- live `http://127.0.0.1:8087/api/status` 可返回正常 JSON

---

## 6. 当前剩余项

本轮完成后，Stage III 还剩三类明确缺口：

1. **真流验收未做完**
   - 还需要至少一条真实 running task，验证后端 SSE 自然推送到页面，而不是浏览器内事件注入

2. **事件种类仍不够细**
   - `tool.finished`
   - `knowledge.retrieved`
   - `note.created`
   这些事件还没有稳定的结构化真流

3. **Logs live 关联还可增强**
   - 当前 `log_line` 仍偏通用，`run_id` / `task_id` 关联度还可以继续提高

判断：

> 这些都属于 **Stage III 首轮之后的自然下一步**，不否定本轮“页面级实时联动已接通”的结论。

---

## 7. 下一步建议

建议保持 Stage III 顺序，不切去动作接口：

1. **先做 Stage III 第二轮真流验收**
   - 启动一个真实 running task
   - 观察 `Task Detail / Trace Detail / Logs` 三页自然接流表现

2. 真流验收通过后，再决定是否补：
   - `knowledge.retrieved`
   - `note.created`
   - `tool.finished`
   这三类结构化事件

不建议现在就跳到 Stage IV 动作接口，因为实时链路还没有拿到完整真流证据。

---

## 8. 一句话状态

> **FlagHunter Web Console 已正式进入 Stage III，并完成首轮页面级实时联动：Task Detail live feed 与 Trace incremental timeline 已接通，下一步应直接做真实运行任务的真流验收。**
