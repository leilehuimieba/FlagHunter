# FlagHunter Web 可视化控制台 Stage IV · Knowledge Usage 可视分析状态卡 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 归属阶段：Stage IV / Milestone 4
- 结论：**已完成 Task Detail 的 Knowledge usage 可视分析增强**

---

## 1. 本轮完成项

1. 后端 `Task Detail` 已支持真实 `knowledgeHits` 构建：
   - `session_snapshot`：从真实 session conversation 提取 knowledge tool 调用与结果
   - `metrics_observed`：当缺少 session snapshot 时，降级为 metrics 级“observed only”知识使用记录
   - `unobserved`：没有知识检索行为时返回真实空态
2. `detailSource` 已补充 knowledge 来源字段：
   - `knowledge`
   - `knowledgeConfidence`
3. 前端 `KnowledgeCard` 已从简单列表升级为：
   - `fidelity / queries / matched / no match / observed only` 统计
   - `source × count` 汇总
   - 命中明细（source / result kind / query / preview / time）
4. 右侧 `observed sources` 已新增 knowledge 来源与可信度字段

---

## 2. 本轮解决的核心问题

此前 Task Detail 右侧 `knowledge hits` 仅是占位式列表：

- live 任务历史无法回放真实 knowledge usage
- 无法区分 snapshot-backed / metrics-only / empty
- 无法直接看见 query、结果类型与低保真边界

本轮修补后：

- 有真实 session 时，KnowledgeCard 直接显示真实 knowledge usage 明细
- 只有 metrics 时，不再伪造 query/chunk，而是明确显示 `observed only`
- 无使用记录时，保持真实空态 `no observed knowledge hits`

---

## 3. 本轮验证结论

### 3.1 snapshot-backed 案例

验证任务：

- `task_260527023632_121e`

结果：

- `detailSource.knowledge = session_snapshot`
- `knowledgeHits.length = 1`
- 命中项包含：
  - `source = knowledge_search`
  - `resultKind = no_match`
  - `query = CTF web reconnaissance local target short pass ...`
- 浏览器页面显示：
  - `fidelity = snapshot-backed`
  - `queries = 1`
  - `no match = 1`

### 3.2 metrics-observed 案例

验证任务：

- `task_260527023937_7b56`

结果：

- `detailSource.knowledge = metrics_observed`
- `knowledgeHits.length = 1`
- 命中项为低保真记录：
  - `title = knowledge_search observed in metrics`
  - `resultKind = observed_only`
  - `preview = query / chunk details unavailable without session snapshot`
- 浏览器页面显示：
  - `fidelity = metrics-observed`
  - `observed only = 1`

### 3.3 empty 案例

验证任务：

- `task_260527022218_d4b1`

结果：

- `detailSource.knowledge = unobserved`
- `knowledgeHits = []`
- 浏览器页面显示：
  - `fidelity = unobserved`
  - `no observed knowledge hits`

### 3.4 console

- 浏览器级复验过程中未见新的 console error / warn

---

## 4. 当前残余边界

1. `metrics_observed` 仅提供“工具使用已观察到”的低保真知识记录，不伪造 query / doc / chunk
2. `score` 仅在输出文本中能解析到结构时才展示；目前大多数 live 样本仍为空
3. 本轮只增强 `Task Detail` 右侧 Knowledge usage，可视化未外扩到 Trace / Dashboard

---

## 5. 下一步建议

Milestone 4 已可视为完成。

若继续推进 Stage IV，建议优先转入：

- Stage IV 当前轮次归档 / 总验收整理
- 或进入下一轮真正需要的新功能，而不是继续打磨本卡片
