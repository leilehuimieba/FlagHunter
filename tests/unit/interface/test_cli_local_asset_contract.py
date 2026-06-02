from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from pentestagent.interface import cli as interface_cli


class _FakeRuntime:
    def __init__(self):
        self.mcp_manager = None


@pytest.fixture
def _mute_cli_console(monkeypatch):
    monkeypatch.setattr(interface_cli.console, "print", lambda *args, **kwargs: None)


def test_parse_arguments_accepts_cli_local_asset_contract(monkeypatch) -> None:
    interface_main = importlib.import_module("pentestagent.interface.main")
    monkeypatch.setattr(
        "sys.argv",
        [
            "pentestagent",
            "run",
            "--target",
            "http://127.0.0.1:3000",
            "--mode",
            "ctf",
            "--ctf-type",
            "web",
            "--challenge-path",
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "--artifact-path",
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            "--artifact-path",
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\README.md",
            "solve easy_login",
        ],
    )

    _, args = interface_main.parse_arguments()

    assert args.mode == "ctf"
    assert args.ctf_type == "web"
    assert args.challenge_path == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    assert args.artifact_path == [
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\README.md",
    ]


def test_cli_ctf_dispatcher_hint_includes_control_decision_for_bootstrap_local_assets() -> None:
    hint = interface_cli._ctf_dispatcher_hint(
        challenge_path=r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        artifact_paths=[
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\README.md",
        ],
        control_decision={
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "ctf local assets available",
            "nextAction": "bootstrap_local_assets",
        },
    )

    assert "[local_ctf_assets]" in hint
    assert "[control_decision]" in hint
    assert "decisionKind=direct_execute" in hint
    assert "nextAction=bootstrap_local_assets" in hint


def test_cli_ctf_dispatcher_hint_includes_endpoint_verified_and_runtime_signal_fields() -> None:
    blackboard_snapshot = {
        "facts": [
            {"kind": "discovered_endpoint", "value": "http://challenge.test/admin"},
            {"kind": "verified_flag", "value": "flag{verified_candidate}"},
        ],
        "pending_verifications": [
            {"kind": "runtime_flag", "value": "flag{runtime_candidate}"},
        ],
    }

    endpoint_hint = interface_cli._ctf_dispatcher_hint(
        control_decision={
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "discovered endpoint present in blackboard",
            "nextAction": "probe_discovered_endpoint",
            "driver": "blackboard.discovered_endpoint",
        },
        blackboard_snapshot=blackboard_snapshot,
    )
    verified_hint = interface_cli._ctf_dispatcher_hint(
        control_decision={
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "verified flag already present in blackboard",
            "nextAction": "verify_or_submit_flag",
            "driver": "blackboard.verified_flag",
        },
        blackboard_snapshot=blackboard_snapshot,
    )
    runtime_hint = interface_cli._ctf_dispatcher_hint(
        control_decision={
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "runtime flag pending verification in blackboard",
            "nextAction": "verify_runtime_signal",
            "driver": "blackboard.runtime_flag",
        },
        blackboard_snapshot=blackboard_snapshot,
    )

    assert "endpoint=http://challenge.test/admin" in endpoint_hint
    assert "verifiedFlag=flag{verified_candidate}" in verified_hint
    assert "runtimeFlag=flag{runtime_candidate}" in runtime_hint


