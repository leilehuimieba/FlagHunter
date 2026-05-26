# FlagHunter Web 可视化控制台前端原型拆解与组件树规范 V1

- 文档版本：V1
- 编写日期：2026-05-26
- 适用项目：FlagHunter
- 目的：给前端实现 agent 提供页面拆解、组件树、Mock 数据组织和实施边界

---

# 1. 文档目标

本文档用于补足前两份方案文档中“可以做什么”和“接口长什么样”之外的内容，进一步明确：
- 每个页面应该拆成哪些模块
- 各模块建议有哪些组件
- 前端目录应该如何组织
- Mock 数据应该如何存放
- 哪些组件应该先做、哪些后做
- 如何在不接真实后端的情况下完成高质量演示版

本文档不涉及具体代码实现，但要求前端实现严格参考本文档的结构化拆分。

---

# 2. 总体实施原则

## 2.1 先组件树，后页面细节

要求前端 agent 不要先“拼页面”，而是先建立稳定组件层级：
- Layout 层
- Feature 层
- Domain 组件层
- Shared 基础组件层
- Data adapters 层

## 2.2 Mock-first，但结构必须真实

Mock 数据不是临时乱写，而是：
- 命名与未来 API 返回结构一致
- 类型与未来真实接口一致
- 一个 service 对应一个 mock adapter
- 前端页面永远不直接读 mock JSON 文件

## 2.3 优先做高价值页面

推荐实现顺序：
1. Console Shell
2. Dashboard
3. Tasks
4. Trace
5. Logs
6. Knowledge
7. Settings

---

# 3. 推荐前端工程目录

```text
web-console/
  app/
    (console)/
      dashboard/
        page.tsx
      tasks/
        page.tsx
        [taskId]/
          page.tsx
      traces/
        page.tsx
        [runId]/
          page.tsx
      knowledge/
        page.tsx
        [docId]/
          page.tsx
      logs/
        page.tsx
      settings/
        page.tsx
      layout.tsx
    globals.css
    layout.tsx

  src/
    components/
      layout/
      dashboard/
      tasks/
      traces/
      knowledge/
      logs/
      settings/
      shared/

    features/
      dashboard/
      tasks/
      traces/
      knowledge/
      logs/
      settings/

    lib/
      api/
        types.ts
        client.ts
        mock/
        services/
      stores/
      utils/
      formatters/
      constants/

    hooks/

    mock/
      fixtures/
      generators/
      scenarios/
```

说明：
- `app/`：只放页面入口与布局，不堆业务逻辑
- `components/`：放可复用 UI 组件
- `features/`：放页面级业务组合
- `lib/api/mock/`：放 mock adapter
- `mock/scenarios/`：放演示用场景数据组合

---

# 4. 全局布局组件树

## 4.1 Console Shell 组件树

```text
ConsoleShell
  ├─ AppSidebar
  │   ├─ SidebarBrand
  │   ├─ SidebarNav
  │   └─ SidebarRuntimeBadge
  ├─ Topbar
  │   ├─ GlobalSearch
  │   ├─ CurrentRuntimeIndicator
  │   ├─ NotificationBell
  │   └─ ThemeToggle
  ├─ MainContentOutlet
  └─ GlobalCommandPalette
```

## 4.2 首期必须实现
- 左侧导航
- 顶部全局状态栏
- 主体内容区
- 深色主题
- 页面 loading / empty / error 框架

## 4.3 可后做
- 全局命令面板
- 多工作区切换
- 快捷键总览

---

# 5. Dashboard 页面拆解

## 5.1 页面模块

```text
DashboardPage
  ├─ DashboardHeader
  ├─ KpiGrid
  │   ├─ RunningTasksCard
  │   ├─ DailyTokensCard
  │   ├─ EstimatedCostCard
  │   ├─ SuccessRateCard
  │   ├─ RuntimeCard
  │   └─ ToolCallsCard
  ├─ DashboardChartsSection
  │   ├─ TokenTrendChart
  │   ├─ ToolDistributionChart
  │   ├─ FailureDistributionChart
  │   └─ KnowledgeHitTrendChart
  ├─ DashboardActivitySection
  │   ├─ RecentTasksPanel
  │   ├─ RecentToolCallsPanel
  │   ├─ RecentNotesPanel
  │   └─ RecentArtifactsPanel
  └─ DashboardAlertsSection
```

