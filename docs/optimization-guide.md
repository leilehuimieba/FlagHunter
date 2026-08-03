# 项目优化与治理指南

> 文档状态：Active / Canonical
>
> 当前版本：V2.10
>
> 最近更新：2026-08-03
>
> 适用版本：FlagHunter v0.4.1 及后续演进版本
>
> 适用范围：架构、功能能力、代码质量、运行时、数据、运维、安全、成本、发布与文档治理
>
> 权威性：本文件是当前仓库唯一有效的综合优化与治理指南。历史 Gap Report、Roadmap、审计记录和阶段性设计稿保留为证据，不再分别承担当前优先级的真相源。

---

## 0. 文档定位

### 0.1 本文解决什么问题

本文统一回答以下问题：

1. FlagHunter 当前已经具备哪些能力，哪些能力只是“存在”但还没有达到稳定、可信、可运营的状态。
2. 目前最值得优先优化的地方是什么，为什么它们比继续增加策略或工具更重要。
3. 每个功能域负责什么、当前主要问题是什么、应如何优化、如何检测质量、预期达到什么效果。
4. 如何建立代码质量、架构质量、运行质量、事实可信度和真实解题率的统一检测体系。
5. 如何补齐部署、监控、告警、容量、备份、恢复、发布、回滚、供应链和事件响应等运维能力。
6. 哪些容易被忽略的问题会在项目规模扩大、远程部署、多 Agent 并发或长期运行后暴露。
7. 如何把已有大量文档收口为少数入口，避免“文档越多，真相越难找”。

### 0.2 本次工作的边界

本次仅整理和优化文档：

- 不修改任何业务代码、测试代码、配置实现或运行逻辑。
- 不编写代码示例、利用示例、测试用例或部署实例。
- 不执行单元测试、集成测试、端到端测试、基线评测或 live 任务。
- 文中的现状判断来自当前仓库的静态结构、配置、工作流、接口和近期提交记录。
- 所有目标值均为建议的治理目标，不代表本次已经验证通过。

### 0.3 阅读方式

- 项目负责人优先阅读第 1、2、3、5、13、15 节。
- 架构和核心开发优先阅读第 4、6、7、10 节。
- 运维和交付负责人优先阅读第 8、9、11、13 节。
- 做具体优化任务时，直接使用第 14 节的工作流程和完成定义。

---

## 1. 结论先行

### 1.1 总体判断

FlagHunter 已经不是一个只有 LLM 调用和工具包装的早期原型。当前仓库已经具备：

- 多入口会话装配与 Agent 主循环。
- 确定性 CTF dispatcher、hypothesis、strategy、capability、verifier、recovery 和 strategy memory。
- Local、Docker、SSH 三类运行时。
- TUI、CLI、Web Console、MCP Client、MCP Server 多种交互和集成面。
- Domain、Application、Ports、Adapters 的中立契约骨架。
- claim、evidence、proof、receipt、trace、checkpoint、task graph 等结构化契约。
- 工具作用域校验、审计日志、数据脱敏、报告、指标和会话留痕。
- 真实赛题分层基线、录制/回放和评估框架。

当前主要矛盾已经从“缺少功能”转为以下五类问题：

1. **控制面真实性不足**：停止、取消、完成、成功等状态在部分入口并不完全等价于真实运行行为。
2. **能力存在但治理不闭环**：lint、类型、架构约束、依赖安全、容器安全和文档一致性尚未全部成为阻断式门禁。
3. **核心模块持续膨胀**：dispatcher、coordinator、runtime、presentation、MCP 和大型测试文件仍然承担过多职责。
4. **运行与数据可靠性不足**：大量 JSON/JSONL 本地状态依赖进程内锁或直接覆盖写，面对多线程、多进程、崩溃和磁盘异常时缺少统一保证。
5. **运维产品化不足**：远程入口鉴权、健康检查、SLO、告警、资源配额、备份恢复、供应链和发布回滚还没有形成完整运行手册。

### 1.2 最优先的五件事

在继续扩展策略之前，建议按以下顺序处理：

1. 让停止、取消、超时、失败、成功与实际执行状态严格一致，杜绝“界面已停止但后台仍执行”。
2. 收紧 Web/MCP 远程控制面：非 loopback 绑定必须有鉴权、来源限制、审计、速率限制和明确部署模式。
3. 将 verified proof 作为唯一成功依据，统一 Web、MCP、TUI、CLI、指标、报告和终止状态的语义。
4. 建立阻断式质量门禁：格式、lint、类型、import-linter、依赖/密钥/容器扫描和关键契约检查。
5. 统一版本、依赖、配置、schema 和文档真相源，消除长期漂移。

### 1.3 不建议优先做的事情

现阶段不建议把主要精力放在：

- 无基线依据地继续增加大量低频策略。
- 为了文件变短而机械拆文件，但不改变责任边界和状态所有权。
- 全仓一次性严格化类型或一次性清理全部 lint，造成大面积无关 churn。
- 让 LLM 承担 proof 升级、权限裁决、状态恢复或预算终止等权威职责。
- 在没有单体闭环和任务隔离前继续放大 Crew 并发。
- 继续创建同主题、带日期和版本后缀的新规划文档。

---

## 2. 当前仓库审计快照

### 2.1 规模快照

以下数据来自 2026-07-31 的静态盘点：

| 项目 | 当前快照 | 说明 |
|---|---:|---|
| Python 源文件 | 432 | 覆盖核心包，不含测试目录 |
| Python 测试及测试辅助文件 | 402 | unit、integration、security、eval 等目录 |
| Markdown 文档 | 55 | `docs/` 下当前文件，总计约 20,195 行；根目录入口另计 |
| 静态注册工具 | 41 | 基于 `register_tool` 装饰器提取 |
| 策略定义 | 32 | 覆盖 SQLi、CMDi、SSRF、XSS、Web、Misc、JWT、GraphQL、NoSQL 等 |
| 默认 capability primitives | 13 | 含多实现降级路由 |
| 真实解题率基线题目 | 16 | T0=3、T1=4、T2=4、T3=5 |
| 函数/方法 | 4,423 | 静态 AST 统计，当前文件均可解析 |
| 超过 100 行的函数/方法 | 127 | 超过 200 行的有 35 个 |
| 超过 500 行的类 | 33 | 主要集中于 Agent、dispatcher、runtime 和 presentation |
| 广义 `Exception/BaseException` 捕获 | 912 | 无 bare except，但广义边界较多 |
| `Any` 名称使用 | 2,311 | 类型标注覆盖高，但动态边界仍大 |
| `type: ignore` 标记 | 93 | 需要建立例外台账和收敛策略 |

这些数字不是质量结论本身。它们用于定位风险热区和建立后续趋势基线，不能机械地以“越少越好”替代行为验证。

### 2.2 已有工程优势

| 领域 | 已有基础 | 应保留的方向 |
|---|---|---|
| 架构 | 已有 domain/application/ports/adapters/session 分层与 `.importlinter` 契约 | 继续增量迁移，不做全仓大重命名 |
| 事实治理 | claim、evidence、proof、verification record 已进入核心契约 | verifier/proof authority 保持唯一升级权 |
| 可达性 | StrategyRegistry、HypothesisEngine、CapabilityRegistry 已形成分发主干 | 优先修“注册但不可达”和错误路由 |
| 恢复 | RecoveryController、checkpoint、resume、memory 具备基础 | 统一失败分类、幂等恢复和负反馈 |
| 工具 | 41 个工具、ToolGuard、scope check、receipt/provenance 已存在 | 统一工具结果契约与运行时语义 |
| 运行时 | Local、Docker、SSH 抽象已形成 | 建立能力矩阵和一致性契约 |
| 观测 | session metrics、trace、ledger、Web dashboard、MCP metrics 已存在 | 统一事件模型、SLO、持久化和告警 |
| 评估 | 16 题分层 corpus、runner、judge、record/replay 已存在 | 用真实解题率驱动能力优先级 |
| 协作 | CI、Dependabot、CODEOWNERS、PR 模板、release 文档已存在 | 将软检查升级为硬门禁并去除重复文档 |

### 2.3 当前高风险事实

| 编号 | 优先级 | 当前事实 | 直接风险 | 关键证据位置 |
|---|---|---|---|---|
| F-01 | P0 | Web `stop_task` 主要修改状态并落盘，后台 daemon thread 没有对应强制取消句柄 | 操作者看到 stopped 后仍可能继续调用工具 | `flaghunter/interface/web_server.py` |
| F-02 | P0 | 部分修复：已新增通用 cancellation 原语，但已提交生产入口尚未消费；当前工作树存在 A-04 未提交草稿，仅开始为 MCP 异步任务保存句柄，取消信号尚未贯穿 dispatcher、agent、tool 和 runtime | 状态可能先变为 cancelled，而底层动作、资源清理或 blocking 任务仍未得到一致控制 | `flaghunter/domain/cancellation.py`、`flaghunter/mcp/server/mcp_tools.py` |
| F-03 | P0 | 部分收口：Web 非 loopback 绑定已要求静态 bearer token 并 fail-closed；但尚无 RBAC/action-resource 授权，CORS 仍允许任意 Origin，且当前 `?token=` 对全部 `/api/*` 生效而不只限于 SSE | URL token 可能进入日志、历史或 referrer；共享静态 token 无法表达最小权限，跨来源策略仍不完整 | `flaghunter/config/remote_access.py`、`flaghunter/interface/web_server.py`、`web_settings_*` |
| F-04 | P0 | 部分收口：MCP SSE 默认已改为 `127.0.0.1`；非 loopback 绑定无 token 会拒绝启动，`/mcp` 各方法已受 bearer token 保护，session ID 只用于关联；但尚无角色、租户、资源级授权、TLS 和客户端配额 | 基础未认证暴露风险已下降，但单一高权限 token 泄漏或共享后仍可调用完整控制面 | `flaghunter/interface/main.py`、`flaghunter/config/remote_access.py`、`flaghunter/mcp/server/mcp_transport_streamable_http.py` |
| F-05 | P0 | ✅ 已修：MCP metrics 曾以 task `done` 计算 success rate，不要求 verified proof（现分离 `completion_rate` 与 proof-backed `verified_solve_rate`，见 A-06） | 指标会高估成功，破坏优化决策 |
| F-06 | P0 | ✅ 已修：`.dockerignore` 曾未排除 `loot/`、`logs/`、`reports/`、`challenges/`、`conversations/` 等本地产物，镜像构建使用 `COPY . .`（现补全 denylist + guard 测试，见 A-10） | 本地证据、日志、题目产物可能进入镜像层或构建上下文 |
| F-07 | P1 | 部分修复：变更范围内的 Ruff/Black 已进入阻断式 `lint-changed` job；全树检查仍为 `continue-on-error` 的 advisory backlog | 新改文件可阻断格式/lint 回归，但未触及的遗留问题仍不会阻断合并 |
| F-08 | P1 | CI coverage 下限为 30%，且默认排除整个 interface 和 MCP server 关键区域 | 高风险控制面可能不受覆盖率指标约束 |
| F-09 | P1 | 部分修复：`import-linter` 已成为独立阻断门禁；`mypy`、`pyright`、依赖安全、密钥、SBOM 和容器扫描仍未形成统一阻断链 | 架构依赖方向已有自动保护，但类型和供应链风险仍主要依赖分散检查或人工判断 |
| F-10 | P1 | 🔨 部分修：代码内版本漂移已消除（APP_VERSION 从 pyproject 单源解析，MCP clientInfo/serverInfo 统一消费 APP_VERSION，见 B-06）；仍待处理 release tag 落后与 CHANGELOG 更新（发布流程侧） | 用户、协议和发布信息仍存在漂移 |
| F-11 | P1 | 依赖同时存在 `pyproject.toml`、`requirements.txt`、`requirements-local-tools.txt`，没有锁文件；Docker base 和 apt/pip 依赖未固定到可复现版本 | 构建结果随时间变化，回滚与漏洞定位困难 |
| F-12 | P1 | 多个 JSON/JSONL store 直接 append 或覆盖写，部分只有进程内锁，缺少统一原子写、跨进程锁和损坏恢复 | 并发、断电或磁盘异常可导致状态丢失/损坏 |
| F-13 | P1 | 事件队列在满载时会静默丢弃，缺少 drop 指标和回压策略 | trace/UI 与真实执行产生不可见偏差 |
| F-14 | P1 | 默认配置和环境变量面较大，静态发现约 167 个相关变量/常量名 | 配置冲突、无效开关、重启语义和文档漂移难管理 |
| F-15 | P2 | 核心源码与测试均存在超大模块，最大测试文件超过 7,000 行 | 变更影响面、审阅成本和并行协作冲突高 |
| F-16 | P2 | 时间戳同时使用 naive local time、naive UTC 和 timezone-aware UTC | 排序、跨时区、恢复和审计关联可能不一致 |
| F-17 | P2 | 两个源文件带 UTF-8 BOM，部分字符串触发 invalid escape SyntaxWarning | 编码和构建环境差异可能产生噪声或工具兼容问题 |
| F-18 | P2 | schema 引用很多，命名同时存在整数、`challenge.*`、`p2/p3/p4*` 和独立 state 版本 | schema 生命周期、兼容矩阵和迁移责任不清晰 |
| F-19 | P2 | Markdown 文档中的工具私有记忆引用已清理，但 Python 生产源码注释仍有 19 处、测试 docstring 仍有 1 处不可解析的 wiki-style `project_*` / `feedback_*` / `reference_*` 引用 | 设计理由无法从仓库独立追溯，源码仍显得依赖某个外部会话记忆；本轮因“只改文档”边界未修改代码 | `flaghunter/agents/pa_agent/`、`flaghunter/knowledge/`、`tests/unit/knowledge/test_rag_local_dense_gate.py` |

### 2.4 近期演进方向

近期提交主要集中在：

- 真实解题率 baseline 与 judge 可信度。
- 黑板 loop 的停止纪律、广度耗尽和无实质进展检测。
- 策略可达性和高价值 SQLi/Web 链路。
- 运行工具版本探测与 Windows 子进程清理。
- Web/MCP 大模块的分簇和 read model 收敛。

因此，旧文档中“尚未建立黑板、trace、claim、TaskDAG、baseline”等结论不能直接作为当前事实。当前优化必须以实时代码和最近评测证据为准。

### 2.5 近期实现进度静态复核

本节按“生产接线和验收目标是否成立”判断完成度，而不是直接采用提交标题中的完成标记。判定规则如下：

- 仅新增 contract、schema、Protocol、registry 或其他基础原语，记为“部分完成”。
- 生产入口已经消费，但只覆盖部分路径或只具备身份认证而没有授权，记为“基础能力完成，整体部分完成”。
- 工作树中的未提交改动只记为“草稿”，不进入稳定能力清单，也不作为发布依据。
- 只有所有目标入口接线、负面路径收口、资源清理可证明且达到该项验收目标，才记为“完成”。
- 本次未运行测试；下表是对当前文件、导入关系、工作流和 Git 状态的静态复核结论。

| 工作项 | 当前判定 | 已落地内容 | 尚未完成或需要特别验证的内容 |
|---|---|---|---|
| A-01 统一 lifecycle | 部分完成 | `flaghunter/domain/task_lifecycle.py` 已提供 canonical `TaskState`、Web/MCP/registry dialect 映射、终态集合和 transition service；`SUCCEEDED` 与中性 `COMPLETED` 已明确分离 | 生产 Web、MCP、task registry 等入口尚未导入并消费这些 API；当前 guard 不能替代从真实入口自动发现状态词表；“所有入口状态同义”尚未达到 |
| A-02 cancellation registry | 部分完成 | `flaghunter/domain/cancellation.py` 已提供线程安全 token、父子 scope、传播语义和 task-id registry | 已提交生产代码尚无消费者；token 未向 model、dispatcher、tool、runtime、worker、browser、subprocess 逐层传递；“取消确认后新增动作数为 0”尚未达到 |
| A-04 MCP 真取消 | 进行中，未验收 | 当前工作树存在未提交草稿，开始保存异步 `asyncio.Task` 句柄、触发 `Task.cancel()` 并调用 cancellation registry | 草稿不属于已提交能力；scope 在 task 真正启动前可能尚未建立；协程首次调度前取消时的 handle/scope 清理需验证；token 未传到底层动作边界；blocking `run_task` 没有同等真实取消句柄 |
| A-07 Web 远程控制面 | 基础认证完成，整体部分完成 | loopback 可保持本地模式；非 loopback 无 token 拒绝启动；`Authorization: Bearer` 和专用 token header 已接入 `/api/*` | 这是共享静态 token 身份认证，不是 RBAC；缺少 action/resource 授权、角色、会话管理、速率/并发配额、TLS 边界；query token 当前对所有 API 生效，必须限制为确实需要的 SSE 路由 |
| A-08 MCP network profile | 基础认证完成，整体部分完成 | 默认 host 已从全网卡改为 `127.0.0.1`；非 loopback fail-closed；POST/GET/DELETE `/mcp` 均执行 token gate；session ID 不再被当作身份 | 尚无角色、租户、scope、工具级授权、token 轮换/吊销、客户端配额和 TLS 部署闭环；不能将“有 bearer token”表述为“完整鉴权/授权已完成” |
| A-09 来源与请求防护 | 未完成 | 已识别为独立控制面工作项 | CORS 仍为 `*`，OPTIONS 直接放行；允许 header 未覆盖 `Authorization`/专用 token header；需要 Origin allowlist、修改类请求 CSRF/Origin 校验，并将 query token 严格限于 SSE |
| B-01 变更文件质量门禁 | 分阶段完成 | 改动的 `flaghunter/*.py` 已受阻断式 Ruff/Black 检查 | 全树遗留仍 advisory；需要明确逐步清零、例外期限和最终全树阻断条件 |
| B-02 架构门禁 | 已完成当前定义范围 | `lint-imports --config .importlinter` 已成为独立阻断 job | 后续新增架构边界时仍需同步契约和 source guards；该项不替代类型、依赖或供应链门禁 |

