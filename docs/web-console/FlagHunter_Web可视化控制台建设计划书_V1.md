# FlagHunter Web 可视化控制台建设计划书 V1

- 文档版本：V1
- 编写日期：2026-05-26
- 适用项目：FlagHunter
- 定位：单人本地使用的 Web 可视化控制台建设方案

---

# 1. 文档目的

本文档用于为 FlagHunter 项目的前端可视化控制台建设提供统一规划。

本文档不包含具体代码实现，而是用于指导：
- 前端实现 agent
- 后端适配 agent
- 你本人进行阶段验收与方向控制

本文档明确以下内容：
- 为什么要做 Web 控制台
- 首期做什么，不做什么
- 推荐技术栈与原因
- 页面规划
- 核心数据与事件建设要求
- Mock 数据优先的开发路线
- 分阶段验收标准

---

# 2. 项目背景

FlagHunter 当前已有较强的 agent 执行能力，具备：
- TUI / CLI / MCP 的交互入口
- LocalRuntime / DockerRuntime / SSHRuntime
- knowledge / RAG / strategy memory / notes / retrospective
- CTF dispatcher / hypothesis / strategy / verifier / recovery 主干
- token usage tracking

但当前主要问题是：

1. 可见性不够
   - 能执行，但不容易实时看清 agent 正在做什么
2. 复盘成本高
   - 工具调用、知识引用、写入记录、失败原因分散在多个位置
3. 演示与调试体验弱
   - TUI 适合开发者，不适合长期监控和可视化分析
4. 前后端尚未解耦
   - 还没有专门为 Web UI 准备统一 API 与事件模型

因此需要建设一套：

> FlagHunter Web 可视化控制台

它的目标不是替代现有 agent 主体，而是把项目已有能力产品化、透明化、可追溯化。

---

# 3. 使用场景定位

当前阶段明确假设：
- 只有你一个人使用
- 本地优先
- 不考虑多租户
- 不优先考虑复杂权限系统
- 先前端完成，再逐步接后端真实数据

因此本控制台首期应采用：

> 单用户、本地优先、Mock 数据驱动、后端接口预留完善

这意味着：
- 前端先把 UI 结构与交互体验做完整
- 同时约定好 API contract 与事件 schema
- 后续再由后端逐步把真实数据接进来

---

# 4. 建设目标

## 4.1 总目标

建设一个面向 FlagHunter 的可视化 Web 控制台，用于：
- 看全局运行态
- 与 agent 交互下发任务
- 观察 agent 执行链路
- 查看知识库与记忆系统
- 查看日志和最近调用情况
- 管理配置

## 4.2 首期目标

首期目标不是把所有后端都接通，而是：

1. 把页面结构搭起来
2. 用高质量 Mock 数据把交互效果做完整
3. 预留稳定、可扩展的 API 接口
4. 为后续后端接入降低成本

---

# 5. 非目标

以下内容不作为当前首期目标：

- 不做多租户
- 不做复杂 RBAC
- 不做云原生 SaaS 化部署
- 不重写现有 agent 主体
- 不一次性接通所有后端真实能力
- 不首期做移动端优先

---

# 6. 产品定位

建议将该系统定位为：

> FlagHunter Mission Control / Web 可视化控制台

不是单纯聊天 UI，而是：
- 控制台
- 任务面板
- 可观测平台
- 知识与记忆查看器
- 调试与复盘工作台

---

# 7. 推荐技术栈

## 7.1 前端技术栈

### 核心框架
- Next.js（App Router）
- React
- TypeScript

### 样式与组件
- Tailwind CSS
- shadcn/ui

### 状态与数据层
- TanStack Query
- Zustand

### 可视化组件
- Apache ECharts
- React Flow
- xterm.js
- Monaco Editor
- Data Table（TanStack Table + shadcn/ui 封装）

## 7.2 为什么推荐这套

### Next.js + React + TypeScript
适合：
- 管理台结构化页面
- 多布局、多路由、多状态视图
- 客户端与服务端混合能力
- 对长期维护友好

### Tailwind + shadcn/ui
适合：
- 快速搭建高质量后台界面
- 统一设计语言
- 可组合性高
- 控制台类页面组件丰富

### TanStack Query
适合：
- 列表数据获取
- 详情页缓存
- 轮询
- 后续接真实 API 时状态管理简单

### Zustand
适合：
- 当前选中的 task / run / trace / filters
- UI 级本地状态
- 比把所有状态都塞进 Query 更清晰

### ECharts
适合：
- Dashboard KPI
- 调用分布图
- 耗时 / token / cost 趋势图

### React Flow
适合：
- 展示 agent 执行链
- 展示 Trace DAG
- 展示多步骤与多工具依赖关系

