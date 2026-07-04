from __future__ import annotations

from flaghunter.agents.pa_agent.task_dag_replay_audit import (
    TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION,
    TaskDAGReplayAuditEvent,
    build_task_dag_replay_audit_index,
)
from flaghunter.agents.pa_agent.task_dag_replay_audit_readback import (
    TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION,
    TaskDAGReplayAuditReadbackPackage,
    TaskDAGReplayAuditReadbackRow,
)
from flaghunter.agents.pa_agent.task_dag_replay_audit_view import (
    TASK_DAG_REPLAY_AUDIT_VIEW_SCHEMA_VERSION,
    TaskDAGReplayAuditView,
    TaskDAGReplayAuditViewItem,
    build_task_dag_replay_audit_view,
    load_task_dag_replay_audit_view_items,
)


def _row(
    task_id: str,
    *,
    artifact_type: str = "crew_bridge_admission",
    source_id: str | None = None,
    status: str = "succeeded",
    decision: str = "admit_dry",
    warning_count: int = 0,
    warnings: list[str] | None = None,
) -> TaskDAGReplayAuditReadbackRow:
    return TaskDAGReplayAuditReadbackRow(
        schema_version=TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION,
        row_id=f"row-{artifact_type}-{task_id}",
        artifact_type=artifact_type,
        task_id=task_id,
        source_id=source_id or f"source-{task_id}",
        status=status,
        decision=decision,
        summary_snippet=f"Summary for {task_id}",
        evidence_ref_count=2,
        warning_count=warning_count,
        warnings=list(warnings or []),
        metadata={"safe": task_id},
    )


def _package(package_id: str, rows: list[TaskDAGReplayAuditReadbackRow]):
    return TaskDAGReplayAuditReadbackPackage(
        schema_version=TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION,
        package_id=package_id,
        rows=rows,
        summary={"exportedRowCount": len(rows)},
        filters={},
        source_index_ids=[f"index-{package_id}"],
    )


def test_p4e_c_view_shape_overview_and_digest_counts() -> None:
    package = _package(
        "package-a",
        [
            _row("task-ok"),
            _row(
                "task-failed",
                artifact_type="crew_bridge_admission",
                status="failed",
                decision="reject_failed",
            ),
            _row(
                "task-warning",
                artifact_type="recovery_proposal",
                status="",
                decision="retry_task",
                warning_count=1,
                warnings=["needs_review"],
            ),
        ],
    )

    view = build_task_dag_replay_audit_view(readback=package)
    payload = view.to_dict()
    items = payload["items"]

    assert isinstance(view, TaskDAGReplayAuditView)
    assert payload["schemaVersion"] == TASK_DAG_REPLAY_AUDIT_VIEW_SCHEMA_VERSION
    assert payload["viewId"].startswith("task_dag_replay_view_")
    assert payload["sourcePackageIds"] == ["package-a"]
    assert payload["sourceIndexIds"] == ["index-package-a"]
    assert [item["taskId"] for item in items] == [
        "task-failed",
        "task-warning",
        "task-ok",
    ]
    assert [item["kind"] for item in items] == ["attention", "warning", "timeline"]
    assert [item["severity"] for item in items] == ["high", "medium", "info"]
    assert payload["overview"]["sourcePackageCount"] == 1
    assert payload["overview"]["sourceIndexCount"] == 1
    assert payload["overview"]["inputRowCount"] == 3
    assert payload["overview"]["exportedItemCount"] == 3
    assert payload["overview"]["attentionCount"] == 2
    assert payload["overview"]["warningCount"] == 1
    assert payload["overview"]["severityCounts"] == {
        "high": 1,
        "info": 1,
        "medium": 1,
    }
    assert payload["summary"] == payload["overview"]
    for item in items:
        assert set(item) == {
            "schemaVersion",
            "itemId",
            "kind",
            "severity",
            "artifactType",
            "taskId",
            "sourceId",
            "status",
            "decision",
            "title",
            "detailSnippet",
            "warningCount",
            "metadata",
        }
        assert "evidenceRefs" not in item
        assert "executeAction" not in item
        assert "dispatchAction" not in item
        assert "applyRecovery" not in item
    assert "rows" not in payload
    assert "readback" not in payload
    assert "package" not in payload


