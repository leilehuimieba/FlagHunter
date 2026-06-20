# 架构决策记录(ADR):自顶向下骨架与两关节契约 V1

- 日期:2026-06-17
- 状态:**已确认 / P0 完成**(零代码改动;选型见 §7)
- 起因:历史优化多为「叶子打补丁」(在 `ctf_dispatcher` 方法或某条 web 策略上补能力),层与层之间各修各的、接不回上层。本 ADR 改为**自顶向下**:先把骨架与层间契约定死,再逐层下沉优化。

---

## 1. 现状诊断(三路静态审计结论)

| 维度 | 结论 | 性质 |
|---|---|---|
| 层间依赖方向 | 严格向下、无循环;foundation(`runtime/llm/config/knowledge/session`)与 capability(`tools/cpa_modules`)**无上向依赖**。`llm/llm.py` 对 `cpa_modules.m1_api_hub` 的引用是函数内动态 import,不构成模块级环。 | **地基健康** |
| 关节 A(入口→编排) | 4 入口仅在 `BaseAgent.agent_loop()` 类层统一;编排/事件/结果生命周期**全碎片**。已有共享初始化器 `build_agent_components()`,但**只有 TUI / main.py 用,CLI / web_server 绕过** → cpa_modules m1–m6 被静默跳过(correctness bug,行为不一致)。 | **缺契约 + 1 bug** |
| 关节 B(编排→策略) | `_execute_chain` 用硬 if/elif 分发而非 registry;40 个 chain 方法约 **60% 硬编码 / 40% 在 registry**;chain 全靠 `self.state / self.strategy_memory / self.runtime` 上帝对象隐式取状态,无显式传参。 | **缺契约 + 上帝对象** |

**核心判断**:骨架地基(依赖方向)优秀,缺的是两个**承重关节没浇筑契约**。本 ADR 只定这两个契约 + 落地顺序。

---

## 2. 目标骨架

```
ENTRY(薄)      TUI   CLI   web   MCP          只做 I/O + 渲染;不直接 new LLM/Tools/Runtime
                         │  仅依赖关节 A 契约
SESSION ★A     AgentSession 门面               关节 A:唯一装配入口 + 单一事件总线 + 结果/会话生命周期
                         │  agent_loop 契约
ORCHESTRATION  BaseAgent.agent_loop()          契约已在,P2 仅校验 + 薄适配
                         │  关节 B 契约
STRATEGY ★B    StrategyRegistry 单一分发        关节 B:registry 驱动取代 if/elif
               chains/{web,sqli,xss,ssti,...}   ChainContext 显式传状态,拆上帝对象
                         │
CAPABILITY     tools/   cpa_modules/m1..m6      方向已干净,仅命名/文档
FOUNDATION     runtime llm knowledge config     无环
```

不变量(Architecture invariants,任何阶段不得破坏):
- **I1 依赖单向向下**:foundation 不得 import capability/orchestration/entry;capability 不得 import orchestration/entry。CI/审计可用 grep 守。
- **I2 唯一装配入口**:任何入口构造 agent 必须经 `build_agent_components()`,不得自己 new LLM/Tools/Runtime。
- **I3 事件单源**:agent 运行产生的事件只走一条总线(关节 A 的 EventBus),入口只订阅、不自建并行机制。
- **I4 chain 不读 self 上帝对象**:策略/chain 通过 `ChainContext` 取所需状态,禁止新增对 `dispatcher.*` 的隐式访问(存量逐步收敛)。

---

## 3. 关节 A 契约:`AgentSession`(入口 ↔ 编排)

### 3.1 现状落点(真实代码)
- 共享装配器:`pentestagent/interface/initializer.py:167` `async def build_agent_components(...) -> dict[str, Any]`,返回 `{agent, runtime, runtime_info, rag_engine, ...}`,内部按标准顺序初始化并触发 cpa_modules m1–m6 钩子(`initializer.py:252-311`)。
- 运行契约:`pentestagent/agents/base_agent.py:262` `async def agent_loop(initial_message: str) -> AsyncIterator[AgentMessage]`。
- 现有碎片化事件路径:TUI 用 `interface/notifier.py` 回调;web 用私有 `EventBus`(`web_server.py`);CLI 用 `rich` 直输;MCP 用全局 `_emit` + `_ui_hook`。

