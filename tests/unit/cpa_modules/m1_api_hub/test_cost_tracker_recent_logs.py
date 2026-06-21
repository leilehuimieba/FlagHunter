"""坐实 CostTracker.get_recent_logs 的顺序契约（卡 S4）。

docstring 声明返回值“按时间从旧到新排列（末尾为最新）”，
本测试锁定该契约，防止实现与文档再次漂移。
"""

from __future__ import annotations

from flaghunter.cpa_modules.m1_api_hub.cost_tracker import CostTracker
from flaghunter.cpa_modules.m1_api_hub.models import RequestLog


def _log(request_id: str) -> RequestLog:
    return RequestLog(
        request_id=request_id,
        provider_id="p1",
        model="m",
        prompt_tokens=1,
        completion_tokens=1,
        response_time_ms=1,
    )


def test_get_recent_logs_oldest_to_newest() -> None:
    """记录顺序写入后，返回应保持“旧→新”，末尾为最新。"""
    tracker = CostTracker()
    for i in range(5):
        tracker.record(_log(f"r{i}"))

    result = tracker.get_recent_logs()
    ids = [log.request_id for log in result]

    assert ids == ["r0", "r1", "r2", "r3", "r4"]
    # 末尾为最新一条，契约与 docstring 一致
    assert result[-1].request_id == "r4"


def test_get_recent_logs_respects_limit_keeping_newest() -> None:
    """n 上限生效时，保留最新的 n 条（取尾部），且仍按旧→新排列。"""
    tracker = CostTracker()
    for i in range(5):
        tracker.record(_log(f"r{i}"))

    result = tracker.get_recent_logs(n=2)
    ids = [log.request_id for log in result]

    assert ids == ["r3", "r4"]
