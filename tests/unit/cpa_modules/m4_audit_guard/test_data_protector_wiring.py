"""回归测试 — 锁定 M4 init_m4 中 DataProtector 的 mask_ips/总开关接线一致性。

背景(卡 D)：init_m4 历史上写成 ``mask_ips=not mask_sensitive``，使
``CPA_M4_MASK_SENSITIVE=true``(总开关打开)时 IP 反而不脱敏、=false 时反而脱敏，
与"敏感信息脱敏总开关"语义相悖。已修正为 ``mask_ips=mask_sensitive``，与
``mask_emails`` 对齐。本测试锁定该一致性，防止回归。
"""
from __future__ import annotations

import importlib

import pytest

import flaghunter.cpa_modules.m4_audit_guard as m4

_SAMPLE = "host 192.168.1.100 user a@b.com flag{secret}"


def _reset_m4_singletons() -> None:
    """把 M4 模块级单例重置回未初始化，允许以不同 env 重新 init。"""
    m4._initialized = False
    m4._audit_logger = None
    m4._roe_engine = None
    m4._scope_enforcer = None
    m4._approval_gate = None
    m4._data_protector = None


@pytest.fixture(autouse=True)
def _isolate_m4_state(tmp_path, monkeypatch):
    """每个用例：隔离日志目录、确保总开关开启、重置单例，跑完再重置。"""
    monkeypatch.setenv("CPA_M4_AUDIT_GUARD", "true")
    monkeypatch.setenv("CPA_M4_LOG_DIR", str(tmp_path / "audit"))
    _reset_m4_singletons()
    yield
    _reset_m4_singletons()


# ── 直接验证 DataProtector 的 mask_ips 真实语义(True=脱敏, False=保留) ──

def test_data_protector_mask_ips_true_masks_ip():
    dp = m4.DataProtector(mask_ips=True)
    out = dp.mask("192.168.1.100")
    assert "192.168.1.100" not in out
    assert "192.168.x.x" == out


def test_data_protector_mask_ips_false_keeps_ip():
    dp = m4.DataProtector(mask_ips=False)
    assert dp.mask("192.168.1.100") == "192.168.1.100"


# ── 锁定 init_m4 接线：IP 跟随总开关 mask_sensitive，与 email 同向 ──

async def test_init_m4_mask_sensitive_true_masks_ip(monkeypatch):
    monkeypatch.setenv("CPA_M4_MASK_SENSITIVE", "true")
    await m4.init_m4()
    dp = m4.get_data_protector()
    masked = dp.mask(_SAMPLE)
    # 总开关打开：IP 与邮箱都应被脱敏
    assert "192.168.1.100" not in masked, "总开关=true 时 IP 必须被遮蔽"
    assert "192.168.x.x" in masked
    assert "a@b.com" not in masked, "总开关=true 时邮箱必须被遮蔽"


async def test_init_m4_mask_sensitive_false_keeps_ip(monkeypatch):
    monkeypatch.setenv("CPA_M4_MASK_SENSITIVE", "false")
    await m4.init_m4()
    dp = m4.get_data_protector()
    masked = dp.mask(_SAMPLE)
    # 总开关关闭：IP 与邮箱都应原样保留(不再"取反"脱敏 IP)
    assert "192.168.1.100" in masked, "总开关=false 时 IP 必须原样保留"
    assert "a@b.com" in masked, "总开关=false 时邮箱必须原样保留"


async def test_init_m4_ip_and_email_follow_same_switch(monkeypatch):
    """IP 与 email 必须同向跟随总开关——杜绝 mask_ips 再次被写成取反。"""
    monkeypatch.setenv("CPA_M4_MASK_SENSITIVE", "true")
    await m4.init_m4()
    cfg = m4.get_data_protector()._config
    assert cfg["ip_address"] == cfg["email"] is True
