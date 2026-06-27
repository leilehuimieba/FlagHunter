# FlagHunter 目标架构 · 北极星 V3

- 日期：2026-06-27
- 状态：**已确认（唯一真相源）**
- 收敛自：2026-06-27 三轮亲核审计 —— ①知识层一致性审计、②既有架构文档消化、③控制面代码亲核
- 取代：本文是架构的**唯一真相源**，收敛此前散落的 6 份架构文档（见 §9 索引，原文不删，作历史依据）

---

## 0. 本文地位与边界

本文存在的理由：仓里**不是没有架构设计，而是设计散在 6+ 份文档里、没收敛成一张可执行的总图，且有未调和的内部矛盾**——多套并行设计本身就是屎山源头。本文把三轮亲核的结论收敛成一张图 + 一份施工 checklist。

铁律（沿用 `项目工程治理流程_V1.md` 心法）：
- **本文是"决策 + 闸门"，不是"现状描述"**。现状描述类断言必须配 file:line 证据或守护测试，否则视为过期。
- **任何不变量都必须被测试钉死**，不靠自觉。"没被测试钉死的不变量"是三个月后变屎山的头号原因。
- ADR 只增不改：本文为 V3，推翻或修订须出 V4，不原地改写既成决策。

诚实分维结论（本文的核心判断）：

| 维度 | 状态 | 本文动作 |
|---|---|---|
| **结构维**（骨架/接缝/依赖） | ✅ 优秀且已收敛 | §2 固化，保留不动 |
| **能力维**（执行/解题/知识/记录/学习/搜集/多 agent） | ❌ 欠架构 + 没收敛 + 没护栏 | §3 补目标架构 |
| **已确证缺陷**（今天审计坐实） | 🔴 2 个真 bug + 死代码 | §4 登记 |
| **防屎山护栏** | ⚠️ 点状非面状 | §5 面状化 |

---

## 1. 一页纸全景

结构维 6 层骨架**保留不动**（它是对的）；本文的新增是叠加其上的**纵向能力线**，核心是补一个**待建的第三关节：KnowledgeMemory 门面**。

```
 ENTRY      TUI / CLI / Web / MCP            ← 只做 I/O 与渲染，经关节A装配
   │
 SESSION    AgentSession 门面  ★关节A(已建)   ← 唯一装配 + 单一事件总线
   │
 ORCHEST.   solve-loop（混合控制面）          ← §3.1 既定路线=形式化混合
   │   ┌──────────── 读 / 写 ─────────────┐
   │   ↓                                   ↓
 STRATEGY   registry + chains ★关节B(已建)  ┌─ KnowledgeMemory 门面 ★关节C(待建)─┐
   │        ChainContext 显式传状态         │  · Ledger     唯一事实源(append-only)│
   │                                        │  · Notes      本题发现               │
 CAPABILITY tools/ + cpa m1–m6              │  · StrategyMemory  跨题学习          │
   │        + web_search(网络搜集)          │  · RAG        外部知识库             │
   │        + capability_registry(工具路由)  │  · ShadowGraph 攻击路径图(派生)      │
 FOUNDATION runtime / llm / config          └─ project_for_prompt() 统一投影注入 ──┘
            （无环）
```

三个关节（接缝）：
- **关节 A — AgentSession**（入口↔编排）：✅ 已建并闭合
- **关节 B — ChainContext + registry**（编排↔策略）：✅ 已建并收口
- **关节 C — KnowledgeMemory 门面**（编排/策略↔知识记忆）：❌ **待建**，本文新增。今天审计证明它"不存在"是能力维一切混乱的根（7 组件各自裸 new、各自落盘、3 条互不相交装配链）。

---

## 2. 结构维：已收敛（保留不动）

来源：`FlagHunter_架构决策记录_自顶向下骨架与两关节契约_2026-06-17_V1.md`（状态：P0 完成）。本文原样固化，不重述论证。

### 2.1 六层骨架 + 职责约束

| 层 | 内容 | 职责约束 |
|---|---|---|
| **ENTRY（薄）** | TUI / CLI / web / MCP | 只做 I/O + 渲染；**不直接 new** LLM/Tools/Runtime；仅依赖关节 A 契约 |
| **SESSION ★A** | `AgentSession` 门面 | 唯一装配入口 + 单一事件总线 + 会话/结果生命周期 |
| **ORCHESTRATION** | `BaseAgent.agent_loop()` / solve-loop | 控制环；§3.1 混合控制面 |
| **STRATEGY ★B** | `StrategyRegistry` 单一分发 + `chains/{web,sqli,xss,ssti,…}` | registry 驱动取代 if/elif；`ChainContext` 显式传状态 |
| **CAPABILITY** | `tools/` + `cpa_modules/m1..m6` + `capability_registry` | 工具与横切能力层 |
| **FOUNDATION** | `runtime / llm / knowledge / config` | 无环 |

### 2.2 不变量 I1–I5（统一编号）

