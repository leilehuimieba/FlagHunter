from __future__ import annotations

import json

from flaghunter.agents.pa_agent.solve_node import (
    SolveNode,
    SolveNodeKind,
    SolveNodeStatus,
    build_solve_node_readback,
    empty_solve_node_snapshot,
    solve_node_from_dict,
    solve_node_to_dict,
)


def test_p3a_default_solve_node_shape_is_stable() -> None:
    node = SolveNode(title="Initial recon")
    payload = solve_node_to_dict(node)

    assert payload["id"].startswith("node_")
    assert payload["run_id"] == ""
    assert payload["parent_id"] == ""
    assert payload["kind"] == "generic"
    assert payload["status"] == "planned"
    assert payload["title"] == "Initial recon"
    assert payload["goal"] == ""
    assert payload["summary"] == ""
    assert isinstance(payload["created_at"], float)
    assert isinstance(payload["updated_at"], float)
    assert payload["started_at"] is None
    assert payload["finished_at"] is None
    assert payload["claim_ids"] == []
    assert payload["trace_ids"] == []
    assert payload["receipt_ids"] == []
    assert payload["artifact_refs"] == []
    assert payload["metadata"] == {}


def test_p3a_solve_node_enum_serialization_and_restore() -> None:
    node = SolveNode(
        id="node-exp-1",
        run_id="run-1",
        kind=SolveNodeKind.EXPLOIT,
        status=SolveNodeStatus.RUNNING,
        title="Exploit path",
    )

    restored = solve_node_from_dict(solve_node_to_dict(node))

    assert restored.id == "node-exp-1"
    assert restored.run_id == "run-1"
    assert restored.kind is SolveNodeKind.EXPLOIT
    assert restored.status is SolveNodeStatus.RUNNING
    assert solve_node_to_dict(restored)["kind"] == "exploit"
    assert solve_node_to_dict(restored)["status"] == "running"


def test_p3a_solve_node_restore_unknown_legacy_enums_fallback() -> None:
    restored = solve_node_from_dict(
        {
            "id": "node-legacy",
            "kind": "future_kind",
            "status": "future_status",
            "title": "Legacy node",
        }
    )

    assert restored.kind is SolveNodeKind.GENERIC
    assert restored.status is SolveNodeStatus.PLANNED


def test_p3a_solve_node_restore_ignores_unknown_future_fields() -> None:
    restored = solve_node_from_dict(
        {
            "id": "node-1",
            "future_field": "ignored",
            "kind": "future_kind",
            "status": "future_status",
        }
    )

    assert restored.id == "node-1"
    assert restored.kind is SolveNodeKind.GENERIC
    assert restored.status is SolveNodeStatus.PLANNED


def test_p3a_solve_node_restore_coerces_list_fields_and_metadata() -> None:
    restored = solve_node_from_dict(
        {
            "id": "",
            "claim_ids": ["claim-1", 2, "", None],
            "trace_ids": "trace-1",
            "receipt_ids": ("receipt-1", "receipt-2"),
            "artifact_refs": {"artifact": "ignored"},
            "metadata": "not-a-dict",
        }
    )

    assert restored.id.startswith("node_")
    assert restored.claim_ids == ["claim-1", "2"]
    assert restored.trace_ids == ["trace-1"]
    assert restored.receipt_ids == ["receipt-1", "receipt-2"]
    assert restored.artifact_refs == []
    assert restored.metadata == {}


def test_p3a_empty_solve_node_snapshot_is_stable() -> None:
    assert empty_solve_node_snapshot() == {
        "schemaVersion": "p3.solve_node_snapshot.v1",
        "nodes": [],
        "summary": {
            "nodeCount": 0,
            "exportedNodeCount": 0,
            "truncatedNodeCount": 0,
            "statusCounts": {},
            "kindCounts": {},
        },
    }


def test_p3a_solve_node_readback_redacts_sensitive_content() -> None:
    node = SolveNode(
        id="node-redact",
        kind=SolveNodeKind.RECON,
        status=SolveNodeStatus.BLOCKED,
        title="Probe token=title-token",
        goal="Login with password=goal-password",
        summary=(
            "Cookie: session=summary-cookie\n"
            "Authorization: Bearer summary-token\n"
            "secret=summary-secret"
        ),
        artifact_refs=[
            "file://loot/password=artifact-password.txt",
            "http://ctf.local/?token=artifact-token",
        ],
        metadata={
            "phase": "recon token=metadata-token",
            "headers": {"Authorization": "Bearer metadata-token"},
            "password": "metadata-password",
        },
    )

    readback = build_solve_node_readback([node])
    text = repr(readback)
    item = readback["nodes"][0]

    assert item["nodeId"] == "node-redact"
    assert item["kind"] == "recon"
    assert item["status"] == "blocked"
    assert "token=<redacted>" in item["titlePreview"]
    assert "password=<redacted>" in item["goalPreview"]
    assert item["artifactRefs"] == [
        "file://loot/password=<redacted>",
        "http://ctf.local/?token=<redacted>",
    ]
    for leaked in (
        "title-token",
        "goal-password",
        "summary-cookie",
        "summary-token",
        "summary-secret",
        "artifact-password",
        "artifact-token",
        "metadata-token",
        "metadata-password",
        "Authorization",
        "Cookie",
    ):
        assert leaked not in text


def test_p3a_solve_node_readback_redacts_jsonish_sensitive_values() -> None:
    summary = json.dumps({"token": "raw-token", "password": "raw-pass"})
    note = json.dumps({"secret": "raw-secret"})
    node = SolveNode(
        id="node-json-redact",
        title=json.dumps({"api_key": "raw-api-key"}),
        goal=json.dumps({"session": "raw-session"}),
        summary=summary,
        artifact_refs=[json.dumps({"authorization": "Bearer raw-auth"})],
        metadata={"note": note},
    )

    readback = build_solve_node_readback([node])
    readback_text = repr(readback)

    for leaked in (
        "raw-token",
        "raw-pass",
        "raw-secret",
        "raw-api-key",
        "raw-session",
        "raw-auth",
    ):
        assert leaked not in readback_text
    assert "<redacted>" in readback_text


def test_p3a_solve_node_readback_limit_and_truncation() -> None:
    nodes = [
        SolveNode(id=f"node-{index}", kind=SolveNodeKind.RECON, status=SolveNodeStatus.PLANNED)
        for index in range(3)
    ]

    readback = build_solve_node_readback(nodes, limit=2)

    assert [item["nodeId"] for item in readback["nodes"]] == ["node-1", "node-2"]
    assert readback["summary"]["nodeCount"] == 3
    assert readback["summary"]["exportedNodeCount"] == 2
    assert readback["summary"]["truncatedNodeCount"] == 1
    assert readback["summary"]["statusCounts"] == {"planned": 3}
    assert readback["summary"]["kindCounts"] == {"recon": 3}


def test_p3a_completed_solve_node_does_not_create_proof_fields() -> None:
    node = SolveNode(
        id="node-completed",
        status=SolveNodeStatus.COMPLETED,
        title="Completed plan step",
    )

    payload = solve_node_to_dict(node)
    readback = build_solve_node_readback([node])

    assert payload["status"] == "completed"
    assert payload["claim_ids"] == []
    assert payload["trace_ids"] == []
    assert payload["receipt_ids"] == []
    assert "verificationRecords" not in readback
    assert "verifiedFlags" not in readback
    assert readback["nodes"][0]["status"] == "completed"
