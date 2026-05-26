# FlagHunter Web 可视化控制台前后端联调与验收清单 V1

- 文档版本：V1
- 编写日期：2026-05-26
- 适用项目：FlagHunter
- 用途：用于前端 Mock 版切换真实后端后的联调推进、问题收口与验收

---

# 1. 文档目标

本文档用于回答三个问题：

1. 当前前端从 Mock 切到真实后端时，按什么顺序联调最稳
2. 每一类接口联调时应该检查什么
3. 什么时候算“这一阶段可以收口”

本文档不负责定义产品方案，而是负责：
- 联调顺序
- 对接检查项
- 回归检查项
- 问题记录方式
- 阶段收口标准

---

# 2. 联调总体原则

1. 先只读，后可写
2. 先查询页，后实时页
3. 先低耦合页，后高耦合页
4. 先接口字段对齐，后页面细节打磨
5. 出现问题优先修 adapter/schema，不优先改页面结构
6. 每完成一类接口，就做一次最小回归

---

# 3. 推荐联调顺序

建议严格按下面顺序联调：

1. Dashboard
2. Logs
3. Task List
4. Task Detail
5. Trace Detail
6. Knowledge
7. Settings（只读）
8. Events Stream
9. Task Actions（创建 / stop / retry / hint）
10. Settings（可写）

原因：
- Dashboard / Logs 最容易先接真数据
- Task / Trace 是核心但结构更复杂
- 事件流和动作接口最容易影响主链，放后面更稳

---

# 4. 联调阶段拆分

## Stage I：基础只读数据联调
目标：让大部分页面先“看得见真数据”。

包含：
- Dashboard
- Logs
- Task List
- Knowledge List
- Settings Read

## Stage II：核心详情页联调
目标：让任务详情与 trace 详情有真实内容。

包含：
- Task Detail
- Trace Detail
- Knowledge Detail

## Stage III：实时能力联调
目标：让运行中 agent 可以实时被观察。

包含：
- Events Stream
- Logs live mode
- Tasks side panel live updates
- Trace incremental updates

## Stage IV：动作能力联调
目标：让前端真正可控制后端 agent。

包含：
- create task
- add hint
- stop
- retry
- continue（若支持）

## Stage V：收口回归
目标：做整体回归与文档收口。

---

# 5. Stage I：基础只读数据联调清单

---

## 5.1 Dashboard 联调检查

### 接口
- `GET /api/dashboard/summary`
- `GET /api/dashboard/charts`
- `GET /api/dashboard/activity`

### 必查项
- 字段名与前端类型一致
- 数值字段类型正确
- 时间字段格式统一
- 空数据时页面不崩
- 图表数据为空时有 empty state

### 页面验收
- KPI 卡片全部有值或合理空态
- 图表正常渲染
- 最近活动不报错

### 常见问题
- 后端返回字段缺失
- 时间格式不统一
- 数字字段用字符串返回

---

## 5.2 Logs 联调检查

### 接口
- `GET /api/logs`

### 必查项
- 分页字段是否稳定
- level/source/taskId/runId 是否可过滤
- message 长文本是否安全返回
- payload 是否可选

### 页面验收
- LogsTable 能正常渲染
- 筛选器有效
- 搜索有效
- 点击详情不报错

---

## 5.3 Task List 联调检查

### 接口
- `GET /api/tasks`

### 必查项
- status 枚举是否稳定
- success/finalFlag/stopReason 可空性是否明确
- startedAt/finishedAt/durationMs 是否存在统一规则

### 页面验收
- 列表不抖动
- 筛选结果正确
- 搜索 target/title 可用

---

## 5.4 Knowledge List 联调检查

### 接口
- `GET /api/knowledge`

### 必查项
- 文档 id 唯一
- sourcePath 可展示
- chunkCount / hitCount 数值合法
- 文档为空时页面有空态

### 页面验收
- 列表可看
- 排序/筛选正常

---

## 5.5 Settings 只读联调检查

### 接口
- `GET /api/settings`

### 必查项
- 各配置分组层级稳定
- 不泄露不该展示的敏感值
- 可空字段处理合理

### 页面验收
- 表单初始值正常
- 不报 uncontrolled/undefined 错误

---

# 6. Stage II：详情页联调清单

---

## 6.1 Task Detail 联调检查

### 接口
- `GET /api/tasks/{taskId}`

### 必查项
- messages 结构稳定
- panel 数据完整
- 当前 plan / strategy / tool 缺失时有兜底
- notes / artifacts 可为空

### 页面验收
- 消息区正常渲染
- 右侧状态区不空崩
- 任务状态切换时展示正确

### 重点关注
- 当前运行任务与已完成任务的数据结构是否一致

---

## 6.2 Trace Detail 联调检查

### 接口
- `GET /api/traces/{runId}`
- `GET /api/traces/{runId}/timeline`
- `GET /api/traces/{runId}/graph`

### 必查项
- timeline 事件顺序正确
- graph 节点/边格式稳定
- steps/toolCalls/knowledgeHits/notes/artifacts/fileChanges 均可为空
- 大对象 payload 不应导致页面卡顿

### 页面验收
- TimelineTab 可用
- GraphTab 不报错
- DataTab 各表格可用

### 常见问题
- toolCalls 与 steps 无法关联
- event timestamp 缺失
- graph 数据结构不符合 React Flow 预期

