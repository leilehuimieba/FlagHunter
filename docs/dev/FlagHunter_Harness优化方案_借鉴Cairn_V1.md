# FlagHunter Harness 优化方案（借鉴 Cairn）V1

> 适用范围：`D:\webstudy\FlagHunter` 中与 `/ctf`、`CTFTaskDispatcher`、`CTFState`、验证/恢复、MCP/Web/TUI 任务视图、artifact 管理、长任务交接相关的后续改造。  
> 文档目的：在**不推倒现有主干**的前提下，吸收 `Cairn` 在 **状态外置、artifact-first、会话可回放、调度协议化、长任务可恢复** 方面的长处，补强 FlagHunter 当前 Harness 层的不足。[来源 S1][来源 S2][来源 S3][来源 S4][来源 S5]

---

## 1. 文档结论

本项目当前最值得优先做的，不是继续扩题型或继续堆调度分支，而是先把 **Harness 外壳** 收紧。这里的 Harness，不是单指 prompt，而是指：

1. **状态如何被显式保存**
2. **运行过程如何被 append-only 记录**
3. **artifact 如何统一注册与引用**
4. **验证与恢复如何走统一主线**
5. **长任务如何 handoff / resume**

从仓库现状看，FlagHunter 已经具备不错的主干基础：

- 有显式 `CTFState / Hypothesis / Experiment / VerificationResult`；[来源 S6][来源 S7]
- 有规则优先的 `HypothesisEngine`；[来源 S8]
- 有独立 `Verifier` 与 `RecoveryController`；[来源 S9][来源 S10]
- 有统一 `ToolExecutor`；[来源 S11]
- 有 MCP / TUI / Web 三个运行入口；[来源 S12][来源 S13][来源 S14]

**因此，本轮优化不建议照搬 Cairn 的完整形态，而建议采用“保留现有主干 + 新增轻量 Harness 层”的方案。** 这是本文的核心结论。[来源 S1][来源 S3][来源 S4][来源 S5]

---

## 2. 为什么要借鉴 Cairn

### 2.1 Cairn 值得借鉴的不是“名字”，而是运行时边界

根据 `Cairn` 的 README、仓库结构、配置文件以及作者的两篇相关文章，可以确认它的核心不在“多会几个 exploit”，而在于它把问题抽象成：

- 明确 `origin`
- 明确 `goal`
- 中间路径未知
- 通过共享状态不断生成新事实与新探索方向

它采用的最小概念是：

- `Fact`
- `Intent`
- `Hint`

以及围绕它们的：

- shared board / shared graph
- dispatcher
- worker container
- append-only session / artifact / result accumulation

这一点在 `Cairn` README、仓库目录和作者的 2026-04-26 / 2026-05-27 两篇文章里是一致的。[来源 S1][来源 S3][来源 S4]

### 2.2 Anthropic 的工程文章与 Cairn 的方向一致

Anthropic 在两篇工程文章里强调了几件事：

1. **session / harness / sandbox 应该解耦**；[来源 S2]
2. **会话日志不应等于模型上下文窗口**，而应在上下文窗外可查询、可回放；[来源 S2]
3. 多 agent 的主要价值来自 **并行探索** 和 **上下文隔离**，而不是机械模仿人类岗位分工；[来源 S5]
4. 长任务系统必须优先解决 **可恢复性、可观测性、错误传播和部署一致性**。[来源 S2][来源 S5]

**推断**：Cairn 的“黑板 + worker + dispatcher + 外置状态”并不是孤例，它和 Anthropic 对长任务 agent 的抽象方向是高度一致的。因此，借鉴 Cairn 并不是追热点，而是顺着当前主流 agent 工程的稳定方向在收紧你们自己的主干。[来源 S1][来源 S2][来源 S5]

---

## 3. FlagHunter 当前主干的真实状态

### 3.1 已有基础能力（应保留）

以下能力已经成型，不建议推倒：

#### A. 结构化 CTF 主干已经存在
- `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\ctf_state.py` 里已有：
  - `CTFState`
  - `Hypothesis`
  - `Experiment`
  - `VerificationResult`
  - `FlagProof`
  - `ExplorationItem`
  这说明你们已经从“纯 prompt 解题”走到了“结构化状态驱动”的方向。[来源 S6]

