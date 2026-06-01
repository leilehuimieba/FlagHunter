# CTF Agent Phase 6 规划与主控决策 V1

> **文档性质**：主控架构师决策文档，供其他开发 agent 执行。  
> **写作时间**：Phase 0.5 live solve proof 完成之后、两个 dispatcher/hypothesis 核心 bug 修复之后。  
> **本文优先级高于之前所有 Phase 计划文档中尚未完成的部分。**

---

## §0 知识库建议的理性评判

本次基于 `D:\newwork\aiagentstudy` 知识库的 8 篇条目（BB-177/178/227/230/238/243/254/289）收到了一份外部建议。以下是本主控对该建议的逐条评判，评判结论直接影响下面的开发优先级决策。

### 0.1 高度认同、直接采纳

| 建议 | 认同理由 | 本文如何落地 |
|---|---|---|
| 优先补"评测层"(BB-178) | 947 个测试覆盖的是**组件正确性**，不是**解题成功率**。没有 replay eval，修一个 bug 之后不知道整体有没有进步 | Phase 6 核心任务 |
| 把 verifier 升级成 Proof-driven gate (BB-230/177) | verifier 现在能判对错，但判断过程不可解释、不可回溯。wrong-flag 反馈精度低 | Phase 6.5 核心任务 |
| 多 Agent 先冻结 (BB-177/230) | CTFCrewCoordinator 已建出来但无评测覆盖。没有 eval baseline 就扩 crew 只会把错误放大 | 明确冻结声明 §4 |
| 记忆需要分层 (BB-289) | strategy_memory 当前是 L2（策略模板），L1（原子事实）缺失，导致假设引擎只能靠模式匹配而非事实推断 | Phase 7（延后，条件见 §4） |

### 0.2 方向正确、范围收窄

| 建议 | 为什么要收窄 | 实际落地范围 |
|---|---|---|
| "收束成 CTF Harness" 并定义 5 个一级边界 | 这个框架已经**在实现层隐式存在**（CTFState/Verifier/HypothesisEngine/RecoveryController/StrategyMemory）。再做一轮概念重命名和文档重组性价比极低，会消耗 dev agent 大量 token | 不做代码重组；仅在本文明确哪个模块对应哪个边界 |
| 14 条评测指标 (BB-178) | BB-178 的指标框架来自 RAG/LLM 通用场景，大量指标（Context Relevance、Recall、Precision）对 CTF 解题完全无意义 | 重新定义 CTF 专属指标集（见 §1.3） |
| 工具元数据治理 | 方向正确，但当前没有任何 CTF 题失败是因为"工具元数据不足"导致选错工具。是真实痛点，但不是当前痛点 | 延至 Phase 8，不进入 Phase 6 |
| 可维护性传感器 (BB-243) | BB-243 的核心工具是 ESLint，本项目是 Python。代码质量当前已有 ruff/black/947 tests 保障。文章提出的"agent 特定传感器"（source-only bypass 检测等）有价值，但优先级低于 eval 和 proof | 延至 Phase 8 |

### 0.3 暂不采纳

| 建议 | 原因 |
|---|---|
| L0-L3 全层内存重构（L0 原始过程层、L3 平台画像层） | L0 已散在 `conversations/`/`logs/`/`loot/`，L3 已有 platform profile。全层重构会影响 dispatcher 主路径，在没有 eval baseline 的情况下变更风险极高。等 Phase 6 eval 建立之后再决策 |
| strategy_memory 立刻升级（L1 原子事实层） | 同上：改记忆模型前必须先有能衡量影响的指标面板，否则无法判断改了之后是进步还是退步 |

### 0.4 主控结论

> **知识库建议的方向总体正确，但边界太宽、范围太大、缺乏执行顺序依据。**  
> 真正的执行顺序应该是：**先建 eval（能量变化），再改机制（使结果变好），再扩能力（让更多题可解）。**  
> 当前没有 eval，所有后续改动都是在黑暗中摸索。

---

## §1 Phase 6：Replay Eval Harness（最高优先级）

### 1.1 为什么是 P1

- 我们刚修了两个 dispatcher/hypothesis bug，但没有办法量化"修完之后整体解题率有没有提升"。
- 我们有 easy_tornado 单题 acceptance test，但不知道改这道题是否会破坏其他类型题。
- 没有 eval 就无法做 A/B 对比（改模型 / 改 prompt / 改 strategy 之后效果如何）。
- eval 建好之后，**后续所有改动都必须在 eval 上先跑，不能降指标才能合入**。