def test_sync_runtime_challenge_context_persists_derived_target_fields() -> None:
    challenge_context = {
        "challengePath": r"D:\webstudy\CTF\2026\easy_login",
        "artifactPaths": [r"D:\webstudy\CTF\2026\easy_login\docker-compose.yml"],
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

    derived_target = interface_cli._sync_runtime_challenge_context(
        challenge_context,
        dispatcher,
    )

    assert derived_target == "http://127.0.0.1:3000"
    assert challenge_context["derivedTarget"] == "http://127.0.0.1:3000"
    assert challenge_context["derivedTargetSource"] == "docker_compose_port_mapping"
    assert (
        challenge_context["derivedTargetComposePath"]
        == r"D:\webstudy\CTF\2026\easy_login\docker-compose.yml"
    )


@pytest.mark.asyncio
async def test_run_cli_routes_ctf_mode_into_dispatcher_with_local_asset_hint(monkeypatch, _mute_cli_console) -> None:
    captured = {}

    monkeypatch.setattr(interface_cli, "resolve_mode_contract", lambda payload, source_task=None: {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"}, raising=False)
    monkeypatch.setattr("pentestagent.interface.initializer.activate_workspace_for_target", lambda *args, **kwargs: None)

    async def _fake_build_runtime(**kwargs):
        return _FakeRuntime(), {"label": "Local", "status_text": "ok"}

    monkeypatch.setattr("pentestagent.interface.initializer.build_runtime", _fake_build_runtime)
    monkeypatch.setattr("pentestagent.interface.initializer.has_ssh_runtime_config", lambda: False)
    monkeypatch.setattr("pentestagent.interface.cli.Path.exists", lambda self: False)
    monkeypatch.setattr("pentestagent.interface.cli.get_all_tools", lambda: [], raising=False)

    class _FakeDispatcher:
        def __init__(self, runtime, progress_callback=None, verification_callback=None):
            captured["runtime"] = runtime
            captured["progress_callback"] = progress_callback

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None):
            captured["target"] = target
            captured["goal"] = goal
            captured["type"] = type
            captured["hint"] = hint
            captured["challenge_context"] = challenge_context
            return SimpleNamespace(flag="flag{cli_ctf_ok}", reason="ok", chain_used=["xss"], missing_tools=[], notes=[])

    class _ForbiddenAgent:
        def __init__(self, *args, **kwargs):
            raise AssertionError("PentestAgentAgent should not be constructed for CLI CTF mode")

    monkeypatch.setattr("pentestagent.agents.pa_agent.PentestAgentAgent", _ForbiddenAgent)
    monkeypatch.setattr("pentestagent.agents.pa_agent.ctf_dispatcher.CTFTaskDispatcher", _FakeDispatcher)
    monkeypatch.setattr("pentestagent.interface.cli.CTFTaskDispatcher", _FakeDispatcher, raising=False)

    await interface_cli.run_cli(
        target="http://127.0.0.1:3000",
        model="gpt-5",
        task="solve the challenge",
        mode="ctf",
        ctf_type="web",
        challenge_path=r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        artifact_paths=[
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\README.md",
        ],
    )

    assert captured["target"] == "http://127.0.0.1:3000"
    assert captured["type"] == "web"
    assert captured["challenge_context"] == {
        "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        "artifactPaths": [
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\README.md",
        ],
    }
    assert "[local_ctf_assets]" in captured["hint"]
    assert "[control_decision]" in captured["hint"]
    assert "nextAction=bootstrap_local_assets" in captured["hint"]
    assert r"D:\webstudy\CTF\2026\CTF比赛题\easy_login" in captured["hint"]
    assert r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml" in captured["hint"]


@pytest.mark.asyncio
async def test_run_cli_syncs_derived_target_into_challenge_context_when_target_missing(
    monkeypatch,
    _mute_cli_console,
) -> None:
    captured = {}

    monkeypatch.setattr(
        interface_cli,
        "resolve_mode_contract",
        lambda payload, source_task=None: {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"},
        raising=False,
    )
    monkeypatch.setattr(
        "pentestagent.interface.initializer.activate_workspace_for_target",
        lambda *args, **kwargs: None,
    )

    async def _fake_build_runtime(**kwargs):
        return _FakeRuntime(), {"label": "Local", "status_text": "ok"}

    monkeypatch.setattr("pentestagent.interface.initializer.build_runtime", _fake_build_runtime)
    monkeypatch.setattr("pentestagent.interface.initializer.has_ssh_runtime_config", lambda: False)
    monkeypatch.setattr("pentestagent.interface.cli.Path.exists", lambda self: False)
    monkeypatch.setattr("pentestagent.interface.cli.get_all_tools", lambda: [], raising=False)

    class _FakeDispatcher:
        def __init__(self, runtime, progress_callback=None, verification_callback=None):
            self._challenge_context = {}

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None):
            captured["target"] = target
            captured["challenge_context"] = challenge_context
            self._challenge_context = {
                "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
                "artifactPaths": [
                    r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
                ],
                "derivedTarget": "http://127.0.0.1:3000",
                "derivedTargetSource": "docker_compose_port_mapping",
                "derivedTargetComposePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            }
            return SimpleNamespace(flag="flag{cli_ctf_ok}", reason="ok", chain_used=["xss"], missing_tools=[], notes=[])

    class _ForbiddenAgent:
        def __init__(self, *args, **kwargs):
            raise AssertionError("PentestAgentAgent should not be constructed for CLI CTF mode")

    monkeypatch.setattr("pentestagent.agents.pa_agent.PentestAgentAgent", _ForbiddenAgent)
    monkeypatch.setattr("pentestagent.agents.pa_agent.ctf_dispatcher.CTFTaskDispatcher", _FakeDispatcher)
    monkeypatch.setattr("pentestagent.interface.cli.CTFTaskDispatcher", _FakeDispatcher, raising=False)

    await interface_cli.run_cli(
        target="",
        model="gpt-5",
        task="solve the challenge",
        mode="ctf",
        ctf_type="web",
        challenge_path=r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        artifact_paths=[
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
        ],
    )

    assert captured["target"] == ""
    assert captured["challenge_context"]["derivedTarget"] == "http://127.0.0.1:3000"
    assert (
        captured["challenge_context"]["derivedTargetSource"]
        == "docker_compose_port_mapping"
    )
    assert (
        captured["challenge_context"]["derivedTargetComposePath"]
        == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
    )


@pytest.mark.asyncio
async def test_run_cli_keeps_pentest_path_on_non_ctf_mode(monkeypatch, _mute_cli_console) -> None:
    observed = {"agent_called": False, "dispatcher_called": False}

    monkeypatch.setattr(interface_cli, "resolve_mode_contract", lambda payload, source_task=None: {"mode": "pentest", "modeSubtype": "unknown", "goalStyle": "evidence"}, raising=False)
    monkeypatch.setattr("pentestagent.interface.initializer.activate_workspace_for_target", lambda *args, **kwargs: None)

    async def _fake_build_runtime(**kwargs):
        return _FakeRuntime(), {"label": "Local", "status_text": "ok"}

    monkeypatch.setattr("pentestagent.interface.initializer.build_runtime", _fake_build_runtime)
    monkeypatch.setattr("pentestagent.interface.initializer.has_ssh_runtime_config", lambda: False)
    monkeypatch.setattr("pentestagent.interface.cli.Path.exists", lambda self: False)
    monkeypatch.setattr("pentestagent.interface.cli.get_all_tools", lambda: [], raising=False)

    class _FakeAgent:
        def __init__(self, *args, **kwargs):
            observed["agent_called"] = True

        async def agent_loop(self, task_msg):
            if False:
                yield None
            return

    class _ForbiddenDispatcher:
        def __init__(self, *args, **kwargs):
            observed["dispatcher_called"] = True
            raise AssertionError("dispatcher should not be used for pentest CLI mode")

    monkeypatch.setattr("pentestagent.agents.pa_agent.PentestAgentAgent", _FakeAgent)
    monkeypatch.setattr("pentestagent.agents.pa_agent.ctf_dispatcher.CTFTaskDispatcher", _ForbiddenDispatcher)

    await interface_cli.run_cli(
        target="http://corp.test",
        model="gpt-5",
        task="enumerate the target",
        mode="pentest",
    )

    assert observed["agent_called"] is True
    assert observed["dispatcher_called"] is False
