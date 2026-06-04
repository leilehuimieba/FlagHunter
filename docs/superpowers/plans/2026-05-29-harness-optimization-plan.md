# FlagHunter Harness 优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Cairn 的“共享状态、外置会话、协议化调度、artifact-first、独立验证”思路，以最小破坏方式吸收进 FlagHunter，优先解决当前主干中的状态分裂、长任务不可恢复、dispatcher 过大、上下文装配不可查询、验证与审计链不够外置的问题。

**Architecture:** 不直接照搬 Cairn 的 server/dispatcher 双进程形态，而是在现有单仓结构上新增一个轻量 Harness 层：`session ledger + artifact registry + checkpoint + audit + coordinator split`。CTF 主链继续以 `CTFState/Hypothesis/Verifier/RecoveryController` 为核心，但把“事件真相、artifact 生命周期、恢复断点、上下文切片、UI/MCP 可观察性”从大 prompt 和大函数里剥出来，变成独立模块。

**Tech Stack:** Python 3.10+, dataclasses, JSONL/JSON persistence, existing PentestAgent runtime/tool system, pytest, existing MCP/TUI/Web console.

---

## 先做什么，不做什么

### 本计划优先落地
- append-only 会话事件账本（session/event ledger）
- artifact 注册表与统一引用
- `ctf_dispatcher.py` 的职责收缩与 coordinator 化
- 可查询上下文装配，替代“只靠 summary”
- verify / recovery / checkpoint 的统一断点
- MCP/Web/TUI 面向同一事件流消费

### 本计划明确后置
- 不先上完整 Cairn 风格独立 server 进程
- 不先重写全部 TUI / web console
- 不先引入更多多 agent 角色
- 不先上复杂 graph DB / message bus / sqlite 重构
- 不先把 notes 全部废弃，先做“notes 退居证据层”

---

## 当前代码基线与主要短板

### 已有基础（保留并复用）
- `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\ctf_state.py`
  - 已有 `CTFState / Hypothesis / Experiment / VerificationResult / ExplorationItem`
- `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\hypothesis_engine.py`
  - 已有规则优先的假设生成与反馈更新
- `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\verifier.py`
  - 已有 candidate/runtime/verified/rejected 分层
- `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\recovery.py`
  - 已有恢复决策骨架
- `D:\webstudy\FlagHunter\pentestagent\knowledge\graph.py`
  - 已有 ShadowGraph，可作为派生视图继续保留
- `D:\webstudy\FlagHunter\pentestagent\tools\executor.py`
  - 已统一工具执行、M4 scope check、flag 自动发现
- `D:\webstudy\FlagHunter\pentestagent\mcp\server\mcp_tools.py`
  - 已有 fresh agent per task 的边界意识

### 当前关键短板（要解决）
- `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\ctf_dispatcher.py`
  - 约 7000+ 行，混合了 orchestration、页面解析、具体利用、flag 处理、UI 侧信息拼装
- `D:\webstudy\FlagHunter\pentestagent\llm\memory.py`
  - 摘要是“覆盖式缓存摘要”，不可像 Cairn session 一样做可回溯切片
- `D:\webstudy\FlagHunter\pentestagent\knowledge\context_assembler.py`
  - 来源少、不可按任务阶段查询事件片段，且 notes 在别处拼接，状态来源不单一
- `D:\webstudy\FlagHunter\pentestagent\task_registry.py`
  - 只有任务级 JSON 快照，不是 append-only event log，无法承载恢复、handoff、回放
- `D:\webstudy\FlagHunter\pentestagent\observability.py`
  - 只有指标，没有决策级/验证级/恢复级事件语义
- `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py` 与 `...\mcp\server\mcp_tools.py`
  - 已有 task/thinking/tool_calls 视图，但底层没有统一事件主线，多个界面各记一份

---

## 目标映射：从 Cairn 学什么，怎么落到现仓库

