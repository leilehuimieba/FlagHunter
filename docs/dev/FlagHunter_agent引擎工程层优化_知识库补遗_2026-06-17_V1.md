# FlagHunter agent 引擎工程层优化（知识库补遗）V1

- 日期：2026-06-17
- 定位：[[FlagHunter_红队智能体架构_对标顶级红队工程学_2026-06-17_V2]] 的**工程层补遗**
- 来源：本地 AI-Agent 知识库 `D:\newwork\AI-Agents\aiagentstudy`（4091 篇 md，6 主题）四路挖掘
- 适用：`D:\webstudy\FlagHunter`

---

## 0. 这份文档补的是什么

V2 讲的是**红队领域知识**（怎么"想"——ATT&CK/Kill-Chain/Diamond/攻击图/验证优先）。
本文补的是 V2 漏掉的另一半:**把 agent 引擎本身做到顶级的工程学**（怎么"造"——记忆/上下文、运行时控制面、评估护栏、工具/动作）。

> 知识库里多条目**显式提到 FlagHunter**(引用了我们的 `stop_no_progress`/`FlagProof`/`strategy_memory`)——这套 KB 部分就是为本项目建的,补遗高度对症。

每条优化都注明 **KB 出处 ID**(可溯源)+ **FlagHunter 落点文件**。

---

## 1. 三大痛点 → 优化映射(先看这张)

我们记忆里反复记录的三个痛:**① token 烧得快  ② 反复试错  ③ 能力写好却够不着**。本批优化精准对症:

| 痛点 | 直接对症的优化(本文编号) |
|---|---|
| **③ 够不着** | 混合检索 BM25+向量 RRF(M1)、假设搜索树+回溯(C2,冷落能力=最便宜分支会被选中)、置信度阈值检索→grep 兜底(T5/M10) + V2 的 WSTG 覆盖清单 |
| **②反复试错 / ①token** | **Code-as-Action 固化链→零 token 重放(T3)**、类型化结果信封+语义退出码→确定性重试(T1)、**分层记忆 L0–L3(M7,实测省 61% token/+51% 通过)**、预算治理分层降级(C1)、推理状态压缩+原文指针(M2/M3) |
| **①token(prompt cache)** | 缓存友好 prefix 布局(M4)、延迟/可搜索工具目录(T2)、按需 skill 加载快照(C9) |
| **幻觉 / 未复现** | 双轴判定 attribution×specificity(E1)、三态裁决(E2)、SARIF 式 FlagProof(E6)、奖励作弊护栏(E9/C10)、在线轨迹审计(E5) |

---

## 2. 记忆 / 上下文子系统(落点:`llm/memory.py`、`knowledge/rag.py`、`strategy_memory.py`)