### 2.6 本次未确认的内容

由于本次不运行测试和基线，以下内容不能在本文中宣称已达标：

- 当前全量测试通过数量和耗时。
- 当前 T0/T1/T2/T3 的真实冷启动与暖启动解题率。
- 当前 lint、type-check、import-linter 的实际错误数。
- 当前 Docker/Kali 镜像是否可以完整构建和启动。
- 当前 Web/MCP 入口在真实并发和长时间运行下的稳定性。
- 当前依赖漏洞、镜像 CVE 和密钥扫描结果。

---

## 3. 优化北极星与量化目标

### 3.1 六个北极星

#### 3.1.1 事实可信度

系统显示的状态、结论和指标必须可由运行证据解释：

- `verified` 只能由 verifier/proof authority 产生。
- `success` 必须绑定 verified proof 或明确的非解题任务成功条件。
- `stopped/cancelled/timed_out` 必须意味着不再产生新工具调用和状态写入。
- UI、CLI、MCP、Web、报告和指标使用同一状态模型。

#### 3.1.2 真实解题能力

能力优化以分层 corpus 的真实解题率、失败分类和可达性为依据，而不是策略数量：

- T0 锚题必须长期稳定。
- T1 高频题型应成为发布门槛。
- T2 用于评估通用性和链组合能力。
- T3 用于发现能力边界，不应被伪装成已支持。

#### 3.1.3 运行可靠性

任何入口都应具备：

- 明确生命周期。
- 可取消、可超时、可清理。
- 可恢复、可审计、可重放。
- 依赖降级时给出真实状态，而不是无声回退。

#### 3.1.4 效率与成本

优化目标不是单纯减少 token 或提高并发，而是单位成功的总成本下降：

- 每个 verified solve 的 token、工具调用、墙钟时间和外部 API 成本可计算。
- 重复无效动作、工具轮换和无证据 LLM 探索持续下降。
- 并发只用于真正独立的任务，不放大重复工作和共享状态竞争。

#### 3.1.5 可维护性

新功能应进入稳定契约和组合根，而不是继续增加特殊分支：

- 依赖方向可自动检查。
- 模块职责、状态所有权和错误契约明确。
- 兼容 shim 有期限、有使用观测、有移除条件。
- 高风险文件停止无上限增长。

#### 3.1.6 可运营性

项目应能回答：

- 服务是否活着、是否准备好、依赖是否健康。
- 当前任务为什么慢、为什么停、为什么失败。
- 数据在哪里、保留多久、如何备份和恢复。
- 哪个版本、配置、模型、提示词和工具组合产生了结果。
- 发生异常时如何止损、降级、回滚和复盘。

### 3.2 核心指标体系

| 指标域 | 指标 | 定义 | 初始目标 | 成熟目标 |
|---|---|---|---:|---:|
| 可信度 | 假成功率 | 无 verified proof 却被标记为解题成功的比例 | 0 | 0 |
| 可信度 | 状态一致率 | 入口状态、任务状态、运行时状态、最终报告一致的任务比例 | 100% | 100% |
| 可信度 | 关键 trace 完整率 | 决策、模型调用、工具调用、状态转换、handoff、verification 均可关联的比例 | ≥95% | 100% |
| 控制 | 取消生效延迟 | 发出取消到不再产生新动作的时间 | ≤5 秒 | ≤2 秒 |
| 控制 | 取消后动作数 | 取消确认后产生的新工具调用数 | 0 | 0 |
| 能力 | 策略可达率 | 已注册且有 handler、precondition、信号和路由入口的策略比例 | 100% | 100% |
| 能力 | T0 冷启动解题率 | 无历史记忆条件下的锚题通过率 | 100% | 100% |
| 能力 | T1 冷启动解题率 | 高频能力题通过率 | ≥75% | ≥90% |
| 能力 | T2 冷启动解题率 | 组合型和迁移型题通过率 | ≥40% | ≥70% |
| 能力 | T3 诚实终止率 | 能力不足时给出真实边界且不伪成功的比例 | 100% | 100% |
| 效率 | 单次 verified solve 成本 | token、模型费用、工具时间和基础设施成本总和 | 建立基线 | 持续下降 |
| 效率 | 无实质进展动作率 | 未增加新证据、状态或可执行假设的动作比例 | <20% | <10% |
| 稳定性 | 运行时清理成功率 | 任务结束后无遗留浏览器、子进程、容器、临时凭据 | ≥99% | 100% |
| 稳定性 | 数据损坏率 | 无法解析或无法恢复的持久化记录比例 | 0 | 0 |
| 质量 | 阻断门禁通过率 | 合并分支通过全部必需质量检查的比例 | 100% | 100% |
| 质量 | 新增广义异常捕获 | 新代码中无分类、无上下文、无状态转换的 broad catch | 0 | 0 |
| 质量 | 架构契约违规 | import-linter 和 source guard 新违规数 | 0 | 0 |
| 运维 | 服务可用性 | 在声明支持的运行 profile 中可接受任务的时间比例 | 建立基线 | ≥99.5% |
| 运维 | 恢复时间目标 RTO | 从故障到恢复任务受理能力 | ≤30 分钟 | ≤10 分钟 |
| 运维 | 恢复点目标 RPO | 可接受的持久化数据丢失窗口 | ≤5 分钟 | 接近 0 |
| 文档 | 权威文档新鲜度 | 当前实现变化后在规定周期内完成同步的比例 | ≥95% | 100% |

### 3.3 指标使用纪律

- 指标必须绑定清晰语义和数据来源，不使用“done 就是 success”一类近似替代。
- 指标不得反向激励伪 proof、过度调用工具或隐藏失败。
- 真实解题率必须同时报告冷/暖、题层级、失败类型、预算和模型版本。
- 覆盖率只用于发现盲区，不作为代码质量的唯一代理。
- 所有百分比目标应在连续多轮稳定后再升级，不以单次结果宣布成熟。

---

## 4. 目标架构与必须保持的不变量

### 4.1 依赖方向

目标依赖方向保持：

Presentation → Application Services → Domain/Contracts → Ports；Adapters 实现 Ports；Composition Root 负责装配具体实现。

要求：

- Domain/Contracts 不导入运行时、工具执行器、UI、MCP、存储、浏览器、subprocess 或 worker pool。
- Application Services 只依赖 contracts 和 ports。
- Presentation 只消费 use case、read model 和稳定 DTO，不直接拼接领域状态。
- Adapters 不反向定义核心语义。
- `.importlinter` 与 source guards 必须成为 CI 阻断门禁。

### 4.2 中立公共命名

新公共 contract、port、application service 使用：

- challenge、task、run、agent、worker。
- claim、evidence、proof、artifact、receipt、trace。
- review、checkpoint、policy、strategy、read model。

历史 CTF、安全、利用链名称可保留在 legacy implementation、adapter、fixture、benchmark 和历史文档中。不得借优化之名全仓批量重命名。

### 4.3 Proof Authority

必须保持：

- verifier/proof authority 是 verified proof 的唯一生产者。
- 模型输出、工具结果、候选 flag、状态恢复、memory、handoff、crew receipt、replay、eval 和 UI selector 都不是 proof authority。
- 任何入口不得依据正则命中或模型自述直接升级为 verified。
- success、自动提交、停止其他 worker 和最终报告必须消费同一 proof 结果。

### 4.4 任务生命周期真相

当前已经有 `flaghunter/domain/task_lifecycle.py` 作为 canonical 状态契约，但各生产入口尚未统一接线。下列状态是最终应统一表达的业务语义，不代表当前每个入口都已经完整支持：

统一生命周期至少应区分：

- queued：已受理但未开始。
- running：实际执行资源已启动。
- cancelling：已请求取消，正在传播和清理。
- cancelled：所有执行单元已确认停止。
- timed_out：预算或时限触发并完成清理。
- blocked：权限、配置、依赖或策略门控阻止执行。
- failed：系统错误导致未按预期完成。
- stopped：按策略诚实终止但未失败。
- succeeded：非解题任务完成，或解题任务已获得 verified proof。

禁止：

- 先写终态，再让后台继续执行。
- 将 `done` 同时表示“循环结束”和“任务成功”。
- 仅改变 UI 状态而不传播 cancellation token。
- 清理失败后仍报告 cancelled/succeeded。

### 4.5 状态所有权

每类状态必须有唯一 owner：

| 状态 | 建议 owner | 其他模块角色 |
|---|---|---|
| Task lifecycle | Application task service | Presentation 只读/发命令 |
| Claim/Evidence | Domain + application services | Adapter 持久化 |
| Verified proof | Proof authority | 所有入口只消费 |
| Tool execution | Tool runner/executor | Strategy 发请求 |
| Runtime resources | Runtime adapter | Agent 不直接管理具体进程 |
| Budget | Budget policy/service | LLM、tools、crew 上报消耗 |
| Checkpoint | State/checkpoint port | UI 不直接写文件 |
| Read model | Projection service | TUI/Web/MCP 共用 |

### 4.6 事件与 trace

- 每个 task、run、step、tool call、receipt、claim、evidence、proof、handoff 都有稳定 ID。
- 事件必须带 schema version、UTC 时间、来源、关联 ID 和序号。
- 关键事件不可静默丢弃；发生队列丢弃必须计数并告警。
- trace 是旁路事实，不应成为业务状态的唯一存储。
- replay 必须明确“重放观测”与“重新执行外部动作”的区别。

### 4.7 配置与版本真相源

- 项目版本只由一个构建元数据源定义，其他位置运行时读取或发布时生成。
- 配置只由一个 typed settings schema 定义，环境变量、CLI、Web、MCP 是输入适配器。
- 每个配置项必须有类型、默认值、敏感级别、是否热更新、作用域、废弃版本和验证规则。
- 依赖只保留一个声明源和一个可复现锁定结果。

### 4.8 兼容策略

- 兼容 shim 必须记录 owner、调用量、引入版本、移除条件和最晚移除版本。
- 兼容路径不得获得新功能，只接受必要修复。
- 当调用量归零且迁移窗口结束，应删除 shim 和对应 source guard 豁免。
- 不允许永久保留“临时双写、双读、双路由”。

---

## 5. 优先级模型

### 5.1 优先级定义

| 优先级 | 定义 | 典型范围 |
|---|---|---|
| P0 | 会造成假成功、失控执行、越权控制、敏感数据泄露或不可可信恢复 | proof、取消、远程入口、构建上下文 |
| P1 | 会持续制造回归、数据损坏、不可复现、架构漂移或重大运维风险 | CI 门禁、持久化、依赖、schema、配置 |
| P2 | 明显限制解题率、效率、维护性和跨平台能力 | 策略可达性、模块拆分、错误模型、运行时一致性 |
| P3 | 提升成本、体验、观测和长期扩展能力 | 缓存、性能、UI、插件、生态 |
| P4 | 探索性和低频优化 | 新型策略、实验性 Agent 协议、非关键集成 |

### 5.2 排序评分

每个候选优化项按以下因素评估：

- Impact：对可信度、解题率、稳定性或安全的影响。
- Reach：影响多少入口、任务、运行时或用户。
- Evidence：问题是否由运行、流量、配置或当前代码证实。
- Recurrence：问题是否重复出现或造成长期维护负担。
- Effort：实现、迁移、验证和回滚成本。
- Reversibility：能否小步上线和快速回退。

推荐排序分数为 `(Impact × Reach × Evidence × Recurrence) / Effort`，但 P0 不因工作量大而自动降级。

### 5.3 选择优化切片的规则

- 优先一条可端到端闭环的最窄路径。
- 一次只改变一个核心变量。
- 先修状态、契约和可达性，再增加新能力。
- 先做可逆的 guard、adapter 和 projection，再切换默认路径。
- 先建立观测，再进行高风险迁移。
- 对高 churn 文件设置“禁止继续无界增长”的临时门槛。

---

## 6. 各功能域优化说明

### 6.1 入口、Session 与 Composition Root

**功能定位**

统一 TUI、CLI、Web、MCP 和子 Agent 的初始化过程，装配 LLM、runtime、tools、RAG、memory、metrics、audit 和 workspace，并确保同一配置产生同一行为。

**当前基础**

- `AgentSession` 已承担主要装配门面。
- `session/initializer.py` 负责构造主要组件。
- Web CTF dispatcher 复用 session runtime，但仍有独立生命周期。
- 多入口已经开始共享 control contract 和 read model。

**需要优化**

1. 建立正式 `TaskIngressRequest/Receipt` 到 application service 的唯一入口，presentation 不直接创建后台线程或全局任务对象。
2. Composition Root 显式声明每个 profile 的组件图，禁止入口层临时 import 并拼装具体 adapter。
3. 将启动检查分成配置有效性、模型可用性、工具可用性、runtime 可用性和数据目录可写性。
4. 明确 Web CTF、普通 Agent、Crew 和 MCP task 的生命周期差异，但统一任务状态、取消、trace 和 proof 消费。
5. 对初始化部分失败建立 typed degraded status，避免“初始化 warning 后继续，但功能实际不可用”。
6. 移除重复 settings 解析和运行时覆盖逻辑，所有覆盖通过 typed config merge 完成。

**质量检测**

- 入口装配依赖图检查。
- 同一输入在各入口的 contract parity 检查。
- 每个 profile 的组件清单、启动状态和降级原因对比。
- 禁止 presentation 导入具体 storage/tool/runtime 实现的 source guard。
- 初始化资源泄漏、重复初始化和 shutdown 顺序检查。

**预期效果**

- 各入口行为一致，修一次即可覆盖所有入口。
- 初始化故障可定位，不再通过大量 broad catch 隐藏。
- 新增入口只实现 adapter，不复制核心流程。

### 6.2 Agent Core Loop 与计划执行

**功能定位**

负责思考、工具调用、结果回流、计划更新、状态转换、停止和总结，是普通 Agent、Crew worker 和部分 MCP 任务的公共执行内核。

**当前基础**

- `BaseAgent` 已有明确状态机和共享 loop。
- 支持自动计划、并发工具执行、replan、summarization、metrics 和 session 保存。
- 已有 max iterations、memory budget 和 finish 工具。

**需要优化**

1. 将 300 行以上主循环拆成显式阶段对象或 application use cases，保持单一状态 owner。
2. 把模型调用、工具调度、状态转换、checkpoint 和终止裁决变为可关联 trace span。
3. 使用结构化 `LoopOutcome`，禁止以字符串和隐式属性判断结束原因。
4. 统一 cancellation token，所有 await、并发任务和 runtime call 都消费同一取消信号。
5. 将预算细分为 task、phase、step、model、tool 和 wall-clock，并记录消耗原因。
6. 总结阶段不得覆盖原始 evidence，不得制造 verified 结论。
7. 对模型无工具调用、重复输出、无实质进展和解析失败建立独立错误分类。

**质量检测**

- 状态机合法转换和终态唯一性检查。
- cancellation、timeout、异常和正常完成的资源清理检查。
- loop 每阶段 trace 覆盖率。
- 重复动作、空输出、无进展动作比例。
- 单次迭代 token、耗时和工具 fan-out 分布。

**预期效果**

- Agent loop 更易维护和恢复。
- 停止原因可解释，成本可归因。
- 普通 Agent 与 CTF dispatcher 可以共享控制面语义，而不强行合并执行引擎。

### 6.3 Challenge Dispatcher、Blackboard 与 Coordinator

**功能定位**

将 challenge 输入转换为 observations、hypotheses、strategies、actions、receipts 和最终 proof；Blackboard 提供共享事实投影，Coordinator 负责顶层编排。

**当前基础**

