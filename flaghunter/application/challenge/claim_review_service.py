"""Review neutral challenge claims through injected ports."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.domain.challenge.contracts._serialization import (
    JsonValue,
    coerce_json_dict,
)
from flaghunter.domain.challenge.contracts.claims import ChallengeClaim
from flaghunter.ports.proof_authority import VerifierPort


SCHEMA_VERSION = 1


class ReviewClaim:
    def __init__(self, *, verifier: VerifierPort | None = None) -> None:
        self._verifier = verifier

    async def review(
        self,
        *,
        claim: ChallengeClaim,
        evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, JsonValue]:
        evidence_payload = coerce_json_dict(evidence)
        review_payload: dict[str, JsonValue] = {}
        if self._verifier is not None:
            review_payload = coerce_json_dict(
                await self._verifier.review_claim(claim.claim_id, evidence_payload)
            )
        return {
            "schemaVersion": SCHEMA_VERSION,
            "claimId": claim.claim_id,
            "claim": claim.to_dict(),
            "evidence": evidence_payload,
            "review": review_payload,
        }
