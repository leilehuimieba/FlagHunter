# Web Console Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `D:\webstudy\FlagHunter` 的 Web Console 一期改造成“主流程不依赖 mock、任务详情对话优先、全局状态可信、笔记本到桌面都可用”的最小可用控制台。

**Architecture:** 先稳定后端任务详情契约与前端连接状态真相来源，再把 viewport / i18n / Topbar 语义统一进同一套状态模型，随后分别完成 Dashboard 真值化与 Tasks 主工作区重构。实现保持现有 `aiohttp + React UMD + Babel script tags` 结构，不引入新框架，只做最小必要的契约补强、组件消费调整和响应式样式重排。

**Tech Stack:** Python 3.10+, `aiohttp`, `pytest`, React 18 UMD, Babel standalone, plain JSX scripts, CSS Grid/Flexbox

---

## 0. File Structure / Change Map

### Backend files

- Modify: `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`
  - 稳定任务详情 payload
  - 增加 `capabilities`
  - 保持 dashboard 空态稳定
  - 维持 SSE 为增量事实源

- Create: `D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py`
  - 覆盖 `create_app()` API 契约
  - 验证 `/api/status`、`/api/dashboard/summary`、`/api/tasks/{taskId}`、`/api/tasks/{taskId}/hint`、`/api/tasks/{taskId}/attachments`

### Frontend files

- Modify: `D:\webstudy\FlagHunter\web\console\index.html`
  - 修复固定 `width=1440` viewport
  - 使 1280/1440+ 响应式布局真正生效

- Modify: `D:\webstudy\FlagHunter\web\console\src\api.js`
  - 统一连接状态表达
  - 暴露 `getConnectionState()`
  - 保留 SSE 增量职责

- Modify: `D:\webstudy\FlagHunter\web\console\src\app.jsx`
  - 提升任务详情视图模式状态到 App 层
  - 让 `Topbar` 与 `TasksPage` 共享 detail mode

- Modify: `D:\webstudy\FlagHunter\web\console\src\shell.jsx`
  - Sidebar / Topbar 改用统一连接状态语义
  - 在任务详情路由显示唯一的 mode toggle 入口
  - 去掉 `live/mock` 二元语义

- Modify: `D:\webstudy\FlagHunter\web\console\src\pages\dashboard.jsx`
  - 去掉 dashboard 主路径对 `MOCK.DASHBOARD` / `offlineFlags()` 的依赖
  - 改成真实数据 + 可信空态

- Modify: `D:\webstudy\FlagHunter\web\console\src\pages\tasks.jsx`
  - 去掉 `task_002` 默认依赖
  - 使用后端 `capabilities`
  - 重构任务详情信息层级
  - 完整拆除默认主流程里的 mock panel / mock messages / mock obs
  - 落地 conversation-first / analysis-first 双模式

- Modify: `D:\webstudy\FlagHunter\web\console\src\styles.css`
  - 收紧 sidebar / topbar 状态样式
  - 重构 tasks 布局
  - 增加 detail mode 响应式规则
  - 支持 1280 与 1440+ 两档主要行为

- Modify: `D:\webstudy\FlagHunter\web\console\src\i18n.js`
  - 用 connected / degraded / reconnecting / disconnected 文案替换 `sidebar.live/sidebar.mock`
  - 调整 dashboard subtitle 文案，移除 demo 叙事
  - 增加 `td.modeConversation` / `td.modeAnalysis`
  - 保留 `continue unavailable` 类提示，但改成 capability 语义

### Optional compatibility file

- Keep as-is in phase 1: `D:\webstudy\FlagHunter\web\console\src\mock.js`
  - 允许继续存在作为开发辅助
  - 但不再作为主流程默认真相来源

### Existing local modifications to preserve

当前工作区已经有未提交改动：

- `D:\webstudy\FlagHunter\pentestagent\interface\main.py`
- `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`

执行实现前先运行 `git diff -- D:\webstudy\FlagHunter\pentestagent\interface\web_server.py D:\webstudy\FlagHunter\pentestagent\interface\main.py`，避免覆盖已有本地工作。

### Locked interface decisions for execution

这些接口决策在执行时不再发散：

1. **Task detail mode 只保留一个交互入口：Topbar。**
   - `shell.jsx` 的 `Topbar` 是唯一切换入口。
   - `tasks.jsx` 的 detail header 只展示当前模式状态，不再重复放两个 mode buttons。

2. **`GET /api/tasks/{taskId}` 是 task detail baseline truth。**
   - SSE 仅做增量 merge。

3. **`mock.js` 仍可留仓库，但 Tasks / Dashboard / Topbar 主路径不能再依赖 `task_002` / `MOCK.DASHBOARD` / `MOCK.MESSAGES_002` / `MOCK.TASK_002_PANEL`。**

### Frontend verification policy

当前仓库没有 Web Console 专门的前端单测 / 组件测试基座。本期验证策略明确为：

- 后端 API 契约：`pytest`
- 前端主流程：本地启动后手工验收
- 重点手工验收分辨率：`1280px`、`1366px`、`1440px+`

---

### Task 1: Backend truth-source contract for Dashboard + Task Detail

**Files:**
- Modify: `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py:213-215`
- Modify: `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py:752-846`
- Modify: `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py:1849-2239`
- Test: `D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py`

- [ ] **Step 1: Write the failing backend contract tests**

