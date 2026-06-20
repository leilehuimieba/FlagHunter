"""能力层 capability registry 一致性守卫（ADR §5 / P5 命名·文档线收尾）。

这些守卫把"卡 B"对 cpa_modules m1–m6 的能力暴露对账固化为可执行断言：

1. 六个 m* 模块均按契约暴露 ``init_mN`` 与 ``is_mN_enabled``。
2. 六个 m* 模块均有非空模块级 docstring（DoD 硬性项）。
3. 每个模块 ``__all__`` 里声明的符号都真实可解析（无悬空导出）——
   该断言曾抓出 m5 把四个核心类只在 ``TYPE_CHECKING`` 下导入、
   运行时 ``import *`` 直接 AttributeError 的回归，现经 PEP 562
   ``__getattr__`` 修复。
4. m5 经 ``__getattr__`` 懒加载暴露的核心类确可被运行时导入。
"""
from __future__ import annotations

import importlib

import pytest

# (包后缀, 序号) —— 与 flaghunter/session/initializer.py 的 CPA 钩子一一对应
_CPA_MODULES = [
    ("m1_api_hub", 1),
    ("m2_ctf_kit", 2),
    ("m3_reporter", 3),
    ("m4_audit_guard", 4),
    ("m5_swarm_link", 5),
    ("m6_turbo", 6),
]


def _import(pkg: str):
    return importlib.import_module(f"flaghunter.cpa_modules.{pkg}")


@pytest.mark.parametrize("pkg, idx", _CPA_MODULES)
def test_module_exposes_init_and_enabled_contract(pkg, idx):
    mod = _import(pkg)
    init_name = f"init_m{idx}"
    enabled_name = f"is_m{idx}_enabled"
    assert callable(getattr(mod, init_name, None)), f"{pkg} 缺少 {init_name}"
    assert callable(getattr(mod, enabled_name, None)), f"{pkg} 缺少 {enabled_name}"


@pytest.mark.parametrize("pkg, idx", _CPA_MODULES)
def test_module_has_non_empty_docstring(pkg, idx):
    mod = _import(pkg)
    assert mod.__doc__ and mod.__doc__.strip(), f"{pkg} 缺少非空模块级 docstring"


@pytest.mark.parametrize("pkg, idx", _CPA_MODULES)
def test_all_exports_are_resolvable(pkg, idx):
    """__all__ 中的每个名字都必须可解析（含 PEP 562 懒加载），杜绝悬空导出。"""
    mod = _import(pkg)
    exported = getattr(mod, "__all__", [])
    assert exported, f"{pkg} 未声明 __all__"
    missing = [name for name in exported if not hasattr(mod, name)]
    assert not missing, f"{pkg}.__all__ 存在悬空导出: {missing}"


def test_m5_core_classes_are_importable_at_runtime():
    """m5 的四个核心类经 __getattr__ 懒加载后必须运行时可导入。"""
    m5 = _import("m5_swarm_link")
    for name in ("SharedBlackboard", "PheromoneRouter", "AgentMessenger", "ConsensusMechanism"):
        obj = getattr(m5, name)
        assert isinstance(obj, type), f"m5.{name} 应解析为类，实得 {obj!r}"

    with pytest.raises(AttributeError):
        _ = m5.__getattr__("definitely_not_a_real_attr")
