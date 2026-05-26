# CTF Agent 多 Provider 韧性与多 Agent 协作 V1

> 适用范围：`pentestagent/llm/`、`cpa_modules/m1_api_hub/`、`pentestagent/agents/crew/`、`pentestagent/agents/pa_agent/`。
>
> 本文档解决两件事：
> 1. API 额度耗尽 / 网络抖动时的自动切换与恢复（M1 API Hub 已有基础设施，但**未在 pa_agent 主路径接入 FailoverMonitor**）
> 2. 单 agent 跑通后，如何把多 agent 并行能力（`agents/crew/`）真正用起来，而不是只停留在手册里
>
> 本文档与 `CTF_Agent_自由探索与LLM驱动兜底_V1.md` 配套，前者解决"单 agent 能力上限"，后者解决"系统韧性 + 多 agent 协作"。

---

## 1. Part A：多 Provider 韧性

### 1.1 当前现状

| 模块 | 状态 |
|---|---|
| `cpa_modules/m1_api_hub/provider_manager.py` | ✅ ProviderState 五态（HEALTHY/DEGRADED/DOWN/RECOVERING/DISABLED） |
| `cpa_modules/m1_api_hub/models.py::FallbackChain` | ✅ 降级链按 model_pattern 匹配，`get_next()` 可用 |
| `cpa_modules/m1_api_hub/failover_monitor.py::FailoverMonitor` | ✅ 已实现 health_check_loop + recovery_loop |
| `cpa_modules/m1_api_hub/cost_tracker.py` | ✅ RequestLog 记账 |
| `pentestagent/llm/llm.py::_call` | ✅ 已通过 `get_provider_manager().select_provider()` 拿当前 provider |
| **`pentestagent/llm/llm.py` 失败处理** | ❌ **rate_limit 只走本地 backoff，不切换 provider** |
| **`FailoverMonitor.start_monitoring()` 在 pa_agent 启动时调用** | ❌ **无人启动，DOWN provider 永远不会自动恢复** |
| **provider 选择失败时的兜底** | ❌ **NoProviderAvailable 直接抛异常，agent 死掉** |

### 1.2 用户两个具体问题的答案

#### Q1：API 额度用完了，会不会自动切换？

**当前答案：不会。** 现在只对 rate_limit 错误做本地指数退避（`_retry_with_backoff` 最多 5 次），不切换 provider。配额耗尽通常返回 429 或 insufficient_quota，被识别为 rate_limit 后死循环重试。

**需要的改动**：
- `llm.py::_call` 接到 429 / insufficient_quota / context_length_exceeded 时，调用 `ProviderManager.mark_unavailable(current_id, reason)`
- ProviderManager 把当前 provider 状态置为 DOWN（或 DEGRADED，取决于错误类型）
- 重新走 `select_provider()` 拿降级链下一个 provider
- 重试当前请求

#### Q2：网络问题短时不可用，恢复后怎么识别？

**当前答案：FailoverMonitor 已实现 recovery_loop，但没人启动它。** `failover_monitor.py` 的 `_recovery_loop()` 会定期对 DOWN provider 发探测请求（间隔 `recovery_check_interval`，默认 60s），连续成功 `recovery_confirm_requests` 次（默认 2）后置回 HEALTHY。代码全在，但 pa_agent 主路径从不启动这个监控器。

**需要的改动**：
- pa_agent 启动时（`CTFCoordinator.__init__` 或 main 入口）实例化 FailoverMonitor 并 `await monitor.start_monitoring()`
- 退出时 `await monitor.stop_monitoring()` 优雅关闭
- TUI 增加 `/providers` 命令展示当前各 provider 状态

### 1.3 错误分类与状态转换规则

| LLM 调用错误 | 错误类型 | provider 状态转换 | 重试策略 |
|---|---|---|---|
| 429 rate_limit（短时） | TRANSIENT | HEALTHY → DEGRADED | 本地 backoff 2 次 → 仍失败则切换 |
| 429 insufficient_quota / billing | PERMANENT_DAY | HEALTHY → DOWN (24h cooldown) | 立即切换 |
| 401 / 403 invalid_api_key | PERMANENT | HEALTHY → DISABLED | 立即切换，不再尝试 |
| network timeout / ConnectionError | TRANSIENT_NETWORK | consecutive_failures+1，达到阈值后 → DOWN | recovery_loop 接管 |
| 5xx server_error | TRANSIENT_REMOTE | consecutive_failures+1，达到阈值后 → DEGRADED | 立即切换 |
| context_length_exceeded | LOGIC | 不变（不是 provider 故障） | 不切换，向上抛错 |
| 其他未知错误 | UNKNOWN | consecutive_failures+1 | 本地 backoff 1 次 → 切换 |