```python
from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pentestagent.interface import web_server


@pytest.fixture
async def web_client(tmp_path: Path):
    web_server._tasks.clear()
    web_server._task_threads.clear()
    web_server._aggregator = web_server.DashboardAggregator()
    app = web_server.create_app(tmp_path)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_status_endpoint_returns_stable_shape(web_client: TestClient):
    resp = await web_client.get("/api/status")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert "version" in data
    assert "runtime" in data
    assert set(data["tasks"].keys()) == {"total", "running"}


@pytest.mark.asyncio
async def test_status_endpoint_tracks_running_task_counts(web_client: TestClient):
    web_server._tasks["task_manual"] = {
        "id": "task_manual",
        "title": "manual",
        "target": "http://example.test",
        "goal": "observe",
        "status": "running",
        "createdAt": web_server._now_iso(),
        "startedAt": web_server._now_iso(),
        "finishedAt": None,
        "tokensUsed": 0,
        "toolCalls": 0,
        "finalFlag": None,
        "stopReason": None,
        "currentRunId": "run_manual",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    resp = await web_client.get("/api/status")
    data = await resp.json()
    assert data["tasks"]["total"] >= 1
    assert data["tasks"]["running"] >= 1


@pytest.mark.asyncio
async def test_dashboard_summary_uses_truthful_empty_defaults(web_client: TestClient):
    resp = await web_client.get("/api/dashboard/summary")
    assert resp.status == 200
    data = await resp.json()
    assert data["kpis"]["running"] == 0
    assert data["kpis"]["queued"] == 0
    assert data["flags"] == []
    assert data["recentTasks"] == []
    assert data["recentToolCalls"] == []
    assert isinstance(data["alerts"], list)


@pytest.mark.asyncio
async def test_dashboard_summary_never_omits_required_collections(web_client: TestClient):
    resp = await web_client.get("/api/dashboard/summary")
    data = await resp.json()
    for key in [
        "tokenSeries",
        "toolDistribution",
        "failureDistribution",
        "knowledgeHitTrend",
        "flags",
        "recentTasks",
        "recentToolCalls",
        "alerts",
    ]:
        assert key in data
        assert isinstance(data[key], list)


@pytest.mark.asyncio
async def test_task_detail_includes_capabilities_and_detail_fields(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "demo", "target": "http://example.test", "goal": "collect state"},
    )
    assert created.status == 201
    task = await created.json()

    detail_resp = await web_client.get(f"/api/tasks/{task['id']}")
    assert detail_resp.status == 200
    detail = await detail_resp.json()

    assert detail["id"] == task["id"]
    assert "messages" in detail
    assert "detailSource" in detail
    assert "plan" in detail
    assert "notes" in detail
    assert "knowledgeHits" in detail
    assert "attachments" in detail
    assert "capabilities" in detail
    assert detail["capabilities"] == {
        "hint": True,
        "stop": True,
        "continue": False,
        "retry": False,
        "attachments": True,
    }


@pytest.mark.asyncio
async def test_task_detail_defaults_remain_lists_and_bool_capabilities(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "layout", "target": "http://layout.test", "goal": "read detail"},
    )
    task = await created.json()
    detail_resp = await web_client.get(f"/api/tasks/{task['id']}")
    detail = await detail_resp.json()

    assert isinstance(detail["messages"], list)
    assert isinstance(detail["plan"], list)
    assert isinstance(detail["notes"], list)
    assert isinstance(detail["knowledgeHits"], list)
    assert isinstance(detail["attachments"], list)
    assert isinstance(detail["capabilities"]["hint"], bool)
    assert isinstance(detail["capabilities"]["stop"], bool)


@pytest.mark.asyncio
async def test_hint_endpoint_persists_hint_and_emits_supported_shape(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "demo", "target": "http://example.test", "goal": "collect state"},
    )
    task = await created.json()

    hint_resp = await web_client.post(
        f"/api/tasks/{task['id']}/hint",
        json={"text": "focus on admin surface"},
    )
    assert hint_resp.status == 200
    hint_result = await hint_resp.json()
    assert hint_result["ok"] is True

    detail_resp = await web_client.get(f"/api/tasks/{task['id']}")
    detail = await detail_resp.json()
    assert detail["hints"][-1]["text"] == "focus on admin surface"


@pytest.mark.asyncio
async def test_attachments_endpoint_returns_empty_list_when_no_files(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "demo", "target": "http://example.test", "goal": "collect state"},
    )
    task = await created.json()

    resp = await web_client.get(f"/api/tasks/{task['id']}/attachments")
    assert resp.status == 200
    data = await resp.json()
    assert data == {"taskId": task["id"], "files": []}
```

- [ ] **Step 2: Run tests to verify they fail on missing capabilities / defaults**

Run:

```bash
python -m pytest D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py -v
```

Expected:

```text
FAILED test_task_detail_includes_capabilities_and_detail_fields
E   AssertionError: assert 'capabilities' in detail
```

- [ ] **Step 3: Implement explicit task capabilities and stable detail defaults**

Add these helpers into `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py` near `_serialize_task`:

```python
def _task_capabilities(task: dict[str, Any]) -> dict[str, bool]:
    status = str(task.get("status") or "")
    return {
        "hint": True,
        "stop": status in {"queued", "running"},
        "continue": False,
        "retry": False,
        "attachments": True,
    }


def _task_detail_defaults() -> dict[str, Any]:
    return {
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "hints": [],
        "attachments": [],
        "capabilities": {
            "hint": True,
            "stop": False,
            "continue": False,
            "retry": False,
            "attachments": True,
        },
    }
```

Patch `_serialize_task()` so it always normalizes detail collections:

```python
def _serialize_task(task: dict[str, Any]) -> dict[str, Any]:
    item = dict(task)
    item["durationMs"] = _duration_ms_for_task(item)
    item["hints"] = [
        hint for hint in (item.get("hints") or [])
        if isinstance(hint, dict)
    ]
    item.setdefault("messages", [])
    item.setdefault("plan", [])
    item.setdefault("notes", [])
    item.setdefault("knowledgeHits", [])
    item.setdefault("attachments", [])
    item["capabilities"] = _task_capabilities(item)
    return item
```

