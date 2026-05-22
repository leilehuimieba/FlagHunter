import pytest

from cpa_modules.m1_api_hub.model_router import route
from cpa_modules.m1_api_hub.models import ProviderConfig
from cpa_modules.m1_api_hub.provider_manager import ProviderManager


def test_route_prefers_light_model_for_tool_parse():
    model = route("tool_parse", ["anthropic", "openai"])
    assert "haiku" in model.lower() or "mini" in model.lower()


def test_route_prefers_heavy_model_for_exploitation():
    model = route("exploitation", ["anthropic"])
    assert "opus" in model.lower() or "sonnet" in model.lower()


def test_route_falls_back_to_openai_when_only_openai_available():
    model = route("planning", ["openai"])
    assert "gpt-4o" in model.lower()


@pytest.mark.asyncio
async def test_select_provider_prefers_task_hint_routed_model():
    manager = ProviderManager()
    await manager.register_provider(
        ProviderConfig(
            id="light_openai",
            name="Light OpenAI",
            model="openai/gpt-4o-mini",
            api_base="https://api.openai.com/v1",
            api_key="sk-light",
            priority=1,
        )
    )
    await manager.register_provider(
        ProviderConfig(
            id="heavy_claude",
            name="Heavy Claude",
            model="openai/claude-sonnet-4",
            api_base="https://api.proxy.local/v1",
            api_key="sk-heavy",
            priority=2,
        )
    )

    selected = await manager.select_provider(task_hint="planning")
    assert selected.id == "heavy_claude"

