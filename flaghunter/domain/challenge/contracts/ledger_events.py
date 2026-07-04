from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list
from .sanitization import redact_sensitive_text


SCHEMA_VERSION = "p2.ledger_event_readback.v1"
LEDGER_EVENT_TYPES = {
    "model_call",
    "state_transition",
    "budget_event",
    "handoff_created",
    "handoff_consumed",
}


@dataclass(frozen=True)
class LedgerEventReadback:
    refs: list[JsonValue] = field(default_factory=list)
    summary: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "refs": coerce_json_list(self.refs),
            "summary": coerce_json_dict(self.summary),
        }

    def to_legacy_dict(self) -> dict[str, JsonValue]:
        return {
            "refs": coerce_json_list(self.refs),
            "summary": coerce_json_dict(self.summary),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LedgerEventReadback":
        return cls(
            refs=coerce_json_list(payload.get("refs")),
            summary=coerce_json_dict(payload.get("summary")),
        )


def build_ledger_event_readback(
    events: list[dict[str, Any]] | None,
    *,
    limit: int = 10,
) -> dict[str, JsonValue]:
    normalized_limit = max(0, int(limit))
    p2_events = [
        event
        for event in list(events or [])
        if str(event.get("type") or event.get("event_type") or "").strip()
        in LEDGER_EVENT_TYPES
    ][-normalized_limit:]
    refs = [_project_event(event) for event in p2_events]
    refs = [item for item in refs if item]
    counts: dict[str, int] = {}
    for item in refs:
        event_type = str(item.get("type") or "").strip()
        if not event_type:
            continue
        counts[event_type] = counts.get(event_type, 0) + 1
    return LedgerEventReadback(
        refs=refs,
        summary={
            "countsByType": counts,
            "hasModelCall": counts.get("model_call", 0) > 0,
            "hasStateTransition": counts.get("state_transition", 0) > 0,
            "hasBudgetEvent": counts.get("budget_event", 0) > 0,
            "hasHandoff": (
                counts.get("handoff_created", 0)
                + counts.get("handoff_consumed", 0)
            )
            > 0,
        },
    ).to_legacy_dict()


def _project_event(event: dict[str, Any]) -> dict[str, JsonValue]:
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
    return redact_sensitive_text(value).strip()[:160]
