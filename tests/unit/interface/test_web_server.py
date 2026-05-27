from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pentestagent.interface import web_server


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
    assert task["capabilities"] == {
        "hint": True,
        "stop": True,
        "continue": False,
        "retry": False,
        "attachments": True,
    }


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
