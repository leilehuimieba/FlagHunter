from __future__ import annotations

from types import SimpleNamespace

import pytest

from pentestagent.agents.pa_agent.strategy_registry import (
    StrategyContext,
    StrategyRegistry,
)


class _DummyDispatcher:
    async def _run_llm_driven_exploration(self, context):  # noqa: SLF001
        return {"kind": "llm_driven_exploration", "target": context.target}

    async def _attempt_auth_form_sqli(self, target, auth_form):  # noqa: SLF001
        return {"target": target, "auth_form": auth_form}

    async def _attempt_stored_xss_chain(self, base, auth_form, writable_field):  # noqa: SLF001
        return {"base": base, "auth_form": auth_form, "writable_field": writable_field}

    async def _run_backup_source_leak_strategy(self, target, page_features, hint):  # noqa: SLF001
        return {"target": target, "page_features": page_features, "hint": hint}

    async def _run_contact_report_chain_strategy(self, target, page_features):  # noqa: SLF001
        return {"target": target, "page_features": page_features, "kind": "contact_report_chain"}

    async def _run_unicode_numeric_form_bypass_strategy(self, target, page_features):  # noqa: SLF001
        return {"target": target, "page_features": page_features, "kind": "unicode_numeric_form_bypass"}

    async def _run_artifact_forensics_strategy(self, target, page_features, hint):  # noqa: SLF001
        return {"target": target, "page_features": page_features, "hint": hint, "kind": "artifact_forensics"}

    async def _attempt_php_unserialize_chain(self, target, exploit_info, *, artifact_url):  # noqa: SLF001
        return {"target": target, "exploit_info": exploit_info, "artifact_url": artifact_url}


def test_strategy_registry_contains_phase5_core_strategies():
    registry = StrategyRegistry.build_default()

    for kind in (
        "llm_driven_exploration",
        "artifact_forensics",
        "auth_form_sqli",
        "xss_admin_bot_sid",
        "contact_report_chain",
        "backup_source_leak",
        "php_unserialize_magic_method",
    ):
        strategy = registry.get(kind)
        assert strategy is not None
        assert strategy.precondition_description
        assert strategy.minimal_experiment
        assert strategy.success_signal
        assert strategy.failure_signal
        assert strategy.escalation_condition


def test_strategy_registry_exposes_contract_summary_for_core_strategy():
    registry = StrategyRegistry.build_default()

    contract = registry.get_contract("auth_form_sqli")

    assert contract is not None
    assert contract["kind"] == "auth_form_sqli"
    assert contract["chain_name"] == "sqli"
    assert contract["precondition"]
    assert contract["minimal_experiment"]
    assert contract["success_signal"]
    assert contract["failure_signal"]
    assert contract["escalation_condition"]


def test_strategy_registry_matches_expected_strategies_for_chain():
    registry = StrategyRegistry.build_default()
    dispatcher = _DummyDispatcher()
    context = StrategyContext(
        dispatcher=dispatcher,
        target="http://ctf.local",
        page_features={
            "forms": [
                {
                    "action": "/login",
                    "method": "post",
                    "inputs": [
                        {"name": "username", "type": "text"},
                        {"name": "password", "type": "password"},
                        {"name": "bio", "type": "textarea"},
                    ],
                }
            ],
            "endpoints": ["/visit", "/admin"],
        },
        hint="",
        extras={"base_target": "http://ctf.local"},
    )

    sqli_kinds = [item.kind for item in registry.list_for_chain("sqli", context)]
    xss_kinds = [item.kind for item in registry.list_for_chain("xss", context)]
    web_kinds = [item.kind for item in registry.list_for_chain("web", context)]

    assert "auth_form_sqli" in sqli_kinds
    assert "xss_admin_bot_sid" in xss_kinds
    assert "backup_source_leak" in web_kinds
    assert "llm_driven_exploration" in web_kinds


