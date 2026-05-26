# FlagHunter Web 可视化控制台后端适配任务清单 V1

- 文档版本：V1
- 编写日期：2026-05-26
- 适用项目：FlagHunter
- 用途：指导后端实现 agent / 架构 agent 按阶段为 Web 控制台补齐真实数据接口与事件流

---

# 1. 文档目标

本文档用于把 Web 可视化控制台所需的后端工作拆成可执行任务，明确：
- 先接哪些真实数据
- 哪些接口应先只读
- 哪些事件需要统一抽象
- 哪些现有模块可直接复用
- 如何以最小代价接入现有工程

目标不是重构现有 FlagHunter 主体，而是：

> 在尽量少破坏现有运行链路的前提下，为 Web 控制台补一层稳定的 API 和事件适配层。

---

# 2. 总体原则

1. 不先重构 agent 主干，优先做“适配层”
2. 先读接口，后写接口
3. 先静态查询接口，后实时流接口
4. 先本地单用户设计，后考虑扩展
5. 不让前端直接读取后端内部文件结构
6. 所有 Web 数据优先通过统一 schema 输出

---

# 3. 与现有工程的关系

当前项目内已有大量可复用模块：

- `pentestagent/interface/notifier.py`
- `pentestagent/tools/token_tracker.py`
- `pentestagent/tools/notes/`
- `pentestagent/agents/pa_agent/ctf_dispatcher.py`
- `pentestagent/agents/pa_agent/strategy_memory.py`
- `pentestagent/knowledge/`
- `pentestagent/runtime/`
- `pentestagent/interface/conversation_store.py`
- `mcp/server/`

后端适配的重点不是“发明新系统”，而是：
- 统一这些模块的输出结构
- 建立 Web API 层
- 建立实时事件流层
- 建立可查询的 run/task 视图层

---

# 4. 推荐后端实现方式

## 4.1 推荐技术方案
- FastAPI
- Pydantic
- WebSocket 为主
- SSE 作为兼容/简化方案
- SQLite 作为本地状态存储（首期可选）

## 4.2 推荐接入方式
建议新增一个独立子模块，例如：

```text
pentestagent/web_console/
  api/
  services/
  schemas/
  repositories/
  eventbus/
```

目标是把 Web 控制台能力从 TUI/CLI 中解耦出来。

---

# 5. 总任务分期

- Phase B0：建立 Web 控制台后端骨架
- Phase B1：统一 schema 与 service 层
- Phase B2：Dashboard 读接口接入
- Phase B3：Tasks / Runs / Trace 查询接口接入
- Phase B4：Logs 查询与实时流接入
- Phase B5：Knowledge / Strategy Memory 接入
- Phase B6：Settings 读写接口接入
- Phase B7：实时事件流接入
- Phase B8：任务动作接口接入
- Phase B9：联调收口与兼容层整理

---

# 6. Phase B0：建立 Web 控制台后端骨架

## 6.1 任务目标
先搭出独立后端入口，不直接让前端连零散模块。

## 6.2 任务项

### B0-1 新建 Web Console 后端模块
建议目录：

```text
pentestagent/web_console/
  __init__.py
  app.py
  api/
  schemas/
  services/
  repositories/
  eventbus/
```

#### 验收
- 有单独 FastAPI app
- 能正常启动

---

### B0-2 定义基础路由分组
建议分组：
- `/api/dashboard`
- `/api/tasks`
- `/api/traces`
- `/api/knowledge`
- `/api/logs`
- `/api/settings`
- `/api/events`

#### 验收
- 路由结构稳定
- 可返回 mock/placeholder

---

### B0-3 接入基础配置与启动入口
#### 验收
- 可本地启动 Web API
- 有 README/启动说明

---

# 7. Phase B1：统一 schema 与 service 层

## 7.1 任务目标
把前端文档里的类型转换为后端 schema。

## 7.2 任务项

