# FlagHunter 智能化改造路线图

> 日期：2026-05-26 | 基于 BB-331 分析结论 + FlagHunter 源码全面勘察

## 0. 项目定性（纠正前提假设）

在讨论"怎么改"之前，先确认 FlagHunter 是什么、不是什么：

**FlagHunter = AI 渗透测试框架 + CTF 自动化解题引擎**

| 维度 | 事实 |
|------|------|
| 类型 | 渗透测试 agent（不是 coding agent） |
| 工具面 | 安全工具为主：nmap、sqlmap、nuclei、ffuf、katana、subfinder、msf 等 30+ 工具 |
| 双模式 | 通用渗透模式（playbook 驱动）+ CTF 模式（自主解题流水线） |
| 已有智能设施 | Hypothesis 引擎、Reasoning 层、Strategy Memory、CTF Dispatcher、Recovery Controller、Platform Orchestrator |
| 已有外部接口 | MCP Server（对外暴露）、TUI + CLI、Docker/SSH Runtime |
| 版本 | v0.4.0 |

**这个定性意味着**：改进方案不能照搬 coding agent（Claude Code）的模式，而必须适配**渗透测试**的场景特征——工具风险更高（bash/shell）、任务天然可并行（recon/exploit/post-exploit）、上下文以扫描结果和攻击链为主（而非代码文件）。

---

## 1. 已有智能设施的现状

`flaghunter/agents/pa_agent/` 目录下实际上已经建立了一套 CTF 解题的专用智能体系：

| 模块 | 文件 | 实际功能 |
|------|------|---------|
| **Reasoning 层** | `reasoning.py` | 确定性推理决策（PreActionReasoning、ReasoningDecision），在每次工具执行前过滤：批准/降级/提问/拒绝 |
| **Hypothesis 引擎** | `hypothesis_engine.py` | 基于规则 + LLM 驱动的攻击假说生成，支持 SQLi/LFI/SSTI/CMDI/SSRF/JWT 等 30+ 攻击链类型 |
| **Strategy Memory** | `strategy_memory.py` | 跨题目策略记忆，基于 ChallengeFingerprint 做相似题目匹配和经验复用 |
| **CTF Dispatcher** | `ctf_dispatcher.py` | CTF 模式的总调度器：flag 正则检测、题目类型检测、备份文件探测、攻击链编排 |
| **Recovery Controller** | `recovery.py` | Provider 故障恢复、flag 检测、工具缺失处理 |
| **Platform Orchestrator** | `platform_orchestrator.py` | 多平台题目队列管理（优先队列、rate limit、状态同步） |
| **CTF Planner** | `ctf_planner.py` | 题目类型检测、登录表单识别、攻击链路由 |

**然而，这些设施存在三个结构性问题**：

1. **CTF 专用，通用渗透模式用不上**：Reasoning 层和 Strategy Memory 只在 CTF dispatcher 中被调用，base_agent 的基础 ReAct loop 完全没有受益
2. **处于 agent loop 外部，是"过滤器"而非"决策器"**：ReasoningDecision 描述的是 approve/downgrade/question，缺乏"分派子任务""搜索工具""请求帮助"等主动决策
3. **核心控制循环仍然是**：
   ```
   iteration=1 → 强制出计划 → 按步骤执行 → 步骤失败 → replan → 计划完成 → 退出
   ```
   这个循环剥夺了 LLM 自主决定"我该怎么做"的自由

---

## 2. 与 Claude Code 架构的实质性差距

将 BB-331 的 7 原则映射到渗透测试场景：

