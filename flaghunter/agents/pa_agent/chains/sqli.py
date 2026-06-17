"""SQL injection chain orchestration."""

from __future__ import annotations

from typing import Any

from ....tools.tool_guard import ToolMissingError
from ..ctf_planner import find_auth_form
from .base import _ChainOutcome


class SQLIChainMixin:
    """SQLi route wrapper coordinating registry strategies and sqlmap capability."""

    async def _execute_sqli_chain(
        self,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> _ChainOutcome:
        reasons: list[str] = []
        progress = False
        sqli_strategies = list(
            self._strategies_for_chain(
                "sqli",
                target=target,
                page_features=page_features,
                hint=hint,
            )
        )

        for strategy in sqli_strategies:
            if strategy.kind == "generic_param_sqli":
                continue
            bypass = await self.strategy_registry.execute(
                strategy.kind,
                self._strategy_context(
                    target=target,
                    page_features=page_features,
                    hint=hint,
                ),
            )
            progress = progress or bypass.progress
            if bypass.flag:
                return bypass
            if bypass.reason:
                reasons.append(bypass.reason)

        forms = page_features.get("forms") or []
        auth_form = find_auth_form(forms)
        sqlmap_form = auth_form
        if sqlmap_form is None:
            for form in forms:
                if not isinstance(form, dict):
                    continue
                inputs = form.get("inputs") or []
                if any(
                    isinstance(item, dict) and str(item.get("name") or "").strip()
                    for item in inputs
                ):
                    sqlmap_form = form
                    break
        sqli_impl = self.capability_registry.best_available("sql_injection_test")
        if sqli_impl is None:
            missing = self.capability_registry.missing_tools_for("sql_injection_test")
            if missing:
                raise ToolMissingError(missing)
        elif sqli_impl.method == "sqlmap":
            sqlmap = await self._attempt_sqlmap_sqli(target, auth_form=sqlmap_form)
            progress = progress or sqlmap.progress
            if sqlmap.flag:
                return sqlmap
            if sqlmap.reason:
                reasons.append(sqlmap.reason)
        else:
            reasons.append(
                f"sqli capability degraded to {sqli_impl.method}; skip heavy installer flow"
            )

        for strategy in sqli_strategies:
            if strategy.kind != "generic_param_sqli":
                continue
            generic = await self.strategy_registry.execute(
                strategy.kind,
                self._strategy_context(
                    target=target,
                    page_features=page_features,
                    hint=hint,
                ),
            )
            progress = progress or generic.progress
            if generic.flag:
                return generic
            if generic.reason:
                reasons.append(generic.reason)

        if hint:
            reasons.append(f"hint considered: {hint}")

        return _ChainOutcome(progress=progress, reason="; ".join(filter(None, reasons)))
