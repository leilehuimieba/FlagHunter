"""守卫测试：锁定 initializer CPA 钩子段的门控方式统一且等价（卡 G）。

背景
----
``flaghunter/session/initializer.py`` 的 CPA M1..M6 钩子段负责决定是否调用各模块的
``init_mX()``。卡 G 把 M3/M4/M6 的「直读 env」门控统一为调用模块的
``is_mX_enabled()``（与 M1 标杆写法对齐），M2/M5 因 ``is_mX_enabled`` 额外要求模块
已初始化（自锁陷阱），必须保留直读 env。

本测试锁三件事：
  (a) M1/M3/M4/M6 在钩子段经 ``is_mX_enabled()`` 求值，且 M3/M4/M6 无残留直读门控；
      M2/M5 仍为直读 env（不被误统一）。
  (b) M3/M4/M6 的 ``is_mX_enabled()`` 为纯 env 检查，设/清 env 后真值与门控行为一致。
  (c) M2/M5 的 ``is_mX_enabled()`` 依赖初始化标志，固化「为何不统一」——若用作 init 前
      门控会自锁。M1/M3/M4/M6 的 ``is_mX_enabled()`` 不依赖初始化标志，可安全用作门控。
"""

import inspect
import re
from pathlib import Path

import pytest

from flaghunter.cpa_modules.m1_api_hub import is_m1_enabled
from flaghunter.cpa_modules.m2_ctf_kit import is_m2_enabled
from flaghunter.cpa_modules.m3_reporter import is_m3_enabled
from flaghunter.cpa_modules.m4_audit_guard import is_m4_enabled
from flaghunter.cpa_modules.m5_swarm_link import is_m5_enabled
from flaghunter.cpa_modules.m6_turbo import is_m6_enabled

import flaghunter.session.initializer as initializer


# ---------------------------------------------------------------------------
# 钩子段源码切片
# ---------------------------------------------------------------------------

def _hook_segment() -> str:
    """提取 initializer.py 中 CPA M1 HOOK BEGIN .. M6 HOOK END 之间的源码。"""
    src = Path(initializer.__file__).read_text(encoding="utf-8")
    begin = src.index("# === CPA M1 HOOK BEGIN ===")
    end = src.index("# === CPA M6 HOOK END ===") + len("# === CPA M6 HOOK END ===")
    return src[begin:end]


def _module_subsegment(module: str) -> str:
    """提取单个模块 `# === CPA Mx HOOK BEGIN/END ===` 之间的源码。"""
    seg = _hook_segment()
    begin = seg.index(f"# === CPA {module} HOOK BEGIN ===")
    end = seg.index(f"# === CPA {module} HOOK END ===")
    return seg[begin:end]


# (env_key, env_default) — 与 initializer 现状逐字一致
ENV_INFO = {
    "M1": ("CPA_M1_API_HUB", None),       # 含 legacy 回退，行为不在 (b) 参数化范围
    "M2": ("CPA_M2_CTF_KIT", "true"),
    "M3": ("CPA_M3_REPORTER", "true"),
    "M4": ("CPA_M4_AUDIT_GUARD", "true"),
    "M5": ("CPA_M5_SWARM_LINK", "false"),
    "M6": ("CPA_M6_TURBO", "true"),
}

IS_ENABLED = {
    "M1": is_m1_enabled,
    "M2": is_m2_enabled,
    "M3": is_m3_enabled,
    "M4": is_m4_enabled,
    "M5": is_m5_enabled,
    "M6": is_m6_enabled,
}

UNIFIED = ["M1", "M3", "M4", "M6"]   # 经 is_mX_enabled() 门控
DIRECT_ENV = ["M2", "M5"]            # 保留直读 env（自锁例外）


# ---------------------------------------------------------------------------
# (a) 门控方式：统一 vs 直读 env
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module", UNIFIED)
def test_unified_modules_gate_via_is_enabled(module):
    """M1/M3/M4/M6 钩子段以 `if is_mX_enabled():` 求值。"""
    sub = _module_subsegment(module)
    fn = f"is_m{module[1:]}_enabled"
    assert f"if {fn}():" in sub, f"{module} 应经 {fn}() 门控，实际:\n{sub}"


@pytest.mark.parametrize("module", ["M3", "M4", "M6"])
def test_unified_modules_have_no_residual_direct_env(module):
    """M3/M4/M6 钩子段不得残留 `os.getenv("<KEY>"` 作为门控直读。"""
    sub = _module_subsegment(module)
    key = ENV_INFO[module][0]
    assert f'os.getenv("{key}"' not in sub, f"{module} 仍有残留直读 env:\n{sub}"


@pytest.mark.parametrize("module", DIRECT_ENV)
def test_direct_env_modules_retain_env_gating(module):
    """M2/M5 必须保留直读 env，且不得被误统一为 is_mX_enabled() 门控。"""
    sub = _module_subsegment(module)
    key = ENV_INFO[module][0]
    fn = f"is_m{module[1:]}_enabled"
    assert f'os.getenv("{key}"' in sub, f"{module} 应保留直读 env:\n{sub}"
    assert f"if {fn}():" not in sub, f"{module} 不应用 {fn}() 门控（自锁陷阱）:\n{sub}"


# ---------------------------------------------------------------------------
# (b) M3/M4/M6 行为等价：is_mX_enabled() 真值随 env 变化
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module", ["M3", "M4", "M6"])
@pytest.mark.parametrize(
    "env_value,expected",
    [
        (None, True),       # 未设 → 默认启用
        ("true", True),
        ("TRUE", True),     # 大小写不敏感
        ("false", False),
    ],
)
def test_pure_env_modules_behaviour(module, env_value, expected, monkeypatch):
    """设/清 env 后 is_mX_enabled() 真值与预期一致（门控即此函数，故行为等价）。"""
    key = ENV_INFO[module][0]
    if env_value is None:
        monkeypatch.delenv(key, raising=False)
    else:
        monkeypatch.setenv(key, env_value)
    assert IS_ENABLED[module]() is expected


# ---------------------------------------------------------------------------
# (c) 固化「为何不统一」：M2/M5 的 is_mX_enabled 依赖初始化标志
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module", DIRECT_ENV)
def test_direct_env_modules_is_enabled_depends_on_init_flag(module):
    """M2/M5 的 is_mX_enabled 引用初始化标志 → 不能用作 init 前门控（会自锁）。"""
    src = inspect.getsource(IS_ENABLED[module])
    assert re.search(r"_[Ii]nitialized\b|_INITIALIZED\b", src), (
        f"{module} 的 is_enabled 预期依赖初始化标志，实际:\n{src}"
    )


@pytest.mark.parametrize("module", UNIFIED)
def test_unified_modules_is_enabled_is_pure_env(module):
    """M1/M3/M4/M6 的 is_mX_enabled 不引用初始化标志 → 可安全用作门控。"""
    src = inspect.getsource(IS_ENABLED[module])
    assert not re.search(r"_[Ii]nitialized\b|_INITIALIZED\b", src), (
        f"{module} 的 is_enabled 不应依赖初始化标志，实际:\n{src}"
    )