#### B. 验证与恢复不再是纯日志行为
- `verifier.py` 已区分 `candidate / runtime / verified / rejected`；[来源 S9]
- `recovery.py` 已具备：
  - provider unavailable
  - missing tools
  - candidate-only
  - blocked surface
  - no-progress → explore agenda / switch chain
  等恢复路径。[来源 S10]

#### C. 假设引擎已具备规则优先意识
- `hypothesis_engine.py` 已不是完全靠 LLM 猜，而是基于结构特征生成候选假设，并带反馈更新逻辑。[来源 S8]

#### D. 工具执行已走统一 executor
- `tools/executor.py` 已有：
  - scope check
  - stealth
  - 缺失工具检测
  - flag 自动发现
  - result cache
  这说明工具层已经具备成为“统一动作面”的基础。[来源 S11]

### 3.2 当前核心短板（应优先处理）

#### A. `ctf_dispatcher.py` 体积过大，职责混杂
`D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\ctf_dispatcher.py` 当前约 **7027 行**，承载了：

- orchestration
- 页面结构分析
- exploit helper
- flag 相关处理
- 平台/场景逻辑
- UI 相关拼接
- 部分恢复与调度细节

这已经超出“协调器”应承担的职责边界。[来源 S15][来源 S7][来源 S16]

#### B. 运行时“真相”仍然是分裂的
当前任务状态分散在：

- `CTFState`
- notes
- `task_registry.py`
- `conversation_store.py`
- MCP `TaskEntry`
- Web server task detail
- ConversationMemory summary

这意味着：

- TUI/MCP/Web 看到的任务真相并非来自同一底层对象；
- 恢复通常仍依赖“读 notes / 看日志 / 重新猜上下文”；
- 很难做可靠 handoff / resume。[来源 S6][来源 S11][来源 S12][来源 S13][来源 S14][来源 S17][来源 S18]

#### C. 上下文装配仍偏 prompt 拼接，不够 queryable
- `knowledge/context_assembler.py` 当前仍是轻量的 gather/select/structure/compress；[来源 S18]
- `llm/memory.py` 主要负责聊天历史摘要，不适合承担运行时状态记忆。[来源 S17]

**推断**：你们已经具备“状态模型”，但还缺少“session log + session context view + checkpoint store”这三个壳层模块。[来源 S17][来源 S18][来源 S2]

#### D. artifact 仍然以裸路径为主，生命周期不统一
- Web / MCP / finish / notes 中都有 artifact 路径，但没有统一 artifact handle / registry；[来源 S11][来源 S12][来源 S13]
- 这会让：
  - artifact 复用困难
  - UI 侧详情呈现分裂
  - handoff 时只能传 path，无法传 artifact 语义

#### E. 指标有了，语义事件还没有统一主线
- `observability.py` 可以记录 metrics；[来源 S19]
- 但 verifier / recovery / tool / artifact / checkpoint 还没有落在同一个 append-only 事件流里。

---

## 4. 从 Cairn 映射到 FlagHunter 的正确姿势

### 4.1 不直接引入 Cairn 的术语替换
本项目不建议把现有对象全改名为 `Fact/Intent/Hint`。更合理的映射是：

| Cairn 概念 | FlagHunter 现有对象 | 建议处理 |
|---|---|---|
| Fact | `Observation / Artifact / FlagRecord / FlagProof` | 保持现名，统一写入 session ledger |
| Intent | `Hypothesis / next_experiments / exploration_agenda` | 保持现名，把调度动作事件化 |
| Hint | `hint / challengePath / artifactPaths / user feedback` | 走 checkpoint / ledger 注入 |
| Shared board | 当前分散在 `CTFState + notes + task registry + UI task model` | 收拢为 `ledger + state snapshot + artifact registry` |
| Dispatcher | `CTFTaskDispatcher` | façade 化，背后引入 `CTFCoordinator` |
| Queryable session | 当前 summary + notes | 增加 session context view |

这个映射方式的好处是：**保留当前语义与测试基础，不在第一轮重构中制造术语级迁移成本。** [来源 S1][来源 S3][来源 S4][来源 S6][来源 S7]

### 4.2 不先拆双进程，而是先拆逻辑边界
Cairn 明确分了 server / dispatcher / worker container。[来源 S1]

你们现在不适合直接拆成独立 server 进程，原因有三：

