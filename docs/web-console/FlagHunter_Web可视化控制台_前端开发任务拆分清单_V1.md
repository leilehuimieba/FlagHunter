# FlagHunter Web 可视化控制台前端开发任务拆分清单 V1

- 文档版本：V1
- 编写日期：2026-05-26
- 适用项目：FlagHunter
- 用途：可直接交给前端实现 agent 执行

---

# 1. 文档目标

本文档将前端可视化控制台的建设工作拆成：
- 可执行任务
- 任务顺序
- 每项输入输出
- 验收标准
- 依赖关系

要求前端实现 agent 按任务推进，而不是自由发挥式实现。

---

# 2. 总体执行原则

1. 先搭骨架，再补页面
2. 先 Mock 数据，再接真实后端
3. 先高价值页面，再补高级可视化
4. 每阶段都必须可运行、可演示、可验收
5. 页面逻辑必须通过 service 层获取数据，不允许页面直连 mock 文件

---

# 3. 总任务分期

- Phase 0：前端工程初始化与规范落地
- Phase 1：Console Shell 与基础共享组件
- Phase 2：Dashboard 首版
- Phase 3：Tasks 列表与详情页首版
- Phase 4：Trace / Timeline 首版
- Phase 5：Logs 首版
- Phase 6：Knowledge 首版
- Phase 7：Settings 首版
- Phase 8：Mock 场景增强与交互打磨
- Phase 9：后端接入预留检查与交付收口

---

# 4. Phase 0：前端工程初始化与规范落地

## 4.1 任务目标
建立独立、可维护、可扩展的前端工程基础。

## 4.2 任务项

### T0-1 创建前端工程
- 技术栈：Next.js + React + TypeScript + Tailwind
- 建立 `web-console/` 子工程

#### 输入
- 三份规划文档

#### 输出
- 可运行的前端工程

#### 验收
- `npm run dev` 可启动
- 首页可访问

---

### T0-2 引入基础依赖
- shadcn/ui
- TanStack Query
- Zustand
- ECharts
- React Flow
- xterm.js
- Monaco Editor（可先预留）

#### 输出
- 依赖安装完成
- 无类型报错

#### 验收
- 基础依赖已纳入工程
- 项目能正常编译

---

### T0-3 建立基础目录结构

#### 必建目录
```text
app/
src/components/
src/features/
src/lib/api/
src/lib/stores/
src/mock/
```

#### 验收
- 目录结构符合规划文档
- 无“所有代码都堆 page.tsx”情况

---

### T0-4 建立全局类型与 API 基础层

#### 内容
- 创建 `src/lib/api/types.ts`
- 创建 `src/lib/api/client.ts`
- 创建 `src/lib/api/services/`
- 创建 `src/lib/api/mock/`

#### 验收
- 至少存在 1 个 service + 1 个 mock adapter 示例

---

### T0-5 建立基础设计令牌

#### 内容
- 字体
- 间距
- 圆角
- 色板
- 状态色
- 深色主题

#### 验收
- 有统一 theme 基础
- 后续页面不重复自定义大量颜色

---

# 5. Phase 1：Console Shell 与共享组件

## 5.1 任务目标
先完成控制台骨架与共享 UI 底座。

## 5.2 任务项

### T1-1 实现 ConsoleShell 布局

#### 包含组件
- AppSidebar
- Topbar
- MainContentOutlet

#### 验收
- 所有主路由都挂在 ConsoleShell 下
- 左侧导航与顶部栏稳定显示

---

### T1-2 实现 Sidebar 导航

#### 页面入口
- Dashboard
- Tasks
- Traces
- Knowledge
- Logs
- Settings

#### 验收
- 每个页面都有导航入口
- 当前路由高亮正常

---

### T1-3 实现共享状态组件

#### 组件
- LoadingState
- EmptyState
- ErrorState
- StatusBadge
- RuntimeBadge
- MetricCard
- SectionCard

#### 验收
- 后续页面直接复用
- 不重复造相同状态 UI

---

### T1-4 实现共享数据展示组件

#### 组件
- DataTableShell
- SearchInput
- FilterSelect
- TimestampText
- JsonPreview
- DetailDrawer

#### 验收
- 至少被一个示例页使用

---

