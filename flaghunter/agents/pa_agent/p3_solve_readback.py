"""Compact read-side P3 solve graph/task/receipt projections."""

from __future__ import annotations

from typing import Any

from .solve_node import (
    build_solve_graph_readback,
    build_solve_node_receipt_readback,
    build_task_brief_readback,
)


SCHEMA_VERSION = "p3.solve_readback.v1"
CREW_TRACE_SCHEMA_VERSION = "p3.crew_trace_readback.v1"


def build_p3_solve_readback(
    state: Any | None,
    *,
    node_limit: int = 20,
    edge_limit: int = 50,
    task_brief_limit: int = 20,
    node_receipt_limit: int = 20,
    preview_limit: int = 160,
) -> dict[str, Any]:
    """Build a bounded read-only P3 planning/execution snapshot."""
    normalized_node_limit = max(0, int(node_limit))
    normalized_edge_limit = max(0, int(edge_limit))
    normalized_task_brief_limit = max(0, int(task_brief_limit))
    normalized_node_receipt_limit = max(0, int(node_receipt_limit))
    normalized_preview_limit = max(1, int(preview_limit))

    graph = build_solve_graph_readback(
        getattr(state, "solve_node_graph", None) if state is not None else None,
        node_limit=normalized_node_limit,
        edge_limit=normalized_edge_limit,
        preview_limit=normalized_preview_limit,
    )
    task_briefs = build_task_brief_readback(
        list(getattr(state, "task_briefs_by_id", {}).values())
        if state is not None
        else [],
        limit=normalized_task_brief_limit,
        preview_limit=normalized_preview_limit,
    )
    receipts = build_solve_node_receipt_readback(
        list(getattr(state, "solve_node_receipts_by_id", {}).values())
        if state is not None
        else [],
        limit=normalized_node_receipt_limit,
        preview_limit=normalized_preview_limit,
    )
    crew_trace = build_p3_crew_trace_readback(
        state,
        worker_limit=normalized_node_receipt_limit,
        node_ref_limit=normalized_node_limit,
        receipt_ref_limit=normalized_node_receipt_limit,
        preview_limit=normalized_preview_limit,
    )

    graph_summary = dict(graph.get("summary") or {})
    task_brief_summary = dict(task_briefs.get("summary") or {})
    receipt_summary = dict(receipts.get("summary") or {})
    crew_summary = dict(crew_trace.get("summary") or {})
    node_count = _int(graph_summary.get("nodeCount"))
    edge_count = _int(graph_summary.get("edgeCount"))
    task_brief_count = _int(task_brief_summary.get("briefCount"))
    receipt_count = _int(receipt_summary.get("receiptCount"))

    return {
        "schemaVersion": SCHEMA_VERSION,
        "solveGraph": graph,
        "taskBriefs": task_briefs,
        "solveNodeReceipts": receipts,
        "crewTrace": crew_trace,
        "summary": {
            "nodeCount": node_count,
            "edgeCount": edge_count,
            "taskBriefCount": task_brief_count,
            "solveNodeReceiptCount": receipt_count,
            "crewWorkerCount": _int(crew_summary.get("workerCount")),
            "crewHandoffCount": _int(crew_summary.get("handoffCount")),
            "crewReceiptCount": _int(crew_summary.get("receiptCount")),
            "hasSolveNodes": node_count > 0,
            "hasTaskBriefs": task_brief_count > 0,
            "hasSolveNodeReceipts": receipt_count > 0,
            "hasCrewTrace": _int(crew_summary.get("workerCount")) > 0
            or _int(crew_summary.get("handoffCount")) > 0,
            "nodeStatusCounts": dict(graph_summary.get("statusCounts") or {}),
            "nodeKindCounts": dict(graph_summary.get("kindCounts") or {}),
            "edgeRelationCounts": dict(graph_summary.get("relationCounts") or {}),
            "receiptStatusCounts": dict(receipt_summary.get("statusCounts") or {}),
            "crewWorkerTypeCounts": dict(
                crew_summary.get("workerTypeCounts") or {}
            ),
            "taskBriefWorkerTypeCounts": dict(
                task_brief_summary.get("workerTypeCounts") or {}
            ),
            "receiptWorkerTypeCounts": dict(
                receipt_summary.get("workerTypeCounts") or {}
            ),
            "truncated": {
                "nodes": _int(graph_summary.get("truncatedNodeCount")),
                "edges": _int(graph_summary.get("truncatedEdgeCount")),
                "taskBriefs": _int(
                    task_brief_summary.get("truncatedBriefCount")
                ),
                "solveNodeReceipts": _int(
                    receipt_summary.get("truncatedReceiptCount")
                ),
            },
        },
    }