> 收敛说明：ADR 定义 I1–I4；`项目工程治理流程_V1.md` 另定义 I5（可达性）并已有守护测试。本文统一为 I1–I5 canonical 集。

- **I1 依赖单向向下**：foundation 不得 import capability/orchestration/entry；capability 不得 import orchestration/entry。**守护：待建 import-linter（§5.1，当前最大缺口）**。
- **I2 唯一装配入口**：任何入口构造 agent 必须经 `build_agent_components()`，不得自己 new LLM/Tools/Runtime。守护：`test_run_cli_does_not_import_assembly_primitives` 等点状断言。
- **I3 事件单源**：agent 事件只走关节 A 的一条 EventBus，入口只订阅。守护：**待补面状测试**。
- **I4 chain 不读上帝对象**：策略/chain 经 `ChainContext` 取状态，禁止新增对 `dispatcher.*` 的隐式访问。
- **I5 注册策略可达**：每个注册进 `StrategyRegistry` 的策略必须有可达路径被触发。守护：`tests/unit/agents/test_strategy_reachability.py`（已落地）。**注意：I5 的"可达"目前只校验"注册了能被 list_for_chain 取到"，不校验"chain 在 chain_order 里"——这正是 §3.1 "够不着" 缺口的所在**。

### 2.3 两个已建关节契约

**关节 A — `AgentSession`**（`flaghunter/session/agent_session.py`）
- API：`create(...)`（唯一装配，内部必调 `build_agent_components`）/ `events() -> EventBus` / `run(task) -> RunResult{flag,findings,tokens,status,session_id}` / `session_store()` / `metrics()`
- 满足 I2 + I3。状态：CLI/web/mcp/tui 全迁，已全闭合。

**关节 B — `ChainContext` + registry 分发**
- `ChainContext` 8 字段：`services / target / page_features / hint / extras / state / ingress_handoff / challenge_context`
- 分发：`_execute_chain` 按 `chain_name` 从 `StrategyRegistry` 取有序策略跑 `_run_strategy_sequence`
- **关键不变量（零回归前提，不可改）：仅 `outcome.flag` 短路，progress 不短路**
- 状态：if/elif→registry、破上帝对象（L1 收窄为 `StrategyServices` Protocol）已收口。

### 2.4 依赖方向规则

- I1 是硬规则，严格单向向下，禁反向 import。
- 唯一合规的"看似反向"：`llm/llm.py` 对 `cpa_modules.m1_api_hub` 是**函数内动态 import，不构成模块级环**。
- composition root（`build_agent_components`/`build_runtime`）已下沉到 `session/initializer.py`，`interface/initializer.py` 退为兼容 re-export。

---

## 3. 能力维：目标架构（本文新增收敛）

### 3.1 控制面 = 混合（既定路线，代码已 80% 成型）

**翻转结论（2026-06-27 控制面代码亲核坐实）**：红队 V2（控制派：算法打分挑边）与黑板方案（协议派：决策权给模型）在文档里被描绘成"未调和的二选一"。但读代码真身，**当前已落在'混合'路线上，且约 80% 成型**——文档的分歧在代码里早已务实解决。

证据：

| 层 | 形态 | 证据 |
|---|---|---|
| **外层循环** | 控制派残留：按预播种 `chain_order` 序列迭代 | `ctf_dispatcher.py:449` `while chain_index < len(chain_order)` |
| **内层动作选择** | 协议派：黑板 Fact/Intent/Hint 投影注入 prompt，模型自选 | `llm_executor.py:302-326` `project_blackboard(...)` + "prefer the top active intent" + `ctx.llm(prompt)` |
| **排序** | 轻量建议（非算法控制器）：value→directness(最短链)→confidence | `blackboard.py:138` `intents.sort(key=lambda i:(i["refuted"],-i["value_score"],-i["directness"],-i["confidence"]))`（全文件仅 152 行） |

即：红队 V2 的 `path_shortening_bonus / 最短链` 思想**已实现，但作为给模型的排序建议**，不是 Dijkstra 硬控制器；黑板方案的"协议为主、决策权给模型"**也已落地**（B2 slice）。纯 A 与纯 B 谁都没建。

**决策（✅ 已批准 2026-06-27，O1=C 形式化混合，见 §7-O1）**：**形式化混合为唯一路线**。理由：
- 代码已投票（80% 成型），形式化是低成本；砸向纯 A（Dijkstra 控制器）高成本且跟模型能力赛跑、文档 B 已论证会变冗余代码；拆掉 ranking 退纯 B 会复活"够不着"病（无代码遍历兜底）+ 弱模型崩 + 无法守护。