| Cairn 思想 | FlagHunter 当前对象 | 本次映射方式 |
|---|---|---|
| Fact | `Observation / Artifact / FlagRecord / FlagProof` | 不重命名；新增 append-only 事件账本记录其产生与升级 |
| Intent | `Hypothesis / next_experiments / exploration_agenda` | 不引入新术语；把调度动作显式事件化 |
| Hint | `hint / challengePath / artifactPaths / user feedback / notes evidence` | 统一走 session event 与 checkpoint 注入 |
| Shared board | 当前分散在 `CTFState + notes + task_registry + UI task object` | 收拢到 `session ledger + CTFState snapshot + artifact registry` |
| Server/Dispatcher 分离 | 当前单体进程 | 先做逻辑分层，不先拆进程 |
| Artifact-first | 当前 raw path / notes / web task 字段散落 | 增加 `ArtifactRegistry` 与 artifact handle |
| Queryable session | 当前 summary memory | 增加可切片 event ledger 与 session context view |
| Independent verification | 当前已有 verifier，但结果传播路径分散 | verifier 输出写入统一 ledger/checkpoint |

---

## 目标文件结构

### 新增目录
- Create: `D:\webstudy\FlagHunter\pentestagent\harness\__init__.py`
- Create: `D:\webstudy\FlagHunter\pentestagent\harness\models.py`
- Create: `D:\webstudy\FlagHunter\pentestagent\harness\session_ledger.py`
- Create: `D:\webstudy\FlagHunter\pentestagent\harness\artifact_registry.py`
- Create: `D:\webstudy\FlagHunter\pentestagent\harness\checkpoint_store.py`
- Create: `D:\webstudy\FlagHunter\pentestagent\harness\audit_events.py`
- Create: `D:\webstudy\FlagHunter\pentestagent\knowledge\session_context.py`
- Create: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\coordinator.py`
- Create: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\recon_executor.py`
- Create: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\explore_executor.py`
- Create: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\state_persistence.py`

### 重点修改文件
- Modify: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\ctf_dispatcher.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\ctf_state.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\verifier.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\recovery.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\knowledge\context_assembler.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\llm\memory.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\task_registry.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\observability.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\mcp\server\mcp_tools.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\tools\finish\__init__.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\tools\executor.py`

### 测试文件
- Create: `D:\webstudy\FlagHunter\tests\unit\harness\test_session_ledger.py`
- Create: `D:\webstudy\FlagHunter\tests\unit\harness\test_artifact_registry.py`
- Create: `D:\webstudy\FlagHunter\tests\unit\harness\test_checkpoint_store.py`
- Create: `D:\webstudy\FlagHunter\tests\unit\knowledge\test_session_context.py`
- Create: `D:\webstudy\FlagHunter\tests\unit\agents\pa_agent\test_coordinator_split.py`
- Create: `D:\webstudy\FlagHunter\tests\integration\test_ctf_handoff_resume.py`
- Create: `D:\webstudy\FlagHunter\tests\integration\test_mcp_web_event_projection.py`

---

## 分阶段实施流程

### Phase A：先把“真相记录层”立起来
1. 建立 session ledger（append-only）
2. 建立 artifact registry（artifact handle 而不是裸路径）
3. 给 CTFState 增加 snapshot/export/restore
4. 让 verifier/recovery/tool executor 把关键事件写入 ledger

### Phase B：再把调度逻辑从超大 dispatcher 里抽出来
1. 新建 `CTFCoordinator`
2. 新建 recon/explore executor
3. `ctf_dispatcher.py` 退化为 façade + 兼容适配层
4. 验证行为不变，再删旧分支

### Phase C：把“上下文”和“恢复”改成可查询、可恢复
1. session context view 替代单纯 summary
2. checkpoint store 按关键节点落盘
3. MCP/Web/TUI 从 ledger 投影视图，而不是各自拼字符串

### Phase D：最后补测试与评估
1. 单测验证 event schema / artifact / checkpoint
2. 集成测试验证 recover / resume / verify 升级路径
3. eval 比较优化前后：误报、恢复成功率、平均上下文长度、人工定位时间

---

## Task 1：建立 Harness 事件模型与 Session Ledger

**Files:**
- Create: `D:\webstudy\FlagHunter\pentestagent\harness\models.py`
- Create: `D:\webstudy\FlagHunter\pentestagent\harness\session_ledger.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\task_registry.py`
- Test: `D:\webstudy\FlagHunter\tests\unit\harness\test_session_ledger.py`

- [ ] **Step 1: 定义统一事件 schema**

```python
# pentestagent/harness/models.py
from dataclasses import dataclass, field
from typing import Any, Literal

