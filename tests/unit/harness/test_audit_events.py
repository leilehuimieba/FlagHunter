from __future__ import annotations

import json
from types import SimpleNamespace

from flaghunter.harness.audit_events import (
    build_artifact_registered_event,
    build_budget_event,
    build_control_action_completed_event,
    build_control_action_started_event,
    build_checkpoint_written_event,
    build_dispatcher_started_event,
    build_handoff_consumed_event,
    build_handoff_created_event,
    build_model_call_event,
    build_missing_tools_recorded_event,
    build_recovery_decision_event,
    build_state_transition_event,
    build_task_finished_event,
    build_tool_called_event,
    build_tool_finished_event,
    build_verification_decision_event,
)


def test_build_dispatcher_started_event_keeps_resume_contract() -> None:
    event = build_dispatcher_started_event(
        target="http://ctf.local",
        goal="capture the flag",
        requested_type="web",
        local_challenge_auto_verify=True,
        has_challenge_context=True,
        has_resume_context=True,
        resume_run_id="run-prev-1",
        resume_checkpoint_id="checkpoint-prev-1",
    )

    assert event["event_type"] == "dispatcher_started"
    assert event["payload"]["target"] == "http://ctf.local"
    assert event["payload"]["requested_type"] == "web"
    assert event["payload"]["has_resume_context"] is True
    assert event["payload"]["resume_run_id"] == "run-prev-1"
    assert event["payload"]["resume_checkpoint_id"] == "checkpoint-prev-1"


def test_build_control_action_events_keep_driver_and_result_contract() -> None:
    started = build_control_action_started_event(
        action="bootstrap_local_assets",
        decision_kind="direct_execute",
        driver="task.local_assets",
        target="http://ctf.local",
        expected_action="bootstrap_local_assets",
        alignment="matched",
        switched_from="probe_discovered_endpoint",
        trigger_reason="endpoint probe returned empty findings",
    )
    completed = build_control_action_completed_event(
        action="bootstrap_local_assets",
        decision_kind="direct_execute",
        driver="task.local_assets",
        result="ok",
        target="http://ctf.local",
        details={"ingested": 2},
        switched_from="probe_discovered_endpoint",
        trigger_reason="endpoint probe returned empty findings",
    )

    assert started == {
        "event_type": "control_action_started",
        "payload": {
            "action": "bootstrap_local_assets",
            "decision_kind": "direct_execute",
            "driver": "task.local_assets",
            "target": "http://ctf.local",
            "expected_action": "bootstrap_local_assets",
            "alignment": "matched",
            "switched_from": "probe_discovered_endpoint",
            "trigger_reason": "endpoint probe returned empty findings",
        },
    }
    assert completed == {
        "event_type": "control_action_completed",
        "payload": {
            "action": "bootstrap_local_assets",
            "decision_kind": "direct_execute",
            "driver": "task.local_assets",
            "result": "ok",
            "target": "http://ctf.local",
            "details": {"ingested": 2},
            "switched_from": "probe_discovered_endpoint",
            "trigger_reason": "endpoint probe returned empty findings",
        },
    }


def test_build_control_action_started_event_keeps_alignment_reason_for_mismatch() -> None:
    started = build_control_action_started_event(
        action="verify_runtime_signal",
        decision_kind="direct_execute",
        driver="blackboard.runtime_flag",
        target="http://ctf.local",
        expected_action="collect_initial_facts",
        alignment="mismatched",
        alignment_reason="runtime verification preempted planned first action",
    )

    assert started["payload"]["expected_action"] == "collect_initial_facts"
    assert started["payload"]["alignment"] == "mismatched"
    assert (
        started["payload"]["alignment_reason"]
        == "runtime verification preempted planned first action"
    )