### B1-1 建立 Pydantic schema
至少包括：
- TaskRecord
- RunRecord
- RunStepRecord
- ToolCallRecord
- KnowledgeHitRecord
- NoteRecord
- ArtifactRecord
- FileChangeRecord
- LogRecord
- AgentEvent

#### 验收
- schema 集中管理
- 字段名与前端合同一致

---

### B1-2 建立 service 层
建议：
- `dashboard_service.py`
- `tasks_service.py`
- `traces_service.py`
- `knowledge_service.py`
- `logs_service.py`
- `settings_service.py`
- `events_service.py`

#### 验收
- API 层不直接读文件/模块
- 统一走 service

---

### B1-3 建立 repository 层（可轻量）
首期可只做简单封装：
- notes repository
- strategy memory repository
- token usage repository
- logs repository

#### 验收
- repository 可单测
- service 不直接耦合磁盘格式

---

# 8. Phase B2：Dashboard 读接口接入

## 8.1 任务目标
先把最容易接的总览数据接出来。

## 8.2 任务项

### B2-1 接入 token_tracker
来源：
- `pentestagent/tools/token_tracker.py`

输出到：
- `GET /api/dashboard/summary`

字段优先：
- dailyTokens
- last input/output
- currentDate

---

### B2-2 接入最近任务摘要
来源优先级：
- conversation/task session
- recent run cache
- retrospective/export

如果当前没有统一任务表，可先做轻量缓存索引。

---

### B2-3 接入最近 notes / artifacts / memory 摘要
来源：
- notes
- strategy_memory
- loot artifacts 索引（如有）

---

### B2-4 生成 Dashboard charts 数据
即使底层数据不完整，首期也应先给出：
- token trend
- tool distribution
- failure distribution

#### 验收
- Dashboard 全部是“真数据接口”，不再依赖纯 mock

---

# 9. Phase B3：Tasks / Runs / Trace 查询接口接入

## 9.1 任务目标
把 Web 控制台最核心的数据读接口接起来。

## 9.2 任务项

### B3-1 定义 Task / Run 的持久化视图
当前项目可能没有专门的“task table”，因此建议先建立轻量索引机制：
- 每次 run 开始记录 task metadata
- 每次 run 结束记录 result metadata
- 索引文件或 SQLite 表皆可

建议最少记录：
- task_id
- run_id
- title
- target
- goal
- status
- started_at
- finished_at
- detected_type
- final_flag
- stop_reason

#### 验收
- 可稳定列出最近任务与 run

---

### B3-2 接入 Task 列表查询
实现：
- `GET /api/tasks`
- `GET /api/tasks/{taskId}`

#### 验收
- 前端任务列表可直接接真接口

---

### B3-3 接入 Run / Trace 列表查询
实现：
- `GET /api/traces`
- `GET /api/traces/{runId}`

#### 验收
- 前端 trace 列表可接真接口

---

### B3-4 建立 run 详情聚合逻辑
聚合内容：
- steps
- tool calls
- observations
- notes
- artifacts
- final result

#### 重点
这里不要求后端一开始就完全数据库化，允许从多个来源聚合。

#### 验收
- 一个 run 的详情能完整返回前端需要的关键字段

---

# 10. Phase B4：Logs 查询与实时流接入

## 10.1 任务目标
补齐 Logs 页面需要的数据面。

## 10.2 任务项

### B4-1 统一日志读取入口
来源可能包括：
- app logs
- runtime logs
- task/run logs
- notifier 输出

建议先封装为：
- log repository
- log query service

---

### B4-2 实现日志查询接口
- `GET /api/logs`

支持参数：
- level
- source
- taskId
- runId
- keyword
- page
- pageSize

#### 验收
- 前端 LogsTable 可接真实接口

---

### B4-3 实现日志实时流接口
优先实现：
- SSE 或 WebSocket

#### 验收
- 前端可看到新增日志滚动进来