### 3.2 目标契约(P0 仅定义,P1 落地)
新增 `pentestagent/session/agent_session.py`,作为 4 入口与编排层之间的**唯一门面**:

```python
class AgentSession:
    """入口与 agent 引擎之间的唯一门面。封装装配、运行、事件、结果生命周期。"""

    @classmethod
    async def create(cls, *, target=None, scope=None, model=None,
                     docker=False, ssh=False, no_rag=False, no_mcp=False,
                     on_progress=None) -> "AgentSession":
        """唯一装配路径 —— 内部必须调用 build_agent_components(...)。
        消除 CLI/web 跳过 cpa 初始化的 bug(满足 I2)。"""

    def events(self) -> "EventBus":
        """单一事件总线;入口只订阅这里(满足 I3)。事件为结构化 dict/dataclass,
        统一替代 notifier 回调 / web 私有 EventBus / MCP _emit 三套。"""

    async def run(self, task: str) -> "RunResult":
        """驱动 agent_loop(task);逐条 AgentMessage 转成事件 emit 到 events();
        汇总为 RunResult{flag, findings, tokens, status, session_id}。"""

    def session_store(self) -> "SessionStore": ...
    def metrics(self) -> "MetricsCollector": ...
```

入口改造后职责收敛为:`session = await AgentSession.create(...)` → 订阅 `session.events()` → `await session.run(task)` → 渲染 `RunResult`。**TUI/CLI/web/MCP 不再各自 new LLM/Tools/Runtime,不再各搞事件机制。**

### 3.3 关节 A「完成定义(DoD)」
- 4 入口全部经 `AgentSession.create` → `build_agent_components`(I2 成立,grep 审计无旁路)。
- 4 入口事件都来自 `session.events()`(I3 成立);notifier/web-EventBus/MCP-_emit 三套收敛为一套(或后两者成为对单一总线的薄适配)。
- CLI/web 不再跳过 cpa m1–m6(bug 关闭,补一条「CLI 启用 M2/M3/M5」的回归断言)。

---

## 4. 关节 B 契约:`ChainContext` + registry 分发(编排 ↔ 策略)

### 4.1 现状落点(真实代码)
- 已有 `ChainContext`/兼容别名 `StrategyContext`(`strategy_registry.py:14`):`{dispatcher:Any, target, page_features, hint, extras, state, runtime, capability_registry, strategy_memory, exploitation_mode}` —— **显式字段已叠加,但 `dispatcher:Any` 仍作为过渡期兼容能力透传**。
- 已有 `StrategyDefinition`(`strategy_registry.py:23`):`{kind, chain_name, precondition, execute, ...}` + `is_applicable(ctx)`。
- 分发现状:`_execute_chain`(`ctf_dispatcher.py:2291`)硬 if/elif on `chain_name`;约 60% chain 逻辑仍是 dispatcher 上的 `_execute_*/_attempt_*/_run_*_strategy` 方法(共 40 个),未进 registry。
- 结果类型:`_ChainOutcome{progress, flag, reason}`(`ctf_dispatcher.py:268`)。

### 4.2 目标契约(P0 仅定义,P3/P4 落地)
- **`ChainContext`**:由现有 `StrategyContext` 演进。把 chain 真正需要的状态**显式字段化**,替换 `dispatcher:Any` 透传:
  ```python
  @dataclass
  class ChainContext:
      target: str
      page_features: dict
      state: "CTFState"            # 显式,而非 dispatcher.state
      strategy_memory: "StrategyMemory"
      runtime: "Runtime"
      capability_registry: "CapabilityRegistry"
      exploitation_mode: str       # aggressive / conservative
      hint: str = ""
      extras: dict = field(default_factory=dict)
  ```
  过渡期允许保留 `dispatcher` 引用做兼容,但新代码只准用显式字段(I4);存量逐 chain 收敛。
