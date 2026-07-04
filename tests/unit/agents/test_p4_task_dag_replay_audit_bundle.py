from __future__ import annotations

from flaghunter.agents.pa_agent.task_dag_replay_audit import (
    TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION,
    build_task_dag_replay_audit_index,
)
from flaghunter.agents.pa_agent.task_dag_replay_audit_bundle import (
    TASK_DAG_REPLAY_AUDIT_BUNDLE_SCHEMA_VERSION,
    TaskDAGReplayAuditBundle,
    build_task_dag_replay_audit_bundle,
    load_task_dag_replay_audit_bundle_items,
)
from flaghunter.agents.pa_agent.task_dag_replay_audit_readback import (
    build_task_dag_replay_audit_readback,
)
from flaghunter.agents.pa_agent.task_dag_replay_audit_view import (
    build_task_dag_replay_audit_view,
)


def _artifact(task_id: str, *, status: str = "succeeded", decision: str = "admit_dry"):
    return {
        "schemaVersion": "custom.compact.v1",
        "id": f"artifact-{task_id}",
        "taskId": task_id,
        "status": status,
        "decision": decision,
        "summary": f"Summary for {task_id}",
        "metadata": {"safe": task_id},
    }


def test_p4e_d_bundle_shape_from_compact_artifacts() -> None:
    bundle = build_task_dag_replay_audit_bundle(
        artifacts=[
            _artifact("task-a"),
            _artifact("task-b", status="failed", decision="reject_failed"),
        ]
    )
    payload = bundle.to_dict()

    assert isinstance(bundle, TaskDAGReplayAuditBundle)
    assert payload["schemaVersion"] == TASK_DAG_REPLAY_AUDIT_BUNDLE_SCHEMA_VERSION
    assert payload["bundleId"].startswith("task_dag_replay_bundle_")
    assert payload["index"]["schemaVersion"] == TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION
    assert payload["readback"]["schemaVersion"] == "p4e.task_dag_replay_audit_readback.v1"
    assert payload["view"]["schemaVersion"] == "p4e.task_dag_replay_audit_view.v1"
    assert payload["summary"]["artifactCount"] == 2
    assert payload["summary"]["indexEventCount"] == 2
    assert payload["summary"]["readbackRowCount"] == 2
    assert payload["summary"]["viewItemCount"] == 2
    assert payload["summary"]["warningCount"] == 2
    assert payload["summary"]["attentionCount"] == 2
    assert payload["warnings"] == []
    assert "artifacts" not in payload
    assert "executeAction" not in repr(payload)
    assert "dispatchAction" not in repr(payload)
    assert "applyRecovery" not in repr(payload)


def test_p4e_d_accepts_prebuilt_index_and_composes_readback_and_view() -> None:
    index = build_task_dag_replay_audit_index(
        artifacts=[_artifact("task-index", status="failed", decision="reject_failed")]
    )

    payload = build_task_dag_replay_audit_bundle(index=index).to_dict()

    assert payload["index"]["indexId"] == index.index_id
    assert payload["readback"]["summary"]["inputEventCount"] == 1
    assert payload["view"]["overview"]["inputRowCount"] == 1
    assert payload["summary"]["sourceIndexCount"] == 1


def test_p4e_d_accepts_readback_or_view_only_with_clear_warning() -> None:
    index = build_task_dag_replay_audit_index(artifacts=[_artifact("task-a")])
    readback = build_task_dag_replay_audit_readback(audit=index)
    view = build_task_dag_replay_audit_view(readback=readback)

    readback_payload = build_task_dag_replay_audit_bundle(readback=readback).to_dict()
    view_payload = build_task_dag_replay_audit_bundle(view=view).to_dict()

    assert readback_payload["readback"]["packageId"] == readback.package_id
    assert readback_payload["view"]["overview"]["inputRowCount"] == 1
    assert readback_payload["index"]["events"] == []
    assert "missing_source_index" in readback_payload["warnings"]
    assert view_payload["view"]["viewId"] == view.view_id
    assert view_payload["index"]["events"] == []
    assert view_payload["readback"]["rows"] == []
    assert "missing_source_index" in view_payload["warnings"]
    assert "missing_source_readback" in view_payload["warnings"]


