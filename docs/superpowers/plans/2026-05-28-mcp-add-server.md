# MCP Add Server Implementation Plan

> **Status as of 2026-05-29:** this implementation plan has already been executed and should now be read as a historical execution record, not as an open work queue.
>
> Current truth and current availability should be recovered from:
> - `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md`
> - `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_规划文档收口映射_V1.md`
> - commit `da34d67` · `feat(web-console): wire MCP add server flow`
> - contract test `D:\webstudy\FlagHunter\tests\unit\web_console\test_mcp_add_server_contract.py`
> - broader regression baseline `71 passed in 0.53s`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `D:\webstudy\FlagHunter` 的 Settings MCP 区域从只读占位推进为“可读取真实 MCP server 列表，并可最小新增一个 SSE server”的 live 联通能力。

**Architecture:** 保持当前 `aiohttp + React UMD` 结构不变，后端复用 `pentestagent.mcp.manager.MCPManager` 现有配置读写能力，在 `web_server.py` 增加独立 MCP add-server API，并让 `GET /api/settings` 暴露真实 `mcp.servers`。前端只在 `settings.jsx` 的 `McpSec` 增加最小 inline form 与 live availability 逻辑，不把 add-server 混入现有 partial save 主线。

**Tech Stack:** Python 3.10+, `aiohttp`, `pytest`, React 18 UMD, plain JSX, existing `window.API` REST wrapper

---

## 0. File Structure / Change Map

- Modify: `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`
  - 让 `GET /api/settings` 返回真实 `mcp.servers`
  - 新增 `POST /api/settings/mcp/servers`
  - 复用 `MCPManager` 写入 `mcp_servers.json`

- Modify: `D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py`
  - 增加 MCP settings read / write / invalid payload contract tests

- Modify: `D:\webstudy\FlagHunter\web\console\src\api.js`
  - 暴露 `addMcpServer(payload)`

- Modify: `D:\webstudy\FlagHunter\web\console\src\pages\settings.jsx`
  - `McpSec` 改为真实 server 列表 + inline add form
  - 按 connection/API 状态给出 `c.notConnected` / `c.notWired`

- Create: `D:\webstudy\FlagHunter\tests\unit\web_console\test_mcp_add_server_contract.py`
  - 覆盖 API 暴露与 Settings 页 live contract 绑定

- Modify: `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md`
  - 同步本轮接通后边界

---

### Task 1: Backend MCP settings read/write contract

**Files:**
- Modify: `D:\webstudy\FlagHunter\pentestagent\interface\web_server.py`
- Test: `D:\webstudy\FlagHunter\tests\unit\interface\test_web_server.py`

- [ ] **Step 1: Write the failing backend contract tests**

```python
@pytest.mark.asyncio
async def test_settings_payload_includes_real_mcp_servers(web_client: TestClient, tmp_path: Path):
    config_path = tmp_path / "mcp_servers.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "docs-mcp": {
                        "type": "sse",
                        "url": "http://127.0.0.1:8080/sse",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    resp = await web_client.get("/api/settings")

    assert resp.status == 200
    data = await resp.json()
    assert data["mcp"]["servers"] == [
        {
            "name": "docs-mcp",
            "type": "sse",
            "url": "http://127.0.0.1:8080/sse",
            "enabled": True,
            "connected": False,
        }
    ]


@pytest.mark.asyncio
async def test_add_mcp_server_persists_new_sse_server(web_client: TestClient, tmp_path: Path):
    resp = await web_client.post(
        "/api/settings/mcp/servers",
        json={"name": "docs-mcp", "url": "http://127.0.0.1:8080/sse"},
    )

    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["settings"]["mcp"]["servers"][0]["name"] == "docs-mcp"
    raw = json.loads((tmp_path / "mcp_servers.json").read_text(encoding="utf-8"))
    assert raw["mcpServers"]["docs-mcp"]["type"] == "sse"
    assert raw["mcpServers"]["docs-mcp"]["url"] == "http://127.0.0.1:8080/sse"


@pytest.mark.asyncio
async def test_add_mcp_server_rejects_invalid_url(web_client: TestClient):
    resp = await web_client.post(
        "/api/settings/mcp/servers",
        json={"name": "docs-mcp", "url": "not-a-url"},
    )

    assert resp.status == 400
    data = await resp.json()
    assert data["error"] == "valid sse url required"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
D:\webstudy\FlagHunter\.venv\Scripts\python.exe -m pytest tests\unit\interface\test_web_server.py -k mcp -q
```

