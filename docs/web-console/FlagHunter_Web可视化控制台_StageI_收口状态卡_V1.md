# FlagHunter Web 可视化控制台 Stage I 收口状态卡 V1

- 文档版本：V1
- 编写日期：2026-05-27
- 适用项目：FlagHunter
- 目标阶段：Stage I（基础只读数据联调）
- 当前结论：**基本收口，可进入 Stage II**

---

## 1. 本次收口范围

本次收口仅覆盖 Stage I 约定的基础只读联调范围，以及为保证 Stage I 稳定性所做的最小配套修补：

### Stage I 页面

1. Dashboard
2. Logs
3. Tasks（列表视角）
4. Knowledge（列表视角）
5. Settings（只读视角）

### 本轮额外收口的小修补

1. `Logs` 启动噪音过滤
2. `Knowledge` 重复 key 修复
3. `Settings` 只读文案对齐
4. `Tasks` 列表尾巴问题修补

---

## 2. 当前阶段判断

当前 Web Console 已完成：

1. 基础只读接口接线
2. live/mock 切换主链验证
3. 关键页面浏览器级联调
4. Stage I 尾巴问题清理

因此当前阶段判断为：

> **Stage I 已基本收口，具备进入 Stage II（详情页联调）的条件。**

---

## 3. 收口结果总表

| 模块 | 目标 | 当前状态 | 结论 |
|---|---|---:|---|
| Dashboard | live 只读展示 | 已接 live 数据，空态正常 | 通过 |
| Logs | live 日志列表 + 空态 | 已过滤启动噪音，空态正常 | 通过 |
| Tasks | 列表可看、可筛选、可选中 | 已补目标搜索/自动选中/空态分支 | 通过 |
| Knowledge | 文档列表可看 | 已补时间字段、空态、重复 key | 通过 |
| Settings | 只读展示 | 已切到 Stage I 只读口径 | 通过 |

---

## 4. 本轮完成项

### 4.1 后端

已完成：

1. `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`
   - 补 `GET /api/tasks` 的 `durationMs`
   - 补 `GET /api/dashboard/summary` 的 `recentTasks` / `recentToolCalls` / `alerts` / `flags`
   - 统一 `GET /api/logs` 返回字段：`msg` / `message` / `runId` / `taskId`
   - 补 `GET /api/knowledge` 的 `chunkCount` / `updatedAt` / `lastHitAt`
   - 过滤 `web_console_*.log` 启动噪音

### 4.2 前端

已完成：

1. `D:\webstudy\FlagHunter\web\console\src\pages\dashboard.jsx`
   - 关键块切 live
   - 图表与活动区补空态

2. `D:\webstudy\FlagHunter\web\console\src\pages\logs.jsx`
   - 增加日志 normalize
   - 统一消费 live / mock 日志字段

3. `D:\webstudy\FlagHunter\web\console\src\pages\knowledge.jsx`
   - 补空时间兜底
   - 修重复 key

4. `D:\webstudy\FlagHunter\web\console\src\pages\settings.jsx`
   - 明确 Stage I 只读
   - 保存按钮禁用

5. `D:\webstudy\FlagHunter\web\console\src\pages\tasks.jsx`
   - 搜索补 `target`
   - 没有 `task_002` 时自动选中首个 live task
   - 无选中时增加空态分支

6. `D:\webstudy\FlagHunter\web\console\src\i18n.js`
   - 补只读文案
   - 补 Tasks 空态文案

---

## 5. 浏览器级联调结果

### 5.1 验证环境

- 验证方式：真实浏览器联调
- 浏览器：
  - `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`
- 验证地址：
  - `http://127.0.0.1:8082`

### 5.2 页面结果

#### Dashboard

- `window.IS_LIVE = true`
- 无 `console error`
- 无 `page error`
- 无失败请求
- 图表类空数据区域已显示空态

结论：**通过**

#### Logs

- `window.IS_LIVE = true`
- 无 `console error`
- 无 `page error`
- 无失败请求
- `GET /api/logs` 在本轮最新实例下返回空数组
- 页面正确显示“没有匹配的日志”

结论：**通过**

#### Knowledge

- `window.IS_LIVE = true`
- 无 `console error`
- 无 `page error`
- 无失败请求
- 重复 key 警告已消失

结论：**通过**

#### Settings

- `window.IS_LIVE = true`
- 无 `console error`
- 无 `page error`
- 无失败请求
- 页面已显示：
  - “Stage I 为只读模式，不会将修改写入 .env”
  - “Stage I：只读”

结论：**通过**

#### Tasks

- `window.IS_LIVE = true`
- 无 `console error`
- 无 `page error`
- 无失败请求
- 在没有 `task_002` 的 live 数据场景下，页面已自动选中首个任务

结论：**通过**

---

## 6. 验证证据

本轮收口的关键验证证据如下：

1. `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageI_首轮浏览器联调证据_V1.json`
   - Stage I 首轮浏览器级联调结果

2. `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_StageI_尾巴复验证据_V1.json`
   - Stage I 尾巴修补后的浏览器复验结果

3. `D:\webstudy\FlagHunter\logs\web_console_8082_stdout.log`
   - 最新 8082 实例启动日志

4. Python 语法检查：
   - `python -m py_compile D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`

---

## 7. 当前剩余项

下面这些项当前**不阻塞 Stage I 收口**，但建议在 Stage II 或后续小迭代中处理：

### 7.1 非阻塞显示问题

1. `Tasks` 页相对时间出现负值  
   现象示例：
   - `-44378s ago`

   判断：
   - 这是前端时间格式化仍使用 mock 基准时间带来的显示问题
   - 不影响接口联通和页面主链
   - **不阻塞 Stage I 收口**

### 7.2 仍保留 mock 的次要区域

1. Dashboard 的 `recentNotes / recentArtifacts`
2. Knowledge 详情页大部分内容仍为 mock
3. Settings 虽已只读，但表单仍保留可编辑外观

判断：
 - 这些属于 Stage II/后续收口，不影响 Stage I 基础只读页通过

---

## 8. 是否通过 Stage I

结论：

> **通过。**

更准确地说：

> **Stage I 已达到“可收口、可留痕、可进入下一阶段”的标准。**

不建议继续在 Stage I 上反复打磨边角。

---

## 9. 下一步建议

建议正式进入：

> **Stage II：核心详情页联调**

推荐顺序：

1. `Task Detail`
2. `Trace Detail`
3. `Knowledge Detail`

推荐原则：

1. 先补真实详情数据
2. 先只读，后动作
3. 先结构稳定，后交互增强

---

## 10. 一句话状态

> **FlagHunter Web Console 的 Stage I 已基本收口，live 联调主链通过，可以进入 Stage II。**