HarnessEventType = Literal[
    "task_started",
    "state_snapshot",
    "observation_added",
    "artifact_registered",
    "hypothesis_ranked",
    "experiment_started",
    "experiment_finished",
    "verification_decided",
    "recovery_decided",
    "tool_called",
    "tool_finished",
    "handoff_written",
    "task_finished",
]

@dataclass(slots=True)
class HarnessEvent:
    run_id: str
    seq: int
    ts: float
    type: HarnessEventType
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 2: 实现 append-only JSONL ledger**

```python
# pentestagent/harness/session_ledger.py
class SessionLedger:
    def append(self, event: HarnessEvent) -> None: ...
    def read_all(self, run_id: str) -> list[HarnessEvent]: ...
    def read_slice(self, run_id: str, *, event_types: set[str] | None = None, last_n: int | None = None) -> list[HarnessEvent]: ...
    def latest_seq(self, run_id: str) -> int: ...
```

- [ ] **Step 3: 让 TaskRegistry 只保留任务目录索引，不再承担完整事件真相**

```python
# task_registry.py 方向
# 原 tasks.json 继续保留，但只记录任务概览与 ledger/checkpoint 路径
{
  "task_id": "...",
  "status": "running",
  "ledger_path": "loot/runs/<run_id>/events.jsonl",
  "checkpoint_path": "loot/runs/<run_id>/checkpoint.json",
}
```

- [ ] **Step 4: 先写单测再落代码**

Run: `pytest tests/unit/harness/test_session_ledger.py -v`
Expected: 初次 FAIL，提示缺少 `SessionLedger` 或 schema 不匹配

- [ ] **Step 5: 完成实现并验证通过**

Run: `pytest tests/unit/harness/test_session_ledger.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pentestagent/harness/models.py pentestagent/harness/session_ledger.py pentestagent/task_registry.py tests/unit/harness/test_session_ledger.py
git commit -m "feat: add harness session ledger"
```

---

## Task 2：建立 Artifact Registry，统一 artifact 生命周期

**Files:**
- Create: `D:\webstudy\FlagHunter\pentestagent\harness\artifact_registry.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\tools\finish\__init__.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\mcp\server\mcp_tools.py`
- Test: `D:\webstudy\FlagHunter\tests\unit\harness\test_artifact_registry.py`

- [ ] **Step 1: 定义 artifact handle 而不是继续裸传 path**

```python
@dataclass(slots=True)
class ArtifactHandle:
    artifact_id: str
    run_id: str
    kind: str
    path: str
    title: str
    producer: str
    tags: list[str]
    metadata: dict[str, Any]
```

- [ ] **Step 2: 实现 registry，支持 register/get/list/by_tag**

```python
class ArtifactRegistry:
    def register(self, *, run_id: str, kind: str, path: str, title: str, producer: str, tags: list[str] | None = None, metadata: dict[str, Any] | None = None) -> ArtifactHandle: ...
    def list(self, run_id: str) -> list[ArtifactHandle]: ...
```

- [ ] **Step 3: finish、web_server、mcp_tools 全部从 `artifactPaths: list[str]` 向 `artifactRefs` 兼容迁移**

