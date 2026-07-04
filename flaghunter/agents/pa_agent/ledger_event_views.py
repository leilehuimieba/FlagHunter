"""Compact readback for P2 session-ledger events."""

from __future__ import annotations

import re
from typing import Any


P2_LEDGER_EVENT_TYPES = {
    "model_call",
    "state_transition",
    "budget_event",
    "handoff_created",
    "handoff_consumed",
}


def build_p2_ledger_event_readback(
    events: list[dict[str, Any]] | None,
    *,
    limit: int = 10,
) -> dict[str, Any]:
    normalized_limit = max(0, int(limit))
    p2_events = [
        event
        for event in list(events or [])
        if str(event.get("type") or event.get("event_type") or "").strip()
        in P2_LEDGER_EVENT_TYPES
    ][-normalized_limit:]
    refs = [_project_event(event) for event in p2_events]
    refs = [item for item in refs if item]
    counts: dict[str, int] = {}
    for item in refs:
        event_type = str(item.get("type") or "").strip()
        if not event_type:
            continue
        counts[event_type] = counts.get(event_type, 0) + 1
    return {
        "refs": refs,
        "summary": {
            "countsByType": counts,
            "hasModelCall": counts.get("model_call", 0) > 0,
            "hasStateTransition": counts.get("state_transition", 0) > 0,
            "hasBudgetEvent": counts.get("budget_event", 0) > 0,
            "hasHandoff": (
                counts.get("handoff_created", 0) + counts.get("handoff_consumed", 0)
            )
            > 0,
        },
    }


def _project_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("type") or event.get("event_type") or "").strip()
    payload = dict(event.get("payload") or {})
    base = {
        "type": event_type,
        "t": event.get("t") or event.get("ts"),
    }
    if event_type == "model_call":
        return {
            **base,
            "model": _text(payload.get("model")),
            "provider": _text(payload.get("provider")),
            "status": _text(payload.get("status")),
            "durationMs": payload.get("duration_ms"),
            "totalTokens": payload.get("total_tokens"),
        }
    if event_type == "state_transition":
        return {
            **base,
            "fromState": _text(payload.get("from_state")),
            "toState": _text(payload.get("to_state")),
            "source": _text(payload.get("source")),
            "success": payload.get("success"),
        }
    if event_type == "budget_event":
        return {
            **base,
            "budgetName": _text(payload.get("budget_name")),
            "event": _text(payload.get("event")),
            "used": payload.get("used"),
            "limit": payload.get("limit"),
            "remaining": payload.get("remaining"),
            "unit": _text(payload.get("unit")),
            "source": _text(payload.get("source")),
        }
    if event_type == "handoff_created":
        return {
            **base,
            "handoffId": _text(payload.get("handoff_id")),
            "source": _text(payload.get("source")),
            "target": _text(payload.get("target")),
            "decisionKind": _text(payload.get("decision_kind")),
            "nextAction": _text(payload.get("next_action")),
        }
    if event_type == "handoff_consumed":
        return {
            **base,
            "handoffId": _text(payload.get("handoff_id")),
            "consumer": _text(payload.get("consumer")),
            "status": _text(payload.get("status")),
        }
    return {}


def _text(value: Any) -> str:
    return _redact_text(value).strip()[:160]


def _redact_text(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(r"(?im)^\s*set-cookie\s*:.*$", "<redacted>", text)
    text = re.sub(r"(?im)^\s*cookie\s*:.*$", "<redacted>", text)
    text = re.sub(r"(?im)^\s*authorization\s*:.*$", "<redacted>", text)
    text = re.sub(
        r"(?i)\bauthorization\s*:\s*bearer\s+[^\s,;&]+",
        "authorization=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b(token|api[_-]?key|password|secret|session|cookie|authorization)\b\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^\s,;&]+)",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)([\"'](?:token|api[_-]?key|password|secret|session|cookie|authorization)[\"']\s*:\s*)([\"'][^\"']*[\"']|[^,\n\r}\]]+)",
        r'\1"<redacted>"',
        text,
    )
    return text