### xterm.js
适合：
- 日志页
- 终端输出
- 命令回放

### Monaco Editor
适合：
- 配置查看与编辑
- JSON / YAML / Prompt 展示
- 文件 diff 展示

---

# 8. 页面规划

建议首期主导航：

1. Dashboard
2. Agent / Tasks
3. Trace / Timeline
4. Knowledge
5. Logs
6. Settings

可后续扩展：
- Artifacts
- Memory
- Runtime

---

# 9. 页面详细规划

## 9.1 Dashboard

### 目标
展示项目总体状态。

### 展示内容
- 当前运行任务数
- 今日 token 使用
- 今日估算成本
- 最近成功/失败任务数
- 平均任务耗时
- Tool 调用 Top N
- 最近知识命中次数
- 最近写入 notes / memory / artifacts
- 当前 runtime 状态

### 预期效果
一眼看清：
- 系统忙不忙
- 最近稳定不稳定
- 成本高不高
- 当前是否有任务在跑

---

## 9.2 Agent / Tasks

### 目标
成为主操作页。

### 结构
- 左侧：任务列表
- 中间：聊天/任务交互区
- 右侧：实时状态面板

### 右侧实时状态面板建议展示
- 当前 plan
- 当前 hypothesis
- 当前 strategy
- 当前 tool call
- 当前 observation
- 当前 knowledge hits
- 当前 notes / artifacts

### 支持操作
- 发布任务
- 继续任务
- 停止任务
- 重试任务
- 插入补充提示
- 查看当前执行状态

### 预期效果
不是单纯聊天，而是“可看见 agent 在工作”。

---

## 9.3 Trace / Timeline

### 目标
完整展示一次 run 的执行过程。

### 展示方式
- 时间线模式
- 节点图模式

### 节点建议类型
- task started
- recon
- plan created
- hypothesis generated
- strategy selected
- tool called
- tool finished
- knowledge retrieved
- note written
- artifact written
- verifier result
- recovery decision
- task finished

### 预期效果
用户可以回答：
- 它为什么这么做
- 为什么失败
- 哪个步骤耗时最多
- 哪个步骤最消耗 token

---

## 9.4 Knowledge

### 目标
可视化展示项目知识系统。

### 展示内容
- 知识库列表
- 文档列表
- 文档详情
- chunk 信息
- 最近检索历史
- 本次任务引用了哪些知识
- 哪些知识命中最多

### 可选扩展
- 图谱视图
- 文档与策略的关联视图

---

## 9.5 Logs

### 目标
统一查看所有运行日志。

### 展示内容
- app logs
- tool logs
- runtime logs
- error logs
- 审计日志
- 最近调用记录

### 能力要求
- 搜索
- 过滤
- 分页
- 实时 tail
- 单条详情展开

---

## 9.6 Settings

### 目标
统一管理配置。

### 配置分组建议
- 模型配置
- Runtime 配置
- MCP 配置
- Knowledge / RAG 配置
- Token / Budget 配置
- 审计与可观测配置

### 注意
首期可以先只做：
- 展示配置
- 修改 UI
- 暂不真实提交

即先走 Mock 配置保存流程。

---

# 10. 核心实现原则

## 10.1 Mock 优先，不直接绑死后端

当前阶段应采用：

> 前端先按真实产品标准完成，数据用 Mock；后续再接真实 API。

### 原因
1. 前后端并行效率高
2. 不被当前后端结构限制住 UI 设计
3. 可以先验证交互体验
4. 便于后续逐步接入而非一次性重构

## 10.2 API 必须预留好

虽然首期用 Mock 数据，但所有页面都必须：
- 先定义接口类型
- 再写 Mock adapters
- 最后替换为真实 adapters

换句话说，前端不是直接绑 JSON 文件，而是：
- 面向 API contract 开发
- Mock 只是接口实现之一

## 10.3 单用户架构优先

因为你现在单人使用，所以：
- 不做多租户隔离
- 不做用户管理系统
- 不做组织/团队维度
- 只保留未来扩展接口即可

---

# 11. 核心后端配合要求

前端虽然先 Mock，但后端未来要适配这些接口，因此现在就要规划：

## 11.1 必须补统一事件模型

如果没有统一事件流，前端只能看静态结果，无法展示“agent 正在怎么做”。

建议后端统一这些事件：
- task.started
- task.finished
- agent.plan.created
- agent.plan.updated
- agent.hypothesis.generated
- agent.strategy.selected
- tool.called
- tool.finished
- tool.failed
- knowledge.retrieved
- note.created
- artifact.created
- file.created
- file.updated
- file.deleted
- memory.strategy.saved
- verifier.flag.candidate
- verifier.flag.verified
- recovery.chain.switched
- recovery.stopped

