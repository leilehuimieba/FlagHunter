"""Guard tests for the N8 attackGraph field on the trace detail payload.

The detailed trace payload re-derives a ShadowGraph from the task's persisted
notes and exposes it under ``attackGraph``. The list view stays lean (no graph).
"""

from __future__ import annotations

import json
from pathlib import Path

from flaghunter.interface import web_server


def _write_notes(project_root: Path) -> None:
    loot = project_root / "loot"
    loot.mkdir(parents=True, exist_ok=True)
    notes = {
        "host-svc": {
            "content": "service found on 10.0.0.1",
            "category": "finding",
            "status": "confirmed",
            "metadata": {
                "target": "10.0.0.1",
                "services": [{"port": 22, "product": "OpenSSH", "protocol": "tcp"}],
            },
        }
    }
    (loot / "notes.json").write_text(json.dumps(notes), encoding="utf-8")


def _task() -> dict:
    return {
        "id": "task-attack-graph-1",
        "currentRunId": "run-attack-graph-1",
        "target": "10.0.0.1",
        "status": "completed",
    }


def test_build_attack_graph_payload_derives_from_task_notes(tmp_path: Path):
    _write_notes(tmp_path)
    graph = web_server._build_attack_graph_payload(tmp_path, _task())

    assert set(graph.keys()) == {"nodes", "edges"}
    node_ids = {n["id"] for n in graph["nodes"]}
    assert "host:10.0.0.1" in node_ids
    assert any(n["type"] == "service" for n in graph["nodes"])
    assert any(e["type"] == "HAS_SERVICE" for e in graph["edges"])


def test_build_attack_graph_payload_no_notes_returns_empty(tmp_path: Path):
    # No loot/notes.json on disk.
    graph = web_server._build_attack_graph_payload(tmp_path, _task())
    assert graph == {"nodes": [], "edges": []}


def test_trace_detail_payload_includes_attack_graph(tmp_path: Path):
    _write_notes(tmp_path)
    payload = web_server._build_trace_payload(tmp_path, _task(), include_timeline=True)

    assert "attackGraph" in payload
    assert set(payload["attackGraph"].keys()) == {"nodes", "edges"}
    assert {n["id"] for n in payload["attackGraph"]["nodes"]} & {"host:10.0.0.1"}


def test_trace_list_payload_omits_attack_graph(tmp_path: Path):
    _write_notes(tmp_path)
    payload = web_server._build_trace_payload(tmp_path, _task(), include_timeline=False)

    # List view must stay lean — no per-task graph derivation.
    assert "attackGraph" not in payload
