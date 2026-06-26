"""Knowledge-hit builders (from session snapshot or run metrics).

Extracted from web_server.py (god-module 分簇·刀8, 债池第五波). This themed
cluster reconstructs the knowledge-retrieval timeline of a task — which RAG /
memory tools fired, their queries, scores and result kinds — from either a
session snapshot or the coarser run metrics. Members call only each other, the
cluster-local ``_KNOWLEDGE_TOOLS`` set, and the shared leaf helpers in
web_leaf_utils, so they carry no upward dependency on web_server.
"""

from __future__ import annotations

import re
from typing import Any

from .web_leaf_utils import (
    _message_time_at,
    _now_iso,
    _single_line_preview,
    _truncate_text,
)

_KNOWLEDGE_TOOLS = {"knowledge_search", "rag", "memory_query"}


def _knowledge_result_kind(output: str, success: bool) -> str:
    lower = str(output or "").lower()
    if not success:
        return "failed"
    if "no relevant knowledge found" in lower or "no relevant entries were returned" in lower:
        return "no_match"
    return "matched"


def _parse_knowledge_score(text: str) -> float | None:
    if not text:
        return None
    match = re.search(r"\bscore\b\s*[:=]?\s*(0?\.\d+|1(?:\.0+)?)", text, re.IGNORECASE)
    if not match:
        return None
    try:
        return round(float(match.group(1)), 2)
    except Exception:
        return None


def _build_knowledge_hits_from_snapshot(task: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    raw_messages = snapshot.get("conversation") or []
    if not isinstance(raw_messages, list):
        return []

    hits: list[dict[str, Any]] = []
    pending_searches: list[dict[str, Any]] = []
    total = len(raw_messages)
    hit_idx = 0

    for idx, raw in enumerate(raw_messages):
        if not isinstance(raw, dict):
            continue
        t = _message_time_at(task, snapshot, idx, total)
        role = str(raw.get("role") or "")
        if role == "assistant":
            tool_calls = raw.get("tool_calls") if isinstance(raw.get("tool_calls"), list) else []
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                tool_name = str(tool_call.get("name") or "")
                if tool_name not in _KNOWLEDGE_TOOLS:
                    continue
                arguments = tool_call.get("arguments") if isinstance(tool_call.get("arguments"), dict) else {}
                pending_searches.append({
                    "tool": tool_name,
                    "query": str(arguments.get("query") or "").strip(),
                    "t": t,
                })
        elif role == "tool_result":
            tool_results = raw.get("tool_results") if isinstance(raw.get("tool_results"), list) else []
            for result in tool_results:
                if not isinstance(result, dict):
                    continue
                tool_name = str(result.get("tool_name") or "")
                if tool_name not in _KNOWLEDGE_TOOLS:
                    continue
                pending = pending_searches.pop(0) if pending_searches else {
                    "tool": tool_name,
                    "query": "",
                    "t": t,
                }
                output = str(result.get("result") or result.get("error") or "").strip()
                success = bool(result.get("success", True))
                hit_idx += 1
                chunk_match = re.search(r"chunk[_\s:-]*(\d+)", output, re.IGNORECASE)
                chunk_id = f"chunk_{int(chunk_match.group(1)):03d}" if chunk_match else None
                preview = _single_line_preview(output or pending.get("query") or f"{tool_name} retrieved", 180)
                query = str(pending.get("query") or "").strip()
                result_kind = _knowledge_result_kind(output, success)
                title = query or preview or f"{tool_name} retrieved"
                hits.append({
                    "id": f"knowledge_hit_{hit_idx}",
                    "source": pending.get("tool") or tool_name,
                    "title": title,
                    "query": query or None,
                    "score": _parse_knowledge_score(output),
                    "output": _truncate_text(output, 1600),
                    "preview": preview,
                    "chunkId": chunk_id,
                    "success": success,
                    "resultKind": result_kind,
                    "mode": "session_snapshot",
                    "t": pending.get("t") or t,
                })
    return hits[:16]


def _build_knowledge_hits_from_metrics(task: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    turns = metrics.get("turns", []) or []
    if not isinstance(turns, list):
        return []

    hits: list[dict[str, Any]] = []
    started_at = task.get("startedAt") or task.get("createdAt") or _now_iso()
    timing_snapshot = {
        "created_at": started_at,
        "updated_at": task.get("finishedAt") or started_at,
    }
    for turn_idx, turn in enumerate(turns, start=1):
        if not isinstance(turn, dict):
            continue
        tool_calls = [str(name) for name in (turn.get("tool_calls") or []) if name]
        tool_success = turn.get("tool_success") if isinstance(turn.get("tool_success"), list) else []
        for tool_offset, tool_name in enumerate(tool_calls, start=1):
            if tool_name not in _KNOWLEDGE_TOOLS:
                continue
            success = None
            if tool_offset - 1 < len(tool_success):
                success = bool(tool_success[tool_offset - 1])
            hits.append({
                "id": f"metric_knowledge_{turn_idx}_{tool_offset}_{tool_name}",
                "source": tool_name,
                "title": f"{tool_name} observed in metrics",
                "query": None,
                "score": None,
                "output": "",
                "preview": "query / chunk details unavailable without session snapshot",
                "chunkId": None,
                "success": success,
                "resultKind": "observed_only",
                "mode": "metrics_observed",
                "t": _message_time_at(task, timing_snapshot, turn_idx, len(turns) + 1),
                "iteration": turn.get("iteration", turn_idx),
            })
    return hits[:16]
