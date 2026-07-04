"""Control-side completion receipts for P2 trace readback."""

from __future__ import annotations

from enum import Enum
from typing import Any

from flaghunter.domain.challenge.contracts.control import (
    build_control_receipt_payload,
)


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
    normalized_success = bool(success)
    normalized_status = (
        str(finish_status or "").strip()
        or _derive_finish_status(
            selected.get("claim"),
            selected.get("record"),
            success=normalized_success,
        )
    )
    payload = build_control_receipt_payload(
        producer=str(producer or "").strip() or "control:completion",
        success=normalized_success,
        stop_reason=stop_reason,
        finish_status=normalized_status,
        input_summary=input_summary,
        output_summary=output_summary,
        artifact_refs=artifact_refs,
        answer_kind=answer_kind,
        source_channel=source_channel,
        selected_claim_id=selected_claim_id or selected.get("claim_id", ""),
        selected_verification_record_id=(
            selected_verification_record_id or selected.get("verification_record_id", "")
        ),
        selected_trace_id=selected_trace_id or selected.get("trace_id", ""),
        metadata=metadata,
    )
    return state.record_execution_trace(**payload)


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


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value or "").strip()
    return str(getattr(value, "value", value) or "").strip()