**实现位置**：`llm.py` 新增 `_classify_error(exc) -> ErrorClass` 函数；`_call` 根据分类决定状态转换 + 重试策略。

### 1.4 配置示例（.env）

```bash
# 主 provider：OpenAI gpt-4o
CPA_M1_PROVIDER_OPENAI_ID=openai-primary
CPA_M1_PROVIDER_OPENAI_NAME=OpenAI GPT-4o
CPA_M1_PROVIDER_OPENAI_MODEL=gpt-4o
CPA_M1_PROVIDER_OPENAI_API_BASE=https://api.openai.com/v1
CPA_M1_PROVIDER_OPENAI_API_KEY=sk-...
CPA_M1_PROVIDER_OPENAI_PRIORITY=1

# 备 provider：Anthropic
CPA_M1_PROVIDER_ANTHROPIC_ID=anthropic-backup
CPA_M1_PROVIDER_ANTHROPIC_NAME=Anthropic Claude Sonnet
CPA_M1_PROVIDER_ANTHROPIC_MODEL=claude-sonnet-4-20250514
CPA_M1_PROVIDER_ANTHROPIC_API_BASE=https://api.anthropic.com
CPA_M1_PROVIDER_ANTHROPIC_API_KEY=sk-ant-...
CPA_M1_PROVIDER_ANTHROPIC_PRIORITY=2
CPA_M1_PROVIDER_ANTHROPIC_IS_BACKUP=true

# 第三备 provider：DeepSeek
CPA_M1_PROVIDER_DEEPSEEK_ID=deepseek-cheap
CPA_M1_PROVIDER_DEEPSEEK_NAME=DeepSeek Chat
CPA_M1_PROVIDER_DEEPSEEK_MODEL=deepseek-chat
CPA_M1_PROVIDER_DEEPSEEK_API_BASE=https://api.deepseek.com
CPA_M1_PROVIDER_DEEPSEEK_API_KEY=sk-...
CPA_M1_PROVIDER_DEEPSEEK_PRIORITY=3
CPA_M1_PROVIDER_DEEPSEEK_IS_BACKUP=true

# 降级链：所有 GPT-4 系列模型按下面顺序降级
CPA_M1_FALLBACK_1_PATTERN=gpt-4*
CPA_M1_FALLBACK_1_IDS=openai-primary,anthropic-backup,deepseek-cheap

# 健康检查
CPA_M1_HEALTH_CHECK_INTERVAL=30
CPA_M1_RECOVERY_CHECK_INTERVAL=60
CPA_M1_FAIL_THRESHOLD=3
CPA_M1_RECOVERY_CONFIRM_REQUESTS=2

# 预算
CPA_M1_DAILY_BUDGET_USD=5.00
CPA_M1_BUDGET_ALERT_THRESHOLD=0.8
```

### 1.5 Part A 实施步骤（按顺序）

| 步骤 | 文件 | 改动 | 验收 |
|---|---|---|---|
| A1 | `pentestagent/llm/llm.py` | 新增 `_classify_error(exc)` | 单测：6 类错误各识别正确 |
| A2 | `pentestagent/llm/llm.py::_call` | 接到 PERMANENT_*/DEGRADED 错误时 `mark_unavailable` + 切换 provider | 单测：模拟 429 quota，第二次请求走备份 provider |
| A3 | `pentestagent/agents/pa_agent/ctf_dispatcher.py::__init__` 或 main 入口 | 启动 FailoverMonitor | 集成测：DOWN provider 在 60s 内被 RECOVERING |
| A4 | `pentestagent/interface/cli.py` 或 tui | 增加 `/providers` 命令 | 手工：显示 5 态 emoji |
| A5 | `cpa_modules/m1_api_hub/cost_tracker.py` | budget 超限时阻断新请求 | 单测：budget 满后 select_provider 抛 BudgetExhausted |
| A6 | `pentestagent/agents/pa_agent/recovery.py` | 新增 `RecoveryDecision` action `wait_for_provider_recovery` | 集成测：所有 provider DOWN 时返回此 action |
| A7 | `.env.example` | 补全多 provider 配置示例 | 文档校对 |