**形式化契约（O1=C 的精确定义，守护测试钉死）**：
- **C1 代码拥有宏观 `chain_order`**：外层 `while chain_index < len(chain_order)`（`ctf_dispatcher.py:449`）保证**遍历 = 覆盖 + 终止 + I5 可达**。每个排序假设经 `_CHAIN_BY_KIND` 必映射到链（N4 守护已钉）。
- **C2 模型拥有链内动作**：黑板投影（`llm_executor.py:307`）照旧，模型在一条链内自由选动作。
- **C3 模型可发"重定向意图"调顺序，但不删条目**：模型/黑板高分 intent 可把链顶到前面（经假设注入→`recovery.py` 重排 honored），但**够得着的链最终都必须被遍历**——模型只能改 ORDER，不能删 ENTRY。这是两个排序权威（代码重排 vs 模型重定向）的 **precedence 底线**：代码保覆盖，模型只加速。
- **C4 directness 保持建议**：`blackboard.py:138` 的 directness/最短链仍是投影进 prompt 的排序建议，**不升级成算法控制器**（省掉跟模型赛跑成本）。
- **C5 主动探索归代码侧**（N9）：ε-greedy/强制试未试链作为**确定性重排加成**落在 `hypothesis_engine` 排序里，受 C1 覆盖底线约束（只重排不删），不夺 C2 链内自由。

**"强能力够不着"的真正杠杆 = `chain_order` 播种，不是控制哲学**：
- 历史实证（记忆 [[project_web_chain_reachability_sqli]]）：随便注 SQLi 6m27s 未解，把 `generic_param_sqli` 追加进 web 链后 59s 解出——根因是该 chain **不在 chain_order 里，内层黑板再聪明也轮不到**。
- 目标修法：**让黑板高分 intent 能把不在 chain_order 里的链动态顶进来**（intent→动态扩 chain_order），而非重写控制器。这是一刀小手术（见 §6-N4）。I5 守护应相应升级为"注册策略在真实运行里可达"。

### 3.2 KnowledgeMemory 门面 = 待建第三关节（关节 C）

**今天知识层一致性审计的核心发现**：担心的"职责重叠"基本不存在——7 个记忆/知识组件语义边界其实干净；真正的债是**没有中心化门面**（各自裸 new、3 条互不相交装配链：dispatcher / crew / session），由此连出 2 个真 bug（§4）。

7 组件归位（亲核测绘）：

| 组件 | 性质 | 存储 | 作用域 | 归属 |
|---|---|---|---|---|
| `harness/session_ledger` | **唯一事实源** append-only 事件流 | JSONL | 单 session | **门面·事实源** |
| `tools/notes`（note_store 封装） | 本题发现 | `loot/notes.json`（workspace 路由） | 单题 | **门面·记录** |
| `strategy_memory` | 跨题 learned 经验 | `loot/strategy_memory.json`(JSONL) | 跨题持久 | **门面·学习** |
| `knowledge/rag` | 外部静态知识检索 | `knowledge/embeddings/index.json` | 跨题静态 | **门面·知识库** |
| `knowledge/graph`(ShadowGraph) | notes 派生攻击图 | 纯内存（从 notes 重建） | 单 session | **门面·攻击图** |
| `exploit_replay_memory` | 内置 exploit 配方+运行期重建 | 不落盘 | 单题 | ⚠️ 实为 capability，**命名误导**（§4） |
| `capability_registry` | 工具健康/降级路由 | 纯内存 | 运行期 | capability 层，**不属知识门面** |

**门面 API**（`flaghunter/agents/pa_agent/memory_facade.py` — ⚠️ **非** `knowledge/`；见下"归属修正"）：
```python
class KnowledgeMemory:
    ledger: SessionLedger                  # 唯一事实源
    # —— 写（一切落盘走 workspace 路由，统一根目录）——
    def record_fact(event): ...            # → ledger
    def record_finding(note): ...          # → notes(本题) + ledger
    def record_learned(retro): ...         # → strategy_memory(跨题) + ledger
    # —— 读 / 检索 ——
    def recall_strategy(fingerprint): ...  # ← strategy_memory（修复 §4-Bug1 格式）
    def search_knowledge(query): ...       # ← RAG
    def attack_graph(): ...                # ← ShadowGraph（从 ledger/notes 派生）
    # —— 统一投影（注入 LLM planner）——
    def project_for_prompt(): ...          # {facts, intents, hints}
```
原则（取自黑板方案 §2.3，本文采纳为硬约束）：
- **唯一事实源 = Ledger**，投影是纯只读派生，**绝不持久化第二份真相**。
- 落盘统一走 `workspaces.utils.get_loot_file`（修 §4-Bug2）。
- `exploit_replay_memory` / `capability_registry` **不进** KnowledgeMemory（它们是 capability 层），但应改名消歧（§4）。

**归属修正（as-built，N3c 实证）**：草案把门面放 `knowledge/`，但门面组合 `strategy_memory` / `session_context`（都在 `agents/pa_agent` = ORCHESTRATION）。若放 `knowledge/`（CAPABILITY）则 import 它们=CAPABILITY→ORCHESTRATION，**违反 I1，被 N2 的 `.importlinter` 当场拦下**。门面正确归属由"它组合什么"决定 = **`agents/pa_agent/memory_facade.py`**（与消费者 ContextAssembler 同层，向下 import knowledge、平行 import strategy/session_context）。教训：门面层级不能拍脑袋，由依赖闭包反推；执法层（import-linter）正是在此处替我们把关。

