from __future__ import annotations

import io
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from pentestagent.agents.pa_agent.ctf_state import CTFState
from pentestagent.interface import web_server
import pentestagent.config.settings as settings_module
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
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "PENTESTAGENT_MODEL=openai/gpt-5.4",
                "FH_PROVIDER=custom",
                "LITELLM_API_BASE=http://127.0.0.1:11434/v1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "_settings", None)
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
        "ctfChainUsed": ["recon", "", None, 1],
        "ctfMissingTools": "bad",
        "ctfNotes": ["keep", "", None],
    }

    serialized = web_server._serialize_task(task)

    assert serialized["hints"] == [{"text": "keep"}]
    assert serialized["messages"] == []
    assert serialized["plan"] == []
    assert serialized["notes"] == [{"value": "note"}]
    assert serialized["knowledgeHits"] == [{"title": "hit"}]
    assert serialized["attachments"] == [{"name": "file.txt"}]
    assert serialized["ctfChainUsed"] == ["recon", "1"]
    assert serialized["ctfMissingTools"] == []
    assert serialized["ctfNotes"] == ["keep"]
    assert serialized["capabilities"]["stop"] is False


def test_ctf_dispatcher_hint_and_context_include_resume_contract():
    task = {
        "hints": [{"text": "focus on the admin flow"}],
        "challengePath": r"D:\webstudy\CTF\2026\easy_login",
        "artifactPaths": [r"D:\webstudy\CTF\2026\easy_login\docker-compose.yml"],
        "resumeFromRunId": "run-prev-1",
        "resumeFromCheckpointId": "checkpoint-prev-1",
        "resumeSummary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
        "sessionContext": {
            "resumeContext": {
                "runId": "run-prev-1",
                "checkpointId": "checkpoint-prev-1",
                "checkpointLabel": "task_failed",
                "stopReason": "wrong_flag_feedback",
                "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
                "verifiedFlags": [],
                "runtimeFlags": [],
            }
        },
        "ingressHandoff": {
            "decisionKind": "resume_execute",
            "nextAction": "resume_from_checkpoint",
            "challengeContext": {
                "challengePath": r"D:\webstudy\CTF\2026\easy_login",
                "artifactPaths": [r"D:\webstudy\CTF\2026\easy_login\docker-compose.yml"],
                "resumeContext": {
                    "runId": "run-prev-1",
                    "checkpointId": "checkpoint-prev-1",
                    "checkpointLabel": "task_failed",
                    "stopReason": "wrong_flag_feedback",
                    "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
                    "verifiedFlags": [],
                    "runtimeFlags": [],
                },
            },
            "resumeBootstrap": {
                "nextAction": "resume_from_checkpoint",
                "runId": "run-prev-1",
                "checkpointId": "checkpoint-prev-1",
                "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
            },
        },
    }

    hint = web_server._ctf_dispatcher_hint(task)
    challenge_context = web_server._build_ctf_challenge_context(task)

    assert "[local_ctf_assets]" in hint
    assert "[resume_context]" in hint
    assert "[resume_bootstrap]" in hint
    assert "nextAction=resume_from_checkpoint" in hint
    assert "runId=run-prev-1" in hint
    assert "checkpointId=checkpoint-prev-1" in hint
    assert "run_id=run-prev-1; stop_reason=wrong_flag_feedback" in hint
    assert challenge_context == {
        "challengePath": r"D:\webstudy\CTF\2026\easy_login",
        "artifactPaths": [r"D:\webstudy\CTF\2026\easy_login\docker-compose.yml"],
        "resumeContext": {
            "runId": "run-prev-1",
            "checkpointId": "checkpoint-prev-1",
            "checkpointLabel": "task_failed",
            "stopReason": "wrong_flag_feedback",
            "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
            "verifiedFlags": [],
            "runtimeFlags": [],
        },
    }


def test_sync_runtime_challenge_context_persists_derived_target_fields():
    task = {
        "ingressHandoff": {
            "decisionKind": "direct_execute",
            "nextAction": "bootstrap_local_assets",
            "challengeContext": {
                "challengePath": r"D:\webstudy\CTF\2026\easy_login",
                "artifactPaths": [r"D:\webstudy\CTF\2026\easy_login\docker-compose.yml"],
            },
        }
    }
    dispatcher = SimpleNamespace(
        _challenge_context={
            "challengePath": r"D:\webstudy\CTF\2026\easy_login",
            "artifactPaths": [r"D:\webstudy\CTF\2026\easy_login\docker-compose.yml"],
            "derivedTarget": "http://127.0.0.1:3000",
            "derivedTargetSource": "docker_compose_port_mapping",
            "derivedTargetComposePath": r"D:\webstudy\CTF\2026\easy_login\docker-compose.yml",
        }
    )

    web_server._sync_runtime_challenge_context(task, dispatcher)

    assert task["target"] == "http://127.0.0.1:3000"
    challenge_context = task["ingressHandoff"]["challengeContext"]
    assert challenge_context["derivedTarget"] == "http://127.0.0.1:3000"
    assert challenge_context["derivedTargetSource"] == "docker_compose_port_mapping"
    assert (
        challenge_context["derivedTargetComposePath"]
        == r"D:\webstudy\CTF\2026\easy_login\docker-compose.yml"
    )


def test_ctf_dispatcher_hint_includes_control_decision_block():
    task = {
        "hints": [{"text": "focus on the admin flow"}],
        "controlDecision": {
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "verified flag already present in blackboard",
            "nextAction": "verify_or_submit_flag",
            "driver": "blackboard.verified_flag",
        },
    }

    hint = web_server._ctf_dispatcher_hint(task)

    assert "[control_decision]" in hint
    assert "decisionKind=direct_execute" in hint
    assert "nextAction=verify_or_submit_flag" in hint
    assert "driver=blackboard.verified_flag" in hint
    assert "reason=verified flag already present in blackboard" in hint


def test_ctf_dispatcher_hint_includes_verified_flag_for_verify_or_submit_action():
    task = {
        "hints": [{"text": "focus on verified flag handoff"}],
        "controlDecision": {
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "verified flag already present in blackboard",
            "nextAction": "verify_or_submit_flag",
            "driver": "blackboard.verified_flag",
        },
        "ctfStateSnapshot": {
            "observations": [],
            "artifacts": [],
            "runtime_flags": [],
            "verified_flags": [
                {
                    "value": "flag{verified_candidate}",
                    "level": "verified",
                    "evidence_source": "platform-accept",
                    "rationale": "accepted by prior verification",
                }
            ],
        },
    }

    hint = web_server._ctf_dispatcher_hint(task)

    assert "[control_decision]" in hint
    assert "nextAction=verify_or_submit_flag" in hint
    assert "verifiedFlag=flag{verified_candidate}" in hint


def test_ctf_dispatcher_hint_includes_discovered_endpoint_for_probe_action():
    task = {
        "hints": [{"text": "focus on the admin flow"}],
        "controlDecision": {
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "discovered endpoint present in blackboard",
            "nextAction": "probe_discovered_endpoint",
            "driver": "blackboard.discovered_endpoint",
        },
        "ctfStateSnapshot": {
            "observations": [
                {
                    "kind": "recon_url",
                    "value": "http://challenge.test/admin",
                    "source": "recon",
                    "metadata": {"confidence": "high"},
                }
            ],
            "artifacts": [],
            "runtime_flags": [],
            "verified_flags": [],
        },
    }

    hint = web_server._ctf_dispatcher_hint(task)

    assert "[control_decision]" in hint
    assert "nextAction=probe_discovered_endpoint" in hint
    assert "endpoint=http://challenge.test/admin" in hint


