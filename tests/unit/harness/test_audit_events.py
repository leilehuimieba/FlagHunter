from __future__ import annotations

from types import SimpleNamespace

from flaghunter.harness.audit_events import (
    build_artifact_registered_event,
    build_control_action_completed_event,
    build_control_action_started_event,
    build_checkpoint_written_event,
    build_dispatcher_started_event,
    build_missing_tools_recorded_event,
    build_recovery_decision_event,
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
