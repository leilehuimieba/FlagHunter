"""回归测试 — 锁定 PheromoneRouter 两处 bug 修复（卡 S1+S2）。

S1（运行时崩溃）：``get_prioritized_queue`` 用 heapq 入堆元组
``(-final_score, prio)``，但 ``TaskPriority`` 是无 ``order=True`` 的
dataclass，不可比较。两 target 同 ``final_score`` 时 heapq 会回落去比较
元组第二元素（TaskPriority）→ ``TypeError``。默认 base_priority=5、无信息素
时全部同分，极易触发。修复：入堆元组加单调 tie-breaker idx
``(-score, idx, prio)``，同分不再去比较 TaskPriority，且排序稳定（FIFO）。

S2（配置失效）：``PheromoneTrail.is_active`` 写死阈值 0.1，而
``PheromoneRouter`` 持有可配置 ``self._threshold``（evaporate / get_stats
都用它）。调用方传非 0.1 阈值时，活跃判定与蒸发逻辑判定不一致。修复：
``get_active_trails`` 改用 ``t.is_active_above(self._threshold)``。
"""
from __future__ import annotations

import pytest

from flaghunter.cpa_modules.m5_swarm_link.pheromone_router import (
    PheromoneRouter,
    PheromoneTrail,
    TaskPriority,
)


# --------------------------------------------------------------------------
# S1: 同 final_score 多 target 入队/取队不崩
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prioritized_queue_equal_scores_does_not_crash():
    """全部 target 同分（默认 base_priority=5、无信息素）时不应 TypeError。"""
    router = PheromoneRouter()
    targets = ["a", "b", "c", "d", "e"]

    queue = await router.get_prioritized_queue(targets)

    # 不崩，且全部 target 都在结果里
    assert len(queue) == len(targets)
    assert all(isinstance(p, TaskPriority) for p in queue)
    assert {p.target for p in queue} == set(targets)
    # 全部同分
    scores = [p.final_score for p in queue]
    assert len(set(scores)) == 1


@pytest.mark.asyncio
async def test_prioritized_queue_equal_scores_stable_order():
    """同分时排序稳定：按入队（targets 列表）顺序 FIFO。"""
    router = PheromoneRouter()
    targets = ["t0", "t1", "t2", "t3"]

    queue = await router.get_prioritized_queue(targets)

    assert [p.target for p in queue] == targets


@pytest.mark.asyncio
async def test_prioritized_queue_orders_by_score_desc():
    """混合分数：高分在前；同分段内保持稳定顺序。"""
    router = PheromoneRouter()
    # high 沉积大量信息素 → 更高 final_score；其余两个同分
    await router.deposit("high", strength=100.0)
    targets = ["low1", "high", "low2"]

    queue = await router.get_prioritized_queue(targets)

    assert queue[0].target == "high"
    # 剩余两个同分，按入队顺序稳定
    assert [p.target for p in queue[1:]] == ["low1", "low2"]


# --------------------------------------------------------------------------
# S2: 自定义 threshold（非 0.1）时活跃判定与该阈值一致
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_trails_respects_custom_threshold():
    """阈值设为 2.0 时，强度 1.5 的 trail 不算活跃；强度 3.0 的算活跃。"""
    router = PheromoneRouter(decay_rate=1.0, threshold=2.0)
    await router.deposit("weak", strength=1.5)
    await router.deposit("strong", strength=3.0)

    active = await router.get_active_trails()
    active_targets = {t.target for t in active}

    assert "strong" in active_targets
    assert "weak" not in active_targets


@pytest.mark.asyncio
async def test_active_trails_low_threshold_includes_more():
    """阈值设为 0.01（低于写死的 0.1）时，强度 0.05 的 trail 应算活跃。"""
    router = PheromoneRouter(decay_rate=1.0, threshold=0.01)
    await router.deposit("tiny", strength=0.05)

    active = await router.get_active_trails()

    # 若仍用写死 0.1 的 is_active，0.05 会被错误排除
    assert {t.target for t in active} == {"tiny"}


@pytest.mark.asyncio
async def test_active_judgement_consistent_with_evaporate():
    """活跃判定与蒸发判定对同一阈值一致：蒸发后被删的 trail 也非活跃。"""
    router = PheromoneRouter(decay_rate=1.0, threshold=2.0)
    await router.deposit("below", strength=1.5)
    await router.deposit("above", strength=5.0)

    # 蒸发：strength <= threshold(2.0) 的 below 应被删除
    await router.evaporate()
    stats = await router.get_stats()

    active = await router.get_active_trails()
    active_targets = {t.target for t in active}

    # below 已被蒸发删除，自然不在活跃集；above 仍活跃
    assert active_targets == {"above"}
    # get_active_trails 的活跃计数与 get_stats 的 active_trails 口径一致
    assert len(active) == stats["active_trails"]


def test_trail_is_active_above_helper():
    """is_active_above(threshold) 行为正确，且 is_active 兼容默认 0.1。"""
    trail = PheromoneTrail(target="x", strength=0.5, decay_rate=1.0)
    assert trail.is_active_above(0.1) is True
    assert trail.is_active_above(0.6) is False
    # 向后兼容：is_active 仍用写死 0.1
    assert trail.is_active is True
