from __future__ import annotations

import json

from flaghunter.agents.pa_agent.session_context import SessionContextView
from flaghunter.harness.audit_events import (
    build_budget_event,
    build_handoff_consumed_event,
    build_handoff_created_event,
    build_model_call_event,
    build_state_transition_event,
)
from flaghunter.harness.session_ledger import SessionLedger


def _append_built_event(ledger: SessionLedger, run_id: str, event: dict) -> None:
    ledger.append_event(
        run_id,
        str(event.get("event_type") or ""),
        dict(event.get("payload") or {}),
    )


def test_p2_ledger_events_surface_compact_resume_readback(tmp_path) -> None:
    run_id = "run-p2-ledger-readback"
    ledger = SessionLedger(tmp_path / "session_ledgers")
    _append_built_event(
        ledger,
        run_id,
        build_model_call_event(
            model="claude-sonnet-4",
            provider="anthropic",
            status="success",
            duration_ms=42,
            prompt="prompt token=prompt-token password=prompt-password",
            completion="completion secret=completion-secret",
            prompt_tokens=10,
            completion_tokens=20,
            metadata={"source_channel": "ctf_dispatcher"},
        ),
    )
    _append_built_event(
        ledger,
        run_id,
        build_state_transition_event(
            from_state="THINKING",
            to_state="EXECUTING",
            reason="state reason cookie=state-cookie",
            source="agent_loop",
            metadata={"phase": "exploit"},
        ),
    )
    _append_built_event(
        ledger,
        run_id,
        build_budget_event(
            budget_name="phase_round",
            event="threshold_reached",
            used=12,
            limit=12,
            remaining=0,
            unit="round",
            source="recovery",
            metadata={"phase": "exploit"},
        ),
    )
    _append_built_event(
        ledger,
        run_id,
        build_handoff_created_event(
            handoff_id="handoff-1",
            source="web",
            target="dispatcher",
            decision_kind="direct_execute",
            next_action="verify_runtime_signal",
            reason="handoff token=handoff-token",
            metadata={"run_id": run_id},
        ),
    )
    _append_built_event(
        ledger,
        run_id,
        build_handoff_consumed_event(
            handoff_id="handoff-1",
            consumer="dispatcher",
            status="accepted",
            reason="Authorization: Bearer consumed-token",
            metadata={"checkpoint_id": "checkpoint-1"},
        ),
    )

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    refs = context["resumeContext"]["ledgerEventRefs"]
    summary = context["resumeContext"]["ledgerEventSummary"]
    refs_by_type = {item["type"]: item for item in refs}

    assert [item["type"] for item in refs] == [
        "model_call",
        "state_transition",
        "budget_event",
        "handoff_created",
        "handoff_consumed",
    ]
    assert refs_by_type["model_call"]["model"] == "claude-sonnet-4"
    assert refs_by_type["model_call"]["provider"] == "anthropic"
    assert refs_by_type["model_call"]["status"] == "success"
    assert refs_by_type["model_call"]["totalTokens"] == 30
    assert refs_by_type["state_transition"]["fromState"] == "THINKING"
    assert refs_by_type["state_transition"]["toState"] == "EXECUTING"
    assert refs_by_type["budget_event"]["budgetName"] == "phase_round"
    assert refs_by_type["handoff_created"]["handoffId"] == "handoff-1"
    assert refs_by_type["handoff_consumed"]["handoffId"] == "handoff-1"
    assert summary == {
        "countsByType": {
            "model_call": 1,
            "state_transition": 1,
            "budget_event": 1,
            "handoff_created": 1,
            "handoff_consumed": 1,
        },
        "hasModelCall": True,
        "hasStateTransition": True,
        "hasBudgetEvent": True,
        "hasHandoff": True,
    }
    resume_text = repr(context["resumeContext"])
    for leaked in (
        "prompt-token",
        "prompt-password",
        "completion-secret",
        "state-cookie",
        "handoff-token",
        "consumed-token",
        "Authorization",
    ):
        assert leaked not in resume_text