- **registry 驱动分发**:`_execute_chain` 改为按 `chain_name` 从 `StrategyRegistry` 取该链有序策略并跑 `_run_strategy_sequence`,取代 if/elif。保留现有语义:**仅 `outcome.flag` 短路,progress 不短路**(这是已验证 4 次的「末尾追加桥接策略零回归」前提,不能改)。
- **chains/ 子包**:dispatcher 上的 40 个 chain 方法物理迁出到 `flaghunter/agents/pa_agent/chains/{web,sqli,xss,ssti,upload,jwt,misc,cmdi,ssrf,lfi}.py`,每个注册为 `StrategyDefinition`。`ctf_dispatcher.py` 收缩为「装配 + 主循环 + 路由」。

### 4.3 关节 B「完成定义(DoD)」
- `_execute_chain` 无 chain 专属 if/elif(除最外层 registry 查询)。
- registry 覆盖率从 ~40% 提升到目标 100%(所有 chain 方法皆 `StrategyDefinition`)。
- 新增 chain 不再访问 `dispatcher.*` 隐式状态(`ChainContext` 显式传)。
- `ctf_dispatcher.py` 行数显著下降(目标主文件 < 2k 行,其余进 chains/)。

---

## 5. 自顶向下落地顺序

| 阶段 | 范围 | 关节 | 风险 | 主要 DoD |
|---|---|---|---|---|
| **P0** | 本 ADR:定骨架 + 两契约(纸面) | — | 无 | 经确认 |
| **P1** | `AgentSession` 落地;4 入口改走门面;修 CLI/web cpa-skip bug | A | 中(触 TUI/web 大文件) | §3.3 |
| **P2** | pa_agent & crew 校验同一事件/结果契约 | A→编排 | 低 | 两 agent 输出经同一总线 |
| **P3** | P3a 已完成:`_execute_chain` if/elif → handler map;P3b 渐进引入 `ChainContext` 破上帝对象 | B | 中高 | §4.3 前两条 |
| **P4** | 拆 `chains/` 子包,低耦合先行(misc/cmdi/ssrf/lfi → sqli/jwt/upload → web/xss/ssti) | B | 中高 | §4.3 后两条 |
| **P5** | cpa_modules m1..m6 命名/文档、capability registry 收尾 | 能力层 | 低 | 模块职责对照表 |

每阶段硬性 gate(沿用现有纪律):
- full unit suite 零新增失败(deselect 2 个 `*_on_kali` 测试);必要时跑 integration。
- 逻辑拆 commit;conventional 前缀 + `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`;直推 main。
- 每个对外行为变更配 live 或单测回归证据。
- **不提交 `challenges/`。**

---

## 5.1 已清理:组合根错位(P1-b/P2)

`build_agent_components`(及 `build_runtime`)本质是**组合根**(composition root):向下 import agents/llm/tools/runtime 装配一切,理应被所有入口依赖、位置在 entry 层之下。当前代码已将组合根迁入 `session/initializer.py`,避免 `AgentSession` 反向 import `interface` 层(满足 I1)。

- **P1-a 临时处置(已落地)**:`AgentSession.create` 通过**延迟(函数内)import** 或注入式 `builder` 参数引用组合根,**无模块级环**;单测用 fake builder 注入。
- **P1-b/P2 正解(已落地)**:`build_agent_components/build_runtime/activate_workspace_for_target/has_ssh_runtime_config` 已迁到 `session/initializer.py`;`interface/initializer.py` 退为 re-export 保后向兼容;`AgentSession.create` 默认从 session-owned composition root 延迟 import。

## 5.2 进展日志