```python
# 兼容返回结构
{
  "artifactPaths": ["legacy/path.txt"],
  "artifactRefs": [
    {"artifact_id": "art_001", "kind": "log", "path": "loot/...", "title": "sqlmap output"}
  ]
}
```

- [ ] **Step 4: 事件化 artifact 注册动作**

每次 register 时同时写一条 `artifact_registered` 事件到 ledger。

- [ ] **Step 5: 验证**

Run: `pytest tests/unit/harness/test_artifact_registry.py tests/unit/interface/test_web_server.py -v`
Expected: PASS，旧 `artifactPaths` 用例不回退，新 `artifactRefs` 用例新增通过

- [ ] **Step 6: Commit**

```bash
git add pentestagent/harness/artifact_registry.py pentestagent/tools/finish/__init__.py pentestagent/interface/web_server.py pentestagent/mcp/server/mcp_tools.py tests/unit/harness/test_artifact_registry.py
git commit -m "feat: add artifact registry and refs"
```

---

## Task 3：为 CTFState 增加 snapshot / restore / checkpoint 能力

**Files:**
- Create: `D:\webstudy\FlagHunter\pentestagent\harness\checkpoint_store.py`
- Create: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\state_persistence.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\ctf_state.py`
- Test: `D:\webstudy\FlagHunter\tests\unit\harness\test_checkpoint_store.py`

- [ ] **Step 1: 给 CTFState 增加纯数据导出与恢复接口**

```python
class CTFState:
    def to_snapshot(self) -> dict[str, Any]: ...
    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> "CTFState": ...
```

- [ ] **Step 2: 增加 checkpoint store**

```python
class CheckpointStore:
    def save(self, run_id: str, snapshot: dict[str, Any], *, label: str) -> str: ...
    def load_latest(self, run_id: str) -> dict[str, Any] | None: ...
```

- [ ] **Step 3: 规定 checkpoint 触发点**

必须在以下节点落盘：
- recon 完成后
- verification 决策后
- recovery 决策前
- task_finished 前

- [ ] **Step 4: 写单测**

Run: `pytest tests/unit/harness/test_checkpoint_store.py -v`
Expected: FAIL，缺少 `to_snapshot/from_snapshot` 或 checkpoint API

- [ ] **Step 5: 实现并回归**

Run: `pytest tests/unit/harness/test_checkpoint_store.py tests/unit/agents/pa_agent -k "ctf_state or verifier or recovery" -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pentestagent/harness/checkpoint_store.py pentestagent/agents/pa_agent/state_persistence.py pentestagent/agents/pa_agent/ctf_state.py tests/unit/harness/test_checkpoint_store.py
git commit -m "feat: add ctf state checkpoint persistence"
```

---

## Task 4：把 `ctf_dispatcher.py` 收缩为 façade，新增 `CTFCoordinator`

**Files:**
- Create: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\coordinator.py`
- Create: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\recon_executor.py`
- Create: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\explore_executor.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\ctf_dispatcher.py`
- Test: `D:\webstudy\FlagHunter\tests\unit\agents\pa_agent\test_coordinator_split.py`

- [ ] **Step 1: 抽出 coordinator 合同**

```python
class CTFCoordinator:
    async def run(self, target: str, hint: str = "") -> SolveResult: ...
    async def observe(self) -> None: ...
    async def reason(self) -> None: ...
    async def explore(self) -> None: ...
    async def verify(self) -> None: ...
    async def recover(self) -> None: ...
```

- [ ] **Step 2: recon/explore executor 只承接“动作”，不承接排序和停止判断**

```python
class ReconExecutor:
    async def collect_page_features(...): ...

class ExploreExecutor:
    async def run_strategy(...): ...
```

- [ ] **Step 3: `ctf_dispatcher.py` 退为兼容入口**

```python
class CTFTaskDispatcher:
    async def solve(...):
        coordinator = CTFCoordinator(...)
        return await coordinator.run(...)
```

