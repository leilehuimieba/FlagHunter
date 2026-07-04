"""Compact read-side Task DAG recovery proposal records."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .task_dag_recovery_proposal import (
    TASK_DAG_RECOVERY_PROPOSAL_SCHEMA_VERSION,
    TaskDAGRecoveryProposal,
)


TASK_DAG_RECOVERY_PROPOSAL_READBACK_SCHEMA_VERSION = (
    "p4c.task_dag_recovery_proposal_readback.v1"
)
_ALLOWED_PROPOSAL_ACTIONS = {"propose_recovery"}
_ALLOWED_RECOMMENDED_ACTIONS = {
    "no_action",
    "retry_task",
    "adjust_inputs",
    "request_more_evidence",
    "mark_blocked",
    "manual_review",
    "propose_new_task",
}
_ALLOWED_PRIORITIES = {"low", "normal", "high"}
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


@dataclass
class TaskDAGRecoveryProposalRecord:
    schema_version: str
    source_schema_version: str
    proposal_id: str
    action: str
    task_id: str
    source_receipt_id: str
    source_status: str
    recovery_reason: str
    recommended_action: str
    confidence: float
    priority: str
    evidence_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    valid: bool = True

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_RECOVERY_PROPOSAL_READBACK_SCHEMA_VERSION
        self.source_schema_version = _preview(self.source_schema_version, limit=160)
        self.proposal_id = _preview(self.proposal_id, limit=160)
        self.action = _preview(self.action, limit=80)
        self.task_id = _preview(self.task_id, limit=160)
        self.source_receipt_id = _preview(self.source_receipt_id, limit=160)
        self.source_status = _preview(self.source_status, limit=80)
        self.recovery_reason = _preview(self.recovery_reason, limit=160)
        self.recommended_action = _recommended_action(self.recommended_action)
        self.confidence = _clamp_float(self.confidence, minimum=0.0, maximum=1.0)
        self.priority = _priority(self.priority)
        self.evidence_refs = _safe_refs(self.evidence_refs, limit=20)
        self.warnings = _safe_refs(self.warnings, limit=10)
        self.metadata = _safe_metadata(self.metadata)
        self.created_at = _coerce_float(self.created_at)
        self.valid = bool(self.valid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "sourceSchemaVersion": self.source_schema_version,
            "proposalId": self.proposal_id,
            "action": self.action,
            "taskId": self.task_id,
            "sourceReceiptId": self.source_receipt_id,
            "sourceStatus": self.source_status,
            "recoveryReason": self.recovery_reason,
            "recommendedAction": self.recommended_action,
            "confidence": self.confidence,
            "priority": self.priority,
            "evidenceRefs": list(self.evidence_refs),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "createdAt": self.created_at,
            "valid": self.valid,
        }


def proposal_to_readback_record(
    proposal: TaskDAGRecoveryProposal | TaskDAGRecoveryProposalRecord | dict[str, Any],
) -> TaskDAGRecoveryProposalRecord:
    return normalize_task_dag_recovery_proposal_record(proposal)


def normalize_task_dag_recovery_proposal_record(
    proposal: TaskDAGRecoveryProposal | TaskDAGRecoveryProposalRecord | dict[str, Any] | None,
) -> TaskDAGRecoveryProposalRecord:
    if isinstance(proposal, TaskDAGRecoveryProposalRecord):
        return TaskDAGRecoveryProposalRecord(**asdict(proposal))
    payload = _payload_from_input(proposal)
    warnings: list[str] = _safe_refs(_get(payload, "warnings"), limit=10)
    source_schema_version = _preview(
        _get(payload, "sourceSchemaVersion", "source_schema_version")
        or _get(payload, "schemaVersion", "schema_version"),
        limit=160,
    )
    proposal_id = _preview(_get(payload, "proposalId", "proposal_id"), limit=160)
    task_id = _preview(_get(payload, "taskId", "task_id"), limit=160)
    action = _preview(_get(payload, "action"), limit=80)
    recommended_action = _recommended_action(
        _get(payload, "recommendedAction", "recommended_action")
    )
    valid = True

    if source_schema_version not in {
        TASK_DAG_RECOVERY_PROPOSAL_SCHEMA_VERSION,
        TASK_DAG_RECOVERY_PROPOSAL_READBACK_SCHEMA_VERSION,
    }:
        valid = False
        warnings.append("invalid_schema")
    if not proposal_id:
        valid = False
        warnings.append("missing_proposal_id")
    if not task_id:
        valid = False
        warnings.append("missing_task_id")
    if action not in _ALLOWED_PROPOSAL_ACTIONS:
        valid = False
        warnings.append("invalid_action")
    if not valid:
        action = "invalid"
        recommended_action = "no_action"

    return TaskDAGRecoveryProposalRecord(
        schema_version=TASK_DAG_RECOVERY_PROPOSAL_READBACK_SCHEMA_VERSION,
        source_schema_version=source_schema_version,
        proposal_id=proposal_id,
        action=action,
        task_id=task_id,
        source_receipt_id=_preview(
            _get(payload, "sourceReceiptId", "source_receipt_id"),
            limit=160,
        ),
        source_status=_preview(_get(payload, "sourceStatus", "source_status"), limit=80),
        recovery_reason=_preview(
            _get(payload, "recoveryReason", "recovery_reason"),
            limit=160,
        ),
        recommended_action=recommended_action,
        confidence=_clamp_float(_get(payload, "confidence"), minimum=0.0, maximum=1.0),
        priority=_priority(_get(payload, "priority")),
        evidence_refs=_safe_refs(_get(payload, "evidenceRefs", "evidence_refs"), limit=20),
        warnings=warnings,
        metadata=_safe_metadata(dict(_get(payload, "metadata") or {})),
        created_at=_coerce_float(_get(payload, "createdAt", "created_at")),
        valid=valid,
    )


def build_task_dag_recovery_proposal_readback(
    proposals: Any,
    *,
    max_records: int = 20,
    task_id: str = "",
    recommended_action: str = "",
    priority: str = "",
) -> dict[str, Any]:
    items = _coerce_sequence(proposals)
    records = [
        normalize_task_dag_recovery_proposal_record(item)
        for item in items
    ]
    filtered = _filter_records(
        records,
        task_id=task_id,
        recommended_action=recommended_action,
        priority=priority,
    )
    ordered = sorted(
        filtered,
        key=lambda item: (item.created_at, item.proposal_id, item.task_id),
    )
    normalized_limit = max(0, int(max_records))
    selected = ordered[:normalized_limit] if normalized_limit else []
    return {
        "schemaVersion": TASK_DAG_RECOVERY_PROPOSAL_READBACK_SCHEMA_VERSION,
        "records": [record.to_dict() for record in selected],
        "summary": {
            "inputCount": len(items),
            "recordCount": len(records),
            "matchedCount": len(filtered),
            "exportedCount": len(selected),
            "truncatedCount": max(0, len(filtered) - len(selected)),
            "invalidCount": sum(1 for record in records if not record.valid),
            "filters": {
                "taskId": _preview(task_id, limit=160),
                "recommendedAction": _preview(recommended_action, limit=80),
                "priority": _preview(priority, limit=80),
            },
        },
    }


def load_task_dag_recovery_proposal_records(
    proposals: Any,
    *,
    max_records: int = 20,
    task_id: str = "",
    recommended_action: str = "",
    priority: str = "",
) -> list[TaskDAGRecoveryProposalRecord]:
    readback = build_task_dag_recovery_proposal_readback(
        proposals,
        max_records=max_records,
        task_id=task_id,
        recommended_action=recommended_action,
        priority=priority,
    )
    return [
        normalize_task_dag_recovery_proposal_record(record)
        for record in readback["records"]
    ]


def _payload_from_input(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, TaskDAGRecoveryProposal):
        return value.to_dict()
    if isinstance(value, dict):
        return dict(value)
    return {}


def _get(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _coerce_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (TaskDAGRecoveryProposal, TaskDAGRecoveryProposalRecord, dict)):
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _filter_records(
    records: list[TaskDAGRecoveryProposalRecord],
    *,
    task_id: str,
    recommended_action: str,
    priority: str,
) -> list[TaskDAGRecoveryProposalRecord]:
    task_filter = str(task_id or "").strip()
    action_filter = str(recommended_action or "").strip()
    priority_filter = str(priority or "").strip()
    result: list[TaskDAGRecoveryProposalRecord] = []
    for record in records:
        if task_filter and task_filter not in record.task_id:
            continue
        if action_filter and record.recommended_action != action_filter:
            continue
        if priority_filter and record.priority != priority_filter:
            continue
        result.append(record)
    return result


def _recommended_action(value: Any) -> str:
    normalized = str(value or "no_action").strip().lower() or "no_action"
    if normalized not in _ALLOWED_RECOMMENDED_ACTIONS:
        return "no_action"
    return normalized


def _priority(value: Any) -> str:
    normalized = str(value or "normal").strip().lower() or "normal"
    if normalized not in _ALLOWED_PRIORITIES:
        return "normal"
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
        key = _preview(raw_key, limit=80)
        if not key or raw_key in _RAW_FIELD_KEYS or raw_key in _PROOF_LIKE_KEYS:
            continue
        if _is_sensitive_key(key):
            safe[key] = "<redacted>"
            continue
        value_limit = 80 if key == "error_class" else 160
        if isinstance(raw_value, bool) or raw_value is None:
            safe[key] = raw_value
        elif isinstance(raw_value, int):
            safe[key] = raw_value
        elif isinstance(raw_value, float):
            safe[key] = _clamp_float(
                raw_value,
                minimum=-1_000_000.0,
                maximum=1_000_000.0,
            )
        else:
            safe[key] = _preview(raw_value, limit=value_limit)
    return safe


def _preview(value: Any, *, limit: int) -> str:
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


def _clamp_float(value: Any, *, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = minimum
    return max(minimum, min(maximum, result))


def _coerce_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
