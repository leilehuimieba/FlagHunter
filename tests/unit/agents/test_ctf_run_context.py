from __future__ import annotations

import pytest

from flaghunter.agents.pa_agent.coordinator import (
    CoordinatorDispatcherServices,
    RunContext,
)


def _build_protocol_satisfying_namespace() -> dict:
    """Build a class namespace exposing every ``CoordinatorDispatcherServices``
    member as a *real* attribute (data members → sentinel value, method members
    → callable). Python 3.12's runtime ``isinstance`` for protocols uses
    ``getattr_static`` (which ignores ``__getattr__``), so members must be
    statically discoverable for the Protocol's ``isinstance`` to succeed.
    """
    non_callable = CoordinatorDispatcherServices.__non_callable_proto_members__
    ns: dict = {}
    for attr in CoordinatorDispatcherServices.__protocol_attrs__:
        if attr in non_callable:
            ns[attr] = None  # placeholder data member; overwritten in __init__
        else:
            ns[attr] = lambda self, *a, **k: None
    return ns


_FakeDispatcher = type(
    "_FakeDispatcher", (), _build_protocol_satisfying_namespace()
)


def _make_ctx() -> tuple[RunContext, object]:
    dispatcher = _FakeDispatcher()
    # Real run-state-ish sentinels the proxy tests poke at.
    dispatcher.state = object()
    dispatcher.misc = "initial"
    return RunContext(dispatcher), dispatcher


# ── DoD ④: ctx.dispatcher property 仍返回真身 ──
def test_dispatcher_property_returns_real_object():
    ctx, dispatcher = _make_ctx()
    assert ctx.dispatcher is dispatcher


# ── DoD ①: ctx.state 读仍落 dispatcher.state(同一引用) ──
def test_state_read_delegates_to_dispatcher_same_identity():
    ctx, dispatcher = _make_ctx()
    assert ctx.state is dispatcher.state


# ── DoD ①: ctx.state 写仍穿透到 dispatcher.state ──
def test_state_write_passes_through_to_dispatcher():
    ctx, dispatcher = _make_ctx()
    new_state = object()
    ctx.state = new_state
    assert dispatcher.state is new_state
    assert ctx.state is new_state


# ── DoD ②: 任意非白名单属性 get 代理 dispatcher ──
def test_arbitrary_attribute_get_delegates():
    ctx, dispatcher = _make_ctx()
    assert ctx.misc == "initial"
    dispatcher.misc = "changed"
    assert ctx.misc == "changed"


# ── DoD ②: 任意非白名单属性 set 代理 dispatcher ──
def test_arbitrary_attribute_set_delegates():
    ctx, dispatcher = _make_ctx()
    ctx.misc = "via_ctx"
    assert dispatcher.misc == "via_ctx"
    # 没有在 ctx 实例自身建立影子字段
    assert "misc" not in ctx.__dict__


# ── DoD ③: L3a 不改变 isinstance(ctx, Protocol) 行为 vs 纯代理 ──
# Python 3.12 的 runtime_checkable Protocol 实例检查走 getattr_static(忽略
# __getattr__),故透明代理对象 ctx 本身【不】结构化满足该 Protocol——这在
# L3a 前后完全一致(空白名单零承载),不是 L3a 引入的回归。真正承载 Protocol
# 契约的是 ctx.dispatcher(传给 Protocol 类型形参的真身),它满足 isinstance。
def test_protocol_isinstance_behavior_preserved():
    ctx, dispatcher = _make_ctx()
    # 真身 dispatcher 满足契约(传给 Protocol 形参的就是它)
    assert isinstance(dispatcher, CoordinatorDispatcherServices)
    assert isinstance(ctx.dispatcher, CoordinatorDispatcherServices)
    # ctx 代理对象:getattr_static 看不穿 __getattr__,故 False——纯代理时即如此,
    # L3a 空白名单未改变这一点(行为等价)。
    assert isinstance(ctx, CoordinatorDispatcherServices) is False


# ── L3a 机制坐实:白名单为空 ──
def test_own_fields_is_empty():
    assert RunContext._OWN_FIELDS == frozenset()


# ── 内部名不被代理吞掉:_dispatcher 经 property 取真身,不递归 ──
def test_internal_dispatcher_name_not_proxied():
    ctx, dispatcher = _make_ctx()
    # _dispatcher 直接读实例属性,命中 object.__setattr__ 写入的值
    assert object.__getattribute__(ctx, "_dispatcher") is dispatcher


# ── 空白名单下行为等价纯代理:写一个新名字穿透到 dispatcher ──
def test_new_attribute_write_creates_on_dispatcher_only():
    ctx, dispatcher = _make_ctx()
    ctx.brand_new = 42
    assert dispatcher.brand_new == 42
    assert "brand_new" not in ctx.__dict__


# ── __getattr__ 对内部名短路:即便 _dispatcher 缺位也抛 AttributeError 而非递归 ──
def test_getattr_internal_name_shortcircuits():
    ctx = object.__new__(RunContext)  # 不调 __init__,_dispatcher 未就绪
    with pytest.raises(AttributeError):
        # 经 __getattr__ 显式短路,抛 AttributeError(不会无限递归)
        ctx.__getattr__("_dispatcher")
    with pytest.raises(AttributeError):
        ctx.__getattr__("_OWN_FIELDS")
