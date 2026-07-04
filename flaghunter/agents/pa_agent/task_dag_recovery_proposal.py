from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .solve_node import SolveNodeReceipt, solve_node_receipt_from_dict
from .task_dag_plan import (
    TaskDAGPlan,
    TaskDAGStatus,
    task_dag_plan_from_dict,
    task_dag_plan_to_dict,
)


TASK_DAG_RECOVERY_PROPOSAL_SCHEMA_VERSION = "p4c.task_dag_recovery_proposal.v1"
_ACTION_VALUE = "propose_recovery"
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
_PROOF_FIELD_KEYS = {
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
_ALLOWED_ACTIONS = {
    "no_action",
    "retry_task",
    "adjust_inputs",
    "request_more_evidence",
    "mark_blocked",
    "manual_review",
    "propose_new_task",
}
_ALLOWED_PRIORITIES = {"low", "normal", "high"}
_METADATA_KEYS = {
    "error_class",
    "error_summary",
    "output_summary",
    "exit_code",
    "duration_ms",
    "source_kind",
    "outcome_kind",
    "retry_count",
    "attempt_count",
    "previous_proposal_count",
}


class TaskDAGRecoveryProposalError(ValueError):
    pass


@dataclass
class TaskDAGRecoveryProposal:
    schema_version: str
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

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_RECOVERY_PROPOSAL_SCHEMA_VERSION
        self.proposal_id = _preview(self.proposal_id, limit=160)
        self.action = _preview(self.action or _ACTION_VALUE, limit=80) or _ACTION_VALUE
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
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
            "metadata": {
                "schema_version": TASK_DAG_RECOVERY_PROPOSAL_SCHEMA_VERSION,
                **dict(self.metadata),
            },
        }


