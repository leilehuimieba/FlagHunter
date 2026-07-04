from __future__ import annotations

import json

import pytest

from flaghunter.agents.pa_agent.solve_node import (
    SolveNode,
    SolveNodeEdge,
    SolveNodeGraph,
    SolveNodeGraphError,
    SolveNodeStatus,
    build_solve_graph_readback,
    empty_solve_graph_snapshot,
    solve_node_edge_from_dict,
    solve_node_edge_to_dict,
)


def test_p3b_solve_node_edge_default_shape_and_round_trip() -> None:
    edge = SolveNodeEdge(source_id="node-a", target_id="node-b")

    payload = solve_node_edge_to_dict(edge)
    restored = solve_node_edge_from_dict(payload)

    assert payload["source_id"] == "node-a"
    assert payload["target_id"] == "node-b"
    assert payload["relation"] == "depends_on"
    assert isinstance(payload["created_at"], float)
    assert payload["metadata"] == {}
    assert restored.source_id == "node-a"
    assert restored.target_id == "node-b"
    assert restored.relation == "depends_on"
    assert restored.metadata == {}


def test_p3b_edge_restore_unknown_relation_and_future_fields_fallback() -> None:
    restored = solve_node_edge_from_dict(
        {
            "source_id": "node-a",
            "target_id": "node-b",
            "relation": "future_relation",
            "future_field": "ignored",
            "metadata": "not-a-dict",
        }
    )

    assert restored.source_id == "node-a"
    assert restored.target_id == "node-b"
    assert restored.relation == "depends_on"
    assert restored.metadata == {}


def test_p3b_empty_solve_graph_snapshot_is_stable() -> None:
    assert empty_solve_graph_snapshot() == {
        "schemaVersion": "p3.solve_node_graph.v1",
        "nodes": [],
        "edges": [],
        "summary": {
            "nodeCount": 0,
            "edgeCount": 0,
            "exportedNodeCount": 0,
            "exportedEdgeCount": 0,
            "truncatedNodeCount": 0,
            "truncatedEdgeCount": 0,
            "statusCounts": {},
            "kindCounts": {},
            "relationCounts": {},
            "restoreWarningCount": 0,
        },
        "restoreWarnings": [],
    }


def test_p3b_registry_add_node_and_get_node_upserts_by_id() -> None:
    graph = SolveNodeGraph()
    graph.add_node(SolveNode(id="node-a", title="first"))
    graph.add_node(SolveNode(id="node-a", title="second"))

    node = graph.get_node("node-a")

    assert node is not None
    assert node.title == "second"
    assert graph.to_dict()["summary"]["nodeCount"] == 1


def test_p3b_add_edge_happy_path_and_duplicate_is_idempotent() -> None:
    graph = SolveNodeGraph()
    graph.add_node(SolveNode(id="node-a"))
    graph.add_node(SolveNode(id="node-b"))

    first = graph.add_edge("node-a", "node-b", relation="depends_on")
    second = graph.add_edge("node-a", "node-b", relation="depends_on")

    assert first is second
    assert len(graph.edges) == 1
    assert graph.edges[0].source_id == "node-a"
    assert graph.edges[0].target_id == "node-b"
    assert graph.edges[0].relation == "depends_on"


def test_p3b_add_edge_rejects_missing_nodes_and_self_edge() -> None:
    graph = SolveNodeGraph()
    graph.add_node(SolveNode(id="node-a"))

    with pytest.raises(SolveNodeGraphError, match="missing target"):
        graph.add_edge("node-a", "node-b")
    with pytest.raises(SolveNodeGraphError, match="missing source"):
        graph.add_edge("node-b", "node-a")
    with pytest.raises(SolveNodeGraphError, match="self edge"):
        graph.add_edge("node-a", "node-a")


def test_p3b_cycle_guard_rejects_back_edge() -> None:
    graph = SolveNodeGraph()
    for node_id in ("node-a", "node-b", "node-c"):
        graph.add_node(SolveNode(id=node_id))
    graph.add_edge("node-a", "node-b")
    graph.add_edge("node-b", "node-c")

    with pytest.raises(SolveNodeGraphError, match="cycle"):
        graph.add_edge("node-c", "node-a")

    assert len(graph.edges) == 2


