# FlagHunter Web 可视化控制台 Stage II 首轮状态卡 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 适用项目：FlagHunter
- 目标阶段：Stage II（核心详情页只读联调）
- 当前结论：**已完成首轮 live 接线，进入第二轮收尾阶段**

---

## 1. 本轮范围

本轮 Stage II 仅覆盖三块核心详情页的**只读联调主链**：

1. `Task Detail`
2. `Trace Detail`
3. `Knowledge Detail`

本轮不扩到：

1. 可写动作增强
2. Trace Graph 真图生成
3. Knowledge 命中历史 / 相关运行的真实统计链
4. 任务完整会话回放

---

## 2. 本轮结论

当前结论：

> **Stage II 已完成第一轮“详情页 live 主链接通”。**

更具体地说：

1. `Task Detail` 已可走真实任务详情接口
2. `Trace Detail` 已可走真实 trace 详情接口
3. `Knowledge Detail` 已可走真实文档详情接口
4. 三页详情页在真实浏览器中都已出现 **live 数据渲染结果**
5. `Task Detail` 的负相对时间问题已拿到修补后的浏览器复验证据
6. `Knowledge Detail` 的面包屑 leaf 已拿到修补后的浏览器复验证据

因此当前阶段状态建议标记为：

> **Stage II 首轮完成，核心详情页主链通过。**

---

## 3. 本轮完成项

### 3.1 后端

已修改文件：

- `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`

本轮完成：

1. 统一任务时长计算逻辑
   - 抽出任务 `durationMs` 计算
   - `GET /api/tasks`
   - `GET /api/tasks/{taskId}`
   - `GET /api/traces`
   统一走同一套时长口径

2. 新增 Trace 详情接口
   - `GET /api/traces/{runId}`

3. 新增 Knowledge 文档详情接口
   - `GET /api/knowledge/{docKey}`

4. 详情数据最小结构收口
   - trace payload 统一输出：
     - `id`
     - `taskId`
     - `target`
     - `status`
     - `startedAt`
     - `finishedAt`
     - `durationMs`
     - `totalSteps`
     - `totalToolCalls`
     - `totalTokens`
     - `inputTokens`
     - `outputTokens`
     - `finalFlag`
   - trace detail 支持最小 `timeline`
   - knowledge detail 支持：
     - `docKey`
     - `summary`
     - `preview`
     - `chunks`
     - `hitHistory`
     - `relatedRuns`
     - `citedBy`

5. 复用现有真实产物而非新造状态
   - trace timeline 优先读取 `loot/metrics/*.json`
   - knowledge detail 直接读取 `knowledge/**/*.md`

---

### 3.2 前端

已修改文件：

- `D:\webstudy\FlagHunter\web\console\src\api.js`
- `D:\webstudy\FlagHunter\web\console\src\app.jsx`
- `D:\webstudy\FlagHunter\web\console\src\shell.jsx`
- `D:\webstudy\FlagHunter\web\console\src\mock.js`
- `D:\webstudy\FlagHunter\web\console\src\pages\tasks.jsx`
- `D:\webstudy\FlagHunter\web\console\src\pages\traces.jsx`
- `D:\webstudy\FlagHunter\web\console\src\pages\knowledge.jsx`
- `D:\webstudy\FlagHunter\web\console\index.html`

本轮完成：

#### Task Detail

1. 支持 `#/tasks/{taskId}` 深链
2. 详情面板主动拉取 `GET /api/tasks/{taskId}`
3. 附件面板继续走 `GET /api/tasks/{taskId}/attachments`
4. “追踪”按钮可跳到对应 `runId`
5. live 任务详情与 mock 详情做了分流，不再强依赖 `task_002`

#### Trace Detail

1. 详情页改为走 `GET /api/traces/{runId}`
2. timeline 支持消费真实 detail payload
3. “打开任务”可跳回 `#/tasks/{taskId}`
4. Graph 视图继续保留 mock-only 降级口径，不阻塞详情主链

#### Knowledge Detail

1. 列表页改为用唯一 `docKey` 做深链
2. 详情页改为走 `GET /api/knowledge/{docKey}`
3. 概览 / 预览 / chunks / metadata 已走真实数据
4. hits / relatedRuns / citedBy 在没有真实数据时已明确走空态

#### 壳层 / 路由

1. 顶部面包屑支持 detail route
2. detail 页可主动上报当前 leaf label
3. 前端静态资源版本号已抬升，避免浏览器缓存旧脚本

---

## 4. 浏览器级验证结果

### 4.1 验证环境

- 验证方式：真实浏览器联调
- 浏览器：
  - Codex 内置浏览器
  - 项目 `.venv` + Playwright + Microsoft Edge headless
- 验证地址：
  - `http://127.0.0.1:8083`
  - `http://127.0.0.1:8085`

### 4.2 已拿到的首轮验证结论

#### Task Detail

验证路由：

- `#/tasks/task_260526145338_0466`

已观察到：

1. 顶部已进入任务详情路由
2. 已成功请求：
   - `GET /api/tasks`
   - `GET /api/tasks/task_260526145338_0466`
   - `GET /api/tasks/task_260526145338_0466/attachments`
3. 页面已渲染真实字段：
   - `taskId`
   - `runId`
   - `target`
   - `goal`
   - `tokens`
   - `toolCalls`
   - `stopReason`
4. “追踪”按钮可作为后续跳转入口

结论：

> **Task Detail live 主链已接通。**

---

#### Trace Detail

验证路由：

- `#/traces/run_260526145338_10b6`

已观察到：

1. 已成功请求：
   - `GET /api/traces/run_260526145338_10b6`
