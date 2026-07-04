"""Control-side completion receipts for P2 trace readback."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any


_CONTROL_METADATA_KEYS = {
    "stop_reason",
    "finish_status",
    "selected_claim_id",
    "selected_verification_record_id",
    "selected_trace_id",
    "answer_kind",
    "source_channel",
}


def record_completion_control_receipt(
    state: Any,
    *,
    producer: str,
    success: bool,
    stop_reason: str = "",
    finish_status: str = "",
    input_summary: str = "",
    output_summary: str = "",
    artifact_refs: list[str] | None = None,
    answer_kind: str = "",
    source_channel: str = "",
    selected_claim_id: str = "",
    selected_verification_record_id: str = "",
    selected_trace_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> Any | None:
    """Record a completion/stop control receipt without creating proof.

    The receipt is an audit readback of a control-flow action. It only references
    existing claim/verification/trace records and never upgrades or verifies
    anything by itself.
    """
    if state is None or not hasattr(state, "record_execution_trace"):
        return None

    selected = _select_existing_completion_evidence(state)
    normalized_stop_reason = _redact_control_text(stop_reason)[:200]
    normalized_success = bool(success)
    normalized_status = (
        str(finish_status or "").strip()
        or _derive_finish_status(
            selected.get("claim"),
            selected.get("record"),
            success=normalized_success,
        )
    )
    raw_metadata = {
        "stop_reason": normalized_stop_reason,
        "finish_status": normalized_status,
        "selected_claim_id": selected_claim_id or selected.get("claim_id", ""),
        "selected_verification_record_id": (
            selected_verification_record_id or selected.get("verification_record_id", "")
        ),
        "selected_trace_id": selected_trace_id or selected.get("trace_id", ""),
        "answer_kind": str(answer_kind or "").strip(),
        "source_channel": str(source_channel or "").strip(),
        **dict(metadata or {}),
    }
    safe_metadata = {
        key: _safe_metadata_value(raw_metadata.get(key, ""))
        for key in sorted(_CONTROL_METADATA_KEYS)
    }
    return state.record_execution_trace(
        kind="control_receipt",
        producer=str(producer or "").strip() or "control:completion",
        input_summary=_redact_control_text(input_summary)[:500],
        output_summary=_redact_control_text(output_summary)[:1000],
        success=normalized_success,
        artifact_refs=[
            _redact_control_text(item)[:500]
            for item in list(artifact_refs or [])
            if str(item or "").strip()
        ],
        metadata=safe_metadata,
    )


def _select_existing_completion_evidence(state: Any) -> dict[str, Any]:
    claim = None
    try:
        if hasattr(state, "strongest_claim"):
            claim = state.strongest_claim("flag_found")
    except Exception:
        claim = None
    if claim is None:
        return {
            "claim": None,
            "record": None,
            "claim_id": "",
            "verification_record_id": "",
            "trace_id": "",
        }

    records = []
    record_store = getattr(state, "verification_records_by_id", {}) or {}
    for record_id in list(getattr(claim, "verification_record_ids", []) or []):
        record = record_store.get(record_id)
        if record is not None:
            records.append(record)
    record = max(
        records,
        key=lambda item: float(getattr(item, "created_at", 0.0) or 0.0),
        default=None,
    )
    trace_id = (
        str(getattr(record, "trace_id", "") or "").strip()
        if record is not None
        else ""
    ) or str(getattr(claim, "primary_trace_id", "") or "").strip()
    return {
        "claim": claim,
        "record": record,
        "claim_id": str(getattr(claim, "id", "") or "").strip(),
        "verification_record_id": (
            str(getattr(record, "id", "") or "").strip() if record is not None else ""
        ),
        "trace_id": trace_id,
    }


def _derive_finish_status(claim: Any, record: Any, *, success: bool) -> str:
    if _claim_has_verified_record(claim, record):
        return "verified"
    if success:
        return "answered"
    if claim is not None:
        return "insufficient"
    return "attempted"


def _claim_has_verified_record(claim: Any, record: Any) -> bool:
    if claim is None or record is None:
        return False
    claim_level = _enum_value(getattr(claim, "level", ""))
    claim_status = _enum_value(getattr(claim, "status", ""))
    decision = _enum_value(getattr(record, "decision", ""))
    return (
        claim_level == "verified"
        and claim_status == "active"
        and decision == "verified"
        and bool(getattr(record, "passed", False))
        and bool(getattr(record, "sufficient_for_upgrade", False))
    )


def _safe_metadata_value(value: Any) -> Any:
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return _redact_control_text(value)[:200]


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value or "").strip()
    return str(getattr(value, "value", value) or "").strip()


def _redact_control_text(value: Any) -> str:
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