def test_p3b_graph_snapshot_serialize_and_restore() -> None:
    graph = SolveNodeGraph()
    graph.add_node(SolveNode(id="node-a", status=SolveNodeStatus.COMPLETED))
    graph.add_node(SolveNode(id="node-b"))
    graph.add_edge("node-a", "node-b", relation="derived_from", metadata={"phase": "recon"})

    restored = SolveNodeGraph.from_dict(graph.to_dict())

    assert restored.get_node("node-a") is not None
    assert restored.get_node("node-a").status is SolveNodeStatus.COMPLETED
    assert len(restored.edges) == 1
    assert restored.edges[0].relation == "derived_from"
    assert restored.edges[0].metadata == {"phase": "recon"}
    assert restored.to_dict()["summary"]["relationCounts"] == {"derived_from": 1}


def test_p3b_restore_skips_invalid_edges_and_records_warnings() -> None:
    graph = SolveNodeGraph.from_dict(
        {
            "nodes": [
                {"id": "node-a"},
                {"id": "node-b"},
            ],
            "edges": [
                {"source_id": "node-a", "target_id": "node-missing"},
                {"source_id": "node-b", "target_id": "node-b"},
                {"source_id": "node-a", "target_id": "node-b"},
                {"source_id": "node-b", "target_id": "node-a"},
            ],
        }
    )

    snapshot = graph.to_dict()

    assert len(graph.edges) == 1
    assert snapshot["summary"]["edgeCount"] == 1
    assert snapshot["summary"]["restoreWarningCount"] == 3
    assert len(snapshot["restoreWarnings"]) == 3


def test_p3b_graph_snapshot_redacts_legacy_restore_warnings() -> None:
    graph = SolveNodeGraph.from_dict(
        {
            "nodes": [{"id": "node-a"}],
            "restoreWarnings": [
                json.dumps({"token": "legacy-warning-token"}),
                "password=legacy-warning-password",
            ],
        }
    )

    snapshot = graph.to_dict()
    snapshot_text = repr(snapshot)

    assert snapshot["summary"]["restoreWarningCount"] == 2
    for leaked in ("legacy-warning-token", "legacy-warning-password"):
        assert leaked not in snapshot_text
    assert "<redacted>" in snapshot_text


def test_p3b_restore_skips_malformed_legacy_edges_without_crashing() -> None:
    graph = SolveNodeGraph.from_dict(
        {
            "nodes": [{"id": "node-a"}],
            "edges": [
                {},
                {
                    "source_id": "node-a",
                    "metadata": {"note": json.dumps({"token": "raw-edge-token"})},
                },
            ],
        }
    )

    snapshot = graph.to_dict()
    text = repr(snapshot)

    assert graph.edges == []
    assert snapshot["summary"]["edgeCount"] == 0
    assert snapshot["summary"]["restoreWarningCount"] == 2
    assert len(snapshot["restoreWarnings"]) == 2
    assert "raw-edge-token" not in text


def test_p3b_constructor_filters_invalid_and_cyclic_edges() -> None:
    graph = SolveNodeGraph(
        nodes_by_id={
            "node-a": SolveNode(id="node-a"),
            "node-b": SolveNode(id="node-b"),
        },
        edges=[
            SolveNodeEdge(source_id="node-b", target_id="node-a"),
            SolveNodeEdge(source_id="node-a", target_id="node-b"),
            SolveNodeEdge(source_id="node-missing", target_id="node-a"),
        ],
    )

    snapshot = graph.to_dict()

    assert [(edge.source_id, edge.target_id) for edge in graph.edges] == [
        ("node-b", "node-a")
    ]
    assert snapshot["summary"]["edgeCount"] == 1
    assert snapshot["summary"]["restoreWarningCount"] == 2