### 1.2 任务边界

| | 描述 |
|---|---|
| 入口文件 | 新建 `tests/eval/benchmark_runner.py` |
| 依赖 | 现有 mock 服务器（integration tests 里已有 4 个），不依赖真实网络 |
| 禁止范围 | 不改任何 agent 代码；不新增外部依赖；不连接真实 CTF 平台 |

### 1.3 CTF 专属指标集（替代 BB-178 通用指标）

以下 9 个指标是 CTF 解题场景专属的。每个指标都可以从现有 `CTFState` + mock server 录制数据中计算，不需要额外外部工具。

#### A. 解题成功率指标（最重要）

```
solve_rate              = verified_flags / total_challenges
wrong_flag_rate         = wrong_flag_submissions / total_flag_submit_attempts
premature_stop_rate     = stopped_without_flag / total_challenges  
                          （分子：agent 停止时 state.verified_flags 为空）
```

#### B. 路径效率指标

```
avg_chains_to_solve     = sum(chain_iterations_used) / solved_challenges
source_only_false_stop  = 次数：candidate_flag 触发停止但 runtime_flag 为空
                          （表示 source-only 误判成 verified）
hypothesis_first_hit    = 第一个 active_hypothesis 就拿到 flag 的比例
```

#### C. 恢复能力指标

```
recovery_after_wrong    = wrong flag 之后成功恢复并最终 solve 的比例
hypothesis_exhaustion_rate = 被标记 exhausted 的假设 / 生成的假设总数
                             （过高说明 exhaustion 太激进）
no_progress_stop_rate   = 因 stop_no_progress 停止的比例
                          （过高说明 agenda / chain 策略不够）
```

### 1.4 Benchmark Corpus（题目列表）

以下 mock challenges 来自现有 integration tests，可直接复用其 server fixture：

| challenge_id | 类型 | mock 来源 | 预期 solve |
|---|---|---|---|
| `easy_tornado` | web/hash-ssti | `test_ctf_dispatcher_easy_tornado_acceptance.py::easy_tornado_server` | True |
| `php_backup` | web/backup-leak | `test_ctf_dispatcher_backup_acceptance.py::php_backup_server` | True |
| `php_unserialize` | web/php-object | `test_ctf_dispatcher_php_object_injection_acceptance.py` | True |
| `stored_xss` | web/xss | `test_ctf_dispatcher_acceptance.py` | True |
| `auth_sqli` | web/sqli | `test_ctf_dispatcher_acceptance.py` | True |

注：第一版 benchmark 只用已有 mock server，**不新建 mock challenge**。新 mock 进 Phase 6 之后的迭代。

### 1.5 输出格式

```python
# tests/eval/benchmark_result.py

@dataclass
class ChallengeResult:
    challenge_id: str
    solved: bool
    wrong_flag_count: int       # 提交错误 flag 次数
    chain_iterations: int       # 用了几轮 chain
    stop_reason: str            # state.stop_reason
    has_source_only_stop: bool  # candidate_flag 存在但无 runtime_flag 时停止
    hypothesis_exhausted_count: int
    wall_time_seconds: float

@dataclass  
class BenchmarkReport:
    run_id: str
    timestamp: str
    git_sha: str
    results: list[ChallengeResult]
    # 聚合指标
    solve_rate: float
    wrong_flag_rate: float
    premature_stop_rate: float
    avg_chains_to_solve: float
    hypothesis_exhaustion_rate: float
```

报告写入 `reports/benchmarks/benchmark_<timestamp>.json`，不写入 git（加入 .gitignore）。

### 1.6 执行接口

```python
# tests/eval/benchmark_runner.py
async def run_benchmark(
    challenges: list[str] | None = None,   # None = 全部
    report_path: str | None = None,         # None = 自动命名
    verification_callback=lambda f: "yes",
) -> BenchmarkReport:
    ...
```

CLI 接口：

```bash
python -m tests.eval.benchmark_runner
python -m tests.eval.benchmark_runner --challenges easy_tornado php_backup
python -m tests.eval.benchmark_runner --report reports/benchmarks/baseline.json
```

### 1.7 完成标准（验收门禁）

