"""回放 harness 自测：每条金标准 fixture 都应被确定性复现。

这是确定性回归门的最小落地（基准_验证与解题判定 S5）：策略/分发改动后跑本测试，
任何已录 fixture 不再复现即 FAIL —— 把"改动悄悄打断已解题"挡在合并前。
"""

import pytest

from flaghunter.eval.replay import list_fixtures, load_fixture, run_replay


def test_at_least_two_golden_fixtures():
    assert len(list_fixtures()) >= 2, "回放语料至少应有 2 条金标准 fixture"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list_fixtures())
async def test_fixture_reproduces_solve(name):
    fixture = load_fixture(name)
    result = await run_replay(fixture)
    assert result.success, f"{name}: 回放未解出（flag={result.actual_flag!r}）"
    assert result.reproduced, (
        f"{name}: 期望 {result.expected_flag!r}，实得 {result.actual_flag!r} —— "
        "策略/分发改动可能打断了这条已解链"
    )