Patch `_task_detail_payload()` so the final payload always publishes stable collections and capabilities:

```python
def _task_detail_payload(project_root: Path, task: dict[str, Any]) -> dict[str, Any]:
    item = _serialize_task(task)
    defaults = _task_detail_defaults()
    metrics = _pick_metrics_for_task(project_root, item)
    ...
    item["messages"] = messages or defaults["messages"]
    item["plan"] = plan or defaults["plan"]
    item["notes"] = notes or defaults["notes"]
    item["detailSource"] = detail_source
    item["knowledgeHits"] = knowledge_hits or defaults["knowledgeHits"]
    item["attachments"] = item.get("attachments") or defaults["attachments"]
    item["capabilities"] = _task_capabilities(item)
    return item
```

Patch `post_task()` so new tasks start with explicit empty collections:

```python
task = {
    "id": tid,
    "title": payload.get("title") or payload.get("target", ""),
    "target": payload.get("target", ""),
    "goal": payload.get("goal", ""),
    "ctfType": payload.get("ctfType", "web"),
    "detectedType": payload.get("ctfType", "web"),
    "mode": payload.get("mode", "agent"),
    "maxIter": payload.get("maxIter", 30),
    "docker": payload.get("docker", False),
    "flagFormat": payload.get("flagFormat", r"flag\{[^}]+\}"),
    "status": "queued",
    "createdAt": _now_iso(),
    "startedAt": None,
    "finishedAt": None,
    "tokensUsed": 0,
    "toolCalls": 0,
    "finalFlag": None,
    "stopReason": None,
    "currentRunId": rid,
    "sparkSeed": [1, 1, 1, 1],
    "hints": [],
    "messages": [],
    "plan": [],
    "notes": [],
    "knowledgeHits": [],
    "attachments": [],
}
```

- [ ] **Step 4: Re-run the targeted backend contract tests**

Run:

```bash
python -m pytest D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py -v
```

Expected:

```text
PASSED test_status_endpoint_returns_stable_shape
PASSED test_status_endpoint_tracks_running_task_counts
PASSED test_dashboard_summary_uses_truthful_empty_defaults
PASSED test_dashboard_summary_never_omits_required_collections
PASSED test_task_detail_includes_capabilities_and_detail_fields
PASSED test_task_detail_defaults_remain_lists_and_bool_capabilities
PASSED test_hint_endpoint_persists_hint_and_emits_supported_shape
PASSED test_attachments_endpoint_returns_empty_list_when_no_files
```

- [ ] **Step 5: Commit the backend contract slice**

```bash
git add D:\webstudy\FlagHunter\pentestagent\interface\web_server.py D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py
git commit -m "feat(web): add stable task detail contract for mission control"
```

---

### Task 2: Viewport, i18n, and connection-state convergence

**Files:**
- Modify: `D:\webstudy\FlagHunter\web\console\index.html:1-20`
- Modify: `D:\webstudy\FlagHunter\web\console\src\api.js:1-274`
- Modify: `D:\webstudy\FlagHunter\web\console\src\app.jsx:1-83`
- Modify: `D:\webstudy\FlagHunter\web\console\src\shell.jsx:24-384`
- Modify: `D:\webstudy\FlagHunter\web\console\src\styles.css:184-332`
- Modify: `D:\webstudy\FlagHunter\web\console\src\i18n.js`
- Test: `D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py`

- [ ] **Step 1: Confirm the current responsive blocker and translation drift before editing**

Run:

```bash
rg -n "width=1440|sidebar.live|sidebar.mock|dash.sub|dash.liveSub|td.continueUnavailable" D:\webstudy\FlagHunter\web\console\index.html D:\webstudy\FlagHunter\web\console\src\i18n.js D:\webstudy\FlagHunter\web\console\src\shell.jsx D:\webstudy\FlagHunter\web\console\src\pages\dashboard.jsx
```

Expected:

```text
D:\webstudy\FlagHunter\web\console\index.html:5:  <meta name="viewport" content="width=1440" />
D:\webstudy\FlagHunter\web\console\src\i18n.js:...: 'sidebar.live'
D:\webstudy\FlagHunter\web\console\src\i18n.js:...: 'sidebar.mock'
D:\webstudy\FlagHunter\web\console\src\pages\dashboard.jsx:...: : t('dash.sub');
```

- [ ] **Step 2: Fix viewport so responsive CSS can actually work**

Patch `D:\webstudy\FlagHunter\web\console\index.html`:

```html
<meta name="viewport" content="width=device-width, initial-scale=1" />
```

This replacement is mandatory, not optional. Do not keep any fixed-width viewport variant in phase 1.

- [ ] **Step 3: Implement a single connection-state model in `api.js`**

Patch `D:\webstudy\FlagHunter\web\console\src\api.js` so it exports a structured connection snapshot:

```javascript
window.FH_CONNECTION = {
  status: 'connecting',
  isLive: false,
  via: 'probe',
  probeFailures: 0,
  sseFresh: false,
  lastSseAt: 0,
};

function _syncConnection(partial) {
  window.FH_CONNECTION = {
    ...window.FH_CONNECTION,
    ...partial,
    isLive: partial.isLive != null ? !!partial.isLive : window.FH_CONNECTION.isLive,
    sseFresh: _isSseFresh(),
    lastSseAt: _liveState.lastSseAt,
    probeFailures: _liveState.probeFailures,
  };
}

function getConnectionState() {
  return {
    ...window.FH_CONNECTION,
    sseFresh: _isSseFresh(),
    lastSseAt: _liveState.lastSseAt,
    probeFailures: _liveState.probeFailures,
  };
}
```