---

## 2. Part B：多 Agent 协作

### 2.1 当前现状

| 模块 | 状态 |
|---|---|
| `pentestagent/agents/crew/orchestrator.py::CrewOrchestrator` | ✅ 已实现，通过 tool calls 管理 worker |
| `pentestagent/agents/crew/worker_pool.py::WorkerPool` | ✅ 已实现 |
| `pentestagent/agents/crew/swarm_bridge.py` | ✅ 桥接层存在 |
| `pentestagent/knowledge/graph.py::ShadowGraph` | ✅ 从 notes 推导策略 insights |
| **`CTFCoordinator` 与 `CrewOrchestrator` 集成** | ❌ **CTF 路径只走单 agent**（pa_agent/ctf_dispatcher） |
| **/ctf crew 入口** | ❌ **没有让 CTF 任务跑多 agent 的命令** |
| M1~M6 多 Agent 调度手册 | ✅ docs/dev/M1~M6_*.md 完整，**但未实现** |

### 2.2 多 Agent 在 CTF 场景的真正价值

不是为了"多就是好"，而是为了**并行减少端到端时间**：

| 角色 | 工作 | 并发数 |
|---|---|---|
| ReconWorker | 端点扫描 / 备份枚举 / robots.txt / sitemap.xml / .git | 2~3（按不同路径前缀分） |
| ExploitWorker | 跑某个特定 chain（sqli / xss / hash_guarded / unserialize） | 1~3（按假设排序） |
| LLMExplorerWorker | LLM-driven 自由探索（见 `CTF_Agent_自由探索与LLM驱动兜底_V1.md`） | 1 |
| VerifierWorker | 独立验证 candidate flag（不同 worker 写的 flag 互相校验） | 1 |
| Orchestrator | 协调 + ShadowGraph 汇总 + 决定终止 | 1 |

### 2.3 触发条件（什么时候启用多 agent）

**默认不启用**。以下三种条件之一才启用：

1. 用户显式使用 `/ctf crew <task>` 命令
2. 单 agent 第一轮 recon 后发现：
   - endpoints ≥ 10 → 启动 2 个 ReconWorker 并行枚举
   - 假设排序前 3 的 confidence 都 ≥ 0.4 且互不冲突 → 启动 ExploitWorker 并行试
3. 单 agent 触发 RecoveryDecision.action=`stagnant` 且 reranked 链 ≥ 2 时

### 2.4 与现有 CTFCoordinator 的集成方案

**不重写 CTFCoordinator，新增一个外层 CTFCrewCoordinator**：

```
CTFCrewCoordinator
├── 持有 CTFState（共享，唯一）
├── 持有 ProviderManager（共享）
├── 持有 ShadowGraph（共享）
├── ReconWorkers（独立 CTFCoordinator 实例，target_filter=不同前缀）
├── ExploitWorkers（独立 CTFCoordinator，假设范围被限定）
├── VerifierWorker（独立，只读其他 worker 的 candidate_flags）
└── 主循环：
    1. 派发 worker 任务
    2. 聚合 observations 到共享 CTFState
    3. ShadowGraph 更新
    4. 决定下一轮派发 or 终止
```

**关键约束**：
- 所有 worker 共享同一个 CTFState（通过 asyncio.Lock 保护）
- 所有 worker 共享同一个 Verifier（避免重复打 platform）
- 每个 worker 有独立的 LLM 实例但走同一 ProviderManager
- 每个 worker 的 tool 调用走同一 ToolGuard

### 2.5 共享状态写入规则