def test_build_control_action_events_keep_strongest_hypothesis_contract() -> None:
    started = build_control_action_started_event(
        action="collect_initial_facts",
        decision_kind="explore_first",
        driver="blackboard.derived_target.runtime_derived",
        expected_action="collect_initial_facts",
        strongest_hypothesis_kind="generic_web_recon",
        strongest_hypothesis_status="active",
        strongest_hypothesis_confidence=0.52,
    )
    completed = build_control_action_completed_event(
        action="collect_initial_facts",
        result="ok",
        decision_kind="explore_first",
        driver="blackboard.derived_target.runtime_derived",
        strongest_hypothesis_kind="generic_web_recon",
        strongest_hypothesis_status="active",
        strongest_hypothesis_confidence=0.52,
    )

    assert started["payload"]["strongest_hypothesis_kind"] == "generic_web_recon"
    assert started["payload"]["strongest_hypothesis_status"] == "active"
    assert started["payload"]["strongest_hypothesis_confidence"] == 0.52
    assert completed["payload"]["strongest_hypothesis_kind"] == "generic_web_recon"
    assert completed["payload"]["strongest_hypothesis_status"] == "active"
    assert completed["payload"]["strongest_hypothesis_confidence"] == 0.52


def test_build_verification_decision_event_exposes_strategy_and_hypothesis() -> None:
    event = build_verification_decision_event(
        decision="verified",
        flag="flag{ok}",
        evidence_source="browser-rendered-page",
        rationale="homepage contains flag",
        confidence=0.97,
        hypothesis_id="hyp-7",
        strategy_kind="recon",
    )

    assert event == {
        "event_type": "verification_decision",
        "payload": {
            "decision": "verified",
            "flag": "flag{ok}",
            "evidence_source": "browser-rendered-page",
            "rationale": "homepage contains flag",
            "confidence": 0.97,
            "hypothesis_id": "hyp-7",
            "strategy_kind": "recon",
        },
    }


def test_build_artifact_registered_event_preserves_metadata() -> None:
    event = build_artifact_registered_event(
        {
            "artifact_id": "artifact-1",
            "kind": "flag",
            "title": "ctf_flag",
            "location": "note://ctf_flag",
            "path": None,
            "producer": "verifier",
            "metadata": {"source": "verified_flag"},
        }
    )

    assert event == {
        "event_type": "artifact_registered",
        "payload": {
            "artifact_id": "artifact-1",
            "kind": "flag",
            "title": "ctf_flag",
            "location": "note://ctf_flag",
            "path": None,
            "producer": "verifier",
            "metadata": {"source": "verified_flag"},
        },
    }


def test_build_recovery_decision_event_normalizes_decision_shape() -> None:
    decision = SimpleNamespace(
        action="switch_chain",
        reason="login dead end",
        should_stop=False,
        next_chain_order=["sqli", "lfi"],
    )

    event = build_recovery_decision_event(decision, chain_name="login")

    assert event == {
        "event_type": "recovery_decision",
        "payload": {
            "action": "switch_chain",
            "reason": "login dead end",
            "should_stop": False,
            "chain_name": "login",
            "next_chain_order": ["sqli", "lfi"],
        },
    }


def test_build_task_finished_event_and_missing_tools_event_keep_truthful_fields() -> None:
    finished = build_task_finished_event(
        success=False,
        flag="",
        reason="missing tools",
        chain_used=["recon"],
        missing_tools=["sqlmap"],
    )
    missing = build_missing_tools_recorded_event(
        missing_tools=["sqlmap"],
        install_commands={"sqlmap": "pip install sqlmap"},
    )

    assert finished == {
        "event_type": "task_finished",
        "payload": {
            "success": False,
            "flag": "",
            "reason": "missing tools",
            "chain_used": ["recon"],
            "missing_tools": ["sqlmap"],
        },
    }
    assert missing == {
        "event_type": "missing_tools_recorded",
        "payload": {
            "missing_tools": ["sqlmap"],
            "install_commands": {"sqlmap": "pip install sqlmap"},
        },
    }


def test_build_checkpoint_written_event_keeps_label_and_metadata() -> None:
    event = build_checkpoint_written_event(
        {
            "checkpoint_id": "checkpoint-1",
            "label": "task_finished",
            "metadata": {"success": True, "flag": "flag{ok}"},
        }
    )

    assert event == {
        "event_type": "checkpoint_written",
        "payload": {
            "checkpoint_id": "checkpoint-1",
            "label": "task_finished",
            "metadata": {"success": True, "flag": "flag{ok}"},
        },
    }


