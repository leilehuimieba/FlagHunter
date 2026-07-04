from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list


SCHEMA_VERSION = 1


class ReviewState(str, Enum):
    PENDING = "pending"
    SUPPORTED = "supported"
    CONFLICTING = "conflicting"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ProofRecord:
    proof_id: str
    claim_id: str
    review_state: ReviewState = ReviewState.PENDING
    evidence_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    reviewer_ref: str | None = None
    notes: str | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "proofId": self.proof_id,
            "claimId": self.claim_id,
            "reviewState": self.review_state.value,
            "evidenceRefs": [str(item) for item in self.evidence_refs],
            "artifactRefs": [str(item) for item in self.artifact_refs],
            "reviewerRef": self.reviewer_ref,
            "notes": self.notes,
            "metadata": coerce_json_dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProofRecord":
        raw_state = str(payload.get("reviewState", ReviewState.PENDING.value))
        try:
            review_state = ReviewState(raw_state)
        except ValueError:
            review_state = ReviewState.PENDING
        return cls(
            proof_id=str(payload.get("proofId", "")),
            claim_id=str(payload.get("claimId", "")),
            review_state=review_state,
            evidence_refs=[str(item) for item in coerce_json_list(payload.get("evidenceRefs"))],
            artifact_refs=[str(item) for item in coerce_json_list(payload.get("artifactRefs"))],
            reviewer_ref=(
                str(payload["reviewerRef"]) if payload.get("reviewerRef") is not None else None
            ),
            notes=str(payload["notes"]) if payload.get("notes") is not None else None,
            metadata=coerce_json_dict(payload.get("metadata")),
        )