1. 当前仓库已经有 TUI / MCP / Web 三个入口，直接拆进程会放大兼容成本；[来源 S12][来源 S13][来源 S14]
2. 你们的痛点首先在 **状态主线不统一**，而不是“进程数量太少”；[来源 S6][来源 S18]
3. `CTFState/Hypothesis/Verifier/Recovery` 已成型，优先级应是“补壳”，不是“改形态”。[来源 S6][来源 S8][来源 S9][来源 S10]

**结论**：第一轮只做逻辑分层，不做进程分层。[来源 S2][来源 S5]

---

## 5. 建议新增的 Harness 层

### 5.1 目标
在现有单仓形态上新增一个轻量 Harness 层，承担以下职责：

1. **append-only 事件账本**
2. **artifact 注册表**
3. **checkpoint 落盘与恢复**
4. **审计级事件输出**
5. **可切片 session context**

### 5.2 推荐新增模块
建议新增：

- `D:\webstudy\FlagHunter\pentestagent\harness\models.py`
- `D:\webstudy\FlagHunter\pentestagent\harness\session_ledger.py`
- `D:\webstudy\FlagHunter\pentestagent\harness\artifact_registry.py`
- `D:\webstudy\FlagHunter\pentestagent\harness\checkpoint_store.py`
- `D:\webstudy\FlagHunter\pentestagent\harness\audit_events.py`
- `D:\webstudy\FlagHunter\pentestagent\knowledge\session_context.py`

### 5.3 各模块职责

#### A. `session_ledger.py`
负责：
- 以 JSONL 形式 append-only 记录事件；
- 支持按 `run_id` 读取；
- 支持按事件类型切片；
- 支持“最近 N 条”查询。

它是本轮最重要的新模块，因为它会成为：
- context view 的输入；
- handoff / resume 的依据；
- Web/MCP/TUI 统一任务时间线的底层来源。[来源 S2][来源 S12][来源 S13][来源 S14]

#### B. `artifact_registry.py`
负责：
- 把裸路径升级为 `artifact handle`；
- 保存 `artifact_id / run_id / kind / path / title / producer / tags / metadata`；
- 兼容旧 `artifactPaths`，新增 `artifactRefs`。

#### C. `checkpoint_store.py`
负责：
- 存 `CTFState snapshot`；
- 标记 checkpoint label；
- 支持 latest checkpoint load；
- 为 provider unavailable / candidate-only / wait_for_verification 等停止路径提供恢复基础。[来源 S6][来源 S10][来源 S2]

#### D. `audit_events.py`
负责把：
- verifier decision
- recovery decision
- tool called/finished
- artifact registered
- handoff written
统一为结构化事件。

#### E. `session_context.py`
负责：
- 按 `run_id + phase` 查询最近 observation / failed experiment / verification / recovery 事件；
- 为 `ContextAssembler` 提供“可切片会话视图”；
- 将 `ConversationMemory` 从“任务状态记忆”中解耦出来。[来源 S17][来源 S18][来源 S2]

---

## 6. 对现有主干的建议改造

### 6.1 `ctf_dispatcher.py` 应变为 façade，而不是继续膨胀
建议从它里面抽出：

- `coordinator.py`
- `recon_executor.py`
- `explore_executor.py`
- `state_persistence.py`

#### 推荐职责划分

##### `CTFCoordinator`
负责：
- 驱动 `observe -> reason -> explore -> verify -> recover` 主循环；
- 调用 `HypothesisEngine / StrategyRegistry / Verifier / RecoveryController`；
- 写关键事件到 ledger；
- 控制 checkpoint 落盘点。

##### `ReconExecutor`
负责：
- 页面结构探测
- 基础 recon 输出
- 结构特征输入 `CTFState`

##### `ExploreExecutor`
负责：
- 执行 strategy / exploit helper
- 回传结果与 artifact
- 不负责最终 stop 判定

##### `CTFTaskDispatcher`
退化为：
- 兼容对外入口
- 适配旧调用路径
- 调用 coordinator

**注意**：第一轮不要试图把所有 exploit helper 全部迁出去。先把“主循环职责边界”抽清楚，再继续细拆。这是降低重构风险的关键策略。[来源 S7][来源 S15][来源 S16]

### 6.2 `ConversationMemory` 应只负责聊天历史
`llm/memory.py` 当前的摘要机制适合处理聊天上下文，不适合做长任务 runtime state 的主存储。[来源 S17]

建议改成：

- `ConversationMemory`：只负责聊天历史摘要；
- `SessionContextView`：负责运行时状态切片；
- `CTFState snapshot`：负责结构化状态；
- `session_ledger`：负责事件真相。

