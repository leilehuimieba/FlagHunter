# Cairn 源码深度分析（围绕 Blackboard / Dispatcher / Worker Runtime）V1

> 目标仓库：`D:\newwork\tmp\Cairn`
>
> 远端来源：[oritera/Cairn](https://github.com/oritera/Cairn)
>
> 本次分析基线：本地克隆仓库当前 `HEAD = 4939e8a`
>
> 文档用途：
>
> 1. 解释 Cairn 的真实代码结构，而不是只复述 README；
> 2. 说明它为什么能把“AI 渗透 / CTF / 通用状态空间搜索”收敛成一套较稳的工程主干；
> 3. 提炼出对我们现有项目真正可复用的部分。

---

## 1. 结论先行

如果只用一句话概括 Cairn 当前的源码实现，我的判断是：

> **Cairn 的核心不是“更聪明的单个 agent”，而是“一个非常薄的真相源 Server + 一个很强的 Dispatcher + 一组被严格协议化的 Worker CLI 适配层”。**

这套实现最关键的地方有 6 个：

1. **Server 不负责推理，只负责维护图真相**：Project / Fact / Intent / Hint / reason lease 都由服务端保存，且以 SQLite 为唯一持久层。[源码 C3][源码 C4][源码 C5][源码 C6][源码 C7][源码 C8]
2. **Dispatcher 是唯一写协议的人**：Worker 不直接调用 Cairn API，不 claim intent，不 heartbeat，不 conclude；Worker 只接 prompt，回结构化 JSON，真正的协议写回由 Dispatcher 完成。[源码 C10][源码 C14][源码 C15][源码 C16][文档 D1]
3. **任务被强收敛成三类**：`bootstrap / reason / explore`，这使得所有调度、超时、容器、心跳、fallback 都可以围绕有限状态实现，而不会被 prompt 自由漂移拖垮。[源码 C14][源码 C15][源码 C16][源码 C17]
4. **图状态与 prompt 上下文分离**：调度逻辑读结构化 API，prompt 构造读 `export?format=yaml` 快照；也就是说“系统真相”和“模型输入快照”被明确区分开了。[源码 C8][源码 C10][源码 C14][文档 D1]
5. **运行时治理比模型本身更重要**：健康检查、lease heartbeat、取消、容器生命周期、worker 短暂拉黑、project inactive 时强停止，这些都已经是源码主干的一部分，而不是边缘补丁。[源码 C11][源码 C12][源码 C13][源码 C14]
6. **它不是一个“通用 agent 框架外壳包裹任意逻辑”，而是一个针对状态图搜索被强约束过的 runtime**。这也是它比很多“会调用工具的大模型”更稳定的根因。

---

## 2. 仓库结构：Cairn 不是大而全，而是非常刻意地窄

根目录里真正关键的部分并不多：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\server`
- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher`
- `D:\newwork\tmp\Cairn\dispatch.yaml`
- `D:\newwork\tmp\Cairn\dispatch_mock.yaml`
- `D:\newwork\tmp\Cairn\docs\specs\dispatcher-design.md`
- `D:\newwork\tmp\Cairn\docs\specs\server-protocol.md`

从 `README.md` 也能看出来，作者在设计上故意把系统拆成三块：

1. **Cairn Server**：维护 Facts / Intents / Hints 图
2. **Dispatcher**：调度、容器、心跳、协议写回
3. **Worker Container + Worker CLI**：真正执行 agent prompt 的地方

参考：`D:\newwork\tmp\Cairn\README.md:36-126`

**我的判断**：这个项目的成功，不是来自“功能很多”，而是来自**边界非常窄且清楚**。

---

## 3. 入口层：CLI 极薄，但结构非常明确

CLI 只有两个主命令：

- `serve`
- `dispatch`

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\cli.py:11-67`

它的职责几乎只有两件事：

1. `serve`：启动 API server
2. `dispatch`：加载调度配置，启动 `DispatcherLoop`

也就是说，Cairn 没有把“项目状态”“任务视图”“调度逻辑”“大模型适配”“工具编排”揉进一个 CLI 命令里，而是从入口开始就把 **server 面** 与 **dispatcher 面** 分开。

这件事虽然看起来普通，但工程价值很高：

- Server 可以单独稳定；
- Dispatcher 可以单独演进；
- Worker backend 变化不需要改 Server；
- UI / Web / export 也不需要知道调度细节。

---

## 4. Server：它是“图真相源”，不是智能中心

### 4.1 `app.py` 很薄，说明 Server 被有意做成真相源

`server/app.py` 非常短，核心只是：

- 进程启动时配置数据库
- 注册 `settings / projects / hints / intents / export` 路由
- 提供静态页面

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\server\app.py:15-33`

**判断**：Server 故意不承担“调度决策”或“推理任务编排”。这点非常重要。

### 4.2 数据库模型非常克制，但已经足够表达图搜索

`server/db.py` 的 SQLite schema 只维护这些表：

- `settings`
- `projects`
- `facts`
- `intents`
- `intent_sources`
- `hints`
- `counters`
- `scoped_counters`

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\server\db.py:12-80`

这个 schema 有几个关键特点：

1. **Project 只是图容器**；
2. **Fact 是客观已确认事实**；
3. **Intent 是从若干 Fact 指向潜在新 Fact 的边**；
4. `intent_sources` 单独拆表，意味着一个 intent 可以由多个 facts 驱动；
5. `projects` 表里单独存 `reason_worker / reason_trigger / reason_started_at / reason_last_heartbeat_at`，说明 `reason` 被建模成 **项目级独占 lease**，而不是普通 intent。[源码 C3]

这非常值得注意：

> Cairn 不是把“reason”也做成一个普通节点，而是把它显式建模为项目级控制租约。

这会直接影响调度稳定性，因为它天然限制了“一个项目同一时刻只允许一个 reason worker”。

### 4.3 Pydantic 模型把协议边界钉死了

`server/models.py` 定义了当前 API 协议的主要对象：

- `Fact`
- `Intent`
- `Hint`
- `ProjectMeta`
- `ProjectDetail`
- `CreateProjectRequest`
- `CreateIntentRequest`
- `CompleteRequest`
- `ReopenRequest`

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\server\models.py:8-242`

这里的意义不只是“有类型”，而是它在协议层明确规定了：

- `Intent.from` 是 facts 列表；
- `to` 可以为空，也可以指向新 fact，或者 `goal`；
- `CompleteRequest` 与 `CreateIntentRequest` 都必须给出来源 facts；
- `goal` 不能被拿来作为普通来源 fact；
- `reopen` 是一个一等协议动作，不是人工去 DB 里改状态。

这使得 Cairn 的“图”不是概念，而是有严格写入规则的协议对象。

### 4.4 `services.py` 的本质：把协议语义压成一组小而硬的规则函数

`server/services.py` 里没有“智能”，但有很多关键约束：

- ID 生成规则
- project 状态检查
- intent claimability 检查
- fact existence 校验
- goal 不能作为普通来源
- intent → model 转换
- worker lease 过期
- reason lease 过期

关键位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\server\services.py:10-256`

尤其重要的是：

- `get_claimable_open_intent_or_404()` `:112`
- `intent_to_model()` `:150`
- `expire_workers()` `:221`
- `expire_reason_leases()` `:239`

这说明：

1. **claim / heartbeat / conclude 的合法性，不靠 Dispatcher 自觉，而靠 Server 再检查一次**；
2. **lease timeout 是协议内生的，不是调度器私有状态**；
3. **图的最终真相始终在服务端，而不在 worker 或 dispatcher 内存里。**

### 4.5 路由设计体现了 Cairn 的真正协议面

`projects.py`、`intents.py`、`hints.py`、`export.py` 构成了整个协议核心。

#### Projects API
位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\server\routers\projects.py:45-350`

关键动作：

- `list_projects()`：列项目摘要
- `create_project()`：初始化 `origin` / `goal`
- `claim_project_reason()`：项目级 reason lease
- `complete_project()`：把项目标记为完成，并写入一条 `to=goal` 的 intent
- `reopen_project()`：将 completed 项目重新打开，并把 external feedback 写成新 fact + intent

这套设计很巧：

- “完成”不是魔法状态，而是通过一条最终指向 `goal` 的 intent 显式表达；
- “重开”也不是简单改状态，而是写入新的外部反馈事实，继续扩图。[源码 C6]

#### Intents API
位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\server\routers\intents.py:33-142`

关键动作：

- `create_intent()`
- `heartbeat()`
- `release()`
- `conclude()`

语义非常清楚：

1. intent 在未 conclude 前可 claim / release；
2. conclude 会新建一个 fact，并把 intent 的 `to_fact_id` 指向它；
3. 于是“图前进了一步”在数据库里是显式可追踪的。

#### Hints API
位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\server\routers\hints.py:1-21`

Hints 被单独视为人类可注入的信息，不混进 facts。这个边界非常重要：

- Fact = 已确认
- Hint = 人工判断或额外线索

#### Export API
位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\server\routers\export.py:12-164`

Export 提供两种视图：

- `yaml`：给 prompt 用的图快照
- `timeline`：给人读的演进时间线

这说明作者从一开始就区分了：

- **机器调度协议视图**
- **模型上下文视图**
- **人类审计时间线视图**

这是 Cairn 里非常值得学习的一点。

---

## 5. Dispatcher：真正的系统核心

如果说 Server 是真相源，那么 **Dispatcher 才是 Cairn 最重要的工程重心**。

### 5.1 配置模型：运行时 contract 很强

`dispatcher/config.py` 定义了运行时配置：

- `TasksConfig`
- `ContainerConfig`
- `RuntimeConfig`
- `WorkerConfig`
- `DispatchConfig`

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\config.py:129-391`

这里有几个特别关键的点：

1. worker 的 `task_types`、`max_running`、`priority` 都是协议一部分；
2. `common_env` 会自动 merge 到每个 worker；
3. `validate_prompt_resources()` 会校验 prompt 目录里必须包含对应模板；
4. mock worker 不是玩具，而是正式支持的运行形态。

换句话说，Cairn 的 Dispatcher 不是“用 prompt 调一下模型”那么简单，而是**先把运行时 contract 收紧，再让模型进场**。

### 5.2 `CairnClient`：Dispatcher 只通过协议客户端接触 Server

`protocol/client.py` 封装了所有服务端交互：

- `list_projects()`
- `get_project()`
- `get_settings()`
- `export_project()`
- `heartbeat()`
- `claim_reason()`
- `release_reason()`
- `release()`
- `conclude()`
- `complete()`
- `create_intent()`

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\protocol\client.py:17-149`

这意味着 Dispatcher 没有在任何业务逻辑里“散装 HTTP 调用”，而是通过一个协议客户端集中交互。

**工程价值**：

- 便于替换 transport；
- 便于统一错误处理；
- 便于审计协议面；
- 便于后续测试和 mock。

### 5.3 `DispatcherLoop`：整个调度脑干都在这里

`dispatcher/scheduler/loop.py` 是 Cairn 的大脑主循环。

关键位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\scheduler\loop.py:39-849`

其核心职责包括：

1. 周期性轮询 Server
2. 维持启动健康检查
3. 维护本地 running task / cleanup task
4. 决定当前项目应该跑 `bootstrap / explore / reason` 哪一种
5. 选 worker
6. 提交线程池任务
7. 回收任务结果
8. 根据 outcome 更新本地 worker 惩罚窗口
9. 对 stopped / completed / deleted 项目做取消与容器清理

### 5.4 调度顺序非常讲究：不是“想跑什么就跑什么”

从 `_dispatch_available()` 和 `_try_dispatch_project()` 可以看出它的主策略：

- 全局先看 `max_workers`
- 再区分 `active` 项目
- 已运行项目优先于空闲项目
- 项目内：
  - 初始态优先 `bootstrap`
  - 非初始态优先 `explore`
  - 没有可 explore 的未认领 intent 后，再考虑 `reason`

对应位置：

- `_dispatch_available()` `:115`
- `_try_dispatch_project()` `:168`
- `_dispatch_initial_project()` `:260`
- `_dispatch_reason()` `:286`
- `_dispatch_bootstrap()` `:350`
- `_dispatch_explore()` `:408`

这意味着 Cairn 的调度哲学是：

1. **先执行已有探索方向**，不要频繁重新规划；
2. **只有在当前 open intents 被耗尽或图状态发生关键变化时**，才触发新的 reason；
3. **bootstrap 是一次初始直接求解，不是常驻模式**。

这套策略很适合避免 agent 系统常见的问题：

- 过度 replan
- 一直想新路线，不落地执行
- 多个规划器互相打架

### 5.5 `reason_trigger` 是一个很关键的“再规划闸门”

`_reason_trigger()` 的判断很克制：

- facts 增加
- hints 增加
- open intents 从有到无

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\scheduler\loop.py:617-631`

这说明 Cairn 并不是每一轮都去问模型“现在要不要重新想想”，而是通过**图态变化**触发 reason。

这是一个非常强的工程决策，因为它把模型思考频率绑定到了状态变化，而不是绑定到调度 tick。

### 5.6 Worker 选择也不是拍脑袋

`_select_worker()` 与 `worker_select.py` 做了几层过滤：

- 任务类型匹配
- `max_running` 配额
- 短期 unhealthy 拉黑
- 同项目同任务类型 rejected 拉黑
- 优先级升序
- 当前运行数更少优先
- 最后随机打散同分 worker

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\scheduler\loop.py:467-523`
- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\scheduler\worker_select.py:1-14`

这个策略很朴素，但足够有效，而且**解释性很强**。这比很多“让模型自己决定叫谁来做”要稳得多。

### 5.7 运行中项目的强制取消语义非常值得学习

`_cancel_inactive_tasks()` 明确规定：

- 只要项目状态不是 `active`
- 就对本地运行中的任务发取消信号

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\scheduler\loop.py:758-769`

这类代码很容易被低估，但它实际上回答了一个很关键的问题：

> 当外部状态变更后，系统如何保证旧执行流不会偷偷继续推进？

Cairn 的答案是：**Dispatcher 负责硬中断，并阻止后续 fallback 继续写图**。这是一种非常强的运行时治理能力。

---

## 6. 任务执行层：三类任务并不是“prompt 名字不同”而已

Cairn 把任务面做成三种不同执行链路，而不是一个万能 `run_agent(prompt)`。

### 6.1 共有能力都沉淀在 `tasks/common.py`

`common.py` 提供了很多核心运行时能力：

- `run_healthcheck()`
- `run_worker_process()`
- `write_graph_snapshot_reference()`
- `write_conclude_result_with_fact_id()`
- `best_effort_release()`
- `best_effort_release_reason()`

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\tasks\common.py:23-281`

最值得注意的是 `write_graph_snapshot_reference()`：

- 它会把 graph yaml 写进容器里的临时文件；
- prompt 里只告诉 worker 去读取那个文件。

这比直接把超长 YAML 一把塞进 prompt 更稳，原因是：

1. prompt 本身更短更清晰；
2. graph 快照作为 artifact 存在于容器里；
3. 可以被 conclude 阶段复用；
4. 更像“上下文引用”，而不是“上下文硬灌输”。

### 6.2 `bootstrap`：直接求解 + conclude fallback

`run_bootstrap_task()` 执行流程大致是：

1. 起 heartbeat lease
2. 健康检查 worker
3. 渲染 `bootstrap.md`
4. 启动执行阶段
5. 尝试解析 `fact + complete`
6. 如超时 / parse fail，则进入 conclude fallback
7. 最终写 `complete` 或至少写一个 fact

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\tasks\bootstrap.py:34-489`

这个双阶段模型非常有意思：

- 第一阶段：允许 agent 持续工作直到拿到结果；
- 第二阶段：如果第一阶段没收好尾，但 session 里已经有可确认事实，则强制 agent 只做总结，不再继续探索。

这和很多 agent 系统“要么一直跑到死，要么直接报错退出”相比，明显成熟得多。

### 6.3 `reason`：只负责图判断，不负责执行细节

`run_reason_task()` 的输入是：

- graph yaml
- valid fact ids
- open intents
- max intents

输出只能是：

- `complete`
- `intents`
- `noop`

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\tasks\reason.py:33-292`
- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\prompts\default\reason.md`
- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\contracts.py:49-92`

关键点在于：

> reason 不执行 explore，不 claim intent，不直接写图，只做“是否完成 / 是否新增意图”的窄决策。

这就是 Cairn 稳定的重要原因之一：**Reasoning 和 Acting 被强行拆开了。**

### 6.4 `explore`：一条 intent，只产出一个增量 fact

`run_explore_task()` 的职责被控制得更窄：

- 输入：graph yaml + current intent
- 输出：一个最新增量描述 `description`
- 超时或 parse fail 时，可以进入 conclude fallback

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\tasks\explore.py:30-415`
- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\prompts\default\explore.md`
- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\prompts\default\explore_conclude.md`
- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\contracts.py:144-156`

这里最值得学习的是一个限制：

- `description` 只能写**新的、已经确认的、对目标推进有价值的客观结果**；
- 不鼓励重复图里已有的信息；
- 不鼓励把长数据 blob 直接塞进 description。

这其实是在用协议逼 agent 只回“增量真相”。

---

## 7. Runtime 层：Cairn 最强的不是 prompt，而是运行时约束

### 7.1 `ContainerManager`：项目级容器是第一层隔离边界

`runtime/containers.py` 负责：

- 为每个 project 确保单独容器存在
- 清理 completed/stopped/orphan 容器
- 在容器内启动 exec 进程
- 向容器写临时文件（比如 graph snapshot）

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\runtime\containers.py:20-298`

这意味着 Cairn 的最小执行隔离单元不是“单条任务”，而是**单项目容器**。这个决定的好处是：

1. 同一项目内 session 和工作痕迹可复用；
2. 不同项目之间天然隔离；
3. conclude fallback 可以接着前一阶段 session 继续；
4. cleanup 可以按项目语义处理，而不是按零散进程处理。

### 7.2 `ManagedProcess`：对 exec 的 kill/cancel 管控做得很实

`runtime/process.py` 实现了：

- `ProcessResult`
- `ManagedProcess`
- timeout 后 kill
- cancel reason
- container 内 pid kill

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\runtime\process.py:18-166`

很多 agent 系统会忽略一个事实：

> “我发了取消” ≠ “进程真的停了”。

Cairn 在这一层做的是**真实进程级终止**，而不是只在内存里打个 cancelled 标记。

### 7.3 `HeartbeatLease`：lease 失败会直接杀进程

`runtime/heartbeat.py` 的语义非常强：

- 心跳由后台线程定期发；
- 连续失败超过 grace 窗口，或者收到 403/409；
- 标记 lease failure；
- 若有挂载进程，直接 kill。

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\runtime\heartbeat.py:23-119`

这意味着：

- lease 不只是 UI 显示状态；
- lease 是执行合法性的硬约束；
- 一旦 lease 失效，进程必须停。

这是很多系统缺少的“协议合法性 → 运行时强制终止”链路。

### 7.4 `TaskCancellation`：项目状态变化能真正打断执行

`runtime/cancellation.py` 很小，但很关键：

- 可以先记录 cancel reason；
- 后续 attach 进程时立刻 cancel；
- 或者在运行中直接触发 kill。

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\runtime\cancellation.py:8-35`

这保证了 inactive project 不会继续偷偷跑。

### 7.5 启动健康检查是系统级 gate，不是附属日志

`runtime/startup_healthcheck.py` 支持：

- 启动时批量并发检查所有 worker
- 生成结构化健康检查结果
- 若全部失败，直接阻止 dispatcher 启动

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\runtime\startup_healthcheck.py:17-176`

这一点很重要：

- Cairn 不相信“配置写上了就能跑”；
- 它要求在真正调度前确认 worker backend 至少有活口。

---

## 8. Worker 抽象：真正被统一的是 CLI 驱动契约

### 8.1 `WorkerDriver` 是 Cairn 的后端适配基类

`workers/base.py` 把 worker backend 统一成以下接口：

- `build_healthcheck()`
- `build_execute()`
- `build_conclude()`
- `extract_session()`
- `extract_response_text()`

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\workers\base.py:13-62`

也就是说，Cairn 并不试图让所有 agent backend API 一样，而是要求它们**都能映射成同一组 CLI 任务语义**。

### 8.2 Codex / Claude Code / Pi 都被约束成同一种任务接口

#### Codex
位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\workers\adapters\codex.py:8-115`

特点：

- 走 `codex exec`
- 明确设置 provider / base_url / env_key
- conclude 阶段走 `resume <session>`

#### Claude Code
位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\workers\adapters\claudecode.py:11-97`

特点：

- 执行阶段用 `--session-id`
- conclude 阶段用 `-r <session>`

#### Pi
位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\workers\adapters\pi.py:11-183`

特点：

- 通过 shell wrapper 注入 models.json
- 能从 stdout 的结构化事件里抽 session / assistant text
- 可以控制 tools 开关

#### Mock
位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\workers\adapters\mock.py:1-128`

特点：

- 模拟 reason/explore/bootstrap 的各种 outcome
- 可以测试 timeout / invalid_json / rejected / command_fail

**判断**：Cairn 的后端适配不是“统一 SDK”，而是“统一驱动契约”。这更务实，也更容易兼容现实中不同 agent CLI 的差异。

---

## 9. Prompt 与 Output Contract：Cairn 真正强的不是 prompt 文案，而是 prompt 被 contract 扣住了

### 9.1 prompt 非常克制

`reason.md`、`explore.md`、`bootstrap.md` 都在强调同一件事：

- 只返回 raw JSON object
- 拒绝长篇解释
- 只允许非常少的结构
- conclude 阶段覆盖之前的“继续工作”指令

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\prompts\default\reason.md`
- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\prompts\default\explore.md`
- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\prompts\default\bootstrap.md`
- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\prompts\default\explore_conclude.md`

这些 prompt 的设计重点不是“写得多聪明”，而是：

1. 把任务边界压窄；
2. 把输出形状压死；
3. 把 continue 与 conclude 分阶段明确拆开。

### 9.2 真正兜底的是 `contracts.py`

`dispatcher/contracts.py` 负责：

- 从 stdout 抽 JSON
- 校验 reason payload
- 校验 bootstrap execute/conclude payload
- 校验 explore payload

位置：

- `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\contracts.py:1-170`
- `output_parser.py:1-40`

最关键的一点是：

> 模型可以乱说，但系统只接受符合 contract 的结果。

所以 Cairn 的稳定性并不是“模型特别听话”，而是**模型输出被协议闸门强约束**。

---

## 10. Cairn 真正值得我们学的，不是“黑板架构”这四个字，而是下面这些代码层策略

### 10.1 值得强复用的点

#### A. Dispatcher 作为唯一写协议者

这是 Cairn 最值钱的一条。

不要让 agent 自己去：

- claim
- heartbeat
- complete
- release
- conclude

把这些统一放进 dispatcher/runtime 主线，系统会稳定很多。[源码 C10][源码 C14][源码 C15][源码 C16]

#### B. 把“规划”和“执行”彻底拆开

Cairn 的 `reason` 只判断：

- 是否完成
- 是否新增 intents

而 `explore` 只做：

- 沿一条 intent 产出一个 fact

这比“一个 agent 既想、又试、又记、又提交”更稳。[源码 C15][源码 C16]

#### C. 用状态变化触发 reason，而不是按 tick 强行让模型重想

`_reason_trigger()` 很值得借鉴，因为它能显著减少无效 replan。[源码 C14]

#### D. 所有高价值运行时动作都应该有 cancel / lease / timeout / fallback

Cairn 在 bootstrap 与 explore 上都提供 conclude fallback，这是非常实用的模式。[源码 C15][源码 C16]

#### E. Project 级容器比 Task 级进程更适合长任务图搜索

这使 session、痕迹、环境可以在同项目内稳定延续。[源码 C11]

#### F. 输出增量事实，而不是整段“大总结”

这一点对避免上下文污染非常有帮助。[源码 C15][源码 C16][源码 C17]

### 10.2 不建议生搬硬套的点

#### A. 不要直接照抄它的 SQLite + 单 Dispatcher 假设

Cairn 当前文档里已经明确：它按**单 Dispatcher 实例**设计，不支持多个 Dispatcher 同时协作同一服务端。[文档 D1]

如果我们场景更复杂，未来可能要升级为：

- 更强的 event log
- 更强的 distributed lease
- 更强的 resume/handoff

#### B. 不要误以为它“没有 memory，所以 memory 不重要”

Cairn 当前强在搜索协议，但它对长期记忆、跨项目知识沉淀、queryable session replay 仍然是轻量的。

#### C. 不要把它的 worker CLI 驱动误解成“所有 agent 都该这样接”

它适合当前这类 containerized CLI task 模式，但如果我们有浏览器、MCP tool、长连接代理、复杂 artifact pipeline，就不能只靠 CLI 包装。

---

## 11. 对我们现有项目最有价值的复用建议

如果把 Cairn 的代码思想迁移到我们现在的系统里，我认为最值得优先吸收的是这 5 条：

### 11.1 先补“唯一协议写入主线”

把以下动作从 agent 本体里抽走：

- 状态推进
- checkpoint 决策
- 结果提交
- 恢复判定
- worker 心跳 / 取消

让 agent 只负责：

- 读上下文
- 回结构化结果

### 11.2 把主循环拆成 Reason / Explore / Conclude 几个硬阶段

不要让一个大 agent loop 同时干：

- 假设生成
- 利用
- 验证
- 总结
- 恢复

应该像 Cairn 一样，把阶段收窄，再用 contract 串起来。

### 11.3 把“图快照 / 状态快照 / 运行时真相”三者明确区分

Cairn 的 `export yaml` 给了我们一个很好的参照：

- Server truth
- Prompt snapshot
- Timeline / review view

这三个视图不能混成一种对象。

### 11.4 给长任务补强取消与 lease 语义

项目状态一旦变 inactive，运行中的流程必须停；这一点值得直接学。[源码 C12][源码 C13][源码 C14]

### 11.5 用 output contract 约束 agent，而不是靠 prompt 祈祷

如果输出形状不被代码校验，系统最后还是会回到“靠 LLM 自觉”。Cairn 在这件事上做得很对。[源码 C17]

---

## 12. 最终判断

Cairn 最可贵的地方，不是它提出了 Blackboard / Fact / Intent / Hint 这些概念，而是：

> **它把这些概念落实成了一套真实可运行的协议、调度器、容器 runtime、worker lease 和结构化输出契约。**

所以如果我们想从 Cairn 学东西，最不该学的是“概念名称”，最该学的是：

1. **真相源和执行器分离**
2. **Dispatcher 独占协议写回**
3. **Reason / Explore / Conclude 分阶段**
4. **输出强 contract 化**
5. **lease / cancel / timeout / fallback 进入主干**
6. **图快照与系统真相解耦**

这些东西，才是 Cairn 这份代码里真正值钱的部分。

---

## 13. 来源标注

### 源码来源

- [源码 C1] `D:\newwork\tmp\Cairn\README.md:36-126`
- [源码 C2] `D:\newwork\tmp\Cairn\cairn\src\cairn\cli.py:11-67`
- [源码 C3] `D:\newwork\tmp\Cairn\cairn\src\cairn\server\db.py:12-108`
- [源码 C4] `D:\newwork\tmp\Cairn\cairn\src\cairn\server\app.py:15-33`
- [源码 C5] `D:\newwork\tmp\Cairn\cairn\src\cairn\server\models.py:8-242`
- [源码 C6] `D:\newwork\tmp\Cairn\cairn\src\cairn\server\routers\projects.py:45-350`
- [源码 C7] `D:\newwork\tmp\Cairn\cairn\src\cairn\server\routers\intents.py:33-142`
- [源码 C8] `D:\newwork\tmp\Cairn\cairn\src\cairn\server\routers\export.py:12-164`
- [源码 C9] `D:\newwork\tmp\Cairn\cairn\src\cairn\server\services.py:10-256`
- [源码 C10] `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\protocol\client.py:17-149`
- [源码 C11] `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\runtime\containers.py:20-298`
- [源码 C12] `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\runtime\process.py:18-166`
- [源码 C13] `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\runtime\heartbeat.py:23-119`、`D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\runtime\cancellation.py:8-35`
- [源码 C14] `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\scheduler\loop.py:39-849`
- [源码 C15] `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\tasks\bootstrap.py:34-489`、`D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\tasks\common.py:23-281`
- [源码 C16] `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\tasks\reason.py:33-292`、`D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\tasks\explore.py:30-415`
- [源码 C17] `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\contracts.py:1-170`、`D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\output_parser.py:1-40`、`D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\prompting.py:1-29`
- [源码 C18] `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\workers\base.py:13-62`、`D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\workers\registry.py:15-16`
- [源码 C19] `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\workers\adapters\claudecode.py:11-97`、`D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\workers\adapters\codex.py:8-115`、`D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\workers\adapters\pi.py:11-183`、`D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\workers\adapters\mock.py:1-128`
- [源码 C20] `D:\newwork\tmp\Cairn\cairn\src\cairn\dispatcher\config.py:129-391`、`D:\newwork\tmp\Cairn\dispatch.yaml`、`D:\newwork\tmp\Cairn\dispatch_mock.yaml`

### 设计文档来源

- [文档 D1] `D:\newwork\tmp\Cairn\docs\specs\dispatcher-design.md`
