# FlagHunter 下一阶段执行方案：主控 / Blackboard-lite / Eval 三线合并 V1

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 文档角色：**下一阶段实际执行方案 / 讨论结论落地稿 / 后续任务排序依据**
>
> 当前结论：**下一阶段不再平均用力，而是围绕“主控判断能力”组织三条主线，并按先后顺序推进。**

---

## 1. 这份文档回答什么

只回答五件事：

1. 当前项目已经做到了哪一步
2. 接下来为什么不能再散着补功能
3. 下一阶段真正要做的三条主线是什么
4. 三条主线的先后顺序和最小任务是什么
5. 什么先不做

---

## 2. 当前状态判断

当前项目已经完成了一条比较清楚的底层收口链：

1. **入口判定已显式化**
   - `mode`
   - `controlDecision`
   - `driver / reason / facts`

2. **首动作已开始真实消费**
   - `verify_or_submit_flag`
   - `verify_runtime_signal`
   - `resume_from_checkpoint`
   - `collect_initial_facts`
   - `bootstrap_local_assets`

3. **运行时证据链已开始成型**
   - blackboard facts
   - session ledger
   - checkpoint
   - trace timeline / outcomeEvents

4. **测试护栏已形成主干**
   - ingress priority matrix
   - coordinator first-action matrix
   - Web / MCP ingress e2e
   - trace / checkpoint / run-start 事件回归

这说明当前项目的主要矛盾已经不是“有没有功能”，而是：

> **agent 会不会判断、能不能按判断去执行、执行后能不能把事实重新写回系统。**

---

## 3. 下一阶段的核心判断

### 3.1 真正的问题不是“能不能跑”

工具面、runtime、CLI、Kali、本地脚本这些执行能力已经不算弱。

下一阶段真正决定效果的，是下面这些问题：

- 为什么先看这个点，不看那个点
- 当前哪些是事实，哪些只是猜测
- 多条路径里为什么先选这一条
- 什么时候该停
- 什么时候该换路线
- 什么时候该调用知识
- 什么时候该开子代理，什么时候不该开

### 3.2 结论

> **接下来应该先做“主控判断能力”，而不是继续平均扩功能。**

---

## 4. 三条主线

---

### 主线 A：主控 / Blackboard-lite / 调度收紧

这是下一阶段的**第一优先级**。

目标不是做一个重型黑板系统，而是先做一个够用的 `Blackboard-lite`：

1. **事实池**
   - 当前已经确认的事实
   - 来源
   - 置信度
   - 时间顺序

2. **候选动作池**
   - 当前有哪些可做路径
   - 每条路径为什么值得做
   - 哪条是主路径
   - 哪条是备选路径

3. **主控决策器**
   - 当前一步最该做什么
   - 为什么是这一步
   - 为什么不做其他路径

4. **动作回写**
   - 动作开始
   - 动作完成
   - 是否改变事实池

5. **停止 / 切换条件**
   - 无进展
   - 新线索压过旧线索
   - 已拿到 flag
   - 已经形成足够证据

#### 这条线当前已经有的基础

- `controlDecision`
- first-action matrix
- session ledger / checkpoint / trace start event
- truth-source / driver / facts

#### 这条线下一步最小任务

1. `control_action_started`
2. `control_action_completed`
3. candidate queue（候选动作池）
4. next-best-action 选择函数

---

### 主线 B：样本驱动 Eval / Harness

这是第二优先级，但要尽快跟上。

原因很简单：

> 如果没有真实样本，后面的优化很容易变成“结构上看起来更对”，但不一定更能做题、更能给证据。

#### 最小 Eval 包建议

##### CTF

- 1 个 Web 题
- 1 个 Misc / Forensics 或 Crypto 题

输入尽量保持最小：

- 题目链接
- 压缩包
- 或 challenge root

##### Pentest

- 1 个授权 web 靶场
- 1 个服务/主机型小目标

#### Eval 重点不只是结果

不只看“拿没拿到 flag / 是否有漏洞结论”，还要看：

1. 是否先建立事实
2. 是否优先做高价值路径
3. 是否乱用工具
4. 是否能在失败后切换路径
5. 是否能把结果沉淀成可复用知识

---

### 主线 C：本地知识库 / 上下文编排

这是第三优先级，建议跟主线 A 并行少量推进，但不要单独大跃进。

#### 知识分层建议

1. **长期知识**
   - CTF 技法
   - Pentest 方法
   - 工具说明
   - 历史题目总结

2. **当前任务知识**
   - local challenge assets
   - 当前 run 已确认事实
   - 当前 run 的关键结论

3. **运行时临时记忆**
   - 当前主路径
   - 最近失败原因
   - 当前优先的 3 个动作

#### 核心原则

- facts 和 guesses 分开
- 长期知识和当前事实分开
- 大结果外置为 artifact
- 上下文只带当前必要信息

---

## 5. 下一阶段建议顺序

### Phase 1：主控动作证据闭环

先把：

- `control_action_started`
- `control_action_completed`

补到：

- session ledger
- checkpoint metadata
- trace / outcomeEvents

#### 完成标准

- 不只是“决定做什么”
- 还能证明“真的开始做了什么、做完了什么、结果是什么”

---

### Phase 2：Blackboard-lite 候选池

补：

- facts
- candidates
- active_decision
- action_results

#### 完成标准

- 系统能明确说出当前主路径和备选路径
- 候选动作不再只是一条 `nextAction`

---

### Phase 3：最小 Eval Harness

把前两阶段的判断链拿去跑最小真实样本。

#### 完成标准

- 至少 1~2 个真实样本可以稳定复跑
- 能定位是主控问题、工具问题、知识问题还是上下文问题

---

### Phase 4：基于 Eval 修判断逻辑

后续不再凭感觉加功能，而是只修真实瓶颈。

---

## 6. 当前明确不做什么

下一阶段先不做：

- TUI 继续投入
- 大规模前端美化
- 没有样本牵引的大重构
- 无约束扩工具
- 过早扩复杂多智能体

### 多智能体的态度

可以用，但要满足：

1. 任务可以明显并行
2. 任务之间低耦合
3. 有明确合并边界
4. 主控能解释为什么值得并行

---

## 7. 当前最值得立即推进的最小任务清单

### P0

1. `control_action_started / completed`
2. start decision → first action → outcome 的事件链闭环
3. Blackboard-lite candidate queue 最小设计

### P1

4. easy_login 之外再补 1 个最小 eval 样本
5. 本地知识 / 事实 / 临时记忆分层设计

### P2

6. 再讨论子代理策略与约束

---

## 8. 对接下来开发节奏的建议

建议继续保持现在这套节奏：

1. 盘点最高价值缺口
2. TDD：RED → GREEN
3. 窄回归
4. `git diff --stat`
5. commit / push
6. 同步交接文档与状态卡

---

## 9. 一句话收口

> **下一阶段不要再平均扩功能，而要围绕“主控判断能力”推进三条主线：先收紧 Blackboard-lite 与调度，再用真实样本做 eval，最后再优化知识与上下文。**