def test_p4e_d_empty_input_returns_valid_warning_bundle() -> None:
    payload = build_task_dag_replay_audit_bundle().to_dict()

    assert payload["index"]["events"] == []
    assert payload["readback"]["rows"] == []
    assert payload["view"]["items"] == []
    assert payload["summary"]["artifactCount"] == 0
    assert payload["summary"]["warningCount"] == 1
    assert payload["warnings"] == ["empty_replay_audit_bundle_input"]


def test_p4e_d_filter_and_max_values_propagate_to_layers() -> None:
    payload = build_task_dag_replay_audit_bundle(
        artifacts=[
            _artifact("task-1"),
            _artifact("task-2", status="failed", decision="reject_failed"),
            _artifact("task-3", status="failed", decision="reject_failed"),
        ],
        status="failed",
        decision="reject_failed",
        max_events=2,
        max_rows=1,
        max_items=1,
    ).to_dict()

    assert payload["index"]["summary"]["exportedCount"] == 2
    assert payload["readback"]["summary"]["exportedRowCount"] == 1
    assert payload["view"]["overview"]["exportedItemCount"] == 1
    assert payload["summary"]["truncatedCount"] == 1
    assert payload["filters"]["status"] == "failed"
    assert payload["filters"]["decision"] == "reject_failed"


def test_p4e_d_load_bundle_items_returns_view_items() -> None:
    items = load_task_dag_replay_audit_bundle_items(
        artifacts=[_artifact("task-a")],
    )

    assert len(items) == 1
    assert items[0].to_dict()["taskId"] == "task-a"


def test_p4e_d_direct_bundle_dataclass_strips_proof_like_and_raw_values() -> None:
    proof_like = "level='verified' flag{bad}"
    bundle = TaskDAGReplayAuditBundle(
        schema_version="",
        bundle_id="bundle-a",
        index={"schemaVersion": "p4e.task_dag_replay_audit.v1", "events": []},
        readback={"schemaVersion": "p4e.task_dag_replay_audit_readback.v1", "rows": []},
        view={"schemaVersion": "p4e.task_dag_replay_audit_view.v1", "items": []},
        summary={
            "artifactCount": 1,
            "taskId": proof_like,
            "authorization": "Bearer summary-auth",
        },
        filters={"taskId": proof_like, "status": "failed"},
        warnings=[proof_like],
        metadata={
            "authorization": "Bearer metadata-auth",
            "prompt": "raw prompt",
            "verification_decision": "bad",
            "verified_flags": ["flag{bad}"],
            "safe": "ok",
        },
    )
    payload = bundle.to_dict()
    text = repr(payload)

    assert payload["summary"]["taskId"] == "<redacted proof-like value>"
    assert payload["summary"]["authorization"] == "<redacted>"
    assert payload["filters"]["taskId"] == "<redacted proof-like value>"
    assert payload["warnings"] == ["<redacted proof-like value>"]
    assert payload["metadata"] == {"authorization": "<redacted>", "safe": "ok"}
    for leaked in (
        "level='verified'",
        'level="verified"',
        "flag{bad}",
        "raw prompt",
        "verification_decision",
        "verified_flags",
        "metadata-auth",
        "summary-auth",
    ):
        assert leaked not in text


def test_p4e_d_bundle_id_is_deterministic_for_same_normalized_input() -> None:
    artifacts = [
        _artifact("task-b", status="failed", decision="reject_failed"),
        _artifact("task-a"),
    ]

    first = build_task_dag_replay_audit_bundle(artifacts=artifacts)
    second = build_task_dag_replay_audit_bundle(artifacts=list(reversed(artifacts)))

    assert first.bundle_id == second.bundle_id
    assert first.to_dict() == second.to_dict()
