# FlagHunter CTF Solver Implementation Roadmap v0.1

- 日期：2026-07-02
- 状态：Draft / 基于 `FlagHunter_CTF_Solver_Spec_v0.1_2026-07-02.md` 与 `FlagHunter_CTF_Solver_Gap_Report_v0.1_2026-07-02.md` 的首版实施路线图
- 对照规格：[FlagHunter_CTF_Solver_Spec_v0.1_2026-07-02.md](./FlagHunter_CTF_Solver_Spec_v0.1_2026-07-02.md)
- 差距分析：[FlagHunter_CTF_Solver_Gap_Report_v0.1_2026-07-02.md](./FlagHunter_CTF_Solver_Gap_Report_v0.1_2026-07-02.md)
- 适用范围：FlagHunter 当前 CTF 单体主线、blackboard solve loop、verifier、ledger/checkpoint、crew 并行能力

---

## 0. 本文目的

spec 负责定义目标态，gap report 负责说明“哪里还没到位”，而本文负责回答第三个问题：

> 从今天的代码出发，应该按什么顺序改，先钉什么，再接什么，如何逐阶段验收，才能把 CTF Solver 收敛成一个可控的工程系统。

本文不是任务清单的堆砌，而是正式迁移路线。后续若要拆 backlog、开分支、做阶段验收，应以本文为主干。

---

## 1. 结论先行

建议按下面 5 个阶段推进，而不是并行重写：

1. **P1 统一 Claim / VerificationRecord**
   先把“什么是可消费事实、谁能验证、验证结果如何落盘”钉死。
2. **P2 补全 Trace 主干**
   把 `model_call / handoff / state_transition / budget_event` 补到 ledger 中，形成完整因果链。
3. **P3 引入 SolveNode + TaskBrief / Receipt**
   把现在的“强循环”升级为“可审计求解树”。
4. **P4 收敛 Blackboard / Checkpoint / Crew 协议**
   让单体与 crew 共用同一事实面与交接纪律。
5. **P5 接通学习闭环**
   让 strategy memory、wrong-flag、wrong-strategy 真正回流，而不是只做旁路经验库。

这个顺序背后的原则是：

- **先收敛事实，再收敛日志，再收敛调度。**
- **先把单体 CTF 主线钉稳，再让 crew 并入。**
- **先让系统能被解释、能被追责，再追求更多能力。**

---

## 2. 目标主干

本路线图收敛后的目标主干应是：

`AgentSession -> CTFCoordinator -> SolveTree / Blackboard -> TaskBrief -> Solver -> Receipt -> Verifier -> Claim Store -> Trace / Checkpoint / StrategyMemory`

对当前代码的主落点是：

- `flaghunter/session/agent_session.py`
- `flaghunter/agents/pa_agent/coordinator.py`
- `flaghunter/agents/pa_agent/ctf_dispatcher.py`
- `flaghunter/agents/pa_agent/ctf_state.py`
- `flaghunter/agents/pa_agent/verifier.py`
- `flaghunter/agents/pa_agent/recovery.py`
- `flaghunter/agents/pa_agent/blackboard.py`
- `flaghunter/agents/pa_agent/blackboard_adapter.py`
- `flaghunter/agents/pa_agent/audit_infra.py`
- `flaghunter/harness/audit_events.py`
- `flaghunter/harness/session_ledger.py`
- `flaghunter/harness/checkpoint_store.py`
- `flaghunter/agents/crew/orchestrator.py`
- `flaghunter/agents/crew/worker_pool.py`

---

## 3. 实施原则

### 3.1 不推倒重来

当前主线已经有真实骨架：

`AgentSession -> CTFCoordinator -> CTFTaskDispatcher -> blackboard loop -> CTFVerifier -> SessionLedger / Checkpoint / StrategyMemory`

因此本次改造不是另起炉灶，而是沿现有骨架分层换芯。

### 3.2 先改 canonical data，再改流程

如果 `Claim`、`VerificationRecord`、`SolveNode` 不先成为正式对象，后续任何 trace、resume、crew 都只能靠约定维持，难以稳定。

