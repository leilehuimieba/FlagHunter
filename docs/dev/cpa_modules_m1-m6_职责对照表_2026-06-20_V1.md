# cpa_modules m1–m6 职责对照表（capability registry 收尾）

- **日期**：2026-06-20
- **版本**：V1
- **关联**：ADR §2 目标骨架（第 33 行「CAPABILITY tools/ cpa_modules/m1..m6 方向已干净，仅命名/文档」）、
  ADR §5 路线图表 P5 行（DoD=模块职责对照表）。
- **范围**：本表只覆盖**能力层** `flaghunter/cpa_modules/`。
  与之同名易混的 `flaghunter/agents/pa_agent/capability_registry.py`（**工具**能力注册表）
  是另一概念，不在本卡范围。
- **统一注册入口**：六个模块只经 `flaghunter/session/initializer.py` 的 CPA 钩子
  （`init_mN` 调用，第 264–323 行）初始化；各模块的 `/xxx` 命令则由
  `flaghunter/interface/tui.py` 的 `_parse_*_command` 硬编码分发
  （能力层不使用 `command_registry` 抽象，详见 §3）。

---

## 1. 模块职责对照表

| 模块 | 包名 | 职责（实际行为） | 暴露能力（`__all__` 关键项 / 开关 / 注册函数） | 主要调用方 |
|---|---|---|---|---|
| **M1** | `m1_api_hub` | 多 Provider LLM API 枢纽：`init_m1` 加载 `M1Config`，建 `CostTracker`/`ProviderManager`/`FailoverMonitor`、注册全部 Provider、启动故障切换后台监控。子模块：`config_schema` / `cost_tracker` / `failover_monitor` / `model_router` / `models` / `provider_manager` / `status_display`。 | `init_m1`、`is_m1_enabled`、`get_provider_manager`、`get_cost_tracker`、`get_failover_monitor`、`ProviderConfig`/`ProviderState`/`ProviderStatus`/`M1Config`。**无** `register_*_commands`。 | `session/initializer.py:266`（**唯一真正调用 `is_m1_enabled()` 门控的模块**）；运行时 `llm/llm.py`（provider 选择/成本/故障切换）、`interface/tui.py`（`/api`）、`agents/pa_agent/ctf_dispatcher.py:725`。 |
| **M2** | `m2_ctf_kit` | CTF 工具链：`init_m2` 探测 pwnlib/Crypto/r2pipe/capstone/requests，建 `PlaybookEngine`、载 playbook，注入 `ctf_commands`。子模块：`crypto_tools` / `ctf_commands` / `flag_submitter` / `playbook_engine` / `pwn_tools` / `reverse_tools`。 | `init_m2`、`is_m2_enabled`、`get_playbook_engine`、`is_ctf_tool_available` + 一组 `CPA_M2_*` 开关常量。命令以 `cmd_ctf*` 函数形式存在。 | `session/initializer.py:278`（env `CPA_M2_CTF_KIT` 门控）；运行时 `interface/tui.py`（`/ctf`）、`agents/pa_agent/verifier.py`（`submit_flag`）、`platform_executor.py`（`get_platform_snapshot`）。 |
| **M3** | `m3_reporter` | 渗透报告子系统：`init_m3` 建 `TemplateEngine→ReportGenerator→ScreenshotCatcher→IncrementalTracker`。子模块：`template_engine` / `report_generator` / `report_models` / `screenshot_catcher` / `incremental_tracker` / `html_exporter` / `markdown_exporter` / `pdf_exporter`。 | `init_m3`、`is_m3_enabled`、`get_m3_status`、`get_report_generator`/`get_screenshot_catcher`/`get_incremental_tracker`、`PentestReport`/`ReportMeta`/`Finding`/`Severity` 等。**无** `register_*_commands`。 | `session/initializer.py:288`（env `CPA_M3_REPORTER`）；运行时 `interface/tui.py`（`/report`）、`tools/finish/__init__.py`（`get_report_generator`/`is_m3_enabled`/`ReportMeta`）。 |
| **M4** | `m4_audit_guard` | 合规审计守卫：`init_m4`（锁保护、全异常吞掉）建 `AuditLogger`/`RoEEngine`/`ScopeEnforcer`/`ApprovalGate`/`DataProtector`。子模块：`audit_logger`（sha256 链式 JSONL）/ `roe_engine` / `scope_enforcer` / `approval_gate` / `data_protection`。 | `init_m4`、`is_m4_enabled`、`get_audit_logger`/`get_roe_engine`/`get_scope_enforcer`/`get_approval_gate`/`get_data_protector` + 各数据类。**无** `register_*_commands`。 | `session/initializer.py:298`（env `CPA_M4_AUDIT_GUARD`）；**真正的执法接入点** `tools/executor.py:346`（`get_audit_logger`/`get_scope_enforcer`）；`interface/tui.py`（`/audit`）。 |
| **M5** | `m5_swarm_link` | 多 Agent 群体协作（默认 OFF，需 `CPA_M5_SWARM_LINK=true`）：`init_m5` 懒导入核心类，建 `SharedBlackboard`（SQLite）/`PheromoneRouter`、起信息素衰减后台任务；`AgentMessenger`/`ConsensusMechanism` 按 agent 懒建。子模块：`shared_blackboard` / `pheromone_router` / `agent_messenger` / `consensus_mechanism` / `swarm_commands`。 | `init_m5`、`is_m5_enabled`、`get_blackboard`/`get_pheromone_router`/`get_messenger`/`get_consensus_mechanism` + 四核心类（经 `__getattr__` 懒加载暴露，见 §2 修复项）。**无** `register_*_commands`。 | `session/initializer.py:308`（env `CPA_M5_SWARM_LINK=="true"`，默认关）；运行时 `agents/crew/swarm_bridge.py`（`get_messenger`/`get_pheromone_router`）、`interface/tui.py`（`/swarm`）。 |
| **M6** | `m6_turbo` | 性能加速基础设施：`init_m6` 建 `ResultCache`(TTL+LRU)/`ParallelScanner`/`MemoryOptimizer` 并起内存监控。子模块：`result_cache` / `parallel_scanner` / `memory_optimizer` / `lazy_loader` / `turbo_commands`。 | `init_m6`、`is_m6_enabled`、`shutdown_m6`、`apply_turbo`、`get_cache`/`get_scanner`/`get_optimizer`、`ResultCache`/`ParallelScanner`/`LazyLoader`/`MemoryOptimizer`。`turbo_commands.py:672` 有 `register_turbo_commands`（**未接线**，见 §3）。 | `session/initializer.py:318`（env `CPA_M6_TURBO`）；运行时 `interface/tui.py`（`/turbo`，直接 import `is_m6_enabled`/`cmd_turbo`）。 |

