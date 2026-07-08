"""Pure review envelope for Task DAG recovery proposal records."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .task_dag_recovery_proposal import TaskDAGRecoveryProposal
from .task_dag_recovery_proposal_readback import (
    TaskDAGRecoveryProposalRecord,
    normalize_task_dag_recovery_proposal_record,
)
from .task_dag_shared import (
    _clamp_float,
    _is_sensitive_key,
    _redact_text,
)


TASK_DAG_RECOVERY_REVIEW_SCHEMA_VERSION = "p4c.task_dag_recovery_review.v1"
_ALLOWED_RECOMMENDED_ACTIONS = {
    "no_action",
    "retry_task",
    "adjust_inputs",
    "request_more_evidence",
    "mark_blocked",
    "manual_review",
    "propose_new_task",
}
_ALLOWED_ATTENTION = {"none", "review", "urgent"}
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
_ACTION_WEIGHTS = {
    "manual_review": 80,
    "mark_blocked": 75,
    "adjust_inputs": 65,
    "propose_new_task": 60,
    "request_more_evidence": 50,
    "retry_task": 40,
    "no_action": 0,
}
_PRIORITY_WEIGHTS = {"high": 300, "normal": 200, "low": 100}


@dataclass
class TaskDAGRecoveryReview:
    schema_version: str
    review_id: str
    selected_proposal_id: str
    task_id: str
    review_reason: str
    recommended_action: str
    attention: str
    confidence: float
    evidence_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    valid: bool = True
    summary: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_RECOVERY_REVIEW_SCHEMA_VERSION
        self.review_id = _preview(self.review_id, limit=160)
        self.selected_proposal_id = _preview(self.selected_proposal_id, limit=160)
        self.task_id = _preview(self.task_id, limit=160)
        self.review_reason = _preview(self.review_reason, limit=160)
        self.recommended_action = _recommended_action(self.recommended_action)
        self.attention = _attention(self.attention)
        self.confidence = _clamp_float(self.confidence, minimum=0.0, maximum=1.0)
        self.evidence_refs = _safe_refs(self.evidence_refs, limit=20)
        self.warnings = _safe_refs(self.warnings, limit=10)
        self.metadata = _safe_metadata(self.metadata)
        self.valid = bool(self.valid)
        self.summary = _safe_summary(self.summary)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "reviewId": self.review_id,
            "selectedProposalId": self.selected_proposal_id,
            "taskId": self.task_id,
            "reviewReason": self.review_reason,
            "recommendedAction": self.recommended_action,
            "attention": self.attention,
            "confidence": self.confidence,
            "evidenceRefs": list(self.evidence_refs),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "valid": self.valid,
            "summary": dict(self.summary),
        }


def select_task_dag_recovery_proposal(
    proposals: Any,
) -> TaskDAGRecoveryReview:
    return build_task_dag_recovery_review(proposals)


def build_task_dag_recovery_review(
    proposals: Any,
) -> TaskDAGRecoveryReview:
    records = [
        normalize_task_dag_recovery_proposal_record(item)
        for item in _coerce_sequence(proposals)
    ]
    valid_records = [record for record in records if record.valid]
    invalid_count = len(records) - len(valid_records)
    if not records:
        warnings = ["no_recovery_proposals"]
        return _review(
            selected=None,
            records=records,
            valid_count=0,
            invalid_count=0,
            review_reason="no_recovery_proposals",
            recommended_action="no_action",
            attention="none",
            confidence=0.0,
            warnings=warnings,
        )
    if not valid_records:
        warnings = ["no_valid_recovery_proposals"]
        return _review(
            selected=None,
            records=records,
            valid_count=0,
            invalid_count=invalid_count,
            review_reason="no_valid_recovery_proposals",
            recommended_action="no_action",
            attention="review",
            confidence=0.0,
            warnings=warnings,
        )

    selected = sorted(valid_records, key=_selection_key)[0]
    return _review(
        selected=selected,
        records=records,
        valid_count=len(valid_records),
        invalid_count=invalid_count,
        review_reason=_review_reason(selected),
        recommended_action=selected.recommended_action,
        attention=_attention_for_record(selected),
        confidence=selected.confidence,
        warnings=list(selected.warnings),
    )


def _review(
    *,
    selected: TaskDAGRecoveryProposalRecord | None,
    records: list[TaskDAGRecoveryProposalRecord],
    valid_count: int,
    invalid_count: int,
    review_reason: str,
    recommended_action: str,
    attention: str,
    confidence: float,
    warnings: list[str],
) -> TaskDAGRecoveryReview:
    summary = {
        "inputCount": len(records),
        "validCount": int(valid_count),
        "invalidCount": int(invalid_count),
        "candidateCount": int(valid_count),
        "selectedScore": _score(selected) if selected is not None else 0,
    }
    selected_id = selected.proposal_id if selected is not None else ""
    return TaskDAGRecoveryReview(
        schema_version=TASK_DAG_RECOVERY_REVIEW_SCHEMA_VERSION,
        review_id=_review_id(
            selected_id=selected_id,
            task_id=selected.task_id if selected is not None else "",
            recommended_action=recommended_action,
            attention=attention,
            records=records,
        ),
        selected_proposal_id=selected_id,
        task_id=selected.task_id if selected is not None else "",
        review_reason=review_reason,
        recommended_action=recommended_action,
        attention=attention,
        confidence=confidence,
        evidence_refs=list(selected.evidence_refs) if selected is not None else [],
        warnings=warnings,
        metadata=_selected_metadata(selected),
        valid=True,
        summary=summary,
    )


def _review_id(
    *,
    selected_id: str,
    task_id: str,
    recommended_action: str,
    attention: str,
    records: list[TaskDAGRecoveryProposalRecord],
) -> str:
    record_seed = "|".join(
        sorted(
            ":".join(
                [
                    record.proposal_id,
                    record.task_id,
                    record.recommended_action,
                    str(record.valid),
                ]
            )
            for record in records
        )
    )
    seed = "|".join(
        [
            selected_id,
            task_id,
            recommended_action,
            attention,
            str(len(records)),
            record_seed,
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"task_dag_recovery_review_{digest}"


def _selection_key(record: TaskDAGRecoveryProposalRecord) -> tuple[float, float, float, str]:
    return (
        -float(_score(record)),
        -float(record.confidence),
        float(record.created_at),
        record.proposal_id,
    )


def _score(record: TaskDAGRecoveryProposalRecord | None) -> int:
    if record is None or not record.valid:
        return 0
    return (
        _PRIORITY_WEIGHTS.get(record.priority, 0)
        + _ACTION_WEIGHTS.get(record.recommended_action, 0)
    )


def _review_reason(record: TaskDAGRecoveryProposalRecord) -> str:
    if record.priority == "high" and record.recommended_action in {
        "manual_review",
        "mark_blocked",
    }:
        return "high_priority_manual_attention"
    if record.recommended_action == "no_action":
        return "selected_lowest_risk_proposal"
    return f"selected_{record.recommended_action}"


def _attention_for_record(record: TaskDAGRecoveryProposalRecord) -> str:
    if record.priority == "high" and record.recommended_action in {
        "manual_review",
        "mark_blocked",
    }:
        return "urgent"
    if record.recommended_action != "no_action" or record.warnings:
        return "review"
    return "none"


def _selected_metadata(record: TaskDAGRecoveryProposalRecord | None) -> dict[str, Any]:
    if record is None:
        return {}
    metadata = dict(record.metadata)
    metadata["selected_priority"] = record.priority
    metadata["selected_source_status"] = record.source_status
    return _safe_metadata(metadata)


def _coerce_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (TaskDAGRecoveryProposal, TaskDAGRecoveryProposalRecord, dict)):
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _recommended_action(value: Any) -> str:
    normalized = str(value or "no_action").strip().lower() or "no_action"
    if normalized not in _ALLOWED_RECOMMENDED_ACTIONS:
        return "no_action"
    return normalized


def _attention(value: Any) -> str:
    normalized = str(value or "none").strip().lower() or "none"
    if normalized not in _ALLOWED_ATTENTION:
        return "none"
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
        if (
            not key
            or str(raw_key or "") in _RAW_FIELD_KEYS
            or _is_proof_like_key(raw_key)
            or _contains_proof_like_value(raw_value)
        ):
            continue
        if _is_sensitive_key(key):
            safe[key] = "<redacted>"
            continue
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
            safe[key] = _preview(raw_value, limit=160)
    return safe


def _safe_summary(summary: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in dict(summary or {}).items():
        safe_key = _preview(key, limit=80)
        if (
            not safe_key
            or _is_proof_like_key(key)
            or _contains_proof_like_value(value)
        ):
            continue
        if isinstance(value, bool):
            safe[safe_key] = value
            continue
        try:
            safe[safe_key] = int(value or 0)
        except (TypeError, ValueError):
            safe[safe_key] = 0
    return safe


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
    if any(fragment in text for fragment in _PROOF_LIKE_VALUE_FRAGMENTS):
        return True
    lowered = text.lower()
    return lowered in {"verified", "proof", "accepted"} and "flag" in lowered


def _preview(value: Any, *, limit: int) -> str:
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

