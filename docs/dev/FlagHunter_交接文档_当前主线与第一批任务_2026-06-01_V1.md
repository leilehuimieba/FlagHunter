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
- 已补 `nextActionExplanation` 顶层解释合同：`task list / detail / trace payload / replay / retry / continue` 现在都可直接返回“为什么下一步做这个动作”，前端不必再深入 `controlDecision + ingressHandoff + blackboardSnapshot`
- 已补 MCP task 文本合同里的 `next_action_*` 顶层解释：`run_task_async / list_tasks / get_task_status / get_task_result` 现在也能直接返回“下一步做什么 / 为什么 / 由谁驱动”，Web / MCP 恢复入口解释层已基本对齐
- 已补 `ctf_dispatcher` 对结构化 `ingress_handoff.nextAction` 的直接消费，内部选主策略不再只依赖 hint 字符串
- 已补 `probe_discovered_endpoint -> ingressHandoff.endpoint`，coordinator 侦察目标现在会优先消费结构化 endpoint，再回退到 hint 文本
- 已补 MCP ingress 与 Web ingress 的 `probe_discovered_endpoint` 对齐，双入口现在都会结构化传递 `endpoint`
- 已补 `collect_initial_facts` 的 structured follow-up provenance：Web / MCP handoff 现在会携带 `driver / reason / sourceType / switchedFrom / triggerReason / triggerActionDriver / triggerAt / strongestHypothesis*`，coordinator 在 hint 为空时也能直接消费
- 已补 `verify_runtime_signal / verify_or_submit_flag` 的 structured follow-up：Web / MCP handoff 现在会结构化携带 `runtimeFlag / verifiedFlag`，coordinator 在 hint 为空时也能直接 early-finish
- 已补 `resume_from_checkpoint / bootstrap_local_assets` 的 structured handoff-first：coordinator 现在在 hint 为空时也能直接消费，hint 仅保留 fallback 角色
- 已补 `backup_source_leak` 的 structured trigger 顺序收紧：当 follow-up provenance 明确指向 `source leak / backup artifact` 时，`_execute_web_chain()` 也会像 `_select_primary_strategy()` 一样，把 `backup_source_leak` 提前到 `contact_report_chain` 前执行
- 已补 `profile_photo_poisoning` 的 local-source-derived exploit truth：当不存在 runtime/backup observation、但本地源码 hint 已明确暴露 `serialize($profile) / file_get_contents($profile['photo'])` 这类模式时，dispatcher 也能恢复 `exploit_info / artifact_url`，并在 `web` 链里先尝试 `profile_photo_poisoning` 再回到 `backup_source_leak`
- 已补 Web Detail / Trace 对 `profile_photo_poisoning` local-source-derived provenance 的顶层投影：即使还没有 `source_leak_exploit_candidate` observation，只要 `local_challenge_source_hint` 已能稳定派生 exploit 类型，`exploitProvenance` 与 `outcomeEvents` 也会直接展示 `sourceType / exploitKind / artifactUrl`
- 已补 `dispatcher_started / verification_decision / task_finished` 的 exploit summary 文本收口：当前不只会展示 `exploitKind`，还会在摘要中直接带出 `sourceType`（例如 `source=local_challenge_source_hint`），前端不必只靠展开 output JSON 才能看懂 exploit 来源
- 已补 `recovery_decision` 的稳定摘要顺序：当前 recovery 摘要统一收成 `action · chain=... · from=... · hypothesis=... · exploit=... source=...`，候选切换、主假设与 exploit 来源已进入同一层可读文本
- 已补 `control_action_started / control_action_completed` 的标签化摘要：当前已统一成 `action=... / expected=... / alignment=... / driver=... / exploit=... source=...` 与 `action=... / result=... / driver=... / exploit=... source=...` 两种稳定格式，控制链执行摘要风格已开始对齐
- 已补 `checkpoint_written` 的标签化摘要与顶层 output 键：当前已统一成 `label=... · checkpoint=... · stop=...`，并在 output 顶层直接补 `checkpoint_id / checkpoint_label / stop_reason`，checkpoint / resume 信息不再只埋在嵌套对象里
- 已补 `blackboardSnapshot` 顶层可读 summary：
  - `recommendedActionSummary`
  - `candidateSummary`
  - `lastActionResultSummary`
  当前 Task Detail / Trace 不必再深入 `recommendedAction / candidates / actionResults` 内部结构，也能直接读到建议动作、候选池与最近动作结果
- 已补 `pending verification / strongest hypothesis` 顶层可读 summary：
  - `pendingVerificationSummary`
  - `strongestHypothesisSummary`
  当前 Task Detail / Trace 不必再深入 `pendingVerifications / hypotheses / decisionProvenance` 内部结构，也能直接读到待验证信号与当前最强假设
- 已补 `suppressed recommendation / active decision` 顶层可读 summary：
  - `suppressedRecommendationSummary`
  - `activeDecisionSummary`
  当前 Task Detail / Trace 不必再深入 `controlDecision.suppressedRecommendation / activeDecision` 内部结构，也能直接读到被压制的建议动作与当前执行中的主控决策
