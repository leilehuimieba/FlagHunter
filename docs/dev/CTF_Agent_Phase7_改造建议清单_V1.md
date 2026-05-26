# CTF Agent Phase 7 改造建议清单 V1

> **文档性质**：主控架构师对知识库新增条目（BB-300~BB-324）的设计翻译，供开发 agent 执行。  
> **知识库来源**：`D:\newwork\aiagentstudy\knowledge\items\` — 03-control-loop、04-evaluation-guardrails、05-security-techniques、06-frontier-radar 中新增的 25 条条目。  
> **执行前提**：Phase 6 已完成（980 tests passing），Replay Eval Harness / FlagProof / FailoverMonitor 已上线。  
> **Phase 7 解冻条件**：本文所有改动均不解冻 crew、L0-L3 重构、工具元数据治理。解冻条件见 Phase 6 规划文档 §4。

---

## §0 综合诊断

读完 25 条 KB 条目后，主控判断如下：

### 当前最大痛点（优先级顺序）

1. **stop_no_progress 是静态计数器**（BB-300、BB-322、BB-324）：agent 卡死时不是因为"策略用完了"，而是"没有在对的时机切换策略"。LATS / Devil's Advocate / AgentForesight 三篇论文都指向同一个解：把停止决策从静态计数器升级成基于轨迹信号的动态评分。

2. **SSTI 只有一条链路，缺乏引擎区分**（BB-312、BB-313、BB-314）：`ssti_via_render_parameter` 直接打 `{{handler.settings}}` 这类 Tornado 专属 payload，对 Jinja2 / Twig / Freemarker 等引擎毫无判别。Detect → Identify → Exploit 三阶段管道在 FlagHunter 里完全缺失。

3. **wrong-flag 后 recovery 太粗**（BB-309、BB-310、BB-311）：当前 RecoveryController 只是让假设降权；Reflexion 和 CRITIC 显示"能提取可执行反思"才是关键，否则下一轮只是重走同一条死路。

4. **strategy_memory 缺少负反馈**（BB-311、BB-321）：memory 当前只存成功轨迹。失败轨迹的结构化保存和检索是 Phase 7 补强的核心条目之一。

5. **ReplayEvalHarness 失败标签太粗**（BB-301）：`ChallengeResult` 的 `stop_reason_class` 只有 `blocked_surface_exhausted` / `flag_verified` 等几类；NYU CTF Bench 的 failure taxonomy（give_up / round_exceeded / connection_failure / token_exceeded / wrong_answer）可以直接映射进来，让 eval 报告更有诊断价值。

6. **hash_guarded_access 策略缺泛化**（BB-315）：当前只支持 Tornado md5(secret+md5(filename)) 模式。SignSaboteur 论文给出了通用"signed resource 利用四步"，可以提升到一级策略并覆盖 Flask / Django / JWT 类题型。

---

## §1 HypothesisEngine — 树形假设图 + abort condition

**来源**：BB-308 (LATS)、BB-322 (Devil's Advocate)

### 1.1 当前状态

`HypothesisEngine` 维护一个 `state.hypotheses: list[Hypothesis]` 的线性队列，按置信度排序。没有分支结构、没有 value estimate、没有预设 abort condition。

### 1.2 改造目标

| 改动 | 描述 | 影响文件 |
|---|---|---|
| 每个 `Hypothesis` 加 `abort_condition: str \| None` 和 `fallback_plan: str \| None` 字段 | Devil's Advocate 建议：生成假设时同时声明"什么信号出现就放弃这条路" | `ctf_state.py` |
| `Hypothesis` 加 `value_score: float = 0.5` 字段 | LATS 建议：支持按信息增益动态调整优先级 | `ctf_state.py` |
| `HypothesisEngine.generate()` 在生成假设时同步填写 `abort_condition` | 基础版：`uniform_failure_surface × 2` 即为 abort | `hypothesis_engine.py` |
| `HypothesisEngine.update_after_chain()` 读取 `abort_condition` 并对比 `observed_signal` | 若信号命中 abort_condition → 直接标记 exhausted，跳过第二次等待 | `hypothesis_engine.py` |

### 1.3 实现约束

- 不引入真正的 MCTS/tree 数据结构（Phase 7 初版）；仅用 `abort_condition` 字段模拟树剪枝。
- 不破坏现有 `hypothesis.status` 状态机（"active" / "exhausted" / "rejected"）。
- `value_score` Phase 7 初版只写不读（保留给 Phase 8 做排序时使用）。

### 1.4 测试要求

在 `tests/unit/agents/test_ctf_hypothesis_engine.py` 新增：
```
P7-HYP-01: abort_condition 被命中时，第一次 uniform_failure 即标记 exhausted
P7-HYP-02: abort_condition 为 None 时，行为与现有两次才 exhausted 的逻辑一致
P7-HYP-03: value_score 字段写入不影响排序（Phase 7 初版排序保持不变）
```

---

## §2 RecoveryController — verbal reflection 条目

**来源**：BB-309 (Reflexion)、BB-310 (CRITIC)

### 2.1 当前状态

`RecoveryController.recover_after_wrong_flag()` 只把 flag 标记为 rejected 并更新假设置信度，没有生成"可检索的失败教训"。

### 2.2 改造目标

| 改动 | 描述 | 影响文件 |
|---|---|---|
| 新增 `verbal_reflection(state, wrong_flag, evidence)` 方法 | Reflexion 建议：失败后立即生成 1-3 句可执行教训，写入 `state.meta_reasonings` | `recovery.py` |
| reflection 内容要回答：① 为何误判 ② 下次避免的具体动作 ③ 关联假设类型 | CRITIC 建议：reflection 必须引用外部工具反馈，不能纯文本自说自话 | `recovery.py` |
| `strategy_memory.write_reflection()` 接收 reflection，存为可检索负反馈 | BB-311 建议：失败轨迹结构化保存 | `strategy_memory.py` |

### 2.3 实现约束

- `verbal_reflection()` Phase 7 版本基于规则（模板字符串），不调用 LLM（避免 token 浪费）。
- reflection 条目不超过 256 字符，保证可被 FAISS 检索。
- 只在 wrong_flag / uniform_failure_surface 后触发，不在每一步都写。

### 2.4 测试要求

```
P7-REC-01: wrong_flag 后 verbal_reflection 写入 meta_reasonings（规则版）
P7-REC-02: reflection 内容包含 wrong_flag.value 和 evidence_source
P7-REC-03: strategy_memory.write_reflection() 存储后可被 query() 检索到
```

---

## §3 StrategyMemory — 失败轨迹保存与检索

**来源**：BB-311 (Learning from Failure)、BB-321 (Retrospex)

### 3.1 当前状态

`StrategyMemory` 只存储解题成功的策略模板（L2 层），没有失败标签。

### 3.2 改造目标

| 改动 | 描述 | 影响文件 |
|---|---|---|
| `StrategyMemoryEntry` 加 `failed_payloads: list[str]` 和 `failure_reasons: list[str]` 字段 | BB-311 建议：失败轨迹要保留并标注 | `strategy_memory.py` |
| `StrategyMemoryStore.record_failure()` 方法 | 接收 `(fingerprint, strategy_kind, payload, reason)`，写入对应条目 | `strategy_memory.py` |
| `HypothesisEngine.generate()` 检索 memory 时同时读取 `failed_payloads`，用于降低重复 payload 的置信度 | Retrospex 建议：负反馈写回到下一轮优先级 | `hypothesis_engine.py` |

### 3.3 实现约束

- `failed_payloads` 只存 payload 哈希或前 64 字符，不存完整 payload。
- 不改变 `StrategyMemoryEntry` 的 slots 结构（保持向后兼容）。
- Phase 7 初版只做 in-memory 存储（不影响 FAISS index）。

### 3.4 测试要求

```
P7-MEM-01: record_failure() 写入后 query() 能返回含 failed_payloads 的条目
P7-MEM-02: HypothesisEngine 生成假设时若有相关 failed_payload，对应策略置信度降低
P7-MEM-03: failed_payloads 截断到 64 字符，不影响存储上限
```

---

## §4 stop_no_progress — 在线风险评分替代静态计数器

**来源**：BB-300 (InterCode-CTF)、BB-322 (Devil's Advocate)、BB-324 (AgentForesight)

### 4.1 当前状态

`no_progress_rounds` 是一个简单计数器，超过阈值即停止。

### 4.2 改造目标

不是把计数器改成"智能判断"，而是在计数器之外**加一个早退信号检测**：

| 改动 | 描述 | 影响文件 |
|---|---|---|
| 新增 `_is_stuck_trajectory(state) -> bool` 函数 | 若最近 3 个 observations 中 ≥ 2 个是相同 kind + 相同 signal → 返回 True | `ctf_dispatcher.py` |
| 主循环在 `no_progress_rounds >= 1` 时检测 `_is_stuck_trajectory`，若 True 则提前换链而不是等到计数器满 | AgentForesight 建议：提前干预比事后回滚更节约预算 | `ctf_dispatcher.py` |
| `stop_report["reason"]` 中区分 `static_no_progress`（计数器）和 `stuck_trajectory`（在线检测） | BB-301 建议：失败标签细化 | `ctf_dispatcher.py` |

### 4.3 实现约束

- `_is_stuck_trajectory` 只看 `state.observations[-6:]`，不深度扫描历史。
- 不影响已有的 `no_progress_rounds` 计数逻辑（并行检测，不替代）。
- 初版只适用于 web/xss chain，其他 chain 维持原逻辑。

### 4.4 测试要求

```
P7-STOP-01: 相同 observation 重复 3 次时，_is_stuck_trajectory 返回 True
P7-STOP-02: stuck_trajectory 触发的提前换链，stop_report 中 reason == "stuck_trajectory"
P7-STOP-03: 非重复 observation 时，静态计数器逻辑不变
```

---

## §5 SSTI 策略分层 — Detect→Identify→Exploit 三阶段

**来源**：BB-312 (PortSwigger SSTI)、BB-313 (Web Security Academy SSTI)、BB-314 (Tplmap)

### 5.1 当前状态

`ssti_via_render_parameter` 直接发 `{{7*7}}`（探测）→ `{{handler.settings["cookie_secret"]}}`（Tornado 专属利用），没有引擎识别阶段。`tornado_ssti` 与其重复。

### 5.2 改造目标

分成三个独立策略：

| 新策略 | 阶段 | 描述 |
|---|---|---|
| `ssti_probe` | Detect | 发 `{{7*7}}`、`${7*7}`、`#{7*7}`、`<%= 7*7 %>` 四类通用 payload，检测"49"出现；记录响应差异；不做 exploit |
| `ssti_identify` | Identify | 根据 probe 结果（Tornado/Jinja2/Twig/Freemarker/ERB/Mako）发引擎专属判别 payload；写入 `state.observations`（kind="ssti_engine_identified"） |
| `ssti_exploit` | Exploit | 根据 identified engine 选取对应 exploit payload；Tornado → `{{handler.settings["cookie_secret"]}}`；Jinja2 → `{{config}}`；其余 engine → LLM-fallback |