---

## 2. capability registry 一致性对账（`__all__` / 导出 ↔ initializer 调用）

逐模块对账「`__init__.py` 的 `__all__` + `init_mN`/`is_mN_enabled` 导出」与
`session/initializer.py` 实际 import/调用列表。

| 对账项 | 结论 |
|---|---|
| **六模块均定义 `init_mN` + `is_mN_enabled`** | ✅ 一致。六个 `init_mN` + 六个 `is_mN_enabled` 全部存在且在各自 `__all__`。由守卫测试 `tests/unit/config/test_cpa_modules_capability_registry.py::test_module_exposes_init_and_enabled_contract` 锁定。 |
| **initializer 门控方式** | ⚠️ 语义差异（**保留现状，不改行为**）：M1 在 `initializer.py:268` 真正调 `is_m1_enabled()` 门控；M2–M6 在 initializer 处直接读各自环境变量门控，**未调用各自的 `is_mN_enabled`**——这些函数仍被 TUI/运行时其它处消费，非死代码。此外「enabled」语义在模块间不统一：`is_m1/3/4_enabled` 是纯 env 检查；`is_m2/5_enabled` 额外要求 `_initialized=True`（init 成功前返回 False）。属设计选择，记录备查。 |
| **悬空导出（`__all__` 里不存在的符号）** | M1/M2/M3/M4/M6 ✅ 无。**M5 曾有**：`SharedBlackboard`/`PheromoneRouter`/`AgentMessenger`/`ConsensusMechanism` 在 `__all__` 但仅 `TYPE_CHECKING` 下导入，运行时 `from m5 import *` 直接 `AttributeError`。**本卡已修**：在 m5 `__init__.py` 末尾加 PEP 562 `__getattr__` 懒加载这四个类，使其运行时真正可导入（既保留"避免顶层循环依赖"的原意，又让 `__all__` 诚实）。守卫 `test_all_exports_are_resolvable` + `test_m5_core_classes_are_importable_at_runtime`。 |
| **悬空注册（`register_*_commands` 未接线）** | ⚠️ M6 `register_turbo_commands`（`turbo_commands.py:672`）是全仓**唯一**的 `register_*_commands`，但**无任何调用方**，仓库内不存在 `command_registry` 消费者；`/turbo` 实际由 `tui.py::_parse_turbo_command` 硬编码分发。**本卡处置**：保留函数（预留统一命令注册体系），docstring 标注「尚未接线」，不删不改行为。 |
| **M6 透明 wrapper 自动挂载** | ⚠️ docstring 原称「M0 侵入点自动挂载、对 M2–M5 透明加速」，实际 `apply_turbo()` 在工具层**零调用点**、`_wrap_tool` 只登记工具名未真正包裹。**本卡处置**：改写 docstring 如实说明（init 走 session initializer 钩子、实际面是 `/turbo`、透明挂载属预留未接线），不改行为。 |

