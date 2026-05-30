from __future__ import annotations

import sys
import types
import pentestagent.config.settings as settings_module

from types import SimpleNamespace

import pytest

from pentestagent.mcp.server import mcp_tools


class _PrimaryAgentStub:
    target = None
    scope: list[str] = []
    max_iterations = 30

    def get_tools(self):
        return []


def _close_created_task(coro):
    coro.close()
    return SimpleNamespace(done=lambda: True)


@pytest.fixture(autouse=True)
def _reset_mcp_task_state(monkeypatch: pytest.MonkeyPatch, tmp_path):
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
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings_module, "_settings", None)
    mcp_tools._tasks.clear()
    monkeypatch.setattr(mcp_tools, "_primary_agent", _PrimaryAgentStub())


def test_run_task_schema_accepts_mode_and_ctf_type() -> None:
    schema = mcp_tools.mcp_tool_registry._tools["run_task"].schema

    assert "mode" in schema["properties"]
    assert "ctfType" in schema["properties"]
    assert "resumeContext" in schema["properties"]
    assert "challengePath" in schema["properties"]
    assert "artifactPaths" in schema["properties"]


def test_run_task_async_schema_accepts_mode_and_ctf_type() -> None:
    schema = mcp_tools.mcp_tool_registry._tools["run_task_async"].schema

    assert "mode" in schema["properties"]
    assert "ctfType" in schema["properties"]
    assert "resumeContext" in schema["properties"]
    assert "challengePath" in schema["properties"]
    assert "artifactPaths" in schema["properties"]


@pytest.mark.asyncio
async def test_run_task_async_resolves_mode_contract_before_task_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    async def fake_make_agent(target, scope):
        return SimpleNamespace()

    def fake_resolve_mode_contract(payload, *, source_task=None):
        seen["payload"] = dict(payload)
        seen["source_task"] = source_task
        return {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"}

    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools.asyncio, "create_task", _close_created_task)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    await mcp_tools.run_task_async(
        {
            "task": "analyze challenge",
            "target": "http://challenge.test",
            "mode": "auto",
            "ctfType": "web",
            "resumeContext": {
                "runId": "run-prev-1",
                "checkpointId": "checkpoint-prev-1",
                "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
            },
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\src\server.ts",
            ],
        }
    )

    assert seen["payload"] == {
        "task": "analyze challenge",
        "target": "http://challenge.test",
        "mode": "auto",
        "ctfType": "web",
        "resumeContext": {
            "runId": "run-prev-1",
            "checkpointId": "checkpoint-prev-1",
            "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
        },
        "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        "artifactPaths": [
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\src\server.ts",
        ],
    }
    assert seen["source_task"] is None


@pytest.mark.asyncio
async def test_run_task_async_persists_and_reports_mode_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_make_agent(target, scope):
        return SimpleNamespace()

    def fake_resolve_mode_contract(payload, *, source_task=None):
        return {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"}

    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools.asyncio, "create_task", _close_created_task)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    result = await mcp_tools.run_task_async(
        {
            "task": "analyze challenge",
            "target": "http://challenge.test",
            "mode": "auto",
            "ctfType": "web",
            "resumeContext": {
                "runId": "run-prev-1",
                "checkpointId": "checkpoint-prev-1",
                "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
            },
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\src\server.ts",
            ],
        }
    )

    assert len(mcp_tools._tasks) == 1
    entry = next(iter(mcp_tools._tasks.values()))
    assert getattr(entry, "mode", None) == "ctf"
    assert getattr(entry, "modeSubtype", None) == "web"
    assert getattr(entry, "goalStyle", None) == "flag"
    assert getattr(entry, "challengePath", None) == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    assert getattr(entry, "artifactPaths", None) == [
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\src\server.ts",
    ]
    assert getattr(entry, "resumeFromRunId", None) == "run-prev-1"
    assert getattr(entry, "resumeFromCheckpointId", None) == "checkpoint-prev-1"
    assert getattr(entry, "resumeSummary", None) == "run_id=run-prev-1; stop_reason=wrong_flag_feedback"
    assert getattr(entry, "runId", None)
    assert getattr(entry, "ledgerPath", None) == f"loot/session_ledgers/{entry.runId}.jsonl"
    assert getattr(entry, "checkpointPath", None) == f"loot/checkpoints/{entry.runId}.jsonl"
    assert "mode: ctf" in result
    assert "mode_subtype: web" in result
    assert "goal_style: flag" in result
    assert f"run_id: {entry.runId}" in result
    assert f"ledger_path: loot/session_ledgers/{entry.runId}.jsonl" in result
    assert f"checkpoint_path: loot/checkpoints/{entry.runId}.jsonl" in result
    assert "resume_from_run: run-prev-1" in result
    assert "resume_from_checkpoint: checkpoint-prev-1" in result
    assert r"challenge_path: D:\webstudy\CTF\2026\CTF比赛题\easy_login" in result
    assert r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml" in result