2. 页面已渲染真实 trace 指标：
   - `taskId`
   - `target`
   - `durationMs`
   - `totalSteps`
   - `totalToolCalls`
   - `totalTokens`
3. timeline 已渲染最小真实事件链
   - `task started`
   - `generate_plan`
   - `recon_bundle`
   - `notes`
   - `finish`
   - `task stopped`
4. 无新的 console error

结论：

> **Trace Detail live 主链已接通。**

---

#### Knowledge Detail

验证路由：

- `#/knowledge/a25vd2xlZGdlL3JldHJvc3BlY3RpdmVfbm90ZXMubWQ`

已观察到：

1. 已成功请求：
   - `GET /api/knowledge/a25vd2xlZGdlL3JldHJvc3BlY3RpdmVfbm90ZXMubWQ`
2. 页面已渲染真实文档信息：
   - `title`
   - `doc_id`
   - `sourcePath`
   - `summary`
   - `preview`
   - `chunkCount`
   - `updatedAt`
3. `chunks` 标签显示真实块数
4. `hits / relatedRuns / citedBy` 在无真实数据时表现为空态
5. 无新的 console error

结论：

> **Knowledge Detail live 主链已接通。**

---

### 4.3 修补后的复验证据

#### Task Detail：负相对时间已消失

复验路由：

- `http://127.0.0.1:8085/#/tasks/task_260526145338_0466`

复验结果：

1. `negative_relative_time_found = false`
2. 未再匹配到：
   - `-\d+s ago`
   - `-\d+m ago`
   - `-\d+h ago`
3. 任务详情摘录中已显示：
   - `10h ago`
   - `开始时间 10h ago`

对应证据文件：

- `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageII_首轮修补复验证据_V1.json`

结论：

> **Task Detail 的 live 相对时间负值问题已修复。**

---

#### Knowledge Detail：面包屑 leaf 已显示真实标题

复验路由：

- `http://127.0.0.1:8085/#/knowledge/a25vd2xlZGdlL3JldHJvc3BlY3RpdmVfbm90ZXMubWQ`

复验结果：

1. `breadcrumb_leaf_is_real_title = true`
2. 页面摘录已显示：
   - `指挥控制台 / 知识库 / retrospective notes`
3. 不再显示编码后的 `docKey` 作为面包屑 leaf

对应证据文件：

- `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageII_首轮修补复验证据_V1.json`

结论：

> **Knowledge Detail 的面包屑 leaf 已正确显示真实标题。**

---

## 5. 本轮验证证据

本轮关键证据主要来自真实浏览器观察与实际命中接口：

1. `Task Detail`
   - `GET /api/tasks/task_260526145338_0466`
   - `GET /api/tasks/task_260526145338_0466/attachments`

2. `Trace Detail`
   - `GET /api/traces/run_260526145338_10b6`

3. `Knowledge Detail`
   - `GET /api/knowledge/a25vd2xlZGdlL3JldHJvc3BlY3RpdmVfbm90ZXMubWQ`

4. 代码层修补证据：
   - `D:\webstudy\FlagHunter\web\console\src\mock.js`
     - `fmt.since()` 已改为基于 `Date.now()` 计算
     - 并对负值做 `Math.max(0, ...)` 钳制

5. Python 语法检查：
   - `python -m py_compile D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`

6. 修补后的浏览器复验证据：
   - `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageII_首轮修补复验证据_V1.json`
   - 关键字段：
     - `task_detail.negative_relative_time_found = false`
     - `knowledge_detail.breadcrumb_leaf_is_real_title = true`

---

## 6. 当前剩余项

### 6.1 仍保留 mock / 降级的区域

1. `Task Detail`
   - 完整对话历史仍是 synthetic / mock 降级

2. `Trace Detail`
   - graph 视图仍不是实时生成图
   - event drawer 的 tool input/output 仍带 mock 演示性质

3. `Knowledge Detail`
   - `hitHistory`
   - `relatedRuns`
   - `citedBy`
   当前仍主要是空结构 / 降级展示

判断：

> 这些都属于 **Stage II 第二轮或 Stage III** 范畴，不阻塞本轮“详情页主链已接 live”的结论。

---

## 7. 本轮阻塞说明

本轮末尾出现一个**与本次页面联调主线无关**但需要记账的本地运行阻塞：

1. 用系统 Python 走 `python -m pentestagent.interface.main web ...` 时，
   - 命中 `D:\webstudy\FlagHunter\pentestagent\interface\main.py`
   - 存在现存语法错误

2. 直接绕过主入口启动 `web_server.py` 时，
   - 当前系统 Python 又缺少 `aiohttp`

这说明：

> 当前“重新拉起本地 Web Console 实例”的能力依赖于原先已运行好的环境，而不是裸系统 Python。

该问题**不影响本轮已经完成的前端/后端接线结论**，但影响“补新一轮浏览器复验证据”的便捷性。

---

## 8. 当前阶段判断

当前更准确的判断应为：

> **Stage II 首轮已完成，核心详情页 live 主链已打通，且本轮两项关键修补点已拿到浏览器复验证据。**

---

## 9. 下一步建议

建议下一步只做两件事，不扩 scope：

1. **决定是否继续 Stage II 第二轮**
   优先顺序建议：
   - `Task Detail` 会话/笔记真实化
   - `Trace Detail` drawer 真实 I/O
   - `Knowledge Detail` hit/runs/cited 真实统计

---

## 10. 一句话状态

> **FlagHunter Web Console 的 Stage II 已完成首轮详情页 live 接线，Task / Trace / Knowledge Detail 主链已跑通，且本轮两项关键修补点已完成浏览器复验。**