# 6. Phase 2：Dashboard 首版

## 6.1 任务目标
完成首页仪表盘的第一版演示。

## 6.2 任务项

### T2-1 实现 Dashboard 页面骨架

#### 模块
- DashboardHeader
- KpiGrid
- ChartsSection
- ActivitySection

#### 验收
- 页面有完整结构
- 不空白

---

### T2-2 实现 KPI 卡片

#### 数据
- runningTasks
- dailyTokens
- estimatedCost
- successToday
- toolCallsToday
- activeRuntime

#### 验收
- 所有 KPI 正常展示
- 数字格式统一

---

### T2-3 实现图表区域

#### 图表
- TokenTrendChart
- ToolDistributionChart
- FailureDistributionChart

#### 验收
- 3 张图可见
- 支持 mock 数据更新

---

### T2-4 实现最近活动区

#### 面板
- RecentTasksPanel
- RecentToolCallsPanel
- RecentNotesPanel

#### 验收
- 最近活动有数据
- 布局清晰

---

# 7. Phase 3：Tasks 列表与详情页首版

## 7.1 任务目标
完成主任务工作台。

## 7.2 任务项

### T3-1 实现 Tasks 列表页

#### 功能
- 列表展示
- status filter
- keyword search
- create task 按钮

#### 验收
- 可以看到任务列表
- 筛选与搜索有效

---

### T3-2 实现 CreateTaskDialog

#### 字段
- title
- target
- goal
- type
- hint

#### 验收
- 可提交 mock 创建
- 创建后列表刷新

---

### T3-3 实现 Task 详情页骨架

#### 结构
- Header
- ConversationPanel
- SidePanel

#### 验收
- 布局完整
- 左中右结构清晰

---

### T3-4 实现 ConversationPanel

#### 功能
- 用户消息展示
- agent 消息展示
- 输入框
- 补 hint 输入框

#### 验收
- 消息流展示自然
- 加 hint 有 mock 反馈

---

### T3-5 实现 SidePanel

#### 卡片
- CurrentPlanCard
- CurrentStrategyCard
- CurrentToolCard
- ObservationFeedCard
- NotesCard
- ArtifactsCard

#### 验收
- 至少 4 个卡片有内容
- 页面能体现“agent 正在工作”

---

### T3-6 实现详情页动作按钮

#### 按钮
- Retry
- Stop
- Continue
- Add Hint

#### 验收
- 有 mock 行为闭环
- UI 状态变化明确

---

# 8. Phase 4：Trace / Timeline 首版

## 8.1 任务目标
把 agent 执行过程可视化。

## 8.2 任务项

### T4-1 实现 Trace 列表页

#### 功能
- trace 列表
- status filter
- 搜索

#### 验收
- 列表可进入详情页

---

### T4-2 实现 Trace 详情页

#### 模块
- TraceHeader
- Tabs
- TimelineTab
- DataTab

#### 验收
- 页面结构完整

---

### T4-3 实现 TimelineTab

#### 功能
- 时间线事件列表
- 事件详情抽屉

#### 验收
- 至少支持展示 tool.called / tool.finished / knowledge.retrieved / verifier.flag.verified

---

### T4-4 实现 DataTab

#### 表格
- StepsTable
- ToolCallsTable
- KnowledgeHitsTable
- NotesTable

#### 验收
- 每张表都有 mock 数据

---

### T4-5 实现 GraphTab 初版

#### 内容
- 用 React Flow 展示 run -> strategy -> tool -> verifier 的简化图

#### 验收
- 能显示基础节点图
- 不要求首版复杂布局算法

---

# 9. Phase 5：Logs 首版

## 9.1 任务目标
完成日志工作台。

## 9.2 任务项

### T5-1 实现 Logs 页面骨架
- Header
- Toolbar
- Tabs
- Table

### T5-2 实现 LogsTable

#### 字段
- timestamp
- level
- source
- taskId
- runId
- message

#### 验收
- 可排序/筛选/搜索

### T5-3 实现 LogDetailDrawer

#### 验收
- 点一条日志可看详情 payload

### T5-4 实现 TerminalTab（可后做）

#### 验收
- 能展示 mock 流式文本

---

# 10. Phase 6：Knowledge 首版