1. `benchmark_runner.py` 能独立运行，对全部 5 道题输出 `BenchmarkReport`
2. 基线 `solve_rate >= 0.8`（5 道题至少 4 道 solved）
3. `wrong_flag_rate < 0.2`
4. `premature_stop_rate < 0.3`
5. 每次运行输出 JSON 报告到 `reports/benchmarks/`
6. 有 1 个 pytest 测试用例验证 `BenchmarkReport` 数据结构可序列化

**禁止行为：**

- 不允许为了让 benchmark 通过而修改 mock server 使其更"好骗"
- 不允许修改 agent 代码来"针对" benchmark 测试
- 不允许跳过任何一道已有 mock challenge

---

## §2 Phase 6.5：FlagProof Object（第二优先级）

### 2.1 为什么是 P2

当前 `verifier.py` 能判对错，但每个 flag 的验证决策是"黑盒"的：

- 为什么这个 flag 被标记 `verified`？来自哪个工具？是 runtime 还是 source？
- 为什么 wrong flag 发生了？是 verifier 判断过早？还是 evidence source 被误判？
- 如果 replay 时复现不了，哪个步骤是不可重现的？

没有 Proof Object，`wrong_flag` 反馈就只能做到"降权这个 hypothesis"，无法做到"精确降权导致错误的 evidence source"。

这是知识库 BB-177/230 的核心建议之一，且**直接改善 Phase 6 eval 里 `wrong_flag_rate` 的诊断能力**。

### 2.2 数据结构设计

**新增到 `pentestagent/agents/pa_agent/ctf_state.py`：**

```python
@dataclass(slots=True)
class FlagProof:
    """记录一个 flag 决策的可审计证明对象。"""
    
    proof_type: str
    # 取值范围（有限枚举）：
    # "runtime_http"       — HTTP 响应 body 中直接读取
    # "runtime_command"    — 本地命令输出中读取
    # "runtime_collector"  — collector / trap 回调中获取
    # "source_code_leak"   — 源码 / 备份文件中读取
    # "dom_element"        — 浏览器 DOM 中读取
    # "platform_accept"    — 平台 submit 返回成功
    # "user_confirm"       — 用户手动确认
    
    evidence_source: str            # 工具名或策略名，例如 "hash_reconstruction_attack"
    evidence_url: str               # 产生证据的 URL（无则空串）
    evidence_snippet: str           # 最多 200 字符的原始证据片段
    
    replayable: bool                # 能否通过重放同一 HTTP 请求/命令复现
    submit_confidence: float        # 0.0–1.0；< 0.7 时 auto-submit 应被拦截
    
    source_trust: str
    # 取值范围：
    # "runtime"            — 运行时直接观测到
    # "source_only"        — 仅在源码 / 静态文件中看到，未运行时复现
    # "platform"           — 平台返回 accepted
    
    hypothesis_id: str | None       # 产生该证明的假设 ID
    strategy_kind: str | None       # 产生该证明的策略名
    timestamp: str                  # ISO 8601
```

**修改 `FlagRecord`（已在 ctf_state.py 中）：**

```python
@dataclass(slots=True)
class FlagRecord:
    value: str
    level: str                  # "candidate" / "runtime" / "verified" / "rejected"
    evidence_source: str
    rationale: str
    requires_followup: bool
    proof: FlagProof | None = None   # 新增字段
```

### 2.3 改动范围

| 文件 | 改动内容 |
|---|---|
| `ctf_state.py` | 新增 `FlagProof` dataclass；`FlagRecord` 新增 `proof: FlagProof | None` |
| `verifier.py` | `observe_flag()` 产出 `FlagProof` 并附到 `FlagRecord.proof` |
| `ctf_dispatcher.py` | `_observe_flag()` 传入足够信息以构建 `FlagProof` |
| `hypothesis_engine.py` | wrong-flag 反馈时，从 `FlagRecord.proof` 读取 `strategy_kind` / `evidence_source`，精确降权对应路径 |

### 2.4 submit_confidence 规则

```
source_trust == "source_only"      → submit_confidence = max(0.0, given - 0.4)
source_trust == "runtime"          → 保持 given
source_trust == "platform"         → submit_confidence = 1.0
replayable == False                → submit_confidence = max(0.0, given - 0.2)
```

**验证器规则（在 verifier.py 中执行）：**