Expected:
- FAIL because `GET /api/settings` still returns `mcp.servers == []`
- FAIL because `/api/settings/mcp/servers` is not registered yet

- [ ] **Step 3: Write the minimal backend implementation**

```python
from ..mcp.manager import MCPManager


def _mcp_manager_for_project(project_root: Path) -> MCPManager:
    return MCPManager(project_root / "mcp_servers.json")


def _settings_to_api(project_root: Path) -> dict:
    manager = _mcp_manager_for_project(project_root)
    mcp_servers = manager.list_configured_servers()
    return {
        ...,
        "mcp": {
            "enabled": True,
            "servers": [
                {
                    "name": item.get("name", ""),
                    "type": item.get("type", ""),
                    "url": item.get("url", ""),
                    "enabled": bool(item.get("enabled", True)),
                    "connected": bool(item.get("connected", False)),
                }
                for item in mcp_servers
            ],
            "timeoutMs": int(env.get("MCP_TIMEOUT_MS", "30000")),
        },
        ...,
    }


async def post_mcp_server(req: web.Request) -> web.Response:
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    name = str(body.get("name") or "").strip()
    url = str(body.get("url") or "").strip()
    if not name:
        return web.json_response({"error": "name required"}, status=400)
    if not url.startswith("http://") and not url.startswith("https://"):
        return web.json_response({"error": "valid sse url required"}, status=400)

    manager = _mcp_manager_for_project(project_root)
    manager.add_sse_server(name=name, url=url)
    return web.json_response({"ok": True, "settings": _settings_to_api(project_root)})
```

And register:

```python
app.router.add_post("/api/settings/mcp/servers", h["post_mcp_server"])
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
D:\webstudy\FlagHunter\.venv\Scripts\python.exe -m pytest tests\unit\interface\test_web_server.py -k mcp -q
```

Expected:
- PASS with 3 MCP-related tests green

- [ ] **Step 5: Commit**

```powershell
git add tests/unit/interface/test_web_server.py pentestagent/interface/web_server.py
git commit -m "feat(web-console): add MCP server settings API"
```

---

### Task 2: Frontend API wiring and Settings MCP interaction contract

**Files:**
- Modify: `D:\webstudy\FlagHunter\web\console\src\api.js`
- Modify: `D:\webstudy\FlagHunter\web\console\src\pages\settings.jsx`
- Create: `D:\webstudy\FlagHunter\tests\unit\web_console\test_mcp_add_server_contract.py`

- [ ] **Step 1: Write the failing frontend contract tests**

```python
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_api_layer_exposes_add_mcp_server_function() -> None:
    source = _read("web/console/src/api.js")

    assert "async function addMcpServer(payload)" in source
    assert "return apiFetch('/api/settings/mcp/servers', {" in source
    assert "method: 'POST'" in source
    assert "addMcpServer," in source


def test_settings_page_binds_mcp_add_server_to_live_action() -> None:
    source = _read("web/console/src/pages/settings.jsx")

    assert "const addServerAvailable = ['connected', 'degraded'].includes(connection?.status)" in source
    assert "&& typeof window.API?.addMcpServer === 'function';" in source
    assert "const result = await window.API.addMcpServer({ name: addServerForm.name, url: addServerForm.url });" in source
    assert "const merged = mergeSettings(result.settings || draft);" in source
    assert "disabled={true} title={t('st.actionReadOnly')}>{t('st.mcp.addServer')}" not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
D:\webstudy\FlagHunter\.venv\Scripts\python.exe -m pytest tests\unit\web_console\test_mcp_add_server_contract.py -q
```

Expected:
- FAIL because `addMcpServer` does not exist in `api.js`
- FAIL because `settings.jsx` still has the permanent read-only button

- [ ] **Step 3: Write the minimal frontend implementation**

```javascript
async function addMcpServer(payload) {
  return apiFetch('/api/settings/mcp/servers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
```

And in `McpSec`:

```javascript
const [addingServer, setAddingServer] = uSt(false);
const [addServerForm, setAddServerForm] = uSt({ name: '', url: '' });
const [addServerState, setAddServerState] = uSt({ error: '', saving: false });
const addServerAvailable = ['connected', 'degraded'].includes(connection?.status)
  && typeof window.API?.addMcpServer === 'function';
const addServerUnavailableReason = ['connected', 'degraded'].includes(connection?.status)
  ? t('c.notWired')
  : t('c.notConnected');

async function handleAddServer() {
  const result = await window.API.addMcpServer({ name: addServerForm.name, url: addServerForm.url });
  if (!result?.ok) {
    setAddServerState({ error: t('c.failed'), saving: false });
    return;
  }
  const merged = mergeSettings(result.settings || draft);
  // refresh draft/base/meta here
}
```

Render an inline form with:

```jsx
<input className="input" value={addServerForm.name} />
<input className="input mono" value={addServerForm.url} />
<button className="btn sm">{t('c.save')}</button>
<button className="btn sm ghost">{t('c.cancel')}</button>
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
D:\webstudy\FlagHunter\.venv\Scripts\python.exe -m pytest tests\unit\web_console\test_mcp_add_server_contract.py -q
```

Expected:
- PASS with both frontend MCP contract tests green

- [ ] **Step 5: Commit**

```powershell
git add web/console/src/api.js web/console/src/pages/settings.jsx tests/unit/web_console/test_mcp_add_server_contract.py
git commit -m "feat(web-console): wire MCP add server action"
```

---

### Task 3: Fresh verify and docs sync

**Files:**
- Modify: `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md`
- Optional evidence update: `D:\webstudy\FlagHunter\docs\web-console\FlagHunter_Web可视化控制台_当前可用性Smoke验证证据_V1.json`

- [ ] **Step 1: Run the focused MCP regression slice**

Run:

```powershell
D:\webstudy\FlagHunter\.venv\Scripts\python.exe -m pytest tests\unit\interface\test_web_server.py tests\unit\web_console\test_mcp_add_server_contract.py -q
```

Expected:
- PASS for backend + frontend MCP add-server contract tests

- [ ] **Step 2: Run the broader current mainline verify slice**

Run:

```powershell
D:\webstudy\FlagHunter\.venv\Scripts\python.exe -m pytest tests\unit\interface\test_web_server.py tests\unit\web_console\test_non_mainline_mock_retirement.py tests\unit\web_console\test_settings_truth_source.py tests\unit\web_console\test_traces_drawer_truth_source.py tests\unit\web_console\test_tasks_traces_empty_state_i18n.py tests\unit\web_console\test_capability_reason_copy.py tests\unit\web_console\test_trace_replay_contract.py tests\unit\web_console\test_task_retry_contract.py tests\unit\web_console\test_task_continue_contract.py tests\unit\web_console\test_knowledge_reindex_contract.py tests\unit\web_console\test_runtime_test_contract.py tests\unit\web_console\test_knowledge_add_doc_contract.py tests\unit\web_console\test_knowledge_open_file_contract.py tests\unit\web_console\test_dashboard_filters_contract.py tests\unit\web_console\test_traces_filters_contract.py tests\unit\web_console\test_mcp_add_server_contract.py -q
```

Expected:
- PASS with MCP add-server slice folded into the current stable regression pack

- [ ] **Step 3: Sync docs to current truth**

Update the availability doc to move MCP add-server from “planned frozen design” to “live minimal contract available” and state the first-version boundary explicitly:

```markdown
- `MCP add server`
  - first version supports SSE only
  - independent action, not part of Settings Save changes
  - no edit / delete / bearer / test-connect yet
```

- [ ] **Step 4: Commit**

```powershell
git add docs/web-console/FlagHunter_Web可视化控制台_当前可用性收口与使用边界_V1.md tests/unit/interface/test_web_server.py tests/unit/web_console/test_mcp_add_server_contract.py pentestagent/interface/web_server.py web/console/src/api.js web/console/src/pages/settings.jsx
git commit -m "docs(web-console): sync MCP add server availability"
```

---

## Self-review

- Spec coverage check:
  - covered real `mcp.servers` read path
  - covered `POST /api/settings/mcp/servers`
  - covered invalid payload rejection
  - covered Settings live contract wiring
- Placeholder scan:
  - no `TODO` / `TBD`
  - each task includes exact files, commands, and expected outcomes
- Type consistency:
  - payload names use `name` + `url`
  - frontend function name uses `addMcpServer`
  - endpoint is consistently `/api/settings/mcp/servers`