| # | Claude Code 原则 | FlagHunter 当前状态 | 渗透场景的具体含义 |
|---|-----------------|-------------------|-------------------|
| 1 | 工程化 ReAct（事件模型+hook+compact） | 基础 while loop，无事件模型 | 一条 nmap 扫描结果不应只是"输出"，而应触发后续攻击假设生成 |
| 2 | 统一工具契约（权限声明附在工具上） | Tool 类无 required_permission | 30+ 安全工具，有些该只读（nmap -sL），有些是攻击性的（sqlmap --os-shell） |
| 3 | 权限硬门禁 | **完全缺失** | 渗透测试工具天然有"侦察→攻击→后渗透"的破坏力梯度，需要硬门控制 |
| 4 | 子代理一等公民 | **缺失** | 渗透天然可并行：recon agent + vuln agent + exploit agent 同时工作 |
| 5 | 外化记忆（CLAUDE.md） | 有 strategy_memory（CTF 专用）+ notes | 渗透方法论、工具偏好、常用 payload 应形成可复用知识工件 |
| 6 | GSSC 上下文流水线 | 有 RAG + notes，但散装 | 扫描结果、工具输出、flag 线索需要统一装配而非全量灌入 |
| 7 | 可演化生态 | MCP Server 对外暴露，无 MCP Client | 各厂商扫描器（AWVS/Nessus/Xray）可作为 MCP 工具接入 |

**最关键的差距**：智能设施的"作用范围"问题——

```
现有架构:
  CTF Dispatcher → Reasoning层 → Hypothesis引擎 → Strategy Memory
        ↑                ↑              ↑              ↑
    仅 CTF 模式      仅做过滤     仅 CTF 假说   仅 CTF 记忆

  BaseAgent._run_loop() ← 通用渗透/assist/interact 模式都走这里
       ↓
  简单的 plan→execute→repeat（无任何智能层介入）

目标架构:
  BaseAgent._run_loop() ← 所有模式统一入口
       ↓
  权限门 → 推理层(ReasoningLayer) → 决策体(自主选择:探索/分派/执行/求助)
       ↓
  子代理(keyword:Explore→recon, General→exploit) + 工具搜索 + 外化记忆
```

---

## 3. 分 Phase 实施计划（适配渗透场景版）

### Phase 1：建立控制面 — 安全底线

**目标**：让所有工具调用经过统一权限门，为后续"放手让 agent 自己决策"建立信任基础

#### 1.1 权限门禁系统

**新增文件**：`flaghunter/runtime/permission_enforcer.py`

```python
class PermissionMode(IntEnum):
    RECON_ONLY = 1       # 仅侦察：nmap -sL/-sV, subfinder, whatweb, whois
    VULN_SCAN = 2        # 漏洞扫描：nuclei, sqlmap --batch, nikto（可产生请求但不利用）
    EXPLOIT = 3          # 漏洞利用：sqlmap --os-shell, msf exploit, 文件写入
    POST_EXPLOIT = 4     # 后渗透：lateral movement, data exfiltrate, persistence
    ALLOW = 99           # 无限制

class PermissionEnforcer:
    """渗透工具权限分级门禁"""
    def check(self, tool_name: str, arguments: dict) -> EnforcementResult: ...
    def _classify_tool_risk(self, tool_name: str, arguments: dict) -> PermissionMode: ...
    def _classify_bash_risk(self, command: str) -> PermissionMode: ...
```

**渗透工具风险分类**（不是文件读写的权限模型）：

| 风险级别 | 工具示例 | 默认允许模式 |
|---------|---------|------------|
| 侦察 | subfinder, whatweb, nmap -sL, katana, httpx | RECON_ONLY |
| 扫描 | nuclei, nikto, nmap -sV --script vuln, sqlmap --batch | VULN_SCAN |
| 利用 | sqlmap --os-shell, msf exploit, hydra, hashcat | EXPLOIT |
| 后渗透 | msf post/multi, mimikatz, psexec, nc -e | POST_EXPLOIT |

**改动点**：
- `Tool` 类添加 `required_permission: PermissionMode` 字段
- `_execute_single` 在 `tool.execute()` 前调用 `enforcer.check()`
- bash/terminal 工具增加渗透命令风险分类（反向 shell 检测、提权命令检测等）

#### 1.2 统一工具执行路径