| 字段 | 谁可以写 | 冲突解决 |
|---|---|---|
| observations | 所有 worker | append-only，按 timestamp 排序 |
| candidate_flags | 所有 worker | 去重（按 value）；同一 value 多个 worker 写视为加强证据 |
| runtime_flags / verified_flags | 仅 Verifier | 其他 worker 写入抛异常 |
| rejected_flags | 仅 Verifier | 同上 |
| hypotheses | 仅 Orchestrator | worker 通过 propose_hypothesis(...) 请求，Orchestrator 决定是否纳入 |
| exploration_agenda | Orchestrator + ReconWorker | append-only |

### 2.6 Part B 实施步骤（按顺序）

| 步骤 | 文件 | 改动 | 验收 |
|---|---|---|---|
| B1 | `pentestagent/agents/pa_agent/ctf_state.py` | 增加 `acquire_write_lock()` / `release_write_lock()` 异步锁 | 并发单测：100 个并发 write 不丢数据 |
| B2 | `pentestagent/agents/pa_agent/ctf_crew_coordinator.py` (新建) | CTFCrewCoordinator 骨架 | 单测：能启动 3 个 worker + 收回结果 |
| B3 | `pentestagent/agents/crew/swarm_bridge.py` | 把 CTFCoordinator 包装成 worker | 单测：worker 完成后 state diff 正确 |
| B4 | `pentestagent/agents/pa_agent/ctf_crew_coordinator.py` | 派发规则（recon 并行 / exploit 并行） | 集成测：模拟两 endpoint 不同前缀，2 个 recon worker 并行完成 |
| B5 | `pentestagent/interface/cli.py` | 增加 `/ctf crew <task>` 命令 | 手工：启动后 TUI 显示多 worker progress |
| B6 | `pentestagent/agents/crew/orchestrator.py` 复用 | 接入 ShadowGraph 决定下一轮派发 | 集成测：第一轮 recon 后第二轮派发的 worker 任务体现 ShadowGraph 推荐 |
| B7 | 完整测试用例追加 CREW1~CREW6 | 见 §3 | 全部通过 |

### 2.7 终止条件

CTFCrewCoordinator 终止条件（任一满足）：

1. `state.verified_flags` 非空 → 成功终止
2. 所有 worker 都报告 stop / exhausted → 失败终止
3. 总耗时 > `crew_timeout_seconds`（默认 600s）→ 超时终止
4. 总 LLM 成本 > `crew_budget_usd`（从 Settings 读取）→ 预算终止
5. 用户 Esc 中断 → 用户终止

---

## 3. 完整测试用例（追加到 `CTF_Agent_完整测试用例集_V1.md`）

### 3.1 Provider 韧性用例

| 用例 | Given | When | Then |
|---|---|---|---|
| PROV1 | provider openai-primary HEALTHY，anthropic-backup HEALTHY | openai 返回 429 insufficient_quota | openai → DOWN, 第二次请求走 anthropic |
| PROV2 | provider openai DOWN，recovery_loop 运行中 | 模拟 openai 恢复响应 OK | 60s 内 openai → RECOVERING → HEALTHY，下次请求走回 openai |
| PROV3 | 所有 provider DOWN | LLM 调用 | RecoveryController 返回 wait_for_provider_recovery，不抛异常 |
| PROV4 | provider openai 返回 401 invalid_api_key | LLM 调用 | openai → DISABLED 永久禁用，不再尝试 |
| PROV5 | 日预算超限 | 新请求 | select_provider 抛 BudgetExhausted，UI 弹告警 |
| PROV6 | provider 网络抖动连续超时 3 次 | 第 4 次请求 | openai → DOWN（超过 fail_threshold），切换 |

### 3.2 多 Agent 协作用例