```
if proof.submit_confidence < 0.5:
    → 不允许 auto_submit
    → 升级到 "requires_followup" 状态
    → 在 recovery.suggested_actions 中添加 "seek stronger runtime primitive"
```

### 2.5 完成标准

1. `FlagProof` 存在于 `ctf_state.py`，有 `__slots__`，字段类型完整
2. 每个 `FlagRecord` 在 `level` 变为 `"runtime"` 或 `"verified"` 时必须挂一个非 None 的 `proof`
3. `source_trust == "source_only"` 的 flag 不能触发 `auto_submit`（有 unit test 验证）
4. `submit_confidence < 0.5` 的 flag 不能触发 `auto_submit`（有 unit test 验证）
5. `hypothesis_engine` 接收 wrong-flag 反馈时，能从 `proof.strategy_kind` 精确降权（有 unit test 验证）
6. Phase 6 benchmark 在加入 Proof Object 之后，`wrong_flag_rate` 不能比 Phase 6 基线更高

---

## §3 Phase 6.8：系统稳定性补强（第三优先级）

这一阶段是中小型修复，可在 Phase 6 和 6.5 进行中并行处理。

### 3.1 FailoverMonitor 启动（已标记为 side task）

- 文件：`cpa_modules/m1_api_hub/failover_monitor.py`
- 目标：在 `CTFTaskDispatcher.__init__` 中（或 `run()` 开始时）调用 `FailoverMonitor.start_monitoring()`
- 要求：
  - 如果 FailoverMonitor 不可导入（缺依赖），静默跳过，不中断 dispatcher
  - 在 `run()` 结束时调用 `stop()`
  - 有 unit test：dispatcher 在 FailoverMonitor 启动失败时能继续正常运行

### 3.2 `_run_hash_reconstruction_attack_strategy` 动态文件路径提取

当前 `_collect_candidate_filenames()` 已能从 observations 中提取路径（`/fllllllllllllag` 等），但扫描 regex 仍局限于 `r"(/[-A-Za-z0-9_./]{3,})"` 这个单一模式，会漏掉：

```
"flag 在 /fllllllllllllag 文件里"
"真实 flag 文件是 /flag_is_here"
"cat /fllllllllllllag 查看"
```

补强点：在 `_collect_candidate_filenames()` 中额外扫描以下模式：

```python
# 中文和英文提示句式：
r"(?:flag|在|in|is\s+at|at|see|check|file\s+is)\s+([/][^\s<>\"']+)"
r"(?:cat|view|read)\s+([/][^\s<>\"']+)"
```

完成标准：有 unit test 验证从 `"flag in /fllllllllllllag"` 中提取出 `/fllllllllllllag`。

### 3.3 `tornado_ssti` 策略去重

当前 `tornado_ssti` 和 `ssti_via_render_parameter` 共享相同执行函数（`_run_render_parameter_ssti_strategy`）且共享相同 surface exhaustion key（`"ssti_via_render_parameter"`）。

结果：`tornado_ssti` 每次都直接返回 "render parameter surface already exhausted"，**完全无效**。

两种修复方案二选一（dev agent 决定）：

- **方案 A**：删除 `_WEB_STRATEGY_ORDER` 中的 `"tornado_ssti"` 条目（最简单，一行改动）
- **方案 B**：给 `tornado_ssti` 单独实现一套使用 Tornado 特有语法的 payload（`{%raw handler.settings["cookie_secret"]%}`），并使用独立的 surface key

完成标准：有 unit test 验证 `tornado_ssti` 在同一 session 中不会静默跳过 SSTI 探测。

---

## §4 明确冻结声明

以下内容在本文件覆盖时间段内（Phase 6 全部完成之前）**明确禁止开发**：

### 4.1 CTFCrewCoordinator / multi-agent

- 文件：`pentestagent/agents/pa_agent/ctf_crew_coordinator.py`（662 行）
- 状态：已建出骨架，**冻结，不开发，不接入任何测试路径**
- 原因：单 agent 路径仍有已知 bug，且无 eval baseline。multi-agent 只会放大当前的失败模式
- 解冻条件：Phase 6 benchmark `solve_rate >= 0.9`，`wrong_flag_rate < 0.1`

### 4.2 L0-L3 全层内存重构