---

# 11. Phase B5：Knowledge / Strategy Memory 接入

## 11.1 任务目标
把知识系统和策略记忆系统前台化。

## 11.2 任务项

### B5-1 接入 Knowledge 文档索引视图
来源：
- `knowledge/`
- rag/indexer metadata
- embeddings/index metadata（如果存在）

输出：
- `GET /api/knowledge`
- `GET /api/knowledge/{docId}`

---

### B5-2 接入 chunk 视图
首期即使没有完整 chunk 索引库，也应能返回：
- chunk text
- chunk index
- source path

---

### B5-3 接入 strategy_memory
来源：
- `pentestagent/agents/pa_agent/strategy_memory.py`

可提供：
- 最近 memory entries
- matched entries
- solved/failed correlation

#### 注意
这部分可以先并到 Knowledge 页面，后续再拆独立 Memory 页面。

---

### B5-4 接入 knowledge hit 视图
如果当前检索命中尚未统一记录，则需要补：
- 检索时写命中审计记录
- run_id 关联
- step_id 关联

#### 验收
- 能回答“某次任务用了哪些知识”

---

# 12. Phase B6：Settings 读写接口接入

## 12.1 任务目标
把配置读取和部分配置写入暴露给前端。

## 12.2 任务项

### B6-1 接入只读配置接口
- `GET /api/settings`

建议先支持：
- model
- runtime
- knowledge
- budget

---

### B6-2 接入部分可写配置接口
- `PUT /api/settings`

首期建议只允许改低风险配置：
- UI 相关配置
- 非核心默认项
- RAG threshold 等软配置

#### 暂不建议首期开放
- 直接改 SSH 密钥路径
- 直接改高风险执行模式

---

### B6-3 增加配置测试接口
- `POST /api/settings/test-runtime`

用途：
- 测试 Local/Docker/SSH 是否可达

---

# 13. Phase B7：实时事件流接入

## 13.1 任务目标
这是整个 Web 控制台价值最高的后端部分。

## 13.2 任务项

### B7-1 建立统一事件总线
推荐做轻量 event bus：
- publish(event)
- subscribe(listener)

可以先进程内实现。

---

### B7-2 接入 notifier
来源：
- `pentestagent/interface/notifier.py`

目标：
- 将现有 UI 通知桥扩展为 Web 可消费事件桥

---

### B7-3 为关键节点补结构化事件
建议优先补：
- task.started
- task.finished
- tool.called
- tool.finished
- knowledge.retrieved
- note.created
- verifier.flag.verified
- recovery.stopped

---

### B7-4 暴露实时事件接口
- `GET /api/events/stream`
或
- `WS /api/events/ws`

#### 验收
- 前端 Tasks/Trace/Logs 至少有一个页面可实时更新

---

# 14. Phase B8：任务动作接口接入

## 14.1 任务目标
让前端不只是“看”，还能真正控制 agent。

## 14.2 任务项

### B8-1 创建任务接口
- `POST /api/tasks`

要求：
- 能启动一次真实 run
- 返回 task_id / run_id

---

### B8-2 增加 hint 接口
- `POST /api/tasks/{taskId}/hint`

要求：
- 能把额外提示注入到当前任务上下文中
- 至少支持下一轮 agent 消费到

---

### B8-3 Stop / Retry / Continue 接口
- `POST /api/tasks/{taskId}/stop`
- `POST /api/tasks/{taskId}/retry`
- `POST /api/tasks/{taskId}/continue`

#### 注意
如果当前运行模型不支持真正“热插入继续”，首期可以先实现：
- stop
- retry with previous context

---

# 15. Phase B9：联调收口与兼容层整理

## 15.1 任务目标
确保前端 Mock 到真实后端切换平滑。

## 15.2 任务项

### B9-1 对照前端 API 合同逐项验收
核查：
- 字段名
- 可空性
- 时间格式
- status 枚举
- 详情结构

