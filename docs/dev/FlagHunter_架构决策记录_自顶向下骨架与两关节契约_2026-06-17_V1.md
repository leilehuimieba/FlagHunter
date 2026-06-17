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
- 已有 `StrategyContext`(`strategy_registry.py:14`):`{dispatcher:Any, target, page_features, hint, extras}` —— **半成型,但 `dispatcher:Any` 仍是上帝对象透传**。
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
- **chains/ 子包**:dispatcher 上的 40 个 chain 方法物理迁出到 `pentestagent/agents/pa_agent/chains/{web,sqli,xss,ssti,upload,jwt,misc,cmdi,ssrf,lfi}.py`,每个注册为 `StrategyDefinition`。`ctf_dispatcher.py` 收缩为「装配 + 主循环 + 路由」。

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
| **P3** | `_execute_chain` if/elif → registry;引入 `ChainContext` 破上帝对象 | B | 中高 | §4.3 前两条 |
| **P4** | 拆 `chains/` 子包,低耦合先行(misc/cmdi/ssrf/lfi → sqli/jwt/upload → web/xss/ssti) | B | 中高 | §4.3 后两条 |
| **P5** | cpa_modules m1..m6 命名/文档、capability registry 收尾 | 能力层 | 低 | 模块职责对照表 |

每阶段硬性 gate(沿用现有纪律):
- full unit suite 零新增失败(deselect 2 个 `*_on_kali` 测试);必要时跑 integration。
- 逻辑拆 commit;conventional 前缀 + `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`;直推 main。
- 每个对外行为变更配 live 或单测回归证据。
- **不提交 `challenges/`。**

---

## 5.1 已知债:组合根错位(P1-b/P2 清理)

`build_agent_components`(及 `build_runtime`)现住在 `interface/initializer.py`,但它本质是**组合根**(composition root):向下 import agents/llm/tools/runtime 装配一切,理应被所有入口依赖、位置在 entry 层之下。`AgentSession` 在 `session/`,若模块级 import 它即构成 `session→interface` 反向依赖(违反 I1)。

- **P1-a 临时处置(已落地)**:`AgentSession.create` 通过**延迟(函数内)import** 或注入式 `builder` 参数引用组合根,**无模块级环**;单测用 fake builder 注入。
- **P1-b/P2 正解**:把 `build_agent_components/build_runtime/activate_workspace_for_target` 迁到 `session/`(或新 `bootstrap/`)中立层,`interface/initializer.py` 改为 re-export 保后向兼容,届时删除延迟 import。

## 5.2 进展日志

- **P0 完成**(commit `65de99a`):本 ADR + 契约选型。
- **P1-a 完成**(commit `d6c1712`):`session/event_bus.py`(中立 EventBus,I3)+ `session/agent_session.py`(`AgentSession` 门面 + `RunResult`,I2),10 单测,零回归(1521 passed)。独立新代码,未触入口。
- **P1-b 进行中(CLI 已迁)**:`interface/cli.py` 三模式(ctf/crew/default)全部经 `AgentSession.create` 装配,删除手工 `build_runtime/LLM/get_all_tools/PentestAgentAgent` 构造 → **CLI 的 CPA M1–M6 不再被跳过**(bug 关闭)。新增结构守卫单测 `test_cli_uses_agent_session.py` 锁定 I2;原 `test_cli_local_asset_contract.py` 的 4 个 run_cli 测试改打桩到门面 seam(`AgentSession.create`)。CTF 模式 LLM 仍是 `temperature=0.7`(与门面一致)→ **行为零扰动**。
  - **待续**:web_server / MCP server / TUI 三入口尚未迁(各自仍 hand-roll 或部分经 `build_agent_components`);事件总线适配(web 私有 EventBus / TUI notifier / MCP `_emit` → 中立 `EventBus`)留待这些入口迁移时一并做。

## 6. 显式非目标(本轮不做)
- 不重构 foundation 依赖方向(已健康)。
- 不改 LLM provider / api_hub 路由逻辑。
- 不在 P1–P4 期间新增 CTF 解题能力(叶子能力补丁暂停,直到骨架就位)——这正是本 ADR 要纠正的旧惯性。

---

## 7. 契约选型(已确认 2026-06-17)
1. **`AgentSession` 落在 `pentestagent/session/`**(与 SessionStore/会话生命周期同居,且对非 interface 的 MCP 更中立)。
2. **P1 先改 CLI**(最小、独立)验证门面契约 + 顺手修 cpa-skip bug,再依次推 web / MCP / TUI。
3. **新建中立 `EventBus`**(放 `pentestagent/session/`);web 现有 EventBus、TUI notifier 回调、MCP `_emit` 逐一适配到这条中立总线。
