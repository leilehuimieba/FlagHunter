"""Task-detail section builders (messages / plan from snapshot or metrics).

Extracted from web_server.py (god-module 分簇·刀7, 债池第五波). This themed
cluster builds the message / plan sections of a task-detail payload from either
a session snapshot or run metrics. All three are pure builders called only by
the resident `_task_detail_payload`; they are down-closed, calling only the
shared leaf helpers in web_leaf_utils, so they carry no upward dependency on
web_server.
"""

from __future__ import annotations

from typing import Any

from .web_leaf_utils import (
    _message_role_for,
    _message_time_at,
    _now_iso,
    _truncate_text,
)


def _build_messages_from_snapshot(task: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    raw_messages = snapshot.get("conversation") or []
    if not isinstance(raw_messages, list):
        return []
    items: list[dict[str, Any]] = []
    total = len(raw_messages)
    tool_event_index = 0
    for idx, raw in enumerate(raw_messages):
        if not isinstance(raw, dict):
            continue
        t = _message_time_at(task, snapshot, idx, total)
        role = str(raw.get("role") or "system")
        content = str(raw.get("content") or "").strip()
        tool_calls = raw.get("tool_calls") if isinstance(raw.get("tool_calls"), list) else []
        if role in {"user", "assistant", "system"} and (content or tool_calls):
            entry = {
                "id": f"msg_{idx}",
                "role": _message_role_for(role),
                "t": t,
                "content": content or ("tool call issued" if tool_calls else "—"),
            }
            tools = [str(tc.get("name") or "") for tc in tool_calls if isinstance(tc, dict) and tc.get("name")]
            if tools:
                entry["tools"] = tools
            items.append(entry)
        if role == "tool_result":
            tool_results = raw.get("tool_results") if isinstance(raw.get("tool_results"), list) else []
            for result in tool_results:
                if not isinstance(result, dict):
                    continue
                tool_event_index += 1
                tool_name = str(result.get("tool_name") or "tool")
                success = bool(result.get("success", True))
                payload = str(result.get("result") or result.get("error") or "").strip()
                payload = _truncate_text(payload, 1200)
                if not payload:
                    payload = "no output captured"
                items.append({
                    "id": f"tool_{tool_event_index}",
                    "role": "system",
                    "t": t,
                    "content": f"{tool_name} · {'ok' if success else 'failed'}\n{payload}",
                })
    return items


def _build_plan_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    plan = snapshot.get("plan") if isinstance(snapshot.get("plan"), dict) else {}
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    normalized: list[dict[str, Any]] = []
    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        status = str(step.get("status") or "pending")
        state = {
            "complete": "done",
            "skip": "done",
            "fail": "failed",
            "pending": "todo",
        }.get(status, "todo")
        normalized.append({
            "id": step.get("id", idx),
            "label": step.get("description") or f"step {idx}",
            "state": state,
            "status": status,
            "result": step.get("result"),
        })
    if normalized and not any(step["state"] == "active" for step in normalized):
        for step in normalized:
            if step["state"] == "todo":
                step["state"] = "active"
                break
    return normalized


def _build_messages_from_metrics(task: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    started_at = task.get("startedAt") or task.get("createdAt") or _now_iso()
    messages: list[dict[str, Any]] = [{
        "id": "metric_msg_user",
        "role": "user",
        "t": started_at,
        "content": f"{task.get('goal') or ''}\nTarget: {task.get('target') or '—'}".strip(),
    }]
    turns = metrics.get("turns", []) or []
    for turn_idx, turn in enumerate(turns, start=1):
        tool_calls = turn.get("tool_calls", []) or []
        if not tool_calls:
            continue
        tools = [str(name) for name in tool_calls if name]
        messages.append({
            "id": f"metric_msg_{turn_idx}",
            "role": "system",
            "t": _message_time_at(task, {"created_at": started_at, "updated_at": task.get("finishedAt") or started_at}, turn_idx, len(turns) + 1),
            "content": f"iteration {turn.get('iteration', turn_idx)} · observed tools: {', '.join(tools)}",
            "tools": tools,
        })
    if task.get("finishedAt"):
        finish_content = (
            f"flag verified ✓ {task.get('finalFlag')}"
            if task.get("finalFlag")
            else f"task ended · stop_reason={task.get('stopReason') or task.get('status') or 'completed'}"
        )
        messages.append({
            "id": "metric_msg_finish",
            "role": "system",
            "t": task.get("finishedAt"),
            "content": finish_content,
        })
    return messages