---

## 6.3 Knowledge Detail 联调检查

### 接口
- `GET /api/knowledge/{docId}`
- `GET /api/knowledge/{docId}/chunks`

### 必查项
- docId 存在时一定能取到详情
- chunks 顺序稳定
- 长文本预览不导致页面溢出

### 页面验收
- Overview 正常
- Chunks 正常
- chunk 预览正常

---

# 7. Stage III：实时能力联调清单

---

## 7.1 Events Stream 联调检查

### 接口
- `GET /api/events/stream`
或
- `WS /api/events/ws`

### 必查项
- 连接建立正常
- 断线可重连
- 事件格式稳定
- 不同事件类型前端都能安全 fallback

### 页面联动检查
- Tasks 详情页能看到状态变化
- Trace 页能追加 timeline item
- Logs 页能追加日志

---

## 7.2 实时事件必测类型

至少验证以下事件真实流入前端：
- `task.started`
- `tool.called`
- `tool.finished`
- `knowledge.retrieved`
- `note.created`
- `verifier.flag.verified`
- `task.finished`

---

## 7.3 稳定性检查

### 必查项
- 长任务 1~3 分钟不断流
- 同一任务事件顺序基本合理
- 高频事件不会把页面打爆
- 前端事件去重策略有效

---

# 8. Stage IV：动作接口联调清单

---

## 8.1 Create Task 联调检查

### 接口
- `POST /api/tasks`

### 必查项
- 创建成功后返回 task_id/run_id
- 前端提交后列表更新
- 新任务详情页可进入

### 页面验收
- CreateTaskDialog 可真实发任务
- 成功/失败 toast 正常

---

## 8.2 Add Hint 联调检查

### 接口
- `POST /api/tasks/{taskId}/hint`

### 必查项
- hint 被后端接受
- 当前任务后续状态确实能反映 hint 进入上下文
- 失败时前端有错误提示

### 页面验收
- Add Hint 有明确反馈
- 至少能看到一条“hint accepted”类事件或状态变化

---

## 8.3 Stop / Retry 联调检查

### 接口
- `POST /api/tasks/{taskId}/stop`
- `POST /api/tasks/{taskId}/retry`

### 必查项
- stop 后状态变化正确
- retry 会产生新 run 或重置状态（规则必须明确）
- 页面能够正确反映 stop/retry 结果

---

## 8.4 Continue 联调检查（如支持）

### 必查项
- continue 语义必须清楚
- 如果当前不支持真实 continue，不应假装支持

---

# 9. Stage V：收口回归清单

---

## 9.1 页面级回归

### Dashboard
- [ ] 真数据加载正常
- [ ] 图表正常
- [ ] 空态正常

### Tasks
- [ ] 列表正常
- [ ] 详情正常
- [ ] 创建任务正常
- [ ] hint 正常
- [ ] stop/retry 正常

### Traces
- [ ] 列表正常
- [ ] 时间线正常
- [ ] graph 正常
- [ ] data tables 正常

### Knowledge
- [ ] 列表正常
- [ ] 详情正常
- [ ] chunks 正常

### Logs
- [ ] 查询正常
- [ ] live 正常

### Settings
- [ ] 读取正常
- [ ] 写入项（如已开放）正常

---

## 9.2 类型与合同回归
- [ ] 前端不再依赖 mock 专属字段
- [ ] 后端字段未偏离文档合同
- [ ] adapter 不存在大规模“临时兜底脏逻辑”

---

## 9.3 性能回归
- [ ] Dashboard 首屏可接受
- [ ] Task 详情切换不卡顿
- [ ] Trace 详情打开不卡死
- [ ] Logs 高频追加可接受

---

# 10. 联调问题记录模板

建议每发现一个问题，都按下面格式记录：

```text
[问题ID]
模块：Dashboard / Tasks / Trace / Knowledge / Logs / Settings / Events
接口：
现象：
预期：
根因判断：前端 / 后端 / 合同不一致 / 数据缺失 / 事件缺失
修复建议：
优先级：P0 / P1 / P2
状态：open / fixed / verified
```

---

# 11. 收口标准

满足以下条件时，可判定“前后端联调阶段基本收口”：

1. 六大主页面全部能接真数据
2. 至少一个运行中任务可以被实时观察
3. 至少一个任务能从前端真实创建并完成
4. 至少一个成功 run 能在 Trace 页面完整回放
5. 至少一个 hint 注入流程跑通
6. 无阻断级 P0 问题
7. 页面不再依赖仅供 Mock 的临时字段

---

# 12. 推荐联调顺序摘要

给执行 agent 的最短顺序：

1. Dashboard 真数据
2. Logs 真数据
3. Task List 真数据
4. Task Detail 真数据
5. Trace Detail 真数据
6. Knowledge 真数据
7. Settings 只读真数据
8. Events 真流
9. Create/Hint/Stop/Retry 真动作
10. 全量回归收口

---

# 13. 结论

前后端联调的关键不是“把接口都写完”，而是：

> 让 Mock 版前端平滑切到真后端，同时不破坏现有 FlagHunter 主链。

因此最稳的路线是：
- 先读后写
- 先静态后实时
- 先字段对齐后体验打磨
- 每完成一块就做最小回归

这样最容易收口，也最容易定位问题。