### 3.3 兼容过渡，不做大爆炸切换

每个阶段都必须允许一段时间的“双写 / 双读”或“旧结构包裹新结构”：

- 旧 `candidate_flags / runtime_flags / verified_flags / rejected_flags`
- 旧 `observations / artifacts / hypotheses`
- 新 `Claim / VerificationRecord / SolveNode`

目标不是一步删光旧结构，而是在阶段毕业后关闭旧写入口。

### 3.4 先单体后 crew

crew 不是第一阶段。若单体 CTF 主线还没有统一事实与验证纪律，直接扩 crew 只会放大混乱。

### 3.5 阶段毕业必须靠验收，不靠主观感觉

每个阶段都要定义：

- 交付物
- 代码落点
- 风险
- 验收口径
- 禁止提前做的事项

---

## 4. 阶段总览

| 阶段 | 核心目标 | 主要模块 | 前置依赖 | 毕业标志 |
|---|---|---|---|---|
| P1 | 统一 Claim / VerificationRecord | `ctf_state.py`, `verifier.py`, `coordinator.py`, `ctf_dispatcher.py` | 无 | verified 写入口收敛到 verifier |
| P2 | Trace 全链路可回放 | `audit_events.py`, `audit_infra.py`, `session_ledger.py`, `llm/*`, `coordinator.py` | P1 | 任一最终答案可回溯到模型、工具、验证与状态迁移 |
| P3 | SolveNode + TaskBrief / Receipt | `coordinator.py`, `ctf_dispatcher.py`, `blackboard*.py`, `checkpoint_store.py` | P1, P2 | 每个子问题都有状态、预算、交接物与结果回执 |
| P4 | 单体 / crew 协议统一 | `agents/crew/*`, `swarm_bridge.py`, `coordinator.py`, `verifier.py` | P1, P2, P3 | 单体与 crew 导出同型 Claim / Trace / Receipt |
| P5 | 学习闭环与评测闭环 | `strategy_memory.py`, `recovery.py`, `tests/eval/*`, `harness/*` | P1, P2, P3 | 历史成功与失败都能反向影响后续解题 |

---

## 5. 分阶段实施路线

### 5.1 P1：统一 Claim / VerificationRecord

**目标**

把当前散落在 `observations / artifacts / hypotheses / flags / notes` 里的可消费结论，统一收敛到一条正式事实线。

**为什么先做**

因为后面的 `Trace`、`SolveNode`、`Receipt`、`Crew` 都要围绕“事实原子”工作。没有统一 Claim，后续所有控制面都只是贴皮。

**建议交付物**

- `Claim` 逻辑 schema
- `VerificationRecord` 逻辑 schema
- `ClaimLevel` 与 `ClaimKind` 枚举
- 统一 claim 写入口
- verifier 对 verified 的唯一升级权限

**建议代码落点**

- `flaghunter/agents/pa_agent/ctf_state.py`
  - 新增 claims 存储与索引
  - 保留旧 flags 桶作为兼容投影，不再作为事实真相源
- `flaghunter/agents/pa_agent/verifier.py`
  - 从 `flag verifier` 向 `claim verifier` 演进
  - 先支持 `flag_found`、`credential_valid`、`endpoint_exists`、`exploit_succeeded` 这 4 类高价值 claim
- `flaghunter/agents/pa_agent/ctf_dispatcher.py`
  - 工具结果与模型结论不再直接写散装事实
  - 改为先生成候选 claim，再进入 verifier 或挂入待验证队列
- `flaghunter/agents/pa_agent/coordinator.py`
  - 顶层终止条件改读 verified claim，而不是散落的 flag 状态组合
- `flaghunter/agents/pa_agent/blackboard_adapter.py`
  - blackboard 的 facts 段从旧桶结构投影为 claim 视图

**迁移策略**

第一步做“新结构上线，旧结构兼容”：

- 旧 flag 状态继续保留
- verifier 在写旧 flag 状态时同步双写 claim
- blackboard 优先消费 claim，缺失时回退旧结构