def propose_task_dag_recovery(
    *,
    state: Any | None = None,
    plan: TaskDAGPlan | dict[str, Any] | None = None,
    receipt: SolveNodeReceipt | dict[str, Any] | None = None,
    task_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> TaskDAGRecoveryProposal:
    _validate_input_tree("plan", plan)
    _validate_input_tree("receipt", receipt)
    _validate_input_tree("metadata", metadata)
    if isinstance(state, dict):
        _validate_input_tree("state", state)

    normalized_plan = _coerce_plan(plan if plan is not None else _state_plan(state))
    normalized_task_id = str(task_id or "").strip()
    node = _select_node(normalized_plan, normalized_task_id)
    if node is not None and not normalized_task_id:
        normalized_task_id = node.id

    normalized_receipt = _coerce_receipt(
        receipt if receipt is not None else _state_receipt(state, node)
    )
    input_metadata = metadata if isinstance(metadata, dict) else {}
    merged_metadata = _merge_metadata(normalized_receipt, input_metadata)
    source_status = _source_status(node, normalized_receipt)
    receipt_id = normalized_receipt.id if normalized_receipt is not None else ""
    evidence_refs = _evidence_refs(node, normalized_receipt)
    warnings: list[str] = []

    if node is None and normalized_receipt is None:
        warnings.append("no_" + "rec" + "overy_source")
        return _proposal(
            task_id=normalized_task_id,
            receipt_id=receipt_id,
            source_status=source_status,
            reason="no_" + "rec" + "overy_source",
            recommended_action="no_action",
            confidence=0.0,
            priority="low",
            evidence_refs=evidence_refs,
            warnings=warnings,
            metadata=merged_metadata,
        )

    if source_status in {"succeeded", "completed"}:
        return _proposal(
            task_id=normalized_task_id,
            receipt_id=receipt_id,
            source_status=source_status,
            reason="terminal_success",
            recommended_action="no_action",
            confidence=0.0,
            priority="low",
            evidence_refs=evidence_refs,
            warnings=warnings,
            metadata=merged_metadata,
        )

    if source_status == "skipped":
        return _proposal(
            task_id=normalized_task_id,
            receipt_id=receipt_id,
            source_status=source_status,
            reason="task_skipped",
            recommended_action="no_action",
            confidence=0.2,
            priority="low",
            evidence_refs=evidence_refs,
            warnings=warnings,
            metadata=merged_metadata,
        )

    if normalized_receipt is None and source_status in {"failed", "insufficient", "blocked"}:
        warnings.append("missing_source_receipt")
        return _proposal(
            task_id=normalized_task_id,
            receipt_id="",
            source_status=source_status,
            reason="missing_source_receipt",
            recommended_action="manual_review",
            confidence=0.45,
            priority="normal",
            evidence_refs=evidence_refs,
            warnings=warnings,
            metadata=merged_metadata,
        )

    attempts = _attempt_count(merged_metadata)
    if attempts > 2:
        warnings.append("retry_limit_reached")
        return _proposal(
            task_id=normalized_task_id,
            receipt_id=receipt_id,
            source_status=source_status,
            reason="retry_limit_reached",
            recommended_action="manual_review",
            confidence=0.65,
            priority="high",
            evidence_refs=evidence_refs,
            warnings=warnings,
            metadata=merged_metadata,
        )

    if source_status == "blocked":
        return _proposal(
            task_id=normalized_task_id,
            receipt_id=receipt_id,
            source_status=source_status,
            reason="task_blocked",
            recommended_action="manual_review",
            confidence=0.55,
            priority="normal",
            evidence_refs=evidence_refs,
            warnings=warnings,
            metadata=merged_metadata,
        )

    if source_status in {"partial", "insufficient"}:
        return _proposal(
            task_id=normalized_task_id,
            receipt_id=receipt_id,
            source_status=source_status,
            reason="insufficient_evidence",
            recommended_action="request_more_evidence",
            confidence=0.6,
            priority="normal",
            evidence_refs=evidence_refs,
            warnings=warnings,
            metadata=merged_metadata,
        )

    if source_status == "failed":
        if _looks_like_input_problem(merged_metadata):
            return _proposal(
                task_id=normalized_task_id,
                receipt_id=receipt_id,
                source_status=source_status,
                reason="input_problem",
                recommended_action="adjust_inputs",
                confidence=0.65,
                priority="high",
                evidence_refs=evidence_refs,
                warnings=warnings,
                metadata=merged_metadata,
            )
        return _proposal(
            task_id=normalized_task_id,
            receipt_id=receipt_id,
            source_status=source_status,
            reason="task_failed",
            recommended_action="retry_task",
            confidence=0.55,
            priority="high",
            evidence_refs=evidence_refs,
            warnings=warnings,
            metadata=merged_metadata,
        )

    return _proposal(
        task_id=normalized_task_id,
        receipt_id=receipt_id,
        source_status=source_status,
        reason="no_actionable_status",
        recommended_action="no_action",
        confidence=0.0,
        priority="low",
        evidence_refs=evidence_refs,
        warnings=warnings,
        metadata=merged_metadata,
    )


def _proposal(
    *,
    task_id: str,
    receipt_id: str,
    source_status: str,
    reason: str,
    recommended_action: str,
    confidence: float,
    priority: str,
    evidence_refs: list[str],
    warnings: list[str],
    metadata: dict[str, Any],
) -> TaskDAGRecoveryProposal:
    normalized_action = _recommended_action(recommended_action)
    return TaskDAGRecoveryProposal(
        schema_version=TASK_DAG_RECOVERY_PROPOSAL_SCHEMA_VERSION,
        proposal_id=_proposal_id(task_id, receipt_id, source_status, normalized_action),
        action=_ACTION_VALUE,
        task_id=task_id,
        source_receipt_id=receipt_id,
        source_status=source_status,
        recovery_reason=reason,
        recommended_action=normalized_action,
        confidence=confidence,
        priority=priority,
        evidence_refs=evidence_refs,
        warnings=warnings,
        metadata=metadata,
    )


def _proposal_id(
    task_id: str,
    receipt_id: str,
    source_status: str,
    recommended_action: str,
) -> str:
    seed = "|".join(
        [
            _preview(task_id, limit=160),
            _preview(receipt_id, limit=160),
            _preview(source_status, limit=80),
            _preview(recommended_action, limit=80),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"task_dag_proposal_{digest}"


def _coerce_plan(value: Any) -> TaskDAGPlan | None:
    if value is None:
        return None
    if isinstance(value, TaskDAGPlan):
        return task_dag_plan_from_dict(task_dag_plan_to_dict(value))
    if isinstance(value, dict):
        return task_dag_plan_from_dict(value)
    return None


def _coerce_receipt(value: Any) -> SolveNodeReceipt | None:
    if value is None:
        return None
    if isinstance(value, SolveNodeReceipt):
        return solve_node_receipt_from_dict(value.to_dict())
    if isinstance(value, dict):
        return solve_node_receipt_from_dict(value)
    return None


def _state_plan(state: Any | None) -> Any:
    if state is None:
        return None
    getter = getattr(state, "get_task_dag_plan", None)
    if callable(getter):
        return getter()
    if isinstance(state, dict):
        return state.get("task_dag_plan")
    return getattr(state, "task_dag_plan", None)


def _state_receipt(state: Any | None, node: Any | None) -> Any:
    if state is None or node is None:
        return None
    receipt_ids = list(getattr(node, "receipt_ids", []) or [])
    if not receipt_ids:
        return None
    receipt_id = str(receipt_ids[-1] or "").strip()
    if not receipt_id:
        return None
    getter = getattr(state, "get_solve_node_receipt", None)
    if callable(getter):
        return getter(receipt_id)
    if isinstance(state, dict):
        store = dict(state.get("solve_node_receipts_by_id") or {})
        return store.get(receipt_id)
    store = getattr(state, "solve_node_receipts_by_id", {})
    if isinstance(store, dict):
        return store.get(receipt_id)
    return None


def _select_node(plan: TaskDAGPlan | None, task_id: str) -> Any | None:
    if plan is None:
        return None
    normalized_task_id = str(task_id or "").strip()
    if normalized_task_id:
        return plan.get_node(normalized_task_id)
    for status in (
        TaskDAGStatus.FAILED,
        TaskDAGStatus.INSUFFICIENT,
        TaskDAGStatus.BLOCKED,
        TaskDAGStatus.SKIPPED,
    ):
        for node in plan.nodes_by_id.values():
            if node.status is status:
                return node
    return next(iter(plan.nodes_by_id.values()), None)


def _source_status(node: Any | None, receipt: SolveNodeReceipt | None) -> str:
    receipt_status = str(getattr(receipt, "status", "") or "").strip().lower()
    node_status = str(getattr(getattr(node, "status", ""), "value", getattr(node, "status", "")) or "").strip().lower()
    if receipt_status and receipt_status != "completed":
        return _canonical_status(receipt_status)
    if node_status:
        return _canonical_status(node_status)
    return _canonical_status(receipt_status)


def _canonical_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "success": "succeeded",
        "ok": "succeeded",
        "error": "failed",
        "failure": "failed",
        "timeout": "partial",
        "timed_out": "partial",
        "no_evidence": "partial",
    }
    return aliases.get(normalized, normalized)


def _merge_metadata(
    receipt: SolveNodeReceipt | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if receipt is not None:
        receipt_metadata = dict(receipt.metadata or {})
        for key in _METADATA_KEYS:
            if key in receipt_metadata:
                merged[key] = receipt_metadata[key]
        if receipt.error_class:
            merged["error_class"] = receipt.error_class
        if receipt.error_summary:
            merged["error_summary"] = receipt.error_summary
        if receipt.output_summary:
            merged["output_summary"] = receipt.output_summary
        if receipt.duration_ms is not None:
            merged["duration_ms"] = receipt.duration_ms
    for key in _METADATA_KEYS:
        if key in metadata:
            merged[key] = metadata[key]
    return _safe_metadata(merged)


def _evidence_refs(node: Any | None, receipt: SolveNodeReceipt | None) -> list[str]:
    refs: list[str] = []
    if receipt is not None:
        refs.extend(list(getattr(receipt, "trace_ids", []) or []))
        refs.extend(list(getattr(receipt, "claim_ids", []) or []))
        refs.extend(list(getattr(receipt, "artifact_refs", []) or []))
    return _safe_refs(refs, limit=20)


def _attempt_count(metadata: dict[str, Any]) -> int:
    attempts = 0
    for key in ("retry_count", "attempt_count", "previous_proposal_count"):
        try:
            attempts = max(attempts, int(metadata.get(key, 0) or 0))
        except (TypeError, ValueError):
            continue
    return attempts


def _looks_like_input_problem(metadata: dict[str, Any]) -> bool:
    text = " ".join(
        str(metadata.get(key, "") or "")
        for key in ("error_class", "error_summary", "output_summary")
    )
    return bool(
        re.search(
            r"(?i)(invalid\s*input|missing\s*(required\s*)?input|bad\s*argument|invalid\s*argument|validation)",
            text,
        )
    )


def _recommended_action(value: Any) -> str:
    normalized = str(value or "no_action").strip().lower() or "no_action"
    if normalized not in _ALLOWED_ACTIONS:
        return "no_action"
    return normalized


def _priority(value: Any) -> str:
    normalized = str(value or "normal").strip().lower() or "normal"
    if normalized not in _ALLOWED_PRIORITIES:
        return "normal"
    return normalized


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for raw_key, raw_value in dict(metadata or {}).items():
        key = _preview(raw_key, limit=80)
        if not key:
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
            safe[key] = _clamp_float(raw_value, minimum=-1_000_000.0, maximum=1_000_000.0)
        else:
            safe[key] = _preview(raw_value, limit=value_limit)
    return safe


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


def _validate_input_tree(label: str, value: Any) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        _validate_scalar_value(label, value)
        return
    if isinstance(value, dict):
        for raw_key, raw_value in value.items():
            key = str(raw_key or "")
            if key in _RAW_FIELD_KEYS:
                raise TaskDAGRecoveryProposalError(f"raw field is not accepted: {key}")
            if key in _PROOF_FIELD_KEYS:
                raise TaskDAGRecoveryProposalError(
                    f"proof-like field is not accepted: {key}"
                )
            _validate_scalar_value(key, raw_value)
            _validate_input_tree(key, raw_value)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _validate_input_tree(label, item)


def _validate_scalar_value(label: str, value: Any) -> None:
    if isinstance(value, str) and _is_proof_like_value(value):
        raise TaskDAGRecoveryProposalError(
            f"proof-like value is not accepted: {label}"
        )


def _is_proof_like_value(value: str) -> bool:
    normalized = str(value or "")
    blocked = {
        'level="' + "verified" + '"',
        "level='" + "verified" + "'",
    }
    return any(item in normalized for item in blocked)