@pytest.mark.asyncio
async def test_get_server_status_exposes_model_readiness_reason(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(settings_module, "_settings", None)

    result = await mcp_tools.get_server_status({})

    assert "ready:      True" in result
    assert "model_ready: False" in result
    assert "model_readiness_reason: custom_provider_unconfigured" in result


@pytest.mark.asyncio
async def test_run_task_async_rejects_when_model_is_not_ready(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(settings_module, "_settings", None)

    result = await mcp_tools.run_task_async(
        {
            "task": "analyze challenge",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
        }
    )

    assert result == "[error] model_not_ready: custom_provider_unconfigured"
    assert mcp_tools._tasks == {}


class _ForbiddenMcpAgent:
    def __init__(self):
        self.runtime = object()
        self.tools = []

    async def run_mcp(self, task):
        raise AssertionError("run_mcp should not be used for MCP CTF dispatcher path")


@pytest.mark.asyncio
async def test_run_task_routes_ctf_mode_into_dispatcher_with_explicit_challenge_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_make_agent(target, scope):
        return _ForbiddenMcpAgent()

    def fake_resolve_mode_contract(payload, *, source_task=None):
        return {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"}

    class _FakeDispatcher:
        def __init__(self, runtime, progress_callback=None, verification_callback=None):
            captured["runtime"] = runtime

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None, run_id=None, ledger_root=None, checkpoint_root=None):
            captured["target"] = target
            captured["goal"] = goal
            captured["type"] = type
            captured["hint"] = hint
            captured["challenge_context"] = challenge_context
            return SimpleNamespace(flag="flag{mcp_ctf_ok}", reason="ok", chain_used=["xss"], missing_tools=[], notes=[])

    fake_dispatcher_module = types.ModuleType("pentestagent.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    result = await mcp_tools.run_task(
        {
            "task": "solve easy_login from MCP",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "resumeContext": {
                "runId": "run-prev-1",
                "checkpointId": "checkpoint-prev-1",
                "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
            },
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\README.md",
            ],
        }
    )

    assert captured["target"] == "http://challenge.test"
    assert captured["goal"] == "solve easy_login from MCP"
    assert captured["type"] == "web"
    assert captured["challenge_context"] == {
        "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        "artifactPaths": [
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\README.md",
        ],
        "resumeContext": {
            "runId": "run-prev-1",
            "checkpointId": "checkpoint-prev-1",
            "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
        },
    }
    assert "flag{mcp_ctf_ok}" in result


@pytest.mark.asyncio
async def test_run_task_async_background_ctf_path_uses_explicit_challenge_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_make_agent(target, scope):
        return _ForbiddenMcpAgent()

    def fake_resolve_mode_contract(payload, *, source_task=None):
        return {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"}

    class _FakeDispatcher:
        def __init__(self, runtime, progress_callback=None, verification_callback=None):
            captured["runtime"] = runtime

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None, run_id=None, ledger_root=None, checkpoint_root=None):
            captured["target"] = target
            captured["goal"] = goal
            captured["type"] = type
            captured["hint"] = hint
            captured["challenge_context"] = challenge_context
            captured["run_id"] = run_id
            return SimpleNamespace(flag="flag{mcp_async_ctf_ok}", reason="ok", chain_used=["xss"], missing_tools=[], notes=[])

    def fake_create_task(coro):
        captured["scheduled_coro"] = coro
        return SimpleNamespace(done=lambda: False)

    fake_dispatcher_module = types.ModuleType("pentestagent.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    result = await mcp_tools.run_task_async(
        {
            "task": "solve easy_login from MCP async",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "resumeContext": {
                "runId": "run-prev-1",
                "checkpointId": "checkpoint-prev-1",
                "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
            },
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            ],
        }
    )

    assert "task_id:" in result
    scheduled = captured.get("scheduled_coro")
    assert scheduled is not None
    await scheduled

    assert captured["target"] == "http://challenge.test"
    assert captured["goal"] == "solve easy_login from MCP async"
    assert captured["type"] == "web"
    assert str(captured["run_id"]).startswith("mcp-ctf-")
    assert captured["challenge_context"] == {
        "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        "artifactPaths": [
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        ],
        "resumeContext": {
            "runId": "run-prev-1",
            "checkpointId": "checkpoint-prev-1",
            "summary": "run_id=run-prev-1; stop_reason=wrong_flag_feedback",
        },
    }