- [ ] **Step 4: 限制本轮只迁移主循环骨架，不迁移所有 exploit helper**

本轮原则：helper 方法先保留在 `ctf_dispatcher.py`，由 executor/coordinator 调用；第二轮再继续搬迁，避免一次性破坏 7000+ 行文件的行为稳定性。

- [ ] **Step 5: 验证**

Run: `pytest tests/unit/agents/pa_agent/test_coordinator_split.py tests/eval/benchmark_runner.py -k "not slow" -v`
Expected: 新增单测 PASS，现有 benchmark runner 不因入口改变而断裂

- [ ] **Step 6: Commit**

```bash
git add pentestagent/agents/pa_agent/coordinator.py pentestagent/agents/pa_agent/recon_executor.py pentestagent/agents/pa_agent/explore_executor.py pentestagent/agents/pa_agent/ctf_dispatcher.py tests/unit/agents/pa_agent/test_coordinator_split.py
git commit -m "refactor: split ctf coordinator from dispatcher"
```

---

## Task 5：把 verifier / recovery / tool execution 接入统一审计事件流

**Files:**
- Create: `D:\webstudy\FlagHunter\pentestagent\harness\audit_events.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\verifier.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\agents\pa_agent\recovery.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\tools\executor.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\observability.py`
- Test: `D:\webstudy\FlagHunter\tests\integration\test_mcp_web_event_projection.py`

- [ ] **Step 1: 审计事件统一格式**

```python
class AuditEventWriter:
    def tool_called(...): ...
    def tool_finished(...): ...
    def verification_decided(...): ...
    def recovery_decided(...): ...
```

- [ ] **Step 2: ToolExecutor 不只返回结果，还写 tool event**

必须写：
- tool name
- canonical args hash
- duration
- success/error
- artifact refs（如有）
- discovered flags（如有）

- [ ] **Step 3: verifier/recovery 输出结构化决策事件**

```python
{
  "type": "verification_decided",
  "payload": {
    "decision": "runtime",
    "flag": "flag{...}",
    "confidence": 0.85,
    "requires_followup": true
  }
}
```

- [ ] **Step 4: observability 保留聚合指标，但来源改为 ledger/audit event 聚合**

- [ ] **Step 5: 验证**

Run: `pytest tests/integration/test_mcp_web_event_projection.py -v`
Expected: MCP 与 web task detail 都能看到同一条 verification/recovery/tool trace

- [ ] **Step 6: Commit**

```bash
git add pentestagent/harness/audit_events.py pentestagent/agents/pa_agent/verifier.py pentestagent/agents/pa_agent/recovery.py pentestagent/tools/executor.py pentestagent/observability.py tests/integration/test_mcp_web_event_projection.py
git commit -m "feat: add unified harness audit events"
```

---

## Task 6：把上下文装配从“摘要缓存”升级为“可切片 session context”

**Files:**
- Create: `D:\webstudy\FlagHunter\pentestagent\knowledge\session_context.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\knowledge\context_assembler.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\llm\memory.py`
- Test: `D:\webstudy\FlagHunter\tests\unit\knowledge\test_session_context.py`

- [ ] **Step 1: 先定义 session context view，而不是继续扩 get_messages_with_summary**

```python
class SessionContextView:
    def build_for_phase(self, *, run_id: str, phase: str, max_items: int = 20) -> str: ...
    def latest_observations(self, run_id: str, limit: int = 10) -> list[dict[str, Any]]: ...
    def latest_failed_experiments(self, run_id: str, limit: int = 5) -> list[dict[str, Any]]: ...
```

- [ ] **Step 2: ContextAssembler 改为 GSSC + ledger slice**

保留 Gather→Select→Structure→Compress，但 Gather 增加：
- latest observations
- latest artifacts
- recent verification decisions
- recent recovery decisions
- last checkpoint summary

