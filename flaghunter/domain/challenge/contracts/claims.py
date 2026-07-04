from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list, coerce_json_value


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ChallengeClaim:
    claim_id: str
    claim_type: str
    claim_value: JsonValue
    status: str = "candidate"
    evidence_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "claimId": self.claim_id,
            "claimType": self.claim_type,
            "claimValue": coerce_json_value(self.claim_value),
            "status": self.status,
            "evidenceRefs": [str(item) for item in self.evidence_refs],
            "artifactRefs": [str(item) for item in self.artifact_refs],
            "metadata": coerce_json_dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ChallengeClaim":
        return cls(
            claim_id=str(payload.get("claimId", "")),
            claim_type=str(payload.get("claimType", "")),
            claim_value=coerce_json_value(payload.get("claimValue")),
            status=str(payload.get("status", "candidate")),
            evidence_refs=[str(item) for item in coerce_json_list(payload.get("evidenceRefs"))],
            artifact_refs=[str(item) for item in coerce_json_list(payload.get("artifactRefs"))],
            metadata=coerce_json_dict(payload.get("metadata")),
        )
