from __future__ import annotations

from flaghunter.agents.pa_agent.task_dag_crew_bridge_admission import (
    TASK_DAG_CREW_BRIDGE_ADMISSION_SCHEMA_VERSION,
    TaskDAGCrewBridgeAdmissionItem,
    TaskDAGCrewBridgeAdmissionPackage,
)
from flaghunter.agents.pa_agent.task_dag_replay_audit import (
    TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION,
    TaskDAGReplayAuditEvent,
    TaskDAGReplayAuditIndex,
    build_task_dag_replay_audit_index,
    load_task_dag_replay_audit_events,
)
from flaghunter.agents.pa_agent.task_dag_recovery_review import (
    TASK_DAG_RECOVERY_REVIEW_SCHEMA_VERSION,
    TaskDAGRecoveryReview,
)


def _recovery_proposal(task_id: str) -> dict:
    return {
        "schemaVersion": "p4c.task_dag_recovery_proposal.v1",
        "proposalId": f"proposal-{task_id}",
        "action": "propose_recovery",
        "taskId": task_id,
        "sourceReceiptId": f"receipt-{task_id}",
        "sourceStatus": "failed",
        "recoveryReason": "task_failed",
        "recommendedAction": "retry_task",
        "confidence": 0.6,
        "priority": "high",
        "evidenceRefs": [f"trace-{task_id}"],
        "warnings": [],
        "metadata": {"safe": task_id},
    }


def _recovery_review(task_id: str) -> TaskDAGRecoveryReview:
    return TaskDAGRecoveryReview(
        schema_version=TASK_DAG_RECOVERY_REVIEW_SCHEMA_VERSION,
        review_id=f"review-{task_id}",
        selected_proposal_id=f"proposal-{task_id}",
        task_id=task_id,
        review_reason="selected_retry_task",
        recommended_action="retry_task",
        attention="review",
        confidence=0.6,
        evidence_refs=[f"review-trace-{task_id}"],
        warnings=[],
        metadata={"safe": f"review-{task_id}"},
        valid=True,
        summary={"inputCount": 1},
    )


def _preview_payload(task_id: str) -> dict:
    return {
        "schemaVersion": "p4d.task_dag_crew_bridge_preview.v1",
        "records": [
            {
                "taskId": task_id,
                "requestId": f"request-{task_id}",
                "receiptId": f"receipt-{task_id}",
                "taskBriefId": f"brief-{task_id}",
                "solveNodeId": f"node-{task_id}",
                "workerType": "web",
                "status": "succeeded",
                "goalSnippet": "Inspect bridge request",
                "summarySnippet": "Preview summary",
                "hasReceipt": True,
                "evidenceRefs": [f"preview-trace-{task_id}"],
                "warnings": [],
                "metadata": {"safe": f"preview-{task_id}"},
            }
        ],
    }


def _handoff_payload(task_id: str) -> dict:
    return {
        "schemaVersion": "p4d.task_dag_crew_bridge_handoff.v1",
        "items": [
            {
                "taskId": task_id,
                "requestId": f"request-{task_id}",
                "receiptId": f"receipt-{task_id}",
                "workerType": "web",
                "status": "succeeded",
                "handoffDecision": "ready_for_review",
                "goalSnippet": "Handoff goal",
                "summarySnippet": "Handoff summary",
                "hasReceipt": True,
                "evidenceRefs": [f"handoff-trace-{task_id}"],
                "warnings": [],
                "metadata": {"safe": f"handoff-{task_id}"},
            }
        ],
    }


def _admission_package(task_id: str) -> TaskDAGCrewBridgeAdmissionPackage:
    return TaskDAGCrewBridgeAdmissionPackage(
        schema_version=TASK_DAG_CREW_BRIDGE_ADMISSION_SCHEMA_VERSION,
        package_id=f"admission-{task_id}",
        items=[
            TaskDAGCrewBridgeAdmissionItem(
                schema_version=TASK_DAG_CREW_BRIDGE_ADMISSION_SCHEMA_VERSION,
                task_id=task_id,
                request_id=f"request-{task_id}",
                receipt_id=f"receipt-{task_id}",
                worker_type="web",
                status="succeeded",
                handoff_decision="ready_for_review",
                admission_state="admit_dry",
                reason="ready_for_review",
                goal_snippet="Admission goal",
                summary_snippet="Admission summary",
                has_receipt=True,
                evidence_refs=[f"admission-trace-{task_id}"],
                warnings=[],
                metadata={"safe": f"admission-{task_id}"},
            )
        ],
        summary={"exportedCount": 1},
        filters={},
    )