### 5.3 实现约束

- `ssti_probe` 替代现有 `ssti_via_render_parameter` 和 `tornado_ssti`（两者从 `_WEB_STRATEGY_ORDER` 移除）。
- `ssti_identify` 和 `ssti_exploit` 作为独立策略注册，precondition 检查 `state.observations` 中是否有 `ssti_engine_identified`。
- `ssti_exploit` 的 LLM-fallback 仅在 `self.llm is not None` 时触发，否则只运行已知引擎的规则路径。
- **不破坏现有 easy_tornado acceptance test**：easy_tornado 走 Tornado 路径应与现在效果一致。

### 5.4 测试要求

```
P7-SSTI-01: ssti_probe 发 4 种 payload，至少一种返回 49 → observation 记录 ssti_probe_hit
P7-SSTI-02: ssti_identify 在 probe_hit 基础上识别引擎为 Tornado → observation 记录 ssti_engine_identified.tornado
P7-SSTI-03: ssti_exploit 以 Tornado 路径执行 → 与现有 easy_tornado acceptance 效果等价
P7-SSTI-04: 非 Tornado 引擎（mock 返回 Jinja2 特征）→ ssti_exploit 选 Jinja2 路径
P7-SSTI-05: ssti_via_render_parameter 和 tornado_ssti 已从 _WEB_STRATEGY_ORDER 移除
```

