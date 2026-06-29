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

import pytest

from flaghunter.eval.replay import list_fixtures, load_fixture, run_replay


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
