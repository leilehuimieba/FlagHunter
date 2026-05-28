# FlagHunter Web 可视化控制台 规划文档收口映射 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 最近同步日期：2026-05-29
- 文档角色：**planning → current reality 的映射文档**
- 用途：说明早期规划文档里哪些已经完成、哪些已递延、哪些已被实际实现方案替代

---

## 1. 为什么需要这份文档

`docs/web-console/` 里的多份规划文档创建于 `2026-05-26`，当时它们主要解决的是：

- 前端先怎么搭骨架
- 后端先用什么技术形态
- 阶段任务如何拆
- 前后端联调怎么分阶段收口

随着 Stage I ~ Stage V 的实际推进，以及之后连续几轮 Web Console 最小联通补齐，项目**已经落地成功并完成当前可用性收口**，但实际代码实现采用了更小、更直接的方案，因此：

- 规划目标的大方向多数已完成
- 规划中的具体技术方案，部分已被替代
- 规划里的“下一步要做”有一部分现在已经变成“当前已接通基线”
- 若不做映射，后续很容易把“推荐方案”误读成“当前实现真相”

---

## 2. 总体映射结论

| 规划文档 | 当前结论 |
|---|---|
| `建设计划书_V1` | **大方向已完成，技术细节不能直接当真相** |
| `信息架构与API事件草案_V1` | **大部分接口/事件合同已落地，少量仍是增强项** |
| `前端原型拆解与组件树规范_V1` | **界面结构与页面目标大体落地，但工程技术栈未按原设想实现** |
| `前端开发任务拆分清单_V1` | **阶段目标大多已完成，但 Phase 级任务与实际代码组织不再一一对应** |
| `后端适配任务清单_V1` | **功能目标大多已完成，但架构落地方式与原方案明显不同** |
| `前后端联调与验收清单_V1` | **Stage I ~ V 联调与后续最小联通收口已大体完成，可作为历史 checklist 参考** |

---

## 3. 前端规划 → 当前现实

### 3.1 已实现 / 已达成的大方向

以下前端目标已经在当前代码中落地：

1. 控制台 shell 与多页面路由骨架
2. Dashboard / Tasks / Traces / Logs / Knowledge / Settings 页面
3. Mock → live 的渐进接线
4. Tasks / Traces / Logs / Knowledge 的真实联调
5. 最小实时体验（SSE）
6. 深色控制台风格与统一组件复用
7. Web Console 主路径真值化收口

### 3.2 与原前端技术方案的偏差

原文档中曾推荐：

- `Next.js + React + TypeScript + Tailwind`
- `web-console/` 独立子工程

但当前实际实现是：

- 静态入口：`D:\webstudy\FlagHunter\web\console\index.html`
- 页面脚本：`D:\webstudy\FlagHunter\web\console\src\*.jsx`
- 并未落成 `Next.js + TypeScript + Tailwind` 方案

结论：

> **前端规划文档中的“Phase 目标”多数已完成，但“工程栈与目录形态”没有按原方案实现。**

### 3.3 当前已从“规划项”转成“现实基线”的前端能力

以下能力不应再被当作“待做规划项”，而应视为当前代码真相的一部分：

1. Dashboard 顶部 `window / runtime` 最小筛选
2. Traces 顶部 `window / target` 最小筛选
3. Dashboard `browse` 动作接线
4. Dashboard `notes / artifacts` 真值化
   - 不再依赖 `recentNotes / recentArtifacts`
   - 当前改为只消费真实存在的 `alerts`
5. Task Detail 侧栏附件上传最小闭环
6. Task Detail attachments unavailable reason truthful alignment

### 3.4 当前仍属后续增强的前端方向

1. Logs 行级 DOM / 自动化可观测性增强
2. 更高阶的 trace / knowledge 分析增强
3. 更复杂的筛选持久化、组合 drill-down 与富交互可视化

---

## 4. 后端规划 → 当前现实

### 4.1 已实现 / 已达成的大方向

以下后端目标已经在当前代码中落地：

1. Dashboard 读接口
2. Task list / Task detail
3. Trace list / Trace detail
4. Logs query
5. Knowledge list / Knowledge detail
6. Settings get
7. 事件流接口
8. 任务动作：创建 / 停止 / hint / retry / continue / 附件
9. Knowledge 动作：reindex / add doc / open file
10. Settings 动作：runtime test / MCP add server（首版）
11. 结构化 SSE 事件（至少 `tool.finished / knowledge.retrieved / note.created`）

### 4.2 与原后端技术方案的偏差

原文档中曾推荐：

- `FastAPI`
- `Pydantic`
- `WebSocket 为主，SSE 为兼容`
- 独立目录：`pentestagent/web_console/`

但当前实际实现是：

- `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`
- 技术形态：`aiohttp + REST + SSE`
- 路由直接集中在现有 `interface` 适配层
- 没有引入独立 `web_console` 子模块

结论：