- Blackboard loop 已成为默认路径。
- 已有停止纪律、广度耗尽、spinning 检测和恢复决策。
- `CTFTaskDispatcher`、`CTFCoordinator`、`CTFState` 已承载复杂流程。
- TaskDAG、SolveNode、readback 和 crew bridge 契约已大量落地。

**需要优化**

1. 明确 dispatcher、coordinator、blackboard brain、recovery controller 各自只负责一个裁决层次。
2. Blackboard 必须是 read model，不允许 presentation 或 worker 直接写入“事实”。
3. 将 task graph 的执行状态与 legacy chain 状态建立单向投影，避免双向同步。
4. 冻结超大类继续增长：新流程优先落入 application service、policy 或 adapter。
5. 将 branch decision、reason code、input evidence IDs、selected strategy、rejected alternatives 全部结构化。
6. Recovery 不得仅基于字符串结果，应消费 typed outcome 和 progress delta。
7. 对 LLM brain 与 deterministic controller 的权力边界做显式 policy：模型提出，控制器裁决。

**质量检测**

- strategy 注册、hypothesis 输出、chain handler 和 capability 的全链可达性检查。
- Blackboard projection 与底层 claim/evidence store 的一致性检查。
- 每个决策是否具有输入 evidence、reason code 和输出 action。
- no-progress、breadth exhaustion、budget exhaustion 的终止一致性。
- legacy 与新 task graph 路径的终态语义对比。

**预期效果**

- 降低 dispatcher/coordinator 继续膨胀的速度。
- 失败能回到明确阶段，不再横向盲目扩展。
- TaskDAG 不再只是展示契约，而能逐步成为真实控制平面。

### 6.4 Hypothesis、Strategy 与 Capability 路由

**功能定位**

- Hypothesis：根据当前 evidence 形成可证伪候选。
- Strategy：描述前提、最小实验、成功/失败信号和升级条件。
- Capability：为一个抽象能力选择实际工具实现，并支持降级。

**当前基础**

- 32 个 StrategyDefinition。
- 默认 13 个 capability primitives。
- Observation Floor、Devil's Advocate、memory adjustment 和降级路由已存在。

**需要优化**

1. 每个策略必须绑定稳定 strategy ID、版本、owner、适用 evidence、成本模型和弃用状态。
2. 每个策略的 precondition 必须可解释，不能长期保留 `True` 作为宽泛入口而无证据门槛。
3. capability cost 应综合墙钟时间、外部费用、噪声、权限风险和成功概率，不只使用静态整数。
4. 工具缺失、工具不可用、目标不适用、payload 失败和预算不足必须分开记录。
5. Strategy Memory 只能调整优先级，不能绕过 observation floor 或 proof authority。
6. 对 legacy 策略设置迁移/退役条件，避免同一能力长期双路由。
7. 建立 strategy outcome dataset，按题型、运行时、模型、冷暖状态计算真实贡献。

**质量检测**

- 100% 策略可达性与 handler 覆盖。
- precondition 命中精度和误触发率。
- strategy 选择后实际 progress 率。
- capability 降级成功率、安装建议准确率和工具探测缓存命中率。
- 新策略对 baseline 的增量收益与回归影响。

**预期效果**

- 从“策略数量增长”转向“策略真实贡献增长”。
- 降低昂贵工具和 LLM fallback 的无效调用。
- 能力缺口可被明确归类为路由、工具、策略或验证问题。

### 6.5 Recon、HTTP 与浏览器自动化

**功能定位**

发现页面、表单、链接、端点、cookie、技术栈、附件和目标结构，为后续 hypothesis 提供运行证据。

**当前基础**

- Browser、http_request、httpx_probe、recon_bundle、katana、gau、dirscan、subfinder、vhost、param discovery 等工具。
- LocalRuntime 使用 Playwright，Docker/SSH 具备文本化 fallback。
- cookie 自动注入和 browser diagnostics 已存在。

**需要优化**

1. 统一 HTTP request/response receipt：method、URL、status、headers 摘要、body artifact、redirect、timing、TLS 和 error class。
2. 浏览器会话必须按 task/workspace 隔离 cookie、storage、proxy 和下载目录。
3. 建立 canonical URL、origin、scope 和 redirect 校验，处理 DNS 变化、IPv6、IDN 和相对 URL。
4. 将 browser fallback 的能力差异显式暴露，避免 Docker 文本抓取被当成完整浏览器。
5. 对附件、下载、截图和 HTML 建立 artifact manifest、hash、大小限制和来源 trace。
6. Recon 采用增量差异，不重复抓取未变化资源。
7. 对网络错误建立 DNS、connect、TLS、timeout、HTTP、parse 和 policy 分类。

**质量检测**

- 三种 runtime 的功能一致性矩阵。
- redirect、cookie、编码、压缩、二进制、超大响应和 JS 渲染处理能力。
- task 间 cookie/storage 泄漏检查。
- 每次 recon 产生的新 evidence 比例和重复请求率。
- scope 校验在重定向和域名解析后的持续生效情况。

**预期效果**

- Hypothesis 输入更稳定，减少错误路由。
- 浏览器和 HTTP 行为可重放、可审计。
- 运行时降级不再隐式损失关键能力。

### 6.6 Web 策略能力

**功能定位**

覆盖当前仓库中的 SQLi、CMDi、SSRF、XSS、SSTI、文件读取、源码泄露、反序列化、XXE、JWT、GraphQL、NoSQL、IDOR、重定向和业务逻辑等策略族。

**当前基础**

- SQLi 已包含 auth bypass、UNION、generic parameter、blind、second-order 等路径。
- 已有 source leak → runtime primitive、PHP object injection、file read、hash reconstruction 等组合链。
- SSTI 已有 legacy 与 detect/identify/exploit 分层路径。
- GraphQL、NoSQL、JWT 和多类 Web 探测已注册。

**需要优化**

1. 按“识别 → 最小确认 → 利用 → 取证 → 验证”统一策略阶段，而不是每个策略独立定义流程形状。
2. 把 payload 生成、request execution、oracle analysis、extraction 和 proof submission 分离。
3. 将 WAF/过滤器特征作为 evidence，不把某个题目的 payload 固化为通用首选。
4. 所有提取型策略建立预算估算、进度 checkpoint 和可恢复位置。
5. 对源码驱动链建立 source artifact hash 与 runtime target 的关联，避免陈旧源码解释当前行为。
6. 对 false positive 设置类型化否证信号，及时降低对应 hypothesis。
7. 通过 baseline failure clusters 决定新增策略，不按漏洞类别目录机械补齐。

**质量检测**

- 按策略族统计识别准确率、最小确认成功率、最终 verified solve 贡献率。
- 同一策略在不同 runtime、模型和冷暖状态下的稳定性。
- false positive、无效 payload、重复请求和平均提取成本。
- 识别成功但利用失败的阶段分布。

**预期效果**

- 将题目特化逻辑逐步收敛为可复用阶段能力。
- 新增策略更容易组合、恢复和度量。
- 降低“命中线索但走不到最终 proof”的损耗。

### 6.7 Crypto、Reverse、Pwn 与 Misc

**功能定位**

处理非 Web challenge：编码链、密码学构造、二进制分析、符号执行、pwn 运行、文件取证、隐写和附件恢复。

**当前基础**

- `crypto_solve`、M2 crypto tools。
- `binary`、`radare2`、`angr_solve`、M2 reverse tools。
- `pwn`、pwntools wrapper、远程文件传输。
- artifact forensics、zip/sqlite/wal/pcap 等线索分析。

**需要优化**

1. 为每个领域建立标准 artifact input/output contract，而不是依赖自由文本。
2. 原始文件、解包文件、修复文件、反编译结果和 solver 产物必须分目录并带 hash/provenance。
3. 本地、Docker、SSH 的工具版本和 loader/libc/runtime 信息必须进入 receipt。
4. 长时间 solver 支持 checkpoint、阶段进度和资源配额。
5. 避免将第三方工具 stdout 直接当 proof；必须经过提取和 verifier。
6. 对可选重依赖建立明确 profile，不让核心安装隐式拉入大型包。
7. 将领域能力纳入 T3 corpus 的诊断指标，不以“工具存在”代表自动解题能力。

**质量检测**

- artifact hash、来源、变换链和输出可重现性。
- 工具版本、架构、操作系统、loader/libc 兼容矩阵。
- 超时、内存、临时文件和远程目录清理。
- 候选结果到 verified proof 的转换率。

**预期效果**

- 非 Web 能力从“工具包装”升级为可追溯工作流。
- 避免环境差异导致不可复现。
- 为后续扩展 corpus 和自动化策略提供统一底座。

### 6.8 Claim、Evidence、Verifier 与 Proof

**功能定位**

管理候选事实、证据、验证记录和最终证明，决定什么可以被系统当作可信结论。

**当前基础**

- 中立 claim/evidence/proof contracts 已存在。
- CTFVerifier 具备 candidate/runtime/verified/rejected 分级。
- proof authority port 与 adapters 已建立。
- board read model 和 claim review service 已落地。

**需要优化**

1. 将 flag-centric 验证规则推广为通用 claim review，但保持不同 claim kind 的独立 verifier policy。
2. 所有 evidence 引用 immutable artifact/receipt/trace ID，不复制易漂移的全文。
3. 明确 candidate、observed、runtime-grounded、verified、rejected、retracted 的状态转换。
4. verification record 必须包含 verifier identity/version、输入 evidence、policy version、结论、原因和时间。
5. UI 和报告只通过 read model 展示 proof，不直接扫描文本决定 badge。
6. 处理 proof 冲突、撤回、过期和 verifier 不可用场景。
7. 自动提交结果必须回写平台响应 evidence，并区分平台确认与本地验证。

**质量检测**

- 非 proof-authority 写 verified 的 source guard。
- 每个 verified proof 的 evidence 和 verification record 完整性。
- rejected/retracted 后下游 read model 是否及时更新。
- verifier false positive/false negative 与超时率。
- 不同入口对同一 proof 的展示一致性。

**预期效果**

- 假成功率稳定为 0。
- 结果可审计、可撤回、可解释。
- 指标、报告和停止纪律建立在同一可信事实线上。

### 6.9 Recovery、Budget、Stop 与 Cancellation

**功能定位**

在失败、无进展、超时、预算耗尽、工具缺失和人工停止时决定下一步，并确保执行真实停止和资源清理。

**当前基础**

- RecoveryController 已有 explore/switch/stop/wait 等动作。
- 黑板 loop 已有无实质进展、广度耗尽和停止 sanction。
- 运行时和工具普遍接受 timeout。
- 已新增 `CancellationToken`、父子 `CancellationScope` 和 `CancellationRegistry` 领域原语，但已提交生产链路尚未消费，不能据此宣称真实取消已完成。

**需要优化**

1. 引入统一 cancellation scope，从 task 向 step、model、tool、runtime、worker、browser 和 subprocess 传播。
2. 区分 request cancellation、acknowledged、draining、cleaned 和 terminal cancelled。
3. 超时必须触发子进程树、浏览器 context、容器 exec、远程命令和临时文件清理。
4. Web 和 MCP 不得仅写状态；必须持有任务句柄并等待清理确认。
5. Recovery reason 使用稳定 taxonomy，不用自由文本控制逻辑。
6. Budget service 统一 token、费用、tool time、wall time、并发和外部请求配额。
7. 失败重试必须满足幂等性或具备 operation key，防止重复提交和重复副作用。

**质量检测**

- 取消后新增工具调用数必须为 0。
- 各层取消确认和清理耗时。
- 超时后遗留进程、线程、容器、socket、临时文件数量。
- retry 是否重复执行非幂等动作。
- stop reason 与实际最后 evidence/action 的一致性。

**预期效果**

- 操作者对停止按钮和取消命令有真实控制力。
- 避免后台任务继续消耗 token、执行工具或污染状态。
- 恢复和重试从“再跑一次”升级为可控状态机。

### 6.10 Tool Registry、Executor、Guard 与 Receipt

**功能定位**

发现和注册工具，执行参数校验、scope、cookie、stealth、timeout、flag scanning、receipt、provenance 和错误归类。

**当前基础**

- 41 个静态注册工具。
- ToolExecutor 已有 M4 scope check、cookie 注入、stealth、flag scanning、receipt sink 和 provenance。
- ToolGuard 支持可用性与版本探测。

**需要优化**

1. 工具输入输出使用版本化 schema，禁止核心流程依赖任意字符串解析。
2. 工具错误统一为 unavailable、invalid_input、policy_blocked、timeout、cancelled、execution_error、parse_error、partial_result。
3. scope 校验不仅在执行前做，还要覆盖 redirect、解析后 IP、子目标和工具内部派生目标。
4. 对 terminal 类高权限工具建立 permission policy 和审计级别。
5. receipt 包含命令摘要、runtime、tool version、duration、exit code、artifact refs、redaction 状态和 trace ID。
6. flag scanning 只生成 candidate claim，不直接构成 success。
7. 安装建议与自动安装分离，默认不允许任务静默改变运行环境。
8. 缓存只缓存可证明幂等的工具结果，并绑定输入、环境和版本 hash。

**质量检测**

- 所有工具 schema 完整率和 receipt 产出率。
- scope guard 覆盖率、误拦截率和漏拦截率。
- 工具 timeout/cancel 语义一致性。
- 版本探测耗时、缓存命中率和死锁率。
- 敏感参数/输出脱敏完整性。

**预期效果**

- 工具成为稳定 adapter，而不是自由文本副作用源。
- 失败可分类、可恢复、可统计。
- 调用链可完整解释到 proof。

### 6.11 Local、Docker 与 SSH Runtime

**功能定位**

为命令、浏览器、代理和文件传输提供可替换执行环境。

**当前基础**

- Runtime 抽象定义 start、stop、execute_command、browser_action、proxy_action、status。
- LocalRuntime 具备 Playwright 和浏览器 fallback。
- DockerRuntime 支持容器、VPN 和文件传输。
- SSHRuntime 支持 key/password/askpass 和远程执行。

**需要优化**

1. 建立 runtime capability descriptor，明确 browser、proxy、PTY、file transfer、privilege、network namespace 和 cancellation 支持。
2. 统一 CommandResult：stdout/stderr/exit/timeout/cancelled/truncated/artifacts/runtime metadata。
3. 禁止上层根据 runtime 类型写特殊分支，改为能力查询和 ports。
4. Local subprocess 统一进程树管理，Windows Job Object 与 Unix process group 语义对齐。
5. Docker 容器设置资源限制、只读文件系统、最小 capability、网络策略和生命周期标签。
6. SSH host key 验证、连接复用、远程临时目录、凭据文件权限和清理必须显式治理。
7. 运行时 status 区分 alive、ready、degraded 和 unavailable。

**质量检测**

- runtime contract parity 矩阵。
- 进程树和资源清理检查。
- 网络、文件、浏览器和 timeout 行为对比。
- 容器/SSH 断连、重连和部分失败恢复。
- 权限和敏感文件留存检查。

**预期效果**

- 同一策略可在不同运行环境下得到可预测行为。
- 环境降级透明可见。
- 长任务和取消操作更加可靠。

### 6.12 Memory、RAG、Knowledge 与 ShadowGraph

**功能定位**

保存对话、策略经验、事实、文档索引和关系图，帮助检索已有知识并减少重复探索。

**当前基础**

- ConversationMemory 支持 token 预算和摘要。
- Hybrid RAG 使用 dense + BM25 + RRF。
- StrategyMemory 支持 fingerprint、成功率、mute/deprecated 和负反馈。
- ShadowGraph 从 notes 派生关系和路径。

**需要优化**

1. 区分会话记忆、策略记忆、知识文档、运行事实和 proof，禁止互相越权。
2. 所有 memory entry 带来源、版本、适用条件、置信度、成功/失败统计和过期策略。
3. 摘要必须保留 evidence refs、open questions、失败动作和预算状态，不能只保留叙述。
4. 检索结果必须记录 query、候选、分数、过滤原因、最终引用和实际贡献。
5. 负反馈应降低错误路径优先级，但不能永久屏蔽新证据支持的路径。
6. 索引增量更新、schema migration、embedding model 变化和重建过程需要显式版本。
7. ShadowGraph 洞察是候选，不是 verified 事实。

**质量检测**

- retrieval hit、citation、useful contribution 和 solve uplift 分开统计。
- cold/warm baseline 对比，防止数据泄漏。
- 错误记忆的降级、撤回和传播检查。
- embedding/model/index 版本一致性。
- 索引损坏恢复和重建耗时。

**预期效果**

- Memory 真正降低重复成本，而不是放大陈旧错误。
- RAG 效果可归因，不再只看命中数量。
- 冷暖评测可信。

### 6.13 Crew、Worker Pool 与 Swarm

**功能定位**

并行处理独立子任务，通过 worker 隔离、handoff、receipt、共享 read model 和调度策略协作。

**当前基础**