这样做的收益是：
- summary 丢信息不再直接影响主循环恢复；
- prompt 构造可以按 phase 查最近最相关事件，而不是把一大段摘要硬塞回模型。

### 6.3 `task_registry.py` 应退居“任务索引层”
当前它更像任务快照存储。[来源 S20]

建议后续它只保存：
- `task_id`
- `run_id`
- `status`
- `ledger_path`
- `checkpoint_path`
- `artifact_index_path`

而不是继续承担完整任务真相的职责。

### 6.4 Web / MCP / TUI 应消费同一事件源
你们现在已经有：
- MCP `TaskEntry` 记录 thinking/tool_calls/tool_results；[来源 S12]
- Web task detail 记录 artifactPaths 等；[来源 S13]
- TUI 也有自己的实时视图和会话存储。[来源 S14]

建议目标是：

> 三端不再各自产生一份“主任务真相”，而是从同一个 `run_id` 的 ledger / checkpoint / artifact registry 做投影。

这会直接提升：
- 可观察性
- 可调试性
- replay/retry/resume 一致性

---

## 7. 推荐分阶段实施路径

### Phase A：先把“真相记录层”立起来
优先级最高，风险最低。

#### 目标
- 新增 session ledger
- 新增 artifact registry
- 给 `CTFState` 增加 `to_snapshot / from_snapshot`
- 定义 checkpoint 落点

#### 预期收益
- 任何 `/ctf run` 都能形成：
  - event log
  - checkpoint
  - artifact index
- wrong-flag、provider-down、candidate-only 停止路径可审计

### Phase B：把 dispatcher 收缩成协调器 façade

#### 目标
- 抽出 `CTFCoordinator`
- 抽出 recon/explore executor
- 保持 helper 利用逻辑暂时不动

#### 预期收益
- 降低 `ctf_dispatcher.py` 的认知负担
- 后续更容易加 resume、checkpoint 和 eval

### Phase C：把上下文与恢复改成 queryable / resumable

#### 目标
- `SessionContextView` 替代“只靠 summary”
- MCP/Web/TUI 围绕同一 `run_id`
- `conversation_store.py` 增加 handoff metadata

#### 预期收益
- 长任务停止后不是“重新来一遍”，而是“从最近断点继续”

### Phase D：最后补评估与验收矩阵

#### 推荐指标
- candidate → verified 转化率
- wrong-flag 后恢复成功率
- 平均 prompt context 长度
- 人工定位失败链路耗时

**推断**：这四项指标比“又加了几个题型策略”更能反映 Harness 改造是否真的产生了稳定性收益。[来源 S9][来源 S10][来源 S19]

---

## 8. 不建议现在做的事

以下事项本轮明确后置：

1. **不先改成 Cairn 风格独立 server/dispatcher 双进程**  
   理由：当前仓库已有多入口，直接拆进程成本高且收益不在第一位。[来源 S1][来源 S12][来源 S13][来源 S14]

2. **不先上更多多 agent 角色**  
   理由：你们当前主要问题不是并行度，而是状态主线与恢复主线不统一。[来源 S7][来源 S5]

3. **不先用数据库替代 JSONL / JSON checkpoint**  
   理由：append-only JSONL 已足够支撑第一阶段的可回放与可切片。

4. **不先废弃 notes**  
   理由：更合理的路径是让 notes 退居“证据层 / 审计层”，而不是第一轮硬删除。[来源 S6][来源 S16]

---

## 9. 预期收益

### 9.1 工程收益
- `ctf_dispatcher.py` 从“巨型混合器”向“协调器 façade”收缩；[来源 S15]
- verifier / recovery / tool / artifact / checkpoint 都能进入同一事件主线；[来源 S9][来源 S10][来源 S11][来源 S19]
- Web / MCP / TUI 终于能围绕同一 run 真相工作；[来源 S12][来源 S13][来源 S14]
- 后续 resume / handoff / eval 不再建立在 notes 拼接和 prompt 猜测之上。[来源 S2][来源 S17][来源 S18]

### 9.2 产品收益
- 用户更容易回答：
  - 系统为什么停？
  - 停在第几步？
  - 哪个 flag 被拒绝过？
  - 哪些 artifact 产出了？
  - 可以从哪里恢复？

