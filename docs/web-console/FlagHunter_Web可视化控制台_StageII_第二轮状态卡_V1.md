# FlagHunter Web 可视化控制台 Stage II 第二轮状态卡 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 适用项目：FlagHunter
- 目标阶段：Stage II（核心详情页第二轮真实化收口）
- 当前结论：**第二轮三项核心真实化已完成，已留痕，可视为 Stage II 第二轮收口完成**

---

## 1. 本轮范围

本轮只收口 Stage II 第二轮约定的三项详情页增强，不扩到新增动作或第三阶段功能：

1. `Task Detail`：会话 / 笔记真实化，无法观测时明确空态
2. `Trace Detail`：drawer 真实 tool input/output，未捕获时明确空态
3. `Knowledge Detail`：`hitCount` / `relatedRuns` / `citedBy` / `heatmap` 真实统计或真实空态

---

## 2. 本轮结论

当前结论：

> **Stage II 第二轮已完成三项核心详情真实化收口。**

更具体地说：

1. `Task Detail` 已优先消费真实 session snapshot，其次降级到 metrics observed，不再强行展示无关 mock 对话
2. `Task Detail` 的 `notes` / `plan` / `knowledgeHits` 在无真实观测时已明确显示空态
3. `Trace Detail` 已支持从 session conversation 中提取真实 tool I/O；未捕获时 drawer 会明确提示 `no observed tool I/O snapshot for this event`
4. `Knowledge Detail` 已建立文档命中统计链，`hitHistory` / `relatedRuns` / `citedBy` / `heatmap` 现在来自真实 session / knowledge usage 扫描，而不是固定 mock
5. 本轮已有 live API 与浏览器证据可以证明三页详情都已按“真实优先、空态明确”的口径工作

因此当前阶段状态建议标记为：

> **Stage II 第二轮完成，Stage II 已具备“首轮主链 + 第二轮真实化”双重留痕。**

---

## 3. 本轮完成项

### 3.1 后端

已修改文件：

- `D:/webstudy/FlagHunter/pentestagent/agents/base_agent.py`
- `D:/webstudy/FlagHunter/pentestagent/interface/web_server.py`

本轮完成：

1. 稳定化 `sessionId`
   - agent metrics session 启动前会先确保生成 `_session_id`
   - 任务结束时会主动 `save_session()` 并把 `sessionId` 落回 task registry
   - 为 `task -> session -> metrics` 对齐提供稳定主键

2. `Task Detail` 真实详情聚合
   - `GET /api/tasks/{taskId}` 现在返回真实聚合 payload，而不再只是列表项直出
   - 聚合字段包括：
     - `sessionId`
     - `messages`
     - `plan`
     - `notes`
     - `knowledgeHits`
     - `detailSource`
   - 消息来源按以下顺序收口：
     - `session_snapshot`
     - `metrics_observed`
     - `synthetic_fallback`

3. `Trace Detail` 真实 I/O 提取
   - `GET /api/traces/{runId}` 新增：
     - `sessionId`
     - `detailSource`
     - `toolEvents`
   - timeline 事件若能匹配到真实 tool event，会挂上：
     - `input`
     - `output`
   - 未匹配时保持最小 timeline，不再误把其他事件当成工具 I/O

4. `Knowledge Detail` 真实统计链
   - `GET /api/knowledge` 补齐：
     - `hitCount`
     - `lastHitAt`
   - `GET /api/knowledge/{docKey}` 补齐：
     - `hitHistory`
     - `relatedRuns`
     - `citedBy`
     - `heatmap`
   - 统计基于 session conversation 中对 `knowledge_search` / `rag` / `memory_query` 的真实提及与输出匹配

### 3.2 前端

已修改文件：

- `D:/webstudy/FlagHunter/web/console/src/pages/tasks.jsx`
- `D:/webstudy/FlagHunter/web/console/src/pages/traces.jsx`
- `D:/webstudy/FlagHunter/web/console/src/pages/knowledge.jsx`

本轮完成：

#### Task Detail

1. live 模式优先使用接口返回的 `messages`
2. 顶部新增 `◎ live detail` 来源卡
3. 右侧新增 observed sources / live plan / live notes / live knowledge hits
4. `plan` 兼容真实结构的 `label` / `description`
5. 无真实观测时空态明确显示：
   - `no observed plan snapshot`
   - `no observed notes`
   - `no observed knowledge hits`

#### Trace Detail

1. live 模式不再强回退到固定 mock run
2. 顶部新增 source bar，展示：
   - `session`
   - `metrics`
   - `tool I/O: observed / not captured`
3. timeline 无观测事件时显示：
   - `no observed trace timeline`
4. drawer 优先展示 event 上的真实 `input/output`
5. 未捕获时明确显示：
   - `no observed tool I/O snapshot for this event`

#### Knowledge Detail

1. live 列表不再强回退 mock list
2. live 详情不再强回退 mock detail
3. chunk `hits` 改为基于 `hitHistory` 的真实汇总
4. `heatmap` 改为消费真实数组，没有数据时真实为 0

---

## 4. live 验证证据

> 说明：本状态卡整理的是 **2026-05-27 已捕获的 live 联调证据**，并将关键结果沉淀到同目录 JSON。当前文档撰写阶段未追加新功能开发，只做留痕与清理。

