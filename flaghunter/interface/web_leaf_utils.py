"""Leaf utilities split out of web_server (debt ledger 第五波·刀4).

Universally-shared, zero-dependency pure helpers — clock/ISO, text truncation,
string-list normalization, role/tool naming. Extracted FIRST (before themed
cluster cuts) so web_server and every future sibling module import these leaves
from here instead of from web_server — proactively breaking the import cycle that
kept _build_knowledge_usage behind in 刀2. This module imports nothing from
web_server (down-closed leaf layer); web_server re-imports the whole set so that
``web_server._parse_iso`` and stay-behind callers resolve unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _sort_time_key(value: str | None) -> tuple[int, datetime]:
    dt = _parse_iso(value)
    if dt is None:
        return (1, datetime.max.replace(tzinfo=timezone.utc))
    return (0, dt)


def _duration_ms_for_task(task: dict[str, Any]) -> int | None:
    started = _parse_iso(task.get("startedAt"))
    finished = _parse_iso(task.get("finishedAt"))
    duration_ms = task.get("durationMs")
    if duration_ms is not None:
        return duration_ms
    if started and finished:
        return int((finished - started).total_seconds() * 1000)
    if started and task.get("status") == "running":
        return int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    return None


def _message_time_at(task: dict[str, Any], snapshot: dict[str, Any], index: int, total: int) -> str:
    start_dt = _parse_iso(task.get("startedAt") or task.get("createdAt")) or _parse_iso(snapshot.get("created_at")) or datetime.now(timezone.utc)
    end_dt = _parse_iso(snapshot.get("updated_at")) or _parse_iso(task.get("finishedAt")) or start_dt
    if total <= 1 or end_dt <= start_dt:
        return start_dt.isoformat()
    ratio = index / max(total - 1, 1)
    return (start_dt + (end_dt - start_dt) * ratio).isoformat()


def _truncate_text(text: str, limit: int = 1000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _single_line_preview(text: str | None, limit: int = 180) -> str:
    raw = str(text or "").strip()
    if not raw:
        return "no output captured"
    compact = " ".join(raw.split())
    return _truncate_text(compact, limit)


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _friendly_tool_name(name: str) -> str:
    return str(name or "").replace("_", " ").strip() or "unknown"


def _message_role_for(role: str) -> str:
    if role == "assistant":
        return "agent"
    if role == "user":
        return "user"
    return "system"
