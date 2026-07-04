"""Minimal pure Task DAG to crew bridge boundary contracts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .solve_node import SolveNodeReceipt, TaskBrief


TASK_DAG_CREW_BRIDGE_REQUEST_SCHEMA_VERSION = "p4d.task_dag_crew_bridge_request.v1"
TASK_DAG_CREW_BRIDGE_RECEIPT_SCHEMA_VERSION = "p4d.task_dag_crew_bridge_receipt.v1"
_WORKER_TYPES = {"default", "web", "recon", "exploit", "crypto"}
_RECEIPT_STATUSES = {
    "pending",
    "running",
    "succeeded",
    "failed",
    "partial",
    "blocked",
    "skipped",
    "insufficient",
}
_STATUS_ALIASES = {
    "completed": "succeeded",
    "complete": "succeeded",
    "success": "succeeded",
    "ok": "succeeded",
    "error": "failed",
    "failure": "failed",
    "timeout": "partial",
    "timed_out": "partial",
    "no_evidence": "insufficient",
}
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
class TaskDAGCrewBridgeRequest:
    schema_version: str
    request_id: str
    task_id: str
    task_brief_id: str
    solve_node_id: str
    worker_type: str
    goal: str
    context_summary: str = ""
    allowed_tool_names: list[str] = field(default_factory=list)
    blocked_tool_names: list[str] = field(default_factory=list)
    allowed_tool_categories: list[str] = field(default_factory=list)
    dependency_task_ids: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_CREW_BRIDGE_REQUEST_SCHEMA_VERSION
        self.request_id = _preview(self.request_id, limit=160)
        self.task_id = _preview(self.task_id, limit=160)
        self.task_brief_id = _preview(self.task_brief_id, limit=160)
        self.solve_node_id = _preview(self.solve_node_id, limit=160)
        self.worker_type = _worker_type(self.worker_type)
        self.goal = _preview(self.goal, limit=160)
        self.context_summary = _preview(self.context_summary, limit=160)
        self.allowed_tool_names = _safe_refs(self.allowed_tool_names, limit=20)
        self.blocked_tool_names = _safe_refs(self.blocked_tool_names, limit=20)
        self.allowed_tool_categories = _safe_refs(self.allowed_tool_categories, limit=20)
        self.dependency_task_ids = _safe_refs(self.dependency_task_ids, limit=20)
        self.evidence_refs = _safe_refs(self.evidence_refs, limit=20)
        self.warnings = _safe_refs(self.warnings, limit=10)
        self.metadata = _safe_metadata(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "requestId": self.request_id,
            "taskId": self.task_id,
            "taskBriefId": self.task_brief_id,
            "solveNodeId": self.solve_node_id,
            "workerType": self.worker_type,
            "goal": self.goal,
            "contextSummary": self.context_summary,
            "allowedToolNames": list(self.allowed_tool_names),
            "blockedToolNames": list(self.blocked_tool_names),
            "allowedToolCategories": list(self.allowed_tool_categories),
            "dependencyTaskIds": list(self.dependency_task_ids),
            "evidenceRefs": list(self.evidence_refs),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass
class TaskDAGCrewBridgeReceipt:
    schema_version: str
    receipt_id: str
    source_receipt_id: str
    task_id: str
    task_brief_id: str
    solve_node_id: str
    worker_id: str
    worker_type: str
    status: str
    summary: str = ""
    error_class: str = ""
    reason: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.schema_version = TASK_DAG_CREW_BRIDGE_RECEIPT_SCHEMA_VERSION
        self.receipt_id = _preview(self.receipt_id, limit=160)
        self.source_receipt_id = _preview(self.source_receipt_id, limit=160)
        self.task_id = _preview(self.task_id, limit=160)
        self.task_brief_id = _preview(self.task_brief_id, limit=160)
        self.solve_node_id = _preview(self.solve_node_id, limit=160)
        self.worker_id = _preview(self.worker_id, limit=160)
        self.worker_type = _worker_type(self.worker_type)
        self.status = _status(self.status)[0]
        self.summary = _preview(self.summary, limit=160)
        self.error_class = _preview(self.error_class, limit=80)
        self.reason = _preview(self.reason, limit=160)
        self.evidence_refs = _safe_refs(self.evidence_refs, limit=20)
        self.warnings = _safe_refs(self.warnings, limit=10)
        self.metadata = _safe_metadata(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "receiptId": self.receipt_id,
            "sourceReceiptId": self.source_receipt_id,
            "taskId": self.task_id,
            "taskBriefId": self.task_brief_id,
            "solveNodeId": self.solve_node_id,
            "workerId": self.worker_id,
            "workerType": self.worker_type,
            "status": self.status,
            "summary": self.summary,
            "errorClass": self.error_class,
            "reason": self.reason,
            "evidenceRefs": list(self.evidence_refs),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


def build_task_dag_crew_bridge_request(
    task: TaskBrief | TaskDAGCrewBridgeRequest | dict[str, Any] | None,
) -> TaskDAGCrewBridgeRequest:
    payload = _payload_from_request_input(task)
    metadata = _safe_metadata(dict(_get(payload, "metadata") or {}))
    task_id = _preview(
        _get(payload, "taskId", "task_id", "id", "nodeId", "node_id"),
        limit=160,
    )
    task_brief_id = _preview(
        _get(payload, "taskBriefId", "task_brief_id", "briefId", "brief_id"),
        limit=160,
    )
    solve_node_id = _preview(_get(payload, "solveNodeId", "solve_node_id", "node_id"), limit=160)
    worker_type = _worker_type(
        _get(payload, "workerType", "worker_type", "workerTypeHint", "worker_type_hint", "kind")
    )
    goal = _preview(_get(payload, "goal", "objective", "title"), limit=160)
    context_summary = _preview(
        _get(payload, "contextSummary", "context_summary", "summary"),
        limit=160,
    )
    allowed_tool_names = _safe_refs(
        _get(payload, "allowedToolNames", "allowed_tool_names"),
        limit=20,
    )
    blocked_tool_names = _safe_refs(
        _get(payload, "blockedToolNames", "blocked_tool_names"),
        limit=20,
    )
    allowed_tool_categories = _safe_refs(
        _get(payload, "allowedToolCategories", "allowed_tool_categories"),
        limit=20,
    )
    dependency_task_ids = _safe_refs(
        _get(payload, "dependencyTaskIds", "dependency_task_ids", "dependsOn", "depends_on"),
        limit=20,
    )
    evidence_refs = _merge_refs(
        _get(payload, "evidenceRefs", "evidence_refs"),
        _get(payload, "traceIds", "trace_ids"),
        _get(payload, "claimIds", "claim_ids"),
        _get(payload, "artifactRefs", "artifact_refs"),
    )
    warnings = _safe_refs(_get(payload, "warnings"), limit=10)
    request = TaskDAGCrewBridgeRequest(
        schema_version=TASK_DAG_CREW_BRIDGE_REQUEST_SCHEMA_VERSION,
        request_id="",
        task_id=task_id,
        task_brief_id=task_brief_id,
        solve_node_id=solve_node_id,
        worker_type=worker_type,
        goal=goal,
        context_summary=context_summary,
        allowed_tool_names=allowed_tool_names,
        blocked_tool_names=blocked_tool_names,
        allowed_tool_categories=allowed_tool_categories,
        dependency_task_ids=dependency_task_ids,
        evidence_refs=evidence_refs,
        warnings=warnings,
        metadata=metadata,
    )
    request.request_id = _request_id(request)
    return request


def normalize_task_dag_crew_bridge_receipt(
    receipt: SolveNodeReceipt | TaskDAGCrewBridgeReceipt | dict[str, Any] | None,
) -> TaskDAGCrewBridgeReceipt:
    if isinstance(receipt, TaskDAGCrewBridgeReceipt):
        return TaskDAGCrewBridgeReceipt(**asdict(receipt))
    payload = _payload_from_receipt_input(receipt)
    metadata = _safe_metadata(dict(_get(payload, "metadata") or {}))
    source_receipt_id = _preview(
        _get(payload, "sourceReceiptId", "source_receipt_id", "receiptId", "receipt_id", "id"),
        limit=160,
    )
    task_id = _preview(
        _get(payload, "taskId", "task_id") or metadata.get("task_dag_task_id"),
        limit=160,
    )
    status, status_warning = _status(_get(payload, "status"))
    warnings = _safe_refs(_get(payload, "warnings"), limit=10)
    if status_warning:
        warnings = _safe_refs([*warnings, status_warning], limit=10)
    bridge_receipt = TaskDAGCrewBridgeReceipt(
        schema_version=TASK_DAG_CREW_BRIDGE_RECEIPT_SCHEMA_VERSION,
        receipt_id="",
        source_receipt_id=source_receipt_id,
        task_id=task_id,
        task_brief_id=_preview(
            _get(payload, "taskBriefId", "task_brief_id", "inputBriefId", "input_brief_id"),
            limit=160,
        ),
        solve_node_id=_preview(_get(payload, "solveNodeId", "solve_node_id", "nodeId", "node_id"), limit=160),
        worker_id=_preview(_get(payload, "workerId", "worker_id"), limit=160),
        worker_type=_worker_type(_get(payload, "workerType", "worker_type")),
        status=status,
        summary=_preview(
            _get(payload, "summary", "outputSummary", "output_summary"),
            limit=160,
        ),
        error_class=_preview(_get(payload, "errorClass", "error_class"), limit=80),
        reason=_preview(_get(payload, "reason", "errorSummary", "error_summary"), limit=160),
        evidence_refs=_merge_refs(
            _get(payload, "evidenceRefs", "evidence_refs"),
            _get(payload, "traceIds", "trace_ids"),
            _get(payload, "claimIds", "claim_ids"),
            _get(payload, "artifactRefs", "artifact_refs"),
        ),
        warnings=warnings,
        metadata=metadata,
    )
    bridge_receipt.receipt_id = _receipt_id(bridge_receipt)
    return bridge_receipt


def _payload_from_request_input(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, TaskDAGCrewBridgeRequest):
        return value.to_dict()
    if isinstance(value, TaskBrief):
        return {
            "taskBriefId": value.id,
            "solveNodeId": value.node_id,
            "workerType": value.worker_type,
            "goal": value.objective,
            "contextSummary": value.context_summary,
            "allowedToolNames": list(value.allowed_tool_names),
            "blockedToolNames": list(value.blocked_tool_names),
            "traceIds": list(value.trace_ids),
            "claimIds": list(value.claim_ids),
            "artifactRefs": list(value.artifact_refs),
            "metadata": dict(value.metadata),
        }
    if isinstance(value, dict):
        return _strip_raw_payload(value)
    return {}


def _payload_from_receipt_input(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, TaskDAGCrewBridgeReceipt):
        return value.to_dict()
    if isinstance(value, SolveNodeReceipt):
        return {
            "sourceReceiptId": value.id,
            "solveNodeId": value.node_id,
            "workerId": value.worker_id,
            "workerType": value.worker_type,
            "status": value.status,
            "taskBriefId": value.input_brief_id,
            "summary": value.output_summary,
            "traceIds": list(value.trace_ids),
            "claimIds": list(value.claim_ids),
            "artifactRefs": list(value.artifact_refs),
            "errorClass": value.error_class,
            "reason": value.error_summary,
            "metadata": dict(value.metadata),
        }
    if isinstance(value, dict):
        return _strip_raw_payload(value)
    return {}


def _strip_raw_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in dict(value or {}).items()
        if str(key or "") not in _RAW_FIELD_KEYS and not _is_proof_like_key(key)
    }


def _get(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _request_id(request: TaskDAGCrewBridgeRequest) -> str:
    seed = "|".join(
        [
            request.task_id,
            request.task_brief_id,
            request.solve_node_id,
            request.worker_type,
            request.goal,
            ",".join(request.allowed_tool_names),
            ",".join(request.dependency_task_ids),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"task_dag_crew_request_{digest}"


def _receipt_id(receipt: TaskDAGCrewBridgeReceipt) -> str:
    seed = "|".join(
        [
            receipt.source_receipt_id,
            receipt.task_id,
            receipt.task_brief_id,
            receipt.solve_node_id,
            receipt.worker_id,
            receipt.worker_type,
            receipt.status,
            receipt.summary,
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"task_dag_crew_receipt_{digest}"


def _worker_type(value: Any) -> str:
    normalized = str(value or "default").strip().lower() or "default"
    if normalized not in _WORKER_TYPES:
        return "default"
    return normalized


def _status(value: Any) -> tuple[str, str]:
    normalized = str(value or "pending").strip().lower() or "pending"
    normalized = _STATUS_ALIASES.get(normalized, normalized)
    if normalized in _RECEIPT_STATUSES:
        return normalized, ""
    return "failed", "invalid_status"


def _merge_refs(*values: Any) -> list[str]:
    refs: list[str] = []
    for value in values:
        refs.extend(_safe_refs(value, limit=20))
    return _safe_refs(refs, limit=20)


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
        if isinstance(raw_value, bool) or raw_value is None:
            safe[key] = raw_value
        elif isinstance(raw_value, int):
            safe[key] = raw_value
        elif isinstance(raw_value, float):
            safe[key] = _clamp_float(raw_value, minimum=-1_000_000.0, maximum=1_000_000.0)
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


def _clamp_float(value: Any, *, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = minimum
    return max(minimum, min(maximum, result))