- CrewOrchestrator、WorkerPool、typed worker、独立 LocalRuntime。
- Task dependency 和 ShadowGraph insight。
- M5 pheromone、consensus 和 shared blackboard。
- CTF crew bridge 和 TaskDAG 相关契约已存在。

**需要优化**

1. 只有能证明独立、资源足够且预期信息增益高的任务才并行。
2. worker 通过 TaskBrief 接收任务，通过 Receipt 返回，不共享可变内部对象。
3. 共享面只接受 claim/evidence/proof/read model，禁止 worker 直接升级 verified。
4. 并发预算覆盖 token、工具、目标 host、browser、runtime 和总墙钟时间。
5. 取消必须级联到全部 worker，并等待清理回执。
6. 重复任务检测和结果去重必须在 orchestrator 完成。
7. pheromone/consensus 只能影响推荐优先级，不成为事实权威。

**质量检测**

- Crew 相比单体的 solve uplift、成本增量和时间收益。
- 重复工具调用率、冲突写入率和无用 worker 比例。
- worker isolation、scope 和凭据隔离。
- handoff/receipt 完整率及取消传播延迟。

**预期效果**

- 并发带来真实收益而非成本放大。
- 单体和 Crew 使用同一事实纪律。
- worker 故障不会污染其他任务。

### 6.14 MCP Client 与 MCP Server

**功能定位**

- Client：连接外部 MCP server，包装其工具并处理多种传输。
- Server：把 FlagHunter 的任务、工具、记忆、日志和指标暴露给 MCP 客户端。

**当前基础**

- 支持 stdio、SSE、FIFO、WebSocket、Streamable HTTP 等路径。
- 每个任务创建新 Agent/Runtime，降低状态污染。
- server 提供异步任务、取消、工具管理、memory、logs 和 metrics。
- 大工具集可通过 RAG optimizer 收敛。
- MCP SSE 默认绑定已收回 `127.0.0.1`；非 loopback 绑定已实施 bearer token fail-closed，且 session ID 只承担会话关联。
- 当前安全能力属于基础身份认证，不包含角色、租户、工具、scope 或资源级授权。

**需要优化**

1. 网络传输默认绑定 loopback；远程模式必须显式开启并配置身份认证、授权、TLS 和 origin policy。
2. session ID 只用于会话关联，不能替代身份认证。
3. 工具按权限分组，远程客户端默认不能启用/禁用全局工具或修改高敏设置。
4. async task 必须保存 task handle，取消真实传播到 dispatcher、agent 和 runtime。
5. 为每个 client/server 建立 trust level、允许工具、scope 和资源配额。
6. MCP tool output 使用稳定结构化 envelope，文本仅作为展示。
7. protocol/client version 从统一版本源读取，并记录 capability negotiation。
8. 外部 MCP server 是不可信 adapter，返回内容不得作为指令或 proof。

**质量检测**

- 未认证、越权、跨 session、重放和并发请求检查。
- stdio/SSE/HTTP/WebSocket 行为一致性。
- message ID、session queue、取消和断线清理。
- MCP tool schema compatibility 和版本协商。
- 外部 server 超时、恶意输出和工具数膨胀时的稳定性。

**预期效果**

- MCP 从开发集成接口升级为可控远程控制面。
- 任务取消、权限和指标语义与其他入口一致。
- 外部工具不会破坏核心事实边界。

### 6.15 TUI、CLI 与 Web Console

**功能定位**

向操作者展示任务、计划、trace、proof、memory、runtime、成本和失败原因，并提供控制命令。

**当前基础**

- TUI 功能丰富，支持 rewind、fork、crew、CTF、诊断和各 CPA 模块面板。
- CLI 支持 headless、playbook、MCP、memory 和多种运行 profile。
- Web Console 提供 task、trace、dashboard、knowledge、memory、attachment 和 SSE。

**需要优化**

1. 三个 presentation 入口消费同一 read model 和 command service。
2. 清晰区分 candidate、runtime evidence、verified proof、stopped、failed 和 cancelled。
3. 所有按钮/命令显示真实能力：无法强制取消时不得显示已停止。
4. Web Console 的 settings、task execution、attachment、knowledge 和 MCP server 管理建立权限分层。
5. SSE/event queue 增加序号、重连游标、丢失检测和 backpressure。
6. UI 不直接推导事实，不复制复杂业务判断。
7. 长输出采用 artifact 引用、摘要和按需加载，避免内存及浏览器压力。
8. 增加可访问性、键盘操作、错误可读性和国际化/编码治理。

**质量检测**

- read model parity 和命令结果 parity。
- 状态更新顺序、SSE 重连和事件缺失检查。
- 大任务列表、长 trace、大附件和慢客户端压力。
- 设置读写的字段级权限、脱敏和重启提示。
- Windows/Linux 终端编码和宽字符显示。

**预期效果**

- 操作者在任意入口看到相同事实。
- 控制动作可预测、可审计。
- presentation 不再成为第二套业务逻辑。

### 6.16 Notes、Report、Audit 与 Artifact

**功能定位**

保存发现、输出报告、记录操作审计、管理附件和运行产物。

**当前基础**

- notes 工具有异步锁和 schema 检查。
- M3 支持报告生成。
- M4 支持 scope、RoE、approval、audit chain 和数据脱敏。
- artifact registry、session ledger、checkpoint store 已存在。

**需要优化**

1. Notes 只保存可追溯 finding/observation，不承担 proof authority。
2. Report 只从 read model、claim、evidence、proof 和 artifact manifest 生成。
3. 所有敏感字段按数据分类和输出渠道执行统一 redaction policy。
4. Audit log 与 session trace 分开：前者记录安全/控制行为，后者记录执行因果链。
5. 文件写入使用原子替换、校验和、跨进程协调和损坏恢复。
6. artifact 建立大小、类型、来源、hash、保留期、访问级别和删除状态。
7. 报告生成失败不得影响任务终态，但必须形成独立可见失败。

**质量检测**

- proof 到报告的引用完整性。
- 敏感数据在日志、报告、metrics、trace 和 UI 中的泄漏检查。
- audit chain 完整性和时序一致性。
- 存储写入的原子性、并发性和损坏恢复。
- artifact retention、清理和磁盘配额。

**预期效果**

- 输出可审计且不会夸大结论。
- 本地状态更耐并发和崩溃。
- 证据生命周期可管理。

### 6.17 LLM、Provider Failover 与 Context Management

**功能定位**

封装模型调用、provider 路由、故障切换、预算、token 管理、提示词和上下文摘要。

**当前基础**

- LiteLLM 多 provider。
- M1 health、failover、recovery 和 cost tracker。
- ConversationMemory 自动摘要。
- Anthropic prefill sanitization 和 drop_params 兼容处理。

**需要优化**

1. 每次模型调用记录 model/provider、prompt version、sampling、token、latency、retry、error class 和 response hash。
2. 提示词使用版本化 registry，不在多个模块复制长字符串。
3. 规划、工具解析、总结、分类等 task hint 对应明确模型层级和 fallback policy。
4. Failover 后必须记录语义变化风险，不能只记录 provider 健康。
5. Logic error、context overflow、rate limit、network 和 provider outage 分开处理。
6. Context summarization 保留结构化 state refs，不让摘要覆盖原始事实。
7. 配额按照任务和用户/入口隔离，防止一个任务耗尽全局预算。
8. 模型输出一律作为 untrusted proposal，经过 parser、policy 和 verifier。

**质量检测**

- 不同模型的 solve rate、成本、延迟和假成功率矩阵。
- fallback 前后行为差异和重试放大率。
- prompt version 对 baseline 的影响。
- context compression 前后关键信息保留率。
- 预算超限后是否真实停止。

**预期效果**

- 模型选择从经验判断变为可度量路由。
- 降低 provider 波动导致的不可解释行为。
- 上下文和费用可控。

### 6.18 Eval、Replay、Baseline 与 Harness

**功能定位**

用可重复的 corpus、runner、judge、record/replay 和报告衡量真实能力、成本和回归。

**当前基础**

- 16 题 T0–T3 corpus。
- 进程级 runner、judge、cold/warm、scorecard。
- record/replay fixtures 和 profile/model matrix。
- session ledger、checkpoint、artifact 和 control receipt harness。

**需要优化**

1. corpus entry 固定题目版本、环境 hash、预期 proof policy、预算和允许工具。
2. judge 只消费 proof/receipt/trace，不从任意 stdout 猜测成功。
3. 报告必须同时给出 pass、honest stop、false success、infra failure 和 timeout。
4. 冷暖评测隔离 memory、cache、workspace、provider cache 和工具输出。
5. 模型、prompt、配置、依赖、runtime 和 commit 全部进入 run manifest。
6. baseline 分为 PR 快速层、nightly 分层层和 release 全量层。
7. 对不稳定题建立 quarantine 和 owner，不能静默从统计中删除。
8. failure taxonomy 直接生成优化 backlog，避免手工挑选结果。

**质量检测**

- run manifest 完整率和可重放率。
- judge 一致性、false positive 和 infra error 分类准确率。
- 冷暖隔离和跨运行污染检查。
- 同一 commit 多轮方差。
- 每个优化项对题层级和失败类型的实际增量。

**预期效果**

- 优化优先级由真实数据驱动。
- 模型、策略和工具变化可比较。
- 不再用单个成功案例替代系统能力证明。

---

## 7. 代码质量检测与门禁体系

### 7.1 当前质量门禁评价

| 检查项 | 当前状态 | 主要问题 | 建议目标 |
|---|---|---|---|
| Python 版本矩阵 | CI 覆盖 3.10–3.12 | Docker base 使用 3.14，支持矩阵不一致 | 统一声明、CI、Docker 和发布矩阵 |
| Ruff | 变更文件已阻断；全树为 advisory | 遗留全树仍 `continue-on-error`，规则集较基础 | 保持 changed-files 零回归并分阶段清零，最终全树阻断 |
| Black | 变更文件已阻断；全树为 advisory | 未修改的遗留文件仍不阻断 | 保持修改范围格式一致并规划最终全树阻断 |
| isort | 单独配置，Ruff 也启用 I | 两个 owner 可能重复 | 明确唯一 import format owner |
| mypy | 已列入 dev 依赖 | 未进入 CI，`ignore_missing_imports=true` | 核心层分阶段 strict |
| pyright | basic 配置 | 未进入统一门禁 | 作为 IDE/辅助检查或明确第二门禁职责 |
| import-linter | 已有较完整契约并进入独立阻断 job | 新边界仍需同步契约和 source guard | 保持全部 contract 通过，架构变化必须同步门禁 |
| Coverage | CI 下限 30% | 排除 interface/MCP 高风险区 | 分层阈值 + changed-code threshold |
| Security tests | CI 有 security 目录 | 不等于 SAST/依赖/密钥/镜像扫描 | 补完整供应链检查 |
| Pre-commit | 未配置 | 本地反馈晚 | 增加快速一致性门禁 |
| 复杂度/大小 | 无统一自动门槛 | 超大函数和类持续增长 | 对新增和高风险文件设增长预算 |
| Dead code | 无固定门禁 | 依赖人工审计 | 引入候选报告和人工确认流程 |
| Dependency audit | Dependabot 已有 | 无 lock、无合并前漏洞门禁 | 锁定 + audit + SBOM |
| Container scan | Docker CI 构建发布 | 无 CVE、secret、SBOM、signature gate | 发布前扫描并签名 |

### 7.2 质量检测维度

#### 7.2.1 语法、编码与格式

检测内容：

- 全部支持 Python 版本能解析源文件。
- UTF-8 编码统一，禁止无必要 BOM。
- 无 invalid escape、混合换行、尾随空白和不可见控制字符。
- Black/Ruff format 结果唯一且稳定。

目标：

- 新增解析 warning 为 0。
- 格式检查为阻断项。
- 编码差异不再污染构建和终端输出。

#### 7.2.2 Lint 与常见缺陷

在现有 E/W/F/I/B/C4 基础上分阶段评估：

- Python upgrade 与现代语法规则。
- simplify、performance、async、exception、security 和 Ruff-specific 规则。
- 每条新增 ignore 必须说明作用域、原因、owner 和移除条件。
- 不对 legacy 全仓一次性 autofix；先对新增/修改代码设零债务门槛。

目标：

- 修改范围内 lint 错误为 0。
- CI 不再 `continue-on-error`。
- ignore 数量可趋势化、不可静默增长。

#### 7.2.3 类型质量

当前粗略静态统计显示返回值标注约 90.9%，参数完整标注约 95.9%，但 `Any` 使用较多，说明“有标注”不等于“边界严格”。

建议分层：

1. Domain/Contracts、Ports：最高严格度，禁止隐式 Any 和未标注公共 API。
2. Application Services：高严格度，所有 port 调用和 outcome 结构化。
3. Adapters：允许受控 Any，但必须在边界完成 parse/validation。
4. Legacy Agent/Presentation：按模块逐步收敛，不做一次性全仓严格化。

目标：

- 新公共 contract/port 无 Any 泄漏。
- `type: ignore` 有精确错误码和原因。
- mypy 成为核心层阻断门禁，pyright 角色明确。

#### 7.2.4 架构与依赖

检测内容：

- `.importlinter` 全部 contract。
- Domain、Ports、Application 的 forbidden imports。
- Presentation 直连具体 adapter。
- proof authority 越权。
- 新公共命名不符合中立词汇。
- compatibility shim 的调用和过期状态。

目标：

- 新架构违规为 0。
- 所有例外必须区分 BY-DESIGN 与 DEBT。
- 架构规则在 PR 中自动阻断。

#### 7.2.5 复杂度、大小与职责

建议采用“禁止增长 + 渐进拆解”而非全仓硬切：

| 对象 | 建议治理线 | 处理原则 |
|---|---:|---|
| 新函数 | 建议不超过 80 行 | 超过时说明为何无法拆分 |
| 现有函数 >100 行 | 不得无审查继续增长 | 优先提取纯逻辑和边界 adapter |
| 现有函数 >200 行 | 列入结构债 | 变更时必须评估拆分 |
| 新模块 | 建议不超过 800 行 | schema/生成代码可申请豁免 |
| 现有模块 >1,500 行 | 冻结无界增长 | 新职责不得继续加入 |
| 类 >500 行 | 检查是否同时拥有状态、IO、策略和展示 | 按 owner 和 use case 拆分 |

检测工具可使用 AST 指标、radon/xenon、依赖图和 churn 热点联合判断。单纯行数不作为自动拒绝的唯一理由。

#### 7.2.6 重复、死代码与兼容债

检测内容：

- 重复 contract 构造、状态映射、错误字符串和正则。
- 无生产消费者的 helper、旧入口和 shim。
- 同一语义多张映射表。
- 仅被测试 patch 的 load-bearing seam。

治理要求：

- 重复检测先报告候选，再由行为证据确认，不机械合并。
- 删除前证明生产调用面、测试 patch 面和动态 import 面。
- 兼容债进入台账，不允许通过注释永久保留。

#### 7.2.7 异常、日志与错误契约

906 处 broad catch 不能简单全删，因为 adapter/UI/long-running loop 确实需要故障隔离。正确治理方式是分类：

- Boundary catch：允许，但必须记录上下文、转换 typed error/outcome，并决定是否继续。
- Cleanup catch：允许 best-effort，但必须有 cleanup failure 指标。
- Optional feature catch：允许降级，但 readiness 必须显示 degraded。
- Silent catch：禁止关键路径静默 `pass`。
- Control-flow catch：禁止依赖异常文本长期驱动主流程。

目标：

- 新增 broad catch 必须说明边界和后续状态。
- 关键 trace、proof、persistence、cancellation 不得静默吞错。
- 日志使用结构化字段，不在核心层直接 `print`。

#### 7.2.8 异步、线程与资源生命周期

检测内容：

- `create_task` 是否保存句柄、传播取消、收集异常。
- daemon thread 是否可控停止和 join。
- event loop 是否总能 close。
- browser、HTTP client、subprocess、container、SSH、socket 和 temp file 是否有 owner。
- 锁是否只在进程内有效，是否可能跨 loop 复用。
- 队列满时是否有 backpressure 或 drop 指标。

目标：

- 所有后台执行单元都有 registry 和生命周期。
- shutdown 后无遗留资源。
- 取消和超时语义在所有 runtime 一致。

#### 7.2.9 安全静态检测

建议门禁覆盖：

- Python SAST：危险 subprocess、反序列化、路径、TLS、临时文件和日志敏感信息。
- 密钥扫描：提交前和 CI 双层扫描。
- 依赖漏洞：Python、GitHub Actions、Docker base 和系统包。
- 容器扫描：CVE、secret、misconfiguration、SBOM 和 provenance。
- Web/MCP 控制面：鉴权、授权、CORS、CSRF、rate limit、upload 和 SSRF 边界。