def test_p4e_c_accepts_mixed_package_row_dict_and_audit_index_inputs() -> None:
    audit_index = build_task_dag_replay_audit_index(
        artifacts={
            "schemaVersion": "custom.compact.v1",
            "id": "custom-1",
            "taskId": "task-index",
            "status": "partial",
            "summary": "Unknown compact artifact",
        }
    )
    row_dict = _row(
        "task-dict",
        artifact_type="crew_bridge_handoff",
        decision="ready_for_review",
    ).to_dict()
    row_dataclass = _row(
        "task-row",
        artifact_type="crew_bridge_preview",
        decision="",
    )

    payload = build_task_dag_replay_audit_view(
        readback=[audit_index, row_dict, row_dataclass]
    ).to_dict()

    assert payload["overview"]["sourceIndexCount"] == 1
    assert payload["overview"]["inputRowCount"] == 3
    assert [item["taskId"] for item in payload["items"]] == [
        "task-index",
        "task-dict",
        "task-row",
    ]
    assert payload["sourceIndexIds"] == [audit_index.index_id]


def test_p4e_c_unknown_or_empty_input_yields_warning_item() -> None:
    payload = build_task_dag_replay_audit_view(readback={}).to_dict()

    assert payload["overview"]["inputRowCount"] == 1
    assert payload["overview"]["warningCount"] == 1
    assert payload["items"][0]["kind"] == "warning"
    assert payload["items"][0]["artifactType"] == "unknown_compact_artifact"
    assert payload["items"][0]["title"] == "unknown_compact_artifact"


def test_p4e_c_severity_and_attention_mapping() -> None:
    rows = [
        _row("task-clean", status="succeeded", decision="admit_dry"),
        _row("task-warn", warning_count=1, warnings=["needs_review"]),
        _row("task-fail", status="failed", decision="reject_failed"),
        _row(
            "task-retry",
            artifact_type="recovery_proposal",
            status="",
            decision="retry_task",
        ),
        _row(
            "task-manual",
            artifact_type="recovery_review",
            status="",
            decision="manual_review",
        ),
    ]

    payload = build_task_dag_replay_audit_view(readback=_package("package-map", rows)).to_dict()
    by_task = {item["taskId"]: item for item in payload["items"]}

    assert by_task["task-clean"]["kind"] == "timeline"
    assert by_task["task-clean"]["severity"] == "info"
    assert by_task["task-warn"]["kind"] == "warning"
    assert by_task["task-warn"]["severity"] == "medium"
    assert by_task["task-fail"]["kind"] == "attention"
    assert by_task["task-fail"]["severity"] == "high"
    assert by_task["task-retry"]["kind"] == "attention"
    assert by_task["task-retry"]["severity"] == "medium"
    assert by_task["task-manual"]["kind"] == "attention"
    assert by_task["task-manual"]["severity"] == "medium"


def test_p4e_c_filters_sorts_and_truncates_deterministically() -> None:
    rows = [
        _row("task-3", artifact_type="crew_bridge_preview", decision=""),
        _row("task-1", artifact_type="crew_bridge_admission"),
        _row(
            "task-2",
            artifact_type="crew_bridge_admission",
            status="failed",
            decision="reject_failed",
            warning_count=1,
            warnings=["failed"],
        ),
        _row("task-4", artifact_type="crew_bridge_admission"),
        _row("other-task", artifact_type="crew_bridge_admission"),
    ]

    first = build_task_dag_replay_audit_view(
        readback=_package("package-filter", rows),
        artifact_type="crew_bridge_admission",
        task_id="task-",
        kind="timeline",
        severity="info",
        has_warnings=False,
        max_items=1,
    ).to_dict()
    second = build_task_dag_replay_audit_view(
        readback=_package("package-filter", list(reversed(rows))),
        artifact_type="crew_bridge_admission",
        task_id="task-",
        kind="timeline",
        severity="info",
        has_warnings=False,
        max_items=1,
    ).to_dict()

    assert first == second
    assert [item["taskId"] for item in first["items"]] == ["task-1"]
    assert first["overview"]["inputRowCount"] == 5
    assert first["overview"]["exportedItemCount"] == 1
    assert first["overview"]["truncatedCount"] == 1
    assert first["filters"] == {
        "kind": "timeline",
        "severity": "info",
        "artifactType": "crew_bridge_admission",
        "taskId": "task-",
        "status": "",
        "decision": "",
        "hasWarnings": False,
    }