第二步做“收口”：

- 限制非 verifier 路径写 verified
- 把 `record_fact()` 之类入口降级为 `conjecture` 或 `assumption`

**主要风险**

- 双写期间语义漂移
- 旧测试大量依赖旧桶结构
- `candidate/runtime/verified/rejected` 与 `verified/conjecture/assumption/retracted` 的映射不清

**阶段验收**

- 至少 4 类关键事实已经可落为 claim
- 任一 verified 事实都能指出 verification record
- 除 verifier 外，不存在写 verified 的代码路径
- 错 flag / source-only 假阳性仍能被拦下

**禁止提前做的事**

- 不要在 P1 就大规模重写 crew
- 不要在 P1 就追求完整知识图统一

---

### 5.2 P2：补全 Trace 主干

**目标**

把当前已经不错的 append-only ledger，扩成真正的 CTF trace 主链。

**为什么第二阶段做**

P1 先定义了“事实是什么”；P2 再解决“事实是怎么来的、为什么升级、为什么被拒绝、何时回退”。

**建议交付物**

- `model_call` 事件
- `handoff_created` / `handoff_consumed` 事件
- `state_transition` 事件
- `budget_event` 事件
- `claim_created` / `claim_verified` / `claim_retracted` 事件
- trace id 与 claim id / node id / brief id / receipt id 之间的引用协议

**建议代码落点**

- `flaghunter/harness/audit_events.py`
  - 新增事件 builder
- `flaghunter/agents/pa_agent/audit_infra.py`
  - 承接统一 trace 写入口
  - 约束所有主干写入都经过这里
- `flaghunter/harness/session_ledger.py`
  - 保持 append-only，不做语义膨胀
  - 补检索辅助能力即可
- `flaghunter/llm/llm.py`
  - 包一层 `model_call` 记录点
- `flaghunter/agents/pa_agent/coordinator.py`
  - 记录 orchestrator 级决策、状态切换、预算裁决
- `flaghunter/agents/pa_agent/ctf_dispatcher.py`
  - 记录 solver 级局部状态变化与 handoff 消费

**迁移策略**

- 先补事件类型，不改现有 ledger 格式原则
- 再补事件关联字段
- 最后补 trace 查询与验收用例

**主要风险**

- prompt / output 直接落盘可能过大
- trace 过长影响性能
- 敏感信息与可观测性之间需要边界

**工程约束**

- 默认记录结构化摘要 + 引用 id
- 对超长 prompt / output 做切片、哈希或 artifact 落地
- trace 可查，但不要求所有大文本都内嵌一份

**阶段验收**

- 任一 verified flag 都能回溯到：题目输入 -> model decision -> tool call -> verification -> finish
- 任一 rejected claim 都能说明拒绝理由和对应证据
- 至少有一条测试覆盖 `model_call` 与 `state_transition`

**禁止提前做的事**

- 不要为追求 trace 完整而改写 SessionLedger 为数据库
- 不要在 P2 讨论 UI 展示层先行

---

### 5.3 P3：引入 SolveNode + TaskBrief / Receipt

**目标**

把当前“黑板驱动循环”升级为“有节点、有预算、有交接物、有回执”的求解树主干。

**为什么第三阶段做**

SolveNode 与交接物需要依赖前两阶段：

- 没有 Claim，就没有节点依赖
- 没有 Trace，就没有交接物可审计性

**建议交付物**

- 根节点 + 子节点 schema
- `TaskBrief` schema
- `Receipt` schema
- 节点状态机
- 节点预算与 spent 统计
- 节点级 checkpoint 锚点

**建议代码落点**

- `flaghunter/agents/pa_agent/coordinator.py`
  - 成为 SolveNode 树的唯一裁决者
  - 负责建根节点、分派节点、回收 receipt、处理污染传播
- `flaghunter/agents/pa_agent/ctf_dispatcher.py`
  - 作为 solver 执行体消费 `TaskBrief`
  - 输出 `Receipt`
- `flaghunter/agents/pa_agent/ctf_state.py`
  - 增加 node registry、brief registry、receipt registry