---

### B9-2 增加兼容转换层
如果后端内部字段与前端合同不一致，不修改前端，优先在 service/adapter 层转换。

---

### B9-3 补最小联调测试
至少覆盖：
- Dashboard summary
- Task list
- Task detail
- Trace detail
- Logs query
- Knowledge list
- Settings get

---

# 16. 推荐后端工程目录

建议新增：

```text
pentestagent/web_console/
  app.py
  api/
    dashboard.py
    tasks.py
    traces.py
    knowledge.py
    logs.py
    settings.py
    events.py
  schemas/
    dashboard.py
    tasks.py
    traces.py
    knowledge.py
    logs.py
    settings.py
    events.py
  services/
    dashboard_service.py
    tasks_service.py
    traces_service.py
    knowledge_service.py
    logs_service.py
    settings_service.py
    events_service.py
  repositories/
    notes_repository.py
    token_repository.py
    strategy_memory_repository.py
    runs_repository.py
    logs_repository.py
  eventbus/
    bus.py
    publishers.py
    subscribers.py
```

---

# 17. 可复用现有模块映射建议

## 优先复用
- `token_tracker.py` -> dashboard tokens
- `notes` -> notes list / activity / trace notes
- `strategy_memory.py` -> knowledge/memory summary
- `ctf_dispatcher.py` state & observations -> trace detail
- `notifier.py` -> events bridge

## 需要补适配
- tool calls 的结构化沉淀
- file changes 的结构化审计
- knowledge hits 的结构化沉淀
- task/run 的统一索引

---

# 18. 必须优先补的几个结构化缺口

## 缺口 1：Task / Run 索引
当前若没有统一 task/run 存储，前端很多页面会很难接。

## 缺口 2：ToolCall 结构化记录
如果只有零散日志，没有统一 tool call 记录，Trace 页面价值会大幅下降。

## 缺口 3：KnowledgeHit 结构化记录
Knowledge 页面和 Trace 页面都需要这个。

## 缺口 4：FileChange 审计
你前面关心“写了什么、删了什么”，这块必须有统一事件。

---

# 19. 推荐执行顺序（可直接给后端 agent）

按下面顺序推进：

1. B0-1 ~ B0-3
2. B1-1 ~ B1-3
3. B2-1 ~ B2-4
4. B3-1 ~ B3-4
5. B4-1 ~ B4-3
6. B5-1 ~ B5-4
7. B6-1 ~ B6-3
8. B7-1 ~ B7-4
9. B8-1 ~ B8-3
10. B9-1 ~ B9-3

---

# 20. 每阶段验收要求

## 每个阶段必须满足
- 可启动
- 可调用
- 字段结构稳定
- 至少有一条联调证据
- 不破坏现有 TUI/CLI 主链

## 每阶段交付物
- 完成项
- 未完成项
- 风险项
- 下一步建议

---

# 21. 给后端实现 agent 的限制

1. 不允许直接让前端读取内部文件路径格式
2. 不允许把所有逻辑都写进 FastAPI route
3. 不允许跳过 schema 层直接返回散乱 dict
4. 不允许为了 Web UI 大规模重构 agent 主干
5. 不允许一开始就引入复杂消息中间件
6. 不允许先做写接口而忽略读接口与查询视图

---

# 22. 最小可交付后端能力清单

MVP 后端至少应提供：
- Dashboard summary
- Task list
- Task detail
- Trace detail
- Logs query
- Knowledge list
- Settings get
- 至少一个事件流接口

---

# 23. 结论

后端适配最关键的不是“把接口写出来”，而是：

> 把现有 FlagHunter 内部零散但强大的能力，整理成前端能长期消费的稳定数据面。

最优路线是：
- 先 API 骨架
- 再统一 schema
- 再接只读查询
- 再接事件流
- 最后接控制动作

这样能最大程度减少对现有主系统的扰动。
