"""Operator-facing digest view for Task DAG replay audit readbacks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from .task_dag_replay_audit_readback import (
    TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION,
    TaskDAGReplayAuditReadbackPackage,
    TaskDAGReplayAuditReadbackRow,
    build_task_dag_replay_audit_readback,
)


TASK_DAG_REPLAY_AUDIT_VIEW_SCHEMA_VERSION = "p4e.task_dag_replay_audit_view.v1"
_KINDS = {"timeline", "attention", "warning"}
_SEVERITIES = {"info", "medium", "high"}
_SEVERITY_ORDER = {"high": 0, "medium": 1, "info": 2}
_KIND_ORDER = {"warning": 0, "attention": 1, "timeline": 2}
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
_HIGH_STATUS = {"failed", "blocked", "error"}
_HIGH_DECISION = {"reject_failed", "blocked_or_failed"}
_ATTENTION_DECISION = {
    "manual_review",
    "manual_review_required",
    "retry_task",
    "request_more_evidence",
    "propose_recovery",
    "ready_for_review",
    "reject_failed",
    "blocked_or_failed",
}


@dataclass
class TaskDAGReplayAuditViewItem:
    schema_version: str
    item_id: str
    kind: str
    severity: str
    artifact_type: str
    task_id: str
    source_id: str
    status: str = ""
    decision: str = ""
    title: str = ""
    detail_snippet: str = ""
    warning_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_REPLAY_AUDIT_VIEW_SCHEMA_VERSION
        self.item_id = _preview(self.item_id, limit=160)
        self.kind = _kind(self.kind)
        self.severity = _severity(self.severity)
        self.artifact_type = _preview(
            self.artifact_type or "unknown_compact_artifact",
            limit=80,
        ) or "unknown_compact_artifact"
        self.task_id = _preview(self.task_id, limit=160)
        self.source_id = _preview(self.source_id, limit=160)
        self.status = _preview(self.status, limit=80)
        self.decision = _preview(self.decision, limit=80)
        self.title = _preview(self.title, limit=160)
        self.detail_snippet = _preview(self.detail_snippet, limit=160)
        self.warning_count = _nonnegative_int(self.warning_count)
        self.metadata = _safe_metadata(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "itemId": self.item_id,
            "kind": self.kind,
            "severity": self.severity,
            "artifactType": self.artifact_type,
            "taskId": self.task_id,
            "sourceId": self.source_id,
            "status": self.status,
            "decision": self.decision,
            "title": self.title,
            "detailSnippet": self.detail_snippet,
            "warningCount": self.warning_count,
            "metadata": dict(self.metadata),
        }


@dataclass
class TaskDAGReplayAuditView:
    schema_version: str
    view_id: str
    overview: dict[str, Any] = field(default_factory=dict)
    items: list[TaskDAGReplayAuditViewItem] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)
    source_package_ids: list[str] = field(default_factory=list)
    source_index_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_REPLAY_AUDIT_VIEW_SCHEMA_VERSION
        self.view_id = _preview(self.view_id, limit=160)
        self.overview = _safe_mapping(self.overview)
        self.items = [_coerce_item(item) for item in list(self.items or [])]
        self.summary = _safe_mapping(self.summary)
        self.filters = _safe_mapping(self.filters)
        self.source_package_ids = _safe_refs(self.source_package_ids, limit=20)
        self.source_index_ids = _safe_refs(self.source_index_ids, limit=20)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "viewId": self.view_id,
            "overview": dict(self.overview),
            "items": [item.to_dict() for item in self.items],
            "summary": dict(self.summary),
            "filters": dict(self.filters),
            "sourcePackageIds": list(self.source_package_ids),
            "sourceIndexIds": list(self.source_index_ids),
        }


def build_task_dag_replay_audit_view(
    *,
    readback: Any = None,
    max_items: int = 20,
    kind: str = "",
    severity: str = "",
    artifact_type: str = "",
    task_id: str = "",
    status: str = "",
    decision: str = "",
    has_warnings: bool | None = None,
) -> TaskDAGReplayAuditView:
    normalized = _normalize_inputs(readback)
    items = [_item_from_row(row) for row in normalized["rows"]]
    filtered = _filter_items(
        items,
        kind=kind,
        severity=severity,
        artifact_type=artifact_type,
        task_id=task_id,
        status=status,
        decision=decision,
        has_warnings=has_warnings,
    )
    ordered = sorted(
        filtered,
        key=lambda item: (
            _SEVERITY_ORDER.get(item.severity, 99),
            _KIND_ORDER.get(item.kind, 99),
            item.artifact_type,
            item.task_id,
            item.source_id,
            item.status,
            item.decision,
            item.item_id,
        ),
    )
    normalized_limit = max(0, int(max_items))
    selected = ordered[:normalized_limit] if normalized_limit else []
    filters = {
        "kind": _preview(kind, limit=80),
        "severity": _preview(severity, limit=80),
        "artifactType": _preview(artifact_type, limit=80),
        "taskId": _preview(task_id, limit=160),
        "status": _preview(status, limit=80),
        "decision": _preview(decision, limit=80),
        "hasWarnings": has_warnings,
    }
    overview = {
        "sourcePackageCount": len(normalized["source_package_ids"]),
        "sourceIndexCount": len(normalized["source_index_ids"]),
        "inputRowCount": len(items),
        "exportedItemCount": len(selected),
        "truncatedCount": max(0, len(filtered) - len(selected)),
        "attentionCount": sum(
            1 for item in filtered if item.kind in {"attention", "warning"}
        ),
        "warningCount": sum(item.warning_count for item in filtered),
        "artifactTypeCounts": _counts(item.artifact_type for item in filtered),
        "statusCounts": _counts(item.status for item in filtered),
        "decisionCounts": _counts(item.decision for item in filtered),
        "severityCounts": _counts(item.severity for item in filtered),
        "filters": dict(filters),
    }
    view = TaskDAGReplayAuditView(
        schema_version=TASK_DAG_REPLAY_AUDIT_VIEW_SCHEMA_VERSION,
        view_id="",
        overview=overview,
        items=selected,
        summary=dict(overview),
        filters=filters,
        source_package_ids=normalized["source_package_ids"],
        source_index_ids=normalized["source_index_ids"],
    )
    view.view_id = _view_id(
        view.items,
        view.source_package_ids,
        view.source_index_ids,
        overview,
    )
    return view


def load_task_dag_replay_audit_view_items(
    *,
    readback: Any = None,
    max_items: int = 20,
    kind: str = "",
    severity: str = "",
    artifact_type: str = "",
    task_id: str = "",
    status: str = "",
    decision: str = "",
    has_warnings: bool | None = None,
) -> list[TaskDAGReplayAuditViewItem]:
    return build_task_dag_replay_audit_view(
        readback=readback,
        max_items=max_items,
        kind=kind,
        severity=severity,
        artifact_type=artifact_type,
        task_id=task_id,
        status=status,
        decision=decision,
        has_warnings=has_warnings,
    ).items


def _normalize_inputs(readback: Any) -> dict[str, Any]:
    rows: list[TaskDAGReplayAuditReadbackRow] = []
    source_package_ids: list[str] = []
    source_index_ids: list[str] = []
    for item in _coerce_sequence(readback):
        item_rows, item_package_ids, item_index_ids = _rows_from_input(item)
        rows.extend(item_rows)
        source_package_ids.extend(item_package_ids)
        source_index_ids.extend(item_index_ids)
    return {
        "rows": rows,
        "source_package_ids": _safe_refs(source_package_ids, limit=20),
        "source_index_ids": _safe_refs(source_index_ids, limit=20),
    }


def _rows_from_input(
    value: Any,
) -> tuple[list[TaskDAGReplayAuditReadbackRow], list[str], list[str]]:
    if isinstance(value, TaskDAGReplayAuditReadbackPackage):
        return (
            [_coerce_row(row) for row in list(value.rows or [])],
            _safe_refs([value.package_id], limit=20),
            _safe_refs(value.source_index_ids, limit=20),
        )
    if isinstance(value, TaskDAGReplayAuditReadbackRow):
        return [_coerce_row(value)], [], []
    payload = _payload(value)
    if _is_readback_package_payload(payload):
        package_id = _preview(_get(payload, "packageId", "package_id"), limit=160)
        return (
            [_coerce_row(row) for row in list(payload.get("rows") or [])],
            _safe_refs([package_id], limit=20) if package_id else [],
            _safe_refs(payload.get("sourceIndexIds") or [], limit=20),
        )
    if _is_readback_row_payload(payload):
        return [_coerce_row(payload)], [], []
    package = build_task_dag_replay_audit_readback(audit=value)
    return (
        [_coerce_row(row) for row in package.rows],
        _safe_refs([package.package_id], limit=20),
        _safe_refs(package.source_index_ids, limit=20),
    )


def _item_from_row(row: TaskDAGReplayAuditReadbackRow) -> TaskDAGReplayAuditViewItem:
    kind, severity = _classify(row)
    title = _title(row, kind)
    item = TaskDAGReplayAuditViewItem(
        schema_version=TASK_DAG_REPLAY_AUDIT_VIEW_SCHEMA_VERSION,
        item_id="",
        kind=kind,
        severity=severity,
        artifact_type=row.artifact_type,
        task_id=row.task_id,
        source_id=row.source_id,
        status=row.status,
        decision=row.decision,
        title=title,
        detail_snippet=row.summary_snippet,
        warning_count=row.warning_count,
        metadata=dict(row.metadata),
    )
    item.item_id = _item_id(item)
    return item


def _classify(row: TaskDAGReplayAuditReadbackRow) -> tuple[str, str]:
    status = str(row.status or "")
    decision = str(row.decision or "")
    if status in _HIGH_STATUS or decision in _HIGH_DECISION:
        return "attention", "high"
    if row.warning_count > 0:
        return "warning", "medium"
    if decision in _ATTENTION_DECISION:
        return "attention", "medium"
    return "timeline", "info"


def _title(row: TaskDAGReplayAuditReadbackRow, kind: str) -> str:
    if kind == "warning":
        return row.artifact_type
    if kind == "attention":
        if row.decision:
            return row.decision
        if row.status:
            return row.status
        return "attention"
    return row.artifact_type


def _filter_items(
    items: list[TaskDAGReplayAuditViewItem],
    *,
    kind: str,
    severity: str,
    artifact_type: str,
    task_id: str,
    status: str,
    decision: str,
    has_warnings: bool | None,
) -> list[TaskDAGReplayAuditViewItem]:
    kind_filter = str(kind or "").strip()
    severity_filter = str(severity or "").strip()
    artifact_filter = str(artifact_type or "").strip()
    task_filter = str(task_id or "").strip()
    status_filter = str(status or "").strip()
    decision_filter = str(decision or "").strip()
    result: list[TaskDAGReplayAuditViewItem] = []
    for item in items:
        if kind_filter and item.kind != kind_filter:
            continue
        if severity_filter and item.severity != severity_filter:
            continue
        if artifact_filter and item.artifact_type != artifact_filter:
            continue
        if task_filter and task_filter not in item.task_id:
            continue
        if status_filter and item.status != status_filter:
            continue
        if decision_filter and item.decision != decision_filter:
            continue
        if has_warnings is not None and (item.warning_count > 0) is not bool(has_warnings):
            continue
        result.append(item)
    return result


def _coerce_item(value: Any) -> TaskDAGReplayAuditViewItem:
    if isinstance(value, TaskDAGReplayAuditViewItem):
        return TaskDAGReplayAuditViewItem(
            schema_version=value.schema_version,
            item_id=value.item_id,
            kind=value.kind,
            severity=value.severity,
            artifact_type=value.artifact_type,
            task_id=value.task_id,
            source_id=value.source_id,
            status=value.status,
            decision=value.decision,
            title=value.title,
            detail_snippet=value.detail_snippet,
            warning_count=value.warning_count,
            metadata=dict(value.metadata),
        )
    payload = dict(value or {}) if isinstance(value, dict) else {}
    return TaskDAGReplayAuditViewItem(
        schema_version=str(payload.get("schemaVersion") or ""),
        item_id=str(payload.get("itemId") or ""),
        kind=str(payload.get("kind") or ""),
        severity=str(payload.get("severity") or ""),
        artifact_type=str(payload.get("artifactType") or ""),
        task_id=str(payload.get("taskId") or ""),
        source_id=str(payload.get("sourceId") or ""),
        status=str(payload.get("status") or ""),
        decision=str(payload.get("decision") or ""),
        title=str(payload.get("title") or ""),
        detail_snippet=str(payload.get("detailSnippet") or ""),
        warning_count=_nonnegative_int(payload.get("warningCount")),
        metadata=dict(payload.get("metadata") or {}),
    )


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


def _is_readback_package_payload(payload: dict[str, Any]) -> bool:
    return (
        str(_get(payload, "schemaVersion", "schema_version") or "")
        == TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION
        and isinstance(payload.get("rows"), list)
    )


def _is_readback_row_payload(payload: dict[str, Any]) -> bool:
    return (
        str(_get(payload, "schemaVersion", "schema_version") or "")
        == TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION
        and (
            "rowId" in payload
            or "row_id" in payload
            or "artifactType" in payload
            or "artifact_type" in payload
        )
    )


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        return dict(result or {}) if isinstance(result, dict) else {}
    return {}


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


def _item_id(item: TaskDAGReplayAuditViewItem) -> str:
    seed = "|".join(
        [
            item.kind,
            item.severity,
            item.artifact_type,
            item.task_id,
            item.source_id,
            item.status,
            item.decision,
            item.title,
            item.detail_snippet,
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"task_dag_replay_view_item_{digest}"


def _view_id(
    items: list[TaskDAGReplayAuditViewItem],
    source_package_ids: list[str],
    source_index_ids: list[str],
    overview: dict[str, Any],
) -> str:
    seed = "|".join(
        [
            str(overview.get("sourcePackageCount", 0)),
            str(overview.get("inputRowCount", 0)),
            str(overview.get("exportedItemCount", 0)),
            "|".join(source_package_ids),
            "|".join(source_index_ids),
            "|".join(
                ":".join(
                    [
                        item.item_id,
                        item.kind,
                        item.severity,
                        item.artifact_type,
                        item.task_id,
                        item.source_id,
                    ]
                )
                for item in items
            ),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"task_dag_replay_view_{digest}"


def _kind(value: Any) -> str:
    normalized = str(value or "timeline").strip() or "timeline"
    if normalized not in _KINDS:
        return "timeline"
    return normalized


def _severity(value: Any) -> str:
    normalized = str(value or "info").strip() or "info"
    if normalized not in _SEVERITIES:
        return "info"
    return normalized


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
        r"(?i)\bauthorization\s*=\s*bearer\s+[^\s,;&]+",
        "authorization=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b(token|api[_-]?key|password|secret|session|sessionid|cookie|authorization)\b\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^\s,;&]+)",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)([\"'])(token|api[_-]?key|password|secret|session|sessionid|cookie|authorization)[\"']\s*:\s*([\"'])(.*?)\3",
        r'\1\2\1: \3<redacted>\3',
        text,
    )
    return text


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


def _is_sensitive_key(value: Any) -> bool:
    return bool(
        re.search(
            r"(?i)(token|api[_-]?key|password|secret|session|sessionid|cookie|authorization)",
            str(value or ""),
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


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "").strip()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
