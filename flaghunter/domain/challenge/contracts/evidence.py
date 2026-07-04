from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list, coerce_json_value
from .sanitization import redact_sensitive_text


SCHEMA_VERSION = 1


def redact_text(value: str, *, max_chars: int = 200) -> str:
    if max_chars <= 0:
        return ""
    text = redact_sensitive_text(value, marker="[redacted]")
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3] + "..."


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    claim_id: str
    evidence_type: str
    evidence_value: JsonValue
    source_ref: str | None = None
    artifact_ref: str | None = None
    text_preview: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "evidenceId": self.evidence_id,
            "claimId": self.claim_id,
            "evidenceType": self.evidence_type,
            "evidenceValue": coerce_json_value(self.evidence_value),
            "sourceRef": self.source_ref,
            "artifactRef": self.artifact_ref,
            "textPreview": redact_text(self.text_preview) if self.text_preview is not None else None,
            "tags": [str(item) for item in self.tags],
            "metadata": coerce_json_dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceRecord":
        text_preview = payload.get("textPreview")
        return cls(
            evidence_id=str(payload.get("evidenceId", "")),
            claim_id=str(payload.get("claimId", "")),
            evidence_type=str(payload.get("evidenceType", "")),
            evidence_value=coerce_json_value(payload.get("evidenceValue")),
            source_ref=(
                str(payload["sourceRef"]) if payload.get("sourceRef") is not None else None
            ),
            artifact_ref=(
                str(payload["artifactRef"]) if payload.get("artifactRef") is not None else None
            ),
            text_preview=str(text_preview) if text_preview is not None else None,
            tags=[str(item) for item in coerce_json_list(payload.get("tags"))],
            metadata=coerce_json_dict(payload.get("metadata")),
        )