- `_execute_single` 改为统一调用 `ToolExecutor.execute()`（而非直接调用 `tool.execute()`）
- 删除 `_execute_single` 中的 workspace scope 检查（改由 PermissionEnforcer 统一处理）
- ReasoningDecision 的 approve/downgrade 逻辑从 pa_agent 提升到 BaseAgent 层

**验证标准**：
- RECON_ONLY 模式下拒绝 `sqlmap --os-shell`
- 反向 shell 命令（`nc -e /bin/bash`）被检测并需要显式授权
- 不在 scope 内的目标 IP 被 PermissionEnforcer 拦截

**预估时间**：3-4 天

---

### Phase 2：让 Agent 会思考 — "智能感"的核心

**目标**：把 pa_agent 已有的 Reasoning/Hypothesis/Strategy 设施从"CTF 专用过滤器"升级为"所有模式的通用智能层"

#### 2.1 推理层重构：从过滤器到决策器

**现状**：`reasoning.py` 只做 approve/downgrade/question，在工具调用前过滤
**目标**：`ReasoningLayer` 参与控制循环决策：

```python
class ReasoningDecision:
    approve: bool
    reason: str
    action: str  # 新增: "execute" | "delegate" | "search_tools" | "request_help" | "retry"
    subagent_type: str | None  # 新增: "Recon" | "Exploit" | "Analysis"
    tool_suggestions: list[str]  # 新增: 建议尝试的替代工具
```

**改动点**：
- `base_agent._run_loop` 中，在工具调用前/后插入 `ReasoningLayer.evaluate(tool_call, result)`
- 把 pa_agent 的 `PreActionReasoning` 重构为 BaseAgent 的通用推理中间件

#### 2.2 子代理系统（渗透场景定制）

与 Claude Code 的子代理不同类型的工具白名单：

| 子代理类型 | 允许工具 | 用途 |
|-----------|---------|------|
| **Recon** | subfinder, nmap(-sL/-sV), katana, httpx, whatweb, gau, wayback | 信息收集 |
| **VulnScan** | nuclei, nikto, sqlmap(--batch), waf, afrog | 漏洞扫描 |
| **Exploit** | sqlmap, msf, hydra, dirscan, browser, http_request | 漏洞利用 |
| **Analysis** | terminal(只读), notes, web_search, knowledge_search | 结果分析 |
| **General** | 所有工具 | 完整能力 |

**新增文件**：`flaghunter/agents/subagent.py`

```python
@register_tool(name="Agent", category="agent")
async def agent_tool(task: str, subagent_type: str, runtime: Runtime) -> str:
    """分派子任务给专用子代理"""
    config = SUBAGENT_CONFIGS[subagent_type]
    sub_agent = SubagentRunner(
        llm=runtime.llm,           # 复用主 agent 的 LLM 实例
        tools=config.allowed_tools,  # 按类型白名单
        permission=config.max_permission,  # 子代理的权限上限
    )
    return await sub_agent.run(task)
```

#### 2.3 强制计划的解除 — 最关键的认知转变

**现状**：
```python
if iteration == 1 and len(self._task_plan.steps) == 0:
    plan_msg = await self._auto_generate_plan()  # 强制出计划！
```

**目标**：把计划生成从"强制步骤"改为"LLM 可选工具"

```python
# 新增工具，由 LLM 自主决定何时调用
@register_tool(name="generate_plan", category="planning")
async def plan_tool(steps: list[str]) -> str:
    """LLM 自主选择生成计划（不再强制）"""
    ...
```

**核心逻辑变化**：
```
之前:  iteration=1 → 强制 generate_plan → 按步骤执行 → 完成 → 退出
之后:  iteration=1 → LLM 自由思考 →
         ├─ 需要规划 → 自己调用 generate_plan
         ├─ 需要探索 → 自己调用 Agent(type="Recon")
         ├─ 可以直接做 → 直接调用 nmap/subfinder/...
         └─ 完成了 → 自己调用 finish
```

**注意**：计划完成后自动退出的逻辑保留（`_can_finish` / `is_complete` 检查保留），只是不再强制首轮出计划。

