"""Proof review boundary contracts."""

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class VerifierPort(Protocol):
    async def review_claim(
        self,
        claim_id: str,
        evidence: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...


@runtime_checkable
class ProofAuthorityPort(Protocol):
    def append_proof_record(
        self,
        claim_id: str,
        record: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...

    def confirm_claim(
        self,
        claim_id: str,
        *,
        record_id: str,
    ) -> Mapping[str, Any]:
        ...