## 10.1 任务目标
完成知识库管理展示页面。

## 10.2 任务项

### T6-1 实现 Knowledge 列表页

#### 字段
- title
- sourcePath
- type
- chunkCount
- hitCount
- updatedAt

#### 验收
- 列表可浏览、筛选、搜索

---

### T6-2 实现 Knowledge 详情页

#### Tab
- Overview
- Chunks
- HitHistory
- RelatedRuns

#### 验收
- 至少前两项完整可看

---

### T6-3 实现 ChunkPreviewPanel

#### 验收
- 点 chunk 能看内容预览

---

# 11. Phase 7：Settings 首版

## 11.1 任务目标
完成配置管理页。

## 11.2 任务项

### T7-1 实现 Settings 页骨架
- Tabs
- SaveBar
- Form sections

### T7-2 实现基础配置页签

#### 页签
- Model
- Runtime
- Knowledge

#### 验收
- 表单可编辑
- mock 保存成功

### T7-3 扩展配置页签

#### 页签
- MCP
- Budget
- Audit

#### 验收
- 可展示结构
- 可以后续逐步细化

---

# 12. Phase 8：Mock 场景增强与交互打磨

## 12.1 任务目标
让演示版更像真实系统。

## 12.2 任务项

### T8-1 补 5 个核心场景
- 运行中的任务
- 成功的 wal_recover 风格任务
- 失败任务
- 知识高命中任务
- 配置编辑任务

### T8-2 增加场景切换能力

#### 形式
- dev-only 场景切换面板
- query param 场景切换

### T8-3 打磨 loading/empty/error

#### 验收
- 各页面状态完整
- 不出现白屏/空白卡片

### T8-4 打磨视觉一致性

#### 验收
- 卡片风格一致
- 表格风格一致
- 深色主题细节一致

---

# 13. Phase 9：后端接入预留检查与交付收口

## 13.1 任务目标
确保前端可以无痛接后端。

## 13.2 任务项

### T9-1 检查 service 层是否完整

#### 验收
- 每个页面只依赖 service，不直接依赖 mock 文件

### T9-2 检查 types 是否稳定

#### 验收
- API 类型集中定义
- 页面不定义重复类型

### T9-3 检查 mock adapter / future real adapter 边界

#### 验收
- mock adapter 可单独替换

### T9-4 输出对接清单

#### 需要补一份简短交付物
- 哪些 API 已预留
- 哪些事件已预留
- 后端优先接什么

---

# 14. 推荐执行顺序（可直接给前端 agent）

按下面顺序做：

1. T0-1 ~ T0-5
2. T1-1 ~ T1-4
3. T2-1 ~ T2-4
4. T3-1 ~ T3-6
5. T4-1 ~ T4-5
6. T5-1 ~ T5-4
7. T6-1 ~ T6-3
8. T7-1 ~ T7-3
9. T8-1 ~ T8-4
10. T9-1 ~ T9-4

---

# 15. 每阶段交付要求

## 每个 Phase 完成后必须满足
- 可运行
- 可演示
- 无明显报错
- 有最小验收记录
- 不破坏前序页面

## 每个 Phase 都要产出
- 完成项清单
- 未完成项清单
- 风险/阻塞项
- 下一步建议

---

# 16. 给前端实现 agent 的执行限制

1. 不允许跳过基础目录与 service 层直接堆页面
2. 不允许页面直接读取 mock fixture
3. 不允许先做复杂动画而跳过功能主链
4. 不允许把所有页面状态塞进单一 store
5. 不允许把类型定义散落多个页面文件
6. 不允许在没有统一组件基础前大量复制粘贴卡片/表格 UI

---

# 17. 最小验收清单

## MVP 验收必须包含
- Dashboard 可展示
- Tasks 列表与详情可展示
- Trace 时间线可展示
- Logs 可展示
- Knowledge 可展示
- Settings 可展示
- Mock 场景至少 3 个
- 有统一导航与深色主题

---

# 18. 结论

这份任务拆分清单的目标是：

> 让前端实现 agent 拿到后，不需要再重新理解项目背景，就能按阶段稳定推进。

最关键的是：
- 先搭骨架
- 再做页面
- 用 Mock 先跑通
- 最后平滑接后端

这样返工最少，控制力最强。