---

## 3. 命令分发现状（为何 `command_registry` 抽象在能力层未用）

六个模块的 slash 命令全部由 `flaghunter/interface/tui.py` 的硬编码 `_parse_*_command`
方法分发：M1 `/api`、M2 `/ctf`、M3 `/report`、M4 `/audit`、M5 `/swarm`、M6 `/turbo`。
M6 的 `register_turbo_commands` + 它指向的 `command_registry` 抽象当前为预留/未用。
若未来要统一命令注册，应让 M0/initializer 持有一个 `command_registry` 并接线
`register_turbo_commands`（并为 M2/M5 等补对应注册函数）——属后续工作，不在本卡。

---

## 4. 名实不符 / 待复核清单（仅记录，未改行为）

| 模块 | 现象 | 本卡处置 |
|---|---|---|
| M6 | docstring「M0 侵入点自动挂载 / 透明加速」与实现不符；`apply_turbo` 无调用点、`_wrap_tool` 未真包裹；`LazyLoader` 导出但 `__init__` 内未实例化 | docstring 已校准为如实描述；`register_turbo_commands` 加「未接线」说明。行为不动。 |
| M5 | 四核心类 `__all__` 悬空导出 | 已用 `__getattr__` 修复（§2）。 |
| M3 | 顶部注释「仅在类型检查时循环引用，运行时正常导入」措辞误导（导入其实是无条件顶层执行） | 注释已校准。 |
| **M4** | `init_m4` 第 84–85 行 `DataProtector(mask_ips=not mask_sensitive, mask_emails=mask_sensitive, ...)`：`mask_ips` 取 `mask_sensitive` 的**反**值——`CPA_M4_MASK_SENSITIVE=true`（默认）时 IP 脱敏被关闭，`=false` 时反而开启，读起来与开关语义相悖。`DataProtector` 默认 `mask_ips=False`，故默认值下无可见差异，异常仅在 `=false` 时显现。 | ⚠️ **疑似 bug，但语义存在歧义（可能有意"报告里保留 IP"）**。按卡 B 纪律「仅明确 bug 才单列改+加测试」，本项**只记录待复核、不改行为**，避免在低风险文档卡里夹带行为变更。 |

---

## 5. DoD 核对

- [x] 六模块职责对照表落到 `docs/dev/`（本文件，§1 每模块一行）。
- [x] `__all__`/导出 ↔ `initializer` 调用逐项对账成文（§2），差异列出并在范围内修正（M5 悬空导出已修）。
- [x] 六模块均有非空模块级 docstring（守卫 `test_module_has_non_empty_docstring` 校验；`cpa_modules/__init__.py` 包级 docstring 亦补齐）。
- [x] 全套件零回归（守卫测试新增，详见提交说明与 ADR §5.2）。