- `flaghunter/agents/pa_agent/blackboard.py`
  - 暴露节点视图、活跃方向、节点依赖 claim 视图
- `flaghunter/harness/checkpoint_store.py`
  - 从 run 级恢复扩到 node/task 级锚点

**迁移策略**

- 第一步把当前 solve loop 包进“单根节点”
- 第二步再把 agenda / hypothesis / phase 转成可衍生子节点
- 第三步让 solver 真正通过 brief/receipt 交接，而不是默认共享隐式上下文

**主要风险**

- 一次性引入完整树结构过重
- `phase`、`agenda`、`hypothesis` 与 `SolveNode` 之间映射不稳定
- 老的恢复逻辑可能与节点恢复冲突

**建议做法**

- 先只支持两层树：root + child
- 不在 P3 就追求无限深树
- 节点状态先覆盖 `open / claimed / blocked / solved_verified / abandoned / needs_recheck`

**阶段验收**

- 任一 solver 执行都能指出它处理的是哪个 node
- 任一 node 都能说明：goal、status、relevant_claims、budget、spent
- 手动 retract 一条上游 claim 后，受影响 node 会进入 `needs_recheck`

**禁止提前做的事**

- 不要在 P3 就引入复杂自动树搜索算法
- 不要为了节点模型拆散现有有效的 verifier/recovery 逻辑

---

### 5.4 P4：收敛 Blackboard / Checkpoint / Crew 协议

**目标**

让单体 CTF 与 crew 模式不再各讲各的话，而是在同一事实纪律下运行。

**为什么第四阶段做**

如果没有前面三阶段，crew 只会把不一致复制多份。P4 的本质不是“加 worker”，而是“让 worker 接入统一协议”。

**建议交付物**

- crew worker 消费同型 `TaskBrief`
- crew worker 返回同型 `Receipt`
- worker 不再写私有 verified 事实
- orchestrator 统一通过 verifier 裁决
- checkpoint 能表达“哪个 node 被哪个 worker 做到哪一步”

**建议代码落点**

- `flaghunter/agents/crew/orchestrator.py`
  - 作为并行 solver 调度层，接入同型 brief/receipt 协议
- `flaghunter/agents/crew/worker_pool.py`
  - worker runtime 继续隔离，但共享事实面改为 claim discipline
- `flaghunter/agents/crew/swarm_bridge.py`
  - 只允许传播 direction / hint / partial receipt，不传播未验证事实真相
- `flaghunter/agents/pa_agent/verifier.py`
  - 统一裁决单体与 crew 产出的 claim
- `flaghunter/agents/pa_agent/coordinator.py`
  - 单体与 crew 共用终止与回退纪律

**迁移策略**

- 先让 crew worker 只读 blackboard claim 视图
- 再让 worker 回传 receipt
- 最后收紧“共享中间过程”的自由度

**主要风险**

- worker 之间目前可能默认共享过多隐式上下文
- 性能优化与纪律收紧之间会有短期摩擦
- 多 worker 冲突 claim 的裁决机制需要先定义

**阶段验收**

- 同一道题在单体与 crew 模式下，核心输出结构同型
- worker 不能绕过 verifier 直接产出 verified
- resume 后可以定位某个 worker 对某个 node 的最近有效 receipt

**禁止提前做的事**

- 不要在 P4 前把 swarm bridge 当作权威事实源
- 不要为速度牺牲 claim/verifier 纪律

---

### 5.5 P5：学习闭环与评测闭环

**目标**

让历史解题经验真正参与未来决策，同时把“历史错误”也变成可消费资产。

**为什么最后做**

因为如果前面的事实、trace、节点、交接都不稳定，写进 memory 的就不是知识，而是噪声。

**建议交付物**

- strategy memory 命中后的 claim 降级规则
- solved challenge archive
- wrong-flag library
- wrong-strategy / trap pattern library
- 评测集上的前后对比指标

**建议代码落点**

- `flaghunter/agents/pa_agent/strategy_memory.py`
  - 明确区分 reference、assumption、verified lesson