| 用例 | Given | When | Then |
|---|---|---|---|
| CREW1 | 主页 endpoints 含 /api/v1/* 和 /admin/* | 启动 2 个 ReconWorker，target_filter 各自前缀 | 两个 worker 并行完成，state.observations 含两组结果 |
| CREW2 | 假设排序前 3：sqli(0.6), xss(0.55), backup(0.45) | 启动 3 个 ExploitWorker | 三个并行执行；第一个产出 runtime flag 后其他 worker 收到 stop 信号 |
| CREW3 | Worker A 写 candidate_flag X，Worker B 也写 candidate_flag X | Verifier 处理 | 视为加强证据，confidence 升高 |
| CREW4 | Worker A 写 runtime_flag X，Worker B 写 runtime_flag Y | Verifier 处理 | 两个独立 candidate 各自走验证，不互相覆盖 |
| CREW5 | 100 个 worker 并发 add_observation | state.acquire_write_lock 保护 | 全部写入不丢数据，timestamp 单调 |
| CREW6 | 总耗时 > crew_timeout_seconds | 超时触发 | 所有 worker 收到 cancel，state 持久化已收集 observations |

### 3.3 门禁规则追加

| 改动 | 必须通过的用例 |
|---|---|
| 改 `llm.py` provider 切换逻辑 | PROV1 + PROV3 + PROV4 |
| 启动 FailoverMonitor | PROV2 + PROV6 |
| 改 cost_tracker budget 阻断 | PROV5 |
| 改 CTFState 共享锁 | CREW3 + CREW5 |
| 改 CTFCrewCoordinator | CREW1 + CREW2 + CREW6 |
| 改 Verifier 多源 candidate 处理 | CREW3 + CREW4 |

---

## 4. 与 `CTF_Agent_自由探索与LLM驱动兜底_V1.md` 的关系

| 文档 | 解决的问题 |
|---|---|
| 自由探索文档 | 单 agent 在未知题型上的能力上限 |
| 本文档 Part A | 系统韧性（API 故障不死） |
| 本文档 Part B | 端到端时延（并行加速） |

**依赖关系**：
- Part A 与自由探索文档**完全独立**，可并行实现
- Part B 必须**先完成自由探索文档 + Part A**，否则多 worker 也只能跑硬编码策略，并行无意义
- 推荐顺序：自由探索 + Part A 同时启动 → 都验收后 → Part B

---

## 5. 推荐落地节奏

### 5.1 第一周（不接多 agent，单 agent 先变强）

- 自由探索文档 §9 步骤 1~4
- 本文档 Part A 步骤 A1~A4

### 5.2 第二周（韧性 + 验收）

- 自由探索文档 §9 步骤 5~8
- 本文档 Part A 步骤 A5~A7
- 在 easy_tornado + 1 道全新题上验收单 agent + 韧性

### 5.3 第三周（多 agent 开局）

- 本文档 Part B 步骤 B1~B4
- 第一个端到端 crew 跑通

### 5.4 第四周（多 agent 完善 + 性能验收）

- 本文档 Part B 步骤 B5~B7
- 跑 3 道复杂题，对比单 agent 端到端时延

---

## 6. 验收完成标准（总）

### 6.1 韧性验收

- [ ] 关闭 openai-primary 的 API key（模拟额度耗尽），agent 自动切换到 anthropic-backup 完成当前任务，不报错
- [ ] 启动后 60s 内，DOWN provider 在网络恢复后被 recovery_loop 检测到并置回 HEALTHY
- [ ] `/providers` 命令显示 5 态 emoji 和当前请求数 / 累计成本
- [ ] 日预算超限时 UI 弹告警，新请求被 BudgetExhausted 阻断

### 6.2 多 Agent 验收

- [ ] `/ctf crew <task>` 命令可用，TUI 显示多 worker 并行 progress
- [ ] 在一道有 10+ endpoints 的题上，crew 模式端到端时延 < 单 agent 模式 60%
- [ ] CTFState 在 100 并发 write 下不丢数据
- [ ] Verifier 对多源 candidate flag 不重复打 platform

### 6.3 对比指标（vs codex 直跑）

| 指标 | codex 裸跑 | 本项目（自由探索 + 韧性 + crew） |
|---|---|---|
| 可复现性 | ❌ | ✅ 完整 session log + StopReport |
| 审计 | ❌ | ✅ 每步 PreActionReasoning Q1~Q4 |
| API 故障容错 | ❌ 单 provider 挂了就死 | ✅ 多 provider 自动切换 + 恢复 |
| 并行加速 | ❌ 单线程串行 | ✅ multi-worker 并行 |
| 跨题记忆 | ❌ | ✅ StrategyMemory |
| 新题型扩展 | ✅ LLM 自由发挥 | ✅ LLM-driven 兜底通道 |
| 成本控制 | ❌ | ✅ budget + cost_tracker |
| 验证闭环 | ❌ | ✅ Verifier 5 路径 |

**只要这张表打满 ✅，项目相对 codex 就有清晰的不可替代价值。**