- 不开发 L0（原始过程层）的正式索引结构
- 不开发 L3（平台画像层）的正式结构化接口
- L1（原子事实层）推迟到 Phase 7（Phase 6 eval 建立之后）
- 原因：任何记忆模型变化都需要 eval 才能量化影响

### 4.3 Tool 元数据治理

- 不给工具加 `risk_level`、`side_effects`、`evidence_value` 等字段
- 推迟到 Phase 8
- 原因：当前没有任何题失败是因为工具元数据不足导致选错工具

### 4.4 代码重组 / 重命名

- 不做"CTF Harness"概念性重命名
- 不重组 `cpa_modules/` 目录结构
- 不动 `pentestagent/agents/pa_agent/` 现有模块边界
- 原因：概念已在实现中隐式存在；重组不改变解题成功率

---

## §5 当前五个运行时边界的模块映射

（响应 KB 建议的"定义 5 个一级边界"，但以文档形式澄清，不重构代码）

| 边界 | 当前对应模块 | 状态 |
|---|---|---|
| Planner / Orchestrator | `CTFTaskDispatcher.run()` 主循环 + `HypothesisEngine.choose_chain_order()` | 已完成 |
| Tool Governance | `tool_guard.py` + `strategy_registry.py` (preconditions) | 已完成（元数据增强推迟） |
| Evidence / State | `CTFState` + `FlagRecord` | 已完成（FlagProof 待 Phase 6.5）|
| Verification / Guardrails | `verifier.py` + `RecoveryController` | 已完成（Proof-driven 增强待 Phase 6.5）|
| Memory / Retrospective | `strategy_memory.py` + `StrategyMemoryStore` | 已完成（L1 分层待 Phase 7）|

---

## §6 Phase 7 以后（备忘，当前不开发）

按知识库建议、按合理优先级排列，等 Phase 6 eval 建立之后再逐步启动：

| Phase | 内容 | 前置条件 |
|---|---|---|
| Phase 7 | Strategy Memory L1 原子事实层 | Phase 6 eval baseline 存在 |
| Phase 7.5 | Replay eval 扩充（更多 mock challenge，包括 crypto / pwn 类） | Phase 6 eval 框架稳定 |
| Phase 8 | Tool 元数据治理（`risk_level`、`evidence_value`、`preferred_for`） | Phase 7 完成 |
| Phase 8.5 | 可维护性传感器（CTF 特定 lint 规则：source-only bypass 检测等） | Phase 8 完成 |
| Phase 9 | CTFCrewCoordinator 接入 eval 并开始真实测试 | Phase 6 `solve_rate >= 0.9` |
| Phase 10 | L0 原始过程层正式索引（可回放 session 存储） | Phase 9 完成 |

---

## §7 给执行 dev agent 的约束汇总

以下规则适用于所有执行 Phase 6、6.5、6.8 的开发 agent：

1. **先读，再改**：改任何文件之前，必须先 Read 该文件完整内容
2. **改后必测**：每次改动之后必须运行 `.\.venv\Scripts\pytest.exe tests/ -q`，不允许在测试失败时提交
3. **不降测试总数**：Phase 6 开始时测试总数 = 947 passed。任何 Phase 结束时不允许低于该数值
4. **不改 mock server**：benchmark_runner 使用的 mock server 不允许修改使其变得更"好骗"
5. **Proof Object 在 Phase 6.5 之前不影响 Phase 6**：Phase 6.5 必须在 Phase 6 benchmark 基线确认之后才能开始
6. **冻结声明不可绕过**：§4 列出的冻结内容，任何 dev agent 不得在未经主控书面更新本文档的情况下开发

---

## §8 成功标准汇总

| Phase | 完成标准（可机器验证） |
|---|---|
| Phase 6 | `tests/eval/benchmark_runner.py` 存在；5 道题 `solve_rate >= 0.8`；`wrong_flag_rate < 0.2`；`premature_stop_rate < 0.3`；JSON 报告可写入 `reports/benchmarks/` |
| Phase 6.5 | `FlagProof` 在 `ctf_state.py`；`source_only` + `submit_confidence < 0.5` 均拦截 auto_submit；benchmark `wrong_flag_rate` 不退步 |
| Phase 6.8 | FailoverMonitor 软连接完成；`_collect_candidate_filenames` 能从中文提示中提取路径；`tornado_ssti` 无 silent skip |
| 全部 Phase 6 系列 | 测试总数 ≥ 960（+13 新测试）；无任何回归 |
