# FlagHunter 交接文档：当前主线与第一批任务（2026-06-01）V1

> 适用仓库：`D:\webstudy\FlagHunter`
>
> 文档角色：**随时可交接的当前执行底稿**
>
> 最近同步：`2026-06-04`

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
- 已补 verified/runtime early-finish 的 `verification_decision`
- 已补 `task_finished.reason / final checkpoint reason / state.stop_reason` 第一轮对齐
- 已补 `wrong_flag_feedback -> rejected_flags -> resume summary` 这一层
- 已补 strongest hypothesis 贯通：
  - ingress hint
  - `dispatcher_started`
  - `control_action_started / completed`
  - `blackboardSnapshot.activeDecision / actionResults`
  - Trace Detail `outcomeEvents`
- 已补 `recommendedAction -> strongest hypothesis` 继承，候选切换后仍能带着主控上下文继续流转
- 已补 `candidates.selected / candidates.recommended -> strongest hypothesis`，候选动作池已开始带解释上下文
- 已补 `recommendedAction.triggerActionDriver / triggerAt`，候选切换已能追到触发它的动作结果
- 已补 `candidates / recommendedAction.sourceType`，当前可区分 `observation / verification / ingress`
- 已补 `control_contract <- recommendedAction.sourceType / trigger provenance` 消费，黑板解释字段已开始进入实际决策层
- 已补 Task Detail / Trace 顶层 `decisionProvenance` summary，前端不必再深入 `blackboardSnapshot.recommendedAction` 或 `controlDecision.facts` 才能读到来源与 strongest hypothesis
- 已补 `recommendedActionSwitchedFrom / recommendedActionTriggerReason`，候选切换的“从哪切来 / 因为什么切”已进入 `controlDecision.facts` 与 `decisionProvenance`
- 已补 `recommendedActionSwitchedFrom / recommendedActionTriggerReason -> dispatcher_started / control_action_started / control_action_completed`，follow-up provenance 已进入 runtime 证据链
- 已补 blackboard 从 runtime 事件重建 `activeDecision / actionResults` 时投影 `switchedFrom / triggerReason`
- 已补 Task Detail / Trace Detail 顶层 `actionPathSummary`，当前执行路径不必再从 `activeDecision + decisionProvenance` 手工拼接
- 已补 `continue` 入口的 follow-up refresh：同任务继续时，若已有 `recommendedAction`，会刷新 `controlDecision / ingressHandoff`，避免继续沿旧失败动作死跑
- 已补 `retry / replay` 的 follow-up refresh：**仅在 blackboard 确有 `recommendedAction.action` 时** 才刷新 follow-up；否则继续保留原本的 `resume_execute` 语义
- 已补 `ctf_dispatcher` 对结构化 `ingress_handoff.nextAction` 的直接消费，内部选主策略不再只依赖 hint 字符串
- 已补 `probe_discovered_endpoint -> ingressHandoff.endpoint`，coordinator 侦察目标现在会优先消费结构化 endpoint，再回退到 hint 文本
- 已补 MCP ingress 与 Web ingress 的 `probe_discovered_endpoint` 对齐，双入口现在都会结构化传递 `endpoint`
- 已补 `collect_initial_facts` 的 structured follow-up provenance：Web / MCP handoff 现在会携带 `driver / reason / sourceType / switchedFrom / triggerReason / triggerActionDriver / triggerAt / strongestHypothesis*`，coordinator 在 hint 为空时也能直接消费
- 已补 `verify_runtime_signal / verify_or_submit_flag` 的 structured follow-up：Web / MCP handoff 现在会结构化携带 `runtimeFlag / verifiedFlag`，coordinator 在 hint 为空时也能直接 early-finish
- 已补 `resume_from_checkpoint / bootstrap_local_assets` 的 structured handoff-first：coordinator 现在在 hint 为空时也能直接消费，hint 仅保留 fallback 角色
- 当前 control chain 首段主路径（resume / bootstrap / collect / verify / probe）已基本完成 structured handoff-first，后续更值得继续把 provenance 压进 dispatcher 内部策略选择
- 下一步继续补候选动作层 / 切换理由稳定来源与前端更直接展示