- 已补列表层轻量主控摘要：
  - `/api/tasks` 已直接补 `activeDecisionSummary`
  - `dashboard.recentTasks` 已直接补 `nextActionSummary / activeDecisionSummary`
  当前列表层不必再点进 detail，也能直接看出任务的主控方向与下一步
- 已补列表层 resume / checkpoint / runtime outcome 轻量状态：
  - `/api/tasks` 与 `dashboard.recentTasks` 已直接补
    - `resumeStateSummary`
    - `checkpointStateSummary`
    - `runtimeOutcomeSummary`
  当前列表层不必再点进 detail/trace，也能直接看出任务是否从 resume 进入、最新 checkpoint 是什么、当前运行结果轻量态是什么
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
   - 当前返回合同：`continue` 接受响应里的 `nextActionExplanation` 表达“此刻为什么接受继续 / 当前准备执行什么”，而 task detail / trace 继续表达刷新后的持久 decision truth

10. **retry / replay follow-up 收紧**
   - `retry / replay` 不再一刀切覆盖 `resume_execute`
   - 只有在 blackboard 已给出明确 `recommendedAction.action` 时，才改走 next-best action
   - 没有 recommendation 的恢复场景，仍保持原先 `resume_execute` 合同

11. **recovery next action 顶层解释合同**
   - `Task list / Task Detail / Trace payload / replay / retry / continue`
     已可顶层返回 `nextActionExplanation`
   - 当前字段：
     - `decisionKind / nextAction / driver / reason`
     - `sourceType / switchedFrom / triggerReason`
     - `summary`
   - 恢复类入口与前端不必再手工回拼 `controlDecision + ingressHandoff + decisionProvenance`

12. **MCP recovery next action 文本合同**
   - `run_task_async / list_tasks / get_task_status / get_task_result`
     现已可直接输出：
     - `next_action_decision_kind`
     - `next_action`
     - `next_action_driver`
     - `next_action_reason`
     - `next_action_summary`
   - MCP 侧检查与异步提交结果现在不必再靠 `control_decision + blackboard` 手工脑补恢复动作解释

13. **blackboard-lite 顶层可读摘要**
   - `Task Detail` 已有：
     - `recommendedActionSummary`
     - `candidateSummary`
     - `lastActionResultSummary`
   - `Trace payload` 已有：
     - `recommendedActionSummary`
     - `candidateSummary`
     - `lastActionResultSummary`
   - 当前已能直接表达：
     - 建议动作是什么、由谁驱动、从哪条动作切来
     - 当前候选池规模、active / recommended action
     - 最近一次动作结果、alignment 与失败原因
     - 当前待验证数量、最新待验证 kind/source/rationale
     - 当前最强假设的 kind/status/confidence
     - 当前被压制建议动作的 action/driver/suppressedBy
     - 当前 active decision 的 decisionKind/nextAction/driver 与 observedAction/alignment
     - 列表层任务当前的 next action summary
     - 列表层任务当前的 active decision summary
     - 列表层任务当前的 resume state summary
     - 列表层任务当前的 checkpoint state / runtime outcome summary

11. **dispatcher 结构化 follow-up 消费**
   - `ctf_dispatcher` 选主策略时，已开始直接读取 `ingress_handoff.nextAction`
   - 当前已接通：
     - `exploit_identified_engine`
     - `validate_leaked_secret`
     - `probe_discovered_endpoint`（通过 `ingressHandoff.endpoint` 把 recon target 结构化传给 coordinator）
   - 对这批 follow-up，结构化 truth 现在优先于 hint 字符串脆弱匹配
   - 最新补强：当 `nextAction` 退化回 `collect_initial_facts` 时，dispatcher 现在还能继续读取 `switchedFrom / triggerReason / triggerActionDriver`，把 `probe_discovered_endpoint -> collect_initial_facts` 这类结构化 provenance 再收回到高价值策略（例如 `ssti_exploit` / `hash_guarded_file_read` / `backup_source_leak`），以及在 `xss` 链中恢复 `visit-url` fallback、在 `web` 链中恢复 `hint_chain_followup`
   - `StrategyContext` 现在也会优先从真实 observation 注入 `cookie_secret_leaked -> extras.cookie_secret`，使 `hash_reconstruction_attack` 不再只依赖显式参数透传
   - `profile_photo_poisoning` 现在不再只依赖 `source_leak_exploit_candidate` observation；当本地源码 hint 已经给出稳定利用信号时，dispatcher 也会从 `local_challenge_source_hint` 直接恢复 exploit info，并把这条 exploit-heavy runtime 尝试提前到 backup fallback 前
   - Web Detail / Trace 现在也不再只依赖 `source_leak_exploit_candidate` observation 才能展示 exploit 来源；当 exploit truth 仅来自 `local_challenge_source_hint` 时，顶层 `exploitProvenance` 与 `control_action_* outcomeEvents` 也会保留这条 local-source-derived provenance
   - `dispatcher_started / verification_decision / task_finished` 的 summary 文本现在也会直接标出 exploit 来源类型；local-source-derived exploit truth 不再只埋在 output JSON 里，而是进入一眼可读的摘要层
   - `recovery_decision` 的 summary 现在也统一成标签化顺序，不再只是松散堆叠字符串；前端可直接从摘要读到 recovery action、来源切换、主假设与 exploit 来源
   - `control_action_started / completed` 的 summary 也已标签化；前端现在可直接从摘要读到 action、expected/result、alignment、driver 与 exploit source，而不用靠 output JSON 反推执行语义
   - `checkpoint_written` 的 summary / output 也已同步收口；前端现在可直接从摘要读到 checkpoint 标签、checkpoint id 与 stop reason，并在 output 顶层直接读取对应键

