"""XSS chain routing and orchestration."""

from __future__ import annotations

from typing import Any

from ..dispatcher_helpers import _base_target
from .base import _ChainOutcome


class XSSChainMixin:
    """XSS route wrapper and admin-bot/stored-XSS orchestration."""

    async def _execute_xss_route(
        self,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> _ChainOutcome:
        outcome = await self._execute_xss_chain(target, page_features, hint)
        if outcome.progress or outcome.flag:
            return outcome
        if (
            self.llm is not None
            and self.state is not None
            and self.state.is_llm_exploration_allowed()
        ):
            return await self._run_llm_driven_exploration(
                self._strategy_context(
                    target=target,
                    page_features=page_features,
                    hint=hint,
                    extras={"chain_name": "xss"},
                )
            )
        return outcome

    async def _execute_xss_chain(
        self,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> _ChainOutcome:
        base = _base_target(target)
        endpoints = set(page_features.get("endpoints") or [])
        progress = False
        reasons: list[str] = []
        source_hint_text = self._recent_local_source_hint_text().lower()
        structured_next_action = self._structured_followup_next_action().lower()
        structured_switched_from = self._structured_followup_value("switchedFrom").lower()
        structured_trigger_reason = self._structured_followup_value("triggerReason").lower()
        structured_trigger_action_driver = self._structured_followup_value("triggerActionDriver").lower()

        local_log_pivot = await self._attempt_local_challenge_log_pivot(
            target=target,
            page_features=page_features,
            hint=hint,
        )
        progress = progress or local_log_pivot.progress
        if local_log_pivot.flag:
            return local_log_pivot
        if local_log_pivot.reason:
            reasons.append(local_log_pivot.reason)

        for strategy in self._strategies_for_chain(
            "xss",
            target=target,
            page_features=page_features,
            hint=hint,
            extras={"base_target": base},
        ):
            if strategy.kind != "xss_admin_bot_sid":
                continue
            stored = await self.strategy_registry.execute(
                strategy.kind,
                self._strategy_context(
                    target=target,
                    page_features=page_features,
                    hint=hint,
                    extras={"base_target": base},
                ),
            )
            progress = progress or stored.progress
            if stored.flag:
                return stored
            if stored.reason:
                reasons.append(stored.reason)

        if (
            "/visit" in endpoints
            or "targeturl" in hint.lower()
            or "visit" in hint.lower()
            or "/visit" in source_hint_text
            or (
                (
                    structured_next_action == "collect_initial_facts"
                    or structured_switched_from == "probe_discovered_endpoint"
                    or structured_trigger_action_driver == "blackboard.discovered_endpoint"
                )
                and (
                    "/visit" in structured_trigger_reason
                    or "visit-url" in structured_trigger_reason
                    or "admin-bot" in structured_trigger_reason
                    or "admin bot" in structured_trigger_reason
                )
            )
        ):
            visit = await self._attempt_visit_url_chain(base)
            progress = progress or visit.progress
            if visit.flag:
                return visit
            if visit.reason:
                reasons.append(visit.reason)

        return _ChainOutcome(progress=progress, reason="; ".join(filter(None, reasons)))