def test_p3b_constructor_indexes_nodes_by_normalized_node_id() -> None:
    graph = SolveNodeGraph(
        nodes_by_id={
            "legacy-key": SolveNode(id="node-a", title="first"),
            "other": SolveNode(id="node-b", title="second"),
        },
        edges=[
            SolveNodeEdge(source_id="node-a", target_id="node-b"),
        ],
    )

    snapshot = graph.to_dict()

    assert sorted(graph.nodes_by_id) == ["node-a", "node-b"]
    assert graph.get_node("node-a") is not None
    assert graph.get_node("node-a").title == "first"
    assert graph.get_node("legacy-key") is None
    assert snapshot["summary"]["nodeCount"] == 2
    assert snapshot["summary"]["edgeCount"] == 1
    assert snapshot["edges"][0]["source_id"] == "node-a"
    assert snapshot["edges"][0]["target_id"] == "node-b"


def test_p3b_constructor_duplicate_normalized_node_ids_upsert_last() -> None:
    graph = SolveNodeGraph(
        nodes_by_id={
            "legacy-first": SolveNode(id="node-a", title="first"),
            "legacy-second": SolveNode(id="node-a", title="second"),
        }
    )

    assert sorted(graph.nodes_by_id) == ["node-a"]
    assert graph.get_node("node-a") is not None
    assert graph.get_node("node-a").title == "second"
    assert graph.to_dict()["summary"]["nodeCount"] == 1


def test_p3b_graph_readback_redacts_node_and_edge_secrets() -> None:
    graph = SolveNodeGraph()
    graph.add_node(
        SolveNode(
            id="node-a",
            title=json.dumps({"token": "node-title-token"}),
            summary=json.dumps({"password": "node-summary-pass"}),
            metadata={"note": json.dumps({"secret": "node-metadata-secret"})},
        )
    )
    graph.add_node(SolveNode(id="node-b"))
    graph.add_edge(
        "node-a",
        "node-b",
        relation="reports_to",
        metadata={
            "target": "http://ctf.local/?token=edge-target-token",
            "note": json.dumps({"api_key": "edge-json-key"}),
            "cookie": "edge-cookie",
        },
    )

    readback = build_solve_graph_readback(graph)
    text = repr(readback)

    for leaked in (
        "node-title-token",
        "node-summary-pass",
        "node-metadata-secret",
        "edge-target-token",
        "edge-json-key",
        "edge-cookie",
    ):
        assert leaked not in text
    assert "<redacted>" in text


def test_p3b_graph_readback_limits_nodes_and_edges() -> None:
    graph = SolveNodeGraph()
    for index in range(4):
        graph.add_node(SolveNode(id=f"node-{index}"))
    graph.add_edge("node-0", "node-1")
    graph.add_edge("node-1", "node-2")
    graph.add_edge("node-2", "node-3")

    readback = build_solve_graph_readback(graph, node_limit=2, edge_limit=1)

    assert [item["nodeId"] for item in readback["nodes"]] == ["node-2", "node-3"]
    assert len(readback["edges"]) == 1
    assert readback["edges"][0]["sourceId"] == "node-2"
    assert readback["edges"][0]["targetId"] == "node-3"
    assert readback["summary"]["nodeCount"] == 4
    assert readback["summary"]["edgeCount"] == 3
    assert readback["summary"]["exportedNodeCount"] == 2
    assert readback["summary"]["exportedEdgeCount"] == 1
    assert readback["summary"]["truncatedNodeCount"] == 2
    assert readback["summary"]["truncatedEdgeCount"] == 2


def test_p3b_completed_nodes_and_edges_do_not_emit_proof_fields() -> None:
    graph = SolveNodeGraph()
    graph.add_node(SolveNode(id="node-a", status=SolveNodeStatus.COMPLETED))
    graph.add_node(SolveNode(id="node-b"))
    graph.add_edge("node-a", "node-b")

    payload = graph.to_dict()
    readback = build_solve_graph_readback(graph)

    assert payload["nodes"][0]["status"] == "completed"
    for forbidden in ("verificationRecords", "verifiedFlags", "proof"):
        assert forbidden not in payload
        assert forbidden not in readback