### 4.1 Task Detail

验证对象：

- 路由：`http://127.0.0.1:8086/#/tasks/task_260526145338_0466`
- 接口：`GET http://127.0.0.1:8086/api/tasks/task_260526145338_0466`

关键证据：

1. API 返回：
   - `sessionId = "5c1b48e409b1"`
   - `detailSource.metrics = "loot/metrics/metrics_5c1b48e409b1.json"`
   - `detailSource.messages = "metrics_observed"`
   - `notes = []`
   - `plan = []`
2. `messages` 中出现真实观测文案：
   - `iteration 2 · observed tools: recon_bundle`
3. 浏览器复验结果：
   - `live_detail_present = true`
   - `has_metrics_observed_message = true`
   - `notes_empty = true`
   - `plan_empty = true`
   - `console_errors = []`

结论：

> **Task Detail 已按“真实消息优先 + 无观测即空态”工作。**

### 4.2 Trace Detail

验证对象：

- 路由：`http://127.0.0.1:8086/#/traces/run_260526145338_10b6`
- 接口：`GET http://127.0.0.1:8086/api/traces/run_260526145338_10b6`

关键证据：

1. API 返回：
   - `detailSource.metrics = "loot/metrics/metrics_5c1b48e409b1.json"`
   - `detailSource.session = null`
   - `toolEvents = []`
2. timeline 已有真实最小链：
   - `task started`
   - `generate_plan`
   - `recon_bundle`
   - `notes`
   - `finish`
   - `task stopped`
3. 浏览器复验结果：
   - source bar 已显示 `tool I/O: not captured`
   - `recon_event_present = true`
   - `drawer_no_observed_io = true`
   - `console_errors = []`

结论：

> **Trace Detail 已支持真实 I/O，当前样本因未捕获 tool snapshot 而正确走空态。**

### 4.3 Knowledge Detail

验证对象：

- 路由：`http://127.0.0.1:8086/#/knowledge/a25vd2xlZGdlXHJldHJvc3BlY3RpdmVfbm90ZXMubWQ`
- 接口：`GET http://127.0.0.1:8086/api/knowledge/a25vd2xlZGdlXHJldHJvc3BlY3RpdmVfbm90ZXMubWQ`

关键证据：

1. API 返回：
   - `hitCount = 0`
   - `hitHistory = []`
   - `relatedRuns = []`
   - `citedBy = []`
   - `heatmap = [0, 0, ...]`
2. 文档 chunk 命中数均为 0，符合真实空样本
3. 浏览器复验结果：
   - `title = retrospective notes`
   - `hits_empty = true`
   - `runs_empty = true`
   - `heatmap_sample` 为 0 hits 标题
   - `console_errors = []`

结论：

> **Knowledge Detail 已切到真实统计链，当前样本表现为可信空态。**

---

## 5. 当前剩余项

本轮完成后，Stage II 仍有少量非阻塞余项，但已经不属于“第二轮三项核心真实化”范围：

1. `Task Detail`
   - 若后续要提升可读性，可进一步补“完整会话 replay 质量”和更细粒度的 note 分类

2. `Trace Detail`
   - 若后续要增强分析能力，可继续补 graph 视图实时生成与 richer tool event 关联

3. `Knowledge Detail`
   - 若后续有更多真实使用样本，可再观察 hitHistory / heatmap 的密度表现

判断：

> 以上均属于 **Stage II 后续优化或 Stage III**，不阻塞本轮收口。

---

## 6. 文档与证据落点

本轮新增留痕文件：

- `D:/webstudy/FlagHunter/docs/web-console/FlagHunter_Web可视化控制台_StageII_第二轮状态卡_V1.md`
- `D:/webstudy/FlagHunter/docs/web-console/FlagHunter_Web可视化控制台_StageII_第二轮验证证据_V1.json`

本轮清理的一次性验证脚本：

- `D:/webstudy/FlagHunter/tmp_stage2_round2_verify.py`
- `D:/webstudy/FlagHunter/tmp_stage2_round2_knowledge_verify.py`
- `D:/webstudy/FlagHunter/tmp_verify_task_page.py`
- `D:/webstudy/FlagHunter/tmp_verify_trace_page.py`
- `D:/webstudy/FlagHunter/tmp_verify_knowledge_page.py`
- `D:/webstudy/FlagHunter/tmp_verify_knowledge_small.py`

---

## 7. 当前阶段判断

当前更准确的阶段判断应为：

> **Stage II 第二轮已完成并留痕完毕。**

换句话说：

> **Task / Trace / Knowledge 三页详情已经完成“主链接通 + 第二轮真实化收口”，可以把 Stage II 视作已完成的稳定阶段。**

---

## 8. 下一步建议

如继续推进，建议不回头补旧问题，直接二选一：

1. 进入 **Stage III**，开始动作型能力或更深层可视化增强
2. 先做一轮 **Stage II 总验收 / 归档整理**，把阶段边界、剩余优化项和回归清单再压成一份总交接文档

---

## 9. 一句话状态

> **FlagHunter Web Console 的 Stage II 第二轮已完成三项核心真实化收口，live 证据已沉淀到文档与 JSON，当前可视为 Stage II 完成并留痕完毕。**
