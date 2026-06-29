"""成本分层路由:低思考任务(light 档)走 cheap-tagged provider,其余走主力。

对应 provider 管理需求 #7:"有一些思考程度低的可以使用一些便宜的来完成"。
规则:只有 light 档(tool_parse/summary/formatting)分流到 tags 含 cheap/light 的
provider;default/medium/heavy 保持原优先级顺序(主力)。未打 tag 的池字节级一致。
"""

import pytest

from flaghunter.cpa_modules.m1_api_hub.models import ProviderConfig
from flaghunter.cpa_modules.m1_api_hub.provider_manager import ProviderManager


def _p(pid: str, model: str, priority: int, tags: list[str]) -> ProviderConfig:
    return ProviderConfig(
        id=pid, name=pid, model=model,
        api_base="http://x/v1", api_key="k",
        priority=priority, tags=tags,
    )


@pytest.mark.asyncio
async def test_light_task_routes_to_cheap_provider():
    pm = ProviderManager()
    await pm.register_provider(_p("primary", "openai/gpt-5.4", 1, ["heavy", "primary"]))
    await pm.register_provider(_p("cheap", "openai/mimo-v2.5-pro", 4, ["light", "cheap"]))

    # 高思考 / 默认 → 主力
    for hint in ("planning", "analysis", "exploitation", "default"):
        p = await pm.select_provider(model_hint="", task_hint=hint)
        assert p.id == "primary", f"{hint} 应走主力"

    # 低思考 → 便宜模型
    for hint in ("tool_parse", "summary", "formatting"):
        p = await pm.select_provider(model_hint="", task_hint=hint)
        assert p.id == "cheap", f"{hint} 应走便宜模型"


@pytest.mark.asyncio
async def test_cheapest_by_priority_among_tagged():
    pm = ProviderManager()
    await pm.register_provider(_p("primary", "openai/gpt-5.4", 1, ["heavy"]))
    await pm.register_provider(_p("cheap-a", "openai/mimo", 4, ["cheap"]))
    await pm.register_provider(_p("cheap-b", "openai/flash", 5, ["cheap"]))
    p = await pm.select_provider(model_hint="", task_hint="tool_parse")
    assert p.id == "cheap-a"  # 同档按 priority 取最高


@pytest.mark.asyncio
async def test_byte_identical_when_no_cheap_tags():
    # 未打 tag 的池:light 任务回落到原优先级顺序,行为不变。
    pm = ProviderManager()
    await pm.register_provider(_p("a", "openai/gpt-5.4", 1, []))
    await pm.register_provider(_p("b", "openai/mimo", 4, []))
    p = await pm.select_provider(model_hint="", task_hint="tool_parse")
    assert p.id == "a"