## 11.2 必须补结构化审计对象

至少统一抽象这些数据对象：
- Task
- Run
- Step
- ToolCall
- KnowledgeHit
- NoteEntry
- ArtifactEntry
- FileChange
- MemoryEntry
- LogEntry

---

# 12. 实施阶段规划

## Phase A：方案与接口定义

### 目标
不写页面实现细节，先把规范定下来。

### 输出
- 页面信息架构
- API contract
- 事件模型
- Mock 数据规范

### 验收
- 前端可以完全基于文档开始做
- 后端知道后续要提供什么

---

## Phase B：前端骨架 + Mock 数据

### 目标
完成 UI 框架与页面骨架。

### 内容
- 布局
- 路由
- 主题
- 导航
- API client 接口层
- Mock service
- 页面空态 / loading / error state

### 验收
- 所有主页面都能打开
- 所有页面都由 Mock 数据驱动

---

## Phase C：Dashboard + Logs

### 目标
先建立全局可见性。

### 验收
- 能看到指标
- 能看到日志
- 能看到最近活动

---

## Phase D：Agent / Tasks + Trace

### 目标
建立核心使用价值。

### 验收
- 能发布任务
- 能看任务详情
- 能看 Trace
- 能插入提示

---

## Phase E：Knowledge + Settings

### 目标
把知识系统与配置系统补齐。

### 验收
- 知识内容可见
- 设置界面可用

---

## Phase F：后端真实接入

### 目标
逐模块替换 Mock 数据。

### 顺序建议
1. Dashboard 数据
2. Logs 数据
3. Task 列表与详情
4. Trace 数据
5. Knowledge 数据
6. Settings 读写

### 验收
- Mock adapter 可被真实 adapter 无缝替换

---

# 13. 验收标准

## 13.1 功能验收

### Dashboard
- 有 KPI
- 有图表
- 有最近活动

### Agent / Tasks
- 能发布任务
- 能显示运行状态
- 能展示任务消息与状态面板

### Trace
- 能展示一步步时间线
- 能展示 tool 调用与结果摘要

### Knowledge
- 能展示知识库列表与详情

### Logs
- 能看日志、筛选、搜索、实时滚动

### Settings
- 能看配置项
- 能模拟修改流程

## 13.2 架构验收
- 前端所有数据都通过 service 层获取
- Mock 与真实 API 可替换
- 页面不直接耦合后端文件格式

## 13.3 体验验收
- 首屏打开快
- 导航清晰
- 信息密度合理
- 页面统一风格

---

# 14. 风险与应对

## 风险 1：只做成聊天壳
### 应对
Trace、ToolCall、KnowledgeHit、FileChange 必须是一等公民。

## 风险 2：后端事件太散
### 应对
先定义统一 schema，再做接入。

## 风险 3：Mock 做得太随意，后续无法替换
### 应对
Mock 必须严格遵守 API 类型定义。

## 风险 4：想一步到位，导致节奏失控
### 应对
按“Dashboard -> Agent/Trace -> Knowledge/Settings -> 真后端接入”推进。

---

# 15. 结论

这套 Web 控制台非常值得做。

对 FlagHunter 而言，它不是单纯做个前端，而是把现有：
- agent
- tools
- knowledge
- memory
- runtime
- logs
- retrospective

这些能力真正变成一个“可看、可调、可回放、可复盘”的系统。

当前最合理路线是：

> 先高质量做前端与接口规范，使用 Mock 数据完成 UI；随后再分层接入真实后端。

---

# 16. 参考资料

## 官方文档
- Next.js App Router: https://nextjs.org/docs/app
- TanStack Query: https://tanstack.com/query/docs/docs
- shadcn/ui Chart: https://ui.shadcn.com/docs/components/chart?trk=public_post_comment-text
- shadcn/ui Data Table: https://v3.shadcn.com/docs/components/data-table
- React Flow: https://reactflow.dev/
- React Flow API: https://reactflow.dev/api-reference/react-flow
- React Flow Examples: https://reactflow.dev/examples
- xterm.js: https://xtermjs.org/docs
- Monaco Editor: https://microsoft.github.io/monaco-editor/
- Apache ECharts: https://echarts.apache.org/handbook/en/get-started/

## 产品/设计参考
- Langfuse Overview: https://langfuse.com/docs?trk=public_post_main-feed-card-text
- Langfuse Data Model: https://langfuse.com/docs/observability/data-model
- Open WebUI Knowledge: https://docs.openwebui.com/features/workspace/knowledge/
- Cogpit: https://cogpit.dev/
- Mission Control: https://mc.builderz.dev/
- pi-dashboard: https://pi-dashboard.dev/
- Agent Prism: https://github.com/evilmartians/agent-prism
