from __future__ import annotations

from flaghunter.agents.pa_agent.task_dag_replay_audit import (
    TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION,
    TaskDAGReplayAuditEvent,
    TaskDAGReplayAuditIndex,
    build_task_dag_replay_audit_index,
)
from flaghunter.agents.pa_agent.task_dag_replay_audit_readback import (
    TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION,
    TaskDAGReplayAuditReadbackPackage,
    TaskDAGReplayAuditReadbackRow,
    build_task_dag_replay_audit_readback,
    load_task_dag_replay_audit_readback_rows,
)


def _event(
    task_id: str,
    *,
    artifact_type: str = "crew_bridge_admission",
    source_id: str | None = None,
    status: str = "succeeded",
    decision: str = "admit_dry",
    warnings: list[str] | None = None,
) -> TaskDAGReplayAuditEvent:
    return TaskDAGReplayAuditEvent(
        schema_version=TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION,
        event_id=f"event-{artifact_type}-{task_id}",
        artifact_type=artifact_type,
        source_schema_version="p4e.source.v1",
        task_id=task_id,
        source_id=source_id or f"source-{task_id}",
        status=status,
        decision=decision,
        summary_snippet=f"Summary for {task_id}",
        evidence_refs=[f"trace-{task_id}", f"claim-{task_id}"],
        warnings=list(warnings or []),
        metadata={"safe": task_id},
    )


def _index(index_id: str, events: list[TaskDAGReplayAuditEvent]) -> TaskDAGReplayAuditIndex:
    return TaskDAGReplayAuditIndex(
        schema_version=TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION,
        index_id=index_id,
        events=events,
        summary={"eventCount": len(events)},
        filters={},
    )


def test_p4e_b_readback_package_shape_and_summary_counts() -> None:
    source_index = _index(
        "index-a",
        [
            _event("task-a"),
            _event(
                "task-b",
                artifact_type="recovery_proposal",
                status="failed",
                decision="propose_recovery",
                warnings=["needs_review"],
            ),
        ],
    )

    package = build_task_dag_replay_audit_readback(audit=source_index)
    payload = package.to_dict()
    rows = payload["rows"]

    assert isinstance(package, TaskDAGReplayAuditReadbackPackage)
    assert payload["schemaVersion"] == TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION
    assert payload["packageId"].startswith("task_dag_replay_readback_")
    assert payload["sourceIndexIds"] == ["index-a"]
    assert [row["artifactType"] for row in rows] == [
        "crew_bridge_admission",
        "recovery_proposal",
    ]
    assert rows[0]["evidenceRefCount"] == 2
    assert rows[0]["warningCount"] == 0
    assert rows[1]["warningCount"] == 1
    assert payload["summary"]["sourceIndexCount"] == 1
    assert payload["summary"]["inputEventCount"] == 2
    assert payload["summary"]["exportedRowCount"] == 2
    assert payload["summary"]["truncatedCount"] == 0
    assert payload["summary"]["warningCount"] == 1
    assert payload["summary"]["hasWarningsCount"] == 1
    assert payload["summary"]["artifactTypeCounts"] == {
        "crew_bridge_admission": 1,
        "recovery_proposal": 1,
    }
    assert payload["summary"]["statusCounts"] == {"failed": 1, "succeeded": 1}
    assert payload["summary"]["decisionCounts"] == {
        "admit_dry": 1,
        "propose_recovery": 1,
    }
    for row in rows:
        assert set(row) == {
            "schemaVersion",
            "rowId",
            "artifactType",
            "taskId",
            "sourceId",
            "status",
            "decision",
            "summarySnippet",
            "evidenceRefCount",
            "warningCount",
            "warnings",
            "metadata",
        }
        assert "evidenceRefs" not in row
    assert "events" not in payload
    assert "audit" not in payload
    assert "index" not in payload


def test_p4e_b_accepts_mixed_index_event_and_dict_inputs() -> None:
    source_index = build_task_dag_replay_audit_index(
        artifacts={
            "schemaVersion": "custom.compact.v1",
            "id": "custom-1",
            "taskId": "task-custom",
            "status": "partial",
            "summary": "Unknown compact artifact",
        }
    )
    event_dict = _event(
        "task-dict",
        artifact_type="crew_bridge_handoff",
        decision="ready_for_review",
    ).to_dict()
    event_dataclass = _event(
        "task-event",
        artifact_type="crew_bridge_preview",
        decision="",
    )

    payload = build_task_dag_replay_audit_readback(
        audit=[source_index, event_dict, event_dataclass]
    ).to_dict()

    assert payload["summary"]["sourceIndexCount"] == 1
    assert payload["summary"]["inputEventCount"] == 3
    assert [row["taskId"] for row in payload["rows"]] == [
        "task-dict",
        "task-event",
        "task-custom",
    ]
    assert payload["sourceIndexIds"] == [source_index.index_id]


def test_p4e_b_unknown_or_empty_compact_input_yields_warning_row() -> None:
    payload = build_task_dag_replay_audit_readback(audit={}).to_dict()

    assert payload["summary"]["inputEventCount"] == 1
    assert payload["summary"]["warningCount"] == 1
    assert payload["rows"][0]["artifactType"] == "unknown_compact_artifact"
    assert payload["rows"][0]["warnings"] == ["invalid_replay_audit_input"]


