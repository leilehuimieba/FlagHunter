# FlagHunter Web 可视化控制台信息架构与 API/事件草案 V1

- 文档版本：V1
- 编写日期：2026-05-26
- 适用项目：FlagHunter
- 目标：为前端 Mock 开发与后端后续适配提供统一合同

---

# 1. 文档目的

本文档用于定义：
- 页面信息架构
- 前端路由结构
- 页面数据需求
- API 设计草案
- 实时事件模型草案
- Mock 数据组织规范

本文档的核心原则：

> 前端先基于接口合同和 Mock 数据完成，不直接绑定当前后端内部文件结构。

---

# 2. 前端路由建议

建议采用 Next.js App Router，路由结构如下：

```text
/app
  /(console)
    /dashboard
    /tasks
    /tasks/[taskId]
    /traces
    /traces/[runId]
    /knowledge
    /knowledge/[docId]
    /logs
    /settings
```

可选扩展：

```text
    /artifacts
    /memory
    /runtime
```

---

# 3. 页面信息架构

## 3.1 Dashboard

### 数据块
- KPI cards
- 最近任务
- 最近工具调用
- token/cost 趋势
- 失败分布
- runtime 状态

### 所需数据接口
- `GET /api/dashboard/summary`
- `GET /api/dashboard/activity`
- `GET /api/dashboard/charts`

---

## 3.2 Tasks

### 页面分层
- 任务列表页
- 任务详情页

### 列表页展示
- task_id
- title
- target
- status
- detected_type
- started_at
- duration
- success

### 详情页展示
- 对话消息
- 当前运行状态
- 当前计划
- 当前工具调用
- observations
- notes
- artifacts
- actions：retry / stop / continue / add-hint

