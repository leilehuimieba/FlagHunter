from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._serialization import JsonValue, coerce_json_dict, coerce_json_list
from .sanitization import preview_text, sanitize_metadata


SCHEMA_VERSION = "challenge.policy_catalog.v1"
POLICY_REF_SCHEMA_VERSION = "challenge.policy_ref.v1"
POLICY_REVIEW_REF_SCHEMA_VERSION = "challenge.policy_review_ref.v1"


@dataclass(frozen=True)
class PolicyRef:
    policy_id: str
    name: str = ""
    policy_kind: str = "generic"
    status: str = "active"
    applies_to_refs: list[str] = field(default_factory=list)
    checkpoint_refs: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": POLICY_REF_SCHEMA_VERSION,
            "policyId": _clean(self.policy_id),
            "namePreview": preview_text(self.name),
            "policyKind": _clean(self.policy_kind) or "generic",
            "status": _clean(self.status) or "active",
            "appliesToRefs": _str_refs(self.applies_to_refs),
            "checkpointRefs": _str_refs(self.checkpoint_refs),
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PolicyRef":
        return cls(
            policy_id=str(payload.get("policyId", "")),
            name=str(payload.get("namePreview", "")),
            policy_kind=str(payload.get("policyKind", "generic")),
            status=str(payload.get("status", "active")),
            applies_to_refs=[
                str(item) for item in coerce_json_list(payload.get("appliesToRefs"))
            ],
            checkpoint_refs=[
                str(item) for item in coerce_json_list(payload.get("checkpointRefs"))
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class PolicyReviewRef:
    review_id: str
    policy_id: str
    run_id: str = ""
    subject_ref: str = ""
    status: str = "recorded"
    summary_preview: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schemaVersion": POLICY_REVIEW_REF_SCHEMA_VERSION,
            "reviewId": _clean(self.review_id),
            "policyId": _clean(self.policy_id),
            "runId": _clean(self.run_id),
            "subjectRef": _clean(self.subject_ref),
            "status": _clean(self.status) or "recorded",
            "summaryPreview": preview_text(self.summary_preview),
            "evidenceRefs": _str_refs(self.evidence_refs),
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PolicyReviewRef":
        return cls(
            review_id=str(payload.get("reviewId", "")),
            policy_id=str(payload.get("policyId", "")),
            run_id=str(payload.get("runId", "")),
            subject_ref=str(payload.get("subjectRef", "")),
            status=str(payload.get("status", "recorded")),
            summary_preview=str(payload.get("summaryPreview", "")),
            evidence_refs=[
                str(item) for item in coerce_json_list(payload.get("evidenceRefs"))
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


@dataclass(frozen=True)
class PolicyCatalog:
    run_id: str
    policies: list[PolicyRef] = field(default_factory=list)
    reviews: list[PolicyReviewRef] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        policy_payloads = [_coerce_policy(item).to_dict() for item in self.policies]
        review_payloads = [_coerce_review(item).to_dict() for item in self.reviews]
        return {
            "schemaVersion": SCHEMA_VERSION,
            "runId": _clean(self.run_id),
            "policies": policy_payloads,
            "reviews": review_payloads,
            "summary": {
                "policyCount": len(policy_payloads),
                "reviewCount": len(review_payloads),
                "kindCounts": _counts(item.get("policyKind") for item in policy_payloads),
                "statusCounts": _counts(item.get("status") for item in policy_payloads),
                "reviewStatusCounts": _counts(
                    item.get("status") for item in review_payloads
                ),
            },
            "metadata": sanitize_metadata(coerce_json_dict(self.metadata)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PolicyCatalog":
        return cls(
            run_id=str(payload.get("runId", "")),
            policies=[
                PolicyRef.from_dict(item)
                for item in coerce_json_list(payload.get("policies"))
                if isinstance(item, dict)
            ],
            reviews=[
                PolicyReviewRef.from_dict(item)
                for item in coerce_json_list(payload.get("reviews"))
                if isinstance(item, dict)
            ],
            metadata=coerce_json_dict(payload.get("metadata")),
        )


def _coerce_policy(value: PolicyRef | Mapping[str, Any]) -> PolicyRef:
    if isinstance(value, PolicyRef):
        return value
    return PolicyRef.from_dict(value)


def _coerce_review(value: PolicyReviewRef | Mapping[str, Any]) -> PolicyReviewRef:
    if isinstance(value, PolicyReviewRef):
        return value
    return PolicyReviewRef.from_dict(value)


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = _clean(value)
        if key:
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _str_refs(values: Any) -> list[str]:
    return [_clean(item) for item in coerce_json_list(values) if _clean(item)]


def _clean(value: Any) -> str:
    return str(value or "").strip()
