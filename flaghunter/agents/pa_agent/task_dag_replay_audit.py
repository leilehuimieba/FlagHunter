"""Pure read-side replay audit index for compact Task DAG artifacts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any
from .task_dag_shared import (
    _counts,
    _is_sensitive_key,
    _payload,
    _redact_text,
)


TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION = "p4e.task_dag_replay_audit.v1"
_RECOVERY_PROPOSAL_SCHEMA_VERSION = "p4c.task_dag_recovery_proposal.v1"
_RECOVERY_PROPOSAL_READBACK_SCHEMA_VERSION = (
    "p4c.task_dag_recovery_proposal_readback.v1"
)
_RECOVERY_REVIEW_SCHEMA_VERSION = "p4c.task_dag_recovery_review.v1"
_CREW_PREVIEW_SCHEMA_VERSION = "p4d.task_dag_crew_bridge_preview.v1"
_CREW_HANDOFF_SCHEMA_VERSION = "p4d.task_dag_crew_bridge_handoff.v1"
_CREW_ADMISSION_SCHEMA_VERSION = "p4d.task_dag_crew_bridge_admission.v1"
_RAW_FIELD_KEYS = {
    "stdout",
    "stderr",
    "body",
    "http_body",
    "raw_body",
    "raw_output",
    "prompt",
    "completion",
    "tool_result",
    "tool_results",
    "request",
    "response",
    "full_command",
    "raw_args",
    "command_line",
    "terminal_output",
}
_PROOF_LIKE_KEYS = {
    "verification" + "_decision",
    "verified" + "_flags",
    "verifier" + "Proof",
    "proof" + "_level",
    "verification" + "RecordId",
    "verified" + "Flag",
    "flag" + "_level",
    "flag" + "_verified",
    "verifier" + "_decision",
}
_PROOF_LIKE_VALUE_FRAGMENTS = {
    'level="' + "verified" + '"',
    "level='" + "verified" + "'",
}


@dataclass
class TaskDAGReplayAuditEvent:
    schema_version: str
    event_id: str
    artifact_type: str
    source_schema_version: str
    task_id: str
    source_id: str
    status: str = ""
    decision: str = ""
    summary_snippet: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION
        self.event_id = _preview(self.event_id, limit=160)
        self.artifact_type = _preview(
            self.artifact_type or "unknown_compact_artifact",
            limit=80,
        ) or "unknown_compact_artifact"
        self.source_schema_version = _preview(self.source_schema_version, limit=160)
        self.task_id = _preview(self.task_id, limit=160)
        self.source_id = _preview(self.source_id, limit=160)
        self.status = _preview(self.status, limit=80)
        self.decision = _preview(self.decision, limit=80)
        self.summary_snippet = _preview(self.summary_snippet, limit=160)
        self.evidence_refs = _safe_refs(self.evidence_refs, limit=20)
        self.warnings = _safe_refs(self.warnings, limit=10)
        self.metadata = _safe_metadata(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "eventId": self.event_id,
            "artifactType": self.artifact_type,
            "sourceSchemaVersion": self.source_schema_version,
            "taskId": self.task_id,
            "sourceId": self.source_id,
            "status": self.status,
            "decision": self.decision,
            "summarySnippet": self.summary_snippet,
            "evidenceRefs": list(self.evidence_refs),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass
class TaskDAGReplayAuditIndex:
    schema_version: str
    index_id: str
    events: list[TaskDAGReplayAuditEvent] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION
        self.index_id = _preview(self.index_id, limit=160)
        self.events = [_coerce_event(event) for event in list(self.events or [])]
        self.summary = _safe_mapping(self.summary)
        self.filters = _safe_mapping(self.filters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "indexId": self.index_id,
            "events": [event.to_dict() for event in self.events],
            "summary": dict(self.summary),
            "filters": dict(self.filters),
        }


def build_task_dag_replay_audit_index(
    *,
    artifacts: Any = None,
    max_events: int = 20,
    artifact_type: str = "",
    task_id: str = "",
    status: str = "",
    decision: str = "",
    has_warnings: bool | None = None,
) -> TaskDAGReplayAuditIndex:
    artifact_items = _coerce_sequence(artifacts)
    events: list[TaskDAGReplayAuditEvent] = []
    for artifact in artifact_items:
        events.extend(_events_from_artifact(artifact))
    filtered = _filter_events(
        events,
        artifact_type=artifact_type,
        task_id=task_id,
        status=status,
        decision=decision,
        has_warnings=has_warnings,
    )
    ordered = sorted(
        filtered,
        key=lambda event: (
            event.artifact_type,
            event.task_id,
            event.source_id,
            event.status,
            event.decision,
            event.event_id,
        ),
    )
    normalized_limit = max(0, int(max_events))
    selected = ordered[:normalized_limit] if normalized_limit else []
    filters = {
        "artifactType": _preview(artifact_type, limit=80),
        "taskId": _preview(task_id, limit=160),
        "status": _preview(status, limit=80),
        "decision": _preview(decision, limit=80),
        "hasWarnings": has_warnings,
    }
    summary = {
        "artifactCount": len(artifact_items),
        "eventCount": len(filtered),
        "exportedCount": len(selected),
        "truncatedCount": max(0, len(filtered) - len(selected)),
        "artifactTypeCounts": _counts(event.artifact_type for event in filtered),
        "statusCounts": _counts(event.status for event in filtered),
        "decisionCounts": _counts(event.decision for event in filtered),
        "warningCount": sum(len(event.warnings) for event in filtered),
        "filters": dict(filters),
    }
    index = TaskDAGReplayAuditIndex(
        schema_version=TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION,
        index_id="",
        events=selected,
        summary=summary,
        filters=filters,
    )
    index.index_id = _index_id(index.events, summary)
    return index


def load_task_dag_replay_audit_events(
    *,
    artifacts: Any = None,
    max_events: int = 20,
    artifact_type: str = "",
    task_id: str = "",
    status: str = "",
    decision: str = "",
    has_warnings: bool | None = None,
) -> list[TaskDAGReplayAuditEvent]:
    return build_task_dag_replay_audit_index(
        artifacts=artifacts,
        max_events=max_events,
        artifact_type=artifact_type,
        task_id=task_id,
        status=status,
        decision=decision,
        has_warnings=has_warnings,
    ).events


def _events_from_artifact(artifact: Any) -> list[TaskDAGReplayAuditEvent]:
    payload = _payload(artifact)
    schema_version = str(_get(payload, "schemaVersion", "schema_version") or "")
    if schema_version in {
        _RECOVERY_PROPOSAL_SCHEMA_VERSION,
        _RECOVERY_PROPOSAL_READBACK_SCHEMA_VERSION,
    }:
        return [_recovery_proposal_event(payload, schema_version)]
    if schema_version == _RECOVERY_REVIEW_SCHEMA_VERSION:
        return [_recovery_review_event(payload, schema_version)]
    if schema_version == _CREW_PREVIEW_SCHEMA_VERSION:
        records = list(payload.get("records") or [])
        if records:
            return [_crew_preview_event(item, schema_version) for item in records]
        return [_crew_preview_event(payload, schema_version)]
    if schema_version == _CREW_HANDOFF_SCHEMA_VERSION:
        items = list(payload.get("items") or [])
        if items:
            return [_crew_handoff_event(item, schema_version) for item in items]
        return [_crew_handoff_event(payload, schema_version)]
    if schema_version == _CREW_ADMISSION_SCHEMA_VERSION:
        items = list(payload.get("items") or [])
        if items:
            return [_crew_admission_event(item, schema_version) for item in items]
        return [_crew_admission_event(payload, schema_version)]
    if _looks_like_dag_plan(payload, schema_version):
        return [_generic_event(payload, "dag_plan", schema_version)]
    if _looks_like_dag_receipt(payload, schema_version):
        return [_generic_event(payload, "dag_receipt", schema_version)]
    return [_unknown_event(payload, schema_version)]


def _recovery_proposal_event(
    payload: dict[str, Any],
    schema_version: str,
) -> TaskDAGReplayAuditEvent:
    return _event(
        artifact_type="recovery_proposal",
        source_schema_version=schema_version,
        task_id=_get(payload, "taskId", "task_id"),
        source_id=_get(payload, "proposalId", "proposal_id"),
        status=_get(payload, "sourceStatus", "source_status"),
        decision=_get(payload, "action"),
        summary=_get(payload, "recoveryReason", "recovery_reason"),
        evidence_refs=_get(payload, "evidenceRefs", "evidence_refs"),
        warnings=_get(payload, "warnings"),
        metadata=_metadata(payload),
    )


def _recovery_review_event(
    payload: dict[str, Any],
    schema_version: str,
) -> TaskDAGReplayAuditEvent:
    return _event(
        artifact_type="recovery_review",
        source_schema_version=schema_version,
        task_id=_get(payload, "taskId", "task_id"),
        source_id=_get(payload, "reviewId", "review_id"),
        status="",
        decision=_get(payload, "recommendedAction", "recommended_action"),
        summary=_get(payload, "reviewReason", "review_reason"),
        evidence_refs=_get(payload, "evidenceRefs", "evidence_refs"),
        warnings=_get(payload, "warnings"),
        metadata=_metadata(payload),
    )


def _crew_preview_event(
    payload: Any,
    schema_version: str,
) -> TaskDAGReplayAuditEvent:
    item = _payload(payload)
    return _event(
        artifact_type="crew_bridge_preview",
        source_schema_version=schema_version,
        task_id=_get(item, "taskId", "task_id"),
        source_id=_first_non_empty(
            _get(item, "requestId", "request_id"),
            _get(item, "receiptId", "receipt_id"),
        ),
        status=_get(item, "status"),
        decision="",
        summary=_first_non_empty(
            _get(item, "summarySnippet", "summary_snippet"),
            _get(item, "goalSnippet", "goal_snippet"),
        ),
        evidence_refs=_get(item, "evidenceRefs", "evidence_refs"),
        warnings=_get(item, "warnings"),
        metadata=_metadata(item),
    )


def _crew_handoff_event(
    payload: Any,
    schema_version: str,
) -> TaskDAGReplayAuditEvent:
    item = _payload(payload)
    return _event(
        artifact_type="crew_bridge_handoff",
        source_schema_version=schema_version,
        task_id=_get(item, "taskId", "task_id"),
        source_id=_first_non_empty(
            _get(item, "requestId", "request_id"),
            _get(item, "receiptId", "receipt_id"),
        ),
        status=_get(item, "status"),
        decision=_get(item, "handoffDecision", "handoff_decision"),
        summary=_first_non_empty(
            _get(item, "summarySnippet", "summary_snippet"),
            _get(item, "goalSnippet", "goal_snippet"),
        ),
        evidence_refs=_get(item, "evidenceRefs", "evidence_refs"),
        warnings=_get(item, "warnings"),
        metadata=_metadata(item),
    )


def _crew_admission_event(
    payload: Any,
    schema_version: str,
) -> TaskDAGReplayAuditEvent:
    item = _payload(payload)
    return _event(
        artifact_type="crew_bridge_admission",
        source_schema_version=schema_version,
        task_id=_get(item, "taskId", "task_id"),
        source_id=_first_non_empty(
            _get(item, "requestId", "request_id"),
            _get(item, "receiptId", "receipt_id"),
        ),
        status=_get(item, "status"),
        decision=_get(item, "admissionState", "admission_state"),
        summary=_first_non_empty(
            _get(item, "summarySnippet", "summary_snippet"),
            _get(item, "reason"),
            _get(item, "goalSnippet", "goal_snippet"),
        ),
        evidence_refs=_get(item, "evidenceRefs", "evidence_refs"),
        warnings=_get(item, "warnings"),
        metadata=_metadata(item),
    )


def _generic_event(
    payload: dict[str, Any],
    artifact_type: str,
    schema_version: str,
) -> TaskDAGReplayAuditEvent:
    return _event(
        artifact_type=artifact_type,
        source_schema_version=schema_version,
        task_id=_get(payload, "taskId", "task_id", "id"),
        source_id=_get(payload, "id", "planId", "receiptId", "sourceId"),
        status=_get(payload, "status"),
        decision=_get(payload, "decision", "action"),
        summary=_first_non_empty(
            _get(payload, "summarySnippet", "summary"),
            _get(payload, "goal", "title"),
        ),
        evidence_refs=_get(payload, "evidenceRefs", "traceIds", "claimIds"),
        warnings=_get(payload, "warnings"),
        metadata=_metadata(payload),
    )


def _unknown_event(
    payload: dict[str, Any],
    schema_version: str,
) -> TaskDAGReplayAuditEvent:
    warnings = _safe_refs(_get(payload, "warnings"), limit=10)
    if "unknown_compact_artifact" not in warnings:
        warnings.append("unknown_compact_artifact")
    return _event(
        artifact_type="unknown_compact_artifact",
        source_schema_version=schema_version,
        task_id=_get(payload, "taskId", "task_id"),
        source_id=_first_non_empty(
            _get(payload, "sourceId", "source_id"),
            _get(payload, "id"),
            _get(payload, "eventId", "event_id"),
        ),
        status=_get(payload, "status"),
        decision=_get(payload, "decision", "action"),
        summary=_first_non_empty(
            _get(payload, "summarySnippet", "summary_snippet"),
            _get(payload, "summary"),
        ),
        evidence_refs=_get(payload, "evidenceRefs", "evidence_refs"),
        warnings=warnings,
        metadata=_metadata(payload),
    )


def _event(
    *,
    artifact_type: str,
    source_schema_version: str,
    task_id: Any,
    source_id: Any,
    status: Any,
    decision: Any,
    summary: Any,
    evidence_refs: Any,
    warnings: Any,
    metadata: dict[str, Any],
) -> TaskDAGReplayAuditEvent:
    sanitized = TaskDAGReplayAuditEvent(
        schema_version=TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION,
        event_id="",
        artifact_type=artifact_type,
        source_schema_version=str(source_schema_version or ""),
        task_id=str(task_id or ""),
        source_id=str(source_id or ""),
        status=str(status or ""),
        decision=str(decision or ""),
        summary_snippet=str(summary or ""),
        evidence_refs=_safe_refs(evidence_refs, limit=20),
        warnings=_safe_refs(warnings, limit=10),
        metadata=_safe_metadata(metadata),
    )
    sanitized.event_id = _event_id(sanitized)
    return sanitized


def _filter_events(
    events: list[TaskDAGReplayAuditEvent],
    *,
    artifact_type: str,
    task_id: str,
    status: str,
    decision: str,
    has_warnings: bool | None,
) -> list[TaskDAGReplayAuditEvent]:
    artifact_filter = str(artifact_type or "").strip()
    task_filter = str(task_id or "").strip()
    status_filter = str(status or "").strip()
    decision_filter = str(decision or "").strip()
    result: list[TaskDAGReplayAuditEvent] = []
    for event in events:
        if artifact_filter and event.artifact_type != artifact_filter:
            continue
        if task_filter and task_filter not in event.task_id:
            continue
        if status_filter and event.status != status_filter:
            continue
        if decision_filter and event.decision != decision_filter:
            continue
        if has_warnings is not None and bool(event.warnings) is not bool(has_warnings):
            continue
        result.append(event)
    return result


def _coerce_event(value: Any) -> TaskDAGReplayAuditEvent:
    if isinstance(value, TaskDAGReplayAuditEvent):
        return TaskDAGReplayAuditEvent(
            schema_version=value.schema_version,
            event_id=value.event_id,
            artifact_type=value.artifact_type,
            source_schema_version=value.source_schema_version,
            task_id=value.task_id,
            source_id=value.source_id,
            status=value.status,
            decision=value.decision,
            summary_snippet=value.summary_snippet,
            evidence_refs=list(value.evidence_refs),
            warnings=list(value.warnings),
            metadata=dict(value.metadata),
        )
    payload = dict(value or {}) if isinstance(value, dict) else {}
    return TaskDAGReplayAuditEvent(
        schema_version=str(payload.get("schemaVersion") or ""),
        event_id=str(payload.get("eventId") or ""),
        artifact_type=str(payload.get("artifactType") or ""),
        source_schema_version=str(payload.get("sourceSchemaVersion") or ""),
        task_id=str(payload.get("taskId") or ""),
        source_id=str(payload.get("sourceId") or ""),
        status=str(payload.get("status") or ""),
        decision=str(payload.get("decision") or ""),
        summary_snippet=str(payload.get("summarySnippet") or ""),
        evidence_refs=list(payload.get("evidenceRefs") or []),
        warnings=list(payload.get("warnings") or []),
        metadata=dict(payload.get("metadata") or {}),
    )


def _metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    return dict(metadata or {}) if isinstance(metadata, dict) else {}


def _get(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _coerce_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _looks_like_dag_plan(payload: dict[str, Any], schema_version: str) -> bool:
    text = str(schema_version or "").lower()
    return "task_dag_plan" in text or (
        "nodes" in payload and ("planId" in payload or "plan_id" in payload)
    )


def _looks_like_dag_receipt(payload: dict[str, Any], schema_version: str) -> bool:
    text = str(schema_version or "").lower()
    return "task_dag" in text and "receipt" in text


def _event_id(event: TaskDAGReplayAuditEvent) -> str:
    seed = "|".join(
        [
            event.artifact_type,
            event.source_schema_version,
            event.task_id,
            event.source_id,
            event.status,
            event.decision,
            event.summary_snippet,
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"task_dag_replay_event_{digest}"


def _index_id(events: list[TaskDAGReplayAuditEvent], summary: dict[str, Any]) -> str:
    seed = "|".join(
        [
            str(summary.get("artifactCount", 0)),
            str(summary.get("eventCount", 0)),
            str(summary.get("exportedCount", 0)),
            "|".join(
                ":".join(
                    [
                        event.event_id,
                        event.artifact_type,
                        event.task_id,
                        event.source_id,
                        event.status,
                        event.decision,
                    ]
                )
                for event in events
            ),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"task_dag_replay_audit_{digest}"


def _safe_refs(values: Any, *, limit: int) -> list[str]:
    if values is None:
        items: list[Any] = []
    elif isinstance(values, str):
        items = [values]
    elif isinstance(values, (list, tuple, set)):
        items = list(values)
    else:
        items = []
    refs: list[str] = []
    for item in items:
        text = _preview(item, limit=160)
        if text and text not in refs:
            refs.append(text)
        if len(refs) >= max(0, int(limit)):
            break
    return refs


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for raw_key, raw_value in dict(metadata or {}).items():
        key_text = str(raw_key or "")
        key = _preview(key_text, limit=80)
        if (
            not key
            or key_text in _RAW_FIELD_KEYS
            or _is_proof_like_key(key_text)
            or _contains_proof_like_value(raw_value)
        ):
            continue
        if _is_sensitive_key(key):
            safe[key] = "<redacted>"
            continue
        if isinstance(raw_value, (bool, int, float)) or raw_value is None:
            safe[key] = raw_value
        elif isinstance(raw_value, dict):
            safe[key] = _safe_mapping(raw_value)
        else:
            safe[key] = _preview(raw_value, limit=160)
    return safe


def _safe_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for raw_key, raw_value in dict(mapping or {}).items():
        key = _preview(raw_key, limit=80)
        if not key or str(raw_key or "") in _RAW_FIELD_KEYS or _is_proof_like_key(raw_key):
            continue
        if _is_sensitive_key(key):
            safe[key] = "<redacted>"
            continue
        if isinstance(raw_value, dict):
            safe[key] = _safe_mapping(raw_value)
        elif isinstance(raw_value, (bool, int, float)) or raw_value is None:
            safe[key] = raw_value
        else:
            safe[key] = _preview(raw_value, limit=160)
    return safe


def _preview(value: Any, *, limit: int) -> str:
    if _contains_proof_like_value(value):
        return "<redacted proof-like value>"[: max(0, int(limit))]
    text = _redact_text(value)
    if _looks_like_raw_body(text):
        return "<redacted raw body>"[: max(0, int(limit))]
    return text[: max(0, int(limit))]


def _looks_like_raw_body(text: str) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if len(stripped) > 240 and stripped[:1] in {"{", "["}:
        return True
    return any(
        re.search(pattern, text)
        for pattern in (
            r"(?im)^\s*HTTP/\d(?:\.\d)?\s+\d{3}\b",
            r"(?is)<!doctype\s+html|<html[\s>]",
            r"(?im)^\s*PING\s+",
            r"(?im)^\s*\d+\s+bytes\s+from\s+",
            r"(?im)^\s*uid=\d+\(",
            r"(?im)^\s*gid=\d+\(",
        )
    )


def _is_proof_like_key(value: Any) -> bool:
    text = str(value or "")
    if text in _PROOF_LIKE_KEYS:
        return True
    return _contains_proof_like_value(text)


def _contains_proof_like_value(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float)):
        return False
    if isinstance(value, dict):
        return any(
            _is_proof_like_key(key) or _contains_proof_like_value(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return any(_contains_proof_like_value(item) for item in value)
    text = str(value or "")
    return any(fragment in text for fragment in _PROOF_LIKE_VALUE_FRAGMENTS) or bool(
        re.search(r"(?i)\b(?:flag|ctf)\{[^}\s]{1,160}\}", text)
    )


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
