"""上线验收:端到端跑通三类 profile(CTF / 攻防演练 / 代码审计)。

doc《运行方式愿景与上线问题清单》线 210-211 的上线门:三类 profile 各跑通真实
样例,回归全绿 + import-linter / reachability / taxonomy 三道治理全 KEPT。

诚实边界(写进 docstring):这是 **in-session 确定性回归门**,不是 live 真跑——
- CTF / 攻防演练:用 replay harness 重驱真 ``CTFTaskDispatcher``(scripted 响应,
  无 live LLM/靶机);这正是 doc"回归全绿"门的含义。
- 代码审计:source_audit 是纯 Python(无 LLM/靶机),对**真实漏洞源码样例**真扫,
  端到端验白盒最小闭环(scan→可疑点→P12 攻击面面板)。
- live 真跑(live LLM 规划 + 网络靶机 + 真爆破)需用户 infra,见
  ``docs/dev/上线验收_三类profile_handoff.md`` 的可粘贴命令。

CTF profile(aggressive/url)的逐 fixture 复现门在 ``test_replay_harness.py``;
本文件聚焦此前从无端到端验收的攻防演练(conservative)与代码审计(source)两类。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.coordinator import CTFCoordinator
from flaghunter.agents.pa_agent.ctf_state import CTFState
from flaghunter.eval.replay import list_fixtures, load_fixture, run_replay
from flaghunter.knowledge.attack_surface import SurfaceKind, collect_attack_surfaces
from flaghunter.knowledge.profile import get_profile

_SOURCE_SAMPLE = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "samples"
    / "source_audit_app"
)


# ── 攻防演练 profile(pentest:conservative / blackbox)─────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("name", list_fixtures())
async def test_pentest_profile_does_not_break_recorded_solves(name):
    """conservative 激进度覆盖不得打断已录的(非 ssti/hash-gated)解链。

    把每条金标准 fixture 在 ``pentest`` profile(conservative)下重驱,断言仍复现。
    证明 profile覆盖 是真覆盖而非改名:换激进度不破坏不依赖直放 payload 的链。
    """
    result = await run_replay(load_fixture(name), profile="pentest")
    assert result.success, f"{name}: pentest(conservative) 重驱未解出(flag={result.actual_flag!r})"
    assert result.reproduced, (
        f"{name}: pentest 下期望 {result.expected_flag!r},实得 {result.actual_flag!r} —— "
        "conservative 覆盖打断了这条已解链"
    )


# ── 代码审计 profile(code_audit:conservative / source)─────────────────────

def _code_audit_dispatcher(sample_path: Path) -> SimpleNamespace:
    state = CTFState(target="local://audit", goal="audit")
    # profile覆盖:code_audit 的 entry_kind="source" 投到 state(P5 apply_profile)。
    state.apply_profile(get_profile("code_audit"))
    return SimpleNamespace(
        state=state,
        _challenge_context={"challengePath": str(sample_path)},
        _source_audit_findings=[],
    )


def test_code_audit_profile_entry_kind_is_source():
    # P5:code_audit profile 把 entry_kind 覆盖为 source(白盒进场)。
    disp = _code_audit_dispatcher(_SOURCE_SAMPLE)
    assert disp.state.entry_kind == "source"


def test_code_audit_scans_real_source_and_surfaces_suspicious_points():
    """白盒最小闭环端到端:profile→source 进场→scan→可疑点→P12 攻击面面板。

    串起 P5(profile 覆盖进场)+ P10/P11(source_audit 真扫真实漏洞样例)+
    P12(可疑点登记为攻击面)。纯 Python,无 LLM/靶机。
    """
    assert _SOURCE_SAMPLE.is_dir(), "缺少代码审计真样例源码"
    disp = _code_audit_dispatcher(_SOURCE_SAMPLE)

    CTFCoordinator()._apply_source_audit_contract(disp)

    findings = "\n".join(disp._source_audit_findings)
    assert disp._source_audit_findings, "code_audit 应在真实样例上扫出可疑点"
    assert "CWE-502" in findings  # pickle / yaml 反序列化
    assert "CWE-78" in findings   # subprocess shell 执行
    assert "CWE-89" in findings   # SQL 字符串拼接
    # source_audit observation 记入 state
    assert any(o.kind == "source_audit" for o in disp.state.observations)

    # P12:可疑点登记进攻击面面板(source kind)。
    report = collect_attack_surfaces(disp.state)
    source_surfaces = [s for s in report["surfaces"] if s["kind"] == SurfaceKind.SOURCE]
    assert source_surfaces, "P12 攻击面面板应登记 source 可疑点"


def test_ctf_profile_does_not_scan_source_byte_identical():
    # 对照:url 进场(CTF)不触发源码扫描 → 与 CTF 字节级一致。
    state = CTFState(target="http://t", goal="solve")
    state.apply_profile(get_profile("ctf"))
    disp = SimpleNamespace(
        state=state,
        _challenge_context={"challengePath": str(_SOURCE_SAMPLE)},
        _source_audit_findings=[],
    )
    CTFCoordinator()._apply_source_audit_contract(disp)
    assert disp._source_audit_findings == []
    assert not any(o.kind == "source_audit" for o in disp.state.observations)
