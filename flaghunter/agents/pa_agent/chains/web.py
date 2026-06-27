"""Generic web chain routing and orchestration."""

from __future__ import annotations

from typing import Any

from .base import _ChainOutcome

# Single source of truth for the ordered web-strategy sequence. Every kind here
# MUST resolve to a registered StrategyDefinition (StrategyRegistry.build_default);
# the I5 reachability guard (tests/unit/agents/test_chain_reachability_invariant.py)
# pins this so the order can never silently reference a phantom strategy.
# `path_traversal` is intentionally absent: it is generated as a hypothesis kind
# (hypothesis_engine `_CHAIN_BY_KIND`/_rule_based_hypotheses) but has no distinct
# strategy — the same `_has_file_endpoint` trigger is exploited by
# `file_read_endpoint`, so listing it here only produced a silently-skipped no-op
# (strategy_registry.get → None → `continue`). A distinct path-traversal technique
# is a capability-layer gap, not a reachability bug.
WEB_STRATEGY_ORDER = [
    "hint_chain_followup",
    "file_read_endpoint",
    "hash_guarded_file_read",
    "hash_reconstruction_attack",
    "ssti_probe",
    "ssti_identify",
    "ssti_exploit",
    "unicode_numeric_form_bypass",
    "contact_report_chain",
    "backup_source_leak",
    "php_unserialize_magic_method",
    "insecure_deserialization",
    "generic_param_sqli",
    "jwt_manipulation",
    "generic_param_cmdi",
    "generic_param_ssrf",
    "graphql_introspection",
    "nosql_injection",
    "xxe_injection",
    "reflected_xss",
]


class WebChainMixin:
    """Generic web route wrapper and ordered web-strategy orchestration."""

    async def _execute_web_route(
        self,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> _ChainOutcome:
        outcome = await self._execute_xss_chain(target, page_features, hint)
        if outcome.progress or outcome.flag:
            return outcome
        return await self._execute_web_chain(target, page_features, hint)

    async def _execute_web_chain(
        self,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> _ChainOutcome:
        reasons: list[str] = []
        progress = False
        if profile_poisoning_exploit := self._recent_profile_photo_poisoning_source_exploit():
            observed_outcome = await self._attempt_profile_photo_poisoning_chain(
                target,
                profile_poisoning_exploit.get("exploit_info") or {},
                artifact_url=str(profile_poisoning_exploit.get("artifact_url") or ""),
            )
            progress = progress or observed_outcome.progress
            if observed_outcome.flag:
                return observed_outcome
            if observed_outcome.reason:
                reasons.append(observed_outcome.reason)

        web_strategy_order = list(WEB_STRATEGY_ORDER)
        if self._recent_php_unserialize_source_exploit():
            web_strategy_order = [
                kind
                for kind in web_strategy_order
                if kind not in {"php_unserialize_magic_method", "backup_source_leak"}
            ]
            web_strategy_order.extend(["php_unserialize_magic_method", "backup_source_leak"])
        structured_next_action = self._structured_followup_next_action().lower()
        structured_switched_from = self._structured_followup_value("switchedFrom").lower()
        structured_trigger_reason = self._structured_followup_value("triggerReason").lower()
        structured_trigger_action_driver = self._structured_followup_value("triggerActionDriver").lower()
        if (
            (
                structured_next_action == "collect_initial_facts"
                or structured_switched_from == "probe_discovered_endpoint"
                or structured_trigger_action_driver == "blackboard.discovered_endpoint"
            )
            and (
                "source leak" in structured_trigger_reason
                or "backup" in structured_trigger_reason
                or "artifact" in structured_trigger_reason
                or "source archive" in structured_trigger_reason
                or "zip" in structured_trigger_reason
                or "source bundle" in structured_trigger_reason
            )
        ):
            web_strategy_order = [
                kind
                for kind in web_strategy_order
                if kind not in {"backup_source_leak", "contact_report_chain"}
            ]
            web_strategy_order.extend(["backup_source_leak", "contact_report_chain"])
        if self._has_recent_local_source_hint():
            web_strategy_order = [
                kind
                for kind in web_strategy_order
                if kind not in {"backup_source_leak", "contact_report_chain"}
            ]
            web_strategy_order.extend(["backup_source_leak", "contact_report_chain"])
        ctx = self._strategy_context(target=target, page_features=page_features, hint=hint)
        replayed_prefix_from_source_hints = False

        async def _run_strategy_sequence(
            sequence: list[str],
            *,
            allow_source_hint_replay: bool,
        ) -> _ChainOutcome | None:
            nonlocal progress, ctx, replayed_prefix_from_source_hints

            for kind in sequence:
                strategy = self.strategy_registry.get(kind)
                if strategy is None or not strategy.is_applicable(ctx):
                    continue
                before_source_hint_count = self._recent_local_source_hint_count()
                outcome = await self.strategy_registry.execute(kind, ctx)
                progress = progress or outcome.progress
                if outcome.flag:
                    return outcome
                if outcome.reason:
                    reasons.append(outcome.reason)
                ctx = self._strategy_context(target=target, page_features=page_features, hint=hint)

                if (
                    allow_source_hint_replay
                    and not replayed_prefix_from_source_hints
                    and kind == "backup_source_leak"
                    and self._recent_local_source_hint_count() > before_source_hint_count
                ):
                    replayed_prefix_from_source_hints = True
                    prefix = [item for item in web_strategy_order if item != "backup_source_leak"]
                    if prefix:
                        replay_outcome = await _run_strategy_sequence(
                            prefix,
                            allow_source_hint_replay=False,
                        )
                        if replay_outcome is not None:
                            return replay_outcome
            return None

        replay_outcome = await _run_strategy_sequence(
            list(web_strategy_order),
            allow_source_hint_replay=True,
        )
        if replay_outcome is not None:
            return replay_outcome

        for strategy in self._strategies_for_chain("web", target=target, page_features=page_features, hint=hint):
            if strategy.kind in web_strategy_order:
                continue
            outcome = await self.strategy_registry.execute(strategy.kind, ctx)
            progress = progress or outcome.progress
            if outcome.flag:
                return outcome
            if outcome.reason:
                reasons.append(outcome.reason)

        return _ChainOutcome(progress=progress, reason="; ".join(filter(None, reasons)))
