# FlagHunter Web 可视化控制台 · 当前可用性收口与使用边界 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 文档角色：**当前可用性收口 / 使用边界说明**
- 验证起点基线：`33a5293` · `docs(web): sync stage v baseline after stability fix`
- 当前结论：**当前实现已达到“可实际使用”的收口标准，可作为后续继续开发前的稳定可用基线**

---

## 1. 本文档回答什么

本文档不再讨论“下一步加什么新功能”，只回答三件事：

1. 当前 Web Console 哪些能力已经可以放心使用
2. 哪些能力当前不应被当作硬保证
3. 现在如果继续推进，应该以什么边界作为新开发基线

---

## 2. 本轮 fresh smoke verify 范围

本轮只验证**真实使用主路径**，不扩展新功能：

### 2.1 页面可打开性

- Dashboard
- Logs
- Settings
- Task Detail（existing sample）
- Trace Detail（existing sample）
- Task Detail（fresh smoke sample）

### 2.2 当前已开放动作合同

- create task
- add hint
- stop task

### 2.3 当前不纳入本轮硬门槛的内容

- retry
- continue
- 新事件 schema 扩展
- 新图表 / 新页面 / 新控制能力

---

## 3. fresh verify 结论

### 3.1 API reachability：通过

本轮 fresh verify 中，以下端点全部返回 `200`：

- `GET /api/status`
- `GET /api/dashboard/summary`
- `GET /api/tasks`
- `GET /api/traces`
- `GET /api/logs`
- `GET /api/settings`

### 3.2 页面主路径：通过

本轮 fresh verify 已确认：

1. `#/dashboard`
   - 能打开并看到 Dashboard 主体内容
   - 已验证 `活跃运行 / 最近任务 / Flag 看板` 等关键区域

2. `#/logs`
   - 能打开 live 日志页
   - 空态时可安全显示 `没有匹配的日志`
   - `实时追踪` 与来源摘要可正常显示

3. `#/settings`
   - 能打开设置页
   - `配置面板 / 模型配置 / API 密钥` 等核心区域可见
   - 当前 partial live save 的 UI 表面存在且可读取

4. `#/tasks/task_260527072428_7b73`
   - deep-link reload 可用
   - `observed session transcript` 可见
   - persisted hint 可见

5. `#/traces/run_260527072428_ac66`
   - deep-link reload 可用
   - timeline 中 `task stopped / recon bundle / hint accepted` 可见

6. `#/tasks/task_260527085302_2fe6`
   - fresh smoke task detail 可打开
   - fresh hint 文本已在 detail 中持久化可见
   - detail 仍保持 snapshot-backed transcript

### 3.3 动作主路径：通过

本轮补了一个更窄的动作验证样本：

- task: `task_260527085724_8899`
- run: `run_260527085724_9a16`

验证结果：

- `POST /api/tasks` → `201`
- `POST /api/tasks/{taskId}/hint` → `200`
- `POST /api/tasks/{taskId}/stop` → `200`
- 最终任务状态：`stopped`
- 最终停止原因：`user_stop`
- hint 已持久化到 task detail 数据面

这说明：

> **当前 UI 已暴露的 create / hint / stop 三个核心动作合同，在 live 后端下是可实际使用的。**

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

### 4.2 详情与 reload

1. Task Detail deep-link 可直接打开
2. Trace Detail deep-link 可直接打开
3. 已停止任务 reload 后仍能看到持久化 hint
4. Trace replay 中仍能看到 `task.hint`

### 4.3 动作路径

1. 创建任务
2. 注入 hint
3. 停止任务

### 4.4 live 稳定性

1. 连接徽标已完成稳定性修补
2. 短时 `/api/status` probe 抖动不再轻易把 live 状态误翻成 offline
3. SSE 近期活跃时，连接状态会保持 live

---

## 5. 当前不要当作硬保证的边界

以下内容当前**不要**当作“已经正式收口的硬保证”：

1. `retry`
   - 目前不是本轮可用性基线的一部分
   - 未做单独 hard acceptance

2. Logs 页自动化 DOM 粒度稳定性
   - 页面正文可验证
   - 但行级 DOM 选择器稳定性弱于整页文本断言

3. 更高阶的后续增强项
   - richer event schema
   - 更完整 artifact / audit 事件
   - 新动作语义扩展
   - 更进一步的 trace / knowledge 高阶分析

---

## 6. 当前最实用的使用建议

如果你接下来要**实际使用**当前控制台，建议按下面方式理解它：

### 可以依赖

- 当前主页面可打开
- 当前详情页 deep-link 可用
- create / hint / stop 可用
- Stage V 收口链路已完成

### 不建议现在依赖

- 把 planning 文档当成当前实现真相
- 把 retry 当成已最终验收能力
- 用过细的 Logs DOM 自动化断言替代页面级 smoke 验证

---

## 7. 对后续开发的意义

这轮可用性收口完成后，后续如果要继续开发，应该以：

- **当前真实代码**
- **Stage V 总验收文档**
- **本可用性收口文档**
- **本轮 smoke 证据 JSON**

作为新的 source-of-truth 组合，而不是回头依赖早期阶段快照或规划愿景文档。

---

## 8. 配套证据

对应证据文件：

- `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_当前可用性Smoke验证证据_V1.json`

关键样本：

- existing task detail：`task_260527072428_7b73`
- existing trace detail：`run_260527072428_ac66`
- fresh smoke task：`task_260527085302_2fe6` / `run_260527085302_84f5`
- fresh action stop sample：`task_260527085724_8899` / `run_260527085724_9a16`

---

## 9. 最终收口结论

从“当前实现是否可用”的角度看：

- 当前核心读路径 **可用**
- 当前核心详情 / deep-link / reload 路径 **可用**
- 当前 create / hint / stop 动作 **可用**
- 当前连接状态稳定性已完成最小修补

因此当前可以把 Web Console 标记为：

> **已达到“当前实现可实际使用”的收口标准，可作为后续继续开发前的稳定可用基线。**