- [ ] **Step 3: ConversationMemory 保留 summary，但只对“聊天历史”负责，不再承担全部运行时记忆**

即：
- 聊天轮次 → `ConversationMemory`
- 任务状态/事实/验证/恢复 → `SessionContextView + CTFState snapshot`

- [ ] **Step 4: 单测**

Run: `pytest tests/unit/knowledge/test_session_context.py -v`
Expected: PASS，且生成上下文优先返回最近 runtime facts，而不是只返回摘要文本

- [ ] **Step 5: Commit**

```bash
git add pentestagent/knowledge/session_context.py pentestagent/knowledge/context_assembler.py pentestagent/llm/memory.py tests/unit/knowledge/test_session_context.py
git commit -m "feat: add queryable session context assembly"
```

---

## Task 7：为 MCP/Web/TUI 建立统一的 handoff / resume 主线

**Files:**
- Modify: `D:\webstudy\FlagHunter\pentestagent\mcp\server\mcp_tools.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`
- Modify: `D:\webstudy\FlagHunter\pentestagent\interface\conversation_store.py`
- Test: `D:\webstudy\FlagHunter\tests\integration\test_ctf_handoff_resume.py`

- [ ] **Step 1: run_task_async 返回 run_id / ledger_path / checkpoint_path**

```python
{
  "task_id": "...",
  "run_id": "run_xxx",
  "status": "running",
  "ledger_path": "loot/runs/run_xxx/events.jsonl",
  "checkpoint_path": "loot/runs/run_xxx/checkpoint.json"
}
```

- [ ] **Step 2: web_server task detail 与 replay/retry/resume 共用同一 run artifact**

- [ ] **Step 3: ConversationStore 不再只保存聊天消息，同时保存最新 handoff metadata**

```python
{
  "conversation_id": "...",
  "last_run_id": "run_xxx",
  "last_checkpoint": "loot/runs/run_xxx/checkpoint.json"
}
```

- [ ] **Step 4: 新增 resume 语义**

最小目标：当 run 因 provider 不可用 / stop_candidate_only / wait_for_verification 停止时，可以从 checkpoint 重建 state 后继续，而不是完全重跑。

- [ ] **Step 5: 验证**

Run: `pytest tests/integration/test_ctf_handoff_resume.py -v`
Expected: PASS，模拟中断后可从 checkpoint 恢复，且 ledger 序号连续增长

- [ ] **Step 6: Commit**

```bash
git add pentestagent/mcp/server/mcp_tools.py pentestagent/interface/web_server.py pentestagent/interface/conversation_store.py tests/integration/test_ctf_handoff_resume.py
git commit -m "feat: add handoff and resume flow for harness runs"
```

---

## Task 8：建立评估与验收矩阵，证明这次优化真的更稳

**Files:**
- Modify: `D:\webstudy\FlagHunter\tests\eval\benchmark_runner.py`
- Create: `D:\webstudy\FlagHunter\docs\superpowers\plans\2026-05-29-harness-optimization-acceptance.md`
- Test: `D:\webstudy\FlagHunter\tests\eval\benchmark_runner.py`

- [ ] **Step 1: 定义 4 个关键指标**

```text
1. candidate->verified 转化率
2. wrong-flag 后恢复成功率
3. 平均 prompt context 大小
4. 人工定位一次失败链路所需时间
```

- [ ] **Step 2: benchmark_runner 增加 ledger/checkpoint 采样输出**

- [ ] **Step 3: 设定 DoD**

```text
- dispatcher 体积下降到 < 4500 行（第一阶段目标）
- 任一 /ctf run 都会生成 ledger + checkpoint + artifact index
- MCP/Web 至少能显示 verification/recovery/tool timeline
- provider unavailable / wrong flag / candidate-only 三种停止路径可恢复或有明确 handoff
```

- [ ] **Step 4: 验证**

Run: `pytest tests/eval/benchmark_runner.py -v`
Expected: PASS，且 benchmark 输出包含 harness trace metadata