Update the success path in `probe()`:

```javascript
_liveState.probeFailures = 0;
const was = window.IS_LIVE;
window.IS_LIVE = true;
_syncConnection({
  status: 'connected',
  isLive: true,
  via: 'probe',
});
if (!was) _fire('connected', { ...data, via: 'probe', connection: getConnectionState() });
```

Update the failure path in `probe()`:

```javascript
if (_liveState.probeFailures < PROBE_FAILURE_THRESHOLD) {
  _syncConnection({
    status: 'reconnecting',
    isLive: !!window.IS_LIVE,
    via: 'probe',
  });
  return false;
}
if (_isSseFresh()) {
  _syncConnection({
    status: 'degraded',
    isLive: true,
    via: 'sse_recent',
  });
  return false;
}
const was = window.IS_LIVE;
window.IS_LIVE = false;
_syncConnection({
  status: 'disconnected',
  isLive: false,
  via: 'probe_failures',
});
if (was) _fire('disconnected', { via: 'probe_failures', connection: getConnectionState() });
```

Expose it from `window.API`:

```javascript
window.API = {
  probe, getStatus, getSettings, putSettings,
  getDashboard, getTasks, createTask, getTask, stopTask, hintTask,
  getTraces, getTrace, getLogs, getKnowledge, getKnowledgeDoc, subscribeEvents,
  getMemory, getMemoryStats, getMemoryEntry, muteMemoryEntry, activateMemoryEntry, deleteMemoryEntry, getMemoryGraph,
  getAttachments, uploadAttachment,
  getConnectionState,
};
```

- [ ] **Step 4: Lift task detail mode state into `app.jsx` and keep Topbar as the only toggle entry**

Patch `D:\webstudy\FlagHunter\web\console\src\app.jsx`:

```javascript
const [taskViewMode, setTaskViewMode] = uA(() => {
  return localStorage.getItem('fh:task-view-mode') || 'conversation';
});

uAE(() => {
  localStorage.setItem('fh:task-view-mode', taskViewMode);
}, [taskViewMode]);
```

Pass it into the shell and tasks page:

```jsx
<Topbar
  route={crumbRoute}
  leaf={crumbLeaf}
  taskViewMode={taskViewMode}
  onTaskViewModeChange={setTaskViewMode}
/>
...
{route.startsWith('tasks') && (
  <TasksPage
    taskId={route.split('/')[1]}
    onNav={nav}
    taskViewMode={taskViewMode}
    onTaskViewModeChange={setTaskViewMode}
  />
)}
```

- [ ] **Step 5: Update `shell.jsx` and `i18n.js` to use the same state vocabulary**

Patch `D:\webstudy\FlagHunter\web\console\src\shell.jsx` so `Sidebar` and `Topbar` consume `window.API.getConnectionState()` instead of the `live/mock` binary:

```javascript
function connectionLabel(connection) {
  if (!connection) return t('conn.connecting');
  if (connection.status === 'connected') return t('conn.connected');
  if (connection.status === 'degraded') return t('conn.degraded');
  if (connection.status === 'reconnecting') return t('conn.reconnecting');
  if (connection.status === 'connecting') return t('conn.connecting');
  return t('conn.disconnected');
}

function connectionTone(connection) {
  const key = connection?.status || 'connecting';
  return ['connected', 'degraded', 'reconnecting', 'disconnected', 'connecting'].includes(key)
    ? key
    : 'connecting';
}
```

Inside `Sidebar` initialize and update connection state from `getConnectionState()`:

```javascript
const [connection, setConnection] = useStateS(
  window.API?.getConnectionState?.() || { status: 'connecting', isLive: false }
);
```

Replace the badge render:

```jsx
<span className={`conn-badge ${connectionTone(connection)}`}>
  {connectionLabel(connection)}
</span>
```

Patch `Topbar` signature and keep the **only** mode toggle here:

```javascript
function Topbar({ route, leaf, taskViewMode, onTaskViewModeChange }) {
```

```jsx
{route === 'tasks/detail' && (
  <button
    className="icon-btn"
    title={taskViewMode === 'conversation' ? t('td.modeAnalysis') : t('td.modeConversation')}
    onClick={() => onTaskViewModeChange(taskViewMode === 'conversation' ? 'analysis' : 'conversation')}
  >
    {taskViewMode === 'conversation' ? '◫' : '▥'}
  </button>
)}
```

For the notification empty subtitle, stop using `sidebar.mock`:

```jsx
<div className="sub">
  {connection?.status === 'connected' ? t('top.notifLive') : t('conn.disconnected')}
</div>
```

Patch `D:\webstudy\FlagHunter\web\console\src\i18n.js` by replacing old live/mock vocabulary and adding explicit mode keys:

```javascript
'conn.connecting': 'connecting',
'conn.connected': 'connected',
'conn.degraded': 'degraded',
'conn.reconnecting': 'reconnecting',
'conn.disconnected': 'disconnected',
'dash.sub': 'system overview · waiting for live dashboard data',
'dash.liveSub': 'live summary · {0} tasks / {1} success / {2} failed / {3} stopped',
'td.modeConversation': 'Conversation-first',
'td.modeAnalysis': 'Analysis-first',
'td.continueUnavailable': 'continue is currently unsupported by backend capabilities — use inject hint instead',
```

And the Chinese block:

