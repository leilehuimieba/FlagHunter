"""Pure in-memory facade for Task DAG replay audit view bundles."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from .task_dag_replay_audit import (
    TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION,
    TaskDAGReplayAuditIndex,
    build_task_dag_replay_audit_index,
)
from .task_dag_replay_audit_readback import (
    TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION,
    TaskDAGReplayAuditReadbackPackage,
    build_task_dag_replay_audit_readback,
)
from .task_dag_replay_audit_view import (
    TASK_DAG_REPLAY_AUDIT_VIEW_SCHEMA_VERSION,
    TaskDAGReplayAuditView,
    TaskDAGReplayAuditViewItem,
    build_task_dag_replay_audit_view,
)
from .task_dag_shared import (
    _is_sensitive_key,
    _nonnegative_int,
    _payload,
    _redact_text,
)


TASK_DAG_REPLAY_AUDIT_BUNDLE_SCHEMA_VERSION = "p4e.task_dag_replay_audit_bundle.v1"
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
class TaskDAGReplayAuditBundle:
    schema_version: str
    bundle_id: str
    index: dict[str, Any] = field(default_factory=dict)
    readback: dict[str, Any] = field(default_factory=dict)
    view: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_REPLAY_AUDIT_BUNDLE_SCHEMA_VERSION
        self.bundle_id = _preview(self.bundle_id, limit=160)
        self.index = _safe_mapping(self.index)
        self.readback = _safe_mapping(self.readback)
        self.view = _safe_mapping(self.view)
        self.summary = _safe_mapping(self.summary)
        self.filters = _safe_mapping(self.filters)
        self.warnings = _safe_refs(self.warnings, limit=10)
        self.metadata = _safe_metadata(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "bundleId": self.bundle_id,
            "index": dict(self.index),
            "readback": dict(self.readback),
            "view": dict(self.view),
            "summary": dict(self.summary),
            "filters": dict(self.filters),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def build_task_dag_replay_audit_bundle(
    *,
    artifacts: Any = None,
    index: Any = None,
    readback: Any = None,
    view: Any = None,
    max_events: int = 20,
    max_rows: int = 20,
    max_items: int = 20,
    artifact_type: str = "",
    task_id: str = "",
    status: str = "",
    decision: str = "",
    has_warnings: bool | None = None,
    kind: str = "",
    severity: str = "",
    metadata: dict[str, Any] | None = None,
) -> TaskDAGReplayAuditBundle:
    warnings: list[str] = []
    filters = {
        "artifactType": _preview(artifact_type, limit=80),
        "taskId": _preview(task_id, limit=160),
        "status": _preview(status, limit=80),
        "decision": _preview(decision, limit=80),
        "hasWarnings": has_warnings,
        "kind": _preview(kind, limit=80),
        "severity": _preview(severity, limit=80),
        "maxEvents": _nonnegative_int(max_events),
        "maxRows": _nonnegative_int(max_rows),
        "maxItems": _nonnegative_int(max_items),
    }

    input_items = _coerce_sequence(artifacts)
    has_artifacts = artifacts is not None and bool(input_items)
    has_any_input = any(item is not None for item in (artifacts, index, readback, view))
    if not has_any_input or (artifacts is not None and not input_items and index is None and readback is None and view is None):
        warnings.append("empty_replay_audit_bundle_input")

    index_obj = _coerce_index(index)
    if index_obj is None and readback is None and view is None:
        index_obj = build_task_dag_replay_audit_index(
            artifacts=artifacts,
            max_events=max_events,
            artifact_type=artifact_type,
            task_id=task_id,
            status=status,
            decision=decision,
            has_warnings=has_warnings,
        )
    if index_obj is None:
        index_obj = build_task_dag_replay_audit_index(artifacts=[], max_events=0)
        warnings.append("missing_source_index")

    readback_obj = _coerce_readback(readback)
    if readback_obj is None and view is None:
        readback_obj = build_task_dag_replay_audit_readback(
            audit=index_obj,
            max_rows=max_rows,
            artifact_type=artifact_type,
            task_id=task_id,
            status=status,
            decision=decision,
            has_warnings=has_warnings,
        )
    if readback_obj is None:
        readback_obj = build_task_dag_replay_audit_readback(audit=[], max_rows=0)
        warnings.append("missing_source_readback")

    view_obj = _coerce_view(view)
    if view_obj is None:
        view_obj = build_task_dag_replay_audit_view(
            readback=readback_obj,
            max_items=max_items,
            kind=kind,
            severity=severity,
            artifact_type=artifact_type,
            task_id=task_id,
            status=status,
            decision=decision,
            has_warnings=has_warnings,
        )

    index_payload = index_obj.to_dict()
    readback_payload = readback_obj.to_dict()
    view_payload = view_obj.to_dict()
    summary = _summary(
        artifact_count=len(input_items) if artifacts is not None else 0,
        index_payload=index_payload,
        readback_payload=readback_payload,
        view_payload=view_payload,
        extra_warning_count=len(warnings),
    )
    bundle = TaskDAGReplayAuditBundle(
        schema_version=TASK_DAG_REPLAY_AUDIT_BUNDLE_SCHEMA_VERSION,
        bundle_id="",
        index=index_payload,
        readback=readback_payload,
        view=view_payload,
        summary=summary,
        filters=filters,
        warnings=warnings,
        metadata=_safe_metadata(dict(metadata or {})),
    )
    bundle.bundle_id = _bundle_id(bundle.index, bundle.readback, bundle.view, bundle.summary)
    return bundle


def load_task_dag_replay_audit_bundle_items(
    **kwargs: Any,
) -> list[TaskDAGReplayAuditViewItem]:
    bundle = build_task_dag_replay_audit_bundle(**kwargs).to_dict()
    view_payload = dict(bundle.get("view") or {})
    return [
        TaskDAGReplayAuditViewItem(
            schema_version=str(item.get("schemaVersion") or ""),
            item_id=str(item.get("itemId") or ""),
            kind=str(item.get("kind") or ""),
            severity=str(item.get("severity") or ""),
            artifact_type=str(item.get("artifactType") or ""),
            task_id=str(item.get("taskId") or ""),
            source_id=str(item.get("sourceId") or ""),
            status=str(item.get("status") or ""),
            decision=str(item.get("decision") or ""),
            title=str(item.get("title") or ""),
            detail_snippet=str(item.get("detailSnippet") or ""),
            warning_count=_nonnegative_int(item.get("warningCount")),
            metadata=dict(item.get("metadata") or {}),
        )
        for item in list(view_payload.get("items") or [])
    ]


def _coerce_index(value: Any) -> TaskDAGReplayAuditIndex | None:
    if isinstance(value, TaskDAGReplayAuditIndex):
        return value
    payload = _payload(value)
    if str(payload.get("schemaVersion") or "") != TASK_DAG_REPLAY_AUDIT_SCHEMA_VERSION:
        return None
    return TaskDAGReplayAuditIndex(
        schema_version=str(payload.get("schemaVersion") or ""),
        index_id=str(payload.get("indexId") or ""),
        events=list(payload.get("events") or []),
        summary=dict(payload.get("summary") or {}),
        filters=dict(payload.get("filters") or {}),
    )


def _coerce_readback(value: Any) -> TaskDAGReplayAuditReadbackPackage | None:
    if isinstance(value, TaskDAGReplayAuditReadbackPackage):
        return value
    payload = _payload(value)
    if str(payload.get("schemaVersion") or "") != TASK_DAG_REPLAY_AUDIT_READBACK_SCHEMA_VERSION:
        return None
    return TaskDAGReplayAuditReadbackPackage(
        schema_version=str(payload.get("schemaVersion") or ""),
        package_id=str(payload.get("packageId") or ""),
        rows=list(payload.get("rows") or []),
        summary=dict(payload.get("summary") or {}),
        filters=dict(payload.get("filters") or {}),
        source_index_ids=list(payload.get("sourceIndexIds") or []),
    )


def _coerce_view(value: Any) -> TaskDAGReplayAuditView | None:
    if isinstance(value, TaskDAGReplayAuditView):
        return value
    payload = _payload(value)
    if str(payload.get("schemaVersion") or "") != TASK_DAG_REPLAY_AUDIT_VIEW_SCHEMA_VERSION:
        return None
    return TaskDAGReplayAuditView(
        schema_version=str(payload.get("schemaVersion") or ""),
        view_id=str(payload.get("viewId") or ""),
        overview=dict(payload.get("overview") or {}),
        items=list(payload.get("items") or []),
        summary=dict(payload.get("summary") or {}),
        filters=dict(payload.get("filters") or {}),
        source_package_ids=list(payload.get("sourcePackageIds") or []),
        source_index_ids=list(payload.get("sourceIndexIds") or []),
    )


def _summary(
    *,
    artifact_count: int,
    index_payload: dict[str, Any],
    readback_payload: dict[str, Any],
    view_payload: dict[str, Any],
    extra_warning_count: int,
) -> dict[str, Any]:
    index_summary = dict(index_payload.get("summary") or {})
    readback_summary = dict(readback_payload.get("summary") or {})
    view_overview = dict(view_payload.get("overview") or {})
    return {
        "artifactCount": _nonnegative_int(
            index_summary.get("artifactCount", artifact_count)
        ),
        "indexEventCount": len(list(index_payload.get("events") or [])),
        "readbackRowCount": len(list(readback_payload.get("rows") or [])),
        "viewItemCount": len(list(view_payload.get("items") or [])),
        "truncatedCount": (
            _nonnegative_int(index_summary.get("truncatedCount"))
            + _nonnegative_int(readback_summary.get("truncatedCount"))
            + _nonnegative_int(view_overview.get("truncatedCount"))
        ),
        "warningCount": (
            _nonnegative_int(view_overview.get("warningCount"))
            + extra_warning_count
        ),
        "attentionCount": _nonnegative_int(view_overview.get("attentionCount")),
        "sourceIndexCount": _nonnegative_int(view_overview.get("sourceIndexCount")),
        "sourcePackageCount": _nonnegative_int(view_overview.get("sourcePackageCount")),
    }


def _bundle_id(
    index_payload: dict[str, Any],
    readback_payload: dict[str, Any],
    view_payload: dict[str, Any],
    summary: dict[str, Any],
) -> str:
    seed = "|".join(
        [
            str(index_payload.get("indexId") or ""),
            str(readback_payload.get("packageId") or ""),
            str(view_payload.get("viewId") or ""),
            str(summary.get("artifactCount", 0)),
            str(summary.get("indexEventCount", 0)),
            str(summary.get("readbackRowCount", 0)),
            str(summary.get("viewItemCount", 0)),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"task_dag_replay_bundle_{digest}"


def _coerce_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


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
        elif isinstance(raw_value, list):
            safe[key] = [
                _safe_mapping(item) if isinstance(item, dict) else _preview(item, limit=160)
                for item in raw_value[:20]
            ]
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