- [ ] **Step 5: Commit**

```bash
git add tests/eval/benchmark_runner.py docs/superpowers/plans/2026-05-29-harness-optimization-acceptance.md
git commit -m "docs: add harness optimization acceptance matrix"
```

---

## 实施顺序建议（现实版）

### 第一周：低风险收口
- Task 1
- Task 2
- Task 3

### 第二周：主链重构
- Task 4
- Task 5

### 第三周：体验和恢复
- Task 6
- Task 7

### 第四周：评估与裁剪
- Task 8
- 清理旧字段、兼容层、冗余 notes 拼接

---

## 关键设计原则（避免走偏）

1. **不要直接 clone Cairn 架构**
   - 你们已有 `CTFState/Hypothesis/Verifier/Recovery`，这是很强的现成主干；目标是补壳，不是推倒重来。

2. **先把“事件真相”外置，再谈更多智能**
   - 没有统一 ledger，任何多 agent / 更复杂 UI / 自动恢复都会继续建立在沙地上。

3. **notes 退居证据层，不再做唯一主状态**
   - 这一步是最大收益点之一。

4. **dispatcher 先 façade 化，再细拆**
   - 不要试图一口气把 7000 行文件拆成 20 个文件；第一轮只抽主循环责任边界。

5. **Context memory 和 runtime state 分家**
   - `ConversationMemory` 只管聊天历史；任务状态依赖 `CTFState + SessionContextView + checkpoint`。

---

## 风险与回滚策略

### 风险 1：兼容层过多，短期代码更复杂
- 应对：每个新增模块必须有独立测试，且在第二轮明确删除旧调用路径

### 风险 2：UI / MCP / Web 三端事件格式不一致
- 应对：先统一底层 event schema，再做投影层适配

### 风险 3：checkpoint snapshot 与 dataclass 版本漂移
- 应对：沿用 `schema_version`，为 snapshot 增加 migration 钩子

### 风险 4：benchmark 行为抖动
- 应对：Task 4 只抽主循环骨架，不改 helper 利用逻辑；先做行为等价再做深拆

---

## 预期收益

### 工程收益
- 降低 `ctf_dispatcher.py` 的认知负担
- 提高 wrong-flag / candidate-only / provider-down 的恢复能力
- 让 Web/MCP/TUI 看到同一条任务真相链
- 更容易追加 eval、审计、handoff、resume

### 产品收益
- 用户更容易理解“系统为什么停、停在哪、下一步是什么”
- /ctf 场景更接近“长任务可管理系统”，不只是“大 prompt + 大函数”
- 为后续真正的本地挑战资产模式、Web 控制台、MCP 远程编排打下更稳的主干

---

## 自检结论

### Spec coverage
- 已覆盖：状态统一、artifact 外置、dispatcher 收缩、上下文查询化、checkpoint、UI/MCP 统一事件主线、验收指标
- 明确未覆盖：独立进程化 server/dispatcher、完整多 agent 扩展、数据库替代 JSONL

### Placeholder scan
- 未使用 TBD/TODO/后续补充 等占位词作为任务内容
- 每个任务都给出文件落点、接口方向、验证命令

### Type consistency
- 计划统一使用 `run_id / task_id / artifact_id / checkpoint_path / ledger_path`
- 统一使用 `artifactRefs` 作为新增对外字段，保留 `artifactPaths` 兼容

---

## 结论

这份计划不是要把 FlagHunter 改造成 Cairn，而是要吸收 Cairn 最值得学的 5 件事：

1. **状态与事件外置**
2. **artifact-first**
3. **调度协议化**
4. **验证独立化**
5. **长任务可交接可恢复**

在你们当前仓库里，最值得优先做的不是“再加更多能力”，而是把这些壳收紧。只要壳收紧了，后续再加题型、加平台、加多 agent、加 Web 面板，系统都会更稳。
