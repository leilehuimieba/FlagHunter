from __future__ import annotations

import io
import json
import sys
import types
from pathlib import Path

import pytest
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from pentestagent.interface import web_server
import pentestagent.knowledge as knowledge_module
import pentestagent.interface.initializer as initializer_module


class _NoopThread:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def start(self) -> None:
        return None


@pytest.fixture
async def web_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    web_server._tasks.clear()
    web_server._task_threads.clear()
    web_server._aggregator = web_server.DashboardAggregator()
    monkeypatch.setattr(web_server.threading, "Thread", _NoopThread)
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
    assert data["tasks"]["total"] == 1
    assert data["tasks"]["running"] == 1


def test_task_capabilities_toggle_stop_by_status():
    assert web_server._task_capabilities({"status": "queued"})["stop"] is True
    assert web_server._task_capabilities({"status": "running"})["stop"] is True
    assert web_server._task_capabilities({"status": "success"})["stop"] is False


def test_task_capabilities_toggle_continue_by_status():
    assert web_server._task_capabilities({"status": "queued"})["continue"] is False
    assert web_server._task_capabilities({"status": "running"})["continue"] is True
    assert web_server._task_capabilities({"status": "success"})["continue"] is False
    assert web_server._task_capabilities({"status": "failed"})["continue"] is False
    assert web_server._task_capabilities({"status": "stopped"})["continue"] is False


def test_task_capabilities_toggle_retry_by_status():
    assert web_server._task_capabilities({"status": "queued"})["retry"] is False
    assert web_server._task_capabilities({"status": "running"})["retry"] is False
    assert web_server._task_capabilities({"status": "success"})["retry"] is True
    assert web_server._task_capabilities({"status": "failed"})["retry"] is True
    assert web_server._task_capabilities({"status": "stopped"})["retry"] is True