#### 2.4 工具搜索（安全场景定制）

```python
@register_tool(name="ToolSearch", category="meta")
async def tool_search(query: str) -> str:
    """按能力/攻击类型搜索可用工具，例如 query='SSRF检测' 或 query='子域名'"""
    ...
```

#### 2.5 思考/行动分离

LLM 层已正确提取 `reasoning_content`，只需在 agent loop 中利用它：

- TUI 中折叠思考过程（`metadata={"intermediate": True}` 已支持）
- `_run_loop` 中区分：`reasoning_content`（纯思考展示）vs `content + tool_calls`（行动输出）

**改动点**：约 5 行代码在 `_run_loop` 中。

**预估时间**：7-10 天（子代理系统最耗时）

---

### Phase 3：长期运行与知识沉淀

#### 3.1 Task Registry（渗透任务管理）

```python
class Task:
    task_id: str
    description: str
    status: TaskStatus  # created/running/completed/failed/stopped
    sub_tasks: list[str]  # 子代理任务 ID
    findings: list[Finding]  # 渗透发现
```

适用于：批量化 CTF 解题、多目标渗透任务的进度追踪。

#### 3.2 渗透方法论记忆（CLAUDE.md 等价物）

```python
class ProjectMemory:
    def load_methodology(self) -> str:
        """读取 METHODOLOGY.md — 渗透方法论文档"""
    def load_payloads(self) -> str:
        """读取常用 payload 库路径"""
    def inject_to_system_prompt(self) -> str:
        """注入到 agent system prompt"""
```

渗透场景的"项目记忆"不是代码规范，而是：
- 渗透方法论（PTES/OSSTMM 阶段定义）
- 常用 payload 字典位置
- 目标环境信息（网络拓扑、已知服务）
- 上次渗透的遗留发现

#### 3.3 会话持久化

```python
class SessionStore:
    def save(self, session_id, conversation, plan, findings)
    def load(self, session_id) -> Session
    def list_sessions(self) -> list[SessionMeta]
```

#### 3.4 上下文装配（渗透版 GSSC）

```
Gather: 扫描结果 + notes + METHODOLOGY.md + strategy_memory 匹配
Select: 按当前攻击阶段（侦察/利用/后渗透）筛选
Structure: 注入 system prompt + 当前阶段的工具定义
Compress: 扫描输出超长时自动摘要
```

**预估时间**：5-7 天

---

### Phase 4：生态与可观测性

#### 4.1 MCP Client Bridge

让 FlagHunter 消费外部 MCP server 的工具（而非仅对外暴露）：

- 接入 AWVS/Xray/Nessus 等商业扫描器作为 MCP 工具
- 接入自定义漏洞库/情报源

#### 4.2 Hook 系统

```python
class HookRunner:
    def on_tool_pre_execute(self, tool_name, args) -> HookResult  # 工具执行前
    def on_tool_post_execute(self, tool_name, result) -> HookResult  # 工具执行后
    def on_flag_detected(self, flag_text, challenge_id) -> None  # flag 检测到
    def on_vuln_found(self, vuln_type, target) -> None  # 漏洞发现
```

#### 4.3 可观测性

- 每个 turn 的工具执行时间、token 消耗、扫描发现数量
- 渗透效率指标（发现漏洞数 / turn 数、flag 捕获率等）

**预估时间**：5-7 天

---

## 4. 实施优先级矩阵

| Phase | 核心能力 | 优先级 | 预估 | 依赖 | 交付物 |
|-------|---------|--------|------|------|--------|
| **P1** | 权限门禁 + 统一工具路径 | **P0** | 3-4天 | 无 | 所有工具调用有硬门控制 |
| **P2** | 子代理 + 推理升级 + 解除强制计划 | **P0** | 7-10天 | P1 | agent 能自主分解渗透任务 |
| **P3** | Task Registry + 渗透记忆 + 会话持久化 | **P1** | 5-7天 | P2 | 批量化 CTF + 长任务可恢复 |
| **P4** | MCP Client + Hook + 可观测性 | **P2** | 5-7天 | P3 | 可扩展工具生态 |

