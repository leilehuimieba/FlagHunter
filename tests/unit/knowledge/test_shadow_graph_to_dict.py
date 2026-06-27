"""Guard tests for ShadowGraph.to_dict() structured serialization (N8 backend).

to_dict() is the single structured view of the graph; to_mermaid() renders from
the same view, so the two must never diverge.
"""

from flaghunter.knowledge.graph import ShadowGraph


def _host_service_notes() -> dict:
    """Notes producing host + service nodes and a HAS_SERVICE edge."""
    return {
        "svc-note": {
            "content": "open service on host",
            "category": "finding",
            "status": "confirmed",
            "metadata": {
                "target": "10.0.0.1",
                "services": [
                    {
                        "port": 22,
                        "product": "OpenSSH",
                        "version": "8.0",
                        "protocol": "tcp",
                    }
                ],
            },
        }
    }


def test_to_dict_empty_graph():
    graph = ShadowGraph()
    assert graph.to_dict() == {"nodes": [], "edges": []}


def test_to_dict_single_node_no_edges():
    notes = {
        "host-note": {
            "content": "host discovered",
            "category": "finding",
            "status": "confirmed",
            "metadata": {"target": "10.0.0.1"},
        }
    }
    graph = ShadowGraph()
    graph.update_from_notes(notes)

    data = graph.to_dict()
    assert data["edges"] == []
    assert len(data["nodes"]) == 1

    node = data["nodes"][0]
    assert node["id"] == "host:10.0.0.1"
    assert node["type"] == "host"
    assert node["label"] == "10.0.0.1"
    assert node["metadata"] == {}


def test_to_dict_nodes_and_edges_carry_metadata():
    graph = ShadowGraph()
    graph.update_from_notes(_host_service_notes())

    data = graph.to_dict()
    nodes_by_id = {n["id"]: n for n in data["nodes"]}

    # Host + service nodes present.
    assert "host:10.0.0.1" in nodes_by_id
    service_id = "service:host:10.0.0.1:22"
    assert service_id in nodes_by_id

    # Service node carries structured metadata (extra NetworkX attrs).
    service = nodes_by_id[service_id]
    assert service["type"] == "service"
    assert service["metadata"]["product"] == "OpenSSH"
    assert service["metadata"]["version"] == "8.0"

    # One HAS_SERVICE edge with protocol metadata.
    assert len(data["edges"]) == 1
    edge = data["edges"][0]
    assert edge["source"] == "host:10.0.0.1"
    assert edge["target"] == service_id
    assert edge["type"] == "HAS_SERVICE"
    assert edge["metadata"]["protocol"] == "tcp"


def test_to_dict_is_json_serializable():
    import json

    graph = ShadowGraph()
    graph.update_from_notes(_host_service_notes())
    # Must round-trip through JSON without raising.
    restored = json.loads(json.dumps(graph.to_dict()))
    assert set(restored.keys()) == {"nodes", "edges"}


def test_to_mermaid_renders_from_same_view_as_to_dict():
    graph = ShadowGraph()
    notes = _host_service_notes()
    # Add a credential note so the graph spans multiple node/edge types.
    notes["cred-note"] = {
        "content": "creds for box",
        "category": "credential",
        "status": "confirmed",
        "metadata": {"target": "10.0.0.1", "username": "admin", "protocol": "ssh"},
    }
    graph.update_from_notes(notes)

    data = graph.to_dict()
    mermaid = graph.to_mermaid()
    lines = mermaid.splitlines()

    # Header + one line per node + one line per edge: proves single source.
    assert lines[0] == "graph TD"
    assert len(lines) == 1 + len(data["nodes"]) + len(data["edges"])

    # Every node label and every edge type label surfaces in the mermaid text.
    for node in data["nodes"]:
        assert str(node["label"]) in mermaid
    for edge in data["edges"]:
        assert edge["type"] in mermaid
