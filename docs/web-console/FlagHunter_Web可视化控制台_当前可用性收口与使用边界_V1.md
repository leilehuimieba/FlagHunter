# FlagHunter Web 可视化控制台 · 当前可用性收口与使用边界 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 最近同步日期：2026-05-29
- 文档角色：**当前可用性收口 / 使用边界说明**
- 验证起点基线：`9fff682` · `fix(web): truthify dashboard knowledge settings live states`
- 当前结论：**当前实现已达到“可实际使用且边界更诚实”的收口标准，可作为后续继续开发前的稳定可用基线**

---

## 1. 本文档回答什么

本文档不再讨论“下一步加什么新功能”，只回答三件事：

1. 当前 Web Console 哪些能力已经可以放心使用
2. 哪些能力当前不应被当作硬保证
3. 现在如果继续推进，应该以什么边界作为新开发基线

---

## 2. 本轮同步范围

本轮是**文档同步收口**，目标是把当前代码真相写回可用性文档，不扩展新功能。

### 2.1 已同步的页面主路径真相

- Dashboard
- Knowledge
- Logs
- Settings
- Tasks / Task Detail
- Traces / Trace Detail

### 2.2 当前已开放动作合同

- create task
- add hint
- stop task
- retry task
- continue task
- runtime test
- knowledge reindex
- knowledge add doc
- knowledge open file
- MCP add server
- dashboard browse
- task detail attachment upload

### 2.3 当前不纳入硬保证升级的内容

- Dashboard 更高阶组合筛选
- Traces 更高阶分析 / 多维 drill-down
- Settings 中更完整的 MCP 管理动作（edit / delete / test connection / bearer）
- 新事件 schema 扩展
- 新图表 / 新页面 / 新控制能力

---

## 3. 当前代码真相同步结论

### 3.1 API / 合同基线：通过

截至 `2026-05-29`，以下最小联通合同已经具备自动化验证覆盖：

- `POST /api/tasks`
- `POST /api/tasks/{taskId}/hint`
- `POST /api/tasks/{taskId}/stop`
- `POST /api/tasks/{taskId}/retry`
- `POST /api/tasks/{taskId}/continue`
- `POST /api/settings/runtime/test`
- `POST /api/knowledge/reindex`
- `POST /api/knowledge/docs`
- `POST /api/knowledge/open`
- `POST /api/settings/mcp/servers`
- `GET /api/dashboard/summary`
- `GET /api/traces`

当前回归基线：

> `71 passed in 0.53s`

对应合同测试已覆盖到：

- `D:\webstudy\FlagHunter\tests\unit\web_console\test_mcp_add_server_contract.py`
- `D:\webstudy\FlagHunter\tests\unit\web_console\test_traces_filters_contract.py`
- `D:\webstudy\FlagHunter\tests\unit\web_console\test_dashboard_filters_contract.py`
- `D:\webstudy\FlagHunter\tests\unit\web_console\test_task_attachments_contract.py`
- `D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py`

### 3.2 页面主路径：通过

本轮同步后，当前主路径应按以下真相理解：

1. `#/dashboard`
   - 能打开并看到 Dashboard 主体内容
   - 顶部 `window / runtime` 已接成最小 live 筛选器
   - `notes / artifacts` 卡片已完成真值化，不再静默消费 `recentNotes / recentArtifacts` mock 数据
   - 卡片右上角 `browse` 已接通，当前跳转到 `knowledge`

2. `#/logs`
   - 能打开 live 日志页
   - 空态时可安全显示 `没有匹配的日志`
   - `实时追踪` 与来源摘要可正常显示

3. `#/settings`
   - 能打开设置页
   - Settings 不再以 `MOCK.SETTINGS` 作为 live merge 基底
   - `runtime test` 已接成真实动作
   - `MCP add server` 已接成最小 live 闭环：
     - `GET /api/settings` 返回真实 MCP server 列表
     - `POST /api/settings/mcp/servers` 可写入新 server
     - 第一版只支持 **SSE server**
     - 当前使用 **inline form**
     - add server 是**独立动作**，不并入全局 `Save changes`

4. `#/knowledge`
   - 能打开 Knowledge 列表页
   - live 下列表可直接读取真实 doc 数据
   - `reindex / add doc` 已接成真实动作
   - `export` 已接成本地 JSON 导出

