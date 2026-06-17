from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import flaghunter.cpa_modules.m1_api_hub as m1_api_hub
from flaghunter.cpa_modules.m1_api_hub.failover_monitor import FailoverMonitor
from flaghunter.cpa_modules.m1_api_hub.models import ProviderConfig
from flaghunter.cpa_modules.m1_api_hub.models import HealthCheckResult, ProviderState
from flaghunter.cpa_modules.m1_api_hub.provider_manager import ProviderManager


def test_is_m1_enabled_honors_legacy_switch_when_primary_switch_missing(monkeypatch):
    monkeypatch.delenv("CPA_M1_API_HUB", raising=False)
    monkeypatch.setenv("CPA_M1_ENABLED", "false")

    assert m1_api_hub.is_m1_enabled() is False


@pytest.mark.asyncio
async def test_init_m1_starts_failover_monitor(monkeypatch):
    started = {"value": False}

    class _FakeMonitor:
        def __init__(self, provider_manager, config):
            self.provider_manager = provider_manager
            self.config = config

        async def start(self):
            started["value"] = True

    config = SimpleNamespace(
        daily_budget_usd=5.0,
        budget_alert_threshold=0.8,
        health_check_interval=30,
        health_check_timeout=10,
        fail_threshold=3,
        recovery_check_interval=60,
        recovery_confirm_requests=2,
        providers=[
            ProviderConfig(
                id="primary",
                name="Primary",
                model="gpt-4o",
                api_base="https://primary.example/v1",
                api_key="primary-key",
                priority=1,
            )
        ],
    )

    monkeypatch.setenv("CPA_M1_API_HUB", "true")
    monkeypatch.setattr(m1_api_hub, "_provider_manager", None)
    monkeypatch.setattr(m1_api_hub, "_cost_tracker", None)
    monkeypatch.setattr(m1_api_hub, "_failover_monitor", None)
    monkeypatch.setattr(m1_api_hub, "_initialized", False)
    monkeypatch.setattr(m1_api_hub, "load_m1_config_from_env", lambda: config)
    monkeypatch.setattr(m1_api_hub, "FailoverMonitor", _FakeMonitor)

    await m1_api_hub.init_m1()

    assert started["value"] is True
    assert m1_api_hub.get_provider_manager().get_provider("primary") is not None


@pytest.mark.asyncio
async def test_failover_monitor_recovers_down_provider(monkeypatch):
    pm = ProviderManager()
    await pm.register_provider(
        ProviderConfig(
            id="primary",
            name="Primary",
            model="gpt-4o",
            api_base="https://primary.example/v1",
            api_key="primary-key",
            priority=1,
        )
    )
    pm.mark_provider_status("primary", ProviderState.DOWN, "quota")

    monitor = FailoverMonitor(
        provider_manager=pm,
        config={
            "health_check_interval": 3600,
            "recovery_check_interval": 0.01,
            "recovery_confirm_requests": 2,
        },
    )
    transitions: list[tuple[str, str]] = []
    monitor.on_state_change(lambda provider_id, old, new: transitions.append((old.value, new.value)))

    first_probe = {"done": False}
    first_probe_seen = asyncio.Event()
    allow_second_probe = asyncio.Event()

    async def _probe(provider_id: str):
        if not first_probe["done"]:
            first_probe["done"] = True
            first_probe_seen.set()
            return HealthCheckResult(
                provider_id=provider_id,
                success=True,
                response_time_ms=5,
            )
        await allow_second_probe.wait()
        return HealthCheckResult(
            provider_id=provider_id,
            success=True,
            response_time_ms=5,
        )

    async def _verify(provider_id: str) -> bool:
        return True

    monkeypatch.setattr(monitor, "_probe", _probe)
    monkeypatch.setattr(monitor, "_verify_with_real_request", _verify)

    await monitor.start()
    await first_probe_seen.wait()
    await asyncio.sleep(0.02)
    assert pm.get_status("primary").state == ProviderState.RECOVERING

    allow_second_probe.set()
    await asyncio.sleep(0.05)
    await monitor.stop()

    assert pm.get_status("primary").state == ProviderState.HEALTHY
    assert ("down", "recovering") in transitions
    assert ("recovering", "healthy") in transitions
