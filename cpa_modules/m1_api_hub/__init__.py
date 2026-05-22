"""
__init__.py — M1 API Hub 模块入口

通过环境变量 ``CPA_M1_API_HUB`` 控制模块开关（默认启用）。
提供 ``init_m1()`` 完成配置加载、组件初始化与Provider注册，
通过模块级单例暴露 ``ProviderManager`` 、 ``CostTracker`` 、 ``FailoverMonitor`` 。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from .config_schema import load_m1_config_from_env
from .cost_tracker import CostTracker
from .failover_monitor import FailoverMonitor
from .models import M1Config, ProviderConfig, ProviderState, ProviderStatus
from .provider_manager import ProviderManager

logger = logging.getLogger(__name__)

_provider_manager: Optional[ProviderManager] = None
_cost_tracker: Optional[CostTracker] = None
_failover_monitor: Optional[FailoverMonitor] = None
_initialized: bool = False
_M1_ENV_VAR = "CPA_M1_API_HUB"


def is_m1_enabled() -> bool:
    """
    检查M1 API Hub模块是否被启用。

    读取环境变量 ``CPA_M1_API_HUB`` ，默认 "true" ；值为 "false" 时不加载。

    :return: True=启用, False=禁用
    """
    return os.getenv(_M1_ENV_VAR, "true").lower() != "false"


async def init_m1() -> None:
    """
    初始化M1 API Hub模块。

    流程：1) 检查模块开关与重复初始化；2) 加载 ``M1Config`` ；
    3) 创建 ``CostTracker`` 、 ``ProviderManager`` 、 ``FailoverMonitor`` ；
    4) 注册所有Provider；5) 启动FailoverMonitor；6) 标记初始化完成。

    :raises RuntimeError: 重复初始化时抛出
    """
    global _provider_manager, _cost_tracker, _failover_monitor, _initialized

    if not is_m1_enabled():
        logger.info("[M1] 模块已被环境变量 %s 禁用，跳过初始化", _M1_ENV_VAR)
        return

    if _initialized:
        raise RuntimeError("M1 API Hub 已初始化，请勿重复调用 init_m1()")

    logger.info("[M1] 开始初始化 API Hub 模块...")
    config: M1Config = load_m1_config_from_env()

    _cost_tracker = CostTracker(
        budget_usd=config.daily_budget_usd,
        alert_threshold=config.budget_alert_threshold,
    )
    _provider_manager = ProviderManager()
    _failover_monitor = FailoverMonitor(
        provider_manager=_provider_manager,
        config={
            "health_check_interval": config.health_check_interval,
            "health_check_timeout": config.health_check_timeout,
            "fail_threshold": config.fail_threshold,
            "recovery_check_interval": config.recovery_check_interval,
            "recovery_confirm_requests": config.recovery_confirm_requests,
        },
    )

    for pconf in config.providers:
        await _provider_manager.register_provider(pconf)
        logger.info("[M1] Provider已注册: %s (model=%s)", pconf.id, pconf.model)

    await _failover_monitor.start()
    _initialized = True
    logger.info("[M1] 初始化完成，共注册 %d 个Provider", len(config.providers))


def _ensure_initialized() -> None:
    """内部辅助：确保模块已初始化，否则抛出RuntimeError。"""
    if not _initialized:
        raise RuntimeError("M1 API Hub 尚未初始化，请先调用 init_m1()")


def get_provider_manager() -> ProviderManager:
    """获取ProviderManager单例。模块未初始化时抛RuntimeError。"""
    _ensure_initialized()
    return _provider_manager  # type: ignore[return-value]


def get_cost_tracker() -> CostTracker:
    """获取CostTracker单例。模块未初始化时抛RuntimeError。"""
    _ensure_initialized()
    return _cost_tracker  # type: ignore[return-value]


def get_failover_monitor() -> FailoverMonitor:
    """获取FailoverMonitor单例。模块未初始化时抛RuntimeError。"""
    _ensure_initialized()
    return _failover_monitor  # type: ignore[return-value]


__all__ = [
    "init_m1",
    "is_m1_enabled",
    "get_provider_manager",
    "get_cost_tracker",
    "get_failover_monitor",
    "ProviderConfig",
    "ProviderState",
    "ProviderStatus",
    "M1Config",
]