def test_p4e_a_audit_index_shape_and_counts_from_compact_artifacts() -> None:
    index = build_task_dag_replay_audit_index(
        artifacts=[
            _recovery_review("task-review"),
            _recovery_proposal("task-proposal"),
            _preview_payload("task-preview"),
            _handoff_payload("task-handoff"),
            _admission_package("task-admission"),
        ]
    )
    payload = index.to_dict()
    events = payload["events"]

    assert isinstance(index, TaskDAGReplayAuditIndex)
    assert payload["schemaVersion"] == TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION
    assert payload["indexId"].startswith("task_dag_replay_audit_")
    assert [event["artifactType"] for event in events] == [
        "crew_bridge_admission",
        "crew_bridge_handoff",
        "crew_bridge_preview",
        "recovery_proposal",
        "recovery_review",
    ]
    assert payload["summary"]["artifactCount"] == 5
    assert payload["summary"]["eventCount"] == 5
    assert payload["summary"]["exportedCount"] == 5
    assert payload["summary"]["truncatedCount"] == 0
    assert payload["summary"]["warningCount"] == 0
    assert payload["summary"]["artifactTypeCounts"] == {
        "crew_bridge_admission": 1,
        "crew_bridge_handoff": 1,
        "crew_bridge_preview": 1,
        "recovery_proposal": 1,
        "recovery_review": 1,
    }
    assert payload["summary"]["statusCounts"] == {
        "failed": 1,
        "succeeded": 3,
    }
    assert payload["summary"]["decisionCounts"] == {
        "admit_dry": 1,
        "propose_recovery": 1,
        "ready_for_review": 1,
        "retry_task": 1,
    }
    for event in events:
        assert set(event) == {
            "schemaVersion",
            "eventId",
            "artifactType",
            "sourceSchemaVersion",
            "taskId",
            "sourceId",
            "status",
            "decision",
            "summarySnippet",
            "evidenceRefs",
            "warnings",
            "metadata",
        }
    assert "artifacts" not in payload
    assert "handoff" not in payload
    assert "admission" not in payload
    assert "proposal" not in payload


def test_p4e_a_unknown_compact_dict_becomes_bounded_unknown_event() -> None:
    payload = build_task_dag_replay_audit_index(
        artifacts={
            "schemaVersion": "custom.compact.v1",
            "id": "custom-1",
            "taskId": "task-custom",
            "status": "partial",
            "summary": "Compact unknown summary",
            "metadata": {"safe": "ok"},
        }
    ).to_dict()
    event = payload["events"][0]

    assert event["artifactType"] == "unknown_compact_artifact"
    assert event["sourceSchemaVersion"] == "custom.compact.v1"
    assert event["taskId"] == "task-custom"
    assert event["sourceId"] == "custom-1"
    assert event["status"] == "partial"
    assert event["summarySnippet"] == "Compact unknown summary"
    assert event["warnings"] == ["unknown_compact_artifact"]
    assert payload["summary"]["warningCount"] == 1


def test_p4e_a_filters_sorts_and_truncates_deterministically() -> None:
    artifacts = [
        _preview_payload("task-3"),
        _admission_package("task-1"),
        _handoff_payload("task-2"),
        _recovery_proposal("other-task"),
    ]

    first = build_task_dag_replay_audit_index(
        artifacts=artifacts,
        artifact_type="crew_bridge_admission",
        task_id="task-",
        decision="admit_dry",
        max_events=1,
    ).to_dict()
    second = build_task_dag_replay_audit_index(
        artifacts=list(reversed(artifacts)),
        artifact_type="crew_bridge_admission",
        task_id="task-",
        decision="admit_dry",
        max_events=1,
    ).to_dict()

    assert first == second
    assert [event["taskId"] for event in first["events"]] == ["task-1"]
    assert first["summary"]["artifactCount"] == 4
    assert first["summary"]["eventCount"] == 1
    assert first["summary"]["exportedCount"] == 1
    assert first["summary"]["truncatedCount"] == 0
    assert first["summary"]["filters"] == {
        "artifactType": "crew_bridge_admission",
        "taskId": "task-",
        "status": "",
        "decision": "admit_dry",
        "hasWarnings": None,
    }