def test_p4e_b_filters_sorts_and_truncates_deterministically() -> None:
    events = [
        _event("task-3", artifact_type="crew_bridge_preview", decision=""),
        _event("task-1", artifact_type="crew_bridge_admission"),
        _event(
            "task-2",
            artifact_type="crew_bridge_admission",
            source_id="source-task-2",
            status="failed",
            decision="reject_failed",
            warnings=["failed"],
        ),
        _event("task-4", artifact_type="crew_bridge_admission"),
        _event("other-task", artifact_type="crew_bridge_admission"),
    ]

    first = build_task_dag_replay_audit_readback(
        audit=_index("index-filter", events),
        artifact_type="crew_bridge_admission",
        task_id="task-",
        has_warnings=False,
        max_rows=1,
    ).to_dict()
    second = build_task_dag_replay_audit_readback(
        audit=_index("index-filter", list(reversed(events))),
        artifact_type="crew_bridge_admission",
        task_id="task-",
        has_warnings=False,
        max_rows=1,
    ).to_dict()

    assert first == second
    assert [row["taskId"] for row in first["rows"]] == ["task-1"]
    assert first["summary"]["inputEventCount"] == 5
    assert first["summary"]["exportedRowCount"] == 1
    assert first["summary"]["truncatedCount"] == 1
    assert first["summary"]["filters"] == {
        "artifactType": "crew_bridge_admission",
        "taskId": "task-",
        "status": "",
        "decision": "",
        "hasWarnings": False,
    }


def test_p4e_b_filters_by_status_and_decision() -> None:
    payload = build_task_dag_replay_audit_readback(
        audit=[
            _event("task-ready", status="succeeded", decision="admit_dry"),
            _event("task-failed", status="failed", decision="reject_failed"),
        ],
        status="failed",
        decision="reject_failed",
    ).to_dict()

    assert [row["taskId"] for row in payload["rows"]] == ["task-failed"]
    assert payload["summary"]["statusCounts"] == {"failed": 1}
    assert payload["summary"]["decisionCounts"] == {"reject_failed": 1}


def test_p4e_b_load_rows_returns_compact_dataclasses() -> None:
    rows = load_task_dag_replay_audit_readback_rows(
        audit=[_event("task-a")]
    )

    assert len(rows) == 1
    assert isinstance(rows[0], TaskDAGReplayAuditReadbackRow)
    assert rows[0].to_dict()["taskId"] == "task-a"


def test_p4e_b_direct_readback_dataclasses_strip_proof_like_and_raw_values() -> None:
    proof_like = "level='verified' flag{bad}"
    row = TaskDAGReplayAuditReadbackRow(
        schema_version="",
        row_id="row-a",
        artifact_type="crew_bridge_admission",
        task_id=proof_like,
        source_id=proof_like,
        status=proof_like,
        decision=proof_like,
        summary_snippet='level="verified" CTF{bad}',
        evidence_ref_count=3,
        warning_count=2,
        warnings=[proof_like],
        metadata={
            "authorization": "Bearer metadata-auth",
            "prompt": "raw prompt",
            "verification_decision": "bad",
            "verified_flags": ["flag{bad}"],
            "safe": "ok",
        },
    )
    package = TaskDAGReplayAuditReadbackPackage(
        schema_version="",
        package_id="package-a",
        rows=[row],
        summary={
            "rowCount": 1,
            "taskId": proof_like,
            "authorization": "Bearer summary-auth",
            "safeCount": 2,
        },
        filters={"taskId": proof_like, "artifactType": "crew_bridge_admission"},
        source_index_ids=[proof_like, "index-safe"],
    )
    payload = package.to_dict()
    row_payload = payload["rows"][0]
    text = repr(payload)

    assert row_payload["taskId"] == "<redacted proof-like value>"
    assert row_payload["sourceId"] == "<redacted proof-like value>"
    assert row_payload["status"] == "<redacted proof-like value>"
    assert row_payload["decision"] == "<redacted proof-like value>"
    assert row_payload["summarySnippet"] == "<redacted proof-like value>"
    assert row_payload["warnings"] == ["<redacted proof-like value>"]
    assert row_payload["metadata"] == {"authorization": "<redacted>", "safe": "ok"}
    assert payload["summary"]["taskId"] == "<redacted proof-like value>"
    assert payload["summary"]["authorization"] == "<redacted>"
    assert payload["summary"]["safeCount"] == 2
    assert payload["filters"]["taskId"] == "<redacted proof-like value>"
    assert payload["sourceIndexIds"] == ["<redacted proof-like value>", "index-safe"]
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


def test_p4e_b_package_is_deterministic_for_same_normalized_inputs() -> None:
    events = [
        _event("task-b", artifact_type="crew_bridge_handoff", decision="ready_for_review"),
        _event("task-a", artifact_type="crew_bridge_admission"),
    ]

    first = build_task_dag_replay_audit_readback(audit=_index("index-det", events))
    second = build_task_dag_replay_audit_readback(
        audit=_index("index-det", list(reversed(events)))
    )

    assert first.package_id == second.package_id
    assert first.to_dict() == second.to_dict()