| # | 优化 | KB 出处 | FlagHunter 落点 |
|---|---|---|---|
| **M1** | **混合检索 BM25+向量,RRF 融合**(`1/(k+rank)`,k≈60)。向量对 CVE/版本/报错串/参数名等精确 token 系统性漏召,BM25 精准——CTF 命门正是精确 token | BB-2026-05-01-434, -430 | `rag.py` 现 FAISS-only(search:262/329),加 BM25 索引 + RRF 融合。**头号检索修复** |
| **M2** | **按来源分型压缩观测**(HTTP body/headers/stdout/stderr/错误栈各自 schema),非统一截断;大体外置存储留指针可回查 | BB-2026-05-01-323(Acon), -319(ReSum) | `memory.py` 现单一 `_cached_summary`+`_truncate_to_fit`(55/116)→按源摘要器 + ObservationStore |
| **M3** | **摘要成"推理状态"而非散文**(已确认事实/开放假设/已否证 payload/待跟进),保留原文指针 | BB-2026-05-01-319, -323 | 改 `memory.py` 摘要 prompt 输出结构化 task-state |
| **M4** | **缓存友好 prefix 布局**:最稳内容前置(身份/工具规则/冻结记忆快照/skill 索引),易变内容(对话/当前消息)后置→命中 prompt cache | BB-2026-05-01-016, -164(Hermes 槽位[0]-[10]) | 消息装配器定义显式槽序,会话内冻结记忆快照 |
| **M5** | **字符预算 + 精选记忆**(Hermes:MEMORY.md ~2200 字符,`§` 分隔,"curated state not diary",会话启动快照冻结) | BB-2026-05-01-164, -507 | `strategy_memory.py` 加硬字符预算 + 按未来复用价值淘汰 |
| **M6** | **选择性留存**:按未来复用价值 gate 写入(URL 模板/疑似 secret/框架指纹/**已否证 payload** 才留),全 body 外置 | BB-2026-05-01-320(Mem0) | strategy_memory/notes 前加 write-gate 分类 transferable vs ephemeral |
| **M7** | **L0–L3 分层记忆 + extract→aggregate→distill**(原始→原子→场景→画像;context offloading 打破线性增长)。**实测省 61% token / +51% 通过率** | BB-2026-05-01-289(TencentDB,MIT) | L0 SessionLedger→L1 原子发现→L2 每靶场景摘要→L3 跨会话策略画像,周期 distill 喂 ShadowGraph/strategy_memory |
| **M8** | retrieve-then-**rerank**(17M–1B cross-encoder,~3 行代码大幅提精度) | BB-2026-05-01-264(Ettin), -430 | M1 之后加可选 CrossEncoder 重排 top-N,门控在 `[rag]` extra |
| **M9** | **contextual-chunk 嵌入**:嵌入前给每 chunk 加一行 LLM 生成的上下文,治"代词地狱/孤立比较" | BB-2026-05-01-430(Anthropic) | `rag.py:_chunk_text(213)` 加可选 contextualize |
| **M10** | **检索路由**:易变面(目标源码树/文件列表)用 grep/AST 迭代搜索,稳定语料(writeup/payload 库/CVE)才用 RAG | BB-2026-05-01-007, -268 | 加 retrieval router;**别把易变目标数据塞进 FAISS** |
| **M12** | **嵌入失效守卫**(否定/数值阈值/信号稀释):配关键词/元数据(CWE/port/service/version)预过滤 | BB-2026-05-01-332 | 向量路前加 facet 预过滤,免"not vulnerable to X""version < 2.4.49"误召 |

---

## 3. 运行时控制面(落点:`ctf_dispatcher`、`coordinator`、`recovery.py`、`hypothesis_engine.py`、`tools/executor.py`、`crew`)

> **KB 的最强共识 + FlagHunter 最大缺口**:推理层(假设/abort/反思/recovery)已强,但缺成熟 harness 视为底线的运行时控制面。

| # | 优化 | KB 出处 | FlagHunter 落点 |
|---|---|---|---|
| **C1** | **分层预算治理 + 优雅降级**(绿>50% 正常;黄 20–50% 压上下文+去 CoT;红 5–20% 辅助调用切 mini 模型;<5% 熔断→强制 finish 出部分结果),取代散落的 `max_steps=8` | BB-2026-05-01-177, -205(AutoCompact<13k) | 加 `BudgetGovernor`,dispatcher 循环顶 + `CrewOrchestrator.run` 处咨询;辅助调用(摘要/反思)黄/红时走 Haiku |
| **C2** | **假设搜索树 + 价值估计 + 回溯**(节点带 value/visits/reward,UCB1 选枝;错 flag/利用失败→回传父节点剪枝,展开兄弟枝),取代线性 ranked 队列 + 全局 no-progress 计数 | BB-2026-05-01-308(LATS:MCTS+value+reflection) | `hypothesis_engine.py` 引 `HypothesisTree`;`apply_wrong_flag_feedback`/`recovery.after_chain` 推 reward;"主枝 value<最佳兄弟枝"换"no_progress>=阈值" |
| **C4** | **两段式执行审批门**(快速单 token yes/no 过滤,仅命中升 CoT;deny-and-continue 把拒绝当 tool result+"换安全路径"提示;3 连续/20 总拒硬停;剥 assistant prose 防被说服) | BB-2026-05-01-143(Claude Code auto,FPR 8.5%→0.4%), -357 | **FlagHunter 现无权限门**。`tools/executor.py` 加 `PermissionEnforcer` + CTF scope 策略(scope 内 CIDR/target 可信,其余进分类器)。补安全层 + 给 recovery 清晰 deny-retry 信号 |
| **C5** | **控制层包络:熔断 + 抖动重试 + failure→hint 映射**(CLOSED→OPEN→HALF_OPEN;校验失败按 FailureMode 映射纠正提示;**只重试 transient,绝不重试 ValueError/TypeError**) | BB-2026-05-01-257, RSS-2026-003(LangGraph) | `recovery.py` 现仅处理 provider 不可用;加真熔断 + `FailureMode→hint` 表喂下一轮 |
| **C6** | **声明式计划做成可裁决工件 + 硬停门**(planner 出 intent-JSON,coordinator 执行前可重排/并行/拒/审计;`max_steps/max_tokens/max_duration/max_tool_calls` 四门;失败路由=显式决策 retry/degrade/skip/terminate) | BB-2026-05-01-177, -010(Codex `/goal`) | `ctf_planner` 计划→结构化工件,`CTFCoordinator` 裁决冻结;加 duration/tool_calls 门 + 显式 goal+budget 停条件 |
| **C7** | **类型隔离子 agent + 按角色工具白名单 + 上下文隔离**(Explore=读/搜/禁 bash 禁写;Verify=bash 禁写;Plan=仅 todo;子 agent 只见 (task,context),回 1–2k token 压缩摘要) | BB-2026-05-01-327, -205, -002 | `WorkerPool` worker 带 role→allowed-tools 契约(recon worker 不能跑 exploit/写),回 bounded 摘要保护 orchestrator 预算 |
| **C8** | **前瞻失败信号切换**(假设生成时同出 `{detection_signal, fallback_plan}`,信号一现即切,非等 N 次);丰富信号分类(500/403/timeout/WAF) | BB-2026-05-01-322(Devil's Advocate) | 已有 `abort_condition`→每个配 `fallback_hypothesis_id`;`recovery.after_chain` 命中即跳 fallback,不等 `no_progress_count` |
| **C3** | **会话即事件日志 + handoff-file 续跑**(每 thought/tool-call/observation 进 append-only log,崩溃 `wake(sessionId)` 恢复;超长任务全 reset 由结构化 handoff 重建;每 N 工作单元 checkpoint 而非每步) | BB-2026-05-01-024, -412 | `ctf_state` 已存 findings;加 append-only run log + `resume_from(snapshot)`,按 chain checkpoint |
| **C9** | **按需 skill/playbook 加载 + 每轮重注快照**(只注 ~100 token 名+描述 stub,选中才读全体;MAX_SKILLS=150/MAX_CHARS=30k;二进制/env 资格过滤跳没装工具的 playbook) | BB-2026-05-01-341, -205(~96% 工具 schema 省) | `playbooks/`+`tools/loader.py` 暴露 stub 延迟全体;env 资格过滤接 `on_missing_tools` |
| **C10** | **奖励作弊/假解决护栏**(把验证 harness 当 RL 环境:自身失败率<5%,拒"状态变但问题没解"/stale cache/静默 timeout 默认成功;假阳性写入会污染后续 30+ 步) | BB-2026-05-01-459, -412 | `verifier.py`/`flag_submitter.py` 要正向提交确认非仅 regex;`record_experiment_feedback` 不信未验证 progress 防污染假设树 value |

---

## 4. 评估 / 护栏 / 可观测(落点:`verifier.py`、`ctf_state.py:FlagProof`、`observability.py`、`eval/`、`tests/`)

> 现状:**verifier 是扁平串上的布尔 regex 门 + 均值式指标 + 仅事后失败分析**——分不清 runtime grounded flag 与自信幻觉,不能在错 flag 提交前预测,无 replay 回归套件防策略改动悄悄打断已解题。

| # | 优化 | KB 出处 | FlagHunter 落点 |
|---|---|---|---|
| **E1** | **双轴判定:attribution × specificity**。attribution=flag 是否逐字出现在 runtime 产物;specificity=是否匹配平台 regex/形态。**高 specificity + 低 attribution = 幻觉 flag**→REVIEW 不 AUTO_SUBMIT | BB-2026-05-01-228 | `verifier.py` 自动提交前分两轴算;regex 完美但 grounding 仅模型断言→REVIEW |
| **E2** | **三态裁决 ACCEPT/REVIEW/REJECT + reason + 路由**取代布尔门(ACCEPT 强 runtime→自动交;REVIEW→便宜 reviewer 模型→人;REJECT→reason 回喂策略环) | BB-2026-05-01-228, -357 | `VerificationResult` 加 `verdict` enum + `reason`;镜像 tool_guard 的 allowlist→reviewer→human |
| **E6** | **SARIF 式结构化证据对象**(result+location+codeFlow+relatedLocation+artifact;"源码见到"结构性区别于"runtime 触发") | BB-2026-05-01-318 | `ctf_state.py:FlagProof` 从扁平串→节点图(产物+来源分类(已有 `_RUNTIME_SOURCES`)+因果步链+产生它的 tool call),喂 E2 + 给 E8 可复现回归 |
| **E8** | **确定性回归套件 + replay CI 门**(同输入同分;LLM judge 只判 0.45–0.65 边界;L1 确定性 regex/grounding 无 API→L2 批量 judge→L3 全轨迹,**AND 门一题回归即拦**) | BB-2026-05-01-228, -240 | 已解题→录 replay fixture(用 E6 proof);`eval/` 合并前跑 3 层门 |
| **E5** | **在线轨迹审计**(跑中看动作 n-gram 重复/证据矛盾/预算异常,提前降权回滚,非等失败提交;活体标失败类:strategy/tool/verification) | BB-2026-05-01-324(AgentForesight,**KB 明确映射到 FlagHunter `stop_no_progress`/错 flag 预警**) | 加 auditor 消费 SessionLedger/blackboard 流 + MetricsCollector turns,trip 即切策略 |
| **E9** | **奖励作弊护栏**(防靠读题源码/mock/自写 notes 而非活体目标"解出";runtime-grounding 强制为 AUTO_SUBMIT 前提;pin judge seed/temp 确定性) | BB-2026-05-01-367 | runtime-grounding 必填;仅静态/源码/自写来源的 flag 拒交(同 C10) |
| **E3** | **rubric/criteria done-criteria + grader 子 agent 调工具**(per-criterion verdict 回注循环:"flag 来自代码注释非活体响应"→下一策略 hint) | RSS-2026-004(RubricMiddleware) | "task complete" 加 rubric:flag 来自 runtime/干净会话复现/黑板无矛盾证据 |
| **E4** | **链感知/最坏值评分**(报 recon→foothold→flag 各阶段成功率 + p0 最坏值,非均值;按**环境/verifier 状态**判成功非 agent 自称) | BB-2026-05-01-206, -419(SaaS-Bench) | `eval/` 报分阶段链成功 + 最坏跑;验 flag 真被接受 |
| **E7** | **分层 LLM-judge**(全 criteria 批量一调 + 中档模型;**怕 false-pass**(交错 flag 耗 attempt)→不确定偏 REVIEW;别追 100% judge 一致,~95% 是上限) | RSS-2026-005(Harvey/LangChain) | REVIEW 层批量判,judge prompt 偏保守 |
| **E10** | **agent 原生可观测**(round-scoped Entry/Step span + skill/chain span 功能归因 + token 级 trace;六支柱:tracing/eval/monitor/cost/feedback/governance) | BB-2026-05-01-212, -227 | `observability.py:MetricsCollector` 现扁平→分层 span 键到 ledger 轮次 + 活动 chain(归因"哪条 chain 烧预算/出假 flag") |
| **E11** | **轨迹回顾→strategy_memory(批判非日志)**(输出哪步偏离/哪类动作浪费预算/哪条证据误读) | BB-2026-05-01-321(Retrospex) | 每跑后 critic 重放 SARIF 轨迹,结构化 delta 入 strategy_memory,喂 E5 + 下轮 planner |
| **E12** | **静默损坏 round-trip 完整性校验**(长链多步委派 ~25% 内容损坏,~80% 来自罕见灾难性单步丢失,模型改写/幻觉非删除→spot check 看不见) | BB-2026-05-01-214 | 长链快照关键事实(target/creds/endpoints)断言每轮存活,灾难性单步丢失报警 |

---

## 5. 工具 / 动作层(落点:`tools/loader.py`、`tools/executor.py`、`runtime/`、`notes`、`mcp`)

| # | 优化 | KB 出处 | FlagHunter 落点 |
|---|---|---|---|
| **T1** | **语义化退出码 + stdout/stderr 分离的类型化结果信封**`{status, error_class∈{auth,badparam,timeout,network,target_down,transient}, stdout_clean, stderr_noise}`→agent 确定性 retry/backoff 非重 prompt 解析英文报错 | BB-2026-05-01-098(MiniMax MMX-CLI) | `tools/executor.py` 包每个结果;terminal 分进度/banner(stderr)与数据(stdout)。**直击"反复试错烧 token"** |
| **T3** | **Code-as-Action:验证过的链固化成零 token 重放脚本**(成功即 emit 独立 Python/shell 工件,注册为可调工具;重跑已知好链=一次确定性 tool call 无推理环) | BB-2026-05-01-181(Xiaohongshu), -182 | ChainContext 步成功→`loot/` 出工件并注册;配 P3/P4 的 ChainContext+registry。**ROI 最集中:现在每条已解链都从头重推** |
| **T2** | **延迟/可搜索工具目录**(每工具/MCP 动作只注两行 index 条目,`load_tool_schema(name)` 选中才注全 schema)——把现>128 工具才触发的 `mcp_*_rag_optimizer` 升为**默认路径** | BB-2026-05-01-189, -182 | `tools/loader.py` 通用化;削 prompt 膨胀 + 错选工具 |
| **T5** | **置信度阈值检索:部分召回比不召回更差**(8.15 vs 9.18/10)。低于阈值返回"无相关知识→转 grep/活体 recon" | BB-2026-05-01-203, -007 | `rag.py`/`web_search` 加相似度地板;低则显式 fallback 信号接 grep 工具(配 M10) |
| **T7** | **调查轨迹→可复用 KB + triage/investigate 分层**(成功解题的完整 tool-call 轨迹自动入 RAG 作"已解链范例",按题型 tag;下次相似目标取作 few-shot;FP 33%→7%) | BB-2026-05-01-187(Anthropic CLUE), -203 | `notes` 自动 ingest 成功轨迹入索引;agent 拆便宜 triage(指纹/路由)+ 深 investigate |
| **T8** | **3 层 skill 渐进加载 + Trace2Skill 工厂**(SKILL.md 3 层:目录/指令/资源;从成功轨迹蒸馏 playbook 并用 held-out 旧题回归测后才晋升) | BB-2026-05-01-176, -180 | `playbooks/` 改 3 层可加载;加 Trace2Skill harness(配 E8 回归) |
| **T4** | **命令链感知审批 + 单一出口代理**(审批前解析内层链拦 `;`/`&&`/反引号绕过;全工具网络流走一个可观测出口) | BB-2026-05-01-201(OpenClaw) | `runtime/` 加命令解析器逐子命令施 scope/审批;出口走代理给 ledger 完整网络 trace(配 C4) |
| **T6** | **多个小 MCP server + 按工具授权装饰器**(`@requires_scope(...)` 每调用查 scope;粗粒度边缘 + 细粒度 per-tool 两层) | BB-2026-05-01-186(Pinterest), -023 | FlagHunter 作 MCP server 时按能力域拆(recon/exploit/post-ex)+ `tools/executor.py` 加 scope 装饰器 |
| **T9** | **分层模型路由**(高频低风险原子感知如截图/DOM 解析走便宜快模型,planner 留前沿模型) | BB-2026-05-01-181 | browser 工具路 DOM/截图解析走可配便宜模型;token_tracker 已能量收益 |
| **T10** | **结构化结果工具非泄露推理**(显式 `report_finding`/`finish` 带状态 flag_found/blocked/need_input/scheduled_followup) | BB-2026-05-01-189 | 扩展现有 `finish`;notifier/EventBus/TUI 渲染刻意结果,ledger 记意图非传输噪声 |

---

## 6. Do-First 短名单(跨子系统最高杠杆)

四路各自的"biggest gap"汇总,**这几条做完框架基础就上一个台阶**:

1. **T3 Code-as-Action 固化链 → 零 token 重放**(+ T1 类型化结果信封)。最集中的 ROI,直接消灭"已解链重推/反复试错烧 token"。
2. **C4 执行审批门 + C1 预算治理分层降级**。FlagHunter 现**完全没有**权限门;这两条把脆弱的 all-or-nothing 长跑变成可优雅降级、可无人值守安全跑。
3. **E1+E2 双轴+三态判定 + E6 SARIF FlagProof + E8 确定性 replay CI 门**。把验证从 yes/no 升级为 grounded、防作弊、可回归——直击幻觉 flag。
4. **M1 混合检索 RRF + M7 分层记忆**(实测省 61% token/+51% 通过)。检索与记忆是当前把成本和成功率"留在桌上"的子系统。
5. **C2 假设搜索树 + 回溯**。让 agent 真正放弃死路 attack path,而非磨 no-progress 计数——也是"够不着"的结构解。

---

## 7. 与已落地骨架 / V2 路线的整合

- 这些都**坐在本会话已落地的 P0–P4 骨架上**:T3 配 `chains/`+ChainContext+registry;C4/T1/T6 落 `tools/executor.py`;E6/E8 升级 `CTFVerifier`/`FlagProof`;M1/M7 升级 `rag.py`/记忆;C1/C2/C5/C8 落 `coordinator`/`recovery`/`hypothesis_engine`;E10 升级 `observability.py`(全程经 `AgentSession`/`EventBus`/中立总线)。
- 与 V2 路线**互补**:V2 给方向(攻击图/验证优先/覆盖度),本文给**怎么把引擎造扎实**。两者交汇处:**攻击路径图(V2 §3.1)+ 假设搜索树(C2)+ SARIF 证据(E6)+ Code-as-Action 固化(T3)** 合起来就是一个"边打分 pathfinding → 走最便宜分支 → 固化成可复现工件 → 结构化证据回归"的闭环。

---

## 8. 参考(KB 出处)

均为本地 KB `D:\newwork\AI-Agents\aiagentstudy\knowledge\items\<topic>\<ID>\summary.md`,主要条目:
- 记忆/检索:BB-2026-05-01-{434,430,323,319,289,320,264,332,016,164,507,007,268}
- 控制循环:BB-2026-05-01-{177,205,308,143,357,257,024,412,322,327,002,341,459,010}; RSS-2026-003
- 评估护栏:BB-2026-05-01-{228,318,240,324,367,206,419,212,227,321,214}; RSS-2026-{004,005}
- 工具动作:BB-2026-05-01-{098,181,182,189,203,187,176,180,201,186,023}

相关:[[FlagHunter_红队智能体架构_对标顶级红队工程学_2026-06-17_V2]]、[[FlagHunter_架构决策记录_自顶向下骨架与两关节契约_2026-06-17_V1]]。