**N3 收官（2026-06-27，双 agent 并行 + 主控亲核 + 用户拍板"读侧先收口"）**：
- ✅ **N3a（39e55c1）修 Bug2**：writer(StrategyMemoryStore)/reader(ProjectMemory._load_learned_rules) 统一走新增单一解析器 `workspaces.utils.get_strategy_memory_file`（精度 env>workspace>global），杜绝 workspace 模式下二者分裂（否则 N1 复活的 learned_rules 注入会再断）。5 守护 + 724 回归零回归。
- ✅ **N3b（b7d8cbc）消 base_agent→session_store 真债**：改依赖注入 + 优雅降级（SESSION 层 initializer:386 早已注入，lazy 自构造多余），删 import 边，`.importlinter` orchestration-below-session 契约**零 baseline 全清**。169 回归零回归。
- ✅ **N3c（本提交）门面本体 + 读侧接线**：`memory_facade.py` 建为**协调器非新存储**（owns no state / persists no 2nd truth），读侧 `project_context`/`rag_search`/`session_run_context`/`search_knowledge`/`attack_graph` 接进 ContextAssembler（**字节级一致**，3 守护 + 14 单测 + 637 回归零回归），recall/写侧 `recall_strategy`/`record_learned`/`record_finding` **定义为对同一 canonical sink 的诚实薄委托**（非假 stub=无第二写真相）；**3 条写链暂不强迁**（下一增量 N3c-2）。

### 3.3 七问七答（目标态 vs 当前缺口 vs 落点）

| 你的问题 | 目标架构 | 当前缺口 | 落点 |
|---|---|---|---|
| **如何执行** | coordinator 持 8 stateless executor，按 ChainContext 驱动 | ✅ 结构已做 | `coordinator` + `*_executor.py` |
| **如何解题** | solve-loop = 混合控制面（外层 chain_order + 内层黑板协议） | ⚠️ 80% 成型，待形式化 + chain_order 动态化 | `ctf_dispatcher._run_solve_loop:411` |
| **怎么查知识库** | 经 KnowledgeMemory.search_knowledge 统一检索 | ❌ RAG 散装裸 new ≥6 处，无门面 | 关节 C·RAG |
| **怎么记录** | 单一 Ledger 事实源 + Notes 投影 | ⚠️ 清楚但无统一门面 | 关节 C·Ledger/Notes |
| **怎么学习** | 解题后 record_learned→strategy_memory→下题 recall_strategy 注入 | 🔴 **learned_rules 注入坏死**（§4-Bug1） | 关节 C·StrategyMemory |
| **网络搜集** | web_search 作为 recon executor 一能力，结果进 Ledger | ❌ 无架构，孤立 tavily tool | recon_executor + Ledger |
| **多 agent / 模块化** | 单 agent 为主 + crew 可选，经同一门面/事件总线 | ⚠️ 装配已拉齐(D4)，协作智能(M5 蚁群)悬空默认关 | `crew/` + M5 |

---

## 4. 已确证缺陷（2026-06-27 审计坐实，带 file:line）

| # | 缺陷 | 证据 | 严重度 |
|---|---|---|---|
| **Bug1** | `project_memory` 读 `strategy_memory.json` 格式契约错位 → **跨题 learned_rules 注入静默坏死** | 写=JSONL（`strategy_memory.py:188` append + `_load_entries:781` 逐行）；读=整文件 `json.loads` 找 `data["entries"]`（`project_memory.py:90`）。≥1 条 entry 时必返 `[]`，`except` 吞掉无声 | 🔴 高（智能主链死） |
| **Bug2** | `strategy_memory` 落盘**无视 workspace 隔离** | `strategy_memory.py:78` 硬编码 `Path("loot")`，仅 env 可覆盖；而 `note_store` 走 workspace 路由（`tools/notes/__init__.py:70/93`）。开隔离时两份记忆落不同根 | 🟡 中 |
| D1 | `KnowledgeIndexer` 类生产无人构造 + chunking 双实现 | rag.py 只借 `resolve_knowledge_scan_paths`，切块 `rag.py:222-269` 与 `indexer.py:173-224` 重复 | 🟢 低（死代码） |
| D2 | `workspaces/utils.py:120` `graph` 持久化路径是死配置 | ShadowGraph 永不落盘，与该路径矛盾 | 🟢 低 |
| D3 | `exploit_replay_memory` 命名误导 | 叫 "memory" 但不持久化、不跨题，实为"内置配方运行期重建" | 🟢 低（命名） |

---

## 5. 防屎山执法层（回答"好不好维护 / 预防屎山"）

诚实判断：治理**意识与骨架优秀**（控制面三足 ADR+基准+流程、守护测试心法、能力层主动对账），但**自动化护栏是点状而非面状**。最该有的两项恰恰缺：

