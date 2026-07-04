"""Small canonical-claim read helpers for the P1/B3 CTF read surface."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from ...config.constants import (
    CTF_P1_CLAIM_KIND_ALLOWLIST,
    is_ctf_claims_v1_enabled,
)
from .ctf_state import (
    CTFState,
    Claim,
    ClaimKind,
    ClaimLevel,
    ClaimStatus,
    VerificationDecision,
)


@dataclass(slots=True)
class FlagClaimView:
    verified: list[Claim] = field(default_factory=list)
    runtime: list[Claim] = field(default_factory=list)
    candidate: list[Claim] = field(default_factory=list)
    retracted: list[Claim] = field(default_factory=list)

    @property
    def has_any(self) -> bool:
        return bool(self.verified or self.runtime or self.candidate or self.retracted)


@dataclass(slots=True)
class PreferredFlagBucket:
    source: str
    items: list[Any] = field(default_factory=list)

    @property
    def from_claims(self) -> bool:
        return self.source == "claim"


def canonical_claim_reads_enabled() -> bool:
    return is_ctf_claims_v1_enabled()


def flag_found_claim_view(state: CTFState | None) -> FlagClaimView:
    view = FlagClaimView()
    if state is None or not canonical_claim_reads_enabled():
        return view
    if not hasattr(state, "find_claims_by_kind"):
        return view
    try:
        claims = state.find_claims_by_kind(ClaimKind.FLAG_FOUND, include_inactive=True)
    except Exception:
        return view

    for claim in sorted(claims, key=lambda item: float(getattr(item, "updated_at", 0.0) or 0.0)):
        if _is_retracted_claim(claim):
            view.retracted.append(claim)
        elif claim.level == ClaimLevel.VERIFIED and claim.status == ClaimStatus.ACTIVE:
            view.verified.append(claim)
        elif _has_runtime_support(state, claim):
            view.runtime.append(claim)
        elif claim.status == ClaimStatus.ACTIVE:
            view.candidate.append(claim)
    return view


def preferred_flag_summary(state: CTFState | None) -> dict[str, list[str]]:
    buckets = preferred_flag_buckets(state)
    retracted = _bucket_values(buckets["retracted"])
    return {
        "verifiedFlags": _bucket_values(buckets["verified"]),
        "runtimeFlags": _bucket_values(buckets["runtime"]),
        "candidateFlags": _bucket_values(buckets["candidate"]),
        "retractedFlags": retracted,
        "rejectedFlags": list(retracted),
    }


def preferred_flag_buckets(state: CTFState | None) -> dict[str, PreferredFlagBucket]:
    view = flag_found_claim_view(state)
    if state is None:
        return {
            "verified": PreferredFlagBucket(source="legacy", items=[]),
            "runtime": PreferredFlagBucket(source="legacy", items=[]),
            "candidate": PreferredFlagBucket(source="legacy", items=[]),
            "retracted": PreferredFlagBucket(source="legacy", items=[]),
        }
    return {
        "verified": _preferred_bucket(view.verified, getattr(state, "verified_flags", [])),
        "runtime": _preferred_bucket(view.runtime, getattr(state, "runtime_flags", [])),
        "candidate": _preferred_bucket(view.candidate, getattr(state, "candidate_flags", [])),
        "retracted": _preferred_bucket(view.retracted, getattr(state, "rejected_flags", [])),
    }


def flag_claim_counts(state: CTFState | None) -> dict[str, int]:
    view = flag_found_claim_view(state)
    return {
        "claim_flag_found_total": (
            len(view.verified) + len(view.runtime) + len(view.candidate) + len(view.retracted)
        ),
        "claim_flag_found_verified": len(view.verified),
        "claim_flag_found_runtime": len(view.runtime),
        "claim_flag_found_candidate": len(view.candidate),
        "claim_flag_found_retracted": len(view.retracted),
    }


def claim_source(claim: Claim) -> str:
    return str(getattr(claim, "source_channel", "") or "").strip()


def claim_confidence(claim: Claim) -> float:
    return float(getattr(claim, "confidence", 0.0) or 0.0)


def record_structured_claim_fact(state: CTFState, content: str) -> bool:
    if not canonical_claim_reads_enabled():
        return False
    payload = _parse_claim_fact_payload(content)
    if payload is None:
        return False
    kind = str(payload.get("kind") or payload.get("claim_kind") or "").strip()
    value = str(payload.get("content") or payload.get("value") or "").strip()
    level = str(payload.get("level") or ClaimLevel.CONJECTURE.value).strip()
    if not kind or not value:
        return False
    if kind not in CTF_P1_CLAIM_KIND_ALLOWLIST:
        return False
    if level not in {ClaimLevel.ASSUMPTION.value, ClaimLevel.CONJECTURE.value}:
        return False
    try:
        state.create_claim(
            kind=kind,
            content=value,
            level=level,
            producer_type="blackboard",
            producer_id="record_fact",
            primary_trace_id=_record_fact_trace_id(kind, value),
            source_channel="blackboard.record_fact",
            confidence=float(payload.get("confidence") or 0.0),
            confidence_reason=str(payload.get("rationale") or payload.get("reason") or ""),
            metadata={
                "source": "blackboard.record_fact",
                "raw_fact": str(content or "").strip()[:500],
            },
        )
    except Exception:
        return False
    return True


def _legacy_values(records: Any) -> list[str]:
    return [
        str(getattr(record, "value", "") or "").strip()
        for record in list(records or [])
        if str(getattr(record, "value", "") or "").strip()
    ]


def _preferred_bucket(claims: list[Claim], legacy_records: Any) -> PreferredFlagBucket:
    if claims:
        return PreferredFlagBucket(source="claim", items=list(claims))
    return PreferredFlagBucket(source="legacy", items=list(legacy_records or []))


def _bucket_values(bucket: PreferredFlagBucket) -> list[str]:
    if bucket.from_claims:
        return [
            value
            for value in (_claim_value(claim) for claim in bucket.items)
            if value
        ]
    return _legacy_values(bucket.items)


def _claim_value(claim: Claim) -> str:
    return str(getattr(claim, "content", "") or "").strip()


def _is_retracted_claim(claim: Claim) -> bool:
    return claim.level == ClaimLevel.RETRACTED or claim.status == ClaimStatus.RETRACTED


def _has_runtime_support(state: CTFState, claim: Claim) -> bool:
    for record_id in list(getattr(claim, "verification_record_ids", []) or []):
        record = state.verification_records_by_id.get(record_id)
        if record is None:
            continue
        if record.decision == VerificationDecision.RUNTIME_SUPPORTED and record.passed:
            return True
    return False


def _parse_claim_fact_payload(content: str) -> dict[str, Any] | None:
    text = str(content or "").strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _record_fact_trace_id(kind: str, value: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{value}".encode("utf-8")).hexdigest()[:16]
    return f"blackboard_record_fact:{digest}"