**总预估**：20-28 天

---

## 5. 关键设计决策（渗透场景特化）

### 决策 1：权限模型是"工具破坏力梯度"而非"文件读写边界"

Claude Code 的权限是围绕文件操作（read/write/workspace）建模的。FlagHunter 的权限应围绕**攻击行为的破坏力梯度**建模：

```
侦察(只读网络) < 漏洞扫描(可产生恶意请求) < 漏洞利用(可能破坏目标) < 后渗透(可在目标执行代码)
```

工具的分类依据是其**对外部目标的影响**，而非对本地文件的操作。

### 决策 2：子代理按渗透阶段划分，非工程角色

Claude Code 的子代理按"工程角色"分（Explore/Plan/Verification），FlagHunter 应按"渗透阶段"分（Recon/VulnScan/Exploit/Analysis）。

### 决策 3：Strategy Memory 的升级路径

现有的 `strategy_memory.py` 是 CTF 专用的、确定性匹配的。升级方向：
- **短期**：保持现有实现，增加写入接口（当前是从 retrospective 文件读取）
- **中期**：LLM 自主决定何时写入 strategy（发现有效攻击模式 → 自己存档）
- **长期**：跨 session 的策略共享（Agent A 发现的 SQLi 绕过 → Agent B 的后续任务可检索）

### 决策 4：强制计划的解除是"智能化"的开关

当前 iteration=1 强制生成计划的逻辑，是导致 agent "不会自己思考"的**最大单一原因**。即使不做任何其他改进，仅解除强制计划 + 把 plan 变成可选工具，agent 的自主感就会有显著提升。

但这个改动的前提是：权限门（P1）已就位，agent 在安全边界内才能被"放手"。

---

## 6. 不改的部分

以下 FlagHunter 已有设施保持不动：

| 保持不变 | 原因 |
|---------|------|
| Hypothesis 引擎架构 | 规则优先 + LLM fallback 的设计是正确的 |
| Strategy Memory 的 ChallengeFingerprint 匹配 | 确定性匹配先行的设计优于纯向量相似度 |
| CTF Dispatcher 的整体调度逻辑 | flag 检测、备份探索、攻击链路由功能完整 |
| Playbook 系统 | 通用渗透场景的结构化剧本是正确的抽象 |
| MCP Server 接口 | 对外暴露的工具面已完整定义 |
| TUI/CLI 界面 | 交互层不需要改动 |
| LiteLLM 集成 + provider failover | 已正确处理 reasoning_content + M1 API hub |

---

## 7. 第一阶段最小可验证改动（P1 首日）

如果只有 1 天时间，能交付的最大价值改动：

1. **Tool 类添加 `required_permission` 字段**（30 分钟）
   - `flaghunter/tools/registry.py`：`Tool` dataclass 加 `required_permission: int = 99`
   - 所有现有工具注册处加 `required_permission=PermissionMode.ALLOW`（默认兼容）

2. **PermissionEnforcer 最小实现**（2 小时）
   - `flaghunter/runtime/permission_enforcer.py`
   - 实现 `check(tool_name, arguments)` 接口
   - bash 命令风险分类：检测 `nc -e`、`bash -i`、`python -c 'import pty'` 等反向 shell 特征

3. **agent loop 接入 permission check**（1 小时）
   - `_execute_single` 中 `tool.execute()` 前加 `enforcer.check()`
   - permission denied 时返回 ToolResult(error="Permission denied: ...")

4. **解除 iteration=1 强制计划**（30 分钟）
   - 注释掉 `_run_loop` 中的强制 `_auto_generate_plan` 调用
   - 把 `generate_plan` 注册为普通工具

**验收**：`/agent "扫描 example.com 的开放端口"` — agent 不再强制首轮出计划，而是自主调用 nmap（或其他它选择的工具）