def build_p3_crew_trace_readback(
    state: Any | None,
    *,
    worker_limit: int = 20,
    handoff_limit: int = 20,
    node_ref_limit: int = 20,
    receipt_ref_limit: int = 20,
    preview_limit: int = 160,
) -> dict[str, Any]:
    """Aggregate compact worker-facing P3 refs without reading crew internals."""
    normalized_worker_limit = max(0, int(worker_limit))
    normalized_handoff_limit = max(0, int(handoff_limit))
    normalized_node_ref_limit = max(0, int(node_ref_limit))
    normalized_receipt_ref_limit = max(0, int(receipt_ref_limit))
    normalized_preview_limit = max(1, int(preview_limit))

    graph = build_solve_graph_readback(
        getattr(state, "solve_node_graph", None) if state is not None else None,
        node_limit=max(normalized_node_ref_limit, _store_len(state, "solve_node_graph")),
        edge_limit=0,
        preview_limit=normalized_preview_limit,
    )
    task_briefs = build_task_brief_readback(
        list(getattr(state, "task_briefs_by_id", {}).values())
        if state is not None
        else [],
        limit=max(
            normalized_worker_limit,
            normalized_node_ref_limit,
            _store_len(state, "task_briefs_by_id"),
        ),
        preview_limit=normalized_preview_limit,
    )
    receipts = build_solve_node_receipt_readback(
        list(getattr(state, "solve_node_receipts_by_id", {}).values())
        if state is not None
        else [],
        limit=max(
            normalized_receipt_ref_limit,
            normalized_worker_limit,
            _store_len(state, "solve_node_receipts_by_id"),
        ),
        preview_limit=normalized_preview_limit,
    )

    graph_nodes = list(graph.get("nodes") or [])
    receipt_items = list(receipts.get("receipts") or [])
    brief_items = list(task_briefs.get("briefs") or [])
    workers = _worker_refs_from_contracts(receipt_items, brief_items)
    handoffs: list[dict[str, Any]] = []
    node_refs = [_node_ref(item) for item in graph_nodes]
    receipt_refs = [_receipt_ref(item) for item in receipt_items]

    selected_workers = _tail(workers, normalized_worker_limit)
    selected_handoffs = _tail(handoffs, normalized_handoff_limit)
    selected_node_refs = _tail(node_refs, normalized_node_ref_limit)
    selected_receipt_refs = _tail(receipt_refs, normalized_receipt_ref_limit)

    graph_summary = dict(graph.get("summary") or {})
    task_brief_summary = dict(task_briefs.get("summary") or {})
    receipt_summary = dict(receipts.get("summary") or {})

    return {
        "schemaVersion": CREW_TRACE_SCHEMA_VERSION,
        "workers": selected_workers,
        "handoffs": selected_handoffs,
        "nodeRefs": selected_node_refs,
        "receiptRefs": selected_receipt_refs,
        "summary": {
            "workerCount": len(workers),
            "handoffCount": len(handoffs),
            "nodeCount": _int(graph_summary.get("nodeCount")),
            "receiptCount": _int(receipt_summary.get("receiptCount")),
            "workerTypeCounts": _worker_type_counts(workers),
            "receiptStatusCounts": dict(
                receipt_summary.get("statusCounts") or {}
            ),
            "truncated": {
                "workers": max(0, len(workers) - len(selected_workers)),
                "handoffs": max(0, len(handoffs) - len(selected_handoffs)),
                "nodeRefs": max(0, len(node_refs) - len(selected_node_refs)),
                "receiptRefs": max(
                    0,
                    len(receipt_refs) - len(selected_receipt_refs),
                ),
            },
        },
    }


def _worker_refs_from_contracts(
    receipts: list[dict[str, Any]],
    briefs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    workers: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        worker_id = str(receipt.get("workerId") or "").strip()
        worker_type = str(receipt.get("workerType") or "").strip()
        key = worker_id or "|".join(
            [
                worker_type,
                str(receipt.get("nodeId") or "").strip(),
                str(receipt.get("inputBriefId") or "").strip(),
            ]
        )
        if not key.strip():
            continue
        workers[key] = {
            "workerId": worker_id,
            "workerType": worker_type,
            "nodeId": str(receipt.get("nodeId") or "").strip(),
            "inputBriefId": str(receipt.get("inputBriefId") or "").strip(),
            "receiptId": str(receipt.get("receiptId") or "").strip(),
            "status": str(receipt.get("status") or "").strip(),
        }
    for brief in briefs:
        key = "brief:" + str(brief.get("briefId") or "").strip()
        if not key.strip(":"):
            continue
        if any(
            worker.get("inputBriefId") == str(brief.get("briefId") or "").strip()
            for worker in workers.values()
        ):
            continue
        workers[key] = {
            "workerId": "",
            "workerType": str(brief.get("workerType") or "").strip(),
            "nodeId": str(brief.get("nodeId") or "").strip(),
            "inputBriefId": str(brief.get("briefId") or "").strip(),
            "receiptId": "",
            "status": "planned",
        }
    return list(workers.values())


def _node_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "nodeId": str(item.get("nodeId") or "").strip(),
        "kind": str(item.get("kind") or "").strip(),
        "status": str(item.get("status") or "").strip(),
        "titlePreview": str(item.get("titlePreview") or "").strip(),
    }


def _receipt_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "receiptId": str(item.get("receiptId") or "").strip(),
        "nodeId": str(item.get("nodeId") or "").strip(),
        "workerId": str(item.get("workerId") or "").strip(),
        "workerType": str(item.get("workerType") or "").strip(),
        "status": str(item.get("status") or "").strip(),
        "inputBriefId": str(item.get("inputBriefId") or "").strip(),
    }


def _worker_type_counts(workers: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for worker in workers:
        worker_type = str(worker.get("workerType") or "").strip()
        if not worker_type:
            continue
        counts[worker_type] = counts.get(worker_type, 0) + 1
    return counts


def _tail(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    normalized_limit = max(0, int(limit))
    return list(items[-normalized_limit:]) if normalized_limit else []


def _store_len(state: Any | None, attr: str) -> int:
    if state is None:
        return 0
    value = getattr(state, attr, None)
    if attr == "solve_node_graph":
        return len(getattr(value, "nodes_by_id", {}) or {})
    try:
        return len(value or {})
    except TypeError:
        return 0


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