def test_p2_ledger_readback_ignores_ordinary_events_without_shape_break(tmp_path) -> None:
    run_id = "run-p2-ledger-legacy"
    ledger = SessionLedger(tmp_path / "session_ledgers")
    ledger.append_event(run_id, "task_finished", {"success": True, "token": "raw-token"})

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    assert "ledgerEventRefs" not in context["resumeContext"]
    assert "ledgerEventSummary" not in context["resumeContext"]
    assert context["resumeContext"]["recentEventTypes"] == ["task_finished"]


def test_p2_ledger_readback_redacts_raw_external_p2_payloads(tmp_path) -> None:
    run_id = "run-p2-ledger-raw-redaction"
    ledger = SessionLedger(tmp_path / "session_ledgers")
    ledger.append_event(
        run_id,
        "handoff_created",
        {
            "handoff_id": "handoff token=raw-handoff-token",
            "source": "web password=raw-source-password",
            "target": "http://x/?token=raw-target-token",
            "decision_kind": "direct secret=raw-decision-secret",
            "next_action": "use password=raw-action-password",
        },
    )
    ledger.append_event(
        run_id,
        "budget_event",
        {
            "budget_name": "phase token=raw-budget-token",
            "event": "used password=raw-budget-password",
            "source": "recovery secret=raw-source-secret",
        },
    )
    ledger.append_event(
        run_id,
        "state_transition",
        {
            "from_state": "THINKING token=raw-from-token",
            "to_state": "EXECUTING password=raw-to-password",
            "source": "agent password=raw-agent-password",
        },
    )

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    resume_text = repr(context["resumeContext"])
    assert context["resumeContext"]["ledgerEventSummary"]["hasHandoff"] is True
    for leaked in (
        "raw-handoff-token",
        "raw-source-password",
        "raw-target-token",
        "raw-decision-secret",
        "raw-action-password",
        "raw-budget-token",
        "raw-budget-password",
        "raw-source-secret",
        "raw-from-token",
        "raw-to-password",
        "raw-agent-password",
    ):
        assert leaked not in resume_text


def test_p2_ledger_readback_redacts_jsonish_sensitive_raw_payloads(tmp_path) -> None:
    run_id = "run-p2-ledger-jsonish-redaction"
    ledger = SessionLedger(tmp_path / "session_ledgers")
    ledger.append_event(
        run_id,
        "handoff_created",
        {
            "handoff_id": "handoff-json",
            "target": json.dumps({"token": "json-target-token"}),
            "next_action": json.dumps({"password": "json-action-password"}),
        },
    )
    ledger.append_event(
        run_id,
        "handoff_consumed",
        {
            "handoff_id": "handoff-json",
            "consumer": json.dumps({"cookie": "json-consumer-cookie"}),
            "status": json.dumps({"authorization": "Bearer json-status-auth"}),
        },
    )
    ledger.append_event(
        run_id,
        "budget_event",
        {
            "budget_name": json.dumps({"secret": "json-budget-secret"}),
            "event": json.dumps({"token": "json-budget-token"}),
            "source": json.dumps({"session": "json-source-session"}),
        },
    )

    context = SessionContextView(
        ledger_root=tmp_path / "session_ledgers",
        artifact_root=tmp_path / "artifact_registry",
        checkpoint_root=tmp_path / "checkpoints",
    ).build_run_context(run_id)

    resume_text = repr(context["resumeContext"])
    assert context["resumeContext"]["ledgerEventSummary"]["hasHandoff"] is True
    for leaked in (
        "json-target-token",
        "json-action-password",
        "json-consumer-cookie",
        "json-status-auth",
        "json-budget-secret",
        "json-budget-token",
        "json-source-session",
    ):
        assert leaked not in resume_text
