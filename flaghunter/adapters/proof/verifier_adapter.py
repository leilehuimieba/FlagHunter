"""Verifier adapter skeletons."""

from __future__ import annotations

from typing import Any, Mapping

from flaghunter.ports import VerifierPort


class VerifierAdapter:
    """Delegate claim review through an injected verifier port."""

    def __init__(self, verifier: VerifierPort) -> None:
        self._verifier = verifier

    async def review_claim(
        self,
        claim_id: str,
        evidence: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return await self._verifier.review_claim(claim_id, evidence)