```javascript
'conn.connecting': '连接中',
'conn.connected': '已连接',
'conn.degraded': '降级',
'conn.reconnecting': '重连中',
'conn.disconnected': '已断开',
'dash.sub': '系统总览 · 正在等待实时 dashboard 数据',
'dash.liveSub': '实时汇总 · {0} 任务 / {1} 成功 / {2} 失败 / {3} 停止',
'td.modeConversation': '对话优先',
'td.modeAnalysis': '分析优先',
'td.continueUnavailable': '后端 capability 当前不支持 continue，请先使用“注入提示”',
```

After adding the new keys, remove UI dependencies on `sidebar.live` and `sidebar.mock` from the changed files.

- [ ] **Step 6: Update status styles to support `connected / degraded / reconnecting / disconnected / connecting`**

Patch `D:\webstudy\FlagHunter\web\console\src\styles.css`:

```css
.conn-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 999px;
  border: 1px solid var(--line-2);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.conn-badge.connected {
  color: var(--accent);
  border-color: var(--accent-dim);
  background: rgba(107,230,117,0.08);
}
.conn-badge.degraded {
  color: var(--amber);
  border-color: rgba(255,181,71,0.35);
  background: rgba(255,181,71,0.08);
}
.conn-badge.reconnecting,
.conn-badge.connecting {
  color: var(--blue);
  border-color: rgba(93,168,255,0.35);
  background: rgba(93,168,255,0.08);
}
.conn-badge.disconnected {
  color: var(--fg-2);
  border-color: var(--line-2);
  background: var(--bg-2);
}
```

- [ ] **Step 7: Run backend tests and start the console for manual state verification**

Run:

```bash
python -m pytest D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py -v
python -m pentestagent web --host 127.0.0.1 --port 3000
```

Manual verification checklist:

```text
1. Open http://127.0.0.1:3000/
2. Confirm the page scales with browser width after viewport fix; no fixed 1440 layout remains.
3. Confirm sidebar badge no longer says mock/live; it uses connected-style states.
4. Confirm topbar remains stable when SSE is idle.
5. Confirm task detail route shows the single mode toggle button in Topbar only.
6. Confirm there is no second conversation/analysis toggle duplicated inside task detail header.
```

- [ ] **Step 8: Commit the viewport + connection-state slice**

```bash
git add D:\webstudy\FlagHunter\web\console\index.html D:\webstudy\FlagHunter\web\console\src\api.js D:\webstudy\FlagHunter\web\console\src\app.jsx D:\webstudy\FlagHunter\web\console\src\shell.jsx D:\webstudy\FlagHunter\web\console\src\styles.css D:\webstudy\FlagHunter\web\console\src\i18n.js D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py
git commit -m "feat(web): unify viewport and connection semantics"
```

---

### Task 3: Dashboard truthification and mock-retirement from the homepage

**Files:**
- Modify: `D:\webstudy\FlagHunter\web\console\src\pages\dashboard.jsx:1-244`
- Modify: `D:\webstudy\FlagHunter\web\console\src\i18n.js`
- Test: `D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py`

- [ ] **Step 1: Confirm the dashboard still references demo fallback paths**

Run:

```bash
rg -n "MOCK\.DASHBOARD|offlineFlags\(|dash\.sub" D:\webstudy\FlagHunter\web\console\src\pages\dashboard.jsx D:\webstudy\FlagHunter\web\console\src\i18n.js
```

Expected:

```text
D:\webstudy\FlagHunter\web\console\src\pages\dashboard.jsx:...: const d = MOCK.DASHBOARD;
D:\webstudy\FlagHunter\web\console\src\pages\dashboard.jsx:...: offlineFlags(
```

- [ ] **Step 2: Keep the backend contract honest for dashboard empty states**

Run:

```bash
python -m pytest D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py -k dashboard -v
```

Expected:

```text
PASSED test_dashboard_summary_uses_truthful_empty_defaults
PASSED test_dashboard_summary_never_omits_required_collections
```

- [ ] **Step 3: Remove mock fallback from `DashboardPage` happy path**

Patch `D:\webstudy\FlagHunter\web\console\src\pages\dashboard.jsx` so it no longer defaults to `MOCK.DASHBOARD`:

```javascript
/* global React, fmt, t */
```

Replace the data bootstrap:

```javascript
const EMPTY_DASHBOARD = {
  kpis: {
    running: 0,
    queued: 0,
    tasksToday: 0,
    successToday: 0,
    failedToday: 0,
    stoppedToday: 0,
    successRate: 0,
    dailyTokens: 0,
    estimatedCost: 0,
    toolCalls: 0,
    knowledgeHits: 0,
  },
  tokenSeries: [],
  toolDistribution: [],
  failureDistribution: [],
  knowledgeHitTrend: [],
  alerts: [],
  recentTasks: [],
  recentToolCalls: [],
  recentNotes: [],
  recentArtifacts: [],
  flags: [],
};
```

Replace the current fallback line:

```javascript
const dashboardData = liveData || EMPTY_DASHBOARD;
const { flags, copyFlag, copiedId } = useFlagBoard(dashboardData.flags, []);
```

Replace the subtitle logic:

```javascript
const dashboardSub = window.IS_LIVE
  ? t('dash.liveSub', kpis.tasksToday || 0, kpis.successToday || 0, kpis.failedToday || 0, kpis.stoppedToday || 0)
  : t('dash.sub');
```

Replace KPI spark fallback usage with null-safe real data only:

```javascript
spark={tokenSeries.length ? <Sparkline data={tokenSeries.map(s => s.v)} w={56} h={20} /> : null}
```

Use `<Empty>{t('c.unavailable')}</Empty>` or `<Empty>{t('tasks.noMatch')}</Empty>` instead of mock-driven visual filler in sections that have no data.