> **后端规划文档中的“功能目标”多数已达成，但“架构形态与技术选型”并未按原推荐方案实施。**

### 4.3 当前已从“后续联通缺口”转成“现实基线”的后端能力

以下项此前在规划或后续联通清单里常被当作“下一步”，但截至 `2026-05-29` 已经进入当前基线：

1. `POST /api/tasks/{taskId}/retry`
2. `POST /api/tasks/{taskId}/continue`
3. `POST /api/settings/runtime/test`
4. `POST /api/knowledge/reindex`
5. `POST /api/knowledge/docs`
6. `POST /api/knowledge/open`
7. `POST /api/settings/mcp/servers`
8. `/api/traces` 最小筛选合同
   - 返回 `items + filters`
   - 支持 `target` query
   - 非法 `target` 回退 `all`

### 4.4 当前仍属后续增强的后端方向

1. richer trace / event schema
2. 更完整的 artifact / audit 事件结构
3. Settings 更完整的 MCP 管理能力
   - `stdio`
   - bearer
   - edit / delete
   - connection test

---

## 5. API / 事件草案 → 当前现实

### 5.1 已落地的合同

当前 `web_server.py` 已支持或等价支持：

- `GET /api/status`
- `GET /api/settings`
- `POST /api/settings/runtime/test`
- `POST /api/settings/mcp/servers`
- `GET /api/dashboard/summary`
- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/tasks/{taskId}`
- `POST /api/tasks/{taskId}/stop`
- `POST /api/tasks/{taskId}/hint`
- `POST /api/tasks/{taskId}/retry`
- `POST /api/tasks/{taskId}/continue`
- `GET /api/traces`
- `GET /api/traces/{runId}`
- `GET /api/logs`
- `GET /api/knowledge`
- `GET /api/knowledge/{docKey}`
- `POST /api/knowledge/reindex`
- `POST /api/knowledge/docs`
- `POST /api/knowledge/open`
- `GET /api/events/stream`

### 5.2 已落地的关键事件

当前 SSE 至少已验证：

- `task_created`
- `task_status`
- `tool_call`
- `tool.finished`
- `knowledge.retrieved`
- `note.created`
- `task.started`
- `task.success` / `task.stopped`
- `log_line`

### 5.3 当前应按“已接通最小合同”理解的接口族

以下接口虽然不是早期规划里最先被写出的重点，但现在已经不应再视为“未来愿景”：

1. task actions
   - `create / hint / stop / retry / continue`
2. knowledge actions
   - `reindex / add doc / open file`
3. settings actions
   - `runtime test / MCP add server`
4. dashboard / traces 最小筛选
5. task attachments 页内闭环

### 5.4 仍属后续增强的合同

1. 更标准化的 graph/event schema
2. 更完整的 file / artifact / audit 事件结构
3. 更强的 settings write API
4. 更丰富的 dashboard / traces 分析型查询合同

---

## 6. 规划任务状态映射（压缩版）

| 方向 | 当前状态 | 说明 |
|---|---|---|
| 列表页只读联调 | 已完成 | Stage I 已收口 |
| 详情页真实化 | 已完成 | Stage II 已收口 |
| 实时真流联调 | 已完成 | Stage III 已收口 |
| 结构化事件前端消费 | 已完成 | Stage III 第二轮已验收 |
| Settings 可写化 | 已完成（当前基线） | 已支持部分 live 写回，属于当前可用边界的一部分 |
| Trace Graph 真图化 | 已完成（当前基线） | 当前 trace detail 已消费 live timeline / graph 数据 |
| Task replay 精细化 | 已完成（当前基线） | 当前已达到 snapshot-backed / metrics-observed / fallback 可区分的可用标准 |
| Knowledge 高阶分析 | 已完成（当前基线） | 当前基础统计与 detail usage 可视分析已收口；更深层分析仍属增强项 |
| Stage V 页面级回归与动作链收口 | 已完成 | 页面可用、动作链可用、连接稳定性修补已完成 |
| post-Stage-V 最小联通补齐 | 已完成 | 已补齐 retry / continue / runtime test / knowledge actions / MCP add server / traces target filter / dashboard browse / task attachments |

---

## 7. 现在应该怎么用这些规划文档

### 可以继续信的部分

1. 页面边界与页面名称
2. 功能优先级大方向
3. 后续增强项的大类划分
4. 联调分阶段的节奏设计

### 不要再直接照抄的部分

1. 推荐技术栈就是当前实现
2. 推荐目录结构就是当前代码结构
3. 某个 Phase 编号还和当前代码组织一一对应
4. 某个推荐后端子模块已经真实存在
5. 文档里的“下一步待做项”仍然等于当前真实缺口

---

## 8. 一句话映射结论

> **这批规划文档已经完成了“把项目带到正确方向”的使命，但它们现在更像历史设计参考，而不是当前实现真相；当前实现真相必须以 `当前可用性收口与使用边界_V1`、当前自动化合同测试、Stage V 总验收、状态矩阵和当前代码为准。**