def test_build_tool_called_and_finished_events_keep_runtime_contract() -> None:
    called = build_tool_called_event(
        tool_name="proxy_action",
        action="request",
        target="http://ctf.local/login",
        metadata={"method": "POST", "phase": "llm_action"},
    )
    finished = build_tool_finished_event(
        tool_name="proxy_action",
        action="request",
        ok=True,
        status_code=200,
        target="http://ctf.local/login",
        metadata={"phase": "llm_action"},
    )

    assert called == {
        "event_type": "tool_called",
        "payload": {
            "tool_name": "proxy_action",
            "action": "request",
            "target": "http://ctf.local/login",
            "metadata": {"method": "POST", "phase": "llm_action"},
        },
    }
    assert finished == {
        "event_type": "tool_finished",
        "payload": {
            "tool_name": "proxy_action",
            "action": "request",
            "ok": True,
            "status_code": 200,
            "target": "http://ctf.local/login",
            "metadata": {"phase": "llm_action"},
        },
    }


def test_p2_build_model_call_event_keeps_compact_safe_contract() -> None:
    event = build_model_call_event(
        model="claude-sonnet-4",
        provider="anthropic",
        status="success",
        duration_ms=1234.5,
        prompt=(
            "Authorization: Bearer prompt-token\n"
            "Cookie: session=prompt-cookie\n"
            "Solve with password=prompt-password " + "A" * 400
        ),
        completion="secret=completion-secret token=completion-token " + "B" * 400,
        prompt_tokens=111,
        completion_tokens=222,
        metadata={
            "source_channel": "ctf_dispatcher",
            "api_key": "metadata-api-key",
            "headers": {"Authorization": "Bearer metadata-token"},
            "large": "C" * 500,
        },
    )

    payload = event["payload"]
    event_text = repr(event)

    assert event["event_type"] == "model_call"
    assert payload["model"] == "claude-sonnet-4"
    assert payload["provider"] == "anthropic"
    assert payload["status"] == "success"
    assert payload["duration_ms"] == 1234.5
    assert payload["prompt_tokens"] == 111
    assert payload["completion_tokens"] == 222
    assert payload["total_tokens"] == 333
    assert "prompt" not in payload
    assert "completion" not in payload
    assert len(payload["prompt_preview"]) <= 160
    assert len(payload["completion_preview"]) <= 160
    assert len(payload["prompt_sha256"]) == 64
    assert len(payload["completion_sha256"]) == 64
    assert payload["metadata"] == {"source_channel": "ctf_dispatcher"}
    for leaked in (
        "prompt-token",
        "prompt-cookie",
        "prompt-password",
        "completion-secret",
        "completion-token",
        "metadata-api-key",
        "metadata-token",
        "Authorization",
        "Cookie",
    ):
        assert leaked not in event_text


def test_p2_state_budget_and_handoff_events_are_compact_and_redacted() -> None:
    state_event = build_state_transition_event(
        from_state="THINKING",
        to_state="EXECUTING",
        reason="switch because token=state-token password=state-password " + "x" * 400,
        source="agent_loop",
        success=True,
        metadata={"phase": "exploit", "secret": "state-secret"},
    )
    budget_event = build_budget_event(
        budget_name="phase_round",
        event="threshold_reached",
        used=12,
        limit=12,
        remaining=0,
        unit="round",
        source="recovery",
        metadata={"phase": "exploit", "token": "budget-token"},
    )
    created = build_handoff_created_event(
        handoff_id="handoff-1",
        source="web",
        target="dispatcher",
        decision_kind="direct_execute",
        next_action="verify_runtime_signal",
        reason="handoff with cookie=handoff-cookie",
        metadata={"run_id": "run-1", "password": "handoff-password"},
    )
    consumed = build_handoff_consumed_event(
        handoff_id="handoff-1",
        consumer="dispatcher",
        status="accepted",
        reason="consumed Authorization: Bearer consumed-token",
        metadata={"checkpoint_id": "checkpoint-1", "api_key": "consumed-api-key"},
    )

    assert state_event["event_type"] == "state_transition"
    assert state_event["payload"]["from_state"] == "THINKING"
    assert state_event["payload"]["to_state"] == "EXECUTING"
    assert state_event["payload"]["metadata"] == {"phase": "exploit"}
    assert len(state_event["payload"]["reason_preview"]) <= 160
    assert budget_event["event_type"] == "budget_event"
    assert budget_event["payload"]["budget_name"] == "phase_round"
    assert budget_event["payload"]["event"] == "threshold_reached"
    assert budget_event["payload"]["used"] == 12
    assert budget_event["payload"]["limit"] == 12
    assert budget_event["payload"]["remaining"] == 0
    assert budget_event["payload"]["metadata"] == {"phase": "exploit"}
    assert created["event_type"] == "handoff_created"
    assert created["payload"]["handoff_id"] == "handoff-1"
    assert created["payload"]["decision_kind"] == "direct_execute"
    assert created["payload"]["next_action"] == "verify_runtime_signal"
    assert created["payload"]["metadata"] == {"run_id": "run-1"}
    assert consumed["event_type"] == "handoff_consumed"
    assert consumed["payload"]["handoff_id"] == "handoff-1"
    assert consumed["payload"]["consumer"] == "dispatcher"
    assert consumed["payload"]["metadata"] == {"checkpoint_id": "checkpoint-1"}

    combined = repr([state_event, budget_event, created, consumed])
    for leaked in (
        "state-token",
        "state-password",
        "state-secret",
        "budget-token",
        "handoff-cookie",
        "handoff-password",
        "consumed-token",
        "consumed-api-key",
        "Authorization",
    ):
        assert leaked not in combined