### 5.1 import-linter（I1 自动化）— 最高优先

当前 I1"依赖单向向下"只是纸面不变量 + 2~3 个手写断言，**无 `.importlinter`、无全局依赖图守护**。模块一多，跨层乱 import 不会被自动拦。
- 动作：写 `.importlinter` 配置声明 6 层 + 单向规则，进 CI。**这是单人+AI 项目防屎山的命根子。**

### 5.2 其余护栏

| 护栏 | 现状 | 目标 |
|---|---|---|
| 不变量守护测试 | 点状（I2/I5 有，I1/I3 无面状） | I1–I5 全覆盖守护测试 |
| eval 确定性回归门 | **未进 CI**（基准 S5 标"无"） | 进 CI：改 prompt/策略把已解题搞挂→自动红 |
| lint 阻断 | `continue-on-error: true` 不阻断 | ruff+black 阻断合并 |
| 覆盖率门槛 | 仅 30% | 分阶段抬升 |
| 失败分类 | 10 类散在字符串（`recovery.py`） | `FailureCategory` enum + 可重试/终止硬区分（绝不重试 ValueError/TypeError） |
| 新增模块规约 | 靠人记 | 模板 checklist：注册可达测试 + 门面接入 + 不变量绑定 |
| 风险登记 risk register | ❌ 缺 | 建立 |
| 文档叙事对账 | roadmap/cpa/verifier 对"权限门现状"描述不一致 | 本 V3 收敛，后续以本文为准 |

---

## 6. 照图施工路线（增量，非重写）

铁律：**增量重构，绝不推倒重写**；每刀独立 commit 可回滚；每项绑 DoD + 守护测试 + 不变量。

| 序 | 任务 | 优先 | DoD | 守护 |
|---|---|---|---|---|
| **N1** | 修学习链路（Bug1） | 🥇 P0 | `project_memory` 按 JSONL 读，或调 `strategy_memory.load_learned_rules()` API（去裸路径耦合）；写 N 条后 prompt 能拿到 rules | 新回归测试：注入 N 条→`get_context_for_prompt` 含 rules |
| **N2** | import-linter（I1） | 🥈 P0 | `.importlinter` 声明 6 层单向，CI 跑通现状 0 违规 | CI job |
| **N3** | KnowledgeMemory 门面（关节 C） | P1 | ✅ **收官**（N3a Bug2 / N3b base_agent DI / N3c 门面+读侧接线 ContextAssembler）；门面落 `agents/pa_agent/memory_facade.py`（归属修正见 §3.2）；写侧 3 链暂不迁=N3c-2 | ✅ 门面 14 单测 + ContextAssembler 字节级守护 + import-linter 4 kept |
| **N4** | 控制面形式化 + chain_order 动态化 | P1 | 文档化混合为既定；高分 intent 可动态扩 chain_order；I5 升级为"真实运行可达" | 可达性回归（含 generic_param_sqli 型 fixture） |
| **N5** | web_search 归位 + 全量 ledger | P2 | web_search 进 recon executor；动作（成功+失败）全量入 ledger | — |
| **N6** | 死代码清理 + 命名（D1/D2/D3） | P2 | KnowledgeIndexer/重复 chunking 收敛单实现；删 graph 死路径；`exploit_replay_memory` 改名 | 全量门零回归 |

---

## 7. 决定 / 未决 / 不做（诚实边界）

**已决（本文确认）**：
- 6 层骨架 + I1–I5 不变量（§2）保留为硬约束
- KnowledgeMemory 门面（关节 C）为目标架构（§3.2）
- 防屎山护栏面状化，import-linter 最高优先（§5）
- 施工增量、绑守护测试（§6）
- **✅ O1 控制面最终形式 = C（形式化混合），2026-06-27 用户拍板批准为唯一路线**。否决纯 A（高成本+跟模型赛跑+文档 B 证冗余）与纯 B（复活"够不着"病+弱模型崩+无法守护）。精确契约 C1–C5 见 §3.1。N9 主动探索照此落代码侧。

**显式不做（非目标）**：
- 不重写 foundation 依赖、不改 LLM provider/api_hub 路由
- 不把控制面砸成纯 A（Dijkstra 算法控制器）——文档 B 已论证会变冗余
- 不用数据库替 JSONL、不拆双进程、不重写 crew
- 不在结构债治理期新增叶子 CTF 解题能力补丁

---

## 8. 与既有不变量/治理的衔接

- 本文不替代 `项目工程治理流程_V1.md` 的流程（七阶段生命周期、逐功能内循环、WIP 限制），只替代**架构内容**。
- 本文不变量 I1–I5 与治理流程一致；新增的护栏（§5）是治理流程"回归门待建"的具体兑现项。
- 验证/解题判定（done-criteria 四条硬规则）与评估指标，仍以 `基准_验证与解题判定_2026-06-18_V1.md` / `基准_评估指标与失败分类_2026-06-18_V1.md` 为准，本文 §3.3"如何解题"与之衔接。