## 5.2 页面展示目标
- 一眼看全局
- 不要求操作复杂
- 首屏信息密度高但不混乱

## 5.3 首期建议组件优先级
### P0
- KpiGrid
- TokenTrendChart
- RecentTasksPanel
- RecentToolCallsPanel

### P1
- FailureDistributionChart
- RecentNotesPanel
- RecentArtifactsPanel

### P2
- AlertsSection
- Runtime health panel

---

# 6. Tasks 页面拆解

## 6.1 任务列表页组件树

```text
TasksPage
  ├─ TasksHeader
  ├─ TaskToolbar
  │   ├─ TaskSearchInput
  │   ├─ TaskStatusFilter
  │   ├─ TaskTypeFilter
  │   └─ CreateTaskButton
  ├─ CreateTaskDialog
  ├─ TaskList
  │   ├─ TaskListItem
  │   ├─ TaskStatusBadge
  │   ├─ TaskRuntimeBadge
  │   └─ TaskQuickActions
  └─ TaskPagination
```

## 6.2 任务详情页组件树

```text
TaskDetailPage
  ├─ TaskDetailHeader
  │   ├─ TaskTitle
  │   ├─ TaskStatusBadge
  │   ├─ TaskActionButtons
  │   └─ TaskMetaSummary
  ├─ TaskDetailBody
  │   ├─ TaskConversationPanel
  │   │   ├─ MessageList
  │   │   ├─ MessageBubble
  │   │   ├─ TaskComposer
  │   │   └─ AddHintComposer
  │   └─ TaskSidePanel
  │       ├─ CurrentPlanCard
  │       ├─ CurrentStrategyCard
  │       ├─ CurrentToolCard
  │       ├─ ObservationFeedCard
  │       ├─ KnowledgeHitsCard
  │       ├─ NotesCard
  │       └─ ArtifactsCard
  └─ TaskDetailFooter
```

## 6.3 详情页核心要求
- 左边像会话，中间偏内容，右边偏状态
- 右侧必须是实时感强的状态板
- “加 hint”必须是独立交互，不要埋进普通对话输入

## 6.4 首期优先级
### P0
- TaskList
- CreateTaskDialog
- TaskConversationPanel
- CurrentPlanCard
- CurrentToolCard
- ObservationFeedCard

### P1
- KnowledgeHitsCard
- NotesCard
- ArtifactsCard
- Retry/Stop 按钮

### P2
- Fork/Rewind 样式交互
- 多 run 切换

---

# 7. Trace 页面拆解

## 7.1 Trace 列表页组件树

```text
TracesPage
  ├─ TracesHeader
  ├─ TraceToolbar
  │   ├─ TraceSearchInput
  │   ├─ TraceStatusFilter
  │   ├─ TraceDateFilter
  │   └─ TraceViewModeToggle
  ├─ TraceTable
  └─ TracePagination
```

## 7.2 Trace 详情页组件树

```text
TraceDetailPage
  ├─ TraceHeader
  │   ├─ TraceMetaSummary
  │   ├─ TraceStatusBadge
  │   └─ TraceActions
  ├─ TraceViewTabs
  │   ├─ TimelineTab
  │   │   └─ TraceTimeline
  │   │       ├─ TimelineEventItem
  │   │       └─ EventDetailDrawer
  │   ├─ GraphTab
  │   │   └─ TraceGraphView
  │   └─ DataTab
  │       ├─ TraceStepsTable
  │       ├─ ToolCallsTable
  │       ├─ KnowledgeHitsTable
  │       ├─ NotesTable
  │       ├─ ArtifactsTable
  │       └─ FileChangesTable
  └─ TraceBottomInspector
```

## 7.3 Trace 详情页实现建议
- Timeline 与 Graph 不要一开始强耦合
- 先把 Timeline 做扎实，再补 Graph
- Graph 只展示关键节点，不要一开始就做成超复杂 DAG

## 7.4 首期优先级
### P0
- TimelineTab
- ToolCallsTable
- EventDetailDrawer

### P1
- GraphTab
- NotesTable
- KnowledgeHitsTable

### P2
- FileChanges diff 展示
- Step replay 模式

---

# 8. Knowledge 页面拆解

