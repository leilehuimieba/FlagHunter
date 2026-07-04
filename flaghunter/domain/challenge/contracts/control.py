from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list
from .sanitization import redact_sensitive_text


SCHEMA_VERSION = 1

CONTROL_RECEIPT_KIND = "control_receipt"
CONTROL_METADATA_KEYS = {
    "stop_reason",
    "finish_status",
    "selected_claim_id",
    "selected_verification_record_id",
    "selected_trace_id",
    "answer_kind",
    "source_channel",
}


@dataclass(frozen=True)
class ControlReceipt:
    producer: str
    success: bool
    input_summary: str = ""
    output_summary: str = ""
    artifact_refs: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "kind": CONTROL_RECEIPT_KIND,
            "producer": str(self.producer or "").strip() or "control:completion",
            "success": bool(self.success),
            "inputSummary": redact_control_text(self.input_summary)[:500],
            "outputSummary": redact_control_text(self.output_summary)[:1000],
            "artifactRefs": [
                redact_control_text(item)[:500]
                for item in list(self.artifact_refs or [])
                if str(item or "").strip()
            ],
            "metadata": _safe_control_metadata(self.metadata),
        }

    def to_trace_payload(self) -> dict[str, JsonValue]:
        payload = self.to_dict()
        return {
            "kind": payload["kind"],
            "producer": payload["producer"],
            "input_summary": payload["inputSummary"],
            "output_summary": payload["outputSummary"],
            "success": payload["success"],
            "artifact_refs": payload["artifactRefs"],
            "metadata": payload["metadata"],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ControlReceipt":
        return cls(
            producer=str(payload.get("producer", "")),
            success=bool(payload.get("success", False)),
            input_summary=str(payload.get("inputSummary", "")),
            output_summary=str(payload.get("outputSummary", "")),
            artifact_refs=[str(item) for item in coerce_json_list(payload.get("artifactRefs"))],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


def build_control_receipt_payload(
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
) -> dict[str, JsonValue]:
    raw_metadata = {
        "stop_reason": redact_control_text(stop_reason)[:200],
        "finish_status": str(finish_status or "").strip(),
        "selected_claim_id": str(selected_claim_id or "").strip(),
        "selected_verification_record_id": str(
            selected_verification_record_id or ""
        ).strip(),
        "selected_trace_id": str(selected_trace_id or "").strip(),
        "answer_kind": str(answer_kind or "").strip(),
        "source_channel": str(source_channel or "").strip(),
        **dict(metadata or {}),
    }
    receipt = ControlReceipt(
        producer=producer,
        success=success,
        input_summary=input_summary,
        output_summary=output_summary,
        artifact_refs=list(artifact_refs or []),
        metadata=raw_metadata,
    )
    return receipt.to_trace_payload()


def redact_control_text(value: Any) -> str:
    return redact_sensitive_text(value)


def _safe_control_metadata(metadata: Mapping[str, Any]) -> dict[str, JsonValue]:
    return {
        key: _safe_metadata_value(metadata.get(key, ""))
        for key in sorted(CONTROL_METADATA_KEYS)
    }


def _safe_metadata_value(value: Any) -> JsonValue:
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return redact_control_text(value)[:200]
