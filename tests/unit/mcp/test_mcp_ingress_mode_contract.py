from __future__ import annotations

import sys
import types
import flaghunter.config.settings as settings_module

from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.harness.artifact_registry import ArtifactRegistry
from flaghunter.harness.audit_events import (
    build_control_action_completed_event,
    build_control_action_started_event,
)
from flaghunter.harness.checkpoint_store import CheckpointStore
from flaghunter.harness.session_ledger import SessionLedger
from flaghunter.mcp.server import mcp_tools


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
                "FLAGHUNTER_MODEL=openai/gpt-5.4",
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


def test_mcp_ctf_dispatcher_hint_includes_runtime_flag_for_verify_runtime_signal() -> None:
    entry = mcp_tools.TaskEntry(
        id="task-rt-1",
        task="verify runtime signal",
        status="pending",
        created_at="2026-06-02T00:00:00",
        agent=SimpleNamespace(),
        target="http://challenge.test",
        mode="ctf",
        modeSubtype="web",
        controlDecision={
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "runtime flag present in blackboard",
            "nextAction": "verify_runtime_signal",
            "driver": "blackboard.runtime_flag",
        },
        ctfStateSnapshot={
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
    )

    hint = mcp_tools._ctf_dispatcher_hint(entry)

    assert "[control_decision]" in hint
    assert "nextAction=verify_runtime_signal" in hint
    assert "runtimeFlag=flag{runtime_candidate}" in hint


def test_mcp_ctf_dispatcher_hint_includes_verified_flag_for_verify_or_submit_action() -> None:
    entry = mcp_tools.TaskEntry(
        id="task-vf-1",
        task="verify or submit flag",
        status="pending",
        created_at="2026-06-02T00:00:00",
        agent=SimpleNamespace(),
        target="http://challenge.test",
        mode="ctf",
        modeSubtype="web",
        controlDecision={
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "verified flag already present in blackboard",
            "nextAction": "verify_or_submit_flag",
            "driver": "blackboard.verified_flag",
        },
        ctfStateSnapshot={
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
    )

    hint = mcp_tools._ctf_dispatcher_hint(entry)

    assert "[control_decision]" in hint
    assert "nextAction=verify_or_submit_flag" in hint
    assert "verifiedFlag=flag{verified_candidate}" in hint


def test_mcp_build_ingress_handoff_includes_structured_endpoint_for_probe_action() -> None:
    entry = mcp_tools.TaskEntry(
        id="task-endpoint-1",
        task="probe endpoint",
        status="pending",
        created_at="2026-06-04T00:00:00",
        agent=SimpleNamespace(),
        target="http://challenge.test",
        mode="ctf",
        modeSubtype="web",
        controlDecision={
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "discovered endpoint present in blackboard",
            "nextAction": "probe_discovered_endpoint",
            "driver": "blackboard.discovered_endpoint",
        },
        ctfStateSnapshot={
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
    )

    handoff = mcp_tools._build_ingress_handoff(entry)

    assert handoff["nextAction"] == "probe_discovered_endpoint"
    assert handoff["endpoint"] == "http://challenge.test/admin"


def test_mcp_build_ingress_handoff_includes_recommended_action_provenance_for_collect_initial_facts() -> None:
    entry = mcp_tools.TaskEntry(
        id="task-provenance-1",
        task="collect initial facts",
        status="pending",
        created_at="2026-06-04T00:00:00",
        agent=SimpleNamespace(),
        target="http://challenge.test",
        mode="ctf",
        modeSubtype="web",
        controlDecision={
            "shouldRun": True,
            "decisionKind": "explore_first",
            "reason": "derived target available for initial fact collection",
            "nextAction": "collect_initial_facts",
            "driver": "blackboard.derived_target.runtime_derived",
            "facts": [
                "mode=ctf",
                "recommendedActionSourceType=observation",
                "recommendedActionSwitchedFrom=probe_discovered_endpoint",
                "recommendedActionTriggerReason=endpoint probe returned empty findings",
                "recommendedActionTriggerActionDriver=blackboard.derived_target.runtime_derived",
                "recommendedActionTriggerAt=2026-06-03T10:00:02+00:00",
                "strongestHypothesisKind=generic_web_recon",
                "strongestHypothesisStatus=active",
            ],
        },
        ctfStateSnapshot={
            "hypotheses": [
                {
                    "id": "hyp-1",
                    "kind": "generic_web_recon",
                    "description": "continue broad web recon",
                    "confidence": 0.52,
                    "status": "active",
                }
            ],
            "observations": [],
            "artifacts": [],
            "runtime_flags": [],
            "verified_flags": [],
        },
    )

    handoff = mcp_tools._build_ingress_handoff(entry)

    assert handoff["decisionKind"] == "explore_first"
    assert handoff["nextAction"] == "collect_initial_facts"
    assert handoff["driver"] == "blackboard.derived_target.runtime_derived"
    assert handoff["reason"] == "derived target available for initial fact collection"
    assert handoff["sourceType"] == "observation"
    assert handoff["switchedFrom"] == "probe_discovered_endpoint"
    assert handoff["triggerReason"] == "endpoint probe returned empty findings"
    assert handoff["triggerActionDriver"] == "blackboard.derived_target.runtime_derived"
    assert handoff["triggerAt"] == "2026-06-03T10:00:02+00:00"
    assert handoff["strongestHypothesisKind"] == "generic_web_recon"
    assert handoff["strongestHypothesisStatus"] == "active"
    assert handoff["strongestHypothesisConfidence"] == 0.52


def test_mcp_build_ingress_handoff_includes_structured_runtime_flag_for_verify_runtime_signal() -> None:
    entry = mcp_tools.TaskEntry(
        id="task-rt-handoff-1",
        task="verify runtime signal",
        status="pending",
        created_at="2026-06-04T00:00:00",
        agent=SimpleNamespace(),
        target="http://challenge.test",
        mode="ctf",
        modeSubtype="web",
        controlDecision={
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "runtime flag present in blackboard",
            "nextAction": "verify_runtime_signal",
            "driver": "blackboard.runtime_flag",
        },
        ctfStateSnapshot={
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
    )

    handoff = mcp_tools._build_ingress_handoff(entry)

    assert handoff["nextAction"] == "verify_runtime_signal"
    assert handoff["runtimeFlag"] == "flag{runtime_candidate}"


def test_mcp_build_ingress_handoff_includes_structured_verified_flag_for_verify_or_submit() -> None:
    entry = mcp_tools.TaskEntry(
        id="task-vf-handoff-1",
        task="verify or submit flag",
        status="pending",
        created_at="2026-06-04T00:00:00",
        agent=SimpleNamespace(),
        target="http://challenge.test",
        mode="ctf",
        modeSubtype="web",
        controlDecision={
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "verified flag already present in blackboard",
            "nextAction": "verify_or_submit_flag",
            "driver": "blackboard.verified_flag",
        },
        ctfStateSnapshot={
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
    )

    handoff = mcp_tools._build_ingress_handoff(entry)

    assert handoff["nextAction"] == "verify_or_submit_flag"
    assert handoff["verifiedFlag"] == "flag{verified_candidate}"


def test_mcp_ctf_dispatcher_hint_includes_strongest_hypothesis_fields() -> None:
    entry = mcp_tools.TaskEntry(
        id="task-hyp-1",
        task="probe strongest hypothesis",
        status="pending",
        created_at="2026-06-04T00:00:00",
        agent=SimpleNamespace(),
        target="http://challenge.test",
        mode="ctf",
        modeSubtype="web",
        controlDecision={
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "strongest blackboard hypothesis favors endpoint probing",
            "nextAction": "probe_discovered_endpoint",
            "driver": "blackboard.hypothesis.auth_form_sqli",
            "facts": [
                "mode=ctf",
                "blackboard.hypothesis=present",
                "strongestHypothesisKind=auth_form_sqli",
                "strongestHypothesisStatus=supported",
            ],
        },
        ctfStateSnapshot={
            "observations": [
                {
                    "kind": "recon_url",
                    "value": "http://challenge.test/login",
                    "source": "recon",
                    "metadata": {"confidence": "high"},
                }
            ],
            "hypotheses": [
                {
                    "id": "hyp-1",
                    "kind": "auth_form_sqli",
                    "description": "login form may be injectable",
                    "confidence": 0.78,
                    "status": "supported",
                }
            ],
            "artifacts": [],
            "runtime_flags": [],
            "verified_flags": [],
        },
    )

    hint = mcp_tools._ctf_dispatcher_hint(entry)

    assert "strongestHypothesisKind=auth_form_sqli" in hint
    assert "strongestHypothesisStatus=supported" in hint
    assert "strongestHypothesisConfidence=0.78" in hint


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
async def test_run_task_async_persists_control_decision_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_make_agent(target, scope):
        return SimpleNamespace()

    def fake_resolve_mode_contract(payload, *, source_task=None):
        return {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"}

    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools.asyncio, "create_task", _close_created_task)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    await mcp_tools.run_task_async(
        {
            "task": "analyze challenge",
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

    entry = next(iter(mcp_tools._tasks.values()))
    assert getattr(entry, "controlDecision", None) is not None
    assert entry.controlDecision["shouldRun"] is True
    assert entry.controlDecision["decisionKind"] == "resume_execute"
    assert entry.controlDecision["nextAction"] == "resume_from_checkpoint"
    assert entry.controlDecision["driver"] == "task.resume_context"
    assert entry.decisionRecords[0]["driver"] == "task.resume_context"
    assert entry.ingressHandoff["decisionKind"] == "resume_execute"
    assert entry.ingressHandoff["nextAction"] == "resume_from_checkpoint"
    assert entry.ingressHandoff["challengeContext"]["challengePath"] == r"D:\webstudy\CTF\2026\CTF比赛题\easy_login"
    assert entry.ingressHandoff["resumeBootstrap"]["runId"] == "run-prev-1"
    assert entry.ingressHandoff["resumeBootstrap"]["checkpointId"] == "checkpoint-prev-1"


@pytest.mark.asyncio
async def test_run_task_async_prioritizes_verified_flag_over_resume_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_make_agent(target, scope):
        return SimpleNamespace()

    def fake_resolve_mode_contract(payload, *, source_task=None):
        return {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"}

    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools.asyncio, "create_task", _close_created_task)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    await mcp_tools.run_task_async(
        {
            "task": "verify flagged replay",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "resumeContext": {
                "runId": "run-prev-verified-1",
                "checkpointId": "checkpoint-prev-verified-1",
                "summary": "run_id=run-prev-verified-1; stop_reason=flag_verified",
            },
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            ],
            "blackboardSnapshot": {
                "facts": [
                    {
                        "kind": "verified_flag",
                        "value": "flag{mcp_verified_priority}",
                        "source": "platform-accept",
                    }
                ],
                "pendingVerifications": [],
            },
        }
    )

    entry = next(iter(mcp_tools._tasks.values()))
    assert entry.controlDecision["decisionKind"] == "direct_execute"
    assert entry.controlDecision["nextAction"] == "verify_or_submit_flag"
    assert entry.controlDecision["driver"] == "blackboard.verified_flag"
    assert entry.decisionRecords[0]["driver"] == "blackboard.verified_flag"
    assert entry.ingressHandoff["decisionKind"] == "direct_execute"
    assert entry.ingressHandoff["nextAction"] == "verify_or_submit_flag"
    assert entry.ingressHandoff["resumeBootstrap"] is None


@pytest.mark.asyncio
async def test_run_task_async_prioritizes_runtime_flag_over_resume_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_make_agent(target, scope):
        return SimpleNamespace()

    def fake_resolve_mode_contract(payload, *, source_task=None):
        return {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"}

    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools.asyncio, "create_task", _close_created_task)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    await mcp_tools.run_task_async(
        {
            "task": "verify runtime signal replay",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "resumeContext": {
                "runId": "run-prev-runtime-1",
                "checkpointId": "checkpoint-prev-runtime-1",
                "summary": "run_id=run-prev-runtime-1; stop_reason=runtime_flag_pending",
            },
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            ],
            "blackboardSnapshot": {
                "facts": [],
                "pendingVerifications": [
                    {
                        "kind": "runtime_flag",
                        "value": "flag{mcp_runtime_priority}",
                        "source": "runtime-http",
                    }
                ],
            },
        }
    )

    entry = next(iter(mcp_tools._tasks.values()))
    assert entry.controlDecision["decisionKind"] == "direct_execute"
    assert entry.controlDecision["nextAction"] == "verify_runtime_signal"
    assert entry.controlDecision["driver"] == "blackboard.runtime_flag"
    assert entry.decisionRecords[0]["driver"] == "blackboard.runtime_flag"
    assert entry.ingressHandoff["decisionKind"] == "direct_execute"
    assert entry.ingressHandoff["nextAction"] == "verify_runtime_signal"
    assert entry.ingressHandoff["resumeBootstrap"] is None


def test_sync_runtime_challenge_context_persists_derived_target_fields() -> None:
    entry = mcp_tools.TaskEntry(
        id="entry-derived-target-1",
        task="solve challenge",
        status="running",
        created_at="2026-06-02T00:00:00",
        agent=SimpleNamespace(runtime=None, tools=[]),
        target=None,
        ingressHandoff={
            "decisionKind": "direct_execute",
            "nextAction": "bootstrap_local_assets",
            "challengeContext": {
                "challengePath": r"D:\webstudy\CTF\2026\easy_login",
                "artifactPaths": [r"D:\webstudy\CTF\2026\easy_login\docker-compose.yml"],
            },
        },
    )
    dispatcher = SimpleNamespace(
        _challenge_context={
            "challengePath": r"D:\webstudy\CTF\2026\easy_login",
            "artifactPaths": [r"D:\webstudy\CTF\2026\easy_login\docker-compose.yml"],
            "derivedTarget": "http://127.0.0.1:3000",
            "derivedTargetSource": "docker_compose_port_mapping",
            "derivedTargetComposePath": r"D:\webstudy\CTF\2026\easy_login\docker-compose.yml",
        }
    )

    mcp_tools._sync_runtime_challenge_context(entry, dispatcher)

    assert entry.target == "http://127.0.0.1:3000"
    challenge_context = entry.ingressHandoff["challengeContext"]
    assert challenge_context["derivedTarget"] == "http://127.0.0.1:3000"
    assert challenge_context["derivedTargetSource"] == "docker_compose_port_mapping"
    assert (
        challenge_context["derivedTargetComposePath"]
        == r"D:\webstudy\CTF\2026\easy_login\docker-compose.yml"
    )


@pytest.mark.asyncio
async def test_run_task_async_reports_control_decision_in_text_output(
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
            "mode": "ctf",
            "ctfType": "web",
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            ],
        }
    )

    assert "control_decision: direct_execute" in result


@pytest.mark.asyncio
async def test_run_task_async_reports_next_action_explanation_for_resume_ingress(
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
            "task": "resume challenge run",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "resumeContext": {
                "runId": "run-prev-1",
                "checkpointId": "checkpoint-prev-1",
                "summary": "continue from saved recon state",
            },
        }
    )

    assert "next_action_decision_kind: resume_execute" in result
    assert "next_action: resume_from_checkpoint" in result
    assert "next_action_driver: task.resume_context" in result
    assert "next_action_reason: resume context available" in result
    assert (
        "next_action_summary: resume_execute -> resume_from_checkpoint via task.resume_context"
        in result
    )


@pytest.mark.asyncio
async def test_run_task_async_blocked_control_decision_does_not_schedule_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {"scheduled": False}

    async def fake_make_agent(target, scope):
        return SimpleNamespace()

    def fake_create_task(coro):
        captured["scheduled"] = True
        coro.close()
        return SimpleNamespace(done=lambda: False)

    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools.asyncio, "create_task", fake_create_task)

    result = await mcp_tools.run_task_async(
        {
            "task": "need more input before execution",
            "target": "",
        }
    )

    entry = next(iter(mcp_tools._tasks.values()))
    assert entry.controlDecision["shouldRun"] is False
    assert entry.controlDecision["decisionKind"] == "blocked"
    assert entry.status == "blocked"
    assert captured["scheduled"] is False
    assert "control_decision: blocked" in result
    assert "status: blocked" in result


@pytest.mark.asyncio
async def test_run_task_blocked_control_decision_does_not_execute_agent_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {"drove": False}

    async def fake_make_agent(target, scope):
        return SimpleNamespace()

    async def fake_drive_task(entry):
        captured["drove"] = True

    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools, "_drive_task", fake_drive_task)

    result = await mcp_tools.run_task(
        {
            "task": "need more input before execution",
            "target": "",
        }
    )

    entry = next(iter(mcp_tools._tasks.values()))
    assert entry.controlDecision["shouldRun"] is False
    assert entry.controlDecision["decisionKind"] == "blocked"
    assert entry.status == "blocked"
    assert captured["drove"] is False
    assert "[control_decision] blocked" in result
    assert "[status] blocked" in result