- **P0 完成**(commit `65de99a`):本 ADR + 契约选型。
- **P1-a 完成**(commit `d6c1712`):`session/event_bus.py`(中立 EventBus,I3)+ `session/agent_session.py`(`AgentSession` 门面 + `RunResult`,I2),10 单测,零回归(1521 passed)。独立新代码,未触入口。
- **P1-b 进行中(CLI 已迁)**:`interface/cli.py` 三模式(ctf/crew/default)全部经 `AgentSession.create` 装配,删除手工 `build_runtime/LLM/get_all_tools/PentestAgentAgent` 构造 → **CLI 的 CPA M1–M6 不再被跳过**(bug 关闭)。新增结构守卫单测 `test_cli_uses_agent_session.py` 锁定 I2;原 `test_cli_local_asset_contract.py` 的 4 个 run_cli 测试改打桩到门面 seam(`AgentSession.create`)。CTF 模式 LLM 仍是 `temperature=0.7`(与门面一致)→ **行为零扰动**。
- **P1-web 完成**:装配 `77a2618`(修 CPA-skip)+ EventBus 统一 `c25d967`(web 私有 EventBus → 中立适配器)。
- **P1-mcp 完成** `6a0ca41`:MCP 本就经 `build_agent_components`(无 CPA bug),纯 I3——`_emit`/`_ui_hook` → 中立 EventBus。
- **P1-tui 完成** `c25f747`:**关键发现**——TUI 本就经 `build_agent_components`(无 CPA bug);I3 只需把 `notifier.notify` 通道 bus 化(TUI 一行未动,`register_callback` 自动订阅);3 个控制通道(spawn/despawn/wake-up,带返回值的定向 hook)保持原样。
- **关节 A 全闭合**:I2 全线达成(CLI/web 修了 bug,MCP/TUI 本就合规);I3 全线达成(web/MCP/notifier 均收敛到中立 EventBus)。
- **P2 顺带达成**:crew(orchestrator/worker_pool)与单 agent 都走 `notify()` → 随 notifier bus 化即同源;`RunResult` 结果契约在 `AgentSession`。
- **P1-b/P2 组合根下沉完成**:`session/initializer.py` 成为中立组合根,`interface/initializer.py` 仅作兼容 re-export;新增 `test_default_builder_lives_below_interface_layer` 与 `test_interface_initializer_is_compatibility_reexport` 锁定该契约。
- **P3a 完成**:`_execute_chain` 收缩为 handler map 路由 + 统一 LLM fallback;XSS/Web 共享预跑语义下沉到 `_execute_xss_route/_execute_web_route`;新增 `test_execute_chain_routes_through_handler_map_without_chain_specific_branches` 防止 chain 专属分支回流。
- **P3b 第一刀完成**:`StrategyContext` 演进为 `ChainContext`(保留 `StrategyContext` 兼容别名),显式携带 `state/runtime/capability_registry/strategy_memory/exploitation_mode`;`CTFTaskDispatcher._strategy_context()` 统一填充这些字段;SSTI/hash/render 相关 precondition 已优先读 `context.state`,避免新增 `dispatcher.state` 直读。
- **P4 低耦合链拆分完成(8 chain mixin 全部迁出)**:`cmdi/ssrf` 已在 `chains/injection.py`;LFI 固定文件读取探针已迁入 `chains/file_read.py::LFIChainMixin`;misc registry 顺序执行 + LLM fallback 已迁入 `chains/misc.py::MiscChainMixin`;JWT 薄路由已迁入 `chains/jwt.py::JWTChainMixin`;upload 通用上传编排入口已迁入 `chains/upload.py::UploadChainMixin`;SQLi registry/sqlmap 编排入口已迁入 `chains/sqli.py::SQLIChainMixin`;XSS 路由 + 链入口已迁入 `chains/xss.py::XSSChainMixin`;Web 路由 + 固定策略序列入口已迁入 `chains/web.py::WebChainMixin`,SSTI 三段管线仍作为 Web 策略序列保留。dispatcher 对这些链只保留 mixin 组合和 handler 委托。新增 `test_lfi_chain_handler_is_delegated_to_file_read_chain_mixin` / `test_lfi_chain_mixin_builds_existing_probe_commands` / `test_dispatcher_misc_chain_method_comes_from_misc_mixin` / `test_dispatcher_jwt_chain_handler_delegates_to_jwt_mixin` / `test_upload_chain_entrypoint_lives_in_upload_chain_mixin` / `test_sqli_chain_entrypoint_lives_in_sqli_chain_mixin` / `test_xss_chain_entrypoints_live_in_xss_chain_mixin` / `test_web_chain_entrypoints_live_in_web_chain_mixin` 锁定物理迁出和等价入口。
- **P5 第一刀(执行体迁出)完成**:把侦察执行体 `_phase_recon`(约 327 行)从 `ctf_dispatcher.py` 物理迁入新文件 `pa_agent/recon_executor.py::ReconExecutorMixin`,沿用 P4 的混入类套路(方法体逐字搬运、`self.*` 运行时解析、调用点 `coordinator._apply_recon_contract -> dispatcher._phase_recon` 不变)=纯代码搬家近零风险。配套把 recon 专用正则常量 `_SCRIPT_SRC_RE`/`_BACKUP_CLUE_RE` 下沉到无环的 `dispatcher_helpers.py`(经 `import *` re-export,避免 mixin↔dispatcher 循环 import)。`ctf_dispatcher.py` 行数 9733→9405(−328)。新增 `test_recon_phase_lives_in_recon_executor_mixin` 锁定模块归属。**注意**:这是 Workstream A 的安全增量(物理迁出),尚未做激进版——coordinator 仍通过透明 `RunContext` 调 `dispatcher._phase_recon`,真正"coordinator 持有 executor 实例、断开 `self.*` 透传"需重写 contract 依赖注入,高风险,留待后续。
- **P5 第二刀(post-auth recon/auth 表单簇)完成**:`_candidate_auth_page_urls`/`_harvest_auth_forms_from_routes`/`_attempt_post_auth_recon`/`_find_registration_form`/`_build_account_form_submission`(333 行)迁入 recon_executor。新依赖 `find_auth_form` 从无环的 `.ctf_planner` import,表单 helper 从 `dispatcher_helpers` import;`_form_action_url`/`_is_legacy` 留 dispatcher。9405→9074(−333)。守卫扩展 `test_post_auth_recon_methods_live_in_recon_executor_mixin`。
- **P5 第三刀(exploration agenda 簇)完成**:`_populate_exploration_agenda_from_recon`/`_seed_framework_conventional_routes`/`_explore_agenda_items`(120 行)迁入 recon_executor,零新 import(符号已齐),self 依赖(`_should_ignore_exploration_candidate`/`_classify_exploration_hint_strength`/`_scan_and_store`)与类属性 `_FRAMEWORK_CONVENTIONAL_ROUTES` 留 dispatcher 经 MRO 解析。9074→8954(−120)。守卫扩展 `test_exploration_agenda_methods_live_in_recon_executor_mixin`。recon 簇主体迁移完成,`recon_executor.py` 现约 817 行;`ctf_dispatcher.py` 自 P5 起 9733→8954(−779)。
- **P5 第四刀(LLM 执行体簇)完成**:LLM 驱动探索/动作执行的 15 方法连续簇(`_run_llm_driven_exploration`→`_expected_signal_met`,734 行)迁入新文件 `pa_agent/llm_executor.py::LLMExecutorMixin`。调研确认**无障碍符号**:依赖全部已 import 或在 helpers(`parse_llm_json`/`_ChainOutcome`/`LLMStepLog`/`PreActionReasoning`/`StrategyContext`/`_base_target` + stdlib),`project_blackboard` 保持簇内动态导入避免循环。14 方法仅簇内调用,`_run_llm_driven_exploration` 被簇外 2 处(`_execute_chain`、SSTI)调用,mixin self 解析无影响。两个 @staticmethod(`_extract_llm_action_text`/`_looks_like_loopback_or_file_target`)装饰器保留。8954→8220(−734)。守卫 `test_ctf_llm_executor.py`。自 P5 起累计 9733→8220(−1513)。
- **P5 第五刀(flag 文本/拒绝/候选簇)完成**:`_extract_flag`/`_extract_php_var_dump_strings`/`_extract_runtime_flag`/`_is_rejected_flag`/`_looks_like_css_false_flag`/`_load_rejected_flags`/`_store_flag_candidate`(7 方法连续块,152 行)迁入新文件 `pa_agent/flag_parser.py::FlagParserMixin`。前置下沉障碍符号 `_FLAG_RE`/`_STRICT_FLAG_RE` 到 `dispatcher_helpers.py`(+`__all__`,mixin 显式 import);`get_all_notes_sync` 已在顶部 import,`self.state`/`_store_note` 留 dispatcher。8220→8063(−157,含删常量)。守卫 `test_ctf_flag_parser.py`。**注意**:flag 簇里 `_observe_flag`/`_record_wrong_flag_feedback`/`_hydrate_flag_proof`(+辅助 `_recent_relevant_observations`/`_observation_reference`/`_format_reproduction_steps`)物理分散且 hydrate 带辅助簇,留后续刀(它们同样可 mixin 迁出——调研 agent "依赖重不可迁"的判断不成立,mixin 不定义 `__init__`、`self.verifier` 等运行时解析,与已迁 LLM 簇调 runtime 同理)。自 P5 起累计 9733→8063(−1670)。
- **P5 第六刀(JWT helper 簇)完成**:连续 6 方法块(`_collect_candidate_jwts`/`_jwt_mutation_candidates`/`_jwt_algorithm_candidates`/`_jwt_secret_candidates`/`_encode_none_jwt`/`_jwt_request_headers`,约 158 行)迁入新文件 `pa_agent/jwt_executor.py::JWTExecutorMixin`。`_jwt_encode` 已在 `dispatcher_helpers.__all__` 经 re-export → **无障碍符号需下沉**,mixin 仅 `import re`/`Any`/`_jwt_encode`;`self.state`/`_recent_local_source_hint_secret_candidates` 留 dispatcher 经 MRO 解析。注意离群的 `_jwt_target_candidates`(line ~1125)非本簇,未动。8061→7903(−158)。守卫 `test_ctf_jwt_executor.py`。自 P5 起累计 9733→7903(−1830)。
- **P5 第七刀(platform 簇)完成**:连续 5 方法块(`_snapshot_platform_context`/`_infer_platform_profile`/`_infer_challenge_id`/`_align_platform_challenge`/`_build_already_solved_reason`,约 262 行)迁入新文件 `pa_agent/platform_executor.py::PlatformExecutorMixin`。`flag_submitter` 系列 import 保持簇内动态导入(原样)→ **无障碍符号需下沉**,mixin 仅 `import os`/`re`/`Any`/`urlparse`/`parse_qs`;`self.state`/`platform_orchestrator`/`_infer_*`(簇内)经 MRO 解析。注意紧随其后的 `_record_wrong_flag_feedback` 属 flag 簇(下一刀候选),未动。7903→7641(−262)。守卫 `test_ctf_platform_executor.py`。自 P5 起累计 9733→7641(−2092)。
- **P5 第八刀(flag-proof 簇)完成**:连续 5 方法块(`_record_wrong_flag_feedback`/`_hydrate_flag_proof`/`_recent_relevant_observations`/`_observation_reference`/`_format_reproduction_steps`,约 205 行)迁入新文件 `pa_agent/flag_proof.py::FlagProofMixin`。先派 Explore agent 测绘:确认**零障碍符号**(只用 `typing.Any` + 已 import 的 `FlagProof`),物理连续(6727–6932);依赖 `self.state`/`hypothesis_engine`/`_store_note`/`_pending_wrong_flag_feedback`/`_current_fingerprint` 全经 MRO 解析。入口枢纽 `_observe_flag`(离群 174 行,~6448)留 dispatcher,经 MRO 调到这些方法。7641→7436(−205)。守卫 `test_ctf_flag_proof.py`。自 P5 起累计 9733→7436(−2297)。
- **P5 第九刀(note/artifact 存储簇)完成**:连续 6 方法块(`_store_secret_note`/`_store_missing_tools`/`_store_retrospective`/`_store_note`/`_derive_artifact_producer`/`_derive_artifact_category`,约 141 行)迁入新文件 `pa_agent/note_store.py::NoteStoreMixin`。**零障碍符号**:依赖全部已 import(`typing.Any`/`urlparse`/`build_missing_tools_recorded_event`/`notes_tool`),无需下沉常量;`self.*`(`state`/`runtime`/`reasoning_layer`/`_record_session_event`/`_select_hypothesis_for_chain`/`_register_artifact_record`/`_notes_log`/`_emit`)全经 MRO 解析。簇内 `_store_note` 被簇外多处调用,迁出后经 MRO 等价解析无影响。7438→7297(−141)。守卫 `test_ctf_note_store.py`。自 P5 起累计 9733→7297(−2436)。**全套件 469 passed 零回归。**
- **P5 第十刀(flag 验证入口 `_observe_flag`)完成**:单方法(105 行)迁入新文件 `pa_agent/flag_observer.py::FlagObserverMixin`。先派 Explore agent 测绘:确认它是全仓 30+ 处调用的**唯一 flag 验证入口**,与紧邻的 5 个物理邻居(`_apply_submit_profile`/`_record_uniform_failure_surface`/`_restore_context`/`_select_hypothesis_for_chain`/`_snapshot_flag_counts`)语义无关(分属 submit-profile/strategy-memory/checkpoint/hypothesis-routing/progress-delta 子系统的"杂物抽屉"),逐一排除——其中 `_select_hypothesis_for_chain` 还会引入 `_CHAIN_NAME_FOR_HYPOTHESIS` 下沉成本,更不该捆迁。**零障碍符号**:`build_verification_decision_event` 直接从无环叶子 `harness.audit_events` import,`urlparse` 用 stdlib,无需下沉。`self.*` 全经 MRO 解析:`_hydrate_flag_proof`/`_record_wrong_flag_feedback` 在 FlagProofMixin、`_store_note` 在 NoteStoreMixin、`_record_session_event`/`state`/`verifier`/`_active_*_context` 留 dispatcher;`flag_proof.py` docstring 早已声明"`_observe_flag` 留 dispatcher 经 MRO 调到这些方法",本刀把"留 dispatcher"改为"留另一 mixin",MRO 行为完全等价。30+ 调用点(dispatcher/coordinator/chains/llm_executor)零改动。7297→7193(−104)。守卫 `test_ctf_flag_observer.py`。自 P5 起累计 9733→7193(−2540)。**全套件 470 passed 零回归。**
- **P5 第十一刀(progress-delta 簇)完成**:紧耦合连续对 `_snapshot_flag_counts`(16 行)+ `_derive_progress_delta`(34 行)迁入新文件 `pa_agent/progress_tracker.py::ProgressTrackerMixin`。这是第十刀测绘时点名排除的"杂物抽屉"里**唯一语义自洽的一对**(`_derive_progress_delta` 调 `_snapshot_flag_counts` 算假设引擎的进度信号)。**零障碍符号**:两方法只读 `self.state`(`candidate_flags`/`runtime_flags`/`verified_flags`/`rejected_flags`/`observations`),不引用任何模块级 import/常量,新文件仅需 `from __future__ import annotations`;`chain_outcome` 是 duck-typed 参数(`_ChainOutcome`)无需 import。调用点全经 MRO 不变:`_snapshot_flag_counts`(dispatcher ~462 + 簇内)、`_derive_progress_delta`(coordinator ~1300 `dispatcher._derive_progress_delta(...)`)。7193→7143(−50)。守卫 `test_ctf_progress_tracker.py`。自 P5 起累计 9733→7143(−2590)。**全套件 471 passed 零回归。**
- **P5 第十二刀(审计/持久化基础设施簇)完成**:文件末尾连续 13 方法块(`_setup_session_ledger`/`_setup_artifact_registry`/`_setup_checkpoint_store`/`_record_session_event`/`_write_checkpoint`/`_register_artifact_record`/`_record_recovery_decision`/`_resolve_registered_local_challenge_paths`/`_resolve_registered_local_key_files`/`_ingest_registered_local_source_hints`/`_runtime_browser_action`/`_runtime_proxy_action`/`_runtime_execute_command`,约 297 行)迁入新文件 `pa_agent/audit_infra.py::AuditInfraMixin`。先派 Explore agent 对 7143 行做全局结构测绘,在三个候选(审计基础设施 / render-surface+strategy-context / upload 表单助手)中选定本簇:**职责最单一**(整块即"审计/账本/检查点/注册表底座",全部经唯一汇聚点 `_record_session_event` 出口),**零障碍符号、零前置下沉**——所有模块级依赖(`SessionLedger`/`ArtifactRegistry`/`CheckpointStore` + 五个 `build_*_event`)均从无环 `harness.*` 直接 import(与 `note_store.py` 走的 `harness.audit_events` 同路径,已证无循环)。后备属性(`_session_ledger`/`_artifact_registry`/`_checkpoint_store`/`_ledger_run_id`/`_artifact_run_id`/`_checkpoint_run_id`/`_registered_local_source_hints_loaded`)留 `__init__` 初始化,经 `self` 由 MRO 解析;~105 处调用点全是 `self.*` 零改动。紧邻的 UI 透传 `_emit` 非审计职责,留 dispatcher 保持 mixin 纯净。`AuditInfraMixin` 置于继承列表首位。7143→6846(−297)。守卫 `test_ctf_audit_infra.py`。自 P5 起累计 9733→6846(−2887)。**全套件 472 passed 零回归。**