def test_p4e_a_filters_by_status_and_warning_presence() -> None:
    payload = build_task_dag_replay_audit_index(
        artifacts=[
            _recovery_proposal("task-clean"),
            {
                "schemaVersion": "custom.compact.v1",
                "id": "custom-warn",
                "taskId": "task-warn",
                "status": "partial",
                "summary": "Unknown",
            },
        ],
        status="partial",
        has_warnings=True,
    ).to_dict()

    assert [event["taskId"] for event in payload["events"]] == ["task-warn"]
    assert payload["events"][0]["artifactType"] == "unknown_compact_artifact"
    assert payload["summary"]["filters"]["status"] == "partial"
    assert payload["summary"]["filters"]["hasWarnings"] is True


def test_p4e_a_load_audit_events_returns_compact_dataclasses() -> None:
    events = load_task_dag_replay_audit_events(
        artifacts=[_admission_package("task-a")]
    )

    assert len(events) == 1
    assert isinstance(events[0], TaskDAGReplayAuditEvent)
    assert events[0].to_dict()["artifactType"] == "crew_bridge_admission"


def test_p4e_a_direct_audit_dataclasses_strip_proof_like_and_raw_values() -> None:
    proof_like = "level='verified' flag{bad}"
    event = TaskDAGReplayAuditEvent(
        schema_version="",
        event_id="event-a",
        artifact_type="crew_bridge_admission",
        source_schema_version=proof_like,
        task_id=proof_like,
        source_id=proof_like,
        status=proof_like,
        decision=proof_like,
        summary_snippet='level="verified" CTF{bad}',
        evidence_refs=[proof_like],
        warnings=[proof_like],
        metadata={
            "authorization": "Bearer metadata-auth",
            "prompt": "raw prompt",
            "verification_decision": "bad",
            "verified_flags": ["flag{bad}"],
            "safe": "ok",
        },
    )
    index = TaskDAGReplayAuditIndex(
        schema_version="",
        index_id="index-a",
        events=[event],
        summary={
            "eventCount": 1,
            "taskId": proof_like,
            "authorization": "Bearer summary-auth",
            "safeCount": 2,
        },
        filters={"taskId": proof_like, "artifactType": "crew_bridge_admission"},
    )
    payload = index.to_dict()
    event_payload = payload["events"][0]
    text = repr(payload)

    assert event_payload["sourceSchemaVersion"] == "<redacted proof-like value>"
    assert event_payload["taskId"] == "<redacted proof-like value>"
    assert event_payload["sourceId"] == "<redacted proof-like value>"
    assert event_payload["status"] == "<redacted proof-like value>"
    assert event_payload["decision"] == "<redacted proof-like value>"
    assert event_payload["summarySnippet"] == "<redacted proof-like value>"
    assert event_payload["evidenceRefs"] == ["<redacted proof-like value>"]
    assert event_payload["warnings"] == ["<redacted proof-like value>"]
    assert event_payload["metadata"] == {"authorization": "<redacted>", "safe": "ok"}
    assert payload["summary"]["taskId"] == "<redacted proof-like value>"
    assert payload["summary"]["authorization"] == "<redacted>"
    assert payload["summary"]["safeCount"] == 2
    assert payload["filters"]["taskId"] == "<redacted proof-like value>"
    for leaked in (
        "level='verified'",
        'level="verified"',
        "flag{bad}",
        "CTF{bad}",
        "raw prompt",
        "verification_decision",
        "verified_flags",
        "metadata-auth",
        "summary-auth",
    ):
        assert leaked not in text


def test_p4e_a_index_is_deterministic_for_same_normalized_inputs() -> None:
    artifacts = [
        _admission_package("task-b"),
        _admission_package("task-a"),
        _recovery_proposal("task-c"),
    ]

    first = build_task_dag_replay_audit_index(artifacts=artifacts)
    second = build_task_dag_replay_audit_index(artifacts=list(reversed(artifacts)))

    assert first.index_id == second.index_id
    assert first.to_dict() == second.to_dict()