def test_strategy_registry_matches_misc_artifact_forensics_for_attachment_surface():
    registry = StrategyRegistry.build_default()
    dispatcher = _DummyDispatcher()
    context = StrategyContext(
        dispatcher=dispatcher,
        target="http://ctf.local/challenge/",
        page_features={
            "raw_links": [
                "http://ctf.local/challenge.zip",
                "http://ctf.local/app.db",
            ],
            "endpoints": ["/challenge.zip", "/app.db"],
            "content": "directory listing app.db challenge.zip",
        },
        hint="",
        extras={},
    )

    misc_kinds = [item.kind for item in registry.list_for_chain("misc", context)]

    assert "artifact_forensics" in misc_kinds
    assert "llm_driven_exploration" in misc_kinds


def test_strategy_registry_strategy_is_applicable_respects_precondition():
    registry = StrategyRegistry.build_default()
    dispatcher = _DummyDispatcher()
    strategy = registry.get("php_unserialize_magic_method")
    assert strategy is not None

    not_ready = StrategyContext(
        dispatcher=dispatcher,
        target="http://ctf.local",
        page_features={},
        hint="",
        extras={},
    )
    ready = StrategyContext(
        dispatcher=dispatcher,
        target="http://ctf.local",
        page_features={},
        hint="",
        extras={"exploit_info": {"payloads": ["payload"]}},
    )

    assert strategy.is_applicable(not_ready) is False
    assert strategy.is_applicable(ready) is True


@pytest.mark.asyncio
async def test_strategy_registry_executes_php_unserialize_strategy():
    registry = StrategyRegistry.build_default()
    dispatcher = _DummyDispatcher()
    context = StrategyContext(
        dispatcher=dispatcher,
        target="http://ctf.local",
        page_features={},
        hint="",
        extras={
            "exploit_info": {"payloads": ["payload"]},
            "artifact_url": "http://ctf.local/www.zip",
        },
    )

    result = await registry.execute("php_unserialize_magic_method", context)

    assert result["target"] == "http://ctf.local"
    assert result["artifact_url"] == "http://ctf.local/www.zip"


def test_strategy_registry_contains_render_parameter_ssti_strategies():
    """Phase 7 §5: old monolithic strategies migrated to web-legacy; new pipeline in web chain."""
    registry = StrategyRegistry.build_default()

    # Phase 7: deprecated strategies moved to web-legacy — no longer auto-dispatched
    for kind in ("ssti_via_render_parameter", "tornado_ssti"):
        strategy = registry.get(kind)
        assert strategy is not None
        assert strategy.chain_name == "web-legacy", (
            f"{kind}: expected chain_name='web-legacy' after Phase 7 §5 migration"
        )
        assert strategy.precondition_description
        assert strategy.minimal_experiment
        assert strategy.success_signal

    # Phase 7: new three-stage pipeline replaces the above in the active web chain
    for kind in ("ssti_probe", "ssti_identify", "ssti_exploit"):
        strategy = registry.get(kind)
        assert strategy is not None, f"{kind} not registered after Phase 7 §5"
        assert strategy.chain_name == "web", (
            f"{kind}: expected chain_name='web' for Phase 7 §5 SSTI pipeline"
        )
        assert strategy.precondition_description
        assert strategy.minimal_experiment
        assert strategy.success_signal


