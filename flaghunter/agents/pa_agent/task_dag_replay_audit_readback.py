"""Read-side report package for Task DAG replay audit indexes."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from .task_dag_replay_audit import (
    TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION,
    TaskDAGReplayAuditEvent,
    TaskDAGReplayAuditIndex,
)
from .task_dag_shared import (
    _counts,
    _is_sensitive_key,
    _nonnegative_int,
    _payload,
    _redact_text,
)


TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION = (
    "p4e.task_dag_replay_audit_readback.v1"
)
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
class TaskDAGReplayAuditReadbackRow:
    schema_version: str
    row_id: str
    artifact_type: str
    task_id: str
    source_id: str
    status: str = ""
    decision: str = ""
    summary_snippet: str = ""
    evidence_ref_count: int = 0
    warning_count: int = 0
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION
        self.row_id = _preview(self.row_id, limit=160)
        self.artifact_type = _preview(
            self.artifact_type or "unknown_compact_artifact",
            limit=80,
        ) or "unknown_compact_artifact"
        self.task_id = _preview(self.task_id, limit=160)
        self.source_id = _preview(self.source_id, limit=160)
        self.status = _preview(self.status, limit=80)
        self.decision = _preview(self.decision, limit=80)
        self.summary_snippet = _preview(self.summary_snippet, limit=160)
        self.evidence_ref_count = _nonnegative_int(self.evidence_ref_count)
        self.warning_count = _nonnegative_int(self.warning_count)
        self.warnings = _safe_refs(self.warnings, limit=10)
        self.metadata = _safe_metadata(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "rowId": self.row_id,
            "artifactType": self.artifact_type,
            "taskId": self.task_id,
            "sourceId": self.source_id,
            "status": self.status,
            "decision": self.decision,
            "summarySnippet": self.summary_snippet,
            "evidenceRefCount": self.evidence_ref_count,
            "warningCount": self.warning_count,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass
class TaskDAGReplayAuditReadbackPackage:
    schema_version: str
    package_id: str
    rows: list[TaskDAGReplayAuditReadbackRow] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)
    source_index_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION
        self.package_id = _preview(self.package_id, limit=160)
        self.rows = [_coerce_row(row) for row in list(self.rows or [])]
        self.summary = _safe_mapping(self.summary)
        self.filters = _safe_mapping(self.filters)
        self.source_index_ids = _safe_refs(self.source_index_ids, limit=20)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "packageId": self.package_id,
            "rows": [row.to_dict() for row in self.rows],
            "summary": dict(self.summary),
            "filters": dict(self.filters),
            "sourceIndexIds": list(self.source_index_ids),
        }


def build_task_dag_replay_audit_readback(
    *,
    audit: Any = None,
    max_rows: int = 20,
    artifact_type: str = "",
    task_id: str = "",
    status: str = "",
    decision: str = "",
    has_warnings: bool | None = None,
) -> TaskDAGReplayAuditReadbackPackage:
    normalized = _normalize_inputs(audit)
    rows = [_row_from_event(event) for event in normalized["events"]]
    filtered = _filter_rows(
        rows,
        artifact_type=artifact_type,
        task_id=task_id,
        status=status,
        decision=decision,
        has_warnings=has_warnings,
    )
    ordered = sorted(
        filtered,
        key=lambda row: (
            row.artifact_type,
            row.task_id,
            row.source_id,
            row.status,
            row.decision,
            row.row_id,
        ),
    )
    normalized_limit = max(0, int(max_rows))
    selected = ordered[:normalized_limit] if normalized_limit else []
    filters = {
        "artifactType": _preview(artifact_type, limit=80),
        "taskId": _preview(task_id, limit=160),
        "status": _preview(status, limit=80),
        "decision": _preview(decision, limit=80),
        "hasWarnings": has_warnings,
    }
    summary = {
        "sourceIndexCount": len(normalized["source_index_ids"]),
        "inputEventCount": len(rows),
        "exportedRowCount": len(selected),
        "truncatedCount": max(0, len(filtered) - len(selected)),
        "artifactTypeCounts": _counts(row.artifact_type for row in filtered),
        "statusCounts": _counts(row.status for row in filtered),
        "decisionCounts": _counts(row.decision for row in filtered),
        "warningCount": sum(row.warning_count for row in filtered),
        "hasWarningsCount": sum(1 for row in filtered if row.warning_count > 0),
        "filters": dict(filters),
    }
    package = TaskDAGReplayAuditReadbackPackage(
        schema_version=TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION,
        package_id="",
        rows=selected,
        summary=summary,
        filters=filters,
        source_index_ids=normalized["source_index_ids"],
    )
    package.package_id = _package_id(package.rows, package.source_index_ids, summary)
    return package


def load_task_dag_replay_audit_readback_rows(
    *,
    audit: Any = None,
    max_rows: int = 20,
    artifact_type: str = "",
    task_id: str = "",
    status: str = "",
    decision: str = "",
    has_warnings: bool | None = None,
) -> list[TaskDAGReplayAuditReadbackRow]:
    return build_task_dag_replay_audit_readback(
        audit=audit,
        max_rows=max_rows,
        artifact_type=artifact_type,
        task_id=task_id,
        status=status,
        decision=decision,
        has_warnings=has_warnings,
    ).rows


def _normalize_inputs(audit: Any) -> dict[str, Any]:
    events: list[TaskDAGReplayAuditEvent] = []
    source_index_ids: list[str] = []
    for item in _coerce_sequence(audit):
        item_events, item_source_ids = _events_from_input(item)
        events.extend(item_events)
        source_index_ids.extend(item_source_ids)
    return {
        "events": events,
        "source_index_ids": _safe_refs(source_index_ids, limit=20),
    }


def _events_from_input(value: Any) -> tuple[list[TaskDAGReplayAuditEvent], list[str]]:
    if isinstance(value, TaskDAGReplayAuditIndex):
        return [
            _coerce_event(event)
            for event in list(value.events or [])
        ], _safe_refs([value.index_id], limit=20)
    if isinstance(value, TaskDAGReplayAuditEvent):
        return [_coerce_event(value)], []
    payload = _payload(value)
    if _is_index_payload(payload):
        index_id = _preview(_get(payload, "indexId", "index_id"), limit=160)
        return [
            _coerce_event(event)
            for event in list(payload.get("events") or [])
        ], _safe_refs([index_id], limit=20) if index_id else []
    if _is_event_payload(payload):
        return [_coerce_event(payload)], []
    return [_invalid_input_event(payload)], []


def _row_from_event(event: TaskDAGReplayAuditEvent) -> TaskDAGReplayAuditReadbackRow:
    warnings = _safe_refs(event.warnings, limit=10)
    row = TaskDAGReplayAuditReadbackRow(
        schema_version=TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION,
        row_id="",
        artifact_type=event.artifact_type,
        task_id=event.task_id,
        source_id=event.source_id,
        status=event.status,
        decision=event.decision,
        summary_snippet=event.summary_snippet,
        evidence_ref_count=len(_safe_refs(event.evidence_refs, limit=20)),
        warning_count=len(warnings),
        warnings=warnings,
        metadata=dict(event.metadata),
    )
    row.row_id = _row_id(row)
    return row


def _invalid_input_event(payload: dict[str, Any]) -> TaskDAGReplayAuditEvent:
    event = TaskDAGReplayAuditEvent(
        schema_version=TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION,
        event_id="",
        artifact_type="unknown_compact_artifact",
        source_schema_version=_preview(
            _get(payload, "schemaVersion", "schema_version"),
            limit=160,
        ),
        task_id=_preview(_get(payload, "taskId", "task_id"), limit=160),
        source_id=_preview(_get(payload, "id", "sourceId", "source_id"), limit=160),
        status=_preview(_get(payload, "status"), limit=80),
        decision=_preview(_get(payload, "decision", "action"), limit=80),
        summary_snippet=_preview(
            _get(payload, "summarySnippet", "summary_snippet", "summary"),
            limit=160,
        ),
        evidence_refs=[],
        warnings=["invalid_replay_audit_input"],
        metadata=_safe_metadata(dict(payload.get("metadata") or {})),
    )
    event.event_id = _event_id(event)
    return event


def _filter_rows(
    rows: list[TaskDAGReplayAuditReadbackRow],
    *,
    artifact_type: str,
    task_id: str,
    status: str,
    decision: str,
    has_warnings: bool | None,
) -> list[TaskDAGReplayAuditReadbackRow]:
    artifact_filter = str(artifact_type or "").strip()
    task_filter = str(task_id or "").strip()
    status_filter = str(status or "").strip()
    decision_filter = str(decision or "").strip()
    result: list[TaskDAGReplayAuditReadbackRow] = []
    for row in rows:
        if artifact_filter and row.artifact_type != artifact_filter:
            continue
        if task_filter and task_filter not in row.task_id:
            continue
        if status_filter and row.status != status_filter:
            continue
        if decision_filter and row.decision != decision_filter:
            continue
        if has_warnings is not None and (row.warning_count > 0) is not bool(has_warnings):
            continue
        result.append(row)
    return result


def _coerce_row(value: Any) -> TaskDAGReplayAuditReadbackRow:
    if isinstance(value, TaskDAGReplayAuditReadbackRow):
        return TaskDAGReplayAuditReadbackRow(
            schema_version=value.schema_version,
            row_id=value.row_id,
            artifact_type=value.artifact_type,
            task_id=value.task_id,
            source_id=value.source_id,
            status=value.status,
            decision=value.decision,
            summary_snippet=value.summary_snippet,
            evidence_ref_count=value.evidence_ref_count,
            warning_count=value.warning_count,
            warnings=list(value.warnings),
            metadata=dict(value.metadata),
        )
    payload = dict(value or {}) if isinstance(value, dict) else {}
    return TaskDAGReplayAuditReadbackRow(
        schema_version=str(payload.get("schemaVersion") or ""),
        row_id=str(payload.get("rowId") or ""),
        artifact_type=str(payload.get("artifactType") or ""),
        task_id=str(payload.get("taskId") or ""),
        source_id=str(payload.get("sourceId") or ""),
        status=str(payload.get("status") or ""),
        decision=str(payload.get("decision") or ""),
        summary_snippet=str(payload.get("summarySnippet") or ""),
        evidence_ref_count=_nonnegative_int(payload.get("evidenceRefCount")),
        warning_count=_nonnegative_int(payload.get("warningCount")),
        warnings=list(payload.get("warnings") or []),
        metadata=dict(payload.get("metadata") or {}),
    )


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


def _is_index_payload(payload: dict[str, Any]) -> bool:
    return (
        str(_get(payload, "schemaVersion", "schema_version") or "")
        == TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION
        and isinstance(payload.get("events"), list)
    )


def _is_event_payload(payload: dict[str, Any]) -> bool:
    return (
        str(_get(payload, "schemaVersion", "schema_version") or "")
        == TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION
        and (
            "eventId" in payload
            or "event_id" in payload
            or "artifactType" in payload
            or "artifact_type" in payload
        )
    )


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


def _row_id(row: TaskDAGReplayAuditReadbackRow) -> str:
    seed = "|".join(
        [
            row.artifact_type,
            row.task_id,
            row.source_id,
            row.status,
            row.decision,
            row.summary_snippet,
            str(row.evidence_ref_count),
            str(row.warning_count),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"task_dag_replay_row_{digest}"


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


def _package_id(
    rows: list[TaskDAGReplayAuditReadbackRow],
    source_index_ids: list[str],
    summary: dict[str, Any],
) -> str:
    seed = "|".join(
        [
            str(summary.get("sourceIndexCount", 0)),
            str(summary.get("inputEventCount", 0)),
            str(summary.get("exportedRowCount", 0)),
            "|".join(source_index_ids),
            "|".join(
                ":".join(
                    [
                        row.row_id,
                        row.artifact_type,
                        row.task_id,
                        row.source_id,
                        row.status,
                        row.decision,
                    ]
                )
                for row in rows
            ),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"task_dag_replay_readback_{digest}"


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

