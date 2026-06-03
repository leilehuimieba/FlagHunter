# FlagHunter 项目级 Source-of-Truth 状态卡（2026-06-01）V1

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 角色：项目级当前事实总览 / 接手恢复卡 / 下一阶段决策底稿
>
> 最近同步：`2026-06-03`

---

## 1. 当前一句话结论

> **FlagHunter 已完成 Web Console 主路径真值化、Mode Router / Control Decision 入口合同接入、Harness 基础壳层建立，并把 start decision → first action → dispatcher_started 的第一段运行时证据落到了 trace、checkpoint、session ledger。**

这意味着当前真正需要推进的是：

- 判断能力
- 事实分层
- 调度收紧
- 样本驱动验证

---

## 2. 当前主线

当前唯一主线：

> **主控 / Blackboard-lite / 调度收紧**

这条主线的优先顺序是：

1. 先会判断
2. 再会跑
3. 最后才扩张

### 2.1 当前成熟度判断

> **项目已进入 blackboard-lite 收紧阶段，但还不是完整黑板模式。**

### 2.2 当前执行原则

- 工具调用是判断后的动作，不是起点
- CLI / 本地脚本 / Kali / runtime 是主执行面
- Web Console 是观察面 + 控制面
- TUI 不再作为重点投入对象

---

## 3. 当前已确认的事实层

### 3.1 Web Console 已进入真值化收口状态

主路径已不再依赖 mock，当前已稳定覆盖：

- Dashboard
- Logs
- Settings
- Tasks / Task Detail
- Traces / Trace Detail
- Knowledge

已接通的关键动作包括：

- create task
- hint
- stop
- retry
- continue
- runtime test
- knowledge reindex
- knowledge add doc
- knowledge open file
- MCP add server
- dashboard browse
- task detail attachment upload

### 3.2 Mode Router 与 Control Decision 已成为真实入口合同

当前 `mode / modeSubtype / goalStyle / controlDecision` 已接入：

- Web ingress
- MCP ingress
- replay / retry / continue

### 3.3 Harness 基础壳层已经存在

当前仓库已有这些真实模块：

- `session_ledger`
- `artifact_registry`
- `checkpoint_store`
- `audit_events`
- `session_context`

### 3.4 Local Challenge / artifactPaths 样本链路已经成型

当前最关键的样本输入合同：

- `challengePath`
- `artifactPaths`
- `runtime-only`
- `zip / source / docker-compose / 日志`

### 3.5 control decision 运行时证据链已稳定到第一段

当前已经被代码与测试共同钉住：

1. **ingress 优先级**
   - `verified_flag > runtime_flag > resume_context > resume_bootstrap_hint > initial_fact_collection_requested > local_assets`

2. **coordinator 首动作矩阵**
   - `verify_or_submit_flag`
   - `verify_runtime_signal`
   - `resume_from_checkpoint`
   - `collect_initial_facts`
   - `bootstrap_local_assets`

3. **当前已能回放的运行时事件**
   - `dispatcher_started`
   - 起始 checkpoint metadata
   - Web Trace `outcomeEvents`

4. **early-finish 的 verification / outcome 对齐**
   - `verify_or_submit_flag` 会补 `verification_decision`
   - `verify_runtime_signal` 会进入统一 verification 流
   - `task_finished.reason / checkpoint metadata.reason / state.stop_reason` 已完成第一轮对齐

---

## 4. 当前最关键的短板

### 4.1 还没有真正完成 Blackboard-lite

还缺少统一稳定的：

- facts
- guesses
- pending verifications
- candidate actions
- active decision
- action results（已开始从 `control_action_completed` 事件真值投影）
- recommended action（已开始基于 failed/skipped 给出 next-best 提示）

### 4.2 控制链还缺“失败反馈 / 候选切换”这一段

当前虽然已经补上了：

- `control_action_started`
- `control_action_completed`
- verified/runtime early-finish 的 verification / outcome 对齐

但还没有完整补齐：

- `wrong_flag_feedback`
- pending verification 的结构化回写
- candidate 切换理由与 next-best action 的稳定来源

### 4.3 `ctf_dispatcher.py` 仍然偏大

这是结构债务，但当前不建议脱离样本与验证单独大拆。

### 4.4 Pentest Mode 仍未进入同等级别的收口阶段

当前收紧主线更多集中在 CTF / control chain。Pentest 方向后续要补，但不是眼下第一刀。

---

## 5. 当前最值得做的事情

如果只看当前阶段，最值得做的是：

1. **继续扩 control action 事件闭环后的动作结果语义**
2. **继续补 wrong_flag_feedback → checkpoint / outcome / resume summary 的闭环**
3. **继续做 Blackboard-lite 候选动作池最小设计**
4. **用本地样本继续做最小 Eval Harness**
5. **保持文档与代码真相同步**

---

## 6. 当前环境约定

本仓库后续测试与验证，优先使用：

```powershell
.\.venv\Scripts\python.exe
```

推荐测试口径：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

不要默认使用系统 Python 去判断项目是否回归，因为那很容易把环境问题误判成代码问题。

---

## 7. 当前最接近真相的文档组合

建议优先看：

1. `D:\webstudy\FlagHunter\docs\README.md`
2. `D:\webstudy\FlagHunter\README.md`
3. `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md`
4. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_交接文档_当前主线与第一批任务_2026-06-01_V1.md`
5. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_项目状态核对与下一步讨论纪要_2026-06-03_V1.md`
6. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_下一阶段执行方案_主控_BlackboardLite_Eval三线合并_V1.md`
7. `D:\webstudy\FlagHunter\docs\dev\local_challenge_sample_matrix.md`

---

## 8. 一句话收口

> **当前项目已经不是“继续补页面”的阶段，而是进入了“先判断、再证明判断真的被执行、再用样本逼出真实缺口”的主控收紧阶段。**

