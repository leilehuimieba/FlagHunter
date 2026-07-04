"""Claim store adapter skeletons."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from flaghunter.ports import ClaimStorePort


class ClaimStoreAdapter:
    """Delegate claim access through an injected claim store port."""

    def __init__(self, store: ClaimStorePort) -> None:
        self._store = store

    def create_candidate_claim(
        self,
        kind: str,
        content: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return self._store.create_candidate_claim(kind, content)

    def find_claims(
        self,
        *,
        kind: str | None = None,
        status: str | None = None,
    ) -> Iterable[Mapping[str, Any]]:
        return self._store.find_claims(kind=kind, status=status)

    def append_evidence_trace(
        self,
        claim_id: str,
        evidence: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return self._store.append_evidence_trace(claim_id, evidence)