def test_p2_event_builders_redact_sensitive_structured_fields() -> None:
    events = [
        build_handoff_created_event(
            handoff_id="handoff token=handoff-id-token",
            source="web token=source-token",
            target="http://ctf.local/?token=target-token",
            decision_kind="direct secret=decision-secret",
            next_action="use password=action-password",
        ),
        build_handoff_consumed_event(
            handoff_id="handoff token=consumed-id-token",
            consumer="dispatcher password=consumer-password",
            status="accepted secret=status-secret",
        ),
        build_state_transition_event(
            from_state="THINKING token=from-token",
            to_state="EXECUTING password=to-password",
            source="agent password=source-password",
        ),
        build_budget_event(
            budget_name="phase token=budget-token",
            event="used password=budget-password",
            unit="round secret=unit-secret",
            source="recovery secret=source-secret",
        ),
        build_model_call_event(
            model="model token=model-token",
            provider="provider password=provider-password",
            status="success secret=status-secret",
        ),
    ]

    event_text = repr(events)

    for leaked in (
        "handoff-id-token",
        "source-token",
        "target-token",
        "decision-secret",
        "action-password",
        "consumed-id-token",
        "consumer-password",
        "status-secret",
        "from-token",
        "to-password",
        "source-password",
        "budget-token",
        "budget-password",
        "unit-secret",
        "source-secret",
        "model-token",
        "provider-password",
    ):
        assert leaked not in event_text


def test_p2_event_builders_redact_jsonish_sensitive_structured_fields() -> None:
    events = [
        build_handoff_created_event(
            handoff_id="handoff-json",
            target=json.dumps({"token": "json-target-token"}),
            next_action=json.dumps({"password": "json-action-password"}),
        ),
        build_handoff_consumed_event(
            handoff_id="handoff-json-consumed",
            consumer=json.dumps({"cookie": "json-consumer-cookie"}),
            status=json.dumps({"authorization": "Bearer json-status-auth"}),
        ),
        build_state_transition_event(
            from_state=json.dumps({"api_key": "json-from-key"}),
            to_state="EXECUTING",
            source=json.dumps({"session": "json-source-session"}),
        ),
        build_budget_event(
            budget_name=json.dumps({"secret": "json-budget-secret"}),
            event=json.dumps({"token": "json-budget-token"}),
            source=json.dumps({"password": "json-source-password"}),
        ),
        build_model_call_event(
            model=json.dumps({"token": "json-model-token"}),
            provider=json.dumps({"password": "json-provider-password"}),
            status=json.dumps({"secret": "json-status-secret"}),
            prompt=json.dumps({"authorization": "Bearer json-prompt-auth"}),
            completion=json.dumps({"cookie": "json-completion-cookie"}),
        ),
    ]

    event_text = repr(events)

    for leaked in (
        "json-target-token",
        "json-action-password",
        "json-consumer-cookie",
        "json-status-auth",
        "json-from-key",
        "json-source-session",
        "json-budget-secret",
        "json-budget-token",
        "json-source-password",
        "json-model-token",
        "json-provider-password",
        "json-status-secret",
        "json-prompt-auth",
        "json-completion-cookie",
    ):
        assert leaked not in event_text