---

## 9. 被收敛文档索引（指针，原文保留作历史依据）

| 文档 | 本文如何收敛 |
|---|---|
| `FlagHunter_架构决策记录_自顶向下骨架与两关节契约_2026-06-17_V1.md` | §2 全盘采纳（结构维），固化为骨架 |
| `FlagHunter_红队智能体架构_对标顶级红队工程学_2026-06-17_V2.md` | §3.1 采纳"最短链/directness"思想（已落地为排序建议）；不采纳"算法控制器"主张 |
| `FlagHunter_架构优化方案_黑板控制单元与façade收尾_2026-06-16_V1.md` | §3.1/§3.2 采纳"协议为主、唯一事实源、投影不持久化第二真相" |
| `FlagHunter_红队黑板智能体架构学习笔记_2026-06-17_V1.md` | 背景笔记，§3 综合参考 |
| `docs/agent-intelligence-roadmap.md` | §3.3/§5 部分采纳（解除强制计划、子代理、可观测）；权限门叙事与 cpa M4 对账，以本文为准 |
| `cpa_modules_m1-m6_职责对照表_2026-06-20_V1.md` | §2.1 capability 层引用，保留为能力层权威 |
| `项目工程治理流程_V1.md` | §5/§8 衔接，流程部分不被替代 |
| `结构债总账_全仓审计_2026-06-23_V1.md` | 结构债执行账本，与本文 §6 互补（账本记"已做什么"，本文记"该往哪走"） |

---

## 10. 能力维现状与扩展接缝（2026-06-27 四路代码亲核追加）

本节把"将来只加能力层就行"的愿景落到**扩展接缝**上：哪些接缝已稳、哪些缺。证据均 file:line。

### 10.1 四接入口对照（怎么看 / 展示什么 / 区别）

| 入口 | 技术 | 做题时实际展示 | 适用 |
|---|---|---|---|
| TUI | Textual | 对话流+工具结果+CTF 文本面板（reasoning belief/status/queue/memory/flag 分桶），按需快照、纯文本、信息密度最高 | 本地交互 |
| CLI | argparse(main.py)+Typer(cli.py，**双入口债**) | `run/tui/mcp_server/workspace/ctf`，日志流 | 批量/脚本 |
| Web Console | **aiohttp + React SPA**（`web/console/` 7 页）+ **SSE 实时** | dashboard/tasks/traces(SVG 执行轨迹图)/memory/knowledge/logs；状态徽章/token/checkpoint/hint 交互 | 远程/可视化 |
| MCP Server | MCP stdio/SSE | 不展示，暴露 `run_task` 等工具表给 Claude Desktop/Cursor | 被其它 AI 编排 |

注意：①CLI 双入口债（argparse+Typer）；②**Web 可视化虽强但 CTF 专用状态没做成 Web UI**，与 TUI 文本面板不对齐。

### 10.2 感知链：agent 如何探知环境 + 采集有效信息（Runtime→diagnose→phase_recon→CTFState）

10.1 讲"信息怎么出去（展示）"，本节讲**信息怎么进来**——agent"睁眼看世界"的完整链路。这是"只加能力层"愿景里**最被忽视的一条接缝**：感知断了，上层再聪明也是盲打。证据均 file:line。

**对外接口边界（你问的"具体实现依靠能力层、是不是还有对外接口"——是）**：能力层对外的唯一法定接缝 = `Runtime` ABC（`runtime.py:381`），agent 逻辑层只对着 5 个动词编程、**从不直接** new socket/subprocess/playwright：

```
   agent 逻辑（chains / strategies / hypotheses / recon_executor）—— 只表达"意图"
        │
        ▼  ═══════ Runtime ABC（对外接口·5 动词，I1 钉死，import-linter[N2] 执法）═══════
   execute_command │ browser_action │ proxy_action │ start·stop │ is_running·get_status
        ▲  —— 实现"怎么做"
   LocalRuntime / DockerRuntime / SSHRuntime / HybridBrowserRuntime
   （旁路：tools/loader 自注册工具 · mcp/manager 消费外部 MCP server）
```

**感知链五环（实证流水线）**：