完成标准：

- 不只是“决定做什么”
- 还能证明“真的开始做了什么、做完了什么、结果是什么”

### P1：Blackboard-lite 候选动作池

当前已落地第一刀：

- `blackboardSnapshot.candidates`
- `blackboardSnapshot.activeDecision`
- `blackboardSnapshot.actionResults` / candidate `lastResult`
- `blackboardSnapshot.recommendedAction` / candidate `recommended`

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

4. **early-finish 对齐**
   - `verify_or_submit_flag` / `verify_runtime_signal` 现在都会把 verification 写回统一事实链
   - final outcome 与 final checkpoint reason 已对齐

5. **wrong_flag_feedback 对齐**
   - final checkpoint metadata 已带 `rejected_flags`
   - session context / resume summary 已能读到 rejected flag

6. **decision provenance 顶层投影**
   - `Task Detail` 已有 `decisionProvenance`
   - `Trace Detail` 已有 `decisionProvenance`
   - 当前字段：
     - `recommendedActionSourceType`
     - `recommendedActionSwitchedFrom`
     - `recommendedActionTriggerReason`
     - `recommendedActionTriggerActionDriver`
     - `recommendedActionTriggerAt`
     - `strongestHypothesisKind / Status / Confidence`

7. **follow-up provenance 运行时闭环**
   - `dispatcher_started` 已带 `switched_from / trigger_reason`
   - `control_action_started / completed` 已带 `switched_from / trigger_reason`
   - blackboard 可从 session runtime events 重建这两项事实

8. **runtime action path 顶层投影**
   - `Task Detail` 已有 `actionPathSummary`
   - `Trace Detail` 已有 `actionPathSummary`
   - 当前字段：
     - `decisionKind / decisionDriver`
     - `plannedAction / observedAction / effectiveAction`
     - `alignment / alignmentReason`
     - `switchedFrom / triggerReason`
     - `strongestHypothesisKind / Status / Confidence`

9. **continue follow-up 收紧**
   - `continue` 不再只写 `resume` 线索
   - 当 blackboard 已有 `recommendedAction` 时，会刷新同任务的 `controlDecision`
   - 当前行为：优先避免继续沿旧失败动作重复推进

10. **retry / replay follow-up 收紧**
   - `retry / replay` 不再一刀切覆盖 `resume_execute`
   - 只有在 blackboard 已给出明确 `recommendedAction.action` 时，才改走 next-best action
   - 没有 recommendation 的恢复场景，仍保持原先 `resume_execute` 合同

11. **dispatcher 结构化 follow-up 消费**
   - `ctf_dispatcher` 选主策略时，已开始直接读取 `ingress_handoff.nextAction`
   - 当前已接通：
     - `exploit_identified_engine`
     - `validate_leaked_secret`
     - `probe_discovered_endpoint`（通过 `ingressHandoff.endpoint` 把 recon target 结构化传给 coordinator）
   - 对这批 follow-up，结构化 truth 现在优先于 hint 字符串脆弱匹配
   - 最新补强：当 `nextAction` 退化回 `collect_initial_facts` 时，dispatcher 现在还能继续读取 `switchedFrom / triggerReason / triggerActionDriver`，把 `probe_discovered_endpoint -> collect_initial_facts` 这类结构化 provenance 再收回到高价值策略（例如 `ssti_exploit` / `hash_guarded_file_read` / `backup_source_leak`）

### 4.4 本地样本主线已成型

当前最关键的样本输入合同：

- `challengePath`
- `artifactPaths`
- `runtime-only`
- `zip / source / docker-compose / 日志`

当前更值得继续追的高价值缺口：

- 把 structured provenance 继续压进 dispatcher 更多策略分支，而不是停在 `nextAction` 字面匹配
- 继续让 follow-up 在退化到泛化动作时，也能靠 `switchedFrom / triggerReason / triggerActionDriver` 恢复高价值决策

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

> **当前项目已从“Web 真值化收口”进入“主控判断收紧 + blackboard-lite 落地 + 调度收短”的下一阶段；下一批任务优先补候选动作池与切换依据，再做最小 Eval Harness。**