@pytest.mark.asyncio
async def test_run_task_async_persists_minimal_decision_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_make_agent(target, scope):
        return SimpleNamespace()

    def fake_resolve_mode_contract(payload, *, source_task=None):
        return {"mode": "ctf", "modeSubtype": "web", "goalStyle": "flag"}

    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools.asyncio, "create_task", _close_created_task)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    await mcp_tools.run_task_async(
        {
            "task": "analyze challenge",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
            "artifactPaths": [
                r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            ],
        }
    )

    entry = next(iter(mcp_tools._tasks.values()))
    assert entry.decisionRecords[0]["kind"] == "direct_execute"
    assert entry.decisionRecords[0]["source"] == "mcp_ingress"
    assert entry.decisionRecords[0]["nextAction"] == "bootstrap_local_assets"


@pytest.mark.asyncio
async def test_get_server_status_exposes_model_readiness_reason(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "FLAGHUNTER_MODEL=openai/gpt-5.4",
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
                "FLAGHUNTER_MODEL=openai/gpt-5.4",
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

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None, ingress_handoff=None, run_id=None, ledger_root=None, checkpoint_root=None):
            captured["target"] = target
            captured["goal"] = goal
            captured["type"] = type
            captured["hint"] = hint
            captured["challenge_context"] = challenge_context
            captured["ingress_handoff"] = ingress_handoff
            return SimpleNamespace(flag="flag{mcp_ctf_ok}", reason="ok", chain_used=["xss"], missing_tools=[], notes=[])

    fake_dispatcher_module = types.ModuleType("flaghunter.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
    monkeypatch.setitem(sys.modules, "flaghunter.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    result = await mcp_tools.run_task(
        {
            "task": "solve easy_login from MCP",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "blackboardSnapshot": {
                "facts": [
                    {
                        "kind": "identified_engine",
                        "value": "tornado",
                        "source": "ssti_identify",
                        "confidence": "high",
                    }
                ],
                "pendingVerifications": [],
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
    assert "[control_decision]" in str(captured["hint"])
    assert "decisionKind=direct_execute" in str(captured["hint"])
    assert "nextAction=exploit_identified_engine" in str(captured["hint"])
    assert captured["ingress_handoff"]["decisionKind"] == "direct_execute"
    assert captured["ingress_handoff"]["nextAction"] == "exploit_identified_engine"
    assert captured["challenge_context"] == {
        "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        "artifactPaths": [
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\README.md",
        ],
    }
    assert "flag{mcp_ctf_ok}" in result


@pytest.mark.asyncio
async def test_run_task_routes_structured_probe_endpoint_handoff_into_dispatcher(
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

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None, ingress_handoff=None, run_id=None, ledger_root=None, checkpoint_root=None):
            captured["target"] = target
            captured["goal"] = goal
            captured["type"] = type
            captured["hint"] = hint
            captured["challenge_context"] = challenge_context
            captured["ingress_handoff"] = ingress_handoff
            return SimpleNamespace(flag="flag{mcp_structured_endpoint_ok}", reason="ok", chain_used=["recon"], missing_tools=[], notes=[])

    fake_dispatcher_module = types.ModuleType("flaghunter.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
    monkeypatch.setitem(sys.modules, "flaghunter.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
    monkeypatch.setattr(mcp_tools, "_make_agent", fake_make_agent)
    monkeypatch.setattr(mcp_tools, "resolve_mode_contract", fake_resolve_mode_contract, raising=False)

    result = await mcp_tools.run_task(
        {
            "task": "probe discovered endpoint from MCP",
            "target": "http://challenge.test",
            "mode": "ctf",
            "ctfType": "web",
            "blackboardSnapshot": {
                "facts": [
                    {
                        "kind": "discovered_endpoint",
                        "value": "http://challenge.test/admin",
                        "source": "recon",
                        "confidence": "high",
                    }
                ],
                "pendingVerifications": [],
            },
        }
    )

    assert captured["target"] == "http://challenge.test"
    assert captured["type"] == "web"
    assert "nextAction=probe_discovered_endpoint" in str(captured["hint"])
    assert "endpoint=http://challenge.test/admin" in str(captured["hint"])
    assert captured["ingress_handoff"]["nextAction"] == "probe_discovered_endpoint"
    assert captured["ingress_handoff"]["endpoint"] == "http://challenge.test/admin"
    assert "flag{mcp_structured_endpoint_ok}" in result


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

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None, ingress_handoff=None, run_id=None, ledger_root=None, checkpoint_root=None):
            captured["target"] = target
            captured["goal"] = goal
            captured["type"] = type
            captured["hint"] = hint
            captured["challenge_context"] = challenge_context
            captured["ingress_handoff"] = ingress_handoff
            captured["run_id"] = run_id
            return SimpleNamespace(flag="flag{mcp_async_ctf_ok}", reason="ok", chain_used=["xss"], missing_tools=[], notes=[])

    def fake_create_task(coro):
        captured["scheduled_coro"] = coro
        return SimpleNamespace(done=lambda: False)

    fake_dispatcher_module = types.ModuleType("flaghunter.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
    monkeypatch.setitem(sys.modules, "flaghunter.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
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
    assert "[resume_bootstrap]" in str(captured["hint"])
    assert "nextAction=resume_from_checkpoint" in str(captured["hint"])
    assert "runId=run-prev-1" in str(captured["hint"])
    assert "checkpointId=checkpoint-prev-1" in str(captured["hint"])
    assert captured["ingress_handoff"]["decisionKind"] == "resume_execute"
    assert captured["ingress_handoff"]["nextAction"] == "resume_from_checkpoint"
    assert captured["ingress_handoff"]["resumeBootstrap"]["runId"] == "run-prev-1"
    assert captured["ingress_handoff"]["resumeBootstrap"]["checkpointId"] == "checkpoint-prev-1"
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
            from flaghunter.agents.pa_agent.ctf_state import CTFState

            self.state = CTFState(target="http://challenge.test", goal="solve from MCP truth fields")
            self.state.add_observation(
                "resume_bootstrap_hint",
                "continue from saved recon state",
                source="ingress_handoff",
                metadata={
                    "decision_kind": "explore_first",
                    "next_action": "collect_initial_facts",
                    "run_id": "run-prev-1",
                    "checkpoint_id": "checkpoint-prev-1",
                },
            )
            self.state.add_flag(
                "flag{mcp_truth_ok}",
                level="verified",
                evidence_source="admin_page",
                rationale="verified hit",
            )

        async def run(self, target, goal, type=None, hint=None, submit_profile=None, challenge_context=None, run_id=None, ledger_root=None, checkpoint_root=None):
            return SimpleNamespace(
                flag="flag{mcp_truth_ok}",
                reason="verified",
                chain_used=["xss", "admin_bot"],
                missing_tools=["sqlmap"],
                notes=["reused admin sid", "collector hit /admin"],
            )

    fake_dispatcher_module = types.ModuleType("flaghunter.agents.pa_agent.ctf_dispatcher")
    fake_dispatcher_module.CTFTaskDispatcher = _FakeDispatcher
    monkeypatch.setitem(sys.modules, "flaghunter.agents.pa_agent.ctf_dispatcher", fake_dispatcher_module)
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
    assert isinstance(getattr(entry, "ctfStateSnapshot", None), dict)
    assert entry.ctfStateSnapshot["observations"][0]["kind"] == "resume_bootstrap_hint"
    assert entry.ctfStateSnapshot["verified_flags"][0]["value"] == "flag{mcp_truth_ok}"


@pytest.mark.asyncio
async def test_mcp_task_inspection_surfaces_control_decision_contract() -> None:
    entry = mcp_tools.TaskEntry(
        id="decision123",
        task="inspect decision",
        status="done",
        created_at="2026-05-29T00:00:00",
        finished_at="2026-05-29T00:01:00",
        agent=SimpleNamespace(runtime=None, tools=[]),
        target="http://challenge.test",
        scope=[],
        result="flag{decision_truth}",
        mode="ctf",
        modeSubtype="web",
        goalStyle="flag",
        challengePath=r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
        artifactPaths=[r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"],
        controlDecision={
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "ctf local assets available",
            "nextAction": "bootstrap_local_assets",
            "facts": ["mode=ctf", "challengePath=D:/sample"],
        },
        decisionRecords=[
            {
                "kind": "direct_execute",
                "source": "mcp_ingress",
                "nextAction": "bootstrap_local_assets",
            }
        ],
    )
    mcp_tools._tasks[entry.id] = entry

    list_output = await mcp_tools.list_tasks({"limit": 20})
    status_output = await mcp_tools.get_task_status({"task_id": entry.id})
    result_output = await mcp_tools.get_task_result({"task_id": entry.id})

    assert "decision=direct_execute" in list_output
    assert "control_decision: direct_execute" in status_output
    assert "control_decision: direct_execute" in result_output
    assert "decision_record_kind: direct_execute" in status_output
    assert "decision_record_source: mcp_ingress" in status_output
    assert "decision_record_next_action: bootstrap_local_assets" in status_output
    assert "decision_record_kind: direct_execute" in result_output
    assert "decision_record_source: mcp_ingress" in result_output
    assert "decision_record_next_action: bootstrap_local_assets" in result_output


@pytest.mark.asyncio
async def test_mcp_task_inspection_exposes_blackboard_snapshot() -> None:
    entry = mcp_tools.TaskEntry(
        id="bb12345",
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
        controlDecision={
            "shouldRun": True,
            "decisionKind": "resume_execute",
            "reason": "resume context available",
            "nextAction": "resume_from_checkpoint",
            "facts": ["mode=ctf"],
        },
        decisionRecords=[
            {
                "kind": "resume_execute",
                "source": "mcp_ingress",
                "nextAction": "resume_from_checkpoint",
                "reason": "resume context available",
            }
        ],
        ingressHandoff={
            "decisionKind": "resume_execute",
            "nextAction": "resume_from_checkpoint",
            "challengeContext": {
                "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
                "artifactPaths": [
                    r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
                ],
                "derivedTarget": "http://127.0.0.1:3000",
                "derivedTargetSource": "docker_compose_port_mapping",
                "derivedTargetComposePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml",
            },
            "resumeBootstrap": {
                "runId": "run-prev-1",
                "checkpointId": "checkpoint-prev-1",
                "summary": "continue from saved recon state",
            },
        },
    )
    entry.ctfStateSnapshot = {
        "target": "http://challenge.test",
        "goal": "拿到flag",
        "observations": [
            {
                "kind": "resume_bootstrap_hint",
                "value": "continue from saved recon state",
                "source": "ingress_handoff",
                "metadata": {
                    "decision_kind": "resume_execute",
                    "next_action": "resume_from_checkpoint",
                    "run_id": "run-prev-1",
                    "checkpoint_id": "checkpoint-prev-1",
                },
            }
        ],
        "artifacts": [],
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
    mcp_tools._tasks[entry.id] = entry

    status_output = await mcp_tools.get_task_status({"task_id": entry.id})
    result_output = await mcp_tools.get_task_result({"task_id": entry.id})

    assert "[blackboard_facts]" in status_output
    assert "control_decision=resume_execute" in status_output
    assert r"challenge_path=D:\webstudy\CTF\2026\CTF比赛题\easy_login" in status_output
    assert "resume_bootstrap_hint=continue from saved recon state" in status_output
    assert "verified_flag=flag{verified_done}" in status_output
    assert "[blackboard_pending_verifications]" in status_output
    assert "runtime_flag=flag{runtime_pending}" in status_output
    assert "derived_target: http://127.0.0.1:3000" in status_output
    assert "derived_target_source: docker_compose_port_mapping" in status_output
    assert "derived_target_origin: inherited_lineage" in status_output
    assert "next_action_decision_kind: resume_execute" in status_output
    assert "next_action: resume_from_checkpoint" in status_output
    assert "next_action_driver: task.resume_context" in status_output
    assert "next_action_reason: resume context available" in status_output
    assert (
        "next_action_summary: resume_execute -> resume_from_checkpoint via task.resume_context"
        in status_output
    )
    assert (
        r"derived_target_compose_path: D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
        in status_output
    )

    assert "[blackboard_facts]" in result_output
    assert "control_decision=resume_execute" in result_output
    assert "[blackboard_pending_verifications]" in result_output
    assert "runtime_flag=flag{runtime_pending}" in result_output
    assert "derived_target: http://127.0.0.1:3000" in result_output
    assert "derived_target_source: docker_compose_port_mapping" in result_output
    assert "derived_target_origin: inherited_lineage" in result_output
    assert "next_action_decision_kind: resume_execute" in result_output
    assert "next_action: resume_from_checkpoint" in result_output
    assert "next_action_driver: task.resume_context" in result_output
    assert "next_action_reason: resume context available" in result_output
    assert (
        "next_action_summary: resume_execute -> resume_from_checkpoint via task.resume_context"
        in result_output
    )
    assert (
        r"derived_target_compose_path: D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
        in result_output
    )


@pytest.mark.asyncio
async def test_mcp_task_inspection_surfaces_runtime_derived_origin() -> None:
    entry = mcp_tools.TaskEntry(
        id="runtime-derived-1",
        task="inspect runtime derived target",
        status="done",
        created_at="2026-06-02T00:00:00",
        finished_at="2026-06-02T00:01:00",
        agent=SimpleNamespace(runtime=None, tools=[]),
        target=None,
        scope=[],
        result="flag{runtime_derived}",
        mode="ctf",
        modeSubtype="web",
        goalStyle="flag",
        ingressHandoff={
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
        },
    )
    mcp_tools._tasks[entry.id] = entry

    status_output = await mcp_tools.get_task_status({"task_id": entry.id})
    result_output = await mcp_tools.get_task_result({"task_id": entry.id})

    assert "derived_target_origin: runtime_derived" in status_output
    assert "derived_target_origin: runtime_derived" in result_output


def test_mcp_entry_blackboard_snapshot_for_decision_normalizes_extended_shape() -> None:
    entry = mcp_tools.TaskEntry(
        id="bb-normalize-1",
        task="normalize explicit blackboard",
        status="pending",
        created_at="2026-06-03T00:00:00",
        agent=SimpleNamespace(runtime=None, tools=[]),
    )

    snapshot = mcp_tools._entry_blackboard_snapshot_for_decision(
        entry,
        {
            "facts": [{"kind": "derived_target", "value": "http://127.0.0.1:3000"}],
            "pending_verifications": [{"kind": "runtime_flag", "value": "flag{runtime_pending}"}],
            "candidates": [{"action": "collect_initial_facts"}],
            "active_decision": {"nextAction": "collect_initial_facts"},
            "action_results": [{"action": "bootstrap_local_assets", "result": "failed"}],
            "recommended_action": {"action": "collect_initial_facts"},
        },
    )

    assert snapshot["facts"] == [{"kind": "derived_target", "value": "http://127.0.0.1:3000"}]
    assert snapshot["pendingVerifications"] == [{"kind": "runtime_flag", "value": "flag{runtime_pending}"}]
    assert snapshot["candidates"] == [{"action": "collect_initial_facts"}]
    assert snapshot["activeDecision"] == {"nextAction": "collect_initial_facts"}
    assert snapshot["actionResults"] == [{"action": "bootstrap_local_assets", "result": "failed"}]
    assert snapshot["recommendedAction"] == {"action": "collect_initial_facts"}


@pytest.mark.asyncio
async def test_mcp_task_inspection_surfaces_decision_record_driver() -> None:
    entry = mcp_tools.TaskEntry(
        id="decision-driver-1",
        task="inspect driver",
        status="done",
        created_at="2026-05-29T00:00:00",
        finished_at="2026-05-29T00:01:00",
        agent=SimpleNamespace(runtime=None, tools=[]),
        target="http://challenge.test",
        scope=[],
        result="flag{driver_truth}",
        controlDecision={
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "verified flag already present in blackboard",
            "nextAction": "verify_or_submit_flag",
            "driver": "blackboard.verified_flag",
            "facts": ["mode=ctf", "blackboard.verified_flag=present"],
        },
        decisionRecords=[
            {
                "kind": "direct_execute",
                "source": "mcp_ingress",
                "nextAction": "verify_or_submit_flag",
                "driver": "blackboard.verified_flag",
            }
        ],
    )
    mcp_tools._tasks[entry.id] = entry

    status_output = await mcp_tools.get_task_status({"task_id": entry.id})
    result_output = await mcp_tools.get_task_result({"task_id": entry.id})

    assert "decision_record_driver: blackboard.verified_flag" in status_output
    assert "decision_record_driver: blackboard.verified_flag" in result_output


@pytest.mark.asyncio
async def test_mcp_task_inspection_exposes_active_decision_alignment_and_suppression() -> None:
    ledger = SessionLedger("loot/session_ledgers")
    started = build_control_action_started_event(
        action="probe_discovered_endpoint",
        decision_kind="direct_execute",
        driver="blackboard.discovered_endpoint",
        expected_action="collect_initial_facts",
        alignment="mismatch",
        alignment_reason="coordinator escalated to higher-value discovered endpoint",
    )
    ledger.append_event(
        "mcp-ctf-active-decision-1",
        str(started.get("event_type") or "control_action_started"),
        dict(started.get("payload") or {}),
    )

    entry = mcp_tools.TaskEntry(
        id="active-decision-1",
        task="inspect active decision",
        status="done",
        created_at="2026-06-03T00:00:00",
        finished_at="2026-06-03T00:01:00",
        agent=SimpleNamespace(runtime=None, tools=[]),
        target="http://challenge.test",
        scope=[],
        result="flag{active_decision_truth}",
        mode="ctf",
        modeSubtype="web",
        goalStyle="flag",
        controlDecision={
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "derived target available for initial fact collection",
            "nextAction": "collect_initial_facts",
            "driver": "blackboard.derived_target",
            "suppressedRecommendation": {
                "action": "resume_from_checkpoint",
                "driver": "blackboard.resume_context",
                "reason": "resume context or resume hint available",
                "suppressedBy": "blackboard.derived_target",
            },
        },
        ingressHandoff={
            "decisionKind": "direct_execute",
            "nextAction": "collect_initial_facts",
            "challengeContext": {
                "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
                "artifactPaths": [
                    r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
                ],
                "derivedTarget": "http://127.0.0.1:3000",
            },
        },
        runId="mcp-ctf-active-decision-1",
        ledgerPath="loot/session_ledgers/mcp-ctf-active-decision-1.jsonl",
    )
    mcp_tools._tasks[entry.id] = entry

    status_output = await mcp_tools.get_task_status({"task_id": entry.id})
    result_output = await mcp_tools.get_task_result({"task_id": entry.id})

    assert "[blackboard_active_decision]" in status_output
    assert "expectedAction=collect_initial_facts" in status_output
    assert "observedAction=probe_discovered_endpoint" in status_output
    assert "alignment=mismatch" in status_output
    assert "alignmentReason=coordinator escalated to higher-value discovered endpoint" in status_output
    assert "suppressedRecommendation.action=resume_from_checkpoint" in status_output
    assert "suppressedRecommendation.driver=blackboard.resume_context" in status_output
    assert "suppressedRecommendation.reason=resume context or resume hint available" in status_output
    assert "suppressedRecommendation.suppressedBy=blackboard.derived_target" in status_output

    assert "[blackboard_active_decision]" in result_output
    assert "observedAction=probe_discovered_endpoint" in result_output
    assert "suppressedRecommendation.suppressedBy=blackboard.derived_target" in result_output


@pytest.mark.asyncio
async def test_mcp_task_inspection_exposes_recommended_action_and_action_results() -> None:
    ledger = SessionLedger("loot/session_ledgers")
    started = build_control_action_started_event(
        action="bootstrap_local_assets",
        decision_kind="direct_execute",
        driver="task.local_assets",
        expected_action="bootstrap_local_assets",
        alignment="aligned",
        alignment_reason="coordinator followed ingress action",
    )
    completed = build_control_action_completed_event(
        action="bootstrap_local_assets",
        result="failed",
        decision_kind="direct_execute",
        driver="task.local_assets",
        details={"reason": "compose parsing failed"},
    )
    ledger.append_event(
        "mcp-ctf-recommended-1",
        str(started.get("event_type") or "control_action_started"),
        dict(started.get("payload") or {}),
    )
    ledger.append_event(
        "mcp-ctf-recommended-1",
        str(completed.get("event_type") or "control_action_completed"),
        dict(completed.get("payload") or {}),
    )

    entry = mcp_tools.TaskEntry(
        id="recommended-1",
        task="inspect recommended action",
        status="done",
        created_at="2026-06-03T00:00:00",
        finished_at="2026-06-03T00:01:00",
        agent=SimpleNamespace(runtime=None, tools=[]),
        target="http://challenge.test",
        scope=[],
        result="bootstrap failed, switched candidate",
        mode="ctf",
        modeSubtype="web",
        goalStyle="flag",
        controlDecision={
            "shouldRun": True,
            "decisionKind": "direct_execute",
            "reason": "local challenge assets available",
            "nextAction": "bootstrap_local_assets",
            "driver": "task.local_assets",
        },
        ingressHandoff={
            "decisionKind": "direct_execute",
            "nextAction": "bootstrap_local_assets",
            "challengeContext": {
                "challengePath": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login",
                "artifactPaths": [
                    r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"
                ],
                "derivedTarget": "http://127.0.0.1:3000",
            },
        },
        ctfStateSnapshot={
            "target": "http://challenge.test",
            "goal": "拿到flag",
            "observations": [
                {
                    "kind": "derived_target",
                    "value": "http://127.0.0.1:3000",
                    "source": "challenge_context",
                    "metadata": {"compose_path": r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\docker-compose.yml"},
                }
            ],
            "artifacts": [],
            "runtime_flags": [],
            "verified_flags": [],
        },
        runId="mcp-ctf-recommended-1",
        ledgerPath="loot/session_ledgers/mcp-ctf-recommended-1.jsonl",
    )
    mcp_tools._tasks[entry.id] = entry

    status_output = await mcp_tools.get_task_status({"task_id": entry.id})
    result_output = await mcp_tools.get_task_result({"task_id": entry.id})

    assert "[blackboard_recommended_action]" in status_output
    assert "action=collect_initial_facts" in status_output
    assert "driver=blackboard.derived_target" in status_output
    assert "reason=selected action failed; switch to next best candidate" in status_output
    assert "switchedFrom=bootstrap_local_assets" in status_output
    assert "triggerResult=failed" in status_output
    assert "triggerReason=compose parsing failed" in status_output
    assert "next_action_decision_kind: direct_execute" in status_output
    assert "next_action: bootstrap_local_assets" in status_output
    assert "next_action_driver: task.local_assets" in status_output
    assert "next_action_reason: local challenge assets available" in status_output
    assert "next_action_summary: direct_execute -> bootstrap_local_assets via task.local_assets" in status_output
    assert "[blackboard_action_results]" in status_output
    assert "action=bootstrap_local_assets" in status_output
    assert "result=failed" in status_output
    assert "alignment=aligned" in status_output
    assert "alignmentReason=coordinator followed ingress action" in status_output

    assert "[blackboard_recommended_action]" in result_output
    assert "action=collect_initial_facts" in result_output
    assert "switchedFrom=bootstrap_local_assets" in result_output
    assert "next_action_decision_kind: direct_execute" in result_output
    assert "next_action: bootstrap_local_assets" in result_output
    assert "next_action_driver: task.local_assets" in result_output
    assert "next_action_reason: local challenge assets available" in result_output
    assert "next_action_summary: direct_execute -> bootstrap_local_assets via task.local_assets" in result_output
    assert "[blackboard_action_results]" in result_output
    assert "result=failed" in result_output


@pytest.mark.asyncio
async def test_mcp_task_inspection_exposes_latest_checkpoint_summary() -> None:
    state = CTFState(target="http://challenge.test", goal="拿到flag")
    state.stop_reason = "wrong_flag_feedback"
    state.add_flag(
        "flag{checkpoint_verified}",
        level="verified",
        evidence_source="platform-accept",
        rationale="accepted before checkpoint",
    )
    checkpoint = CheckpointStore("loot/checkpoints").save_checkpoint(
        run_id="mcp-ctf-checkpoint-1",
        label="control_action_completed",
        state_snapshot=state.to_snapshot(),
        metadata={"decision_kind": "direct_execute"},
    )

    entry = mcp_tools.TaskEntry(
        id="checkpoint-1",
        task="inspect checkpoint summary",
        status="done",
        created_at="2026-06-03T00:00:00",
        finished_at="2026-06-03T00:01:00",
        agent=SimpleNamespace(runtime=None, tools=[]),
        target="http://challenge.test",
        scope=[],
        result="flag{checkpoint_verified}",
        mode="ctf",
        modeSubtype="web",
        goalStyle="flag",
        runId="mcp-ctf-checkpoint-1",
        ledgerPath="loot/session_ledgers/mcp-ctf-checkpoint-1.jsonl",
        checkpointPath="loot/checkpoints/mcp-ctf-checkpoint-1.jsonl",
    )
    mcp_tools._tasks[entry.id] = entry

    status_output = await mcp_tools.get_task_status({"task_id": entry.id})
    result_output = await mcp_tools.get_task_result({"task_id": entry.id})

    assert "[latest_checkpoint]" in status_output
    assert f"checkpointId={checkpoint['checkpoint_id']}" in status_output
    assert "label=control_action_completed" in status_output
    assert "stopReason=wrong_flag_feedback" in status_output
    assert "verifiedFlags=flag{checkpoint_verified}" in status_output

    assert "[latest_checkpoint]" in result_output
    assert f"checkpointId={checkpoint['checkpoint_id']}" in result_output
    assert "stopReason=wrong_flag_feedback" in result_output


@pytest.mark.asyncio
async def test_mcp_task_inspection_exposes_registered_artifacts_summary() -> None:
    artifact = ArtifactRegistry("loot/artifacts").register_artifact(
        run_id="mcp-ctf-artifacts-1",
        kind="log_capture",
        title="nginx error log",
        location=r"D:\webstudy\CTF\2026\CTF比赛题\easy_login\logs\error.log",
        producer="exploit_identified_engine",
        metadata={"action": "collect_runtime_evidence"},
    )

    entry = mcp_tools.TaskEntry(
        id="artifacts-1",
        task="inspect artifacts summary",
        status="done",
        created_at="2026-06-03T00:00:00",
        finished_at="2026-06-03T00:01:00",
        agent=SimpleNamespace(runtime=None, tools=[]),
        target="http://challenge.test",
        scope=[],
        result="artifact captured",
        mode="ctf",
        modeSubtype="web",
        goalStyle="flag",
        runId="mcp-ctf-artifacts-1",
        ledgerPath="loot/session_ledgers/mcp-ctf-artifacts-1.jsonl",
        checkpointPath="loot/checkpoints/mcp-ctf-artifacts-1.jsonl",
    )
    mcp_tools._tasks[entry.id] = entry

    status_output = await mcp_tools.get_task_status({"task_id": entry.id})
    result_output = await mcp_tools.get_task_result({"task_id": entry.id})

    assert "[registered_artifacts]" in status_output
    assert f"artifactId={artifact['artifact_id']}" in status_output
    assert "kind=log_capture" in status_output
    assert "title=nginx error log" in status_output
    assert (
        r"location=D:\webstudy\CTF\2026\CTF比赛题\easy_login\logs\error.log"
        in status_output
    )

    assert "[registered_artifacts]" in result_output
    assert f"artifactId={artifact['artifact_id']}" in result_output
    assert "title=nginx error log" in result_output


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