def test_ctf_dispatcher_hint_includes_runtime_flag_for_verify_runtime_signal():
    task = {
        "hints": [{"text": "focus on runtime verification"}],
        "controlDecision": {
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "runtime flag present in blackboard",
            "nextAction": "verify_runtime_signal",
            "driver": "blackboard.runtime_flag",
        },
        "ctfStateSnapshot": {
            "observations": [],
            "artifacts": [],
            "runtime_flags": [
                {
                    "value": "flag{runtime_candidate}",
                    "level": "runtime",
                    "evidence_source": "runtime-http",
                    "rationale": "reflected in runtime response",
                }
            ],
            "verified_flags": [],
        },
    }

    hint = web_server._ctf_dispatcher_hint(task)

    assert "[control_decision]" in hint
    assert "nextAction=verify_runtime_signal" in hint
    assert "runtimeFlag=flag{runtime_candidate}" in hint


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
    assert data["recentArtifacts"] == []
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
        "recentArtifacts",
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
        "recentArtifacts",
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
async def test_dashboard_summary_projects_recent_artifacts_from_harness_context(
    web_client: TestClient,
):
    now = web_server._now_iso()
    web_server._tasks["task_dashboard_artifact"] = {
        "id": "task_dashboard_artifact",
        "title": "dashboard artifact",
        "target": "http://artifact.test",
        "goal": "surface artifact",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
        "status": "success",
        "createdAt": now,
        "startedAt": now,
        "finishedAt": now,
        "tokensUsed": 1,
        "toolCalls": 1,
        "currentRunId": "run_dashboard_artifact",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    original_builder = web_server._build_run_session_context
    web_server._build_run_session_context = lambda project_root, run_id: {
        "runId": run_id,
        "recentEvents": [],
        "artifacts": [
            {
                "artifactId": "artifact-dashboard-1",
                "kind": "artifact",
                "title": "ssti_response_dump",
                "path": None,
                "location": "http://artifact.test/debug.txt",
                "producer": "ssti_exploit",
                "metadata": {"category": "exploit-output"},
                "t": "2026-05-29T10:00:01+00:00",
            }
        ],
        "latestCheckpoint": None,
        "resumeContext": None,
    }
    try:
        resp = await web_client.get("/api/dashboard/summary?window=all&runtime=all")
    finally:
        web_server._build_run_session_context = original_builder

    assert resp.status == 200
    data = await resp.json()
    assert data["recentArtifacts"][0]["title"] == "ssti_response_dump"
    assert data["recentArtifacts"][0]["taskId"] == "task_dashboard_artifact"
    assert data["recentArtifacts"][0]["runId"] == "run_dashboard_artifact"


@pytest.mark.asyncio
async def test_dashboard_summary_projects_recent_tool_calls_from_harness_context(
    web_client: TestClient,
):
    now = web_server._now_iso()
    web_server._tasks["task_dashboard_tool"] = {
        "id": "task_dashboard_tool",
        "title": "dashboard tool",
        "target": "http://tool.test",
        "goal": "surface tool audit",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
        "status": "success",
        "createdAt": now,
        "startedAt": now,
        "finishedAt": now,
        "tokensUsed": 1,
        "toolCalls": 1,
        "currentRunId": "run_dashboard_tool",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    original_builder = web_server._build_run_session_context
    web_server._build_run_session_context = lambda project_root, run_id: {
        "runId": run_id,
        "recentEvents": [
            {
                "type": "tool_called",
                "t": "2026-05-29T10:00:00+00:00",
                "payload": {
                    "tool_name": "proxy_action",
                    "action": "request",
                    "target": "http://tool.test/login",
                    "metadata": {"method": "GET"},
                },
            },
            {
                "type": "tool_finished",
                "t": "2026-05-29T10:00:01+00:00",
                "payload": {
                    "tool_name": "proxy_action",
                    "action": "request",
                    "target": "http://tool.test/login",
                    "ok": True,
                    "metadata": {"status_code": 200},
                },
            },
        ],
        "artifacts": [],
        "latestCheckpoint": None,
        "resumeContext": None,
    }
    try:
        resp = await web_client.get("/api/dashboard/summary?window=all&runtime=all")
    finally:
        web_server._build_run_session_context = original_builder

    assert resp.status == 200
    data = await resp.json()
    assert data["recentToolCalls"][0]["tool"] == "proxy_action"
    assert data["recentToolCalls"][0]["runId"] == "run_dashboard_tool"
    assert data["recentToolCalls"][0]["status"] in {"running", "success"}
    assert "request" in data["recentToolCalls"][0]["summary"]


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
    assert "ctfChainUsed" in detail
    assert "ctfMissingTools" in detail
    assert "ctfNotes" in detail
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
async def test_post_task_pentest_contract_omits_ctf_legacy_fields(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "pentest-shape", "target": "http://pentest.test", "goal": "verify pentest shape"},
    )

    assert created.status == 201
    task = await created.json()

    assert task["mode"] == "pentest"
    assert task["modeSubtype"] == "unknown"
    assert "ctfType" not in task
    assert "detectedType" not in task


@pytest.mark.asyncio
async def test_post_task_ctf_contract_preserves_ctf_type_without_legacy_field(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={
            "title": "ctf-shape",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "goal": "capture the flag",
        },
    )

    assert created.status == 201
    task = await created.json()

    assert task["mode"] == "ctf"
    assert task["modeSubtype"] == "web"
    assert task["ctfType"] == "web"
    assert "detectedType" not in task


@pytest.mark.asyncio
async def test_post_task_persists_ctf_local_asset_contract_fields(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={
            "title": "ctf-local-assets",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "goal": "capture the flag",
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\src\server.ts",
            ],
        },
    )

    assert created.status == 201
    task = await created.json()

    assert task["challengePath"] == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    assert task["artifactPaths"] == [
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\src\server.ts",
    ]


@pytest.mark.asyncio
async def test_post_task_includes_explore_first_control_decision_with_target_only(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "blocked-control", "target": "http://placeholder.test", "goal": "need target"},
    )

    assert created.status == 201
    task = await created.json()

    assert task["controlDecision"]["shouldRun"] is True
    assert task["controlDecision"]["decisionKind"] == "explore_first"
    assert task["controlDecision"]["nextAction"] == "collect_initial_facts"


@pytest.mark.asyncio
async def test_post_task_blocked_control_decision_does_not_start_execution(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={
            "title": "blocked-control",
            "target": "",
            "goal": "need target or local assets",
        },
    )

    assert created.status == 201
    task = await created.json()

    assert task["controlDecision"]["shouldRun"] is False
    assert task["controlDecision"]["decisionKind"] == "blocked"
    assert task["controlDecision"]["nextAction"] == "await_input"
    assert task["status"] == "blocked"
    assert task["startedAt"] is None
    assert task["finishedAt"] is None
    assert task["capabilities"]["stop"] is False
    assert task["capabilities"]["retry"] is False
    assert task["capabilities"]["continue"] is False
    assert task["id"] not in web_server._task_threads


@pytest.mark.asyncio
async def test_post_task_includes_direct_execute_control_decision_for_ctf_local_assets(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={
            "title": "ctf-control-assets",
            "mode": "ctf",
            "ctfType": "web",
            "target": "http://challenge-assets.test",
            "goal": "solve local challenge",
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            ],
        },
    )

    assert created.status == 201
    task = await created.json()

    assert task["controlDecision"]["shouldRun"] is True
    assert task["controlDecision"]["decisionKind"] == "direct_execute"
    assert task["controlDecision"]["nextAction"] == "bootstrap_local_assets"


@pytest.mark.asyncio
async def test_trace_replay_response_includes_resume_execute_control_decision(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "replay-control-source", "target": "http://replay-control.test", "goal": "re-run original task"},
    )
    assert created.status == 201
    original_task = await created.json()
    original_task_id = original_task["id"]
    original_run_id = original_task["currentRunId"]

    web_server._tasks[original_task_id]["status"] = "success"
    web_server._tasks[original_task_id]["mode"] = "ctf"
    web_server._tasks[original_task_id]["modeSubtype"] = "web"
    web_server._tasks[original_task_id]["goalStyle"] = "flag"
    web_server._tasks[original_task_id]["challengePath"] = r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    web_server._tasks[original_task_id]["artifactPaths"] = [
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
    ]
    web_server._tasks[original_task_id]["sessionContext"] = {
        "resumeContext": {
            "runId": original_run_id,
            "checkpointId": "checkpoint-replay-1",
            "summary": "run_id=run-1; stop_reason=flag_verified",
        }
    }
    web_server._tasks[original_task_id]["resumeFromRunId"] = original_run_id
    web_server._tasks[original_task_id]["resumeFromCheckpointId"] = "checkpoint-replay-1"
    web_server._tasks[original_task_id]["resumeSummary"] = "run_id=run-1; stop_reason=flag_verified"

    replay_resp = await web_client.post(f"/api/traces/{original_run_id}/replay")

    assert replay_resp.status == 200
    replayed_task = await replay_resp.json()
    assert replayed_task["controlDecision"]["shouldRun"] is True
    assert replayed_task["controlDecision"]["decisionKind"] == "resume_execute"
    assert replayed_task["controlDecision"]["nextAction"] == "resume_from_checkpoint"
    assert replayed_task["controlDecision"]["driver"] == "task.resume_context"
    assert replayed_task["decisionRecords"][0]["driver"] == "task.resume_context"
    assert replayed_task["ingressHandoff"]["decisionKind"] == "resume_execute"
    assert replayed_task["ingressHandoff"]["nextAction"] == "resume_from_checkpoint"
    assert replayed_task["ingressHandoff"]["challengeContext"]["challengePath"] == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    assert replayed_task["ingressHandoff"]["resumeBootstrap"]["runId"] == original_run_id
    assert replayed_task["ingressHandoff"]["resumeBootstrap"]["checkpointId"] == "checkpoint-replay-1"


@pytest.mark.asyncio
async def test_post_task_persists_minimal_decision_record(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={
            "title": "decision-record-local-assets",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "goal": "solve local challenge",
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            ],
        },
    )

    assert created.status == 201
    task = await created.json()

    assert task["decisionRecords"][0]["kind"] == "direct_execute"
    assert task["decisionRecords"][0]["source"] == "web_ingress"
    assert task["decisionRecords"][0]["nextAction"] == "bootstrap_local_assets"


@pytest.mark.asyncio
async def test_task_detail_surfaces_minimal_decision_record(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={
            "title": "decision-record-detail",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "goal": "solve local challenge",
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            ],
        },
    )

    assert created.status == 201
    task = await created.json()

    detail_resp = await web_client.get(f"/api/tasks/{task['id']}")
    assert detail_resp.status == 200
    detail = await detail_resp.json()

    assert detail["decisionRecords"][0]["kind"] == "direct_execute"
    assert detail["decisionRecords"][0]["source"] == "web_ingress"
    assert detail["decisionRecords"][0]["nextAction"] == "bootstrap_local_assets"
    assert detail["decisionRecords"][0]["driver"] == ""


@pytest.mark.asyncio
async def test_task_detail_surfaces_blackboard_snapshot(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={
            "title": "blackboard-detail",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "goal": "solve local challenge",
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            ],
        },
    )

    assert created.status == 201
    task = await created.json()
    task_id = task["id"]
    web_server._tasks[task_id]["ingressHandoff"]["challengeContext"]["derivedTarget"] = "http://127.0.0.1:3000"
    web_server._tasks[task_id]["ingressHandoff"]["challengeContext"]["derivedTargetSource"] = "docker_compose_port_mapping"
    web_server._tasks[task_id]["ingressHandoff"]["challengeContext"]["derivedTargetComposePath"] = (
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
    )
    web_server._tasks[task_id]["ctfStateSnapshot"] = {
        "target": "http://challenge.test",
        "goal": "拿到flag",
        "observations": [
            {
                "kind": "resume_bootstrap_hint",
                "value": "continue from saved recon state",
                "source": "ingress_handoff",
                "metadata": {
                    "decision_kind": "direct_execute",
                    "next_action": "bootstrap_local_assets",
                    "run_id": "run-prev-1",
                    "checkpoint_id": "checkpoint-prev-1",
                },
            },
            {
                "kind": "derived_target",
                "value": "http://127.0.0.1:3000",
                "source": "challenge_context",
                "metadata": {
                    "compose_path": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
                    "derivation": "docker_compose_port_mapping",
                },
            },
        ],
        "artifacts": [
            {
                "name": "docker-compose.yml",
                "location": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
                "source": "local_challenge_context",
                "metadata": {},
            }
        ],
        "runtime_flags": [
            {
                "value": "flag{runtime_pending}",
                "level": "runtime",
                "evidence_source": "collector",
                "rationale": "runtime hit",
                "confidence": 0.0,
                "requires_followup": False,
                "proof": None,
                "metadata": {},
            }
        ],
        "verified_flags": [
            {
                "value": "flag{verified_done}",
                "level": "verified",
                "evidence_source": "admin_page",
                "rationale": "verified hit",
                "confidence": 0.0,
                "requires_followup": False,
                "proof": None,
                "metadata": {},
            }
        ],
    }

    detail_resp = await web_client.get(f"/api/tasks/{task_id}")
    assert detail_resp.status == 200
    detail = await detail_resp.json()

    assert "blackboardSnapshot" in detail
    assert detail["blackboardSnapshot"]["facts"]
    assert detail["blackboardSnapshot"]["pendingVerifications"] == [
        {
            "kind": "runtime_flag",
            "value": "flag{runtime_pending}",
            "source": "collector",
            "rationale": "runtime hit",
        }
    ]
    fact_pairs = {(item["kind"], item.get("value")) for item in detail["blackboardSnapshot"]["facts"]}
    assert ("control_decision", "direct_execute") in fact_pairs
    assert ("challenge_path", r"D:\webstudy\CTF\2026\CTF比赛题\easy_login") in fact_pairs
    assert ("resume_bootstrap_hint", "continue from saved recon state") in fact_pairs
    assert ("verified_flag", "flag{verified_done}") in fact_pairs
    assert ("derived_target", "http://127.0.0.1:3000") in fact_pairs
    assert detail["detailSource"]["derivedTarget"] == "http://127.0.0.1:3000"
    assert detail["detailSource"]["derivedTargetSource"] == "docker_compose_port_mapping"
    assert (
        detail["detailSource"]["derivedTargetComposePath"]
        == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
    )
    assert detail["detailSource"]["derivedTargetOrigin"] == "runtime_derived"


