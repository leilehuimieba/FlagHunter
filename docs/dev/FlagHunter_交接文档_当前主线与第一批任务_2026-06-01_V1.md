# FlagHunter 交接文档：当前主线与第一批任务（2026-06-01）V1

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 文档角色：**随时可交接的当前执行底稿**
>
> 最近同步：`2026-06-03`

---

## 1. 当前一句话状态

> **FlagHunter 已经完成 Web Console 真值化收口、Mode Router / Control Decision 入口合同接入、Harness 基础壳层建立，并把 control decision → first action → dispatcher_started 链接到了 trace / checkpoint / session ledger。**

这意味着当前阶段不应该继续把重点放在：

- 继续加 TUI
- 继续加页面动作
- 继续扩复杂 MCP
- 不带样本的大重构

而应该放在：

- 主控判断能力
- Blackboard-lite 事实分层
- 调度链路收短
- 本地样本驱动验证

---

## 2. 当前主线

### 2.1 唯一主线

> **主控 / Blackboard-lite / 调度收紧**

### 2.2 当前成熟度判断

> **这是 blackboard-lite 收紧阶段，不是完整黑板模式。**

### 2.3 主线顺序

1. 先会判断
2. 再会跑
3. 最后才扩张

---

## 3. 当前最小任务优先级

### P0：控制链执行证据闭环

最小目标：

- 已补 `control_action_started`
- 已补 `control_action_completed`
- 下一步继续补结果细节与候选动作层

完成标准：

- 不只是“决定做什么”
- 还能证明“真的开始做了什么、做完了什么、结果是什么”

### P1：Blackboard-lite 候选动作池

当前已落地第一刀：

- `blackboardSnapshot.candidates`
- `blackboardSnapshot.activeDecision`
- `blackboardSnapshot.actionResults` / candidate `lastResult`

下一步目标：

- 让候选动作不只是投影，还能反向喂给后续调度与评估

完成标准：

- 不再只有单条 `nextAction`
- 主控能给出主路径与备选路径

### P2：最小 Eval Harness

最小目标：

- 用 `challengePath + artifactPaths` 继续跑真实样本
- 至少再补 1~2 个低成本样本
- 能区分主控问题 / 工具问题 / 知识问题 / 上下文问题

完成标准：

- 至少有一批样本能稳定复跑
- 每次问题都能落回可解释的主链缺口

---

## 4. 当前已确认的事实层

### 4.1 Web Console 已真值化收口

主路径：

- Dashboard
- Logs
- Settings
- Tasks / Task Detail
- Traces / Trace Detail
- Knowledge

已接通动作：

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

### 4.2 Mode Router 已接入真实入口合同

当前 `mode / modeSubtype / goalStyle` 已进入：

- Web
- MCP
- replay / retry / continue

### 4.3 Control Decision 主链已进入“可回放第一段”状态

当前已经稳定的真实链路包括：

1. **入口优先级**
   - `verified_flag > runtime_flag > resume_context > resume_bootstrap_hint > initial_fact_collection_requested > local_assets`

2. **coordinator 首动作合同**
   - `verify_or_submit_flag`
   - `verify_runtime_signal`
   - `resume_from_checkpoint`
   - `collect_initial_facts`
   - `bootstrap_local_assets`

3. **运行时证据回放**
   - `dispatcher_started` 事件
   - 起始 checkpoint metadata
   - Web Trace `outcomeEvents`

### 4.4 本地样本主线已成型

当前最关键的样本输入合同：

- `challengePath`
- `artifactPaths`
- `runtime-only`
- `zip / source / docker-compose / 日志`

---

## 5. 当前明确不做

当前先不做：

- TUI 重点投入
- 继续优先加页面按钮
- 复杂 MCP 扩张
- 没有样本牵引的大重构
- 先扩功能再补判断

---

## 6. 当前维护规则

### 6.1 文档更新顺序

以后更新按这个顺序来：

1. 先确认代码事实
2. 再更新交接文档
3. 再更新状态卡
4. 再更新入口文档
5. 最后再推进实现

### 6.2 解释器约定

本仓库后续测试与验证，优先使用：

```powershell
.\.venv\Scripts\python.exe
```

推荐测试口径：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

---

## 7. 接手顺序

如果要交接给下一位接手者，建议按这个顺序读：

1. `D:\webstudy\FlagHunter\docs\README.md`
2. `D:\webstudy\FlagHunter\README.md`
3. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_项目级source-of-truth状态卡_2026-06-01_V1.md`
4. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_项目状态核对与下一步讨论纪要_2026-06-03_V1.md`
5. `D:\webstudy\FlagHunter\docs\dev\FlagHunter_下一阶段执行方案_主控_BlackboardLite_Eval三线合并_V1.md`
6. `D:\webstudy\FlagHunter\docs\dev\local_challenge_sample_matrix.md`

---

## 8. 一句话交接摘要

> **当前项目已从“Web 真值化收口”进入“主控判断收紧 + blackboard-lite 落地 + 调度收短”的下一阶段；下一批任务优先补 control action 事件闭环，再做候选动作池与最小 Eval Harness。**