## 8.1 知识列表页组件树

```text
KnowledgePage
  ├─ KnowledgeHeader
  ├─ KnowledgeToolbar
  │   ├─ KnowledgeSearchInput
  │   ├─ KnowledgeTypeFilter
  │   ├─ KnowledgeTagFilter
  │   └─ KnowledgeSortSelect
  ├─ KnowledgeTable
  └─ KnowledgeStatsPanel
```

## 8.2 文档详情页组件树

```text
KnowledgeDetailPage
  ├─ KnowledgeDocHeader
  ├─ KnowledgeDocMetaCard
  ├─ KnowledgeDocContentTabs
  │   ├─ OverviewTab
  │   ├─ ChunksTab
  │   ├─ HitHistoryTab
  │   └─ RelatedRunsTab
  └─ ChunkPreviewPanel
```

## 8.3 首期优先级
### P0
- KnowledgeTable
- OverviewTab
- ChunksTab

### P1
- HitHistoryTab
- RelatedRunsTab

### P2
- 图谱视图

---

# 9. Logs 页面拆解

## 9.1 组件树

```text
LogsPage
  ├─ LogsHeader
  ├─ LogsToolbar
  │   ├─ LogSearchInput
  │   ├─ LogLevelFilter
  │   ├─ LogSourceFilter
  │   ├─ LogTaskFilter
  │   └─ LiveModeToggle
  ├─ LogsViewTabs
  │   ├─ TableTab
  │   │   └─ LogsTable
  │   └─ TerminalTab
  │       └─ TerminalStreamPanel
  └─ LogDetailDrawer
```

## 9.2 首期优先级
### P0
- LogsTable
- Log filters
- LogDetailDrawer

### P1
- TerminalStreamPanel
- LiveModeToggle

---

# 10. Settings 页面拆解

## 10.1 组件树

```text
SettingsPage
  ├─ SettingsHeader
  ├─ SettingsTabs
  │   ├─ ModelSettingsTab
  │   ├─ RuntimeSettingsTab
  │   ├─ MCPSettingsTab
  │   ├─ KnowledgeSettingsTab
  │   ├─ BudgetSettingsTab
  │   └─ AuditSettingsTab
  ├─ SettingsSaveBar
  └─ SettingsTestPanel
```

## 10.2 首期优先级
### P0
- ModelSettingsTab
- RuntimeSettingsTab
- KnowledgeSettingsTab
- SaveBar

### P1
- MCPSettingsTab
- BudgetSettingsTab
- AuditSettingsTab

---

# 11. Shared 通用组件建议

建议抽出以下共享组件：

```text
shared/
  StatusBadge
  MetricCard
  SectionCard
  EmptyState
  ErrorState
  LoadingState
  TimestampText
  JsonPreview
  CodeBlock
  CopyButton
  SearchInput
  FilterSelect
  KeyValueList
  DetailDrawer
  DataTableShell
  TimelineShell
  RuntimeBadge
  ToolBadge
  TokenUsageBadge
```

这些组件应优先通用化，避免每页重复写。

---

# 12. Mock 数据目录规范

## 12.1 推荐目录

```text
src/lib/api/mock/
  dashboard.mock.ts
  tasks.mock.ts
  traces.mock.ts
  knowledge.mock.ts
  logs.mock.ts
  settings.mock.ts

src/mock/fixtures/
  dashboard.fixture.ts
  tasks.fixture.ts
  traces.fixture.ts
  knowledge.fixture.ts
  logs.fixture.ts
  settings.fixture.ts

src/mock/scenarios/
  wal_recover.scenario.ts
  running_task.scenario.ts
  failed_task.scenario.ts
  knowledge_hit.scenario.ts
```

## 12.2 分层建议

### fixture
放基础静态数据块，例如：
- 单个 TaskRecord
- 单个 ToolCallRecord
- 单个 KnowledgeHitRecord

### scenario
放“演示场景组合”，例如：
- 一个成功的 wal_recover run
- 一个失败的 web 题 run
- 一个运行中的长任务

### mock service
对外暴露和未来真实 API 一样的函数，例如：
- `getTasks()`
- `getTaskDetail(taskId)`
- `getTrace(runId)`

---

# 13. 建议至少准备的 Mock 场景

前端为了做出真实感，至少要有以下 Mock 场景：

