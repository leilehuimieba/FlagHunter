"""JWT manipulation chain orchestration."""

from __future__ import annotations

from typing import Any

from .base import _ChainOutcome


class JWTChainMixin:
    """Thin route wrapper for JWT-specific manipulation strategies."""

    async def _execute_jwt_chain(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        return await self._run_jwt_manipulation_strategy(target, page_features)