@pytest.mark.asyncio
async def test_run_task_persists_ctf_dispatcher_truth_fields_for_followup_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_make_agent(target, scope):
        return _ForbiddenMcpAgent()

    def fake_resolve_mode_contract(payload, *, source_task=None):
        return {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"}

    class _FakeDispatcher:
        def __init__(self, runtime, progress_callback=None, verification_callback=None):
            pass

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None, run_id=None, ledger_root=None, checkpoint_root=None):
            return SimpleNamespace(
                flag="flag{mcp_truth_ok}",
                reason="verified",
                chain_used=["xss", "admin_bot"],
                missing_tools=["sqlmap"],
                notes=["reused admin sid", "collector hit /admin"],
            )

    fake_dispatcher_module = types.ModuleType("pentestagent.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
    monkeypatch.setitem(sys.modules, "pentestagent.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    await mcp_tools.run_task(
        {
            "task": "solve from MCP truth fields",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
        }
    )

    entry = next(iter(mcp_tools._tasks.values()))
    assert getattr(entry, "finalFlag", None) == "flag{mcp_truth_ok}"
    assert getattr(entry, "ctfChainUsed", None) == ["xss", "admin_bot"]
    assert getattr(entry, "ctfMissingTools", None) == ["sqlmap"]
    assert getattr(entry, "ctfNotes", None) == ["reused admin sid", "collector hit /admin"]


@pytest.mark.asyncio
async def test_mcp_task_inspection_and_result_expose_ctf_truth_fields() -> None:
    entry = mcp_tools.TaskEntry(
        id="ctf12345",
        task="solve challenge",
        status="done",
        created_at="2026-05-29T00:00:00",
        finished_at="2026-05-29T00:01:00",
        agent=SimpleNamespace(runtime=None, tools=[]),
        target="http://challenge.test",
        scope=[],
        result="flag{inspection_truth}",
        mode="ctf",
        modeSubtype="web",
        goalStyle="flag",
        challengePath=r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        artifactPaths=[r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"],
    )
    entry.runId = "mcp-ctf-12345"
    entry.ledgerPath = "loot/session_ledgers/mcp-ctf-12345.jsonl"
    entry.checkpointPath = "loot/checkpoints/mcp-ctf-12345.jsonl"
    entry.resumeFromRunId = "run-prev-1"
    entry.resumeFromCheckpointId = "checkpoint-prev-1"
    entry.resumeSummary = "run_id=run-prev-1; stop_reason=wrong_flag_feedback"
    entry.finalFlag = "flag{inspection_truth}"
    entry.ctfChainUsed = ["xss", "admin_bot"]
    entry.ctfMissingTools = ["sqlmap"]
    entry.ctfNotes = ["reused admin sid", "collector hit /admin"]
    mcp_tools._tasks[entry.id] = entry

    list_output = await mcp_tools.list_tasks({"limit": 20})
    status_output = await mcp_tools.get_task_status({"task_id": entry.id})
    result_output = await mcp_tools.get_task_result({"task_id": entry.id})

    assert "mode=ctf/web" in list_output
    assert "chain=xss,admin_bot" in list_output

    assert "mode:       ctf" in status_output
    assert "mode_subtype: web" in status_output
    assert "goal_style: flag" in status_output
    assert "run_id:     mcp-ctf-12345" in status_output
    assert "ledger_path: loot/session_ledgers/mcp-ctf-12345.jsonl" in status_output
    assert "checkpoint_path: loot/checkpoints/mcp-ctf-12345.jsonl" in status_output
    assert "resume_from_run: run-prev-1" in status_output
    assert "resume_from_checkpoint: checkpoint-prev-1" in status_output
    assert "final_flag: flag{inspection_truth}" in status_output
    assert "ctf_chain_used: xss, admin_bot" in status_output
    assert "ctf_missing_tools: sqlmap" in status_output
    assert "ctf_notes: reused admin sid | collector hit /admin" in status_output

    assert "mode:        ctf" in result_output
    assert "mode_subtype: web" in result_output
    assert "goal_style:  flag" in result_output
    assert "run_id:      mcp-ctf-12345" in result_output
    assert "ledger_path: loot/session_ledgers/mcp-ctf-12345.jsonl" in result_output
    assert "checkpoint_path: loot/checkpoints/mcp-ctf-12345.jsonl" in result_output
    assert "resume_from_run: run-prev-1" in result_output
    assert "resume_from_checkpoint: checkpoint-prev-1" in result_output
    assert "final_flag:  flag{inspection_truth}" in result_output
    assert "\n[ctf_chain_used]\n  xss\n  admin_bot" in result_output
    assert "\n[ctf_missing_tools]\n  sqlmap" in result_output
    assert "\n[ctf_notes]\n  reused admin sid\n  collector hit /admin" in result_output