5. `#/knowledge/not_real_doc`
   - invalid detail deep-link 可安全打开
   - 当前会显示真实空态，不再混入 `MOCK.CHUNKS_002`
   - `open file` 已接成真实动作，当前走浏览器打开知识源文件内容链路

6. `#/tasks/:taskId`
   - deep-link reload 可用
   - persisted hint 可见
   - `retry / continue` 已完成最小后端联通
   - Task Detail 侧栏附件能力已成最小页内闭环：
     - 即使空态也保留附件卡片
     - 可上传附件
     - 上传成功后会刷新附件列表

7. `#/traces/:runId`
   - deep-link reload 可用
   - trace replay 可见 `task.hint`
   - 顶部 `window` filter 已接通
   - 顶部 `target` filter 已接通
   - `/api/traces` 当前返回 `items + filters`，并支持 `target` query
   - 非法 `target` 会回退到 `all`

### 3.3 动作主路径：通过

当前 UI 已暴露并接通的核心动作合同可以按下列最小闭环理解：

1. Tasks
   - create
   - hint
   - stop
   - retry
   - continue

2. Settings
   - runtime test
   - MCP add server（SSE-only / inline / independent submit）

3. Knowledge
   - reindex
   - add doc
   - open file

4. Dashboard
   - browse（当前跳 `knowledge`）

5. Task Detail
   - attachment upload

这意味着：

> **当前主路径上已经不只是“能看”，而是已经具备一组最小可操作闭环。**

### 3.4 真实性收口补充

与更早的 smoke 基线相比，当前最重要的变化不是“多了多少新按钮”，而是以下真值化已经完成：

- Dashboard `notes / artifacts` 不再伪装成来自 `recentNotes / recentArtifacts`
- Dashboard 相关展示改为只消费真实存在的 `alerts`
- Settings 不再以旧 `MOCK.SETTINGS` 作为 live 合并基底
- Task Detail 附件能力会按真实能力状态显示 unavailable reason

当前附件 unavailable reason 顺序为：

1. `unsupported` → `c.unavailable`
2. `not connected` → `c.notConnected`
3. API missing → `c.notWired`

也就是说：

> **现在前端主路径上的“能不能做”与“为什么不能做”，比早期阶段更接近后端真相。**

---

## 4. 当前可以放心使用的边界

以下能力当前可作为“可用”基线：

### 4.1 读路径

1. Dashboard 真数据查看
2. Logs 页面查看与空态显示
3. Settings 页面读取当前配置
4. Task List / Task Detail 查看
5. Trace List / Trace Detail 查看
6. Knowledge 页面查看
7. Settings 只读统计查看（已接 live 数据或显式空值）
8. Dashboard 顶部最小筛选读取（`24h/all`、`all/local/docker/ssh`）
9. Traces 顶部最小筛选读取（`window`、`target`）
10. Dashboard `notes / artifacts` 卡片真实告警视图

### 4.2 详情与 reload

1. Task Detail deep-link 可直接打开
2. Trace Detail deep-link 可直接打开
3. 已停止任务 reload 后仍能看到持久化 hint
4. Trace replay 中仍能看到 `task.hint`
5. Knowledge detail 可通过 `open file` 打开知识源文件内容
6. Task Detail 空附件态下仍可进入附件操作区

### 4.3 动作路径

1. 创建任务
2. 注入 hint
3. 停止任务
4. retry task
5. continue task
6. runtime test
7. knowledge reindex
8. knowledge add doc
9. knowledge open file
10. MCP add server（首版仅 SSE）
11. dashboard browse
12. task detail attachment upload
13. Tasks / Traces / Logs / Knowledge 的本地 JSON 导出

### 4.4 live 稳定性

1. 连接徽标已完成稳定性修补
2. 短时 `/api/status` probe 抖动不再轻易把 live 状态误翻成 offline
3. SSE 近期活跃时，连接状态会保持 live
4. 页面上的未接线动作已优先改成禁用/空态/本地导出，而不是继续伪装成 live 能力

---

## 5. 当前不要当作硬保证的边界

以下内容当前**不要**当作“已经正式收口的强保证”：

1. Settings 中完整 MCP 管理台
   - 当前只接通 `add server`
   - 首版仅支持 `SSE`
   - 仍不支持 `stdio / bearer / edit / delete / connection test`

2. Dashboard browse 的深层语义
   - 当前 browse 已接通
   - 但现阶段只保证它会把用户带到 `knowledge` 主路径
   - 不应把它理解成完整的多目标 drill-down 导航系统

