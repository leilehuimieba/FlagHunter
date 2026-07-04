"""Proof authority adapter skeletons."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.ports import ProofAuthorityPort


class ProofAuthorityAdapter:
    """Delegate proof authority operations through an injected port."""

    def __init__(self, authority: ProofAuthorityPort) -> None:
        self._authority = authority

    def append_proof_record(
        self,
        claim_id: str,
        record: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return self._authority.append_proof_record(claim_id, record)

    def confirm_claim(
        self,
        claim_id: str,
        *,
        record_id: str,
    ) -> Mapping[str, Any]:
        return self._authority.confirm_claim(claim_id, record_id=record_id)