```
① 自知（能力探测）  browser_action("diagnose") → BrowserCapabilities   runtime.py:357
   ├ 铁律(H18)：能力是"运行时决定"非"类静态" → 调用方必须探测、绝不按类假设
   └ 字段：available / engine(playwright|cli_fetch) / rendered_dom / js_execution
            / cookies / supports_actions[...]
        │  （同一 LocalRuntime：装了 Playwright=rendered_dom，没装=cli_fetch；Docker/SSH 恒 curl）
        ▼
② 采集（phase_recon）                                                  recon_executor.py:92
   ├ diagnose 通过 → navigate → get_content → get_forms → get_cookies  （浏览器渲染态）
   ├ 无论如何再 proxy_action("get") 补采/回退                          recon_executor.py:226
   ├ 抽端点 / 表单 / 内嵌链接 + _fingerprint_framework（8 签名）+ 惯例路由播种
   └ 优雅降级而非崩：缺工具记 recon_missing_tools、错误记 recon_errors  dispatcher_helpers.py:854
        │  产出 page_features{html,content,title,forms,cookies,endpoints,recon_errors,...}
        ▼
③ 定型（detect_type）  page_source+url → web/sqli/xss/lfi/ssrf/upload/jwt/misc   ctf_planner.py:324
        │  （纯证据启发式 → 喂 choose_chain_order 播种 chain_order，即 N4 那条链的源头）
        ▼
④ 沉淀（CTFState）  add_observation(kind/value/source/metadata) + add_artifact(name+location 去重)
        │                                                              ctf_state.py:196 / :234
        ▼
⑤ 认知（黑板 → 假设 → 决策）  blackboard 投影 → HypothesisEngine 消费 → choose_chain_order
   = "感知 → 认知 → 决策"闭环，接回 §3.1 混合控制面
```

**架构原则落点**：你全局 CLAUDE.md 的"先被动观察"在此**字面编码**——先 diagnose 探针、再渲染态采集、curl 兜底、失败软记录，全程不抛异常。

**这条链上的三处断点（机制丰富，认知通道窄）**：

| # | 断点 | 后果 | 落点 |
|---|---|---|---|
| 🔴 | ②采集只取 html/text；**截图存盘不喂模型**（`runtime.py:1151`/`browser/__init__.py:124`） | 感知链在"视觉"维断裂——图片 flag/二维码/隐写/验证码全瞎 | **N7 多模态**（详 §10.3） |
| 🔴 | ③`detect_type` 是**硬编码启发式非模型驱动** | 启发式未覆盖的题型一律退 `web` 兜底，定型粗糙 | N7 顺带（vision/LLM 辅助定型）或留观 |
| 🟡 | ①能力探测**只覆盖 browser**，`execute_command`/`proxy_action` 无对称 capability-probe | shell 能力（nmap 等）靠失败后记 `recon_missing_tools`，无主动自检 | 待办：对称探针（小手术，非 N 系列） |

**一句话**：对外接口 = `Runtime` 5 动词（I1/import-linter 钉死）；探知环境 = `diagnose` 能力探针（铁律：探测不假设）；采集信息 = `phase_recon` 五环流水线沉淀进 `CTFState`/黑板供假设消费。**缺口集中在"纯文本、无多模态"，即 §10.3 + N7。**

### 10.3 模型与多模态（两个诚实的"没有"）

- 接入成熟：LiteLLM 统一层 + `m1_api_hub` 多 provider failover/错误分级/预算（`llm.py:285-388`）。支持 Anthropic/OpenAI/**DeepSeek**/Ollama/中继。默认故意无兜底 model（`constants.py:64-75`）。
- **DeepSeek = 能用非一等公民**：有 reasoning_content 适配（`llm.py:32-57`），但 `model_router` 智能择优**只内建 Claude/GPT 两族打分**（`model_router.py:92-125`），DeepSeek 不被主动择优。
- 🔴 **模型效果无实测**：benchmarks 无 model 字段、eval/replay 不用 LLM（`eval/replay.py:1-11`）。**回答"Claude vs DeepSeek 效果"须先建模型横评 eval**。
- 🔴 **多模态对 LLM 完全没有**：消息体永远纯文本，无 image 通道；截图只存盘不喂模型（`runtime.py:1151`/`browser/__init__.py:124`）；唯一图像识别是硬编码 easyocr 验证码 OCR（`dispatcher_helpers.py:1123`，非 LLM）。**对 CTF 是真能力缺口**（图片 flag/二维码/隐写/验证码全瞎）。

### 10.4 可视化（半成型 + 一处浪费）

- Web>TUI。Web 有 SSE + SVG 图，但**那图是"执行事件时间线"非攻击链路图**（`traces.jsx:772`）。
- 🔴 **最大浪费**：黑板（facts/intents/hints/decision）**已序列化进 API**（`web_server.py:525`），数据已到浏览器，**前端零渲染**（`web/console/src` grep blackboard 无命中）。
- 攻击链路图（ShadowGraph）只 `to_mermaid()` 文本（`graph.py:452`），TUI `/graph` 让用户自己拷到 mermaid.live，Web 不展示。**实时管道与数据都到位，差"画出来"的 UI 层。**

### 10.5 解题四环现状（细节锚点）

- **目标确认**：多路归一（用户 URL + docker-compose 端口推导 `coordinator.py:206` + 偏好端口打分）。无独立存活探针，靠 recon 隐式 + 冷启动重试（`ctf_dispatcher.py:1076`）。
- **信息收集**：`recon_executor.py`——浏览器探针 + 框架指纹（8 签名）+ 惯例路由播种 + 认证表单收割；单次 phase + 可重复探索议程（`add_exploration_item`，hint_strength 分级）。**完整感知链（对外接口→能力探测→采集→定型→沉淀→认知）见 §10.2。**
- **学习回路**：session 内置信度调整 → 跨题 `strategy_memory.json` 沉淀（learned_rules 强制泛化 `:1053`）→ 下次 query top-3 + 信息素重排 chain_order。**注意 learned_rules 注入今天证明坏死（§4-Bug1）。**