目标：

- 高危发现阻断合并/发布。
- 例外必须有风险接受记录、到期日和 owner。

#### 7.2.10 文档与版本一致性

自动检测：

- 项目版本、README badge、MCP clientInfo、CHANGELOG 和 release tag 一致。
- 文档链接存在。
- 当前治理指南唯一且 docs index 指向正确。
- 配置字段与 `.env.example`、Settings schema、Web settings 一致。
- 已废弃文档有状态标记，不参与当前路线决策。

目标：

- 版本漂移为 0。
- 文档断链为 0。
- 同一主题只有一个 Active/Canonical 文档。

### 7.3 分层质量流水线

| 层级 | 触发时机 | 应包含内容 | 目标耗时 | 是否阻断 |
|---|---|---|---:|---|
| 本地快速层 | 每次提交前 | format、lint、基础类型、编码、secret staged scan | 1–3 分钟 | 是 |
| PR 核心层 | 每个 PR | Python 矩阵、核心检查、import-linter、source guards、依赖审计 | 10–20 分钟 | 是 |
| PR 风险层 | 影响核心控制面时 | integration、contract parity、changed coverage、容器配置检查 | 20–40 分钟 | 是 |
| Nightly | 每晚/定时 | 全量 eval、模型矩阵、长时运行、资源泄漏、镜像扫描 | 可较长 | 生成告警 |
| Release | tag 前 | 全量门禁、可复现构建、SBOM、签名、升级/回滚验证 | 按版本 | 是 |

本文不提供具体测试用例；后续实现时应根据受影响边界选择相应验证层。

### 7.4 Coverage 治理

建议从当前 30% 总阈值升级为多维门槛：

- Domain/Contracts、Ports、Application Services：目标 ≥90%。
- Tool Executor、Verifier、Recovery、Task lifecycle：目标 ≥85%。
- Adapters/Runtime：目标 ≥70%，并辅以集成验证。
- Presentation：不再整个目录排除，改为对纯 read model、route service 和 command handler 统计。
- Changed code：目标 ≥80%，防止总体覆盖掩盖新代码盲区。
- Eval/真实解题率独立报告，不与代码行覆盖率混为一谈。

### 7.5 质量评分卡

每个版本建议输出：

| 维度 | 权重 | 核心数据 |
|---|---:|---|
| 事实可信度 | 25% | 假成功、proof 完整、状态一致、trace 完整 |
| 真实能力 | 20% | 分层解题率、诚实终止、策略可达 |
| 可靠性 | 15% | timeout/cancel、资源清理、数据损坏、恢复 |
| 代码质量 | 15% | lint/type/architecture/complexity/coverage |
| 安全 | 15% | 控制面、scope、secret、依赖、镜像 |
| 运维与成本 | 10% | SLO、告警、RTO/RPO、单位成功成本 |

评分只用于趋势和发布决策，不允许通过降低题目难度、扩大排除范围或隐藏失败来提升分数。

---

## 8. 运维与生产化优化

### 8.1 运行 Profile 管理

建议正式定义并维护以下 profile：

| Profile | 目标 | 默认网络暴露 | 权限 | 主要约束 |
|---|---|---|---|---|
| Local Desktop | 单人本机 TUI/CLI/Web | loopback | 当前用户 | 不承诺多用户和高可用 |
| Base Docker | 隔离的通用 Agent | 无或显式映射 | 非 root | 资源、目录和网络受限 |
| Kali Docker | 重工具和 VPN | 无或受控网络 | 高权限但限于隔离宿主 | 禁止作为共享长期服务默认形态 |
| SSH Runtime | 远程受控执行节点 | SSH 专用 | 最小可用账号 | 主机密钥、凭据、配额和清理 |
| MCP Local | 本机 MCP client 集成 | stdio/loopback | 本地用户 | 可信客户端 |
| MCP Remote | 网络 MCP 服务 | 显式开启 | RBAC/tenant scope | TLS、auth、audit、quota 必需 |
| Web Console Remote | 远程操作台 | 显式开启 | RBAC | auth、CSRF/CORS、TLS、session 必需 |

每个 profile 必须有：

- 支持的操作系统和 Python 版本。
- 支持的 runtime capability。
- 默认安全边界。
- 数据目录和保留策略。
- 资源预算。
- 健康检查和升级/回滚方式。

### 8.2 健康检查

至少区分四类状态：

1. **Liveness**：进程事件循环仍能响应，不检查外部依赖。
2. **Readiness**：配置有效、关键目录可写、模型/runtime 可接受任务。
3. **Dependency health**：provider、Docker daemon、SSH、browser、MCP server、RAG index 和 verifier 的独立状态。
4. **Workload health**：队列深度、运行任务、超时、失败、取消中任务和资源占用。

当前 `/api/status` 中 runtime 固定显示为 LocalRuntime，后续必须改为真实 profile 和依赖快照。健康端点不得返回密钥或完整敏感配置。

### 8.3 可观测性

#### 日志

- 采用结构化日志，统一 level、event、task_id、run_id、trace_id、component、error_class。
- stdout 用于运行日志，审计和业务 trace 使用独立 sink。
- 配置 rotation、retention、size cap 和敏感字段 redaction。
- broad catch 必须带异常栈或明确 reason code，禁止关键错误静默 `pass`。

#### 指标

至少覆盖：

- 任务：queued/running/cancelling/succeeded/stopped/failed/cancelled/timed_out。
- Proof：candidate/runtime/verified/rejected/retracted。
- Agent：iterations、no-progress、replan、model calls、tool calls。
- Runtime：command latency、timeouts、cleanup、browser/container/SSH health。
- Provider：latency、tokens、cost、rate limit、failover、error class。
- Persistence：write latency、conflict、corruption、recovery、disk usage。
- Event bus：queue depth、drop count、subscriber lag。

指标标签必须控制基数，不把完整 URL、payload、flag、error text 或 task prompt 作为 label。

#### Trace

- 使用统一 trace/span 模型覆盖 entry、step、chain、skill、model、tool、verification 和 handoff。
- metrics JSON、session ledger、tool provenance 和 Web trace 最终应能通过稳定 ID 关联。
- trace 导出失败不得影响任务执行，但必须产生独立告警。

### 8.4 SLO 与告警

建议首批 SLO：

- 控制面可用性。
- 任务受理成功率。
- 取消生效延迟。
- 关键 trace 完整率。
- 数据持久化成功率。
- provider 可用性和 failover 成功率。
- verified solve 的单位成本和耗时。

告警分级：

- Sev-1：未授权控制面、取消后继续执行、proof 误升级、敏感数据进入镜像/日志。
- Sev-2：持久化损坏、任务大面积失败、provider 全部不可用、磁盘接近耗尽。
- Sev-3：单一工具/runtime 降级、event drop、成本异常、索引陈旧。
- Sev-4：文档漂移、低优先级依赖更新、非关键性能趋势。

### 8.5 配置与密钥运维

当前配置面较大，建议建立配置目录：

- 字段名、类型、默认值和允许范围。
- 输入来源优先级：defaults、config file、env、CLI、session override。
- 是否敏感、是否可回显、是否可 Web 修改。
- 是否热更新、何时生效、是否需要重启。
- 适用 profile 和废弃版本。

密钥治理：

- `.env` 仅作为本地开发方案，不作为远程/长期服务的首选 secret store。
- Web API 不能返回明文 secret；更新 secret 需要独立权限和审计。
- 容器使用 secret mount 或平台 secret，不通过镜像层和普通环境导出。
- SSH askpass/password 临时文件采用最小权限并确保异常路径清理。
- 日志、trace、receipt、report 和 support bundle 使用同一脱敏策略。

### 8.6 容器与镜像

优先事项：

1. `.dockerignore` 排除所有本地运行产物、题目、对话、缓存、报告、日志、workspace 和密钥材料。
2. Base image 使用受控版本或 digest，建立升级窗口。
3. Python 版本与项目支持矩阵一致，不默认使用未在 CI 验证的 3.14。
4. 依赖安装使用 lock/constraints，确保可复现。
5. 构建生成 SBOM、provenance，并执行漏洞和 secret 扫描。
6. 发布镜像签名，`latest` 仅作便利标签，不作为部署唯一引用。
7. Base image 保持非 root、drop capabilities、只读 rootfs 和资源限制。
8. Kali profile 的 privileged、NET_ADMIN、SYS_ADMIN 必须有明确风险接受，只用于隔离环境。
9. 为容器添加 healthcheck、graceful shutdown 和数据卷权限策略。

### 8.7 数据备份与恢复

需要纳入备份范围：

- claims、evidence、proof、receipts、ledger、checkpoint。
- strategy memory、knowledge index metadata、notes、conversation/session。
- reports、artifacts 和 run manifests。
- 配置 schema 和非敏感配置；secret 单独管理。

要求：

- 明确哪些可重建、哪些不可重建。
- 备份加密、校验、保留和访问审计。
- 定期做 restore drill，不以“备份文件存在”代表可恢复。
- 恢复后重建 read model，并验证 artifact hash 和 schema compatibility。

### 8.8 容量与资源管理

至少设置：

- 全局和每任务并发上限。
- 每 host 请求并发和速率。
- browser context、subprocess、container exec 和 SSH session 上限。
- token、费用、墙钟时间、磁盘、内存和 artifact 大小配额。
- event queue、task queue 和日志缓冲上限。

超限行为必须是可解释的 blocked/degraded/timed_out，而不是 OOM、静默丢事件或无限排队。

### 8.9 发布与回滚

建议统一 release policy、checklist 和 playbook 的职责，最终收敛为一份发布手册。

每次发布应有：

- 唯一版本号和 release manifest。
- 变更、兼容性、schema migration、配置变化和已知问题。
- 构建产物 hash、SBOM、签名和来源。
- 数据备份/迁移前置条件。
- 回滚版本、回滚步骤和不可逆变化说明。
- 发布后 smoke、readiness、metrics 和关键任务核验。

### 8.10 事件响应

需要预先定义 runbook：

- 远程控制面疑似未授权访问。
- 任务无法取消或后台持续执行。
- provider 凭据泄漏或费用异常。
- 审计/trace/ledger 损坏。
- 镜像包含不应包含的本地 artifact。
- 大量任务失败或 stuck。
- 磁盘、内存、线程、browser、container 耗尽。
- schema 升级后无法读取旧状态。

每次事件复盘必须产生：时间线、影响、根因、触发条件、检测缺口、修复、长期 guard 和 owner。

---

## 9. 安全与信任边界优化

### 9.1 信任模型

FlagHunter 同时处理模型输出、目标响应、工具 stdout、浏览器内容、上传文件、知识文档、MCP 返回值和恢复状态。以上内容一律是不可信数据，不是系统指令。

建议定义以下信任级别：

| 级别 | 数据来源 | 允许用途 | 禁止用途 |
|---|---|---|---|
| T0 Untrusted | 目标页面、附件、工具输出、外部 MCP、模型文本 | 生成 observation/candidate | 直接改变权限、配置、proof、scope |
| T1 Parsed | 通过 schema 和安全 parser 的结构化数据 | 进入 application service | 绕过 policy/verifier |
| T2 Runtime-grounded | 有 runtime receipt/artifact/trace 的 evidence | 支持 claim review | 自动升级 verified |
| T3 Verified | proof authority 产出的 proof | 终止、提交、报告和指标 | 被普通模块覆盖 |
| T4 Operator-authorized | 明确身份和权限的人工命令 | 修改配置、批准高风险动作 | 越过审计和 scope |

### 9.2 控制面安全

当前最重要的安全收口对象不是某个单独工具，而是 Web/MCP 控制面，因为它们能够：

- 创建和取消任务。
- 修改运行配置和模型密钥。
- 添加外部 MCP server。
- 启用/禁用工具。
- 读取日志、memory、trace 和 artifact。
- 驱动高权限 runtime。

当前已完成的底线是：Web 与 MCP 网络入口默认使用 loopback；非 loopback 绑定必须配置 bearer token，否则拒绝启动；MCP session ID 仅用于关联。该底线只解决“无认证直接暴露”的一部分风险，不等于 RBAC、资源授权、来源控制、TLS、token 生命周期和配额已经完成。Web 当前还必须修正两个具体边界：`?token=` 只能用于无法设置 header 的 SSE 请求，不能作为所有 `/api/*` 的通用凭据；CORS 不能继续使用任意 Origin。

目标控制：

1. 默认只绑定 loopback。
2. 远程模式需要显式 profile，不得通过一个普通 `--host` 参数无意开启。
3. 身份认证与 MCP session ID 分离。
4. RBAC 至少区分 viewer、operator、administrator、automation client。
5. 权限按 action 和 resource 检查，不只按 endpoint。
6. 高风险动作支持审批、二次确认或 policy gate。
7. 所有配置、工具、任务和数据访问写入安全审计。
8. TLS 在服务端或可信反向代理终止，且明确代理信任边界。
9. CORS 使用 allowlist，修改类请求实施 CSRF/Origin 校验。
10. 实施 request size、upload size、rate、concurrency 和 session quota。

### 9.3 Scope 与授权

已有 M4 scope enforcer 是良好基础，但需要扩展到完整目标生命周期：

- 初始输入校验。
- URL normalization 后校验。
- DNS 解析到 IP 后校验。
- redirect 每一跳校验。
- 工具派生子域、vhost、内网 URL 和回调地址校验。
- 浏览器导航、下载和 WebSocket 目标校验。
- 外部 MCP 工具二次派生目标校验。
- 任务恢复时重新确认当前 scope，而不是无条件沿用旧快照。

Scope decision 必须形成 receipt，包含 policy version、输入目标、解析结果、允许/拒绝原因和 operator identity。

### 9.4 Prompt Injection 与数据投毒

需要明确：

- 页面、README、源码注释、文档、日志、工具输出和 MCP 描述中的提示词都只能作为数据。
- 知识入库前执行来源、类型、hash、信任等级和内容安全标注。
- 检索内容使用独立 envelope，禁止与 system/developer 指令拼接成同一权威层。
- 模型提出的工具参数必须经过 schema、scope、permission 和 budget 校验。
- memory 写入必须经过 generalizability、evidence 和负反馈 policy。
- 恢复快照不能携带可执行指令，只恢复结构化状态和引用。

检测指标：

- untrusted content 触发高权限 action 的阻断数。
- memory 被撤回/降级的原因分布。
- 外部 MCP 返回值导致 parser/policy 拒绝的比例。
- prompt version 和 retrieved context 对决策的可追溯率。

### 9.5 凭据与敏感数据

数据分类至少包括：

- Provider API keys。
- SSH password/key path、MSF credentials、platform token。
- Cookie、session、Authorization headers。
- Challenge flag、target details、loot、report 和 conversation。
- 用户上传 artifact 和本地 workspace 路径。

要求：

- secret 不进入普通日志、metrics label、exception message、trace preview、report 或镜像层。
- secret 更新与普通配置更新分离。
- 进程内 secret 尽量短生命周期，子进程只获得必要环境。
- 临时凭据文件设置最小权限并在成功、失败、取消、崩溃恢复时清理。
- support bundle 默认脱敏并需要显式授权导出。
- 凭据轮换后旧会话和连接池可控失效。

### 9.6 Artifact 与上传安全

上传、下载、解包和解析是高风险边界，应统一进入 artifact service：

- 文件名与存储 ID 分离，禁止路径穿越。
- 限制单文件、总任务、解压后大小和文件数量。
- 防止 zip slip、symlink escape、压缩炸弹和特殊设备文件。
- MIME、扩展名和实际文件头分别记录，不能互相信任。
- parser 在隔离进程/容器中运行，并设置 CPU、内存和时限。
- 原始 artifact 只读保存，所有派生物写入独立路径。
- 每个派生物记录 parent hash、transform、tool version 和 trace。
- 清理采用 retention policy，不由任务代码随意递归删除。

### 9.7 Runtime 与容器安全

- Base Docker 默认 non-root、cap-drop、read-only rootfs、no-new-privileges。
- 高权限 Kali 容器只运行在可丢弃隔离节点，不作为共享宿主长期服务。
- Docker socket 不直接暴露给不可信任务。
- SSH 使用 host key pinning、独立低权限账号和命令/目录隔离。
- LocalRuntime 明确提醒其与宿主同权限，不把“本地”误当“沙箱”。
- terminal 和动态脚本工具通过 permission policy、scope 和 receipt 控制。
- browser 下载、扩展、user data dir 和调试端口不得跨任务共享。

### 9.8 软件供应链

当前已使用 Dependabot，但完整供应链还需要：

1. 唯一依赖声明源和可复现 lock/constraints。
2. Python 依赖漏洞扫描与许可证清单。
3. GitHub Actions 固定受控版本，关键发布动作可考虑 pin 到 commit SHA。
4. Docker base digest、apt snapshot/版本策略和镜像 CVE 扫描。
5. 构建 SBOM、provenance、artifact hash 和签名。
6. 发布前 secret scan 和 build context 清单检查。
7. 第三方本地工具记录来源、版本、hash、许可证和更新机制。
8. 可选大型依赖按 profile 隔离，降低默认攻击面。