- [ ] **Step 4: Keep navigation and notifications real-data-driven**

Patch `recentTasks` / `recentToolCalls` rendering so it is entirely based on API data:

```javascript
{recentTasks.length ? recentTasks.map(tk => (
  <div key={tk.id} className="act-row" onClick={() => onNav(`tasks/${tk.id}`)} style={{ cursor: 'pointer' }}>
    <span className="time">{tk.startedAt ? fmt.hh(tk.startedAt).slice(0, 5) : '—'}</span>
    <span className="ico" style={{ color: { running: 'var(--amber)', success: 'var(--accent)', failed: 'var(--red)', queued: 'var(--blue)', stopped: 'var(--fg-2)' }[tk.status] }}>●</span>
    <span className="ttl ellipsis"><span className="dim" style={{ marginRight: 6 }}>{tk.id}</span>{tk.title}</span>
    <span className="meta"><StatusBadge status={tk.status} /></span>
  </div>
)) : <Empty>{t('tasks.noMatch')}</Empty>}
```

Do not reintroduce `offlineFlags()` or `MOCK.DASHBOARD` anywhere in the file.

- [ ] **Step 5: Run backend tests and manual homepage verification**

Run:

```bash
python -m pytest D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py -k dashboard -v
python -m pentestagent web --host 127.0.0.1 --port 3000
```

Manual verification checklist:

```text
1. Dashboard loads without crashing when no tasks exist.
2. Empty sections say "no data" / unavailable instead of showing demo-like activity.
3. Creating a real task updates recent tasks after SSE refresh.
4. Flags panel appears only when real flags exist.
5. Browser width changes below/above 1440 do not break dashboard header or primary action placement.
```

- [ ] **Step 6: Commit the dashboard slice**

```bash
git add D:\webstudy\FlagHunter\web\console\src\pages\dashboard.jsx D:\webstudy\FlagHunter\web\console\src\i18n.js D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py
git commit -m "feat(web): truthify mission control dashboard"
```

---

### Task 4: Tasks workspace truthification, dual-mode layout, and responsive redesign

**Files:**
- Modify: `D:\webstudy\FlagHunter\web\console\src\pages\tasks.jsx:8-977`
- Modify: `D:\webstudy\FlagHunter\web\console\src\styles.css:574-726`
- Modify: `D:\webstudy\FlagHunter\web\console\src\app.jsx:1-83`
- Modify: `D:\webstudy\FlagHunter\web\console\src\shell.jsx:213-384`
- Modify: `D:\webstudy\FlagHunter\web\console\src\i18n.js`

- [ ] **Step 1: Confirm every remaining mock chain in `tasks.jsx` before refactor**

Run:

```bash
rg -n "task_002|MESSAGES_002|TASK_002_PANEL|isMockActive|SyntheticSidePanel|obsExtras|continueTask|retryTask|TaskDetailSourceBanner" D:\webstudy\FlagHunter\web\console\src\pages\tasks.jsx
```

Expected:

```text
D:\webstudy\FlagHunter\web\console\src\pages\tasks.jsx:9: const initialActiveId = taskId || (window.IS_LIVE ? '' : 'task_002');
D:\webstudy\FlagHunter\web\console\src\pages\tasks.jsx:272: const isMockActive = detailTask.id === 'task_002';
D:\webstudy\FlagHunter\web\console\src\pages\tasks.jsx:326: const panel = isMockActive ? MOCK.TASK_002_PANEL : null;
```

This scan is the checklist baseline. Do not stop after removing only `initialActiveId`; the whole chain must be dealt with.

- [ ] **Step 2: Run the task detail contract tests before UI refactor**

Run:

```bash
python -m pytest D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py -k "task_detail or capabilities" -v
```

Expected:

```text
PASSED test_task_detail_includes_capabilities_and_detail_fields
PASSED test_task_detail_defaults_remain_lists_and_bool_capabilities
```

- [ ] **Step 3: Remove task-page dependence on `task_002` and backend-guess heuristics**

Patch the top of `D:\webstudy\FlagHunter\web\console\src\pages\tasks.jsx`:

```javascript
/* global React, fmt, t, NewTaskModal, fileIcon, downloadJson */
```

Update `TasksPage` signature:

```javascript
function TasksPage({ taskId, onNav, taskViewMode = 'conversation', onTaskViewModeChange }) {
```

Replace the mock-based initial state:

```javascript
const initialActiveId = taskId || '';
const [activeId, setActive] = useStateT(initialActiveId);
const [tasks, setTasks] = useStateT([]);
```

Inside `TaskDetail`, remove the mock gate and switch to capability-based availability:

```javascript
function TaskDetail({ task, onNav, taskViewMode = 'conversation' }) {
  const [detailTask, setDetailTask] = useStateT(task);
  const isActive = detailTask.status === 'running';
  const initialMessages = resolveTaskMessages(detailTask);
  const capabilityMap = detailTask.capabilities || {
    hint: true,
    stop: false,
    continue: false,
    retry: false,
    attachments: true,
  };

  const [messages, setMessages] = useStateT(initialMessages);
  const [hintMode, setHintMode] = useStateT(() => !capabilityMap.continue);
  const [draft, setDraft] = useStateT('');
  const [obsFresh, setObsFresh] = useStateT(null);
  const [attachments, setAttachments] = useStateT(detailTask.attachments || []);
  const msgEnd = useRefT(null);
  const continueAvailable = !!capabilityMap.continue;
  const retryAvailable = !!capabilityMap.retry;
  const hintAvailable = !!capabilityMap.hint;
  const stopAvailable = !!capabilityMap.stop;
```

Replace the route-level render:

```jsx
<TaskDetail
  task={active}
  key={active.id}
  onNav={onNav}
  taskViewMode={taskViewMode}
/>
```

- [ ] **Step 4: Fully remove mock-only detail branches and keep synthetic fallback explicit**

Patch the message / attachment / observation loading logic so it no longer branches on `isMockActive`:

```javascript
useEffectT(() => {
  setMessages(resolveTaskMessages(detailTask));
}, [
  detailTask.id,
  Array.isArray(detailTask.messages) ? detailTask.messages.length : 0,
  detailTask.finishedAt,
  detailTask.finalFlag,
  detailTask.stopReason,
]);

useEffectT(() => {
  if (!window.API || !window.API.getAttachments) return;
  window.API.getAttachments(detailTask.id).then(data => {
    if (data && Array.isArray(data.files)) setAttachments(data.files);
  });
}, [detailTask.id]);

const livePlan = Array.isArray(detailTask.plan) ? detailTask.plan : [];
const liveNotes = Array.isArray(detailTask.notes) ? detailTask.notes : [];
const liveKnowledgeHits = Array.isArray(detailTask.knowledgeHits) ? detailTask.knowledgeHits : [];
const [obs, setObs] = useStateT([]);
```

Delete these mock-only constructs entirely from the file:

```javascript
const isMockActive = detailTask.id === 'task_002';
const panel = isMockActive ? MOCK.TASK_002_PANEL : null;
const obsExtras = [ ... ];
useEffectT(() => {
  if (!isMockActive) return;
  ...
}, [isMockActive]);
```

Keep `buildSyntheticMessages()` and `SyntheticSidePanel`, but reposition them as explicit degraded fallbacks only:

- `resolveTaskMessages()` may call `buildSyntheticMessages()` only when backend `messages` is empty.
- `LiveSidePanel` may internally render a compact degraded summary via `SyntheticSidePanel` when `plan/notes/knowledgeHits/observations` are all empty.
- The route happy path must not special-case `task_002` anymore.

Update `resolveTaskMessages()` to prefer backend truth and only degrade explicitly:

```javascript
function resolveTaskMessages(tk) {
  if (Array.isArray(tk.messages) && tk.messages.length) return tk.messages;
  return buildSyntheticMessages({
    ...tk,
    stopReason: tk.stopReason || 'detail_unavailable',
  });
}
```

Keep `TaskDetailSourceBanner`, but render it based on `detailTask.detailSource`, not on “not mock” conditions:

```jsx
{detailTask.detailSource && <TaskDetailSourceBanner source={detailTask.detailSource} />}
```

- [ ] **Step 5: Restructure the task detail hierarchy and keep Topbar as the only mode switch**

Patch the detail header so it shows grouped identity / description / runtime rows and a passive current-mode label instead of duplicated toggle buttons:

```jsx
<div className="task-detail-head">
  <div className="left">
    <div className="identity-row">
      <StatusBadge status={detailTask.status} size="lg" />
      <TypeBadge type={detailTask.detectedType} />
      <span className="dim mono">{detailTask.id}</span>
      {detailTask.currentRunId && <span className="dim mono">· {detailTask.currentRunId}</span>}
      <span className="chip ghost">{taskViewMode === 'conversation' ? t('td.modeConversation') : t('td.modeAnalysis')}</span>
    </div>
    <div className="title">{detailTask.title}</div>
    <div className="descriptor-row">
      <span>{t('c.target')} <b>{detailTask.target || '—'}</b></span>
      <span>{t('c.goal')} <b>{detailTask.goal || '—'}</b></span>
    </div>
    <div className="runtime-row">
      <span>{t('c.started')} <b>{detailTask.startedAt ? fmt.since(detailTask.startedAt) : '—'}</b></span>
      <span>{t('c.tokens')} <b>{((detailTask.tokensUsed || 0) / 1000).toFixed(1)}k</b></span>
      <span>{t('c.tools')} <b>{detailTask.toolCalls || 0}</b></span>
      {detailTask.finalFlag && <span>{t('c.flag')} <b className="green">{detailTask.finalFlag}</b></span>}
      {detailTask.stopReason && <span>{t('c.stopReason')} <b className="red">{detailTask.stopReason}</b></span>}
    </div>
  </div>
  <div className="actions">
    <button className="btn ghost" onClick={() => downloadJson(`${detailTask.id}.json`, detailTask)}>⤓ {t('c.export')}</button>
    <button className="btn ghost" onClick={() => detailTask.currentRunId && onNav && onNav(`traces/${detailTask.currentRunId}`)}>⧉ {t('c.trace')}</button>
    {isActive && stopAvailable && <button className="btn danger" onClick={handleStop}>■ {t('c.stop')}</button>}
  </div>
</div>
```

Patch composer availability logic:

```javascript
useEffectT(() => {
  if (!continueAvailable && !hintMode) setHintMode(true);
}, [continueAvailable, hintMode]);
```

```jsx
<textarea
  className="input"
  placeholder={hintMode ? t('td.composer.hint') : (continueAvailable ? t('td.composer.continue') : t('td.continueUnavailable'))}
  value={draft}
  onChange={e => setDraft(e.target.value)}
  onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); }}}
  rows={2}
  disabled={hintMode ? !hintAvailable : !continueAvailable}
/>
<button
  className={`btn ${hintMode ? '' : 'primary'}`}
  onClick={send}
  disabled={hintMode ? !hintAvailable : !continueAvailable}
  title={hintMode ? (!hintAvailable ? t('c.unavailable') : '') : (!continueAvailable ? t('td.continueUnavailable') : '')}
>
  {hintMode ? t('td.inject') : t('td.sendBtn')} <span className="kbd">⌘↵</span>
</button>
```