### 所需接口
- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/tasks/{taskId}`
- `POST /api/tasks/{taskId}/stop`
- `POST /api/tasks/{taskId}/retry`
- `POST /api/tasks/{taskId}/hint`

---

## 3.3 Traces

### 列表页展示
- run_id
- task_id
- target
- status
- started_at
- finished_at
- total_steps
- total_tool_calls
- total_tokens

### 详情页展示
- timeline
- graph
- steps
- tool calls
- knowledge hits
- file changes
- notes written
- verifier states

### 所需接口
- `GET /api/traces`
- `GET /api/traces/{runId}`
- `GET /api/traces/{runId}/timeline`
- `GET /api/traces/{runId}/graph`

---

## 3.4 Knowledge

### 列表页展示
- doc_id
- title
- source_path
- type
- chunk_count
- updated_at
- last_hit_at
- hit_count

### 详情页展示
- 文档 metadata
- chunk 列表
- 最近被哪些 run 使用
- 相关策略/任务引用

### 所需接口
- `GET /api/knowledge`
- `GET /api/knowledge/{docId}`
- `GET /api/knowledge/{docId}/chunks`
- `GET /api/knowledge/hits`

---

## 3.5 Logs

### 展示内容
- time
- level
- source
- task_id
- run_id
- message
- payload preview

### 所需接口
- `GET /api/logs`
- `GET /api/logs/stream`

---

## 3.6 Settings

### 展示分组
- Model
- Runtime
- MCP
- Knowledge
- Budget
- Audit

### 所需接口
- `GET /api/settings`
- `PUT /api/settings`
- `POST /api/settings/test-runtime`

---

# 4. 统一数据实体草案

---

## 4.1 Task

```ts
export interface TaskRecord {
  id: string
  title: string
  target: string
  goal: string
  status: 'queued' | 'running' | 'success' | 'failed' | 'stopped'
  detectedType?: string
  currentRunId?: string
  startedAt?: string
  finishedAt?: string
  durationMs?: number
  success?: boolean
  finalFlag?: string | null
  stopReason?: string | null
}
```

---

## 4.2 Run

```ts
export interface RunRecord {
  id: string
  taskId: string
  target: string
  status: 'running' | 'success' | 'failed' | 'stopped'
  startedAt: string
  finishedAt?: string
  durationMs?: number
  totalSteps: number
  totalToolCalls: number
  totalTokens?: number
  inputTokens?: number
  outputTokens?: number
  finalFlag?: string | null
}
```

---

## 4.3 Step

```ts
export interface RunStepRecord {
  id: string
  runId: string
  kind:
    | 'recon'
    | 'plan'
    | 'hypothesis'
    | 'strategy'
    | 'tool_call'
    | 'knowledge'
    | 'note'
    | 'artifact'
    | 'verification'
    | 'recovery'
    | 'system'
  title: string
  status: 'pending' | 'running' | 'success' | 'failed' | 'skipped'
  startedAt?: string
  finishedAt?: string
  durationMs?: number
  summary?: string
  payload?: Record<string, unknown>
}
```

---

## 4.4 ToolCall

```ts
export interface ToolCallRecord {
  id: string
  runId: string
  stepId?: string
  toolName: string
  status: 'running' | 'success' | 'failed'
  startedAt: string
  finishedAt?: string
  durationMs?: number
  inputSummary?: string
  outputSummary?: string
  errorMessage?: string
  createdArtifacts?: string[]
  createdNotes?: string[]
}
```

---

## 4.5 KnowledgeHit

```ts
export interface KnowledgeHitRecord {
  id: string
  runId: string
  source: 'rag' | 'strategy_memory' | 'notes' | 'external_hint'
  docId?: string
  chunkId?: string
  title?: string
  score?: number
  excerpt?: string
  usedByStepId?: string
}
```

---

## 4.6 NoteEntry

```ts
export interface NoteRecord {
  id: string
  runId?: string
  key: string
  category: string
  valuePreview: string
  target?: string
  url?: string
  createdAt: string
}
```

---

## 4.7 ArtifactEntry

```ts
export interface ArtifactRecord {
  id: string
  runId?: string
  name: string
  kind: 'file' | 'screenshot' | 'report' | 'memory' | 'other'
  path?: string
  url?: string
  createdAt: string
  summary?: string
}
```

---

## 4.8 FileChange

```ts
export interface FileChangeRecord {
  id: string
  runId: string
  path: string
  action: 'created' | 'updated' | 'deleted'
  summary?: string
  beforePreview?: string
  afterPreview?: string
  createdAt: string
}
```

---

## 4.9 LogEntry

```ts
export interface LogRecord {
  id: string
  timestamp: string
  level: 'debug' | 'info' | 'warning' | 'error'
  source: string
  taskId?: string
  runId?: string
  message: string
  payload?: Record<string, unknown>
}
```

---

# 5. Dashboard API 草案

## 5.1 `GET /api/dashboard/summary`

### 返回示例
```json
{
  "runningTasks": 2,
  "tasksToday": 14,
  "successToday": 9,
  "failedToday": 3,
  "stoppedToday": 2,
  "dailyTokens": 123456,
  "estimatedCost": 8.42,
  "activeRuntime": "LocalRuntime",
  "knowledgeHitsToday": 37,
  "toolCallsToday": 186
}
```

## 5.2 `GET /api/dashboard/charts`

### 返回示例
```json
{
  "tokenSeries": [
    { "time": "10:00", "value": 1200 },
    { "time": "11:00", "value": 4800 }
  ],
  "toolDistribution": [
    { "name": "terminal", "value": 42 },
    { "name": "http_request", "value": 18 }
  ],
  "failureDistribution": [
    { "name": "missing_tool", "value": 3 },
    { "name": "no_progress", "value": 4 }
  ]
}
```

## 5.3 `GET /api/dashboard/activity`

### 返回示例
```json
{
  "items": [
    {
      "id": "act_001",
      "time": "2026-05-26T10:00:00+08:00",
      "type": "tool.finished",
      "title": "artifact_forensics completed",
      "summary": "Recovered flag from app.db-wal"
    }
  ]
}
```

---

# 6. Tasks API 草案

## 6.1 `GET /api/tasks`

### 查询参数
- `status`
- `page`
- `pageSize`
- `keyword`

### 返回示例
```json
{
  "items": [
    {
      "id": "task_001",
      "title": "wal_recover blind run",
      "target": "http://127.0.0.1:8765/.../wal_recover/",
      "goal": "拿到flag",
      "status": "success",
      "detectedType": "misc",
      "currentRunId": "run_001",
      "startedAt": "2026-05-26T10:00:00+08:00",
      "finishedAt": "2026-05-26T10:00:12+08:00",
      "durationMs": 11280,
      "success": true,
      "finalFlag": "flag{...}",
      "stopReason": null
    }
  ],
  "total": 1
}
```

## 6.2 `POST /api/tasks`

### 请求示例
```json
{
  "title": "blind ctf run",
  "target": "http://127.0.0.1:8765/...",
  "goal": "拿到flag",
  "type": "auto",
  "hint": "开启ctf模式，自己判断题型并拿flag。"
}
```

## 6.3 `GET /api/tasks/{taskId}`

### 返回示例
```json
{
  "task": { "id": "task_001", "title": "wal_recover blind run", "status": "running" },
  "messages": [
    { "id": "msg_1", "role": "user", "content": "开启ctf模式...", "createdAt": "2026-05-26T10:00:00+08:00" },
    { "id": "msg_2", "role": "assistant", "content": "正在侦察目标...", "createdAt": "2026-05-26T10:00:01+08:00" }
  ],
  "panel": {
    "currentPlan": ["recon", "misc artifact forensics"],
    "currentStrategy": "artifact_forensics",
    "currentTool": "terminal",
    "detectedType": "misc",
    "lastObservation": "directory listing discovered"
  }
}
```

## 6.4 `POST /api/tasks/{taskId}/hint`

### 请求示例
```json
{
  "content": "注意 sqlite wal 残留"
}
```

### 返回示例
```json
{
  "accepted": true
}
```

---

# 7. Trace API 草案

## 7.1 `GET /api/traces`

### 返回示例
```json
{
  "items": [
    {
      "id": "run_001",
      "taskId": "task_001",
      "target": "http://127.0.0.1:8765/...",
      "status": "success",
      "startedAt": "2026-05-26T10:00:00+08:00",
      "finishedAt": "2026-05-26T10:00:12+08:00",
      "durationMs": 11280,
      "totalSteps": 6,
      "totalToolCalls": 3,
      "totalTokens": 8400,
      "finalFlag": "flag{...}"
    }
  ],
  "total": 1
}
```

## 7.2 `GET /api/traces/{runId}`

### 返回示例
```json
{
  "run": {
    "id": "run_001",
    "taskId": "task_001",
    "status": "success",
    "target": "http://127.0.0.1:8765/..."
  },
  "steps": [],
  "toolCalls": [],
  "knowledgeHits": [],
  "notes": [],
  "artifacts": [],
  "fileChanges": []
}
```

## 7.3 `GET /api/traces/{runId}/timeline`

### 返回示例
```json
{
  "items": [
    {
      "id": "evt_001",
      "timestamp": "2026-05-26T10:00:01+08:00",
      "type": "agent.strategy.selected",
      "title": "Selected artifact_forensics",
      "summary": "misc chain matched attachment surface"
    }
  ]
}
```

## 7.4 `GET /api/traces/{runId}/graph`

### 返回示例
```json
{
  "nodes": [
    { "id": "n1", "type": "run", "data": { "label": "run_001" }, "position": { "x": 0, "y": 0 } },
    { "id": "n2", "type": "strategy", "data": { "label": "artifact_forensics" }, "position": { "x": 300, "y": 0 } }
  ],
  "edges": [
    { "id": "e1", "source": "n1", "target": "n2" }
  ]
}
```

---

# 8. Knowledge API 草案

## 8.1 `GET /api/knowledge`

### 返回示例
```json
{
  "items": [
    {
      "id": "doc_001",
      "title": "SQLite WAL recovery notes",
      "sourcePath": "knowledge/forensics/sqlite_wal.md",
      "type": "md",
      "chunkCount": 12,
      "updatedAt": "2026-05-24T10:00:00+08:00",
      "lastHitAt": "2026-05-26T10:00:03+08:00",
      "hitCount": 4
    }
  ]
}
```

## 8.2 `GET /api/knowledge/{docId}`

### 返回示例
```json
{
  "id": "doc_001",
  "title": "SQLite WAL recovery notes",
  "sourcePath": "knowledge/forensics/sqlite_wal.md",
  "type": "md",
  "chunkCount": 12,
  "updatedAt": "2026-05-24T10:00:00+08:00",
  "summary": "Common SQLite WAL recovery workflow",
  "tags": ["forensics", "sqlite", "wal"]
}
```

## 8.3 `GET /api/knowledge/{docId}/chunks`

### 返回示例
```json
{
  "items": [
    {
      "id": "chunk_001",
      "docId": "doc_001",
      "index": 0,
      "text": "SQLite WAL stores historical frames...",
      "hitCount": 2
    }
  ]
}
```

---

# 9. Logs API 草案

## 9.1 `GET /api/logs`

### 查询参数
- `level`
- `source`
- `taskId`
- `runId`
- `page`
- `pageSize`
- `keyword`

### 返回示例
```json
{
  "items": [
    {
      "id": "log_001",
      "timestamp": "2026-05-26T10:00:02+08:00",
      "level": "info",
      "source": "ctf_dispatcher",
      "taskId": "task_001",
      "runId": "run_001",
      "message": "detected_type=misc"
    }
  ],
  "total": 1
}
```

## 9.2 `GET /api/logs/stream`

- 首期前端可先用 Mock WebSocket/SSE
- 后端接入时再真实替换

---

# 10. Settings API 草案

## 10.1 `GET /api/settings`

### 返回示例
```json
{
  "model": {
    "provider": "openai",
    "name": "gpt-5.4",
    "temperature": 0.2,
    "maxTokens": 128000
  },
  "runtime": {
    "mode": "local",
    "autoSsh": false,
    "dockerEnabled": false,
    "sshConfigured": true
  },
  "knowledge": {
    "enabled": true,
    "chunkSize": 1000,
    "overlap": 200,
    "threshold": 0.35
  },
  "budget": {
    "dailyTokenLimit": 500000,
    "dailyCostLimit": 50
  }
}
```

## 10.2 `PUT /api/settings`

### 请求示例
```json
{
  "runtime": {
    "autoSsh": true
  }
}
```

### 首期建议
前端先只做：
- 读取 Mock
- 表单编辑
- 模拟保存成功

---

# 11. 实时事件模型草案

---

## 11.1 统一事件格式

```ts
export interface AgentEvent {
  id: string
  runId?: string
  taskId?: string
  timestamp: string
  type: string
  level?: 'debug' | 'info' | 'warning' | 'error'
  source: string
  title: string
  summary?: string
  payload?: Record<string, unknown>
}
```

---

## 11.2 建议事件类型

### 任务级
- `task.started`
- `task.updated`
- `task.finished`
- `task.stopped`

### 推理级
- `agent.plan.created`
- `agent.plan.updated`
- `agent.hypothesis.generated`
- `agent.strategy.selected`
- `agent.recovery.decided`

### 工具级
- `tool.called`
- `tool.finished`
- `tool.failed`

### 运行时级
- `runtime.command.started`
- `runtime.command.finished`
- `runtime.browser.started`
- `runtime.browser.finished`

### 知识级
- `knowledge.retrieved`
- `knowledge.index.updated`
- `memory.strategy.saved`
- `memory.strategy.updated`

### 产物级
- `note.created`
- `artifact.created`
- `file.created`
- `file.updated`
- `file.deleted`

### 验证级
- `verifier.flag.candidate`
- `verifier.flag.runtime`
- `verifier.flag.verified`
- `verifier.flag.rejected`

---

# 12. Mock 数据开发规范

## 12.1 原则
- Mock 数据结构必须严格对齐 TypeScript 接口
- 不允许页面直接依赖随意拼接 JSON
- Mock service 与 real service API 保持同签名

## 12.2 建议目录

```text
src/
  lib/
    api/
      client.ts
      types.ts
      mock/
        dashboard.mock.ts
        tasks.mock.ts
        traces.mock.ts
        knowledge.mock.ts
        logs.mock.ts
        settings.mock.ts
      services/
        dashboard.service.ts
        tasks.service.ts
        traces.service.ts
        knowledge.service.ts
        logs.service.ts
        settings.service.ts