### 4.4 本地样本主线已成型

当前最关键的样本输入合同：

- `challengePath`
- `artifactPaths`
- `runtime-only`
- `zip / source / docker-compose / 日志`

当前更值得继续追的高价值缺口：

- 把 structured provenance 继续压进 dispatcher 更多策略分支，而不是停在 `nextAction` 字面匹配
- 继续让 follow-up 在退化到泛化动作时，也能靠 `switchedFrom / triggerReason / triggerActionDriver` 恢复高价值决策
- `php_unserialize` 现已开始走 observation-first：backup/source 分析得到的 exploit candidate 会先落为 `source_leak_exploit_candidate`，后续 `web` 链与 `StrategyContext` 再优先从 observation 恢复 `exploit_info / artifact_url`
- `profile_photo_poisoning` 现也开始走 observation-first：backup/source 分析出的 exploit candidate 会先落为 `source_leak_exploit_candidate`，后续 `web` 链会优先从 observation 恢复 `exploit_info / artifact_url` 再尝试 runtime 利用
- Web Console / Trace Detail 现已开始把 exploit truth-source 顶层投影为 `exploitProvenance`，前端不必再深入翻 `ctfStateSnapshot.observations` 才能知道当前 exploit 是从哪类事实恢复出来的
- Web Trace `outcomeEvents` 现也会继承 `exploitProvenance`：`dispatcher_started` 与 `control_action_started / completed` 的 summary / output 已能直接看到 `exploitKind / observationSource / artifactUrl`，事件流阅读不必再回跳顶层 payload
- Web Trace `outcomeEvents` 的失败反馈段也已开始 truth-first：`verification_decision / recovery_decision / task_finished` 现在会继承 `exploitProvenance + actionPathSummary`，可直接读到 `exploitKind / strongestHypothesis / switchedFrom / triggerReason`
- Web Trace `checkpoint_written` 也已开始继承 resume truth：即使 `sessionContext.resumeContext` 为空，也会从 `runId + latestCheckpoint` 兜底恢复 `resume_context / resume_summary`，Trace Detail 可直接看 checkpoint 与后续 resume 入口合同
- `resumeIngress` 现也已提升为 Task Detail / Trace 顶层合同：即使 session context 里还没预先投影 `resumeIngress`，也会从 `dispatcher_started` 事件兜底恢复 `runId / checkpointId / sourceEvent / stopReason / summary`
- `CTFState.from_snapshot` 现已改为忽略未知字段后再恢复，避免 detail/trace 因快照里混入非 dataclass 字段而把整份 state 吞空

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


## 9. 当前 CTF skills 状态（2026-06-04）

### 9.1 已完成的技能层收口

本轮已完成：

- 新增并收紧 `C:\Users\33371\.codex\skills\ctf-orchestrator\SKILL.md`
- 重写 `C:\Users\33371\.codex\skills\ctf-web\SKILL.md`

当前分层已明确：

- `ctf-orchestrator`
  - 负责主控判断
  - 负责 facts / hypotheses / recovery signals / candidate actions 分层
  - 负责决定当前是恢复旧链、走最短链、还是补最低成本事实
- `ctf-web`
  - 负责 Web 主面的具体执行
  - 负责 source / artifact / runtime 三者之间的最小实验推进
  - 明确依赖 orchestrator，而不是再回到传统漏洞清单式工作流

### 9.2 当前保留 / 重写 / 新增结论

保留：
- `ctf-crypto`
- `ctf-reverse`
- `ctf-misc`
- `ctf-tools-local`
- `local-agent-harness`

已新增 / 已重写：
- 新增：`ctf-orchestrator`
- 重写：`ctf-web`

下一步更值得继续的 skill 方向：
- `ctf-knowledge-writeback`
- `ctf-eval-replay`

### 9.3 这对当前代码主线的意义

这次 skill 收口，不是单纯补文档，而是在技能层把当前仓库主线正式表达清楚：

- 当前不是“见题就扫工具”
- 而是“主控先判断，再由题型层打穿”
- 当前 dispatcher / blackboard-lite / structured provenance 的代码方向，与新的 `ctf-orchestrator -> ctf-web` 分层是一致的

### 9.4 下一条最自然的代码主线

在 skills 收口完成后，下一条最值得继续压的代码缺口仍然是：

- 把 structured provenance 继续压进 exploit-heavy dispatcher 分支
- 尤其是让退化 follow-up 也能继续恢复高价值 exploit 分支，而不是回到泛化收集动作
