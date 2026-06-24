"""Trace / hint / control-event timeline builders.

Extracted from web_server.py (god-module 分簇·刀5, 债池第五波). This themed
cluster builds the per-task trace timeline (tool/hint/control events). It is
down-closed: members call only each other plus the shared leaf helpers in
web_leaf_utils, so it carries no upward dependency on web_server.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .web_leaf_utils import (
    _duration_ms_for_task,
    _friendly_tool_name,
    _now_iso,
    _parse_iso,
    _sort_time_key,
)


def _build_hint_timeline(task: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for idx, raw in enumerate(task.get("hints") or [], start=1):
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "hint accepted").strip() or "hint accepted"
        events.append({
            "id": f"{task['id']}:hint:{idx}",
            "t": str(raw.get("t") or task.get("finishedAt") or task.get("startedAt") or _now_iso()),
            "type": "system",
            "kind": "task.hint",
            "title": "hint accepted",
            "summary": text,
            "status": "done",
            "durationMs": None,
            "tokens": 0,
            "tool": None,
        })
    return events


def _build_control_decision_timeline_event(task: dict[str, Any]) -> dict[str, Any] | None:
    decision = task.get("controlDecision") if isinstance(task.get("controlDecision"), dict) else {}
    active_decision = (
        dict(task.get("blackboardSnapshot", {}).get("activeDecision") or {})
        if isinstance(task.get("blackboardSnapshot"), dict)
        and isinstance(task.get("blackboardSnapshot", {}).get("activeDecision"), dict)
        else {}
    )
    decision_kind = str(decision.get("decisionKind") or "").strip()
    if not decision_kind:
        return None

    event_time = task.get("startedAt") or task.get("createdAt") or _now_iso()
    facts = decision.get("facts") if isinstance(decision.get("facts"), list) else []
    reason = str(decision.get("reason") or "").strip()
    next_action = str(decision.get("nextAction") or "").strip()
    driver = str(decision.get("driver") or "").strip()
    suppressed_recommendation = (
        dict(decision.get("suppressedRecommendation") or {})
        if isinstance(decision.get("suppressedRecommendation"), dict)
        else dict(active_decision.get("suppressedRecommendation") or {})
        if isinstance(active_decision.get("suppressedRecommendation"), dict)
        else {}
    )
    expected_action = str(decision.get("expectedAction") or active_decision.get("expectedAction") or "").strip()
    observed_action = str(decision.get("observedAction") or active_decision.get("observedAction") or "").strip()
    alignment = str(decision.get("alignment") or active_decision.get("alignment") or "").strip()
    alignment_reason = str(
        decision.get("alignmentReason") or active_decision.get("alignmentReason") or ""
    ).strip()

    return {
        "id": f"{task['id']}:decision",
        "t": event_time,
        "type": "decision",
        "kind": f"decision.{decision_kind}",
        "title": "control decision",
        "summary": next_action or decision_kind,
        "status": "done",
        "durationMs": None,
        "tokens": 0,
        "tool": None,
        "driver": driver,
        "input": {
            "reason": reason,
            "facts": facts,
            "nextAction": next_action,
            "expectedAction": expected_action,
            "observedAction": observed_action,
            "alignment": alignment,
            "alignmentReason": alignment_reason,
            "source": "controlDecision",
            "suppressedRecommendation": suppressed_recommendation,
        },
    }


def _build_control_observation_timeline_events(task: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = task.get("ctfStateSnapshot") if isinstance(task.get("ctfStateSnapshot"), dict) else {}
    observations = snapshot.get("observations") if isinstance(snapshot.get("observations"), list) else []
    event_time = task.get("startedAt") or task.get("createdAt") or _now_iso()
    events: list[dict[str, Any]] = []
    supported_kinds = {
        "initial_fact_collection_requested",
        "resume_bootstrap_hint",
    }

    for idx, raw in enumerate(observations, start=1):
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "").strip()
        value = str(raw.get("value") or "").strip()
        source = str(raw.get("source") or "").strip()
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        if kind not in supported_kinds or not value:
            continue
        driver = str(metadata.get("driver") or "").strip()
        reason = str(metadata.get("reason") or "").strip()
        next_action = str(metadata.get("next_action") or "").strip()
        if kind == "resume_bootstrap_hint":
            driver = driver or "blackboard.resume_bootstrap_hint"
            reason = reason or "resume bootstrap hint present in blackboard"
            next_action = next_action or "resume_from_checkpoint"
        events.append({
            "id": f"{task['id']}:observation:{idx}",
            "t": event_time,
            "type": "observation",
            "kind": f"observation.{kind}",
            "title": kind.replace("_", " "),
            "summary": value,
            "status": "done",
            "durationMs": None,
            "tokens": 0,
            "tool": None,
            "driver": driver,
            "input": {
                "source": source,
                "reason": reason,
                "nextAction": next_action,
            },
        })
    return events


def _build_trace_timeline(task: dict[str, Any], metrics: dict[str, Any] | None) -> list[dict[str, Any]]:
    started_at = task.get("startedAt") or task.get("createdAt") or _now_iso()
    start_dt = _parse_iso(started_at) or datetime.now(timezone.utc)
    total_duration = _duration_ms_for_task(task) or int(metrics.get("total_wall_time_ms", 0) if metrics else 0)

    events: list[dict[str, Any]] = [{
        "id": f"{task['id']}:start",
        "t": started_at,
        "type": "task",
        "kind": "task.started",
        "title": "task started",
        "summary": f"target = {task.get('target', '') or '(none)'}",
        "status": "done",
        "durationMs": None,
        "tokens": 0,
        "tool": None,
    }]

    decision_event = _build_control_decision_timeline_event(task)
    if decision_event:
        events.append(decision_event)
    observation_events = _build_control_observation_timeline_events(task)
    if observation_events:
        events.extend(observation_events)

    if metrics:
        elapsed_ms = 0.0
        turns = metrics.get("turns", []) or []
        for turn_idx, turn in enumerate(turns, start=1):
            tool_calls = turn.get("tool_calls", []) or []
            tool_durations = turn.get("tool_durations_ms", []) or []
            tool_success = turn.get("tool_success", []) or []
            turn_tokens = int(turn.get("input_tokens", 0) or 0) + int(turn.get("output_tokens", 0) or 0)
            iteration = turn.get("iteration", turn_idx)

            if not tool_calls:
                continue

            for idx, tool_name in enumerate(tool_calls):
                duration_ms = tool_durations[idx] if idx < len(tool_durations) else None
                success = tool_success[idx] if idx < len(tool_success) else True
                if duration_ms is not None:
                    elapsed_ms += float(duration_ms)
                event_dt = start_dt
                if total_duration > 0:
                    event_dt = start_dt + timedelta(milliseconds=min(elapsed_ms, total_duration))

                event_type = "tool"
                if tool_name == "generate_plan":
                    event_type = "plan"
                elif tool_name in {"notes"}:
                    event_type = "note"
                elif tool_name in {"knowledge_search", "rag", "memory_query"}:
                    event_type = "knowledge"

                events.append({
                    "id": f"{task['id']}:turn{turn_idx}:{idx}",
                    "t": event_dt.isoformat(),
                    "type": event_type,
                    "kind": f"{event_type}.{tool_name}",
                    "title": _friendly_tool_name(tool_name),
                    "summary": f"iteration {iteration} · {'success' if success else 'failed'}",
                    "status": "done" if success else "failed",
                    "durationMs": duration_ms,
                    "tokens": turn_tokens,
                    "tool": tool_name if event_type == "tool" else None,
                })

    if task.get("finalFlag"):
        events.append({
            "id": f"{task['id']}:verified",
            "t": task.get("finishedAt") or _now_iso(),
            "type": "verify",
            "kind": "verifier.flag.verified",
            "title": "flag verified",
            "summary": str(task.get("finalFlag")),
            "status": "done",
            "durationMs": None,
            "tokens": 0,
            "tool": None,
        })
    elif task.get("finishedAt"):
        status = str(task.get("status") or "stopped")
        events.append({
            "id": f"{task['id']}:finish",
            "t": task.get("finishedAt") or _now_iso(),
            "type": "system" if status != "failed" else "err",
            "kind": f"task.{status}",
            "title": f"task {status}",
            "summary": str(task.get("stopReason") or "completed"),
            "status": "done",
            "durationMs": None,
            "tokens": 0,
            "tool": None,
        })

    hint_events = _build_hint_timeline(task)
    if hint_events:
        events.extend(hint_events)
    events.sort(key=lambda event: _sort_time_key(str(event.get("t") or "")))
    return events
