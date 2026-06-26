"""Trace-event extraction from session snapshots (debt ledger 第五波·刀16).

Extracted from web_server.py. This themed cluster turns a task's session
snapshot / session-context into UI trace events: raw tool call/result events
from the conversation, tool-audit events from recentEvents, and rich outcome
events (dispatcher / control-action / verification / checkpoint). Members call
only the shared leaves ``_message_time_at`` / ``_truncate_text`` / ``_now_iso``
(web_leaf_utils) and the already-extracted resume-summary helpers
``_normalize_exploit_provenance`` / ``_normalize_outcome_action_path_summary`` /
``_derive_resume_context_from_latest_checkpoint`` / ``_exploit_summary_parts``
(web_resume_summaries), so the cluster is down-closed with zero upward
dependency on web_server. web_server re-imports the set so stay-behind callers
(``_build_trace_payload`` and the SSE event stream) resolve unchanged.
"""

from __future__ import annotations

import json
from typing import Any

from .web_leaf_utils import _message_time_at, _now_iso, _truncate_text
from .web_resume_summaries import (
    _derive_resume_context_from_latest_checkpoint,
    _exploit_summary_parts,
    _normalize_exploit_provenance,
    _normalize_outcome_action_path_summary,
)


def _extract_tool_events_from_snapshot(task: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    raw_messages = snapshot.get("conversation") or []
    if not isinstance(raw_messages, list):
        return []
    events: list[dict[str, Any]] = []
    total = len(raw_messages)
    pending_calls: list[dict[str, Any]] = []
    for idx, raw in enumerate(raw_messages):
        if not isinstance(raw, dict):
            continue
        t = _message_time_at(task, snapshot, idx, total)
        role = str(raw.get("role") or "")
        if role == "assistant":
            tool_calls = raw.get("tool_calls") if isinstance(raw.get("tool_calls"), list) else []
            pending_calls.extend([
                {
                    "tool": str(tc.get("name") or "tool"),
                    "input": json.dumps(tc.get("arguments") or {}, ensure_ascii=False, indent=2),
                    "t": t,
                }
                for tc in tool_calls if isinstance(tc, dict)
            ])
        elif role == "tool_result":
            tool_results = raw.get("tool_results") if isinstance(raw.get("tool_results"), list) else []
            for result in tool_results:
                if not isinstance(result, dict):
                    continue
                matched = pending_calls.pop(0) if pending_calls else {
                    "tool": str(result.get("tool_name") or "tool"),
                    "input": None,
                    "t": t,
                }
                output = str(result.get("result") or result.get("error") or "").strip()
                events.append({
                    "tool": matched.get("tool"),
                    "input": matched.get("input"),
                    "output": _truncate_text(output or "no output captured", 4000),
                    "success": bool(result.get("success", True)),
                    "durationMs": result.get("duration_ms"),
                    "t": matched.get("t") or t,
                })
    return events


def _extract_tool_audit_events_from_session_context(session_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(session_context, dict):
        return []
    recent_events = session_context.get("recentEvents")
    if not isinstance(recent_events, list):
        return []

    events: list[dict[str, Any]] = []
    for idx, event in enumerate(recent_events, start=1):
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "").strip()
        if event_type not in {"tool_called", "tool_finished"}:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        tool_name = str(payload.get("tool_name") or "tool").strip() or "tool"
        action = str(payload.get("action") or "").strip()
        target = str(payload.get("target") or "").strip()
        summary_bits = [action] if action else []
        if target:
            summary_bits.append(target)
        if event_type == "tool_finished":
            ok = bool(payload.get("ok", True))
            summary_bits.append("ok" if ok else "failed")
        events.append({
            "tool": tool_name,
            "input": json.dumps(payload.get("metadata") or {}, ensure_ascii=False) if event_type == "tool_called" else None,
            "output": None,
            "success": bool(payload.get("ok", True)) if event_type == "tool_finished" else None,
            "durationMs": None,
            "t": str(event.get("t") or _now_iso()),
            "type": "tool",
            "kind": event_type,
            "title": f"{tool_name} {'called' if event_type == 'tool_called' else 'finished'}",
            "summary": " · ".join(summary_bits) if summary_bits else event_type,
            "status": "running" if event_type == "tool_called" else ("done" if payload.get("ok", True) else "failed"),
            "id": f"audit_{event_type}_{idx}",
        })
    return events


def _extract_outcome_events_from_session_context(
    session_context: dict[str, Any] | None,
    exploit_provenance: dict[str, Any] | None = None,
    action_path_summary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(session_context, dict):
        return []
    recent_events = session_context.get("recentEvents")
    if not isinstance(recent_events, list):
        return []
    normalized_exploit_provenance = _normalize_exploit_provenance(exploit_provenance)
    normalized_action_path_summary = _normalize_outcome_action_path_summary(action_path_summary)
    latest_checkpoint = (
        dict(session_context.get("latestCheckpoint") or {})
        if isinstance(session_context.get("latestCheckpoint"), dict)
        else {}
    )
    resume_context = (
        dict(session_context.get("resumeContext") or {})
        if isinstance(session_context.get("resumeContext"), dict)
        else {}
    )
    session_run_id = str(session_context.get("runId") or "").strip()
    effective_resume_context = _derive_resume_context_from_latest_checkpoint(
        session_run_id,
        latest_checkpoint,
        resume_context,
    )

    events: list[dict[str, Any]] = []
    supported_types = {
        "dispatcher_started",
        "control_action_started",
        "control_action_completed",
        "verification_decision",
        "recovery_decision",
        "task_finished",
        "checkpoint_written",
    }
    for idx, event in enumerate(recent_events, start=1):
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "").strip()
        if event_type not in supported_types:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type == "dispatcher_started":
            decision_kind = str(payload.get("decision_kind") or "").strip()
            next_action = str(payload.get("next_action") or "").strip()
            decision_driver = str(payload.get("decision_driver") or "").strip()
            summary_bits = [item for item in [decision_kind, next_action, decision_driver] if item]
            summary_bits.extend(_exploit_summary_parts(normalized_exploit_provenance))
            summary = " · ".join(summary_bits)
            if not summary:
                summary = str(payload.get("requested_type") or "").strip() or event_type
            output_payload = dict(payload)
            if normalized_exploit_provenance:
                output_payload["exploit_provenance"] = normalized_exploit_provenance
            events.append({
                "id": f"outcome_{event_type}_{idx}",
                "type": "system",
                "kind": event_type,
                "title": "dispatcher started",
                "summary": summary,
                "status": "done",
                "t": str(event.get("t") or _now_iso()),
                "output": json.dumps(output_payload, ensure_ascii=False, indent=2),
                "tokens": 0,
            })
            continue
        if event_type in {"control_action_started", "control_action_completed"}:
            action = str(payload.get("action") or "").strip()
            driver = str(payload.get("driver") or "").strip()
            result = str(payload.get("result") or "").strip()
            expected_action = str(payload.get("expected_action") or "").strip()
            alignment = str(payload.get("alignment") or "").strip()
            summary_bits: list[str] = []
            if action:
                summary_bits.append(f"action={action}")
            if expected_action and event_type == "control_action_started":
                summary_bits.append(f"expected={expected_action}")
            if result and event_type == "control_action_completed":
                summary_bits.append(f"result={result}")
            if alignment and event_type == "control_action_started":
                summary_bits.append(f"alignment={alignment}")
            if driver:
                summary_bits.append(f"driver={driver}")
            exploit_summary_parts = _exploit_summary_parts(normalized_exploit_provenance)
            if exploit_summary_parts:
                summary_bits.append("exploit=" + " ".join(exploit_summary_parts))
            summary = " · ".join(summary_bits) or event_type
            output_payload = dict(payload)
            if normalized_exploit_provenance:
                output_payload["exploit_provenance"] = normalized_exploit_provenance
            events.append({
                "id": f"outcome_{event_type}_{idx}",
                "type": "system",
                "kind": event_type,
                "title": "control action started" if event_type == "control_action_started" else "control action completed",
                "summary": summary,
                "status": "done" if event_type == "control_action_started" or result in {"", "ok"} else "failed",
                "t": str(event.get("t") or _now_iso()),
                "output": json.dumps(output_payload, ensure_ascii=False, indent=2),
                "tokens": 0,
            })
            continue
        if event_type == "verification_decision":
            decision = str(payload.get("decision") or "").strip() or "observed"
            flag = str(payload.get("flag") or "").strip()
            rationale = str(payload.get("rationale") or "").strip()
            strategy_kind = str(payload.get("strategy_kind") or "").strip()
            strongest_hypothesis_kind = str(
                normalized_action_path_summary.get("strongestHypothesisKind") or ""
            ).strip()
            summary_bits = [decision]
            if flag:
                summary_bits.append(flag)
            if strategy_kind:
                summary_bits.append(strategy_kind)
            if strongest_hypothesis_kind:
                summary_bits.append(strongest_hypothesis_kind)
            summary_bits.extend(_exploit_summary_parts(normalized_exploit_provenance))
            summary = " · ".join(summary_bits)
            if rationale:
                summary = f"{summary} — {rationale}" if summary else rationale
            output_payload = dict(payload)
            if normalized_exploit_provenance:
                output_payload["exploit_provenance"] = normalized_exploit_provenance
            if normalized_action_path_summary:
                output_payload["action_path_summary"] = normalized_action_path_summary
            events.append({
                "id": f"outcome_{event_type}_{idx}",
                "type": "verify",
                "kind": event_type,
                "title": "verification decision",
                "summary": summary or event_type,
                "status": "failed" if decision == "rejected" else "done",
                "t": str(event.get("t") or _now_iso()),
                "output": json.dumps(output_payload, ensure_ascii=False, indent=2),
                "tokens": 0,
            })
            continue
        if event_type == "recovery_decision":
            action = str(payload.get("action") or "").strip()
            reason = str(payload.get("reason") or "").strip()
            chain_name = str(payload.get("chain_name") or "").strip()
            switched_from = str(normalized_action_path_summary.get("switchedFrom") or "").strip()
            strongest_hypothesis_kind = str(
                normalized_action_path_summary.get("strongestHypothesisKind") or ""
            ).strip()
            summary_bits = [action] if action else []
            if chain_name:
                summary_bits.append(f"chain={chain_name}")
            if switched_from:
                summary_bits.append(f"from={switched_from}")
            if strongest_hypothesis_kind:
                summary_bits.append(f"hypothesis={strongest_hypothesis_kind}")
            exploit_summary_parts = _exploit_summary_parts(normalized_exploit_provenance)
            if exploit_summary_parts:
                summary_bits.append("exploit=" + " ".join(exploit_summary_parts))
            summary = " · ".join(summary_bits)
            if reason:
                summary = f"{summary} — {reason}" if summary else reason
            output_payload = dict(payload)
            if normalized_exploit_provenance:
                output_payload["exploit_provenance"] = normalized_exploit_provenance
            if normalized_action_path_summary:
                output_payload["action_path_summary"] = normalized_action_path_summary
            events.append({
                "id": f"outcome_{event_type}_{idx}",
                "type": "system",
                "kind": event_type,
                "title": "recovery decision",
                "summary": summary or event_type,
                "status": "failed" if bool(payload.get("should_stop")) else "done",
                "t": str(event.get("t") or _now_iso()),
                "output": json.dumps(output_payload, ensure_ascii=False, indent=2),
                "tokens": 0,
            })
            continue
        if event_type == "task_finished":
            reason = str(payload.get("reason") or "").strip()
            chain_used = [str(item).strip() for item in list(payload.get("chain_used") or []) if str(item).strip()]
            missing_tools = [str(item).strip() for item in list(payload.get("missing_tools") or []) if str(item).strip()]
            summary_parts = [reason] if reason else []
            if chain_used:
                summary_parts.append("chain=" + " → ".join(chain_used))
            strongest_hypothesis_kind = str(
                normalized_action_path_summary.get("strongestHypothesisKind") or ""
            ).strip()
            if strongest_hypothesis_kind:
                summary_parts.append("hypothesis=" + strongest_hypothesis_kind)
            exploit_summary_parts = _exploit_summary_parts(normalized_exploit_provenance)
            if exploit_summary_parts:
                summary_parts.append("exploit=" + " ".join(exploit_summary_parts))
            if missing_tools:
                summary_parts.append("missing=" + ", ".join(missing_tools))
            output_payload = dict(payload)
            if normalized_exploit_provenance:
                output_payload["exploit_provenance"] = normalized_exploit_provenance
            if normalized_action_path_summary:
                output_payload["action_path_summary"] = normalized_action_path_summary
            events.append({
                "id": f"outcome_{event_type}_{idx}",
                "type": "system",
                "kind": event_type,
                "title": "task finished",
                "summary": " · ".join(summary_parts) or event_type,
                "status": "done" if bool(payload.get("success")) else "failed",
                "t": str(event.get("t") or _now_iso()),
                "output": json.dumps(output_payload, ensure_ascii=False, indent=2),
                "tokens": 0,
            })
            continue
        label = str(payload.get("label") or latest_checkpoint.get("label") or "").strip()
        checkpoint_id = str(
            payload.get("checkpoint_id")
            or latest_checkpoint.get("checkpointId")
            or effective_resume_context.get("checkpointId")
            or ""
        ).strip()
        stop_reason = str(
            latest_checkpoint.get("stopReason")
            or effective_resume_context.get("stopReason")
            or ""
        ).strip()
        summary_bits: list[str] = []
        if label:
            summary_bits.append(f"label={label}")
        if checkpoint_id:
            summary_bits.append(f"checkpoint={checkpoint_id}")
        if stop_reason:
            summary_bits.append(f"stop={stop_reason}")
        summary = " · ".join(summary_bits) or event_type
        output_payload = dict(payload)
        if session_run_id:
            output_payload["run_id"] = session_run_id
        if checkpoint_id:
            output_payload["checkpoint_id"] = checkpoint_id
        if label:
            output_payload["checkpoint_label"] = label
        if stop_reason:
            output_payload["stop_reason"] = stop_reason
        if latest_checkpoint:
            output_payload["latest_checkpoint"] = latest_checkpoint
        if effective_resume_context:
            output_payload["resume_context"] = effective_resume_context
            resume_summary = str(effective_resume_context.get("summary") or "").strip()
            if resume_summary:
                output_payload["resume_summary"] = resume_summary
        events.append({
            "id": f"outcome_{event_type}_{idx}",
            "type": "system",
            "kind": event_type,
            "title": "checkpoint written",
            "summary": summary,
            "status": "done",
            "t": str(event.get("t") or _now_iso()),
            "output": json.dumps(output_payload, ensure_ascii=False, indent=2),
            "tokens": 0,
        })
    return events