### 9.9 安全验收目标

- 远程控制面在无有效身份时不可执行任何读写操作。
- viewer 不能启动任务、修改配置或读取敏感 artifact。
- operator 不能改变全局安全策略和 provider secret。
- 取消后不得再产生外部动作。
- scope 在 redirect、DNS 和外部 MCP 派生目标上持续生效。
- 构建镜像不包含 `.env`、loot、logs、reports、challenges、conversations、workspaces 或本地缓存。
- 高危依赖/镜像/secret 发现阻止发布。
- verified proof 不可由不可信数据直接产生。

---

## 10. 数据、Schema 与持久化治理

### 10.1 当前数据面

当前数据分散在：

- `loot/notes.json` 和相关 archive。
- strategy memory NDJSON。
- session/conversation snapshots。
- session ledger、checkpoint、artifact registry。
- tool provenance、metrics JSON、Web task JSON。
- audit JSONL、reports、knowledge index 和 retrospective 数据。
- domain contracts 与大量 readback schema。

静态扫描发现 schema/version 相关引用超过 300 处。数量本身不是问题，问题是目前同时存在整数版本、`challenge.*.v1`、`p2/p3/p4*`、state `1.7` 等命名体系，缺少统一 registry 和迁移矩阵。

### 10.2 数据分类与 owner

| 数据类型 | Canonical owner | 可否重建 | 写入模式 | 建议保留 |
|---|---|---|---|---|
| Claim/Evidence/Proof | Domain/Application store | 不应依赖重建 | 追加 + 状态转换 | 长期/按项目策略 |
| Tool Receipt/Trace | Audit/trace store | 部分可重建 | append-only | 中长期 |
| Checkpoint | State store | 可从最近状态继续 | 追加快照 | 短中期 |
| Read Model | Projection service | 可重建 | 覆盖/物化 | 短期 |
| Strategy Memory | Memory store | 不完全可重建 | 追加 + compaction | 中长期 |
| RAG Index | Knowledge adapter | 可从源文档重建 | versioned rebuild | 可重建缓存 |
| Metrics | Observability backend | 不作为业务真相 | append/aggregate | 按运维策略 |
| Artifact | Artifact store | 原始通常不可重建 | immutable blob | 按敏感级别 |
| Report | Reporting adapter | 可从 canonical data 重建 | immutable version | 按交付策略 |

### 10.3 Schema Registry

建议建立统一 schema registry，记录：

- schema ID 和语义版本。
- owner module。
- 当前状态：draft、active、deprecated、retired。
- reader/writer 兼容范围。
- migration function 和回滚能力。
- 存储位置与数据分类。
- 首次引入、最后写入和计划移除版本。

命名建议：

- 公共核心 schema 使用 `challenge.<noun>.vN`。
- 阶段性 `p2/p3/p4` 名称只作为历史 migration source，不继续扩展为公共命名。
- 同一 schema 不同时使用整数和字符串版本。
- state snapshot version 与 domain schema version 分离并明确用途。

### 10.4 写入可靠性

对本地文件 store 统一要求：

1. 先写同目录临时文件，flush/fsync 后原子 replace。
2. append-only 文件按单行完整记录写入，并记录 checksum/sequence。
3. 进程内锁不能替代跨进程协调；明确单进程限制或引入文件锁/事务存储。
4. writer 使用单一 service，presentation/strategy 不直接 `write_text`。
5. 磁盘满、权限、编码、部分写和损坏有 typed error。
6. 启动时检测尾部半行、重复 sequence、checksum 错误并隔离损坏记录。
7. compaction 使用新文件构建、校验、原子切换，不原地重写唯一副本。

### 10.5 并发与一致性

需要明确支持范围：

- 单线程。
- 单进程多 asyncio task。
- 单进程多线程。
- 多进程。
- 多节点共享存储。

当前多个 store 只具备进程内 `asyncio.Lock` 或 `threading.Lock`。在 Web daemon thread、MCP task、Crew 和多进程部署同时写入时，应选择：

- 明确限制为 single-writer，并通过 IPC/queue 统一写入；或
- 使用具备事务、锁和唯一约束的存储 adapter。

不得默认假设“JSON 文件很小，因此并发安全”。

### 10.6 幂等、去重与顺序

- 每个外部副作用 action 有 operation ID。
- receipt、event、checkpoint 和 proof 有唯一 ID 和 sequence。
- 重试写入不得产生重复 proof、重复提交或重复 billing。
- event 到达乱序时 projection 能按 sequence/causal reference 处理。
- 使用 UTC aware timestamp 辅助展示，不用 wall clock 作为唯一排序键。
- UUID/ULID 等 ID 策略统一，避免短 ID 碰撞和不同模块自行截断。

### 10.7 Migration 与兼容

每次 schema 变化必须说明：

- 旧 reader 是否能读新数据。
- 新 reader 是否能读旧数据。
- 是否需要 backfill。
- 是否双读/双写，持续多久。
- 回滚后数据是否仍可用。
- migration 失败如何恢复。
- read model 是否需要重建。

禁止长期无期限双写。兼容窗口结束后删除旧 writer，保留必要 reader 或离线迁移工具。

### 10.8 Retention、删除与隐私

每类数据必须有：

- 默认保留期。
- 最大磁盘配额。
- 敏感级别。
- 是否允许导出。
- 删除方式和 tombstone 语义。
- 是否被备份及备份中的删除策略。

特殊注意：

- loot、conversation、browser storage、cookies、SSH 凭据、模型 prompt/response 和报告可能包含敏感信息。
- metrics 和 trace 不应因“用于调试”而无限保留全文。
- 删除 artifact 后，claim/evidence 保留 hash 和删除状态，不留下失效路径假装可读。

### 10.9 数据治理验收目标

- canonical store、cache、projection 和 export 能被明确区分。
- 关键写入原子且可恢复。
- 多 writer 模式有明确一致性方案。
- 所有 schema 可在 registry 中查询生命周期。
- UTC、ID、sequence 和关联字段统一。
- 备份能够实际恢复，read model 可重建。
- retention 和磁盘配额自动执行且可审计。

---

## 11. 性能、成本与容量优化

### 11.1 性能优化原则

1. 先测量端到端瓶颈，再优化局部函数。
2. 优化单位 verified success 的总成本，不追求孤立吞吐。
3. 缓存必须有正确性边界和失效策略。
4. 并发必须有独立性、配额和回压。
5. 不以牺牲 trace、proof、scope 和取消能力换速度。

### 11.2 性能预算

建议每个任务记录和约束：

| 资源 | 预算维度 | 超限动作 |
|---|---|---|
| Wall clock | task/phase/step | timeout + cleanup + checkpoint |
| Token | task/model-call/phase | route lighter model、summarize 或停止 |
| Cost | task/day/provider | block、degrade 或人工批准 |
| Tool calls | task/tool/host | 降频、切换策略或停止 |
| Network | requests/host/second | queue、backoff、policy block |
| Browser | contexts/pages/downloads | queue 或降级 |
| Process | subprocess/container/SSH | concurrency gate |
| Memory | process/task/cache | evict、degrade 或拒绝新任务 |
| Disk | artifact/log/index/workspace | rotate、cleanup 或 block |

### 11.3 LLM 成本

- 规划、分类、解析、总结和复杂推理使用不同模型 tier。
- deterministic parser/strategy 能完成的工作不调用 LLM。
- Prompt 只包含当前决策所需 evidence refs 和摘要，不重复全量历史。
- 模型失败重试计入预算，避免 provider failover 倍增成本。
- 记录 input cache、output cache 和 provider cache 的实际收益。
- 每个模型 route 以 solve uplift、延迟和成本三维评价。

### 11.4 工具与网络成本

- recon 使用增量去重和 canonical URL。
- 先轻量最小实验，再升级高成本 scanner。
- 同 host 工具调用统一 rate/concurrency policy。
- 长扫描输出流式写 artifact，不在内存和 event bus 复制全文。
- 工具结果缓存绑定 target snapshot、arguments、tool version、runtime 和过期时间。
- 失败安装/探测使用负缓存，避免每轮重复探测。

### 11.5 RAG 与 Memory 性能

- 索引分层：metadata filter → sparse/dense retrieve → rerank → budget truncate。
- 文档增量 hash，未变化内容不重复 embedding。
- 检索 cache 按 query、index version 和 policy version 失效。
- 记录索引加载时间、内存、检索 P50/P95 和实际引用率。
- 大索引可考虑独立进程/服务，但先证明单机瓶颈。

### 11.6 Browser 与 Runtime 性能

- Browser context 按任务复用，page 按策略管理，禁止全局跨任务复用。
- 预热与冷启动分别统计，不隐藏首次安装/启动成本。
- Docker/SSH connection 可复用，但凭据和 task isolation 不得被破坏。
- 子进程输出设置限额和流式消费，防止 pipe 堵塞。
- cleanup 纳入任务耗时，不把资源回收成本排除在外。

### 11.7 Crew 性能

并行收益判定：

- 任务相互独立。
- 共享资源不会成为瓶颈。
- 每个 worker 有不同 hypothesis/信息目标。
- 预期减少 wall time 或提高 solve probability。
- 重复率和协调成本低于收益。

若 Crew 的成本增长高于 solve uplift，应回退单体或减少 worker，而不是继续扩容。

### 11.8 性能目标

- 建立 P50/P95/P99，不只报告平均值。
- 记录冷/暖启动差异。
- 单位 verified solve 的 token、费用、工具时间持续下降。
- no-progress 动作率下降。
- event drop、queue wait、resource saturation 可观测。
- 优化前后使用同一 corpus、profile、model 和 budget 比较。

---

## 12. 容易遗漏但必须纳入的优化点

### 12.1 Graceful Shutdown

应用退出、终端中断、容器停止、Web server shutdown 和 MCP disconnect 时，需要：

- 停止接收新任务。
- 标记运行任务 draining/cancelling。
- 传播取消并等待限定时间。
- 保存 checkpoint 和 terminal receipt。
- 关闭 browser、HTTP client、MCP transport、runtime 和日志 sink。
- 超时后强制回收并记录未清理资源。

### 12.2 Backpressure 与事件丢失

当前部分 queue 满时会静默丢弃。需要：

- 关键事件与 UI 更新分级。
- 关键 receipt/proof/terminal event 不可丢。
- 非关键进度事件可合并或采样。
- 记录 queue depth、subscriber lag、drop count。
- SSE 重连支持 event sequence/cursor。

### 12.3 多用户与多租户

即使当前主要是单人使用，远程 Web/MCP 一旦开放就需要考虑：

- 身份、session 和 task ownership。
- workspace、memory、artifact、secret 和 scope 隔离。
- 每用户/客户端 quota。
- 管理员与 operator 权限分离。
- 审计中记录 actor。

在没有这些能力前，应明确标记远程 profile 为单租户受控环境。

### 12.4 配置爆炸与 Feature Flag 生命周期

约 167 个相关环境变量/常量名说明配置治理已成为独立问题：

- 合并同义开关和历史别名。
- 每个 feature flag 有 owner、默认值、引入日期、观测指标和移除条件。
- 已永久启用的迁移开关应删除。
- 避免模块 import 时读取环境导致后续 update_settings 不生效。
- Web 显示“当前值、来源、是否生效、是否需重启”。

### 12.5 时间、时区和时钟

- 全部持久化时间使用 UTC aware ISO 8601。
- duration 使用 monotonic clock。
- local time 只在 presentation 格式化。
- 分布式节点考虑 clock skew，不用 timestamp 作为唯一因果排序。
- `datetime.utcnow()` 和 naive `datetime.now()` 逐步迁移，但不做无关全仓改动。

### 12.6 ID 与关联

- task_id、run_id、session_id、trace_id、span_id、receipt_id、claim_id、proof_id 明确格式和生命周期。
- 不随意截断 UUID 作为持久唯一键。
- retry/replay/continue 保留 lineage。
- 外部平台 ID 与内部 ID 分开。
- 日志和 metrics 能通过统一关联 ID 回读。

### 12.7 跨平台与编码

- Python 支持矩阵覆盖 Windows、Linux，必要时包含 macOS/WSL 声明。
- shell quoting、路径、临时文件、信号、进程树和换行有平台 adapter。
- 源码统一 UTF-8 无 BOM，清理 invalid escape warning。
- 终端输出处理中文宽字符、ANSI、PowerShell 和非 UTF-8 工具输出。
- Docker 使用的 Python 版本必须在 CI 矩阵中。

### 12.8 网络代理、VPN 与 DNS

- proxy/VPN 是 runtime 属性，不依赖全局环境隐式传播。
- 记录 DNS、代理、VPN interface 和出口 profile，不记录敏感凭据。
- scope 在 DNS/redirect 后复核。
- VPN 失败时任务 blocked/degraded，不无声改走宿主网络。
- 容器网络和 host network 使用必须显式声明。

### 12.9 Offline 与 Degraded Mode

需要定义在以下依赖缺失时系统还能做什么：

- 无 LLM。
- 无 browser。
- 无 Docker/Kali/SSH。
- 无 RAG embedding。
- 无外部 MCP。
- 单一 provider 或全部 provider 不可用。

每种模式必须返回 capability snapshot，防止用户把降级行为误认为完整能力。

### 12.10 插件与第三方工具生命周期

- 插件/工具有 manifest、schema、版本、权限、依赖和来源 hash。
- 加载失败不破坏核心 registry。
- 动态 import 受允许目录和签名/信任策略控制。
- 工具升级有兼容检查和 rollback。
- 未维护/高风险工具可禁用且不会让策略误判为可用。

### 12.11 License 与再分发

Kali 工具、字典、模型、第三方二进制和知识内容可能有不同许可证：

- SBOM 同时记录许可证。
- 镜像/发布包明确哪些工具只是运行时安装，不由项目再分发。
- 知识来源保留 attribution 和使用条件。
- 报告模板、截图和附件的分发范围明确。

### 12.12 数据最小化

- 只收集完成任务所需内容。
- 不把完整响应、cookie、prompt、tool stdout 默认永久保存。
- preview 与完整 artifact 分开。
- 调试级别提升应有时限并自动恢复。
- support/telemetry 导出默认关闭且可审计。

### 12.13 可访问性与操作者体验

- 状态颜色不能是唯一信息载体。
- 长任务提供稳定进度、剩余预算和取消反馈。
- 错误同时提供人类可读说明和 reason code。
- TUI/Web 保持键盘可达、焦点清晰、长文本不破坏布局。
- 关键确认操作避免误触，重复提交具有幂等保护。

### 12.14 维护者总线因子

- 核心架构、发布、恢复、secret rotation 和事故处理不能只存在于单人记忆。
- CODEOWNERS 可进一步按 domain/application/runtime/MCP/ops 分区。
- 关键 runbook 定期演练。
- 复杂 migration 和例外必须留下 ADR，不依赖聊天记录。

### 12.15 文档过期检测

- 文档记录 owner、状态、last reviewed、supersedes/superseded by。
- 代码路径不存在、版本过旧或结论与 runtime 冲突时自动提示。
- 历史 WP/学习笔记不进入当前路线搜索优先级。
- 超长 migration playbook 完成后冻结归档，不再持续追加为日记。

---

## 13. 分阶段优化路线与详细 Backlog

### 13.1 阶段总览

| 阶段 | 主目标 | 完成标志 | 不应混入的工作 |
|---|---|---|---|
| Phase A | 控制面与事实线收口 | 取消真实、远程入口受控、success=verified | 新增低优先级策略 |
| Phase B | 质量与可复现工程 | 硬门禁、版本/依赖单源、可复现构建 | 全仓大重构 |
| Phase C | 数据与状态可靠性 | 原子持久化、schema registry、恢复演练 | UI 装饰性优化 |
| Phase D | 真实解题率提升 | baseline 按失败簇稳定提升 | 无 corpus 依据的能力堆叠 |
| Phase E | 运维与安全产品化 | SLO、告警、RBAC、备份、发布回滚 | 未经容量评估的远程扩容 |
| Phase F | 性能与生态 | 单位成功成本下降、插件治理成熟 | 牺牲 proof/trace 的加速 |

### 13.2 Phase A：控制面与事实线