When sending:

```javascript
if (!draft.trim()) return;
if (hintMode && !hintAvailable) return;
if (!hintMode && !continueAvailable) return;
```

- [ ] **Step 6: Implement responsive layout rules in `styles.css`**

Patch `D:\webstudy\FlagHunter\web\console\src\styles.css`:

```css
.tasks-layout {
  display: grid;
  grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
  gap: 10px;
  min-height: 0;
  flex: 1;
}

.task-detail-head {
  padding: 14px 18px;
  border-bottom: 1px solid var(--line-1);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.identity-row,
.descriptor-row,
.runtime-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-size: 11px;
}

.identity-row { margin-bottom: 8px; }
.descriptor-row { margin-top: 8px; color: var(--fg-2); }
.runtime-row { margin-top: 8px; color: var(--fg-2); }

.task-detail-body {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  min-height: 0;
}

.task-detail-body.mode-conversation {
  grid-template-columns: minmax(0, 1fr) 0px;
}

.task-detail-body.mode-conversation .side-panel {
  border-left: none;
  width: 0;
  min-width: 0;
  overflow: hidden;
}

.task-detail-body.mode-analysis {
  grid-template-columns: minmax(0, 1fr) 340px;
}

.task-convo {
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}

.msg-list {
  flex: 1;
  overflow-y: auto;
  padding: 18px 22px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.composer {
  border-top: 1px solid var(--line-1);
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--bg-1);
}

.side-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--bg-1);
  overflow-y: auto;
  border-left: 1px solid var(--line-1);
}

@media (max-width: 1366px) {
  .tasks-layout {
    grid-template-columns: 280px minmax(0, 1fr);
  }
  .task-detail-body.mode-analysis {
    grid-template-columns: minmax(0, 1fr) 300px;
  }
}

@media (max-width: 1280px) {
  .tasks-layout {
    grid-template-columns: 260px minmax(0, 1fr);
  }
  .task-detail-body.mode-analysis {
    grid-template-columns: minmax(0, 1fr);
  }
  .task-detail-body.mode-analysis .side-panel {
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(360px, 38vw);
    box-shadow: -16px 0 40px rgba(0,0,0,0.35);
    z-index: 5;
  }
}
```

- [ ] **Step 7: Run backend tests and perform the primary manual workflow verification**

Run:

```bash
python -m pytest D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py -v
python -m pentestagent web --host 127.0.0.1 --port 3000
```

Manual verification checklist:

```text
1. Dashboard loads empty but credible when no tasks exist.
2. Create a task from Dashboard or Tasks.
3. Open the task detail page.
4. Confirm the detail header is grouped into identity / description / runtime rows.
5. Confirm conversation-first mode makes the message region dominate the page.
6. Confirm analysis-first mode exposes the right-side context panel.
7. At ~1280px width, conversation-first remains comfortable and analysis-first uses overlay behavior instead of permanently crushing the message area.
8. At ~1366px width, analysis-first still keeps usable conversation width.
9. At 1440px+ width, task list + detail + analysis panel can coexist without obvious wasted padding.
10. Hint input remains usable and respects capability-based disable states.
11. Re-run `rg -n "task_002|MESSAGES_002|TASK_002_PANEL|isMockActive" D:\webstudy\FlagHunter\web\console\src\pages\tasks.jsx` and confirm it returns no matches.
```

- [ ] **Step 8: Commit the tasks workspace slice**

```bash
git add D:\webstudy\FlagHunter\web\console\src\pages\tasks.jsx D:\webstudy\FlagHunter\web\console\src\styles.css D:\webstudy\FlagHunter\web\console\src\app.jsx D:\webstudy\FlagHunter\web\console\src\shell.jsx D:\webstudy\FlagHunter\web\console\src\i18n.js D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py
git commit -m "feat(web): redesign mission control tasks workspace"
```

---

## Plan self-review

### Spec coverage

- Topbar / global state → Task 2
- Dashboard truthification → Task 3
- Tasks truthification + dual mode + responsive behavior → Task 4
- Backend task detail contract + capabilities → Task 1
- Mock cleanup from main workflow → Tasks 3 and 4
- Viewport fix for laptop/desktop responsive support → Task 2
- i18n / state vocabulary convergence → Task 2
- Risk control via staging → Task order preserves truth-source-first strategy

### Placeholder scan

- No `TBD`
- No `TODO`
- No “similar to previous task”
- Every task includes concrete file paths, commands, and implementation snippets
- The previous plan gap around `index.html` / `i18n.js` is now closed

### Type / naming consistency

Locked names used consistently throughout the plan:

- `capabilities`
- `getConnectionState()`
- `taskViewMode`
- `conversation`
- `analysis`
- `_task_capabilities()`
- `_task_detail_defaults()`
- `conn.connected`
- `conn.degraded`
- `conn.reconnecting`
- `conn.disconnected`

### Plan-specific risk review

- `Topbar` is now the only mode toggle entry; `tasks.jsx` header does not duplicate toggle buttons.
- `index.html` viewport fix is now mandatory, not optional.
- `i18n.js` is now an explicit modified file, not an implicit side effect.
- `tasks.jsx` mock retirement explicitly covers `task_002`, `MOCK.MESSAGES_002`, `MOCK.TASK_002_PANEL`, `isMockActive`, `panel`, and `obsExtras`.
- Frontend verification strategy is explicitly manual because the repo currently lacks a dedicated console component-test harness.

---

## Notes for execution

Before executing Task 1, review current local diffs in:

- `D:\webstudy\FlagHunter\pentestagent\interface\main.py`
- `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`

to avoid overwriting unrelated local changes.