- `flaghunter/agents/pa_agent/recovery.py`
  - 把失败原因分类与历史经验关联
- `flaghunter/harness/*`
  - 为回放、评测、回归验证提供统一入口
- `tests/eval/*`
  - 增加阶段性基准题集与稳定性评测

**阶段验收**

- 历史命中不会绕过 verifier 直接变 verified
- 至少一组题集可以观察到效率提升或错误率下降
- wrong-flag / wrong-strategy 能反向抑制重复错误

**禁止提前做的事**

- 不要在没有 claim discipline 之前扩大 strategy memory 写入规模
- 不要把 memory 当权威事实源

---

## 6. 推荐开发顺序

建议按下面顺序拆分 backlog，而不是按模块横切：

1. `Claim` / `VerificationRecord` schema 与状态迁移规则
2. verifier 升级路径与 verified 写权限收口
3. trace event 扩充与 `model_call` 打点
4. `SolveNode` 最小实现与 root-node 包裹
5. `TaskBrief` / `Receipt` 的最小单体版
6. node 级 checkpoint / resume
7. crew 协议接入
8. strategy memory 学习闭环

这个顺序的好处是：

- 每一步都能独立验收
- 每一步都能回退
- 每一步都能减少结构债，而不是制造新债

---

## 7. 建议 backlog 结构

建议把实施任务按下面 4 类维护，而不是只按文件切：

### 7.1 Schema 类

- Claim
- VerificationRecord
- SolveNode
- TaskBrief
- Receipt
- TraceEvent 引用协议

### 7.2 Control Plane 类

- coordinator 裁决逻辑
- verifier 唯一升级逻辑
- recovery 污染传播与停机逻辑
- crew protocol adapter

### 7.3 Persistence / Observability 类

- session ledger 事件扩展
- checkpoint 锚点扩展
- strategy memory 读写契约

### 7.4 Verification / Test 类

- 单元测试
- 集成测试
- 验收题集
- 评测矩阵

---

## 8. 风险管理

### 8.1 最大风险

最大的风险不是“功能写不出来”，而是：

- 新旧结构长期并存，最后谁也不敢删
- crew 提前接入，放大协议不一致
- trace 只记了一半，结果看似可观测，实则关键环节不可解释

### 8.2 风险控制手段

- 每阶段结束都关闭一批旧写入口
- 优先补测试，不允许“只改主流程不补判定”
- 每个阶段都保留回退边界，不做大爆炸合并

### 8.3 明确不建议的路线

- 不建议先做 UI 可视化
- 不建议先做更复杂的自动策略搜索
- 不建议先做更大的知识库
- 不建议先让多 agent 更聪明

当前优先级仍然只有一句话：

> 先把事实、验证、溯源、交接、回退这五条主干钉稳。

---

## 9. 阶段验收板

| 阶段 | 最小验收问题 |
|---|---|
| P1 | 这条结论是不是 Claim，谁验证了它，为什么它能是 verified？ |
| P2 | 这条 verified 结论能否完整回溯到模型、工具、验证和状态变化？ |
| P3 | 这个 solver 在做哪个 node，它收到什么任务，交回了什么 receipt？ |
| P4 | 单体和 crew 导出的核心结构是否同型，worker 能否绕过 verifier？ |
| P5 | 历史成功和历史失败是否都真正影响了后续决策质量？ |

如果某阶段无法回答对应问题，就说明该阶段还没有毕业。

---

## 10. 一页纸路线图

可以把整条路线压缩成下面 6 句话：

1. 先把 Claim 与 VerificationRecord 立起来，统一“事实”。
2. 再把 Trace 补全，统一“因果链”。
3. 再把 SolveNode 与 Brief/Receipt 立起来，统一“调度骨架”。
4. 再让 Blackboard、Checkpoint、Crew 接入同一协议，统一“运行形态”。
5. 最后再让 StrategyMemory 和评测体系接通，统一“学习闭环”。
6. 全过程都坚持：用户选模式，代码做裁决，验证层给结论，trace 负责追责。