## 13.1 场景 A：运行中的任务
- status = running
- 正在调用 tool
- 正在增长 logs
- 右侧 plan/strategy/tool 正在变化

## 13.2 场景 B：成功的附件题任务
建议直接用 `wal_recover` 风格数据：
- detectedType = misc
- strategy = artifact_forensics
- tool = terminal
- artifact = app.db-wal
- verified flag = true

## 13.3 场景 C：失败任务
- 多次 tool failed
- recovery stop
- stopReason = no progress

## 13.4 场景 D：知识命中明显的任务
- 有多个 knowledge hits
- Knowledge 页面能从该任务反查文档

## 13.5 场景 E：配置编辑
- 修改 runtime / model / rag threshold
- 模拟保存成功

---

# 14. 页面原型表现建议

## 14.1 Dashboard
风格应偏“总览型”：
- 2 行 KPI
- 2 行图表
- 右侧或底部 recent activity

## 14.2 Tasks
风格应偏“工作台”：
- 左窄中宽右中等
- 中间对话区最大
- 右侧是 agent 实时面板

建议布局比例：
- 左：20%
- 中：50%
- 右：30%

## 14.3 Trace
风格应偏“调试台”：
- 上面 meta
- 中间 tabs
- Timeline 默认打开

## 14.4 Knowledge
风格应偏“资源台账”：
- 表格主导
- 详情用 tabs

## 14.5 Logs
风格应偏“运维面板”：
- 上面过滤器
- 下面大表格
- 可切换 terminal 模式

---

# 15. 组件优先级清单

## P0：必须先有
- ConsoleShell
- AppSidebar
- Topbar
- MetricCard
- DataTableShell
- StatusBadge
- LoadingState / EmptyState / ErrorState
- Dashboard 基础卡片
- TaskList
- TaskDetail 基础布局
- Timeline 基础列表
- LogsTable
- Settings 表单基础布局

## P1：第二阶段补齐
- TraceGraphView
- xterm TerminalStreamPanel
- Knowledge detail tabs
- Notes / Artifacts 可视化卡片
- EventDetailDrawer

## P2：高级体验
- Diff 视图
- 拖拽布局
- 图谱视图
- 全局命令面板
- 任务回放动画

---

# 16. 前端状态管理建议

## 16.1 Query 负责 server state
适合交给 TanStack Query：
- tasks 列表
- task detail
- dashboard summary
- traces list/detail
- knowledge list/detail
- logs list
- settings data

## 16.2 Zustand 负责 UI state
适合交给 Zustand：
- 当前选中的 taskId
- 当前选中的 runId
- 当前 Trace tab
- 过滤器状态
- 右侧 side panel 展开状态
- terminal live mode 开关
- theme 偏好

---

# 17. 前端交付顺序建议

## Sprint 1
- ConsoleShell
- Dashboard 基础版
- Tasks 列表页
- 公共组件底座

## Sprint 2
- Task 详情页
- Add Hint 交互
- Logs 基础页

## Sprint 3
- Trace 时间线页
- Tool call 详情
- Knowledge 列表页

## Sprint 4
- Knowledge 详情页
- Settings 页
- Graph 视图初版

## Sprint 5
- polish
- loading/error/empty 全覆盖
- 深色主题细节
- 假数据演示打磨

---

# 18. 验收建议

## 18.1 页面原型验收
- 页面结构完整
- 视觉层次清晰
- 信息密度合理
- 页面间导航顺畅

## 18.2 组件化验收
- 重复组件已抽离
- 表格与卡片风格统一
- 状态组件统一

## 18.3 Mock 验收
- 至少 5 个场景可切换
- 页面不直接依赖硬编码静态对象
- mock service 与未来真实 API 签名一致

## 18.4 可接入性验收
- 后端替换时只改 adapter，不重写页面
- 事件流可无缝挂接到 Trace/Logs/Tasks

---

# 19. 结论

这第三份文档的核心不是“画页面”，而是确保前端实现 agent 有一套可落地的拆解方式：
- 知道先做哪些组件
- 知道页面如何分层
- 知道 mock 数据放哪里
- 知道后续如何替换真实后端

最重要的一点：

> 前端先做成一个结构正确、体验完整、接口预留清晰的控制台，再去接真实后端。

这样后续协调适配成本最低。