def test_p4e_c_filters_by_status_and_decision() -> None:
    payload = build_task_dag_replay_audit_view(
        readback=[
            _row("task-ready", status="succeeded", decision="admit_dry"),
            _row("task-failed", status="failed", decision="reject_failed"),
        ],
        status="failed",
        decision="reject_failed",
    ).to_dict()

    assert [item["taskId"] for item in payload["items"]] == ["task-failed"]
    assert payload["overview"]["statusCounts"] == {"failed": 1}
    assert payload["overview"]["decisionCounts"] == {"reject_failed": 1}


def test_p4e_c_load_view_items_returns_compact_dataclasses() -> None:
    items = load_task_dag_replay_audit_view_items(readback=[_row("task-a")])

    assert len(items) == 1
    assert isinstance(items[0], TaskDAGReplayAuditViewItem)
    assert items[0].to_dict()["taskId"] == "task-a"


def test_p4e_c_direct_view_dataclasses_strip_proof_like_and_raw_values() -> None:
    proof_like = "level='verified' flag{bad}"
    item = TaskDAGReplayAuditViewItem(
        schema_version="",
        item_id="item-a",
        kind="attention",
        severity="high",
        artifact_type="crew_bridge_admission",
        task_id=proof_like,
        source_id=proof_like,
        status=proof_like,
        decision=proof_like,
        title=proof_like,
        detail_snippet='level="verified" CTF{bad}',
        warning_count=2,
        metadata={
            "authorization": "Bearer metadata-auth",
            "prompt": "raw prompt",
            "verification_decision": "bad",
            "verified_flags": ["flag{bad}"],
            "safe": "ok",
        },
    )
    view = TaskDAGReplayAuditView(
        schema_version="",
        view_id="view-a",
        overview={
            "inputRowCount": 1,
            "taskId": proof_like,
            "authorization": "Bearer overview-auth",
            "safeCount": 2,
        },
        items=[item],
        summary={"taskId": proof_like, "safeCount": 2},
        filters={"taskId": proof_like, "kind": "attention"},
        source_package_ids=[proof_like, "package-safe"],
        source_index_ids=[proof_like, "index-safe"],
    )
    payload = view.to_dict()
    item_payload = payload["items"][0]
    text = repr(payload)

    assert item_payload["taskId"] == "<redacted proof-like value>"
    assert item_payload["sourceId"] == "<redacted proof-like value>"
    assert item_payload["status"] == "<redacted proof-like value>"
    assert item_payload["decision"] == "<redacted proof-like value>"
    assert item_payload["title"] == "<redacted proof-like value>"
    assert item_payload["detailSnippet"] == "<redacted proof-like value>"
    assert item_payload["metadata"] == {"authorization": "<redacted>", "safe": "ok"}
    assert payload["overview"]["taskId"] == "<redacted proof-like value>"
    assert payload["overview"]["authorization"] == "<redacted>"
    assert payload["summary"]["taskId"] == "<redacted proof-like value>"
    assert payload["filters"]["taskId"] == "<redacted proof-like value>"
    assert payload["sourcePackageIds"] == ["<redacted proof-like value>", "package-safe"]
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
        "overview-auth",
    ):
        assert leaked not in text


def test_p4e_c_view_is_deterministic_for_same_normalized_inputs() -> None:
    rows = [
        _row("task-b", artifact_type="crew_bridge_handoff", decision="ready_for_review"),
        _row("task-a", artifact_type="crew_bridge_admission"),
    ]

    first = build_task_dag_replay_audit_view(readback=_package("package-det", rows))
    second = build_task_dag_replay_audit_view(
        readback=_package("package-det", list(reversed(rows)))
    )

    assert first.view_id == second.view_id
    assert first.to_dict() == second.to_dict()