def test_render_parameter_ssti_precondition_reads_redirect_surface_from_state():
    """Phase 7 §5: old SSTI strategies still resolvable under web-legacy chain (not web)."""
    registry = StrategyRegistry.build_default()
    dispatcher = _DummyDispatcher()
    dispatcher.state = SimpleNamespace(
        observations=[
            SimpleNamespace(
                value="Error",
                metadata={
                    "url": "http://ctf.local/file?filename=/flag.txt",
                    "final_url": "http://ctf.local/error?msg=Error",
                    "redirect_history": [
                        {
                            "status_code": 302,
                            "url": "http://ctf.local/file?filename=/flag.txt",
                            "location": "/error?msg=Error",
                        }
                    ],
                },
            )
        ]
    )
    context = StrategyContext(
        dispatcher=dispatcher,
        target="http://ctf.local",
        page_features={"raw_links": ["/file?filename=/flag.txt&filehash=deadbeef"]},
        hint="",
        extras={},
    )

    # Phase 7: old strategies now under web-legacy — must NOT appear in web dispatch list
    web_kinds = [item.kind for item in registry.list_for_chain("web", context)]
    assert "ssti_via_render_parameter" not in web_kinds, (
        "ssti_via_render_parameter should not auto-dispatch via web chain after Phase 7 §5"
    )
    assert "tornado_ssti" not in web_kinds, (
        "tornado_ssti should not auto-dispatch via web chain after Phase 7 §5"
    )

    # old strategies remain accessible via web-legacy for direct invocation
    legacy_kinds = [item.kind for item in registry.list_for_chain("web-legacy", context)]
    assert "ssti_via_render_parameter" in legacy_kinds
    assert "tornado_ssti" in legacy_kinds


def test_contact_report_chain_precondition_accepts_hidden_contact_surface_after_auth():
    registry = StrategyRegistry.build_default()
    dispatcher = _DummyDispatcher()
    context = StrategyContext(
        dispatcher=dispatcher,
        target="http://ctf.local",
        page_features={
            "content": "Store your URL for free Get Flag Logout",
            "html": '<a href="flag?token=deadbeefdeadbeefdeadbeefdeadbeef">Get Flag</a><a href="logout">Logout</a>',
            "raw_links": ["http://ctf.local/flag?token=deadbeefdeadbeefdeadbeefdeadbeef"],
            "endpoints": [],
            "forms": [],
        },
        hint="",
        extras={},
    )

    kinds = [item.kind for item in registry.list_for_chain("web", context)]

    assert "contact_report_chain" in kinds


def test_strategy_registry_exposes_unicode_numeric_form_bypass_before_backup_fallback():
    registry = StrategyRegistry.build_default()
    dispatcher = _DummyDispatcher()
    context = StrategyContext(
        dispatcher=dispatcher,
        target="http://ctf.local",
        page_features={
            "content": "Unicorn Shop Purchase Item ID Price Only one char allowed!",
            "html": """
                <form action="/charge" method="post">
                  <input name="id" type="text" />
                  <input name="price" type="text" />
                </form>
            """,
            "forms": [
                {
                    "action": "http://ctf.local/charge",
                    "method": "post",
                    "inputs": [
                        {"name": "id", "type": "text"},
                        {"name": "price", "type": "text"},
                    ],
                }
            ],
            "endpoints": ["/charge"],
        },
        hint="",
        extras={},
    )

    web_kinds = [item.kind for item in registry.list_for_chain("web", context)]

    assert "unicode_numeric_form_bypass" in web_kinds
    assert web_kinds.index("unicode_numeric_form_bypass") < web_kinds.index("backup_source_leak")


def test_strategy_registry_ssti_identify_requires_probe_hit_before_identify():
    registry = StrategyRegistry.build_default()
    dispatcher = _DummyDispatcher()
    dispatcher.state = SimpleNamespace(
        observations=[
            SimpleNamespace(
                kind="render_ssti_response",
                value="ORZ",
                source="ssti_probe",
                metadata={"payload": "{{7*7}}"},
            )
        ]
    )
    context = StrategyContext(
        dispatcher=dispatcher,
        target="http://ctf.local",
        page_features={"raw_links": ["http://ctf.local/error?msg=Error"]},
        hint="",
        extras={},
    )

    web_kinds = [item.kind for item in registry.list_for_chain("web", context)]
    assert "ssti_identify" not in web_kinds

    dispatcher.state.observations.append(
        SimpleNamespace(
            kind="ssti_probe_hit",
            value="{{7*7}}",
            source="ssti_probe",
            metadata={},
        )
    )

    web_kinds_after_hit = [item.kind for item in registry.list_for_chain("web", context)]
    assert "ssti_identify" in web_kinds_after_hit
