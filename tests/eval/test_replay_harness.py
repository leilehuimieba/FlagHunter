"""回放 harness 自测：每条金标准 fixture 都应被确定性复现。

这是确定性回归门的最小落地（基准_验证与解题判定 S5）：策略/分发改动后跑本测试，
任何已录 fixture 不再复现即 FAIL —— 把"改动悄悄打断已解题"挡在合并前。
"""

from pathlib import Path

import pytest

from flaghunter.eval.replay import list_fixtures, load_fixture, run_replay

# Real loot subdirs the audit stores default to when no *_root is passed. The
# replay harness must redirect all three into a TemporaryDirectory; this guards
# against regressions that let session_ledger/artifact_registry/checkpoint
# bleed into the real loot/ tree during replay.
_REAL_LOOT_STORE_DIRS = (
    Path("loot") / "session_ledgers",
    Path("loot") / "artifact_registry",
    Path("loot") / "checkpoints",
)


def _snapshot_store_dirs() -> dict[Path, set[str]]:
    snap: dict[Path, set[str]] = {}
    for d in _REAL_LOOT_STORE_DIRS:
        snap[d] = {p.name for p in d.rglob("*")} if d.exists() else set()
    return snap


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


@pytest.mark.asyncio
async def test_replay_does_not_touch_real_loot_stores():
    """回放必须把 session_ledger/artifact_registry/checkpoint 全部重定向到临时目录。

    跑 replay 前后对真实 loot/ 三个 store 目录快照（文件名集合，目录不存在视为空集），
    断言无新增文件——否则说明落盘隔离漏了某个 store。
    """
    fixtures = list_fixtures()
    assert fixtures, "需要至少 1 条 fixture 才能验证落盘隔离"

    before = _snapshot_store_dirs()
    await run_replay(load_fixture(fixtures[0]))
    after = _snapshot_store_dirs()

    for d in _REAL_LOOT_STORE_DIRS:
        new_entries = after[d] - before[d]
        assert not new_entries, (
            f"回放在真实 {d} 留下了新文件 {sorted(new_entries)} —— 落盘隔离漏了该 store"
        )