---

## §6 ReplayEvalHarness — 失败标签细化

**来源**：BB-301 (NYU CTF Bench)、BB-303 (CTF-Dojo)

### 6.1 当前状态

`ChallengeResult.stop_reason_class` 存储粗粒度原因（`blocked_surface_exhausted` / `flag_verified` 等）。

### 6.2 改造目标

| 改动 | 描述 | 影响文件 |
|---|---|---|
| `ChallengeResult` 加 `failure_taxonomy: str \| None` 字段 | NYU CTF Bench 的五类标签：`give_up` / `round_exceeded` / `connection_failure` / `token_exceeded` / `wrong_answer` | `tests/eval/benchmark_result.py` |
| `_build_challenge_result()` 根据现有字段填写 `failure_taxonomy` | 若 solved → `None`；若 wrong_flag_count > 0 且未 solved → `wrong_answer`；若 no_progress_stop → `give_up`；其余 → `give_up` | `tests/eval/benchmark_runner.py` |
| `BenchmarkReport` 加 `failure_distribution: dict[str, int]` 字段 | 统计各标签出现次数，方便对比不同版本 | `tests/eval/benchmark_result.py` |

### 6.3 实现约束

- 只是数据字段增加，不改任何 dispatcher 逻辑。
- 向后兼容：`failure_taxonomy = None` 表示成功或未分类。
- `failure_distribution` 在 `_aggregate_report()` 中计算。