### P3 风险发现(深度测绘,2026-06-17)
`_execute_chain` 的 if/elif 已安全改为 handler map(**P3a 完成**)。但**关节 B 的「破上帝对象」(P3b)高风险**:所有注册策略通过 `context.dispatcher.*` 访问 dispatcher 全部能力(`_run_strategy_sequence` 每轮重建 `ctx=_strategy_context(dispatcher=self)`),strategy_registry 里 40+ lambda 全依赖 `ctx.dispatcher._run_*/_attempt_*/state/strategy_memory/...`。用 ChainContext 显式字段**替换** dispatcher 透传 = 重写这 40+ lambda + 所有 chain 方法,动 live 调过的 CTF 核心,**单测绿 ≠ 解题行为不变**。故 P3 拆分:
- **P3a**:`_execute_chain` if/elif → handler map 分发(已落地,行为等价、机械、安全)。
- **P3b**:ChainContext 破上帝对象——**已完成「叠加显式字段、保留 dispatcher 兼容」第一刀**;下一步逐 strategy/executor 把 `ctx.dispatcher._run_*` 下沉到 chains/ 或显式服务字段,不做一次性替换。

## 6. 显式非目标(本轮不做)
- 不重构 foundation 依赖方向(已健康)。
- 不改 LLM provider / api_hub 路由逻辑。
- 不在 P1–P4 期间新增 CTF 解题能力(叶子能力补丁暂停,直到骨架就位)——这正是本 ADR 要纠正的旧惯性。

---

## 7. 契约选型(已确认 2026-06-17)
1. **`AgentSession` 落在 `pentestagent/session/`**(与 SessionStore/会话生命周期同居,且对非 interface 的 MCP 更中立)。
2. **P1 先改 CLI**(最小、独立)验证门面契约 + 顺手修 cpa-skip bug,再依次推 web / MCP / TUI。
3. **新建中立 `EventBus`**(放 `pentestagent/session/`);web 现有 EventBus、TUI notifier 回调、MCP `_emit` 逐一适配到这条中立总线。