@pytest.mark.asyncio
async def test_task_detail_surfaces_control_decision_driver(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={
            "title": "decision-driver-detail",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "goal": "capture the flag",
        },
    )

    assert created.status == 201
    task = await created.json()
    task_id = task["id"]
    web_server._tasks[task_id]["controlDecision"] = {
        "shouldRun": True,
        "decisionKind": "direct_execute",
        "reason": "verified flag already present in blackboard",
        "nextAction": "verify_or_submit_flag",
        "driver": "blackboard.verified_flag",
        "facts": ["mode=ctf", "blackboard.verified_flag=present"],
    }

    detail_resp = await web_client.get(f"/api/tasks/{task_id}")
    assert detail_resp.status == 200
    detail = await detail_resp.json()

    assert detail["controlDecision"]["driver"] == "blackboard.verified_flag"


@pytest.mark.asyncio
async def test_post_task_persists_mode_aware_default_goal_when_goal_omitted(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "goal-default", "target": "http://goal.test"},
    )

    assert created.status == 201
    task = await created.json()

    assert task["goal"] == "Assess target http://goal.test and produce concrete security evidence"


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


@pytest.mark.asyncio
async def test_post_task_persists_ctf_default_goal_after_mode_resolution(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={
            "title": "ctf-default-goal",
            "target": "http://challenge.test",
            "mode": "auto",
            "ctfType": "web",
        },
    )

    assert created.status == 201
    task = await created.json()

    assert task["mode"] == "ctf"
    assert task["goal"] == "CTF web challenge — capture the flag"


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


