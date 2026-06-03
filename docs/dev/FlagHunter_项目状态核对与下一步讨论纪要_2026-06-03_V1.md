# FlagHunter 项目状态核对与下一步讨论纪要（2026-06-03）V1

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 文档角色：**暂停继续开发时的讨论结论落地稿 / 下一阶段主线对齐稿**

---

## 1. 这次讨论想确认什么

这次不继续扩功能，只确认 4 件事：

1. 当前代码真实推进到了哪一步
2. 项目现在是否已经进入“黑板模式”
3. 下一阶段应该优先收哪条主线
4. 接下来开发应该按什么节奏继续

---

## 2. 代码事实核对结论

本轮抽样核对了这些关键位置：

- `D:\webstudy\FlagHunter\pentestagent\interface\control_contract.py`
- `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`
- `D:\webstudy\FlagHunter\pentestagent\mcp\server\mcp_tools.py`
- `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\coordinator.py`
- `D:\webstudy\FlagHunter\pentestagent\harness\audit_events.py`
- `D:\webstudy\FlagHunter\tests\unit\agents\test_ctf_coordinator.py`
- `D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py`

当前最重要的事实是：

### 2.1 入口控制合同已经真实存在

不是只在文档里提 `mode` / `controlDecision`，而是已经实际进入：

- Web ingress
- MCP ingress
- replay / retry / continue 派生链路

### 2.2 coordinator 已经在消费“首动作”

当前 `first action` 已被测试和代码同时钉住，至少包括：

- `verify_or_submit_flag`
- `verify_runtime_signal`
- `resume_from_checkpoint`
- `collect_initial_facts`
- `bootstrap_local_assets`

### 2.3 start decision 的运行时投影已经打通第一段

现在已经能在这些位置看到起始决策：

- `dispatcher_started` session ledger 事件
- 起始 checkpoint metadata
- Web Trace `outcomeEvents`

这说明项目已经从“能解释为什么这么做”，推进到“能回放它一开始决定做什么”。

### 2.4 early-finish 的 verification / checkpoint / outcome 已完成第一轮对齐

本轮已经补齐并验证：

- `verify_or_submit_flag` 的 early-finish 会写入 `verification_decision`
- `verify_runtime_signal` 的 early-finish 会进入统一 verification 流
- 最终 `task_finished.reason`
- 最终 checkpoint `task_finished.metadata.reason`
- `state.stop_reason`

这三层现在已经能保持一致。

这说明项目不只是“知道先做什么”，而是开始具备：

> **当主控直接命中 verified/runtime flag 时，也能把验证、结束原因、最终断点写成一条一致的事实链。**

---

## 3. 我们现在是不是“黑板模式”

结论很明确：

> **还不是完整黑板模式，但已经进入 blackboard-lite 收紧阶段。**

### 3.1 为什么说“不是完整黑板”

因为现在还没有真正统一的项目级共享板，把下面这些东西稳定分层并持续驱动全链路：

- facts
- guesses
- pending verifications
- active decision
- candidate actions
- action results

### 3.2 为什么又说“已经进入 blackboard-lite 阶段”

因为现在已经有了足够明显的前置骨架：

- ingress 决策合同
- first-action 选择
- ledger / artifact / checkpoint / trace
- `blackboard_lite.py` 的基础投影
- local challenge / artifact ingress 真值化

所以当前更准确的说法是：

> **方向上在借鉴 Cairn 的 blackboard + dispatcher 思想，但实现上是 FlagHunter 自己的 blackboard-lite 收紧路线，不是照抄，也还没一步到位。**

---

## 4. 现在最值得推进的主线是什么

当前唯一主线仍然是：

> **主控 / Blackboard-lite / 调度收紧**

但需要把它拆成更可执行的顺序：

### P0：控制链执行证据闭环

最小切口：

- `control_action_started`
- `control_action_completed`

目标：

- 证明 first action 真的开始执行
- 证明 first action 是否完成 / 跳过 / 失败
- 让 trace / ledger / checkpoint 看到同一条事实链

当前新增进展：

- verified/runtime flag 的 early-finish 已补 `verification_decision`
- 最终 `task_finished` 与 final checkpoint reason 已完成第一轮对齐
- 下一刀更值得做的是 `wrong_flag_feedback` 的结构化闭环

### P1：Blackboard-lite 候选动作池

最小切口：

- facts
- candidates
- active decision
- action results

目标：

- 不再只有单条 `nextAction`
- 主控能说清楚主路径与备选路径

### P2：最小 Eval Harness

最小切口：

- 继续使用 `challengePath + artifactPaths`
- 增加 1~2 个最小真实样本
- 能区分：主控问题 / 工具问题 / 知识问题 / 上下文问题

---

## 5. 当前不再优先投入什么

下一阶段先不做：

- TUI 继续投入
- 没有样本牵引的大重构
- 单纯为了“好看结构”去拆 dispatcher
- 大量新增 MCP 依赖
- 继续把重点放在前端按钮数量

说明：

- Web Console 继续保留为观察面 + 控制面
- CLI / 本地脚本 / Kali / runtime 是主执行面
- 工具尽量偏底层与本地可复用，不优先绑定高成本外部应用

---

## 6. 接下来开发应该按什么节奏继续

建议保持这条节奏，不再频繁切换：

1. 主控盘点最高价值缺口
2. 先做最小设计
3. TDD：RED → GREEN
4. 窄回归
5. `git diff --stat`
6. commit / push
7. 同步交接文档 / 状态卡 / 总入口

这条节奏的目标是：

- 不失控扩 scope
- 不让代码和文档脱节
- 不让“看起来合理”替代“已验证有效”

---

## 7. 当前一句话判断

> **FlagHunter 现在的发展方向，确实在朝“主控判断优先、blackboard-lite 收紧、样本驱动验证”的路线走；它借鉴了 Cairn，但不是简单照搬，当前最值得继续的是把 wrong_flag_feedback 与候选动作层继续收紧。**