def test_serialize_task_normalizes_dirty_collections():
    task = {
        "id": "task_dirty",
        "status": "stopped",
        "hints": [{"text": "keep"}, "bad", None],
        "messages": None,
        "plan": "not-a-list",
        "notes": [{"value": "note"}, 1],
        "knowledgeHits": [{"title": "hit"}, "noise"],
        "attachments": [{"name": "file.txt"}, object()],
    }

    serialized = web_server._serialize_task(task)

    assert serialized["hints"] == [{"text": "keep"}]
    assert serialized["messages"] == []
    assert serialized["plan"] == []
    assert serialized["notes"] == [{"value": "note"}]
    assert serialized["knowledgeHits"] == [{"title": "hit"}]
    assert serialized["attachments"] == [{"name": "file.txt"}]
    assert serialized["capabilities"]["stop"] is False


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
async def test_dashboard_summary_supports_window_and_runtime_filters(web_client: TestClient):
    now = web_server._now_iso()
    old = (web_server.datetime.now(web_server.timezone.utc) - web_server.timedelta(days=2)).isoformat()

    web_server._tasks["task_local_recent"] = {
        "id": "task_local_recent",
        "title": "local recent",
        "target": "http://local.test",
        "goal": "recent local",
        "mode": "pentest",
        "modeSubtype": "unknown",
        "goalStyle": "evidence",
        "status": "success",
        "createdAt": now,
        "startedAt": now,
        "finishedAt": now,
        "tokensUsed": 10,
        "toolCalls": 1,
        "docker": False,
        "currentRunId": "run_local_recent",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }
    web_server._tasks["task_docker_old"] = {
        "id": "task_docker_old",
        "title": "docker old",
        "target": "http://docker.test",
        "goal": "old docker",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
        "status": "failed",
        "createdAt": old,
        "startedAt": old,
        "finishedAt": old,
        "tokensUsed": 20,
        "toolCalls": 2,
        "docker": True,
        "currentRunId": "run_docker_old",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    recent_resp = await web_client.get("/api/dashboard/summary?window=24h&runtime=all")
    assert recent_resp.status == 200
    recent_data = await recent_resp.json()
    assert recent_data["kpis"]["tasksToday"] == 1
    assert recent_data["recentTasks"][0]["id"] == "task_local_recent"
    assert recent_data["recentTasks"][0]["mode"] == "pentest"
    assert recent_data["recentTasks"][0]["modeSubtype"] == "unknown"
    assert recent_data["recentTasks"][0]["goalStyle"] == "evidence"

    docker_resp = await web_client.get("/api/dashboard/summary?window=all&runtime=docker")
    assert docker_resp.status == 200
    docker_data = await docker_resp.json()
    assert docker_data["kpis"]["tasksToday"] == 1
    assert docker_data["recentTasks"][0]["id"] == "task_docker_old"
    assert docker_data["recentTasks"][0]["mode"] == "ctf"
    assert docker_data["recentTasks"][0]["modeSubtype"] == "web"
    assert docker_data["recentTasks"][0]["goalStyle"] == "flag"
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
        assert key in docker_data
        assert isinstance(docker_data[key], list)


@pytest.mark.asyncio
async def test_dashboard_summary_flags_prefer_mode_subtype_over_legacy_detected_type(
    web_client: TestClient,
):
    now = web_server._now_iso()
    web_server._tasks["task_flag_contract"] = {
        "id": "task_flag_contract",
        "title": "flag contract",
        "target": "http://flag.test",
        "goal": "capture flag",
        "mode": "ctf",
        "modeSubtype": "crypto",
        "goalStyle": "flag",
        "ctfType": "web",
        "detectedType": "web",
        "status": "success",
        "createdAt": now,
        "startedAt": now,
        "finishedAt": now,
        "tokensUsed": 1,
        "toolCalls": 1,
        "finalFlag": "flag{contract_truth}",
        "currentRunId": "run_flag_contract",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    resp = await web_client.get("/api/dashboard/summary?window=all&runtime=all")

    assert resp.status == 200
    data = await resp.json()
    assert data["flags"][0]["id"] == "task_flag_contract"
    assert data["flags"][0]["type"] == "crypto"


@pytest.mark.asyncio
async def test_traces_list_supports_window_filter(web_client: TestClient):
    now = web_server._now_iso()
    old = (web_server.datetime.now(web_server.timezone.utc) - web_server.timedelta(days=2)).isoformat()

    web_server._tasks["task_trace_recent"] = {
        "id": "task_trace_recent",
        "title": "trace recent",
        "target": "http://recent.test",
        "goal": "recent trace",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
        "status": "success",
        "createdAt": now,
        "startedAt": now,
        "finishedAt": now,
        "tokensUsed": 10,
        "toolCalls": 1,
        "currentRunId": "run_trace_recent",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }
    web_server._tasks["task_trace_old"] = {
        "id": "task_trace_old",
        "title": "trace old",
        "target": "http://old.test",
        "goal": "old trace",
        "mode": "pentest",
        "modeSubtype": "unknown",
        "goalStyle": "evidence",
        "status": "failed",
        "createdAt": old,
        "startedAt": old,
        "finishedAt": old,
        "tokensUsed": 20,
        "toolCalls": 2,
        "currentRunId": "run_trace_old",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    recent_resp = await web_client.get("/api/traces?window=24h")
    assert recent_resp.status == 200
    recent_data = await recent_resp.json()
    assert [item["id"] for item in recent_data["items"]] == ["run_trace_recent"]
    assert recent_data["items"][0]["mode"] == "ctf"
    assert recent_data["items"][0]["modeSubtype"] == "web"
    assert recent_data["items"][0]["goalStyle"] == "flag"

    all_resp = await web_client.get("/api/traces?window=all")
    assert all_resp.status == 200
    all_data = await all_resp.json()
    assert [item["id"] for item in all_data["items"]] == ["run_trace_recent", "run_trace_old"]
    assert all_data["items"][1]["mode"] == "pentest"
    assert all_data["items"][1]["modeSubtype"] == "unknown"
    assert all_data["items"][1]["goalStyle"] == "evidence"
    assert all_data["filters"] == {
        "window": "all",
        "target": "all",
        "targets": ["all", "http://old.test", "http://recent.test"],
    }


@pytest.mark.asyncio
async def test_traces_list_supports_target_filter(web_client: TestClient):
    now = web_server._now_iso()

    web_server._tasks["task_trace_a"] = {
        "id": "task_trace_a",
        "title": "trace a",
        "target": "http://a.test",
        "goal": "trace a",
        "status": "success",
        "createdAt": now,
        "startedAt": now,
        "finishedAt": now,
        "tokensUsed": 10,
        "toolCalls": 1,
        "currentRunId": "run_trace_a",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }
    web_server._tasks["task_trace_b"] = {
        "id": "task_trace_b",
        "title": "trace b",
        "target": "http://b.test",
        "goal": "trace b",
        "status": "failed",
        "createdAt": now,
        "startedAt": now,
        "finishedAt": now,
        "tokensUsed": 20,
        "toolCalls": 2,
        "currentRunId": "run_trace_b",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    resp = await web_client.get("/api/traces?window=all&target=http://a.test")

    assert resp.status == 200
    data = await resp.json()
    assert [item["id"] for item in data["items"]] == ["run_trace_a"]
    assert data["filters"] == {
        "window": "all",
        "target": "http://a.test",
        "targets": ["all", "http://a.test", "http://b.test"],
    }


@pytest.mark.asyncio
async def test_traces_list_invalid_target_falls_back_to_all(web_client: TestClient):
    now = web_server._now_iso()

    web_server._tasks["task_trace_known"] = {
        "id": "task_trace_known",
        "title": "trace known",
        "target": "http://known.test",
        "goal": "trace known",
        "status": "success",
        "createdAt": now,
        "startedAt": now,
        "finishedAt": now,
        "tokensUsed": 10,
        "toolCalls": 1,
        "currentRunId": "run_trace_known",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    resp = await web_client.get("/api/traces?window=all&target=http://not-found.test")

    assert resp.status == 200
    data = await resp.json()
    assert data["filters"] == {
        "window": "all",
        "target": "all",
        "targets": ["all", "http://known.test"],
    }
    assert [item["id"] for item in data["items"]] == ["run_trace_known"]


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
async def test_post_task_returns_normalized_contract_fields(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "create-shape", "target": "http://shape.test", "goal": "verify create"},
    )

    assert created.status == 201
    task = await created.json()

    assert task["messages"] == []
    assert task["attachments"] == []
    assert task["mode"] == "pentest"
    assert task["modeSubtype"] == "unknown"
    assert task["goalStyle"] == "evidence"
    assert task["capabilities"] == {
        "hint": True,
        "stop": True,
        "continue": False,
        "retry": False,
        "attachments": True,
    }


@pytest.mark.asyncio
async def test_post_task_resolves_auto_mode_to_ctf_contract(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={
            "title": "ctf-auto",
            "target": "http://challenge.test",
            "goal": "analyze challenge",
            "mode": "auto",
            "ctfType": "web",
        },
    )

    assert created.status == 201
    task = await created.json()

    assert task["mode"] == "ctf"
    assert task["modeSubtype"] == "web"
    assert task["goalStyle"] == "flag"


def test_run_agent_task_uses_pentest_default_goal_when_mode_is_pentest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class _FakeRuntime:
        async def stop(self):
            return None

    class _FakeMessage:
        def __init__(self):
            self.tool_calls = []
            self.usage = {"input_tokens": 0, "output_tokens": 0}
            self.tool_results = []
            self.content = ""

    class _FakeAgent:
        goals: list[str] = []

        def __init__(self, **kwargs):
            self.conversation_history = []
            self.permission_enforcer = types.SimpleNamespace(mode=types.SimpleNamespace(value=99))
            self._session_id = "mode_goal_session"

        async def agent_loop(self, goal):
            self.__class__.goals.append(goal)
            yield _FakeMessage()

        def save_session(self):
            return self._session_id

    fake_pa_agent = types.ModuleType("pentestagent.agents.pa_agent")
    fake_pa_agent.PentestAgentAgent = _FakeAgent
    fake_settings = types.ModuleType("pentestagent.config.settings")
    fake_settings.get_settings = lambda: types.SimpleNamespace(model="test-model")
    fake_initializer = types.ModuleType("pentestagent.interface.initializer")
    fake_initializer.activate_workspace_for_target = lambda target: "workspace"

    async def _fake_build_runtime(**kwargs):
        return _FakeRuntime(), {"selected": "local", "connected": True}

    fake_initializer.build_runtime = _fake_build_runtime
    fake_llm = types.ModuleType("pentestagent.llm")
    fake_llm.LLM = lambda model, rag_engine=None: object()
    fake_tools = types.ModuleType("pentestagent.tools")
    fake_tools.get_all_tools = lambda: []

    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent", fake_pa_agent)
    monkeypatch.setitem(sys.modules, "pentestagent.config.settings", fake_settings)
    monkeypatch.setitem(sys.modules, "pentestagent.interface.initializer", fake_initializer)
    monkeypatch.setitem(sys.modules, "pentestagent.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "pentestagent.tools", fake_tools)
    monkeypatch.setattr(web_server, "emit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_server, "_persist_tasks", lambda project_root: None)
    monkeypatch.setattr(web_server._bus, "emit", lambda event: None)

    web_server._tasks["task_mode_goal"] = {
        "id": "task_mode_goal",
        "title": "mode goal",
        "target": "http://pentest.test",
        "goal": "",
        "ctfType": "web",
        "mode": "pentest",
        "modeSubtype": "unknown",
        "goalStyle": "evidence",
        "maxIter": 1,
        "docker": False,
        "flagFormat": r"flag\{[^}]+\}",
        "status": "queued",
        "createdAt": web_server._now_iso(),
        "startedAt": None,
        "finishedAt": None,
        "tokensUsed": 0,
        "toolCalls": 0,
        "finalFlag": None,
        "stopReason": None,
        "currentRunId": "run_mode_goal",
        "sparkSeed": [1, 1, 1, 1],
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    web_server._run_agent_task(
        "task_mode_goal",
        {
            "target": "http://pentest.test",
            "goal": "",
            "ctfType": "web",
            "mode": "pentest",
            "modeSubtype": "unknown",
            "goalStyle": "evidence",
            "maxIter": 1,
            "docker": False,
            "flagFormat": r"flag\{[^}]+\}",
        },
        tmp_path,
    )

    assert _FakeAgent.goals
    assert "capture the flag" not in _FakeAgent.goals[0].lower()
    assert "ctf web challenge" not in _FakeAgent.goals[0].lower()


def test_task_detail_payload_re_normalizes_dirty_derived_collections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    task = {
        "id": "task_detail_dirty",
        "title": "dirty",
        "target": "http://dirty.test",
        "goal": "normalize detail",
        "status": "queued",
        "createdAt": web_server._now_iso(),
        "startedAt": None,
        "finishedAt": None,
        "tokensUsed": 0,
        "toolCalls": 0,
        "finalFlag": None,
        "stopReason": None,
        "currentRunId": "run_dirty",
        "hints": [{"text": "keep"}, "bad"],
        "attachments": [{"name": "stored-artifact"}, "bad"],
    }

    monkeypatch.setattr(web_server, "_pick_metrics_for_task", lambda project_root, item: None)
    monkeypatch.setattr(
        web_server,
        "_pick_session_snapshot",
        lambda project_root, item: (
            {"conversation": []},
            project_root / "loot" / "sessions" / "task_detail_dirty.json",
            {
                "matchedBy": "test",
                "confidence": "high",
                "expectedSessionId": None,
                "blockedReason": None,
                "candidateScore": None,
            },
        ),
    )
    monkeypatch.setattr(
        web_server,
        "_build_messages_from_snapshot",
        lambda item, snapshot: [{"role": "system", "content": "ok"}, "bad-message"],
    )
    monkeypatch.setattr(
        web_server,
        "_build_plan_from_snapshot",
        lambda snapshot: [{"label": "step"}, "bad-plan"],
    )
    monkeypatch.setattr(
        web_server,
        "_load_task_notes",
        lambda project_root, item: ([{"value": "note"}, "bad-note"], ["loot/notes.json"]),
    )
    monkeypatch.setattr(
        web_server,
        "_build_knowledge_hits_from_snapshot",
        lambda item, snapshot: [{"title": "hit"}, "bad-hit"],
    )

    detail = web_server._task_detail_payload(tmp_path, task)

    assert detail["hints"] == [{"text": "keep"}]
    assert all(isinstance(message, dict) for message in detail["messages"])
    assert {"role": "system", "content": "ok"} in [
        {"role": message.get("role"), "content": message.get("content")}
        for message in detail["messages"]
    ]
    assert detail["plan"] == [{"label": "step"}]
    assert detail["notes"] == [{"value": "note"}]
    assert detail["knowledgeHits"] == [{"title": "hit"}]
    assert detail["attachments"] == [{"name": "stored-artifact"}]


def test_task_detail_payload_prefers_task_session_id_over_metrics_session_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    task = {
        "id": "task_session_preferred",
        "title": "preferred session",
        "target": "http://preferred.test",
        "goal": "prefer task session",
        "status": "stopped",
        "createdAt": web_server._now_iso(),
        "startedAt": web_server._now_iso(),
        "finishedAt": web_server._now_iso(),
        "tokensUsed": 12,
        "toolCalls": 1,
        "finalFlag": None,
        "stopReason": "done",
        "currentRunId": "run_preferred",
        "sessionId": "task_session",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }
    seen: dict[str, str | None] = {"sessionId": None}

    monkeypatch.setattr(
        web_server,
        "_pick_metrics_for_task",
        lambda project_root, item: {"session_id": "metrics_session", "turns": []},
    )

    def fake_pick_session_snapshot(project_root: Path, item: dict[str, object]):
        seen["sessionId"] = str(item.get("sessionId") or "")
        if item.get("sessionId") == "task_session":
            return (
                {"conversation": [{"role": "user", "content": "snapshot"}]},
                project_root / "loot" / "sessions" / "task_session.json",
                {
                    "matchedBy": "explicit_session_id",
                    "confidence": "high",
                    "expectedSessionId": "task_session",
                    "blockedReason": None,
                    "candidateScore": None,
                },
            )
        return (
            None,
            None,
            {
                "matchedBy": "none",
                "confidence": "none",
                "expectedSessionId": str(item.get("sessionId") or "") or None,
                "blockedReason": None,
                "candidateScore": None,
            },
        )

    monkeypatch.setattr(web_server, "_pick_session_snapshot", fake_pick_session_snapshot)
    monkeypatch.setattr(
        web_server,
        "_build_messages_from_snapshot",
        lambda item, snapshot: [{"id": "msg_1", "role": "user", "t": web_server._now_iso(), "content": "from snapshot"}]
        if snapshot
        else [],
    )
    monkeypatch.setattr(
        web_server,
        "_build_messages_from_metrics",
        lambda item, metrics: [{"id": "metric_1", "role": "system", "t": web_server._now_iso(), "content": "from metrics"}],
    )

    detail = web_server._task_detail_payload(tmp_path, task)

    assert seen["sessionId"] == "task_session"
    assert detail["detailSource"]["sessionMatchedBy"] == "explicit_session_id"
    assert detail["detailSource"]["messages"] == "session_snapshot"
    assert detail["messages"][0]["content"] == "from snapshot"


def test_pick_session_snapshot_falls_back_to_heuristic_when_explicit_session_missing(tmp_path: Path):
    sessions_dir = tmp_path / "loot" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    heuristic_path = sessions_dir / "heuristic_candidate.json"
    heuristic_path.write_text(
        json.dumps(
            {
                "session_id": "heuristic_candidate",
                "target": "http://heuristic.test",
                "updated_at": "2026-05-29T10:00:05+00:00",
                "conversation": [{"role": "user", "content": "hello"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    snapshot, snapshot_path, meta = web_server._pick_session_snapshot(
        tmp_path,
        {
            "id": "task_missing_session",
            "target": "http://heuristic.test",
            "sessionId": "missing_session",
            "startedAt": "2026-05-29T10:00:00+00:00",
            "createdAt": "2026-05-29T10:00:00+00:00",
        },
    )

    assert snapshot is not None
    assert snapshot_path == heuristic_path
    assert meta["matchedBy"] == "heuristic_target_time"
    assert meta["blockedReason"] == "expected_session_missing"


def test_pick_metrics_for_task_prefers_exact_run_id_over_better_scored_candidate(tmp_path: Path):
    metrics_dir = tmp_path / "loot" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    wrong_but_closer = {
        "session_id": "metrics_wrong",
        "run_id": "run_other",
        "task_id": "task_other",
        "started_at": "2026-05-29T10:00:00+00:00",
        "total_tool_calls": 1,
        "total_wall_time_ms": 1000,
        "turns": [],
    }
    exact_but_farther = {
        "session_id": "metrics_exact",
        "run_id": "run_exact",
        "task_id": "task_exact",
        "started_at": "2026-05-29T10:10:00+00:00",
        "total_tool_calls": 5,
        "total_wall_time_ms": 9000,
        "turns": [],
    }

    (metrics_dir / "metrics_wrong.json").write_text(json.dumps(wrong_but_closer), encoding="utf-8")
    (metrics_dir / "metrics_exact.json").write_text(json.dumps(exact_but_farther), encoding="utf-8")

    metrics = web_server._pick_metrics_for_task(
        tmp_path,
        {
            "id": "task_exact",
            "currentRunId": "run_exact",
            "target": "http://metrics.test",
            "createdAt": "2026-05-29T10:00:00+00:00",
            "startedAt": "2026-05-29T10:00:00+00:00",
            "finishedAt": "2026-05-29T10:00:01+00:00",
            "toolCalls": 1,
        },
    )

    assert metrics is not None
    assert metrics["session_id"] == "metrics_exact"


def test_run_agent_task_persists_session_more_than_once_when_tool_results_are_observed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class _FakeRuntime:
        async def stop(self):
            return None

    class _FakeMessage:
        def __init__(self):
            self.tool_calls = [types.SimpleNamespace(name="terminal", arguments={"cmd": "id"})]
            self.usage = {"input_tokens": 1, "output_tokens": 1}
            self.tool_results = [
                types.SimpleNamespace(
                    tool_name="terminal",
                    result="uid=1000",
                    error=None,
                    success=True,
                    duration_ms=5.0,
                )
            ]
            self.content = ""

    class _FakeAgent:
        instances: list["_FakeAgent"] = []

        def __init__(self, **kwargs):
            self.__class__.instances.append(self)
            self.target = kwargs.get("target", "")
            self.max_iterations = kwargs.get("max_iterations", 1)
            self.conversation_history = []
            self.permission_enforcer = types.SimpleNamespace(mode=types.SimpleNamespace(value=99))
            self._session_id = "live_session"
            self.save_calls = 0

        async def agent_loop(self, goal):
            yield _FakeMessage()

        def save_session(self):
            self.save_calls += 1
            return self._session_id

    fake_pa_agent = types.ModuleType("pentestagent.agents.pa_agent")
    fake_pa_agent.PentestAgentAgent = _FakeAgent
    fake_settings = types.ModuleType("pentestagent.config.settings")
    fake_settings.get_settings = lambda: types.SimpleNamespace(model="test-model")
    fake_initializer = types.ModuleType("pentestagent.interface.initializer")
    fake_initializer.activate_workspace_for_target = lambda target: "workspace"

    async def _fake_build_runtime(**kwargs):
        return _FakeRuntime(), {"selected": "local", "connected": True}

    fake_initializer.build_runtime = _fake_build_runtime
    fake_llm = types.ModuleType("pentestagent.llm")
    fake_llm.LLM = lambda model, rag_engine=None: object()
    fake_tools = types.ModuleType("pentestagent.tools")
    fake_tools.get_all_tools = lambda: []

    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent", fake_pa_agent)
    monkeypatch.setitem(sys.modules, "pentestagent.config.settings", fake_settings)
    monkeypatch.setitem(sys.modules, "pentestagent.interface.initializer", fake_initializer)
    monkeypatch.setitem(sys.modules, "pentestagent.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "pentestagent.tools", fake_tools)
    monkeypatch.setattr(web_server, "emit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_server, "_persist_tasks", lambda project_root: None)
    monkeypatch.setattr(web_server._bus, "emit", lambda event: None)

    task_id = "task_runtime_session"
    web_server._tasks[task_id] = {
        "id": task_id,
        "title": "runtime session",
        "target": "http://runtime.test",
        "goal": "persist session during run",
        "ctfType": "web",
        "detectedType": "web",
        "mode": "agent",
        "maxIter": 1,
        "docker": False,
        "flagFormat": r"flag\{[^}]+\}",
        "status": "queued",
        "createdAt": web_server._now_iso(),
        "startedAt": None,
        "finishedAt": None,
        "tokensUsed": 0,
        "toolCalls": 0,
        "finalFlag": None,
        "stopReason": None,
        "currentRunId": "run_runtime_session",
        "sparkSeed": [1, 1, 1, 1],
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    web_server._run_agent_task(
        task_id,
        {
            "target": "http://runtime.test",
            "goal": "persist session during run",
            "ctfType": "web",
            "mode": "agent",
            "maxIter": 1,
            "docker": False,
            "flagFormat": r"flag\{[^}]+\}",
        },
        tmp_path,
    )

    assert _FakeAgent.instances
    assert _FakeAgent.instances[0].save_calls >= 2


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


@pytest.mark.asyncio
async def test_attachments_upload_then_list_roundtrip(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "attach-demo", "target": "http://example.test", "goal": "collect file"},
    )
    task = await created.json()

    form = FormData()
    form.add_field(
        "files",
        io.BytesIO(b"hello attachment\n"),
        filename="note.txt",
        content_type="text/plain",
    )

    upload_resp = await web_client.post(f"/api/tasks/{task['id']}/attachments", data=form)

    assert upload_resp.status == 200
    upload_data = await upload_resp.json()
    assert upload_data["taskId"] == task["id"]
    assert upload_data["files"][0]["name"] == "note.txt"
    assert upload_data["files"][0]["size"] == len(b"hello attachment\n")

    list_resp = await web_client.get(f"/api/tasks/{task['id']}/attachments")

    assert list_resp.status == 200
    list_data = await list_resp.json()
    assert list_data["taskId"] == task["id"]
    assert list_data["files"][0]["name"] == "note.txt"
    assert list_data["files"][0]["size"] == len(b"hello attachment\n")


@pytest.mark.asyncio
async def test_trace_replay_creates_new_task_from_existing_run(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "replay-source", "target": "http://replay.test", "goal": "re-run original task"},
    )
    assert created.status == 201
    original_task = await created.json()
    original_task_id = original_task["id"]
    original_run_id = original_task["currentRunId"]
    web_server._tasks[original_task_id]["mode"] = "ctf"
    web_server._tasks[original_task_id]["modeSubtype"] = "web"
    web_server._tasks[original_task_id]["goalStyle"] = "flag"

    replay_resp = await web_client.post(f"/api/traces/{original_run_id}/replay")

    assert replay_resp.status == 200
    replayed_task = await replay_resp.json()
    assert replayed_task["id"] != original_task_id
    assert replayed_task["currentRunId"] != original_run_id
    assert replayed_task["title"] == original_task["title"]
    assert replayed_task["target"] == original_task["target"]
    assert replayed_task["goal"] == original_task["goal"]
    assert replayed_task["mode"] == "ctf"
    assert replayed_task["modeSubtype"] == "web"
    assert replayed_task["goalStyle"] == "flag"
    assert replayed_task["status"] == "queued"
    assert replayed_task["capabilities"] == {
        "hint": True,
        "stop": True,
        "continue": False,
        "retry": False,
        "attachments": True,
    }
    assert set(web_server._tasks.keys()) == {original_task_id, replayed_task["id"]}


@pytest.mark.asyncio
async def test_task_retry_creates_new_task_from_finished_task(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "retry-source", "target": "http://retry.test", "goal": "retry original task"},
    )
    assert created.status == 201
    original_task = await created.json()
    original_task_id = original_task["id"]
    original_run_id = original_task["currentRunId"]
    web_server._tasks[original_task_id]["mode"] = "ctf"
    web_server._tasks[original_task_id]["modeSubtype"] = "web"
    web_server._tasks[original_task_id]["goalStyle"] = "flag"

    stopped = await web_client.post(f"/api/tasks/{original_task_id}/stop")
    assert stopped.status == 200

    retry_resp = await web_client.post(f"/api/tasks/{original_task_id}/retry")

    assert retry_resp.status == 200
    retried_task = await retry_resp.json()
    assert retried_task["id"] != original_task_id
    assert retried_task["currentRunId"] != original_run_id
    assert retried_task["title"] == original_task["title"]
    assert retried_task["target"] == original_task["target"]
    assert retried_task["goal"] == original_task["goal"]
    assert retried_task["mode"] == "ctf"
    assert retried_task["modeSubtype"] == "web"
    assert retried_task["goalStyle"] == "flag"
    assert retried_task["status"] == "queued"
    assert retried_task["capabilities"] == {
        "hint": True,
        "stop": True,
        "continue": False,
        "retry": False,
        "attachments": True,
    }
    assert web_server._tasks[original_task_id]["status"] == "stopped"
    assert set(web_server._tasks.keys()) == {original_task_id, retried_task["id"]}


@pytest.mark.asyncio
async def test_task_continue_accepts_running_task_without_creating_new_task(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "continue-source", "target": "http://continue.test", "goal": "continue original task"},
    )
    assert created.status == 201
    task = await created.json()
    task_id = task["id"]
    run_id = task["currentRunId"]

    web_server._tasks[task_id]["mode"] = "ctf"
    web_server._tasks[task_id]["modeSubtype"] = "web"
    web_server._tasks[task_id]["goalStyle"] = "flag"
    web_server._tasks[task_id]["status"] = "running"
    web_server._tasks[task_id]["startedAt"] = web_server._now_iso()

    continue_resp = await web_client.post(f"/api/tasks/{task_id}/continue")

    assert continue_resp.status == 200
    continue_result = await continue_resp.json()
    assert continue_result["ok"] is True
    assert continue_result["taskId"] == task_id
    assert continue_result["runId"] == run_id
    assert continue_result["accepted"] is True
    assert set(web_server._tasks.keys()) == {task_id}
    assert web_server._tasks[task_id]["status"] == "running"
    assert web_server._tasks[task_id]["mode"] == "ctf"
    assert web_server._tasks[task_id]["modeSubtype"] == "web"
    assert web_server._tasks[task_id]["goalStyle"] == "flag"
    assert web_server._tasks[task_id]["hints"][-1]["text"] == "__continue__"


@pytest.mark.asyncio
async def test_task_continue_rejects_finished_task(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "continue-finished", "target": "http://continue.test", "goal": "continue original task"},
    )
    assert created.status == 201
    task = await created.json()
    task_id = task["id"]

    stopped = await web_client.post(f"/api/tasks/{task_id}/stop")
    assert stopped.status == 200

    continue_resp = await web_client.post(f"/api/tasks/{task_id}/continue")

    assert continue_resp.status == 409


@pytest.mark.asyncio
async def test_knowledge_reindex_returns_summary_shape(
    web_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    (knowledge_dir / "sample.md").write_text("# sample\nbody\n", encoding="utf-8")

    class _FakeRAGEngine:
        def __init__(self, knowledge_path, use_local_embeddings=True):
            self.knowledge_path = knowledge_path
            self.use_local_embeddings = use_local_embeddings
            self.documents = []

        def index_documents(self, force=False):
            self.documents = [
                type("Doc", (), {"source": str(knowledge_dir / "sample.md")})(),
                type("Doc", (), {"source": str(knowledge_dir / "sample.md")})(),
            ]

    monkeypatch.setattr(knowledge_module, "RAGEngine", _FakeRAGEngine)

    resp = await web_client.post("/api/knowledge/reindex")

    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["reindexed"] is True
    assert data["docCount"] == 1
    assert data["chunkCount"] == 2
    assert isinstance(data["updatedAt"], str)


@pytest.mark.asyncio
async def test_runtime_test_returns_runtime_summary_shape(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    class _FakeRuntime:
        async def stop(self):
            return None

    async def _fake_build_runtime(*, docker=False, ssh=False, auto_ssh=True, on_progress=None):
        return _FakeRuntime(), {
            "requested": "auto",
            "selected": "local",
            "auto_selected": False,
            "connected": True,
            "host": None,
            "port": None,
            "user": None,
            "label": "Local",
            "status_text": "Local runtime active",
            "fallback_reason": None,
        }

    monkeypatch.setattr(initializer_module, "build_runtime", _fake_build_runtime)

    resp = await web_client.post("/api/runtime/test")

    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["healthy"] is True
    assert isinstance(data["testedAt"], str)
    assert data["runtime"]["selected"] == "local"
    assert data["runtime"]["connected"] is True
    assert data["runtime"]["label"] == "Local"
    assert data["runtime"]["status_text"] == "Local runtime active"


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
    assert data["settings"]["mcp"]["servers"] == [
        {
            "name": "docs-mcp",
            "type": "sse",
            "url": "http://127.0.0.1:8080/sse",
            "enabled": True,
            "connected": False,
        }
    ]

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


@pytest.mark.asyncio
async def test_knowledge_add_doc_upload_saves_document_and_reindexes(
    web_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    knowledge_dir = tmp_path / "knowledge"
    sources_dir = knowledge_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    class _FakeRAGEngine:
        def __init__(self, knowledge_path, use_local_embeddings=True):
            self.knowledge_path = knowledge_path
            self.use_local_embeddings = use_local_embeddings
            self.documents = []

        def index_documents(self, force=False):
            uploaded = sources_dir / "probe.md"
            self.documents = [
                type("Doc", (), {"source": str(uploaded)})(),
                type("Doc", (), {"source": str(uploaded)})(),
            ]

    monkeypatch.setattr(knowledge_module, "RAGEngine", _FakeRAGEngine)

    form = FormData()
    form.add_field(
        "file",
        io.BytesIO(b"# probe\nknowledge body\n"),
        filename="probe.md",
        content_type="text/markdown",
    )

    resp = await web_client.post("/api/knowledge/documents", data=form)

    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["saved"] is True
    assert data["reindexed"] is True
    assert data["document"]["docKey"]
    assert data["document"]["sourcePath"] == "knowledge/sources/probe.md"
    assert data["document"]["title"] == "probe"
    assert data["document"]["chunkCount"] == 2
    assert isinstance(data["updatedAt"], str)
    assert (sources_dir / "probe.md").exists()


@pytest.mark.asyncio
async def test_knowledge_open_returns_source_open_link(web_client: TestClient, tmp_path: Path):
    knowledge_file = tmp_path / "knowledge" / "sources" / "probe.md"
    knowledge_file.parent.mkdir(parents=True, exist_ok=True)
    knowledge_file.write_text("# probe\nbody\n", encoding="utf-8")

    doc_key = web_server._doc_key("knowledge/sources/probe.md")

    resp = await web_client.get(f"/api/knowledge/{doc_key}/open")

    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["openUrl"] == f"/api/knowledge/{doc_key}/content"
    assert data["sourcePath"] == "knowledge/sources/probe.md"
