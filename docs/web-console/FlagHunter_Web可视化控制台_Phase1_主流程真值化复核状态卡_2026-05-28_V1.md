# FlagHunter Web 可视化控制台 Phase 1 主流程真值化复核状态卡 2026-05-28 V1

- 复核时间：2026-05-28（Asia/Shanghai）
- 复核范围：Web Console Phase 1 主流程恢复、mock 语义清理、fresh smoke 留痕
- 复核入口：`http://127.0.0.1:3000`
- 运行环境：`D:\webstudy\FlagHunter\.venv\Scripts\python.exe`

---

## 1. 当前结论

本轮复核确认：

> **Web Console Phase 1 的主目标已经落到当前代码主线，任务详情“对话区过窄”不再是当前主阻塞；当前更合适的阶段判断是“Phase 1 主流程已真值化，进入收尾与验收留痕阶段”。**

更具体地说：

1. 主路径已经不再依赖 `task_002` / `MOCK.DASHBOARD` / `MOCK.MESSAGES_002` / `MOCK.TASK_002_PANEL`
2. 任务详情已经是“列表 + 主对话 / 主分析区 + 右侧上下文面板”的可用布局
3. `Topbar` 已承担唯一的 detail mode toggle 入口
4. `GET /api/tasks/{taskId}` + SSE 增量合并已成为 detail 主真相来源
5. 当前剩余工作不再是“大改布局”，而是：
   - 对齐 plan 状态
   - 清理主路径残留 mock 语义
   - 补 fresh smoke 验收记录

---

## 2. fresh verify 结果

### 2.1 后端契约测试：通过

执行：

```bash
D:\webstudy\FlagHunter\.venv\Scripts\python.exe -m pytest tests\unit\interface\test_web_server.py -q
```

结果：

- `12 passed`

说明：

- `/api/status`
- `/api/dashboard/summary`
- `/api/tasks/{taskId}`
- `/api/tasks/{taskId}/hint`
- `/api/tasks/{taskId}/attachments`

这些当前主流程依赖的接口契约处于可验证通过状态。

---

### 2.2 主页面可打开性：通过

实际启动：

```bash
D:\webstudy\FlagHunter\.venv\Scripts\python.exe -m pentestagent web --host 127.0.0.1 --port 3000
```

并确认：

```bash
GET http://127.0.0.1:3000/api/status
```

返回：

- `ok = true`
- `runtime = LocalRuntime`
- `version = 0.2.0`

---

### 2.3 Tasks 主工作区 smoke：通过

实际复核页面：

- `#/tasks`

已确认：

1. 左侧任务列表可正常显示真实 task 数据
2. 中间 detail 区不再是旧的“窄条式对话区”
3. 右侧分析面板可与 detail 共存
4. 顶部 `对话优先 / 分析优先` 切换可见且位置统一
5. detail header 已是分组后的身份 / 目标 / 运行态信息，而不是旧的 mock 驱动拼接头

---

### 2.4 响应式宽度复核：通过

本轮手工复核了以下宽度：

- `1280px`
- `1366px`
- `1440px`

结论：

#### 1280px

- 任务列表仍可读
- 主对话区仍保持可用宽度
- 分析面板不会把中间内容压回旧的“不合理窄区”

#### 1366px

- 三段结构仍然成立
- detail 区对话阅读宽度可接受
- 分析侧栏未出现明显挤压主内容的问题

#### 1440px

- 列表 / 主 detail / 右侧分析栏共存正常
- 页面没有继续表现为“固定 1440 假大屏”的僵硬布局

---

## 3. 本轮顺手清理的残留语义

本轮没有扩 scope 去全仓库删 mock，而是只清理**主路径误导语义**：

1. `D:\webstudy\FlagHunter\web\console\src\shell.jsx`
   - 去掉不再使用的 `MOCK` global 声明

2. `D:\webstudy\FlagHunter\web\console\index.html`
   - 把 “API layer falls back to MOCK” 改成更准确的 live probe / SSE 语义
   - 明确 `mock.js` 只是 developer support，不是主流程 truth source

---

## 4. 当前仍不在本轮范围内的内容

本轮没有把以下内容当成必须解决项：

1. `traces.jsx` / `knowledge.jsx` 的更广泛仓库级 mock 退休
2. 更高阶的 continue / retry 后端合同落地
3. 新的前端测试基座建设
4. 整个 `docs/web-console/` 历史阶段文档体系重构

也就是说，本轮是 **Phase 1 主流程收尾**，不是新的大阶段启动。

---

## 5. 下一步建议

如果继续沿这条主线推进，最合理的是：

1. 以当前代码 + 当前计划文档为准，不再按旧 planning 文档猜状态
2. 把非主路径页面的 mock 退休单独列为后续事项
3. 若要继续做体验优化，应优先关注：
   - detail 区信息密度
   - analysis 面板层级
   - disabled action 的解释性文案

---

## 6. 最终判断

从“当前是否还需要回头重做任务详情布局”的角度看：

> **不需要。**

从“当前是否已经进入 Phase 1 收尾与 fresh verify 阶段”的角度看：

> **是。**

因此，本轮复核结论可以压缩成一句话：

> **任务详情过窄问题已不再是当前主阻塞；Phase 1 主流程已真值化并通过 fresh smoke，当前进入计划对齐、语义清理和验收留痕阶段。**
