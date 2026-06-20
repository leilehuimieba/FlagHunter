"""回归测试 — 锁定 M6 死代码移除与 _wrap_tool 登记语义。

背景(卡 F)：M6 ``apply_turbo()`` 自诞生起在工具执行层零调用点（"透明 wrapper
自动挂载"始终未接线），其私有辅助 ``_make_cache_key`` 仅服务于它。该死代码已移除。
``_wrap_tool()`` 保留——它有真实调用方（``/turbo wrap`` 命令的 ``_wrap_add``），
但仅把工具名登记进 ``_wrapped_tools`` 供查询/展示，不替换任何工具函数。

本测试锁定：
  1. 死代码不复活：``apply_turbo`` / ``_make_cache_key`` 不再存在，``__all__`` 不再导出。
  2. 模块仍可正常 import、子模块类型/Getter/状态函数齐备。
  3. ``init_m6`` 行为不回归：按总开关门控、登记 default_tools、防重复初始化。
  4. ``_wrap_tool`` 登记语义：只登记可加速工具名，不可加速的工具不进集合。
"""
from __future__ import annotations

import pytest

import flaghunter.cpa_modules.m6_turbo as m6


def _reset_m6_singletons() -> None:
    """把 M6 模块级单例重置回未初始化，允许以不同 env 重新 init。"""
    m6._cache = None
    m6._scanner = None
    m6._loader = None
    m6._optimizer = None
    m6._initialized = False
    m6._wrapped_tools = set()


@pytest.fixture(autouse=True)
def _isolate_m6_state(monkeypatch):
    """每个用例：默认开启总开关、重置单例，跑完再重置。"""
    monkeypatch.setenv("CPA_M6_TURBO", "true")
    # 避免后台内存监控协程：把内存上限设为 0，init 不会 create_task。
    monkeypatch.setenv("CPA_M6_MEMORY_LIMIT_MB", "0")
    _reset_m6_singletons()
    yield
    _reset_m6_singletons()


# ── 1. 死代码不复活 ──────────────────────────────────────────────────────
def test_apply_turbo_removed():
    """apply_turbo 已删除：模块上无此属性，__all__ 不导出。"""
    assert not hasattr(m6, "apply_turbo")
    assert "apply_turbo" not in m6.__all__


def test_make_cache_key_removed():
    """apply_turbo 的私有辅助 _make_cache_key 一并移除。"""
    assert not hasattr(m6, "_make_cache_key")


# ── 2. 模块仍正常 import / 公共面齐备 ─────────────────────────────────────
def test_public_surface_intact():
    """死代码移除后，M6 公共 API 不受影响。"""
    for name in (
        "init_m6", "shutdown_m6", "get_stats",
        "get_cache", "get_scanner", "get_optimizer",
        "is_m6_enabled", "is_turbo_active",
    ):
        assert name in m6.__all__, f"{name} 应仍在 __all__"
        assert hasattr(m6, name), f"{name} 应仍可访问"


# ── 3. init_m6 行为不回归 ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_init_m6_registers_default_tools():
    """init_m6 成功后登记 4 个默认工具，且 is_turbo_active 据此判定。"""
    ok = await m6.init_m6()
    assert ok is True
    assert m6._initialized is True
    assert {"nmap", "sqlmap", "hydra", "nikto"} <= m6._wrapped_tools
    assert m6.is_turbo_active("nmap") is True
    assert m6.is_turbo_active("not-a-real-tool") is False
    await m6.shutdown_m6()
    assert m6._initialized is False
    assert m6._wrapped_tools == set()


@pytest.mark.asyncio
async def test_init_m6_gated_off(monkeypatch):
    """总开关关闭时 init_m6 返回 False，不登记任何工具。"""
    monkeypatch.setenv("CPA_M6_TURBO", "false")
    ok = await m6.init_m6()
    assert ok is False
    assert m6._initialized is False
    assert m6._wrapped_tools == set()


@pytest.mark.asyncio
async def test_init_m6_idempotent():
    """重复 init_m6 不重复初始化（防重复初始化分支）。"""
    assert await m6.init_m6() is True
    assert await m6.init_m6() is True  # 第二次走 _initialized 短路
    assert m6._initialized is True
    await m6.shutdown_m6()


# ── 4. _wrap_tool 登记语义 ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_wrap_tool_only_registers_accelerable(monkeypatch):
    """_wrap_tool 只登记可缓存/可并发的工具名；不可加速的不进集合。"""
    await m6.init_m6()
    # gobuster 在并发列表内 → 可登记
    m6._wrap_tool("gobuster")
    assert "gobuster" in m6._wrapped_tools
    # 一个不在任何加速列表里的工具名 → 不登记
    m6._wrap_tool("totally-unknown-tool")
    assert "totally-unknown-tool" not in m6._wrapped_tools
    await m6.shutdown_m6()