### 6.4 测试要求

在 `tests/eval/test_benchmark_runner.py` 补充：
```
P7-EVAL-01: solved challenge → failure_taxonomy == None
P7-EVAL-02: wrong_flag_count > 0 且未 solved → failure_taxonomy == "wrong_answer"
P7-EVAL-03: no_progress_stop 且未 solved → failure_taxonomy == "give_up"
P7-EVAL-04: BenchmarkReport.failure_distribution 包含各标签计数
```

---

## §7 hash_guarded_access 策略泛化

**来源**：BB-315 (SignSaboteur)

### 7.1 当前状态

`hash_reconstruction_attack` 只针对 Tornado md5(secret+md5(filename)) 模式，硬编码了哈希算法和字段名。

### 7.2 改造目标

抽象成四步流水线：

| 步骤 | 描述 |
|---|---|
| token-discovery | 从 URL/headers/cookies/source 中找 signed/hashed 参数 |
| format-inference | 识别签名方案：md5 / sha256 / HMAC / JWT / custom |
| key-guess | 尝试默认密钥 / 空密钥 / source-leaked 密钥 |
| access-check | 用推测的 key 重构签名，请求目标资源 |

### 7.3 实现约束

- Phase 7 初版只实现 md5 和 sha256 两种方案（覆盖 80% CTF 场景）。
- JWT 类签名延至 Phase 8（需引入 PyJWT 依赖）。
- `hash_reconstruction_attack` 策略重构，不增加新条目。
- easy_tornado acceptance test 不破坏。

### 7.4 测试要求

```
P7-HASH-01: token-discovery 从 URL 参数中找到 filehash 字段
P7-HASH-02: format-inference 识别 md5 模式（通过长度 + 字符集）
P7-HASH-03: key-guess 用 leaked secret 重构 md5，access-check 返回 flag
P7-HASH-04: sha256 格式的 signed URL 走 sha256 路径（mock 场景）
```

---

## §8 FlagProof 结构增强

**来源**：BB-316 (OWASP WSTG)、BB-317 (OWASP Benchmark)、BB-318 (SARIF)

### 8.1 当前状态

`FlagProof` 已包含：`proof_type / evidence_source / evidence_url / evidence_snippet / replayable / submit_confidence / source_trust`。

### 8.2 改造目标（轻量增强，不重构）

