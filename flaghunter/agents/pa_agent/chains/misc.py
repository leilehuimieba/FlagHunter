"""Miscellaneous CTF chain orchestration."""

from __future__ import annotations

from typing import Any

from .base import _ChainOutcome


class MiscChainMixin:
    """Run misc-chain registry strategies and optional LLM exploration fallback."""

    async def _execute_misc_chain(
        self,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> _ChainOutcome:
        reasons: list[str] = []
        progress = False

        for strategy in self._strategies_for_chain(
            "misc",
            target=target,
            page_features=page_features,
            hint=hint,
        ):
            if strategy.kind == "llm_driven_exploration":
                continue
            outcome = await self.strategy_registry.execute(
                strategy.kind,
                self._strategy_context(
                    target=target,
                    page_features=page_features,
                    hint=hint,
                ),
            )
            progress = progress or outcome.progress
            if outcome.flag:
                return outcome
            if outcome.reason:
                reasons.append(outcome.reason)

        if (
            self.llm is not None
            and self.state is not None
            and self.state.is_llm_exploration_allowed()
        ):
            fallback = await self._run_llm_driven_exploration(
                self._strategy_context(
                    target=target,
                    page_features=page_features,
                    hint=hint,
                    extras={"chain_name": "misc"},
                )
            )
            progress = progress or fallback.progress
            if fallback.flag:
                return fallback
            if fallback.reason:
                reasons.append(fallback.reason)

        return _ChainOutcome(progress=progress, reason="; ".join(filter(None, reasons)))