### 10.6 ★反僵化现状：受约束 exploitation + 缺主动探索

**好消息——已有 5 道护栏防"经验压制证据"**（非纯利用）：

| 护栏 | 机制 | 证据 |
|---|---|---|
| 幅度夹紧 | 记忆调整 clamp ±0.25，加性偏置不覆盖 | `strategy_memory.py:927` |
| 证据地板 | 无观察支持的假设被记忆抬过有证据者→降权 | `hypothesis_engine.py:107` |
| 矛盾清零 | 当前事实与记忆矛盾→调整置 0 | `hypothesis_engine.py:771` |
| 原子事实门控 | 正向加成需本题事实匹配历史，否则封顶 0.05 | `hypothesis_engine.py:784` |
| 时间衰减+自禁 | 30 天 ×0.9、<0.3 deprecated；坏经验 muted | `strategy_memory.py:861` |

外加信息素只重排不增删、web 链兜底、负反馈软降权不硬锁、被拒假设黑板保留可见排最后。

**真缺口——缺主动探索**：全仓无 ε-greedy/无随机/无强制试未试链；novelty 奖励形同虚设（`_base_score:702-703` `novelty_bonus=0.1` 再 `×0.1`→实际 +0.01，在 confidence×0.6 面前纯噪声）。当历史经验与当前证据都指向同一条已知失败路时，无随机扰动跳出，只能靠 LLM 兜底（确定性、排最后）。**这不是接缝问题，是控制面策略问题——归 §3.1 混合控制面，作显式探索策略加上去（如探索预算/N 轮无进展强制 novelty 链），不塞进 strategy_memory。**

**→ N9 落点（O1=C 之 C5，2026-06-27 开工）**：在 `hypothesis_engine` 排序里加**确定性两档主动探索**，受 §3.1-C1 覆盖底线约束（**只重排、绝不删除够得着的链**）：
- **档 1 常开有界**：修 `_base_score` 的 novelty 平方衰减（`×0.1` 掐死），让"未试假设/未试链"获得**真实但从属于证据**的加成（不越过证据地板 `:107 capped_ids` / ±0.25 夹紧）——同等证据下未试链浮过已试败链。
- **档 2 卡死升级**：`no_progress_rounds`（dispatcher 已追踪）越阈值时，给"未试 + 够得着"的链额外探索加成顶到前列（§10.6 的"N 轮无进展强制 novelty 链"），确定性、可守护、不夺模型链内自由。
- **确定性而非随机 ε-greedy**：守护测试需可复现（项目禁 `random`/`Math.random` 不确定性），故用"卡死触发 + 未试优先"的确定性规则替代随机探索，效果同源且可钉死。

### 10.7 扩展接缝总表（"只加能力层"的前置条件）

| 想加什么 | 接缝现状 | 缺口/落点 |
|---|---|---|
| 新攻击链/策略 | ✅ `StrategyRegistry`（关节B）干净插入 | chain_order 须够得着（N4） |
| 新工具 | ✅ `tools/loader` 自注册 | — |
| 新知识/记忆源 | ❌ 无门面，到处裸 new | **KnowledgeMemory 门面（关节C / N3）** |
| 新模型/provider | ⚠️ 能配能调 | router 择优不认非 Claude/GPT（N7 顺带） |
| **新输入模态（视觉）** | ❌ 完全无接缝 | **多模态消息层 + vision tool（N7）** |
| 新可视化 | ⚠️ SPA 页可加，数据已就绪 | 黑板/攻击图差渲染（N8） |

### 10.8 路线增补（并入 §6）

| 序 | 任务 | 优先 | DoD |
|---|---|---|---|
| **N7** | 多模态输入接缝 | P1 | LLM 消息层开 image 通道（base64/image_url）+ 一个 vision tool（截图/图片 flag/二维码/验证码送模型识别）；顺带 model_router 支持非 Claude/GPT 择优 |
| **N8** | 可视化接黑板/攻击图 | P2 | Web SPA 渲染 blackboardSnapshot（facts/intents/hints/decision，数据已在 `web_server.py:525`）；ShadowGraph 前端图形化（非 mermaid 文本） |
| **N9** | 主动探索策略 | P2 | 混合控制面加显式探索：探索预算或 N 轮无进展强制试一条 novelty 链；归 §3.1，不动 strategy_memory |

**模型横评能力**：要回答"Claude vs DeepSeek 效果"，须在 eval（`flaghunter/eval`）加 model 维度横评——当前 eval 不用 LLM，无此能力，列为 N5（全量 ledger）之后的增补项。

---

*本文为活文档的"决策层"。现状类断言若与代码不符，以代码为准并触发本文修订（出 V4）。*