| ID | 优先级 | 工作项 | 预期产物 | 验收目标 |
|---|---|---|---|---|
| A-01 | P0 | 部分完成：canonical lifecycle contract 已落地，生产入口接线待 A-03/A-04 | Task status contract + transition service | Web/MCP/registry 全部消费同一状态语义，新增状态可被门禁自动发现 |
| A-02 | P0 | 部分完成：cancellation token/scope/registry 原语已落地，传播接线和清理未完成 | 可传播的 cancellation scope | 取消确认后新增外部动作数为 0，所有子资源均有清理回执 |
| A-03 | P0 | Web thread 真实停止与清理 | managed task runner | stopped 不再仅改 UI |
| A-04 | P0 | 进行中但未验收：当前工作树只有未提交 MCP 草稿，不计入稳定完成度 | task handle + dispatcher/agent/tool/runtime cancellation | async 与 blocking 路径均可及时取消，首次调度前取消也不泄漏 handle/scope |
| A-05 | P0 | ✅ Success 统一消费 proof authority | terminal outcome service | 假成功率为 0 |
| A-06 | P0 | ✅ MCP metrics 修正成功语义 | proof-aware metrics | done 与 success 分离 |
| A-07 | P0 | 部分完成：Web 非 loopback bearer 认证和 fail-closed 已落地；RBAC/资源授权仍待完成 | authentication + authorization policy | 未认证请求被拒绝，已认证主体也只能执行角色和资源范围内动作 |
| A-08 | P0 | 部分完成：MCP 默认 loopback、bearer gate 和 session/identity 分离已落地；细粒度授权仍待完成 | transport auth + client authorization policy | session ID 不作为身份，客户端只能访问允许的工具、scope、任务和数据 |
| A-09 | P0 | CORS/Origin/CSRF 与 URL token 收口 | origin/request credential policy | 非 allowlist 来源被拒绝，修改类请求防跨站，query token 仅限必要 SSE 路由且避免泄漏 |
| A-10 | P0 | ✅ Docker build context 收口 | 完整 `.dockerignore` policy | 本地产物不进入构建 |
| A-11 | P1 | 关键 event 不可静默 drop | priority queue/backpressure | terminal/proof event 0 丢失 |
| A-12 | P1 | 健康端点真实化 | liveness/readiness/dependency view | runtime/provider 状态准确 |

### 13.3 Phase B：质量与可复现工程

| ID | 优先级 | 工作项 | 预期产物 | 验收目标 |
|---|---|---|---|---|
| B-01 | P1 | ✅ Ruff/Black 改为阻断（changed-files gate） | CI hard gate | 修改范围 0 错误 |
| B-02 | P1 | ✅ import-linter 进入 CI | architecture gate | 新违规为 0 |
| B-03 | P1 | Domain/Ports/Application 类型严格化 | staged mypy config | 核心公共 API 无 Any 泄漏 |
| B-04 | P1 | 密钥与依赖扫描 | secret + dependency gate | 高危阻断 |
| B-05 | P1 | 容器/SBOM/provenance 扫描 | release supply-chain job | 发布产物可追溯 |
| B-06 | P1 | 🔨 版本单一真相源（代码侧已单源；release tag/CHANGELOG 待发布流程收口） | generated/read version adapters | 0.2/0.4 漂移消失 |
| B-07 | P1 | 依赖声明与锁定统一 | canonical dependency manifest | 构建可复现 |
| B-08 | P1 | Python/OS/runtime 支持矩阵 | support policy | CI/Docker/文档一致 |
| B-09 | P2 | 复杂度和增长预算 | hotspot guard | 超大模块不再无界增长 |
| B-10 | P2 | broad catch 例外治理 | exception taxonomy/report | 新 silent catch 为 0 |
| B-11 | P2 | 编码、BOM、warning 清理 | source hygiene gate | parse warning 为 0 |
| B-12 | P2 | 大型测试模块按边界拆分计划 | test ownership map | 降低冲突和审阅成本 |
| B-13 | P2 | 源码注释与测试 docstring 去私有记忆依赖 | self-contained source rationale | 代码和测试中的不可解析 wiki-style `project_*` / `feedback_*` / `reference_*` 引用为 0；必要依据改指向 ADR、issue、commit 或仓库文档 |

### 13.4 Phase C：数据与状态可靠性

| ID | 优先级 | 工作项 | 预期产物 | 验收目标 |
|---|---|---|---|---|
| C-01 | P1 | Schema Registry | schema catalog | 所有 active schema 有 owner |
| C-02 | P1 | 统一原子文件写 adapter | state store port/adapter | 崩溃不产生半文件 |
| C-03 | P1 | Single-writer 或事务存储决策 | ADR + implementation boundary | 多线程/多进程语义明确 |
| C-04 | P1 | Ledger/checkpoint checksum 与 sequence | durable append contract | 尾部损坏可检测恢复 |
| C-05 | P1 | ID、UTC、monotonic 统一 | identity/time service | 时序关联一致 |
| C-06 | P1 | Migration/rollback framework | migration registry | 新旧数据可控升级 |
| C-07 | P1 | Retention 与磁盘配额 | lifecycle policy | 磁盘不会无限增长 |
| C-08 | P1 | 备份与 restore drill | backup runbook | 达到 RTO/RPO |
| C-09 | P2 | Read model 可重建 | projection rebuild service | projection 损坏可恢复 |
| C-10 | P2 | Artifact manifest 统一 | artifact service | 原始/派生物可追溯 |
| C-11 | P2 | Config schema/catalog | typed config registry | 167 项配置有生命周期 |
| C-12 | P2 | Compatibility shim 台账 | deprecation dashboard | 兼容债可退出 |

### 13.5 Phase D：真实解题率

| ID | 优先级 | 工作项 | 预期产物 | 验收目标 |
|---|---|---|---|---|
| D-01 | P1 | 固化 16 题 run manifest | versioned corpus | 每题可复现 |
| D-02 | P1 | Judge 只消费 proof/receipt | proof-aware judge | false success 为 0 |
| D-03 | P1 | 冷暖隔离完善 | isolated runner | memory/cache 不泄漏 |
| D-04 | P1 | Strategy reachability 持续门禁 | reachability matrix | 100% 可达 |
| D-05 | P2 | 按失败 taxonomy 聚类 | failure dashboard | backlog 数据驱动 |
| D-06 | P2 | T0/T1 发布门槛 | release capability gate | T0 100%、T1 达阶段目标 |
| D-07 | P2 | Strategy outcome telemetry | strategy scorecard | 能计算真实贡献 |
| D-08 | P2 | Extraction checkpoint | resumable extraction | 长链可恢复 |
| D-09 | P2 | Runtime capability parity | profile matrix | 降级原因明确 |
| D-10 | P2 | 非 Web artifact workflow | structured domain receipts | T3 能力可诊断 |
| D-11 | P2 | Honest stop 质量 | stop reason taxonomy | T3 不伪成功 |
| D-12 | P3 | 新策略准入规则 | strategy admission policy | 新能力有增量证据 |

### 13.6 Phase E：运维与安全产品化

| ID | 优先级 | 工作项 | 预期产物 | 验收目标 |
|---|---|---|---|---|
| E-01 | P1 | 结构化日志与统一 IDs | logging schema | 可跨组件关联 |
| E-02 | P1 | SLO/alert 定义 | operations dashboard | 关键故障可发现 |
| E-03 | P1 | Secret store 与 rotation | secret operations | `.env` 不承担远程生产密钥 |
| E-04 | P1 | Remote RBAC/tenant isolation | authorization service | 数据和任务隔离 |
| E-05 | P1 | Incident runbooks | response handbook | Sev-1/2 可执行响应 |
| E-06 | P1 | Graceful shutdown | drain/cleanup lifecycle | 退出无遗留任务 |
| E-07 | P2 | 容量与 quota | resource policy | 超限可控降级 |
| E-08 | P2 | Event/SSE cursor 与重连 | reliable event stream | 慢客户端不丢关键事实 |
| E-09 | P2 | Release/rollback 收口 | single release handbook | 发布可回滚 |
| E-10 | P2 | Support bundle 脱敏 | diagnostic export | 可安全诊断 |

### 13.7 Phase F：性能与生态

| ID | 优先级 | 工作项 | 预期产物 | 验收目标 |
|---|---|---|---|---|
| F-01 | P2 | 单位成功成本仪表盘 | cost per verified solve | 可按模型/策略比较 |
| F-02 | P2 | Model router 数据化 | route policy | 成本下降且解题率不退化 |
| F-03 | P2 | Tool/cache correctness | cache contract | 无陈旧结果污染 |
| F-04 | P2 | Crew ROI gate | concurrency policy | 并发有净收益 |
| F-05 | P3 | RAG 增量索引和贡献度 | retrieval telemetry | 命中与实际贡献可区分 |
| F-06 | P3 | Plugin manifest/permission | plugin SDK policy | 第三方扩展可控 |
| F-07 | P3 | Runtime node pool | scheduler adapter | 扩容不破坏隔离 |
| F-08 | P3 | UI 大数据量优化 | paged read models | 长任务稳定展示 |

### 13.8 依赖关系

- A-01/A-02 是 Web、MCP、Crew 取消优化的前置。
- A-05 是 metrics、report、baseline 和自动提交可信度的前置。
- B-06/B-07 是可复现构建和 release 的前置。
- C-01/C-02/C-03 是 checkpoint、memory、task store 和多进程部署的前置。
- D-01/D-02/D-03 是所有解题率优化的前置。
- E-03/E-04 是远程长期服务的前置。
- F 阶段不得绕过 A–E 的事实、安全和运行约束。

### 13.9 建议的当前执行顺序

1. A-01 至 A-10。
2. B-01、B-02、B-06、B-07。
3. C-01、C-02、C-03、C-05。
4. D-01 至 D-06。
5. E-01 至 E-06。
6. 其余 P2/P3 按 baseline、事故和成本数据排序。

---

## 14. 单次优化工作的标准流程

### 14.1 Definition of Ready

开始实现前必须具备：

- 明确的问题陈述，不使用“代码太乱”“性能不好”这类无法验证的描述。
- 当前运行/配置/代码证据。
- 受影响入口、模块、数据和 runtime。
- 当前行为与目标行为。
- 风险等级和回滚策略。
- 成功指标与失败指标。
- 是否涉及 schema、配置、权限、proof、兼容和数据迁移。

### 14.2 优化任务卡字段

每个任务至少记录：

| 字段 | 内容 |
|---|---|
| Objective | 要改善的用户/系统结果 |
| Evidence | 当前问题的决定性证据 |
| Scope | 修改范围和明确非目标 |
| Invariants | 不能破坏的规则 |
| Contract | 输入、输出、错误、状态和版本 |
| Owner | 负责模块和审阅人 |
| Risk | 安全、数据、兼容、运行风险 |
| Observability | 上线后如何知道有效/失效 |
| Rollback | 触发条件和恢复动作 |
| Exit Criteria | 可量化完成条件 |
| Docs | 需要更新的权威文档 |

### 14.3 实施步骤

1. 从 live/runtime 或最接近运行的证据确认问题。
2. 追溯到最早不确定阶段，不横向扩大搜索。
3. 选择最小端到端切片。
4. 明确 contract、状态 owner、error taxonomy 和 trace。
5. 先增加观测或 guard，再切换行为。
6. 一次只改变一个核心变量。
7. 保持旧路径可回退，但设置兼容期限。
8. 验证目标指标、负面指标和资源清理。
9. 更新治理指南状态/backlog、ADR、schema registry 或 baseline。
10. 观察稳定窗口后移除旧路径和临时开关。

### 14.4 Definition of Done

一个优化项完成应满足：

- 目标行为已在所有受影响入口一致实现。
- typed contract、error、state 和 version 清晰。
- proof、scope、audit 和 cancellation 不变量未被削弱。
- 质量门禁通过，无新增未记录债务。
- 指标能证明预期效果，且无明显负面回归。
- 数据迁移和回滚已验证。
- 新增 feature flag 有退出计划。
- 文档和配置说明已同步。
- 旧路径已删除，或有明确移除日期/条件。

本文不提供具体测试实现；实际开发必须按风险选择相应验证方式。

### 14.5 变更粒度

- 一个提交只表达一个可审阅逻辑单元。
- 架构抽取、行为改变、schema migration、格式化不要混在同一提交。
- 大模块拆分先保证 import/patch/public surface，再迁移行为。
- 高风险迁移使用 adapter、shadow read、dual read 或 feature flag，但设置收口条件。
- 不借任务删除或改写无关用户改动。

### 14.6 Review 重点

审阅顺序建议：

1. 是否解决了真实问题。
2. 是否破坏 proof、scope、状态或取消语义。
3. 状态 owner 和依赖方向是否正确。
4. 失败、超时、恢复和回滚是否完整。
5. 数据/schema/配置是否可兼容。
6. 是否可观测、可运营。
7. 代码复杂度和命名是否合理。

### 14.7 风险接受

暂时无法修复的风险必须记录：

- 风险描述和影响范围。
- 证据和触发条件。
- 当前缓解措施。
- 监控和告警。
- owner、review date、到期日。
- 不能接受时的停用/降级方案。

---

## 15. 文档收口与维护规则

### 15.1 单一入口原则

今后综合优化只维护本文件：

`docs/optimization-guide.md`

不再创建：

- `<project>_优化方案_<date>_Vn.md`
- `<project>_优化方法论_<date>_Vn.md`
- 按具体 coding agent、模型或 provider 命名的项目级说明、记忆或路线文档。
- 与本指南重复的综合 roadmap、gap report 或“最新审计”文件。

版本、日期和状态只更新在本文件头部和变更记录中。仓库级协作约束统一维护在 `AGENTS.md`；具体品牌名称仅用于真实 provider 兼容、客户端接入或历史证据，不承担项目身份和治理入口职责。源码注释、测试 docstring 和文档中的设计依据也必须在仓库内可追溯，应指向 ADR、issue、commit、稳定代码契约或现有仓库文档，不得依赖某个开发工具的私有会话记忆。

### 15.2 建议保留的权威文档层级

| 层级 | 文档 | 作用 |
|---|---|---|
| 产品入口 | `README.md` | 项目定位、快速开始、当前稳定能力 |
| 协作约束 | `AGENTS.md` | 仓库结构、开发纪律、架构不变量 |
| 文档导航 | `docs/README.md` | 少量权威入口和历史分类 |
| 综合优化 | 本文件 | 当前问题、优先级、路线、运维和质量指南 |
| 架构规范 | Clean Architecture Guidelines + Naming Policy | 稳定边界规则 |
| 能力事实 | 真实解题率 baseline/corpus 报告 | 当前能力数据 |
| 发布规范 | 未来合并后的单一 Release Handbook | 发布和回滚 |

### 15.3 历史文档处理

以下文档类型保留为历史证据，但不作为当前优先级真相源：

- 旧 Solver Spec、Gap Report、Implementation Roadmap。
- 旧架构学习笔记、阶段优化方案、结构债快照。
- 已完成 migration playbook 的逐提交日志。
- 单题 WP、阶段验收记录和 benchmark 过程报告。

建议后续文档清理只做：

1. 增加 `Status: Historical/Superseded` 和被谁取代。
2. 移入清晰的 archive/history 分类目录，保留 Git 历史。
3. 修复当前权威文档的链接。
4. 不为“整理”重写历史事实。

### 15.4 文档更新触发器

| 变化 | 必须更新 |
|---|---|
| 优先级、阶段、SLO、风险变化 | 本指南 |
| 项目定位、稳定功能、安装方式变化 | README |
| 架构不变量和公共命名变化 | AGENTS + Architecture Guidelines/ADR |
| claim/evidence/proof schema 变化 | Schema Registry + 相关 contract 文档 |
| baseline corpus/judge/结果变化 | baseline 文档和报告 |
| 发布、升级、回滚变化 | Release Handbook |
| 文档状态和入口变化 | docs/README |

### 15.5 文档质量门槛

- 每份 Active 文档有 owner、status、last reviewed。
- 所有路径和版本引用可自动检查。
- 当前事实优先引用运行证据和活跃代码。
- 计划项必须有 owner、优先级、完成条件和状态。
- 重复内容优先链接，不复制粘贴。
- 文档不保存密钥、cookie、真实凭据或不必要的运行敏感信息。

### 15.6 本指南的维护方式

- 小变化直接更新对应章节。
- 重大决策新增 ADR，并在本指南更新结论和链接。
- 完成 backlog 时修改状态，不复制一份“完成版”。
- 每个 minor release 做一次全文 review。
- 每季度清理已完成、失效和重复条目。

---

## 16. 目标状态画像

完成主要优化后，FlagHunter 应达到以下状态：

### 16.1 对操作者

- 任意入口展示相同任务状态和 proof。
- 停止就是实际停止，不存在后台继续执行。
- 失败原因、剩余预算、依赖状态和下一步清晰可见。
- 远程控制面默认安全，权限和审计明确。
- 数据、报告和 artifact 可查、可导出、可删除、可恢复。

### 16.2 对开发者