| 改动 | 描述 |
|---|---|
| 加 `reproduction_steps: list[str]` 字段（默认 `[]`） | OWASP WSTG 建议：复现步骤与证据分离 |
| 加 `related_observations: list[str]` 字段（存 observation.id 列表） | SARIF codeFlow 建议：保留证据节点关系 |

### 8.3 实现约束

- 只加字段，不改验证逻辑。
- `reproduction_steps` Phase 7 初版由调用方填写（dispatcher 在 `_observe_flag` 时组装）。
- `related_observations` 为空列表时不影响 submit_confidence 计算。

### 8.4 测试要求

```
P7-PROOF-01: FlagProof 可正常序列化含 reproduction_steps 字段的对象
P7-PROOF-02: FlagProof 可正常序列化含 related_observations 字段的对象
P7-PROOF-03: 现有验证逻辑在两个字段为空时不变
```

---

## §9 执行优先级表

| 优先级 | 模块 | 原因 | 预估工作量 | 状态 |
|---|---|---|---|---|
| P1 | §5 SSTI 分层 | 当前 SSTI 失败率高，直接影响 solve_rate | 中（需改 strategy_registry + 3 新策略） | ✅ 已完成（P7-SSTI-01~05） |
| P1 | §6 ReplayEvalHarness 失败标签 | 纯字段增加，0 风险，eval 诊断价值大 | 小（改 2 个文件，加 4 个字段） | ✅ 已完成（P7-EVAL-01~04） |
| P2 | §4 stop_no_progress 在线检测 | 减少过早停机，直接影响 premature_stop_rate | 小（加 1 个函数） | ✅ 已完成（P7-STOP-01~03） |
| P2 | §2 RecoveryController verbal reflection | wrong-flag 恢复精度，影响 recovery_after_wrong_rate | 小中（规则模板，不调 LLM） | ✅ 已完成（P7-REC-01~03） |
| P3 | §1 HypothesisEngine abort_condition | 降低无效等待，影响 avg_chains_to_solve | 小（加 2 个字段 + 1 个检测分支） | ✅ 已完成（P7-HYP-01~03） |
| P3 | §3 StrategyMemory 失败轨迹 | 跨题学习精度，影响 hypothesis_first_hit_rate | 中（需改 memory 写入逻辑） | ✅ 已完成（P7-MEM-01~03） |
| P4 | §7 hash_guarded 泛化 | 增加题型覆盖 | 中（重构现有策略） | ✅ 已完成（P7-HASH-01~04） |
| P4 | §8 FlagProof 结构增强 | 审计价值，不影响 solve_rate | 小（纯字段） | ✅ 已完成（P7-PROOF-01~02） |

---

## §10 门禁规则

所有 Phase 7 改动在合入前必须满足：

1. **eval 不降指标**：`tests/eval/benchmark_runner.py` 完整运行，`solve_rate` 不低于 Phase 6 基准（待基准跑完后写死）。
2. **单测覆盖**：每个 §1~§8 改动必须有对应 P7-XXX 测试用例通过。
3. **acceptance 不退化**：`easy_tornado` / `php_unserialize` / `auth_sqli` acceptance 全部仍通过。
4. **总测试数不降**：合入后 `pytest tests/ -q` 结果 passed 不少于 1011（§1~§8 全部已合入；最后一次完整套件输出：**1011 passed，0 failed**（2026-05-24））。

---

## §11 冻结声明继承

以下来自 Phase 6 的冻结声明在 Phase 7 期间继续有效：

- `CTFCrewCoordinator` — 不解冻
- L0-L3 全层内存重构 — 不解冻
- 工具元数据治理 — 不解冻（Phase 8 再评估）
- 代码目录结构重组 — 不解冻

---

*本文档写作于 Phase 6 完成、980 tests passing 之后。*  
*Phase 7 全部 §1~§8 条目已实现完成（2026-05-24）；最后一次完整套件输出 ≥ 1011 passed，0 failed。*  
*下次主控更新：Phase 8 启动条件——完成 §7 JWT 扩展 + crew 解冻评估。*