def test_run_agent_task_attaches_run_id_and_project_root_to_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class _FakeRuntime:
        async def stop(self):
            return None

    class _FakeAgent:
        instances: list["_FakeAgent"] = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.run_id = None
            self.project_root = None
            _FakeAgent.instances.append(self)

        async def agent_loop(self, goal):
            if False:
                yield None
            return

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
    fake_knowledge = types.ModuleType("pentestagent.knowledge")
    fake_knowledge.RAGEngine = lambda *args, **kwargs: None

    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent", fake_pa_agent)
    monkeypatch.setitem(sys.modules, "pentestagent.config.settings", fake_settings)
    monkeypatch.setitem(sys.modules, "pentestagent.interface.initializer", fake_initializer)
    monkeypatch.setitem(sys.modules, "pentestagent.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "pentestagent.tools", fake_tools)
    monkeypatch.setitem(sys.modules, "pentestagent.knowledge", fake_knowledge)
    monkeypatch.setattr(web_server, "_persist_tasks", lambda project_root: None)
    monkeypatch.setattr(web_server._bus, "emit", lambda event: None)
    monkeypatch.setattr(web_server, "emit_log", lambda *args, **kwargs: None)

    web_server._tasks["task_agent_context_attach"] = {
        "id": "task_agent_context_attach",
        "title": "attach run context",
        "target": "http://runtime.test",
        "goal": "collect evidence",
        "ctfType": None,
        "mode": "pentest",
        "modeSubtype": "web",
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
        "currentRunId": "run_agent_context_attach",
        "sparkSeed": [1, 1, 1, 1],
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    web_server._run_agent_task(
        "task_agent_context_attach",
        {
            "target": "http://runtime.test",
            "goal": "collect evidence",
            "mode": "pentest",
            "modeSubtype": "web",
            "goalStyle": "evidence",
            "maxIter": 1,
            "docker": False,
            "flagFormat": r"flag\{[^}]+\}",
        },
        tmp_path,
    )

    assert _FakeAgent.instances
    assert _FakeAgent.instances[0].run_id == "run_agent_context_attach"
    assert _FakeAgent.instances[0].project_root == tmp_path


def test_run_agent_task_routes_ctf_mode_to_ctf_dispatcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class _FakeRuntime:
        async def stop(self):
            return None

    class _FakeDispatcher:
        calls: list[dict[str, object]] = []

        def __init__(self, runtime, progress_callback=None, **kwargs):
            self.runtime = runtime
            self.progress_callback = progress_callback

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None, ingress_handoff=None):
            self.__class__.calls.append(
                {
                    "target": target,
                    "goal": goal,
                    "type": type,
                    "hint": hint,
                    "submit_profile": submit_profile,
                    "challenge_context": challenge_context,
                    "ingress_handoff": ingress_handoff,
                }
            )
            return types.SimpleNamespace(
                success=True,
                flag="flag{dispatcher_route}",
                reason="dispatcher solved",
                notes=[],
                chain_used=["recon"],
                missing_tools=[],
            )

    class _ForbiddenAgent:
        def __init__(self, **kwargs):
            raise AssertionError("PentestAgentAgent should not be constructed for ctf mode")

    fake_pa_agent = types.ModuleType("pentestagent.agents.pa_agent")
    fake_pa_agent.PentestAgentAgent = _ForbiddenAgent
    fake_dispatcher_module = types.ModuleType("pentestagent.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
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
    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
    monkeypatch.setitem(sys.modules, "pentestagent.config.settings", fake_settings)
    monkeypatch.setitem(sys.modules, "pentestagent.interface.initializer", fake_initializer)
    monkeypatch.setitem(sys.modules, "pentestagent.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "pentestagent.tools", fake_tools)
    monkeypatch.setattr(web_server, "emit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_server, "_persist_tasks", lambda project_root: None)
    monkeypatch.setattr(web_server._bus, "emit", lambda event: None)

    web_server._tasks["task_ctf_route"] = {
        "id": "task_ctf_route",
        "title": "ctf route",
        "target": "http://challenge.test",
        "goal": "",
        "ctfType": "web",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
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
        "currentRunId": "run_ctf_route",
        "sparkSeed": [1, 1, 1, 1],
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    web_server._run_agent_task(
        "task_ctf_route",
        {
            "target": "http://challenge.test",
            "goal": "",
            "ctfType": "web",
            "mode": "ctf",
            "modeSubtype": "web",
            "goalStyle": "flag",
            "maxIter": 1,
            "docker": False,
            "flagFormat": r"flag\{[^}]+\}",
        },
        tmp_path,
    )

    assert _FakeDispatcher.calls
    assert _FakeDispatcher.calls[0]["type"] == "web"
    assert "capture the flag" in str(_FakeDispatcher.calls[0]["goal"]).lower()
    assert _FakeDispatcher.calls[0]["ingress_handoff"]["decisionKind"] == "explore_first"
    assert _FakeDispatcher.calls[0]["ingress_handoff"]["nextAction"] == "collect_initial_facts"
    assert web_server._tasks["task_ctf_route"]["status"] == "success"
    assert web_server._tasks["task_ctf_route"]["finalFlag"] == "flag{dispatcher_route}"


def test_run_agent_task_routes_ctf_progress_messages_into_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class _FakeRuntime:
        async def stop(self):
            return None

    class _FakeDispatcher:
        def __init__(self, runtime, progress_callback=None, **kwargs):
            self.runtime = runtime
            self.progress_callback = progress_callback

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None):
            if self.progress_callback is not None:
                self.progress_callback("dispatcher phase 1")
            return types.SimpleNamespace(
                success=True,
                flag="flag{dispatcher_progress}",
                reason="dispatcher solved",
                notes=[],
                chain_used=["recon"],
                missing_tools=[],
            )

    fake_pa_agent = types.ModuleType("pentestagent.agents.pa_agent")
    fake_pa_agent.PentestAgentAgent = lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("PentestAgentAgent should not be constructed for ctf mode")
    )
    fake_dispatcher_module = types.ModuleType("pentestagent.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
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

    captured_logs: list[tuple[str, str, str]] = []

    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent", fake_pa_agent)
    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
    monkeypatch.setitem(sys.modules, "pentestagent.config.settings", fake_settings)
    monkeypatch.setitem(sys.modules, "pentestagent.interface.initializer", fake_initializer)
    monkeypatch.setitem(sys.modules, "pentestagent.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "pentestagent.tools", fake_tools)
    monkeypatch.setattr(web_server, "emit_log", lambda level, source, message: captured_logs.append((level, source, message)))
    monkeypatch.setattr(web_server, "_persist_tasks", lambda project_root: None)
    monkeypatch.setattr(web_server._bus, "emit", lambda event: None)

    web_server._tasks["task_ctf_progress"] = {
        "id": "task_ctf_progress",
        "title": "ctf progress",
        "target": "http://challenge.test",
        "goal": "",
        "ctfType": "web",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
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
        "currentRunId": "run_ctf_progress",
        "sparkSeed": [1, 1, 1, 1],
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    web_server._run_agent_task(
        "task_ctf_progress",
        {
            "target": "http://challenge.test",
            "goal": "",
            "ctfType": "web",
            "mode": "ctf",
            "modeSubtype": "web",
            "goalStyle": "flag",
            "maxIter": 1,
            "docker": False,
            "flagFormat": r"flag\{[^}]+\}",
        },
        tmp_path,
    )

    assert any(level == "info" and source == "ctf.dispatcher" and message == "dispatcher phase 1" for level, source, message in captured_logs)
    assert web_server._tasks["task_ctf_progress"]["finalFlag"] == "flag{dispatcher_progress}"


def test_run_agent_task_emits_ctf_dispatcher_lifecycle_summary_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class _FakeRuntime:
        async def stop(self):
            return None

    class _FakeDispatcher:
        def __init__(self, runtime, progress_callback=None, **kwargs):
            self.runtime = runtime
            self.progress_callback = progress_callback

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None):
            return types.SimpleNamespace(
                success=True,
                flag="flag{dispatcher_summary}",
                reason="dispatcher solved",
                notes=[],
                chain_used=["recon", "auth_form_sqli"],
                missing_tools=[],
            )

    fake_pa_agent = types.ModuleType("pentestagent.agents.pa_agent")
    fake_pa_agent.PentestAgentAgent = lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("PentestAgentAgent should not be constructed for ctf mode")
    )
    fake_dispatcher_module = types.ModuleType("pentestagent.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
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

    captured_logs: list[tuple[str, str, str]] = []

    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent", fake_pa_agent)
    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
    monkeypatch.setitem(sys.modules, "pentestagent.config.settings", fake_settings)
    monkeypatch.setitem(sys.modules, "pentestagent.interface.initializer", fake_initializer)
    monkeypatch.setitem(sys.modules, "pentestagent.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "pentestagent.tools", fake_tools)
    monkeypatch.setattr(web_server, "emit_log", lambda level, source, message: captured_logs.append((level, source, message)))
    monkeypatch.setattr(web_server, "_persist_tasks", lambda project_root: None)
    monkeypatch.setattr(web_server._bus, "emit", lambda event: None)

    web_server._tasks["task_ctf_summary"] = {
        "id": "task_ctf_summary",
        "title": "ctf summary",
        "target": "http://challenge.test",
        "goal": "",
        "ctfType": "web",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
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
        "currentRunId": "run_ctf_summary",
        "sparkSeed": [1, 1, 1, 1],
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    web_server._run_agent_task(
        "task_ctf_summary",
        {
            "target": "http://challenge.test",
            "goal": "",
            "ctfType": "web",
            "mode": "ctf",
            "modeSubtype": "web",
            "goalStyle": "flag",
            "maxIter": 1,
            "docker": False,
            "flagFormat": r"flag\{[^}]+\}",
        },
        tmp_path,
    )

    assert any(
        level == "info" and source == "ctf.dispatcher" and "started" in message and "subtype: web" in message
        for level, source, message in captured_logs
    )
    assert any(
        level == "info" and source == "ctf.dispatcher" and message == "chains: recon, auth_form_sqli"
        for level, source, message in captured_logs
    )
    assert web_server._tasks["task_ctf_summary"]["ctfChainUsed"] == ["recon", "auth_form_sqli"]
    assert web_server._tasks["task_ctf_summary"]["ctfMissingTools"] == []
    assert web_server._tasks["task_ctf_summary"]["ctfNotes"] == []


def test_run_agent_task_emits_ctf_dispatcher_missing_tools_log_on_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class _FakeRuntime:
        async def stop(self):
            return None

    class _FakeDispatcher:
        def __init__(self, runtime, progress_callback=None, **kwargs):
            self.runtime = runtime
            self.progress_callback = progress_callback

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None):
            return types.SimpleNamespace(
                success=False,
                flag=None,
                reason="missing tools",
                notes=[],
                chain_used=["recon"],
                missing_tools=["browser", "sqlmap"],
            )

    fake_pa_agent = types.ModuleType("pentestagent.agents.pa_agent")
    fake_pa_agent.PentestAgentAgent = lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("PentestAgentAgent should not be constructed for ctf mode")
    )
    fake_dispatcher_module = types.ModuleType("pentestagent.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
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

    captured_logs: list[tuple[str, str, str]] = []

    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent", fake_pa_agent)
    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
    monkeypatch.setitem(sys.modules, "pentestagent.config.settings", fake_settings)
    monkeypatch.setitem(sys.modules, "pentestagent.interface.initializer", fake_initializer)
    monkeypatch.setitem(sys.modules, "pentestagent.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "pentestagent.tools", fake_tools)
    monkeypatch.setattr(web_server, "emit_log", lambda level, source, message: captured_logs.append((level, source, message)))
    monkeypatch.setattr(web_server, "_persist_tasks", lambda project_root: None)
    monkeypatch.setattr(web_server._bus, "emit", lambda event: None)

    web_server._tasks["task_ctf_missing_tools"] = {
        "id": "task_ctf_missing_tools",
        "title": "ctf missing tools",
        "target": "http://challenge.test",
        "goal": "",
        "ctfType": "web",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
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
        "currentRunId": "run_ctf_missing_tools",
        "sparkSeed": [1, 1, 1, 1],
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    web_server._run_agent_task(
        "task_ctf_missing_tools",
        {
            "target": "http://challenge.test",
            "goal": "",
            "ctfType": "web",
            "mode": "ctf",
            "modeSubtype": "web",
            "goalStyle": "flag",
            "maxIter": 1,
            "docker": False,
            "flagFormat": r"flag\{[^}]+\}",
        },
        tmp_path,
    )

    assert any(
        level == "warn" and source == "ctf.dispatcher" and message == "missing tools: browser, sqlmap"
        for level, source, message in captured_logs
    )
    assert web_server._tasks["task_ctf_missing_tools"]["status"] == "stopped"
    assert web_server._tasks["task_ctf_missing_tools"]["stopReason"] == "missing tools"
    assert web_server._tasks["task_ctf_missing_tools"]["ctfChainUsed"] == ["recon"]
    assert web_server._tasks["task_ctf_missing_tools"]["ctfMissingTools"] == ["browser", "sqlmap"]
    assert web_server._tasks["task_ctf_missing_tools"]["ctfNotes"] == []


def test_run_agent_task_passes_latest_user_hint_to_ctf_dispatcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class _FakeRuntime:
        async def stop(self):
            return None

    class _FakeDispatcher:
        calls: list[dict[str, object]] = []

        def __init__(self, runtime, progress_callback=None, **kwargs):
            self.runtime = runtime
            self.progress_callback = progress_callback

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None):
            self.__class__.calls.append(
                {
                    "target": target,
                    "goal": goal,
                    "type": type,
                    "hint": hint,
                    "submit_profile": submit_profile,
                    "challenge_context": challenge_context,
                }
            )
            return types.SimpleNamespace(
                success=True,
                flag="flag{dispatcher_hint}",
                reason="dispatcher solved",
                notes=[],
                chain_used=["recon"],
                missing_tools=[],
            )

    fake_pa_agent = types.ModuleType("pentestagent.agents.pa_agent")
    fake_pa_agent.PentestAgentAgent = lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("PentestAgentAgent should not be constructed for ctf mode")
    )
    fake_dispatcher_module = types.ModuleType("pentestagent.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
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
    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
    monkeypatch.setitem(sys.modules, "pentestagent.config.settings", fake_settings)
    monkeypatch.setitem(sys.modules, "pentestagent.interface.initializer", fake_initializer)
    monkeypatch.setitem(sys.modules, "pentestagent.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "pentestagent.tools", fake_tools)
    monkeypatch.setattr(web_server, "emit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_server, "_persist_tasks", lambda project_root: None)
    monkeypatch.setattr(web_server._bus, "emit", lambda event: None)

    web_server._tasks["task_ctf_hint_bridge"] = {
        "id": "task_ctf_hint_bridge",
        "title": "ctf hint bridge",
        "target": "http://challenge.test",
        "goal": "",
        "ctfType": "web",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
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
        "currentRunId": "run_ctf_hint_bridge",
        "sparkSeed": [1, 1, 1, 1],
        "hints": [
            {"text": "focus on admin surface", "t": web_server._now_iso(), "runId": "run_ctf_hint_bridge"},
            {"text": "__continue__", "t": web_server._now_iso(), "source": "continue"},
        ],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    web_server._run_agent_task(
        "task_ctf_hint_bridge",
        {
            "target": "http://challenge.test",
            "goal": "",
            "ctfType": "web",
            "mode": "ctf",
            "modeSubtype": "web",
            "goalStyle": "flag",
            "maxIter": 1,
            "docker": False,
            "flagFormat": r"flag\{[^}]+\}",
        },
        tmp_path,
    )

    assert _FakeDispatcher.calls
    assert _FakeDispatcher.calls[0]["hint"] == "focus on admin surface"


def test_run_agent_task_bridges_ctf_local_asset_contract_into_dispatcher_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class _FakeRuntime:
        async def stop(self):
            return None

    class _FakeDispatcher:
        calls: list[dict[str, object]] = []

        def __init__(self, runtime, progress_callback=None, **kwargs):
            from pentestagent.agents.pa_agent.ctf_state import CTFState

            self.runtime = runtime
            self.progress_callback = progress_callback
            self.state = CTFState(target="http://challenge.test", goal="")
            self.state.add_observation(
                "resume_bootstrap_hint",
                "continue from saved recon state",
                source="ingress_handoff",
                metadata={
                    "decision_kind": "direct_execute",
                    "next_action": "bootstrap_local_assets",
                    "run_id": "run-prev-1",
                    "checkpoint_id": "checkpoint-prev-1",
                },
            )
            self.state.add_flag(
                "flag{bridge_truth}",
                level="verified",
                evidence_source="admin_page",
                rationale="verified hit",
            )

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None):
            self.__class__.calls.append(
                {
                    "target": target,
                    "goal": goal,
                    "type": type,
                    "hint": hint,
                    "submit_profile": submit_profile,
                    "challenge_context": challenge_context,
                }
            )
            return types.SimpleNamespace(
                success=True,
                flag="flag{bridge_truth}",
                reason="dispatcher solved",
                notes=["phase1 done"],
                chain_used=["recon", "auth_form_sqli"],
                missing_tools=["browser"],
            )

    fake_pa_agent = types.ModuleType("pentestagent.agents.pa_agent")
    fake_pa_agent.PentestAgentAgent = lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("PentestAgentAgent should not be constructed for ctf mode")
    )
    fake_dispatcher_module = types.ModuleType("pentestagent.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
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
    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
    monkeypatch.setitem(sys.modules, "pentestagent.config.settings", fake_settings)
    monkeypatch.setitem(sys.modules, "pentestagent.interface.initializer", fake_initializer)
    monkeypatch.setitem(sys.modules, "pentestagent.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "pentestagent.tools", fake_tools)
    monkeypatch.setattr(web_server, "emit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_server, "_persist_tasks", lambda project_root: None)
    monkeypatch.setattr(web_server._bus, "emit", lambda event: None)

    web_server._tasks["task_ctf_local_asset_bridge"] = {
        "id": "task_ctf_local_asset_bridge",
        "title": "ctf local asset bridge",
        "target": "http://challenge.test",
        "goal": "",
        "ctfType": "web",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
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
        "currentRunId": "run_ctf_local_asset_bridge",
        "sparkSeed": [1, 1, 1, 1],
        "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        "artifactPaths": [
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\src\server.ts",
        ],
        "hints": [
            {"text": "focus on local artifacts", "t": web_server._now_iso(), "runId": "run_ctf_local_asset_bridge"},
        ],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    web_server._run_agent_task(
        "task_ctf_local_asset_bridge",
        {
            "target": "http://challenge.test",
            "goal": "",
            "ctfType": "web",
            "mode": "ctf",
            "modeSubtype": "web",
            "goalStyle": "flag",
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\src\server.ts",
            ],
            "maxIter": 1,
            "docker": False,
            "flagFormat": r"flag\{[^}]+\}",
        },
        tmp_path,
    )

    assert _FakeDispatcher.calls
    call = _FakeDispatcher.calls[0]
    assert call["challenge_context"] == {
        "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        "artifactPaths": [
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\src\server.ts",
        ],
    }
    hint = str(call["hint"] or "")
    assert "focus on local artifacts" in hint
    assert r"D:\webstudy\CTF\2026\CTF比赛题\easy_login" in hint
    assert r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml" in hint
    assert isinstance(web_server._tasks["task_ctf_local_asset_bridge"].get("ctfStateSnapshot"), dict)
    assert web_server._tasks["task_ctf_local_asset_bridge"]["ctfStateSnapshot"]["observations"][0]["kind"] == "resume_bootstrap_hint"
    assert web_server._tasks["task_ctf_local_asset_bridge"]["ctfStateSnapshot"]["verified_flags"][0]["value"] == "flag{bridge_truth}"


def test_build_trace_payload_includes_ctf_dispatcher_truth_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    now = web_server._now_iso()
    task = {
        "id": "task_trace_ctf_truth",
        "title": "trace ctf truth",
        "target": "http://trace.test",
        "goal": "trace truth",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
        "status": "stopped",
        "createdAt": now,
        "startedAt": now,
        "finishedAt": now,
        "tokensUsed": 3,
        "toolCalls": 1,
        "finalFlag": None,
        "stopReason": "missing tools",
        "currentRunId": "run_trace_ctf_truth",
        "ctfChainUsed": ["recon", "auth_form_sqli"],
        "ctfMissingTools": ["browser"],
        "ctfNotes": ["phase1 done"],
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    monkeypatch.setattr(web_server, "_pick_metrics_for_task", lambda project_root, item: None)
    monkeypatch.setattr(
        web_server,
        "_pick_session_snapshot",
        lambda project_root, item: (
            None,
            None,
            {"matchedBy": "none", "confidence": "none", "expectedSessionId": None, "blockedReason": None, "candidateScore": None},
        ),
    )

    payload = web_server._build_trace_payload(tmp_path, task, include_timeline=False)

    assert payload["ctfChainUsed"] == ["recon", "auth_form_sqli"]
    assert payload["ctfMissingTools"] == ["browser"]
    assert payload["ctfNotes"] == ["phase1 done"]



def test_build_trace_payload_surfaces_decision_record_driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    now = web_server._now_iso()
    task = {
        "id": "task_trace_decision_driver",
        "title": "trace decision driver",
        "target": "http://trace.test",
        "goal": "trace truth",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
        "status": "success",
        "createdAt": now,
        "startedAt": now,
        "finishedAt": now,
        "tokensUsed": 1,
        "toolCalls": 0,
        "finalFlag": "flag{done}",
        "stopReason": None,
        "currentRunId": "run_trace_driver",
        "decisionRecords": [
            {
                "kind": "direct_execute",
                "source": "web_ingress",
                "nextAction": "verify_or_submit_flag",
                "driver": "blackboard.verified_flag",
            }
        ],
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    monkeypatch.setattr(web_server, "_pick_metrics_for_task", lambda project_root, item: None)
    monkeypatch.setattr(
        web_server,
        "_pick_session_snapshot",
        lambda project_root, item: (
            None,
            None,
            {"matchedBy": "none", "confidence": "none", "expectedSessionId": None, "blockedReason": None, "candidateScore": None},
        ),
    )

    payload = web_server._build_trace_payload(tmp_path, task, include_timeline=False)

    assert payload["decisionRecords"][0]["driver"] == "blackboard.verified_flag"


def test_build_trace_payload_surfaces_blackboard_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    now = web_server._now_iso()
    state = CTFState(target="http://trace.test", goal="trace truth")
    state.add_flag(
        "flag{done}",
        level="verified",
        evidence_source="dispatcher",
        rationale="dispatcher verified the flag",
        confidence=1.0,
        metadata={"source_chain": "auth_form_sqli"},
    )
    task = {
        "id": "task_trace_blackboard_snapshot",
        "title": "trace blackboard snapshot",
        "target": "http://trace.test",
        "goal": "trace truth",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
        "status": "success",
        "createdAt": now,
        "startedAt": now,
        "finishedAt": now,
        "tokensUsed": 1,
        "toolCalls": 0,
        "finalFlag": "flag{done}",
        "stopReason": None,
        "currentRunId": "run_trace_blackboard",
        "controlDecision": {
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "verified flag already present in blackboard",
            "nextAction": "verify_or_submit_flag",
            "driver": "blackboard.verified_flag",
            "facts": ["mode=ctf", "blackboard.verified_flag=present"],
        },
        "decisionRecords": [
            {
                "kind": "direct_execute",
                "source": "web_ingress",
                "nextAction": "verify_or_submit_flag",
                "driver": "blackboard.verified_flag",
            }
        ],
        "ctfStateSnapshot": state.to_snapshot(),
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    monkeypatch.setattr(web_server, "_pick_metrics_for_task", lambda project_root, item: None)
    monkeypatch.setattr(
        web_server,
        "_pick_session_snapshot",
        lambda project_root, item: (
            None,
            None,
            {"matchedBy": "none", "confidence": "none", "expectedSessionId": None, "blockedReason": None, "candidateScore": None},
        ),
    )

    payload = web_server._build_trace_payload(tmp_path, task, include_timeline=False)

    assert "blackboardSnapshot" in payload
    assert any(
        fact["kind"] == "verified_flag" and fact["value"] == "flag{done}"
        for fact in payload["blackboardSnapshot"]["facts"]
    )


def test_build_trace_payload_surfaces_control_decision_driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    now = web_server._now_iso()
    task = {
        "id": "task_trace_control_decision_driver",
        "title": "trace control decision driver",
        "target": "http://trace.test",
        "goal": "trace truth",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
        "status": "success",
        "createdAt": now,
        "startedAt": now,
        "finishedAt": now,
        "tokensUsed": 1,
        "toolCalls": 0,
        "finalFlag": "flag{done}",
        "stopReason": None,
        "currentRunId": "run_trace_control_driver",
        "controlDecision": {
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "verified flag already present in blackboard",
            "nextAction": "verify_or_submit_flag",
            "driver": "blackboard.verified_flag",
            "facts": ["mode=ctf", "blackboard.verified_flag=present"],
        },
        "decisionRecords": [
            {
                "kind": "direct_execute",
                "source": "web_ingress",
                "nextAction": "verify_or_submit_flag",
                "driver": "blackboard.verified_flag",
            }
        ],
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    monkeypatch.setattr(web_server, "_pick_metrics_for_task", lambda project_root, item: None)
    monkeypatch.setattr(
        web_server,
        "_pick_session_snapshot",
        lambda project_root, item: (
            None,
            None,
            {"matchedBy": "none", "confidence": "none", "expectedSessionId": None, "blockedReason": None, "candidateScore": None},
        ),
    )

    payload = web_server._build_trace_payload(tmp_path, task, include_timeline=False)

    assert payload["controlDecision"]["driver"] == "blackboard.verified_flag"


def test_build_trace_payload_surfaces_derived_target_detail_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    now = web_server._now_iso()
    task = {
        "id": "task_trace_derived_target",
        "title": "trace derived target",
        "target": "",
        "goal": "trace truth",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
        "status": "queued",
        "createdAt": now,
        "startedAt": None,
        "finishedAt": None,
        "tokensUsed": 0,
        "toolCalls": 0,
        "currentRunId": "run_trace_derived_target",
        "sourceRunId": "run-origin-1",
        "resumeFromRunId": "run-origin-1",
        "ingressHandoff": {
            "challengeContext": {
                "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
                "artifactPaths": [
                    r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
                ],
                "derivedTarget": "http://127.0.0.1:3000",
                "derivedTargetSource": "docker_compose_port_mapping",
                "derivedTargetComposePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            }
        },
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    monkeypatch.setattr(web_server, "_pick_metrics_for_task", lambda project_root, item: None)
    monkeypatch.setattr(
        web_server,
        "_pick_session_snapshot",
        lambda project_root, item: (
            None,
            None,
            {"matchedBy": "none", "confidence": "none", "expectedSessionId": None, "blockedReason": None, "candidateScore": None},
        ),
    )

    payload = web_server._build_trace_payload(tmp_path, task, include_timeline=False)

    assert payload["detailSource"]["derivedTarget"] == "http://127.0.0.1:3000"
    assert payload["detailSource"]["derivedTargetSource"] == "docker_compose_port_mapping"
    assert (
        payload["detailSource"]["derivedTargetComposePath"]
        == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
    )
    assert payload["detailSource"]["derivedTargetOrigin"] == "inherited_lineage"


def test_build_trace_payload_projects_control_decision_into_timeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    now = web_server._now_iso()
    task = {
        "id": "task_trace_decision_timeline",
        "title": "trace decision timeline",
        "target": "",
        "goal": "trace truth",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
        "status": "queued",
        "createdAt": now,
        "startedAt": now,
        "finishedAt": None,
        "tokensUsed": 0,
        "toolCalls": 0,
        "currentRunId": "run_trace_decision_timeline",
        "controlDecision": {
            "shouldRun": True,
            "decisionKind": "explore_first",
            "reason": "derived target available for initial fact collection",
            "nextAction": "collect_initial_facts",
            "driver": "blackboard.derived_target.runtime_derived",
            "facts": [
                "mode=ctf",
                "target=http://127.0.0.1:3000",
                "blackboard.derived_target=present",
                "derivedTargetOrigin=runtime_derived",
            ],
        },
        "decisionRecords": [
            {
                "kind": "explore_first",
                "source": "web_ingress",
                "nextAction": "collect_initial_facts",
                "driver": "blackboard.derived_target.runtime_derived",
                "facts": [
                    "mode=ctf",
                    "target=http://127.0.0.1:3000",
                    "derivedTargetOrigin=runtime_derived",
                ],
            }
        ],
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    monkeypatch.setattr(web_server, "_pick_metrics_for_task", lambda project_root, item: None)
    monkeypatch.setattr(
        web_server,
        "_pick_session_snapshot",
        lambda project_root, item: (
            None,
            None,
            {"matchedBy": "none", "confidence": "none", "expectedSessionId": None, "blockedReason": None, "candidateScore": None},
        ),
    )
    monkeypatch.setattr(
        web_server,
        "_build_run_session_context",
        lambda project_root, run_id: {
            "runId": run_id,
            "recentEvents": [],
            "artifacts": [],
            "latestCheckpoint": None,
            "resumeContext": None,
        },
    )

    payload = web_server._build_trace_payload(tmp_path, task, include_timeline=True)

    decision_events = [event for event in payload["timeline"] if event["type"] == "decision"]
    assert decision_events
    event = decision_events[0]
    assert event["kind"] == "decision.explore_first"
    assert event["summary"] == "collect_initial_facts"
    assert event["driver"] == "blackboard.derived_target.runtime_derived"
    assert "derivedTargetOrigin=runtime_derived" in event["input"]["facts"]


def test_build_trace_payload_projects_initial_fact_collection_observation_into_timeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    now = web_server._now_iso()
    task = {
        "id": "task_trace_initial_fact_observation",
        "title": "trace initial fact observation",
        "target": "http://127.0.0.1:3000",
        "goal": "trace truth",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
        "status": "queued",
        "createdAt": now,
        "startedAt": now,
        "finishedAt": None,
        "tokensUsed": 0,
        "toolCalls": 0,
        "currentRunId": "run_trace_initial_fact_observation",
        "controlDecision": {
            "shouldRun": True,
            "decisionKind": "explore_first",
            "reason": "derived target available for initial fact collection",
            "nextAction": "collect_initial_facts",
            "driver": "blackboard.derived_target.runtime_derived",
            "facts": [
                "mode=ctf",
                "target=http://127.0.0.1:3000",
                "derivedTargetOrigin=runtime_derived",
            ],
        },
        "ctfStateSnapshot": {
            "target": "http://127.0.0.1:3000",
            "goal": "拿到flag",
            "detected_type": "web",
            "observations": [
                {
                    "kind": "initial_fact_collection_requested",
                    "value": "http://127.0.0.1:3000",
                    "source": "control_decision",
                    "metadata": {
                        "driver": "blackboard.derived_target.runtime_derived",
                        "reason": "derived target available for initial fact collection",
                        "next_action": "collect_initial_facts",
                    },
                }
            ],
            "artifacts": [],
            "verified_flags": [],
            "runtime_flags": [],
            "meta_reasonings": [],
            "hypotheses": [],
        },
        "decisionRecords": [],
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    monkeypatch.setattr(web_server, "_pick_metrics_for_task", lambda project_root, item: None)
    monkeypatch.setattr(
        web_server,
        "_pick_session_snapshot",
        lambda project_root, item: (
            None,
            None,
            {"matchedBy": "none", "confidence": "none", "expectedSessionId": None, "blockedReason": None, "candidateScore": None},
        ),
    )
    monkeypatch.setattr(
        web_server,
        "_build_run_session_context",
        lambda project_root, run_id: {
            "runId": run_id,
            "recentEvents": [],
            "artifacts": [],
            "latestCheckpoint": None,
            "resumeContext": None,
        },
    )

    payload = web_server._build_trace_payload(tmp_path, task, include_timeline=True)

    observation_events = [event for event in payload["timeline"] if event["type"] == "observation"]
    assert observation_events
    event = observation_events[0]
    assert event["kind"] == "observation.initial_fact_collection_requested"
    assert event["summary"] == "http://127.0.0.1:3000"
    assert event["driver"] == "blackboard.derived_target.runtime_derived"
    assert event["input"]["nextAction"] == "collect_initial_facts"
    assert event["input"]["reason"] == "derived target available for initial fact collection"


def test_build_trace_payload_projects_tool_audit_events_from_session_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    task = {
        "id": "task_trace_tool_audit",
        "title": "trace tool audit",
        "target": "http://trace.test",
        "goal": "trace tool audit",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
        "status": "stopped",
        "createdAt": web_server._now_iso(),
        "startedAt": web_server._now_iso(),
        "finishedAt": web_server._now_iso(),
        "tokensUsed": 0,
        "toolCalls": 0,
        "finalFlag": None,
        "stopReason": "done",
        "currentRunId": "run_trace_tool_audit",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    monkeypatch.setattr(web_server, "_pick_metrics_for_task", lambda project_root, item: None)
    monkeypatch.setattr(
        web_server,
        "_pick_session_snapshot",
        lambda project_root, item: (
            None,
            None,
            {"matchedBy": "none", "confidence": "none", "expectedSessionId": None, "blockedReason": None, "candidateScore": None},
        ),
    )
    monkeypatch.setattr(
        web_server,
        "_build_run_session_context",
        lambda project_root, run_id: {
            "runId": run_id,
            "recentEvents": [
                {
                    "type": "tool_called",
                    "t": "2026-05-29T10:00:00+00:00",
                    "payload": {"tool_name": "proxy_action", "action": "request", "target": "http://trace.test/login"},
                },
                {
                    "type": "tool_finished",
                    "t": "2026-05-29T10:00:01+00:00",
                    "payload": {"tool_name": "proxy_action", "action": "request", "target": "http://trace.test/login", "ok": True},
                },
            ],
            "artifacts": [],
            "latestCheckpoint": None,
            "resumeContext": None,
        },
    )

    payload = web_server._build_trace_payload(tmp_path, task, include_timeline=True)

    assert not any(event["kind"] == "tool_called" for event in payload["timeline"])
    assert not any(event["kind"] == "tool_finished" for event in payload["timeline"])
    assert any(event["kind"] == "tool_called" for event in payload["toolEvents"])
    assert any(event["kind"] == "tool_finished" for event in payload["toolEvents"])
    assert any(event["tool"] == "proxy_action" for event in payload["toolEvents"])
    assert len(payload["toolEvents"]) >= 2


def test_build_trace_payload_projects_artifacts_checkpoint_and_outcomes_from_session_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    task = {
        "id": "task_trace_harness_projection",
        "title": "trace harness projection",
        "target": "http://trace.test",
        "goal": "trace harness projection",
        "mode": "ctf",
        "modeSubtype": "web",
        "goalStyle": "flag",
        "status": "stopped",
        "createdAt": web_server._now_iso(),
        "startedAt": web_server._now_iso(),
        "finishedAt": web_server._now_iso(),
        "tokensUsed": 0,
        "toolCalls": 0,
        "finalFlag": None,
        "stopReason": "done",
        "currentRunId": "run_trace_harness_projection",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    monkeypatch.setattr(web_server, "_pick_metrics_for_task", lambda project_root, item: None)
    monkeypatch.setattr(
        web_server,
        "_pick_session_snapshot",
        lambda project_root, item: (
            None,
            None,
            {"matchedBy": "none", "confidence": "none", "expectedSessionId": None, "blockedReason": None, "candidateScore": None},
        ),
    )
    monkeypatch.setattr(
        web_server,
        "_build_run_session_context",
        lambda project_root, run_id: {
            "runId": run_id,
            "recentEvents": [
                {
                    "type": "verification_decision",
                    "t": "2026-05-29T10:00:02+00:00",
                    "payload": {
                        "decision": "candidate",
                        "flag": "flag{candidate}",
                        "evidence_source": "http-response",
                        "rationale": "flag-like string found in exploit response",
                        "confidence": 0.72,
                        "strategy_kind": "ssti_exploit",
                    },
                },
                {
                    "type": "recovery_decision",
                    "t": "2026-05-29T10:00:03+00:00",
                    "payload": {
                        "action": "explore_agenda",
                        "reason": "candidate needs stronger runtime confirmation",
                        "should_stop": False,
                        "chain_name": "ssti_exploit",
                    },
                },
                {
                    "type": "task_finished",
                    "t": "2026-05-29T10:00:04+00:00",
                    "payload": {
                        "success": False,
                        "flag": "",
                        "reason": "verifier_reject",
                        "chain_used": ["recon", "ssti_exploit"],
                        "missing_tools": [],
                    },
                },
            ],
            "artifacts": [
                {
                    "artifactId": "artifact-1",
                    "kind": "artifact",
                    "title": "ssti_response_dump",
                    "path": None,
                    "location": "http://trace.test/debug.txt",
                    "producer": "ssti_exploit",
                    "metadata": {"category": "exploit-output"},
                    "t": "2026-05-29T10:00:01+00:00",
                }
            ],
            "latestCheckpoint": {
                "checkpointId": "checkpoint-1",
                "label": "task_finished",
                "t": "2026-05-29T10:00:04+00:00",
                "metadata": {"success": False},
                "stopReason": "verifier_reject",
                "verifiedFlags": [],
                "runtimeFlags": ["flag{candidate}"],
                "artifactCount": 1,
                "observationCount": 3,
            },
            "resumeContext": None,
        },
    )

    payload = web_server._build_trace_payload(tmp_path, task, include_timeline=True)

    assert payload["sessionArtifacts"][0]["title"] == "ssti_response_dump"
    assert payload["latestCheckpoint"]["checkpointId"] == "checkpoint-1"
    assert payload["latestCheckpoint"]["stopReason"] == "verifier_reject"
    assert any(event["kind"] == "verification_decision" for event in payload["outcomeEvents"])
    assert any(event["kind"] == "recovery_decision" for event in payload["outcomeEvents"])
    assert any(event["kind"] == "task_finished" for event in payload["outcomeEvents"])


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


def test_task_detail_payload_exposes_harness_session_context_when_run_artifacts_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from pentestagent.agents.pa_agent.ctf_state import CTFState
    from pentestagent.harness.artifact_registry import ArtifactRegistry
    from pentestagent.harness.checkpoint_store import CheckpointStore
    from pentestagent.harness.session_ledger import SessionLedger

    task = {
        "id": "task_harness_context",
        "title": "harness context",
        "target": "http://ctf.local",
        "goal": "read harness context",
        "status": "completed",
        "createdAt": web_server._now_iso(),
        "startedAt": web_server._now_iso(),
        "finishedAt": web_server._now_iso(),
        "tokensUsed": 12,
        "toolCalls": 1,
        "finalFlag": "flag{ctx_ok}",
        "stopReason": "flag_verified",
        "currentRunId": "run-harness-context",
        "sessionId": None,
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    monkeypatch.setattr(web_server, "_pick_metrics_for_task", lambda project_root, item: None)
    monkeypatch.setattr(
        web_server,
        "_pick_session_snapshot",
        lambda project_root, item: (None, None, {"matchedBy": "none", "confidence": "none", "expectedSessionId": None, "blockedReason": None, "candidateScore": None}),
    )

    run_id = "run-harness-context"
    SessionLedger(tmp_path / "loot" / "session_ledgers").append_event(
        run_id,
        "task_finished",
        {"success": True, "flag": "flag{ctx_ok}"},
    )
    ArtifactRegistry(tmp_path / "loot" / "artifact_registry").register_artifact(
        run_id=run_id,
        kind="artifact",
        title="ctf_backup_candidate",
        location="http://ctf.local/www.zip",
        producer="notes",
        metadata={"category": "artifact"},
    )
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.stop_reason = "flag_verified"
    state.add_flag(
        "flag{ctx_ok}",
        level="verified",
        evidence_source="http-response",
        confidence=1.0,
    )
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={"success": True},
    )

    detail = web_server._task_detail_payload(tmp_path, task)

    assert detail["detailSource"]["sessionContext"] == "harness"
    assert detail["sessionContext"]["runId"] == run_id
    assert detail["sessionContext"]["recentEvents"][0]["type"] == "task_finished"
    assert detail["sessionContext"]["artifacts"][0]["title"] == "ctf_backup_candidate"
    assert detail["sessionContext"]["latestCheckpoint"]["stopReason"] == "flag_verified"
    assert detail["sessionContext"]["resumeContext"]["runId"] == run_id
    assert detail["sessionContext"]["resumeContext"]["stopReason"] == "flag_verified"
    assert "recent_events=task_finished" in detail["sessionContext"]["resumeContext"]["summary"]


def test_task_detail_payload_includes_harness_resume_ingress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from pentestagent.agents.pa_agent.ctf_state import CTFState
    from pentestagent.harness.checkpoint_store import CheckpointStore
    from pentestagent.harness.session_ledger import SessionLedger

    task = {
        "id": "task_resume_ingress",
        "title": "resume ingress",
        "target": "http://ctf.local",
        "goal": "拿到flag",
        "status": "failed",
        "createdAt": web_server._now_iso(),
        "startedAt": web_server._now_iso(),
        "finishedAt": web_server._now_iso(),
        "tokensUsed": 0,
        "toolCalls": 0,
        "finalFlag": None,
        "stopReason": "wrong_flag_feedback",
        "currentRunId": "run-resume-ingress",
        "hints": [],
        "messages": [],
        "plan": [],
        "notes": [],
        "knowledgeHits": [],
        "attachments": [],
    }

    monkeypatch.setattr(web_server, "_pick_metrics_for_task", lambda project_root, item: None)
    monkeypatch.setattr(
        web_server,
        "_pick_session_snapshot",
        lambda project_root, item: (
            None,
            None,
            {
                "matchedBy": "none",
                "confidence": "none",
                "expectedSessionId": None,
                "blockedReason": None,
                "candidateScore": None,
            },
        ),
    )

    run_id = "run-resume-ingress"
    SessionLedger(tmp_path / "loot" / "session_ledgers").append_event(
        run_id,
        "dispatcher_started",
        {
            "has_resume_context": True,
            "resume_run_id": "run-prev-1",
            "resume_checkpoint_id": "checkpoint-prev-1",
        },
    )
    SessionLedger(tmp_path / "loot" / "session_ledgers").append_event(
        run_id,
        "task_finished",
        {"success": False},
    )
    state = CTFState(target="http://ctf.local", goal="拿到flag")
    state.stop_reason = "wrong_flag_feedback"
    CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={"success": False},
    )

    detail = web_server._task_detail_payload(tmp_path, task)

    assert detail["detailSource"]["sessionContext"] == "harness"
    assert detail["sessionContext"]["resumeIngress"] == {
        "hasResumeContext": True,
        "runId": "run-prev-1",
        "checkpointId": "checkpoint-prev-1",
        "sourceEvent": "dispatcher_started",
    }


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
    web_server._tasks[original_task_id]["challengePath"] = r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    web_server._tasks[original_task_id]["artifactPaths"] = [
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
    ]
    web_server._tasks[original_task_id]["ingressHandoff"] = {
        "decisionKind": "direct_execute",
        "nextAction": "bootstrap_local_assets",
        "challengeContext": {
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
            ],
            "derivedTarget": "http://127.0.0.1:3000",
            "derivedTargetSource": "docker_compose_port_mapping",
            "derivedTargetComposePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        },
    }
    web_server._tasks[original_task_id]["ingressHandoff"] = {
        "decisionKind": "direct_execute",
        "nextAction": "bootstrap_local_assets",
        "challengeContext": {
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
            ],
            "derivedTarget": "http://127.0.0.1:3000",
            "derivedTargetSource": "docker_compose_port_mapping",
            "derivedTargetComposePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        },
    }
    web_server._tasks[original_task_id]["ingressHandoff"] = {
        "decisionKind": "direct_execute",
        "nextAction": "bootstrap_local_assets",
        "challengeContext": {
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
            ],
            "derivedTarget": "http://127.0.0.1:3000",
            "derivedTargetSource": "docker_compose_port_mapping",
            "derivedTargetComposePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        },
    }

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
    assert replayed_task["challengePath"] == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    assert replayed_task["artifactPaths"] == [
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
    ]
    assert replayed_task["ingressHandoff"]["challengeContext"]["derivedTarget"] == "http://127.0.0.1:3000"
    assert replayed_task["ingressHandoff"]["challengeContext"]["derivedTargetSource"] == "docker_compose_port_mapping"
    assert (
        replayed_task["ingressHandoff"]["challengeContext"]["derivedTargetComposePath"]
        == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
    )
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
async def test_trace_replay_allows_derived_target_when_source_target_missing(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "replay-derived-target", "target": "http://placeholder.test", "goal": "re-run original task"},
    )
    assert created.status == 201
    original_task = await created.json()
    original_task_id = original_task["id"]
    original_run_id = original_task["currentRunId"]
    web_server._tasks[original_task_id]["target"] = ""
    web_server._tasks[original_task_id]["mode"] = "ctf"
    web_server._tasks[original_task_id]["modeSubtype"] = "web"
    web_server._tasks[original_task_id]["goalStyle"] = "flag"
    web_server._tasks[original_task_id]["challengePath"] = r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    web_server._tasks[original_task_id]["artifactPaths"] = []
    web_server._tasks[original_task_id]["ingressHandoff"] = {
        "decisionKind": "direct_execute",
        "nextAction": "bootstrap_local_assets",
        "challengeContext": {
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [],
            "derivedTarget": "http://127.0.0.1:3000",
            "derivedTargetSource": "docker_compose_port_mapping",
            "derivedTargetComposePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        },
    }

    replay_resp = await web_client.post(f"/api/traces/{original_run_id}/replay")

    assert replay_resp.status == 200
    replayed_task = await replay_resp.json()
    assert replayed_task["controlDecision"]["decisionKind"] == "resume_execute"
    assert "derivedTargetOrigin=inherited_lineage" in replayed_task["controlDecision"]["facts"]
    assert "derivedTargetSource=docker_compose_port_mapping" in replayed_task["controlDecision"]["facts"]
    assert "derivedTargetOrigin=inherited_lineage" in replayed_task["decisionRecords"][0]["facts"]


@pytest.mark.asyncio
async def test_task_retry_allows_derived_target_when_source_target_missing(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "retry-derived-target", "target": "http://placeholder.test", "goal": "retry original task"},
    )
    assert created.status == 201
    original_task = await created.json()
    original_task_id = original_task["id"]
    web_server._tasks[original_task_id]["target"] = ""
    web_server._tasks[original_task_id]["mode"] = "ctf"
    web_server._tasks[original_task_id]["modeSubtype"] = "web"
    web_server._tasks[original_task_id]["goalStyle"] = "flag"
    web_server._tasks[original_task_id]["status"] = "failed"
    web_server._tasks[original_task_id]["challengePath"] = r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    web_server._tasks[original_task_id]["artifactPaths"] = []
    web_server._tasks[original_task_id]["ingressHandoff"] = {
        "decisionKind": "direct_execute",
        "nextAction": "bootstrap_local_assets",
        "challengeContext": {
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [],
            "derivedTarget": "http://127.0.0.1:3000",
            "derivedTargetSource": "docker_compose_port_mapping",
            "derivedTargetComposePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        },
    }

    retry_resp = await web_client.post(f"/api/tasks/{original_task_id}/retry")

    assert retry_resp.status == 200
    retried_task = await retry_resp.json()
    assert retried_task["controlDecision"]["decisionKind"] == "resume_execute"
    assert "derivedTargetOrigin=inherited_lineage" in retried_task["controlDecision"]["facts"]
    assert "derivedTargetSource=docker_compose_port_mapping" in retried_task["controlDecision"]["facts"]
    assert "derivedTargetOrigin=inherited_lineage" in retried_task["decisionRecords"][0]["facts"]


@pytest.mark.asyncio
async def test_trace_replay_inherits_resume_context_lineage_and_detail_seed(
    web_client: TestClient, tmp_path: Path
):
    from pentestagent.agents.pa_agent.ctf_state import CTFState
    from pentestagent.harness.checkpoint_store import CheckpointStore
    from pentestagent.harness.session_ledger import SessionLedger

    created = await web_client.post(
        "/api/tasks",
        json={"title": "replay-lineage", "target": "http://replay-lineage.test", "goal": "re-run original task"},
    )
    assert created.status == 201
    original_task = await created.json()
    original_task_id = original_task["id"]
    original_run_id = original_task["currentRunId"]
    web_server._tasks[original_task_id]["mode"] = "ctf"
    web_server._tasks[original_task_id]["modeSubtype"] = "web"
    web_server._tasks[original_task_id]["goalStyle"] = "flag"
    web_server._tasks[original_task_id]["challengePath"] = r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    web_server._tasks[original_task_id]["artifactPaths"] = [
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
    ]
    web_server._tasks[original_task_id]["ingressHandoff"] = {
        "decisionKind": "direct_execute",
        "nextAction": "bootstrap_local_assets",
        "challengeContext": {
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
            ],
            "derivedTarget": "http://127.0.0.1:3000",
            "derivedTargetSource": "docker_compose_port_mapping",
            "derivedTargetComposePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        },
    }

    SessionLedger(tmp_path / "loot" / "session_ledgers").append_event(
        original_run_id,
        "task_finished",
        {"success": True, "flag": "flag{replay_ctx_ok}"},
    )
    state = CTFState(target="http://replay-lineage.test", goal="拿到flag")
    state.stop_reason = "flag_verified"
    state.add_flag("flag{replay_ctx_ok}", level="verified", evidence_source="http-response", confidence=1.0)
    checkpoint = CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=original_run_id,
        label="task_finished",
        state_snapshot=state.to_snapshot(),
        metadata={"success": True},
    )

    replay_resp = await web_client.post(f"/api/traces/{original_run_id}/replay")
    assert replay_resp.status == 200
    replayed_task = await replay_resp.json()

    assert replayed_task["sourceRunId"] == original_run_id
    assert replayed_task["resumeFromRunId"] == original_run_id
    assert replayed_task["resumeFromCheckpointId"] == checkpoint["checkpoint_id"]
    assert "stop_reason=flag_verified" in replayed_task["resumeSummary"]
    assert replayed_task["sessionContext"]["resumeContext"]["runId"] == original_run_id

    detail_resp = await web_client.get(f"/api/tasks/{replayed_task['id']}")
    detail = await detail_resp.json()
    assert detail["detailSource"]["sessionContext"] == "inherited_resume"
    assert detail["sessionContext"]["resumeContext"]["runId"] == original_run_id
    assert detail["detailSource"]["derivedTarget"] == "http://127.0.0.1:3000"
    assert detail["detailSource"]["derivedTargetSource"] == "docker_compose_port_mapping"
    assert detail["detailSource"]["derivedTargetOrigin"] == "inherited_lineage"


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
    web_server._tasks[original_task_id]["challengePath"] = r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    web_server._tasks[original_task_id]["artifactPaths"] = [
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
    ]
    web_server._tasks[original_task_id]["ingressHandoff"] = {
        "decisionKind": "direct_execute",
        "nextAction": "bootstrap_local_assets",
        "challengeContext": {
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
            ],
            "derivedTarget": "http://127.0.0.1:3000",
            "derivedTargetSource": "docker_compose_port_mapping",
            "derivedTargetComposePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        },
    }

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
    assert retried_task["ctfType"] == "web"
    assert retried_task["challengePath"] == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    assert retried_task["artifactPaths"] == [
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
    ]
    assert retried_task["ingressHandoff"]["challengeContext"]["derivedTarget"] == "http://127.0.0.1:3000"
    assert retried_task["ingressHandoff"]["challengeContext"]["derivedTargetSource"] == "docker_compose_port_mapping"
    assert (
        retried_task["ingressHandoff"]["challengeContext"]["derivedTargetComposePath"]
        == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
    )
    assert "detectedType" not in retried_task
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
async def test_task_retry_inherits_resume_context_lineage_and_detail_seed(
    web_client: TestClient, tmp_path: Path
):
    from pentestagent.agents.pa_agent.ctf_state import CTFState
    from pentestagent.harness.checkpoint_store import CheckpointStore
    from pentestagent.harness.session_ledger import SessionLedger

    created = await web_client.post(
        "/api/tasks",
        json={"title": "retry-lineage", "target": "http://retry-lineage.test", "goal": "retry original task"},
    )
    assert created.status == 201
    original_task = await created.json()
    original_task_id = original_task["id"]
    original_run_id = original_task["currentRunId"]
    web_server._tasks[original_task_id]["mode"] = "ctf"
    web_server._tasks[original_task_id]["modeSubtype"] = "web"
    web_server._tasks[original_task_id]["goalStyle"] = "flag"
    web_server._tasks[original_task_id]["status"] = "failed"

    SessionLedger(tmp_path / "loot" / "session_ledgers").append_event(
        original_run_id,
        "task_finished",
        {"success": False, "reason": "wrong_flag_feedback"},
    )
    state = CTFState(target="http://retry-lineage.test", goal="拿到flag")
    state.stop_reason = "wrong_flag_feedback"
    checkpoint = CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=original_run_id,
        label="task_failed",
        state_snapshot=state.to_snapshot(),
        metadata={"success": False},
    )

    retry_resp = await web_client.post(f"/api/tasks/{original_task_id}/retry")
    assert retry_resp.status == 200
    retried_task = await retry_resp.json()

    assert retried_task["sourceRunId"] == original_run_id
    assert retried_task["resumeFromRunId"] == original_run_id
    assert retried_task["resumeFromCheckpointId"] == checkpoint["checkpoint_id"]
    assert "stop_reason=wrong_flag_feedback" in retried_task["resumeSummary"]
    assert retried_task["sessionContext"]["resumeContext"]["runId"] == original_run_id

    detail_resp = await web_client.get(f"/api/tasks/{retried_task['id']}")
    detail = await detail_resp.json()
    assert detail["detailSource"]["sessionContext"] == "inherited_resume"
    assert detail["sessionContext"]["resumeContext"]["runId"] == original_run_id


@pytest.mark.asyncio
async def test_task_retry_from_pentest_does_not_backfill_ctf_fields(web_client: TestClient):
    created = await web_client.post(
        "/api/tasks",
        json={"title": "retry-pentest", "target": "http://retry-pentest.test", "goal": "retry pentest"},
    )
    assert created.status == 201
    original_task = await created.json()
    original_task_id = original_task["id"]
    web_server._tasks[original_task_id]["status"] = "failed"

    retry_resp = await web_client.post(f"/api/tasks/{original_task_id}/retry")

    assert retry_resp.status == 200
    retried_task = await retry_resp.json()
    assert retried_task["mode"] == "pentest"
    assert retried_task["modeSubtype"] == "unknown"
    assert "ctfType" not in retried_task
    assert "detectedType" not in retried_task


@pytest.mark.asyncio
async def test_task_continue_accepts_running_task_without_creating_new_task(
    web_client: TestClient, tmp_path: Path
):
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
    web_server._tasks[task_id]["ingressHandoff"] = {
        "decisionKind": "direct_execute",
        "nextAction": "bootstrap_local_assets",
        "challengeContext": {
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
            ],
            "derivedTarget": "http://127.0.0.1:3000",
            "derivedTargetSource": "docker_compose_port_mapping",
            "derivedTargetComposePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        },
    }

    from pentestagent.agents.pa_agent.ctf_state import CTFState
    from pentestagent.harness.checkpoint_store import CheckpointStore
    from pentestagent.harness.session_ledger import SessionLedger

    SessionLedger(tmp_path / "loot" / "session_ledgers").append_event(
        run_id,
        "task_running",
        {"success": False},
    )
    state = CTFState(target="http://continue.test", goal="拿到flag")
    state.stop_reason = "waiting_for_verification"
    checkpoint = CheckpointStore(tmp_path / "loot" / "checkpoints").save_checkpoint(
        run_id=run_id,
        label="task_running",
        state_snapshot=state.to_snapshot(),
        metadata={"success": False},
    )

    continue_resp = await web_client.post(f"/api/tasks/{task_id}/continue")

    assert continue_resp.status == 200
    continue_result = await continue_resp.json()
    assert continue_result["ok"] is True
    assert continue_result["taskId"] == task_id
    assert continue_result["runId"] == run_id
    assert continue_result["accepted"] is True
    assert continue_result["sessionContext"]["resumeContext"]["runId"] == run_id
    assert continue_result["resumeFromCheckpointId"] == checkpoint["checkpoint_id"]
    assert continue_result["challengeContext"]["derivedTarget"] == "http://127.0.0.1:3000"
    assert continue_result["challengeContext"]["derivedTargetSource"] == "docker_compose_port_mapping"
    assert (
        continue_result["challengeContext"]["derivedTargetComposePath"]
        == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
    )
    assert set(web_server._tasks.keys()) == {task_id}
    assert web_server._tasks[task_id]["status"] == "running"
    assert web_server._tasks[task_id]["mode"] == "ctf"
    assert web_server._tasks[task_id]["modeSubtype"] == "web"
    assert web_server._tasks[task_id]["goalStyle"] == "flag"
    assert web_server._tasks[task_id]["hints"][-1]["text"] == "__continue__"

    detail_resp = await web_client.get(f"/api/tasks/{task_id}")
    assert detail_resp.status == 200
    detail = await detail_resp.json()
    assert detail["ingressHandoff"]["challengeContext"]["derivedTarget"] == "http://127.0.0.1:3000"


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
async def test_settings_payload_exposes_unconfigured_custom_model_readiness(
    web_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "PENTESTAGENT_MODEL=openai/gpt-5.4",
                "FH_PROVIDER=custom",
                "LITELLM_API_BASE=",
                "OPENAI_API_KEY=",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(settings_module, "_settings", None)

    resp = await web_client.get("/api/settings")

    assert resp.status == 200
    data = await resp.json()
    assert data["model"]["provider"] == "custom"
    assert data["model"]["name"] == "openai/gpt-5.4"
    assert data["model"]["readiness"] == {
        "ready": False,
        "reason": "custom_provider_unconfigured",
        "provider": "custom",
        "model": "openai/gpt-5.4",
    }


@pytest.mark.asyncio
async def test_post_task_rejects_when_model_readiness_is_false(
    web_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "PENTESTAGENT_MODEL=openai/gpt-5.4",
                "FH_PROVIDER=custom",
                "LITELLM_API_BASE=",
                "OPENAI_API_KEY=",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(settings_module, "_settings", None)

    resp = await web_client.post(
        "/api/tasks",
        json={
            "title": "blocked",
            "target": "http://challenge.test",
            "goal": "analyze challenge",
            "mode": "ctf",
        },
    )

    assert resp.status == 409
    data = await resp.json()
    assert data["error"] == "model not ready"
    assert data["reason"] == "custom_provider_unconfigured"
    assert data["readiness"]["ready"] is False
    assert web_server._tasks == {}


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