### 9.3 战略收益
- 为后续本地挑战资产模式、MCP 远程编排、Web 控制台深度可视化提供稳定底座；
- 避免“每扩一层功能，就再复制一份任务真相”的持续失稳。

---

## 10. 最终建议

### 10.1 一句话判断
**FlagHunter 现在不是缺能力模块，而是更缺一层稳定的 Harness 外壳。**

### 10.2 本轮优先级排序
建议实际执行顺序如下：

1. `session_ledger`
2. `artifact_registry`
3. `CTFState snapshot + checkpoint_store`
4. `CTFCoordinator façade 化`
5. `SessionContextView`
6. `MCP/Web/TUI` 统一 run 投影

### 10.3 本文建议的边界
本文不是要把 FlagHunter 改造成 Cairn，而是建议你们**吸收 Cairn 最值得学的 5 件事**：

1. **状态与事件外置**
2. **artifact-first**
3. **调度协议化**
4. **验证独立化**
5. **长任务可交接可恢复**

这是一个“补壳”方案，而不是“推倒重写”方案。[来源 S1][来源 S2][来源 S3][来源 S4][来源 S5]

---

## 11. 来源清单

### 本仓库代码与文档
- **S6** `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\ctf_state.py`
- **S7** `D:\webstudy\FlagHunter\docs\dev\CTF_Agent_主干架构规范_V1.md`
- **S8** `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\hypothesis_engine.py`
- **S9** `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\verifier.py`
- **S10** `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\recovery.py`
- **S11** `D:\webstudy\FlagHunter\pentestagent\tools\executor.py`
- **S12** `D:\webstudy\FlagHunter\pentestagent\mcp\server\mcp_tools.py`
- **S13** `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`
- **S14** `D:\webstudy\FlagHunter\pentestagent\interface\conversation_store.py`
- **S15** `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\ctf_dispatcher.py`
- **S16** `D:\webstudy\FlagHunter\docs\dev\CTF_Agent_实现约束与协作规范_V1.md`
- **S17** `D:\webstudy\FlagHunter\pentestagent\llm\memory.py`
- **S18** `D:\webstudy\FlagHunter\pentestagent\knowledge\context_assembler.py`
- **S19** `D:\webstudy\FlagHunter\pentestagent\observability.py`
- **S20** `D:\webstudy\FlagHunter\pentestagent\task_registry.py`

### 外部项目与文章
- **S1** Cairn GitHub README / 仓库结构 / 配置  
  [https://github.com/oritera/Cairn](https://github.com/oritera/Cairn)
- **S2** Anthropic — Scaling Managed Agents: Decoupling the brain from the hands  
  [https://www.anthropic.com/engineering/managed-agents](https://www.anthropic.com/engineering/managed-agents)
- **S3** 微信文章：国内最强 AI 渗透测试 Agent —— TCH·腾讯云黑客松第二届智能渗透挑战赛 唯一 AK 战队复盘  
  [https://mp.weixin.qq.com/s/DlpEH7bVr0xi0VawPJs3XA](https://mp.weixin.qq.com/s/DlpEH7bVr0xi0VawPJs3XA)
- **S4** 微信文章：无径之径：Cairn AI 从渗透测试到通用问题的求解  
  [https://mp.weixin.qq.com/s/2rEqFLvkxvYWM3gW170C2w](https://mp.weixin.qq.com/s/2rEqFLvkxvYWM3gW170C2w)
- **S5** Anthropic — How we built our multi-agent research system  
  [https://www.anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)

### 背景交叉参考
- **S21** 微信文章：两届TCH之后 —— AI 渗透测试 Agent 的 Harness 工程演进、防御与我的思考  
  [https://mp.weixin.qq.com/s/pbieEet9VCR5iLhjViokIA](https://mp.weixin.qq.com/s/pbieEet9VCR5iLhjViokIA)
- **S22** XBOW validation benchmarks  
  [https://github.com/xbow-engineering/validation-benchmarks](https://github.com/xbow-engineering/validation-benchmarks)

---

## 12. 备注

- 本文中的“建议 / 推断”均基于当前仓库代码快照与上述外部资料交叉得出；若后续主干发生明显变化，应同步更新本文。  
- 若进入具体实施，请以：
  - `D:\webstudy\FlagHunter\docs\superpowers\plans\2026-05-29-harness-optimization-plan.md`
  作为逐任务执行清单；本文则作为**设计说明与来源依据文档**。
