"""
cost_tracker.py — Token消耗追踪器

精确记录每次API请求的Token消耗与成本，支持预算告警、
跨日自动重置、Provider级统计与会话汇总。
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Callable, List, Optional

from .models import ProviderConfig, RequestLog

logger = logging.getLogger(__name__)


class CostTracker:
    """Token消耗追踪器 — 精确记录每次请求的消耗和成本"""

    def __init__(
        self,
        budget_usd: Optional[float] = None,
        alert_threshold: float = 0.8,
    ) -> None:
        """
        初始化CostTracker。

        :param budget_usd: 每日预算上限（USD），None表示不限
        :param alert_threshold: 预算告警阈值（0-1），默认0.8即80%
        """
        self._logs: deque = deque(maxlen=10000)
        self._budget_usd = budget_usd
        self._alert_threshold = alert_threshold
        self._daily_consumed = 0.0
        self._daily_tokens = 0
        self._alert_fired = False
        self._callbacks: List[Callable[[float, float], None]] = []
        self._date = datetime.now().date()

    def record(self, log: RequestLog, provider_config: ProviderConfig = None) -> None:
        """
        记录一次请求的消耗。

        若传入provider_config且log.cost_usd==0，按公式自动计算成本::

            cost = prompt_tokens/1000*cost_per_1k_input + completion_tokens/1000*cost_per_1k_output

        然后追加日志、更新每日统计，并检查预算告警。

        :param log: 单次请求日志对象
        :param provider_config: 对应的Provider配置，用于自动计算成本
        """
        if provider_config is not None and log.cost_usd == 0:
            log.cost_usd = (
                log.prompt_tokens / 1000 * provider_config.cost_per_1k_input
                + log.completion_tokens / 1000 * provider_config.cost_per_1k_output
            )
        if log.timestamp is None:
            log.timestamp = datetime.now()
        self._rollover_date()
        self._logs.append(log)
        self._daily_consumed += log.cost_usd
        self._daily_tokens += log.prompt_tokens + log.completion_tokens
        self._check_budget_alert()

    def on_budget_alert(self, callback: Callable[[float, float], None]) -> None:
        """
        注册预算告警回调函数。

        当今日消耗达到或超过预算阈值时，所有已注册回调会被触发。
        回调签名: ``callback(consumed_usd: float, budget_usd: float) -> None``

        :param callback: 告警回调函数
        """
        self._callbacks.append(callback)

    def get_daily_usage(self) -> tuple:
        """
        获取今日用量概况。

        :return: (consumed_usd, budget_usd, token_count)
                 consumed_usd — 今日已消耗金额（USD）
                 budget_usd   — 每日预算上限（None表示不限）
                 token_count  — 今日已用Token总数
        """
        self._rollover_date()
        return (self._daily_consumed, self._budget_usd, self._daily_tokens)

    def get_provider_usage(self, provider_id: str) -> dict:
        """
        获取指定Provider的累计统计信息。

        :param provider_id: Provider唯一标识
        :return: {"requests": 请求次数, "tokens": 总Token数, "cost": 总成本（USD）, "avg_latency_ms": 平均延迟}
        """
        total_tokens = 0
        total_cost = 0.0
        total_latency = 0
        count = 0
        for log in self._logs:
            if log.provider_id == provider_id:
                count += 1
                total_tokens += log.prompt_tokens + log.completion_tokens
                total_cost += log.cost_usd
                total_latency += log.response_time_ms
        return {
            "requests": count,
            "tokens": total_tokens,
            "cost": round(total_cost, 6),
            "avg_latency_ms": round(total_latency / count, 2) if count else 0.0,
        }

    def get_recent_logs(self, n: int = 100) -> List[RequestLog]:
        """
        获取最近N条请求日志。

        :param n: 返回日志条数上限，默认100
        :return: RequestLog列表，按时间从新到旧排列
        """
        return list(self._logs)[-n:]

    def get_session_summary(self) -> dict:
        """
        获取当前会话汇总统计。

        :return: {"total_requests": int, "total_tokens": int, "total_cost": float, "by_provider": dict}
                 by_provider格式: {"provider_id": {"requests": int, "tokens": int, "cost": float}}
        """
        total_requests = 0
        total_tokens = 0
        total_cost = 0.0
        by_provider: dict = {}
        for log in self._logs:
            total_requests += 1
            log_tokens = log.prompt_tokens + log.completion_tokens
            total_tokens += log_tokens
            total_cost += log.cost_usd
            pid = log.provider_id
            if pid not in by_provider:
                by_provider[pid] = {"requests": 0, "tokens": 0, "cost": 0.0}
            by_provider[pid]["requests"] += 1
            by_provider[pid]["tokens"] += log_tokens
            by_provider[pid]["cost"] += log.cost_usd
        for pid in by_provider:
            by_provider[pid]["cost"] = round(by_provider[pid]["cost"], 6)
        return {
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 6),
            "by_provider": by_provider,
        }

    def _check_budget_alert(self) -> None:
        """
        检查是否触发预算告警。

        若budget_usd为None直接返回。当daily_consumed/budget_usd >= alert_threshold
        且alert_fired为False时，设置alert_fired=True并触发所有回调。
        """
        if self._budget_usd is None:
            return
        ratio = self._daily_consumed / self._budget_usd
        if ratio >= self._alert_threshold and not self._alert_fired:
            self._alert_fired = True
            logger.warning(
                "[CostTracker] 预算告警: 已消耗 $%.4f / 预算 $%.4f (%.1f%%)",
                self._daily_consumed, self._budget_usd, ratio * 100,
            )
            for cb in self._callbacks:
                try:
                    cb(self._daily_consumed, self._budget_usd)
                except Exception:
                    logger.exception("预算回调执行异常")

    def _rollover_date(self) -> None:
        """
        跨日重置检测。

        若系统日期与self._date不一致，重置daily_consumed、daily_tokens、
        alert_fired，并更新_date为新日期。
        """
        today = datetime.now().date()
        if today != self._date:
            logger.info("[CostTracker] 跨日重置: %s -> %s", self._date, today)
            self._daily_consumed = 0.0
            self._daily_tokens = 0
            self._alert_fired = False
            self._date = today