```

## 12.3 Adapter 模式建议

前端 service 不直接知道数据来自哪里，只知道调用：
- mock adapter
- future real adapter

例如：
- `dashboardService.getSummary()`
- 当前内部走 `mockDashboardAdapter`
- 后续替换为 `httpDashboardAdapter`

---

# 13. 前端实现约束

## 13.1 必须做到
- 所有数据类型显式定义
- 所有页面具备 loading / empty / error state
- 所有列表支持分页/筛选预留
- 所有详情页可深链接打开
- 所有时间字段统一格式化

## 13.2 不建议做法
- 不要把 API 调用散落到组件内部
- 不要直接在页面里写大量 mock object
- 不要让页面依赖当前后端内部 notes 文件结构
- 不要先做花哨动画再补数据结构

---

# 14. 与当前项目能力的映射建议

当前项目已有可复用信息源：
- notifier
- token_tracker
- strategy_memory
- notes
- retrospective
- ctf_state observations
- runtime outputs

后续后端接入时建议优先映射：

## 第一优先级
- token_tracker -> Dashboard
- logs -> Logs
- tasks/runs -> Tasks / Trace

## 第二优先级
- observations / tool calls -> Trace
- notes / artifacts -> Trace / Tasks

## 第三优先级
- knowledge / strategy_memory -> Knowledge
- config -> Settings

---

# 15. 分阶段接入建议

## Stage 1：纯 Mock
- 所有页面能跑
- 所有页面交互完整
- 可演示产品形态

## Stage 2：半真实接入
- Dashboard 真数据
- Logs 真数据
- Task 列表真数据

## Stage 3：核心链路真接入
- Trace 真数据
- Tool calls 真数据
- Notes / Artifacts 真数据

## Stage 4：知识与配置真接入
- Knowledge 真数据
- Settings 真读写

---

# 16. 页面验收清单

## Dashboard
- [ ] KPI 可展示
- [ ] 图表可展示
- [ ] 最近活动可展示

## Tasks
- [ ] 任务列表可筛选
- [ ] 任务详情可打开
- [ ] 可模拟发任务
- [ ] 可模拟加 hint

## Traces
- [ ] 时间线可展示
- [ ] 节点图可展示
- [ ] tool call 可展开

## Knowledge
- [ ] 列表页可展示
- [ ] 文档详情可展示
- [ ] chunk 列表可展示

## Logs
- [ ] 实时流预留
- [ ] 表格与过滤可用

## Settings
- [ ] 配置分组完整
- [ ] 编辑与保存流程完整

---

# 17. 结论

前端当前最合理路线是：

> 先把 FlagHunter Web 控制台作为一个“API 预留完整、Mock 数据驱动”的标准控制台做出来。

这样做的好处：
- 前端可以立即开工
- 不受当前后端零散数据结构牵制
- 后端后续只需按合同逐步适配
- 不会出现“前端做完了却接不上后端”的大返工

---

# 18. 参考资料

- Next.js App Router: https://nextjs.org/docs/app
- TanStack Query: https://tanstack.com/query/docs/docs
- React Flow: https://reactflow.dev/
- React Flow API: https://reactflow.dev/api-reference/react-flow
- React Flow Examples: https://reactflow.dev/examples
- xterm.js: https://xtermjs.org/docs
- Monaco Editor: https://microsoft.github.io/monaco-editor/
- Apache ECharts: https://echarts.apache.org/handbook/en/get-started/
- Open WebUI Knowledge: https://docs.openwebui.com/features/workspace/knowledge/
- Langfuse Overview: https://langfuse.com/docs?trk=public_post_main-feed-card-text
- Langfuse Data Model: https://langfuse.com/docs/observability/data-model