3. Dashboard / Traces 的更高阶筛选与分析
   - 当前只保证最小筛选器联通
   - 不保证更复杂的组合筛选、持久化筛选状态或分析型 drill-down

4. Logs 页自动化 DOM 粒度稳定性
   - 页面正文可验证
   - 但行级 DOM 选择器稳定性弱于整页文本断言

5. 更高阶的后续增强项
   - richer event schema
   - 更完整 artifact / audit 事件
   - 新动作语义扩展
   - 更进一步的 trace / knowledge 高阶分析

---

## 6. 当前最实用的使用建议

如果你接下来要**实际使用**当前控制台，建议按下面方式理解它：

### 可以依赖

- 当前主页面可打开
- 当前主页面的未接线能力会显式禁用或显示空态
- 当前详情页 deep-link 可用
- create / hint / stop / retry / continue 可用
- runtime test / knowledge reindex / add doc / open file 可用
- Settings 中 MCP add server 已接通（SSE-only）
- Dashboard 顶部最小筛选与 Traces 顶部最小筛选已接通
- Dashboard `browse` 已可把用户导向 Knowledge 主路径
- Task Detail 附件上传已形成页内最小闭环

### 不建议现在依赖

- 把早期 planning 文档当成当前实现真相
- 把 `MCP add server` 误解成完整 MCP 管理中心
- 把 `browse` 误解成完整 drill-down 导航能力
- 把 disabled 的 Dashboard / Knowledge / Settings 管理按钮当成 bug 误判；它们当前很多是有意诚实化降级
- 用过细的 Logs DOM 自动化断言替代页面级 smoke 验证

---

## 7. 对后续开发的意义

这轮同步完成后，后续如果继续开发，应该以：

- **当前真实代码**
- **当前自动化合同测试**
- **本可用性收口文档**
- **对应 smoke / verify 证据**

作为新的 source-of-truth 组合，而不是回头依赖早期阶段快照或规划愿景文档。

换句话说，接下来的开发起点不再是“这页想做成什么”，而是：

> **当前哪些能力已经真实联通，哪些边界已经明确诚实化，然后在这个基线之上继续扩。**

---

## 8. 配套证据

对应证据文件：

- `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_当前可用性Smoke验证证据_V1.json`

关键样本：

- existing task detail：`task_260527072428_7b73`
- existing trace detail：`run_260527072428_ac66`
- fresh smoke task：`task_260527085302_2fe6` / `run_260527085302_84f5`
- fresh action stop sample：`task_260527085724_8899` / `run_260527085724_9a16`
- truthification verify baseline：`9fff682`
- current regression baseline：`71 passed in 0.53s`

---

## 9. 最终收口结论

从“当前实现是否可用”的角度看：

- 当前核心读路径 **可用**
- 当前核心详情 / deep-link / reload 路径 **可用**
- 当前 Tasks 主动作与 Settings / Knowledge / Dashboard / Task Detail 的最小联通动作 **可用**
- 当前连接状态稳定性已完成最小修补
- 当前 Dashboard / Settings / Task Detail 已完成一轮更诚实的真值化收口

因此当前可以把 Web Console 标记为：

> **已达到“当前实现可实际使用且边界诚实”的收口标准，可作为后续继续开发前的稳定可用基线。**

---

## 10. 已完成同步的最近联通项（2026-05-29）

为避免上下文压缩后丢失当前主线，这里只保留已经完成并进入基线的最近联通项：

1. `Settings -> MCP -> add server`
   - 已接通最小 live 闭环
   - commit：`da34d67`

2. `Traces -> 顶部 target filter`
   - 已接通最小 live 筛选
   - commit：`2a149d4`

3. `Dashboard -> browse`
   - 已接通
   - 当前跳 `knowledge`
   - commit：`bc6625d`

4. `Dashboard -> notes / artifacts 真值化`
   - 已切到真实 `alerts` 语义
   - commit：`525c738`

5. `Task Detail -> attachments loop`
   - 已形成页内最小闭环
   - commit：`6ca4723`

6. `Task Detail -> attachments unavailable reason truthful alignment`
   - 已与真实能力状态对齐
   - commit：`2dfec2a`

这些项现在都应被视为：

> **已进入当前可用性基线，而不是“下一轮设计冻结项”。**