- 新功能沿 contract → use case → port → adapter → composition root 开发。
- 质量、类型、架构、安全和依赖检查在合并前自动反馈。
- 高风险模块有清晰 owner 和增长预算。
- 兼容 shim 和 feature flag 有退出路径。
- 当前路线只看一份优化与治理指南，不在数十份旧文档中猜优先级。

### 16.3 对系统

- verified proof 是唯一解题成功权威。
- task lifecycle、cancellation、budget 和 recovery 可组合、可追踪。
- runtime、tools、MCP、Crew 均通过稳定 ports 和 receipts 接入。
- 持久化可抗并发和崩溃，schema 可迁移。
- observability 能解释每次成功、失败、成本和资源使用。
- 真实解题率按层级稳定提升，诚实终止不被当失败掩盖。

### 16.4 对运维

- profile、支持矩阵、健康检查、SLO、告警和 runbook 完整。
- 构建可复现，镜像有 SBOM、扫描和签名。
- secret、backup、restore、retention、quota 和 rollback 可执行。
- 单机、容器、SSH 和远程 MCP/Web 的风险边界清晰。

---

## 17. 当前决策摘要

### 17.1 立即执行

1. 真实 cancellation 和 terminal state。
2. Web/MCP 远程控制面安全。
3. proof-aware success/metrics/report。
4. Docker build context 和 secret/artifact 排除。
5. CI 硬门禁、version/dependency 单源。
6. 原子持久化、schema/config registry。

### 17.2 随后执行

1. 用 baseline failure cluster 提升 T0/T1/T2。
2. 拆解高 churn 超大模块，但保持 public/patch surface。
3. 统一 runtime capability、tool receipt 和错误 taxonomy。
4. 建立完整 observability、SLO、alert、backup 和 incident runbook。
5. 以单位 verified solve 成本优化模型、RAG、缓存和 Crew。

### 17.3 长期坚持

- 先证据，后能力。
- 先运行真相，后源码推断。
- 先可达性，后策略深度。
- 先最短闭环，后广度扩展。
- 先可信终态，后体验指标。
- 先单体纪律，后 Crew 放大。
- 先稳定 contract，后生态扩展。
- 一个主题只保留一个 Active/Canonical 文档。

---

## 附录 A：本次审计的主要证据位置

| 领域 | 证据位置 |
|---|---|
| 项目版本和依赖 | `pyproject.toml`、`flaghunter/config/constants.py` |
| README 版本和能力状态 | `README.md` |
| 发布记录 | `CHANGELOG.md`、`docs/release-*` |
| CI 与 coverage | `.github/workflows/tests.yml`、`pyproject.toml` |
| 架构约束 | `.importlinter`、`flaghunter/domain/`、`application/`、`ports/`、`adapters/` |
| 任务装配 | `flaghunter/session/`、`flaghunter/interface/initializer.py` |
| Agent loop | `flaghunter/agents/base_agent.py` |
| Dispatcher/Coordinator | `flaghunter/agents/pa_agent/ctf_dispatcher.py`、`coordinator.py` |
| Strategy/Capability | `strategy_registry.py`、`capability_registry.py` |
| Claim/Proof | `flaghunter/domain/challenge/contracts/`、`verifier.py`、proof adapters |
| Tool control | `flaghunter/tools/executor.py`、`tool_guard.py`、M4 audit guard |
| Runtime | `flaghunter/runtime/` |
| MCP | `flaghunter/mcp/`、`flaghunter/mcp/server/` |
| Web control plane | `flaghunter/interface/web_server.py`、`web_settings_io.py`、`web_settings_routes.py` |
| Observability | `flaghunter/observability.py`、session ledger、tool provenance |
| Persistence | `flaghunter/harness/`、`session/session_store.py`、strategy memory、notes |
| Baseline | `flaghunter/eval/baseline/`、`flaghunter/eval/fixtures/` |
| Container | `Dockerfile`、`Dockerfile.kali`、`docker-compose.yml`、`.dockerignore` |
| 文档入口 | `docs/README.md` |

---

## 附录 B：优化评审检查表

### 问题真实性

- [ ] 是否有当前运行、配置或代码证据。
- [ ] 是否排除陈旧文档和 dead code 的误导。
- [ ] 是否定位到最早不确定阶段。

### 架构

- [ ] 依赖方向是否正确。
- [ ] 状态 owner 是否唯一。
- [ ] 公共命名是否中立。
- [ ] 是否新增永久兼容债。

### 可信度

- [ ] 是否绕过 verifier/proof authority。
- [ ] success/stop/fail/cancel 是否与真实行为一致。
- [ ] evidence、receipt、trace 是否可关联。

### 安全

- [ ] scope 是否覆盖所有派生目标。
- [ ] 权限、鉴权和审计是否完整。
- [ ] secret 和 artifact 是否正确分类/脱敏。
- [ ] untrusted content 是否只作为数据处理。

### 可靠性

- [ ] timeout/cancel 是否传播到底层资源。
- [ ] cleanup 失败是否可见。
- [ ] 持久化是否原子、并发安全、可恢复。
- [ ] retry 是否幂等。

### 运维

- [ ] health、metrics、logs、trace 是否覆盖新行为。
- [ ] SLO、alert、quota、retention 是否需要更新。
- [ ] 发布、迁移和回滚是否明确。

### 效果

- [ ] 是否定义正向指标。
- [ ] 是否定义负面指标。
- [ ] 是否能与相同 baseline 对比。
- [ ] 是否说明预期收益和成本。

### 文档

- [ ] 是否更新唯一权威文档。
- [ ] 是否避免新增重复规划文档。
- [ ] 历史资料是否保持历史状态而未被改写。

---

## 附录 C：变更记录

| 版本 | 日期 | 变化 |
|---|---|---|
| V2.0 | 2026-07-31 | 合并原优化方法论，加入当前仓库静态审计、完整功能域、代码质量、运维、安全、数据、成本、遗漏项、阶段 backlog 和文档收口规则；改用稳定文件名作为唯一综合优化总纲。 |
| V2.1 | 2026-07-31 | 记录首批实施进展：✅ A-10/F-06（Docker build context 收口 + guard 测试）、✅ A-06/F-05（MCP metrics proof-backed success，done 与 solve 分离）、🔨 B-06/F-10（代码侧版本单源解析，release tag/CHANGELOG 待发布流程收口）。均含守护测试、零回归。 |
| V2.2 | 2026-07-31 | ✅ A-05：Web 控制面 `_run_agent_task` 曾以 flag 字符串存在性 + 正则重扫模型输出判定成功，会把 dispatcher 近解候选（`SolveResult.flag` 而 `success=False`）或裸正则命中伪装成 verified 成功。引入 `_resolve_terminal_outcome` 单一 proof-backed 策略：仅 verifier 确认的 flag 记 success；未验证候选降级为 `candidateFlag`+`stopped`（`candidate_flag_unverified`/`no_flag_found`），不丢近解（§6.9）。5 guard 测试、295 interface passed 零回归。Web 假成功率→0。 |
| V2.3 | 2026-07-31 | ✅ B-01/B-02：CI 曾以 `continue-on-error` 跑 ruff/black（lint/format 回归永不阻断），`.importlinter` 契约仅经 pytest 间接强制。B-01 新增 `lint-changed` 阻断 job——对本次 push/PR 实际改动的 `flaghunter/*.py`（diff vs base）跑 ruff+black，分阶段落地（修改范围 0 错误·遗留全树保留 advisory `lint` job 作 backlog）；B-02 新增 `import-linter` 阻断 job（`lint-imports --config .importlinter`）作专用架构门禁。`test_ci_quality_gates.py` 锁住"changed-files ruff/black 阻断 + lint-imports 阻断 + 全树 job 仍 advisory（防未验证大爆炸翻转）"。本机 ruff/black 因 TLS 拦截代理无法安装，故全树未预清零，采用 changed-files 方案；import-linter 契约本机 CLI 退出 0 + pytest guard `all_kept=True` 已证 KEPT。8 guard passed。 |
| V2.4 | 2026-07-31 | 记录 A-07/A-08 基础认证批次：新增统一 remote-access policy；Web 和 MCP 非 loopback 绑定无 token 时 fail-closed；MCP SSE 默认从 `0.0.0.0` 收回 `127.0.0.1`；`/mcp` 网络请求执行 bearer gate，session ID 只用于关联。静态复核将两项判为“基础认证完成、整体部分完成”，因为 RBAC、action/resource/tenant 授权、TLS、token 生命周期和配额仍未闭环；Web 还存在任意 Origin 和 query token 适用范围过宽的问题，统一归入 A-09。 |
| V2.5 | 2026-07-31 | 记录 A-01/A-02 基础契约批次：`task_lifecycle.py` 已提供 canonical 状态、dialect 映射和 transition service；`cancellation.py` 已提供 token、父子 scope 和 registry。静态复核没有发现已提交生产入口消费 lifecycle API，也没有发现已提交生产代码消费 cancellation registry，因此两项均为“领域基础完成、生产接线未完成”，不能提前宣称“所有入口状态同义”或“取消后动作数为 0”。工作树中的 A-04 MCP 改动属于未提交草稿，单独标记为进行中且未验收。 |
| V2.6 | 2026-07-31 | 完成文档治理通用化：唯一综合入口固定为 `docs/optimization-guide.md`，仓库级协作入口固定为 `AGENTS.md`；移除按具体 coding agent 命名的项目说明、启动配置、重复旧总纲和 Markdown 中的仓库外私有记忆引用，保留真实 provider、MCP 客户端、兼容 adapter 与历史研究语境。同步 README/AGENTS 的 MCP 默认 loopback 与远程 token 事实；修正 F-02/F-03/F-04/F-07/F-09、Phase A/B 状态和质量门禁说明。另识别出源码注释/测试 docstring 中 20 处同类外部引用，因本轮只改文档未动代码，登记为 F-19/B-13。此轮只做静态文档复核，没有运行测试、lint、build 或 live 任务。 |
| V2.7 | 2026-07-31 | ✅ A-03/A-04：stop/cancel 此前只改状态字段并落盘·后台 daemon thread(Web)与 CTF dispatcher 长 await(MCP)不受句柄控制→操作者见 stopped/cancelled 后工具仍可能继续跑(F-01/F-02)。消费 A-02 registry 落地真中止：**A-04(MCP)**=`run_task_async` 原 `asyncio.create_task` 丢弃句柄→存入 `_task_handles`·`_drive_task` 起时 open scope、finally pop 句柄+close scope·`cancel_task` 先置协作 status 再 latch token(“user_cancel”)再 `handle.cancel()`→泊在 dispatcher 长 await 的后台任务经既有 `CancelledError` 路径及时 unwind(阻塞式 `run_task` 保持内联·其调用方本就在 await 结果)。**A-03(Web)**=task 跑在 daemon thread 自有 event loop(与 `/stop` 所在 aiohttp loop 异线程)→managed task runner：`_run_agent_task` 把协程作具名 asyncio task 驱动·`_register_task_runner((loop,handle))`·`_cancel_web_task` latch token 后经 `loop.call_soon_threadsafe(handle.cancel)` 跨线程调度真取消·新增 `CancelledError` 臂记诚实 `stopped` 终态(带 token reason·不计解题失败)·`stop_task` 先 `_cancel_web_task` 再翻 UI status。测试=`test_mcp_task_cancellation.py`(4·泊 await 中断/token latch/未知 id/终态 no-op)+`test_web_task_cancellation.py`(3·跨线程 <5s 中断 vs 30s await/token latch/无 runner False)·434 interface/mcp/domain/layers 回归零退化·import-linter KEPT。**A-01/A-02/A-03/A-04 合计=§1.2 最优先第①件"停止/取消真实等价"闭环**。剩 timeout/success 等价见 A-05(✅)+超时轴(A-11/A-12 P1)。 |
| V2.8 | 2026-07-31 | ✅ A-09：Web 控制面此前对每个请求回 `Access-Control-Allow-Origin: *`→操作者访问的任意站点都能跨源脚本读控制台 API(F-05·A-07/A-08 的 token-header 鉴权正交但不挡浏览器跨源读)。新增纯 stdlib FOUNDATION origin 策略(`config/remote_access.py`)：loopback origin(本地控制台自身)默认可信 + 操作者 `FLAGHUNTER_WEB_ALLOWED_ORIGINS` allowlist·其余一律不可信。函数 `is_loopback_origin`/`resolve_allowed_origins`/`is_allowed_origin`/`origin_permitted_for_request`(CSRF 门：safe method 与无 Origin 的非浏览器客户端放行·带不可信 Origin 的写请求拒绝)·origin 规范化大小写/尾斜杠无关·`null`/裸 host 等畸形不可信。接入 Web：模块级通配 `cors_middleware`→`make_cors_middleware(allowed_origins)`——仅对可信 origin 回显 ACAO(绝不 `*`)+ `Vary: Origin` + credentials·带不可信 Origin 的状态改写在触及 handler 前 403(在 auth middleware 外层)·SSE StreamResponse 自决 CORS 头(middleware 无法改已 prepare 的流)。验收(A-09 非 allowlist 来源被拒绝)由端到端 middleware 测试钉死(通配从不出现/不可信 origin 无 grant/不可信写 →403/loopback 与无 Origin 放行)。9 policy + 6 web 测试·557 interface/config/mcp/domain 回归零退化·import-linter KEPT(domain/config 纯净)。**A-09 收官=Phase A P0 全清(A-01..A-10 全 ✅)**；§1.2 最优先第②件"Web/MCP 远程控制面鉴权/授权"三支(A-07 token + A-08 token + A-09 origin/CSRF)闭环。 |
| V2.9 | 2026-07-31 | ✅ B-07(F-11)：依赖同存 `pyproject.toml`+`requirements.txt`+`requirements-local-tools.txt` 且无锁文件——`requirements.txt` 已漂移成只声明 `jinja2` 而 pyproject 声明 24 包→构建不可复现、回滚/漏洞定位难。**pyproject.toml `[project.dependencies]` 定为唯一真相源**(两个 Dockerfile 本就 `pip install -e ".[rag]"` 从 pyproject 装→canonical 已喂构建)。新增 `scripts/lock_dependencies.py`：从 pyproject 派生两下游文件——`requirements.txt`(canonical specifier 的**生成镜像**·带 do-not-edit banner·修复漂移·`pip install -r` 路径现与 pyproject 一致)+ `requirements.lock`(**可复现锁**=全传递运行时闭包的精确 `==` pin·经 `importlib.metadata` walk `Requires-Dist`·marker 本地求值排除 extras·76 包)；`--check` 校验新鲜度不重写。lock header 诚实标注可复现范围=生成时的解释器/OS(marker 本地求值·跨平台 universal lock + hash pin 归 B-05 release 供应链后续·本机 TLS 代理挡 clean network resolve 故不做)。guard=`test_dependency_manifest.py`(7·requirements.txt 逐字节等于 canonical render 防漂移/lock 全精确 pin 无 `>=`/lock 覆盖每个顶层 dep + 含传递闭包/banner 存在)·146 config/dockerignore/version 回归零退化·import-linter KEPT。**残留**=`requirements-local-tools.txt` 仍手维护(localtools profile·非核心运行时·可后续纳入生成)+ hash-level pin 与 base image digest pin(B-05)。 |
| V2.10 | 2026-08-03 | ✅ 质量门禁 + 验收证据框架(为 B 阶段后续各项提供可执行验收基础)：新增 `flaghunter/quality/acceptance.py`(执行门禁·解析 backlog·匹配证据·原子写报告)+ `flaghunter/quality/__init__.py` 公共入口；新增 `quality-gates.json`(25 个门禁 × 67 个验收规则全映射 = Phase A/B/C/D/E/F 全部 backlog 都有 owner + (gates 或 evidenceRequirements))，由 `scripts/build_quality_gates.py` 单一真相派生；新增 `scripts/check_source_rationale.py`(B-13 私有记忆引用扫描)与 `scripts/run_changed_lint.py`(B-01/B-11 改文件 lint/format 阻断)；测试 `tests/unit/quality/test_acceptance.py`(12 · profile 未知门禁/重复 gate/coverage 与 guide 一致/失败门禁决定 exit code/缺失工具 UNAVAILABLE/changed-file 空集 SKIP/混合外部不传证据永远 PENDING/陈旧 evidence 不被接受/JSON+Markdown 报告原子写/仓内 manifest 覆盖 67 项)全过。`ruff check`/`black --check`/`isort` 干净。B-13 门禁首次扫描命中 22 处 [[project_*]]/[[feedback_*]]/[[reference_*]] 私有记忆引用——B-13 实际清理留作 B-13 实施(独立逻辑单元)；当前 manifest 把 B-13 标为 automated，验收状态为 PENDING 直到清理完成。**注意**：本机已有的 1 处 `test_attack_taxonomy.py::test_every_registered_strategy_is_tagged_or_exempt` 失败是 HEAD 残留(4 个 strategy kind 未打技术标签)，与本切片无关。 |
