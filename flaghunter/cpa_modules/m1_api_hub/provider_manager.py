"""
FlagHunter M1 API Hub - Provider调度核心模块

提供异步线程安全的LLM Provider注册、发现、健康状态管理与选择调度能力。
支持多Provider优先级排序、模型匹配、请求统计与成本追踪。

Python 3.10+ required. 使用 asyncio.Lock 保证并发安全。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Set

from .models import (
    ProviderConfig,
    ProviderState,
    ProviderStatus,
    RequestLog,
)
from .model_router import resolve_tier, route


# ============================================================
# 自定义异常
# ============================================================

class NoProviderAvailable(Exception):
    """当所有Provider均不可用（禁用、宕机或降级到无法服务）时抛出此异常。"""


def _budget_guard() -> None:
    """Best-effort budget gate; only active when M1 已初始化。"""
    try:
        from . import get_cost_tracker

        get_cost_tracker().raise_if_budget_exceeded()
    except RuntimeError:
        return


# ============================================================
# ProviderManager 核心类
# ============================================================

class ProviderManager:
    """
    Provider调度管理器（异步线程安全）。

    负责：
    - Provider的注册、注销、批量加载
    - 运行时健康状态追踪与更新
    - 按优先级和模型匹配选择最佳Provider
    - 请求统计与成本估算
    """

    def __init__(self) -> None:
        self._providers: Dict[str, ProviderConfig] = {}   # id -> config
        self._status: Dict[str, ProviderStatus] = {}       # id -> status
        self._lock = asyncio.Lock()

    # --------------------------------------------------------
    # Provider 生命周期管理
    # --------------------------------------------------------

    async def register_provider(self, config: ProviderConfig) -> None:
        """
        注册一个新的Provider；若provider_id已存在则覆盖更新。

        同步更新 _providers 配置表与 _status 状态表。
        新注册Provider的初始状态为 HEALTHY。

        Args:
            config: ProviderConfig 配置对象，id字段必须唯一。
        """
        async with self._lock:
            self._providers[config.id] = config
            self._status[config.id] = ProviderStatus(provider_id=config.id)

    async def unregister_provider(self, provider_id: str) -> None:
        """
        注销指定Provider，彻底移除其配置与运行时状态。

        若 provider_id 不存在则静默返回，不抛出异常。

        Args:
            provider_id: 要注销的Provider唯一标识。
        """
        async with self._lock:
            self._providers.pop(provider_id, None)
            self._status.pop(provider_id, None)

    async def load_providers(self, configs: List[ProviderConfig]) -> None:
        """
        批量注册多个Provider，常用于从配置文件或数据库初始化。

        内部逐个调用 register_provider，已存在的同名Provider将被覆盖。

        Args:
            configs: ProviderConfig 列表。
        """
        async with self._lock:
            for config in configs:
                self._providers[config.id] = config
                self._status[config.id] = ProviderStatus(provider_id=config.id)

    # --------------------------------------------------------
    # 查询接口（只读，外部需保证调用时机或自行加锁）
    # --------------------------------------------------------

    def get_provider(self, provider_id: str) -> Optional[ProviderConfig]:
        """
        获取指定Provider的静态配置。

        Args:
            provider_id: Provider唯一标识。

        Returns:
            ProviderConfig 或 None（不存在时）。
        """
        return self._providers.get(provider_id)

    def get_status(self, provider_id: str) -> Optional[ProviderStatus]:
        """
        获取指定Provider的运行时状态。

        Args:
            provider_id: Provider唯一标识。

        Returns:
            ProviderStatus 或 None（不存在时）。
        """
        return self._status.get(provider_id)

    def list_providers(self) -> List[ProviderConfig]:
        """
        列出所有已注册的Provider，按 priority 升序排列（数字越小优先级越高）。

        Returns:
            ProviderConfig 列表。
        """
        return sorted(self._providers.values(), key=lambda c: c.priority)

    def list_healthy_providers(self) -> List[ProviderConfig]:
        """
        列出所有健康可用的Provider（状态为HEALTHY或DEGRADED），按priority升序排列。

        Returns:
            可用的 ProviderConfig 列表。
        """
        healthy: List[ProviderConfig] = []
        for pid, config in self._providers.items():
            status = self._status.get(pid)
            if status is not None and status.is_available():
                healthy.append(config)
        return sorted(healthy, key=lambda c: c.priority)

    def get_active_provider(self) -> Optional[ProviderConfig]:
        """
        获取当前最佳Provider：返回优先级最高且可用的Provider。

        无可用的Provider时返回 None。

        Returns:
            最佳 ProviderConfig 或 None。
        """
        candidates = self.list_healthy_providers()
        return candidates[0] if candidates else None

    @staticmethod
    def _model_matches(config_model: str, desired_model: str) -> bool:
        """模糊匹配路由结果与Provider实际模型名。"""
        config_lower = config_model.lower()
        desired_lower = desired_model.lower()

        if config_lower == desired_lower:
            return True
        if desired_lower in config_lower or config_lower in desired_lower:
            return True

        if "claude" in desired_lower and "claude" in config_lower:
            for variant in ("haiku", "sonnet", "opus"):
                if variant in desired_lower:
                    return variant in config_lower
            return True

        if "gpt-4o-mini" in desired_lower:
            return "gpt" in config_lower and "mini" in config_lower

        if "gpt-4o" in desired_lower:
            return "gpt" in config_lower and "4o" in config_lower and "mini" not in config_lower

        if "gpt" in desired_lower and "gpt" in config_lower:
            return True

        return False

    # --------------------------------------------------------
    # 调度选择（带模型匹配）
    # --------------------------------------------------------

    async def select_provider(
        self,
        model_hint: Optional[str] = None,
        task_hint: str = "default",
        exclude_ids: Optional[Set[str]] = None,
    ) -> ProviderConfig:
        """
        为下一次请求选择最佳Provider（异步线程安全）。

        选择逻辑：
        1. 过滤出 enabled=True 且 is_available() 的Provider；
        2. 按 priority 升序排列；
        3. 如指定 task_hint，先通过 model_router 选择推荐模型并做模糊匹配；
        4. 如指定 model_hint，再按 model 字段包含 hint 优先匹配；
        5. 返回优先级最高的Provider；
        6. 无可用时抛出 NoProviderAvailable。

        Args:
            model_hint: 模型名称片段，用于模型偏好匹配。例如 "gpt-4"。
            task_hint: 任务场景标签，例如 "planning"、"tool_parse"。

        Returns:
            最佳 ProviderConfig。

        Raises:
            NoProviderAvailable: 没有任何可用Provider时抛出。
        """
        _budget_guard()
        excluded = {str(item).strip() for item in (exclude_ids or set()) if str(item).strip()}
        async with self._lock:
            # 1) 过滤可用且启用的Provider
            available = [
                config for config in self._providers.values()
                if config.enabled
                and config.id not in excluded
                and (status := self._status.get(config.id)) is not None
                and status.is_available()
            ]

            if not available:
                raise NoProviderAvailable("没有可用的LLM Provider")

            # 2) 按 priority 升序排列
            available.sort(key=lambda c: c.priority)

            # 2.5) 成本分层路由:仅"低思考"任务(light 档,如 tool_parse/summary/
            # formatting)优先走便宜模型(tags 含 cheap/light);default/medium/heavy
            # 保持原优先级顺序(主力模型)。无 cheap-tagged provider 时回落到下方原
            # 逻辑 → 对未打 tag 的池字节级一致(老配置行为不变)。
            if resolve_tier(task_hint) == "light":
                cheap = [
                    config for config in available
                    if {"cheap", "light"} & {str(t).strip().lower() for t in (config.tags or [])}
                ]
                if cheap:
                    return cheap[0]

            # 3) 如指定 task_hint，优先按任务类型路由模型
            routed_model = route(
                task_hint=task_hint,
                available_providers=[config.model for config in available],
            )
            matched_by_task = [
                config for config in available
                if self._model_matches(config.model, routed_model)
            ]
            if matched_by_task:
                return matched_by_task[0]

            # 4) 如指定 model_hint，优先匹配 model 字段包含 hint 的
            if model_hint:
                model_hint_lower = model_hint.lower()
                matched = [
                    config for config in available
                    if model_hint_lower in config.model.lower()
                ]
                if matched:
                    return matched[0]

            # 5) 返回优先级最高的
            return available[0]

    # --------------------------------------------------------
    # 状态更新与统计
    # --------------------------------------------------------

    def update_after_request(self, provider_id: str, log: RequestLog) -> None:
        """
        请求完成后更新Provider的统计信息。

        更新内容：
        - total_requests += 1
        - total_tokens += prompt_tokens + completion_tokens
        - estimated_cost_usd += log.cost_usd
        - response_time_ms = log.response_time_ms
        - 若成功：更新 last_success_time、增加 consecutive_successes
        - 若失败：更新 last_error、增加 consecutive_failures

        若 provider_id 不存在则静默返回。

        Args:
            provider_id: 处理请求的Provider标识。
            log: 本次请求的 RequestLog 日志对象。
        """
        status = self._status.get(provider_id)
        if status is None:
            return

        status.total_requests += 1
        status.total_tokens += log.prompt_tokens + log.completion_tokens
        status.estimated_cost_usd += log.cost_usd
        status.response_time_ms = log.response_time_ms
        status.last_check_time = datetime.now()

        if log.success:
            status.last_success_time = datetime.now()
            status.consecutive_successes += 1
            status.consecutive_failures = 0
            status.last_error = ""
        else:
            status.consecutive_failures += 1
            status.consecutive_successes = 0
            status.last_error = log.error_message or "请求失败"

    def mark_provider_status(self, provider_id: str, state: ProviderState, error: str = "") -> None:
        """
        标记Provider状态变更，根据状态自动更新连续成功/失败计数。

        - HEALTHY: consecutive_failures 清零, consecutive_successes += 1
        - DOWN:    consecutive_successes 清零, consecutive_failures += 1
        - 其他:    仅更新 state 和 last_error

        若 provider_id 不存在则静默返回。

        Args:
            provider_id: Provider唯一标识。
            state: 新的Provider状态。
            error: 错误信息（可选），仅在状态为DOWN等异常状态时记录。
        """
        status = self._status.get(provider_id)
        if status is None:
            return

        status.state = state
        status.last_check_time = datetime.now()

        if error:
            status.last_error = error

        if state == ProviderState.HEALTHY:
            status.consecutive_failures = 0
            status.consecutive_successes += 1
        elif state == ProviderState.DOWN:
            status.consecutive_successes = 0
            status.consecutive_failures += 1
        # 其他状态（DEGRADED / RECOVERING / DISABLED）仅更新状态字段

    def mark_provider_enabled(self, provider_id: str, enabled: bool) -> None:
        """
        启用或禁用指定Provider。

        禁用时同步将状态设为 DISABLED；启用时不自动恢复状态，
        由健康检查或外部逻辑决定何时恢复为HEALTHY。

        若 provider_id 不存在则静默返回。

        Args:
            provider_id: Provider唯一标识。
            enabled: True 启用，False 禁用。
        """
        config = self._providers.get(provider_id)
        status = self._status.get(provider_id)

        if config is None or status is None:
            return

        config.enabled = enabled
        if not enabled:
            status.state = ProviderState.DISABLED


# ============================================================
# 模块自测试（直接运行 python provider_manager.py 时执行）
# ============================================================

async def _self_test() -> None:
    """内部自测函数，验证ProviderManager各方法基本正确性。"""
    pm = ProviderManager()

    # 1. 注册Provider
    cfg1 = ProviderConfig(
        id="p1", name="OpenAI", model="gpt-4o",
        api_base="https://api.openai.com/v1", api_key="sk-xxx",
        priority=1, cost_per_1k_input=0.005, cost_per_1k_output=0.015,
    )
    cfg2 = ProviderConfig(
        id="p2", name="DeepSeek", model="deepseek-chat",
        api_base="https://api.deepseek.com/v1", api_key="sk-yyy",
        priority=2, is_backup=True,
    )
    await pm.register_provider(cfg1)
    await pm.register_provider(cfg2)
    assert len(pm.list_providers()) == 2
    print(f"[✅] 注册Provider: {len(pm.list_providers())} 个")

    # 2. 查询接口
    assert pm.get_provider("p1").name == "OpenAI"
    assert pm.get_status("p1").state == ProviderState.HEALTHY
    print(f"[✅] 查询接口: get_provider / get_status 正常")

    # 3. list_healthy_providers & get_active_provider
    healthy = pm.list_healthy_providers()
    assert len(healthy) == 2
    assert pm.get_active_provider().id == "p1"  # priority=1 最小
    print(f"[✅] 健康Provider列表: {len(healthy)} 个, 最佳: {pm.get_active_provider().name}")

    # 4. select_provider
    selected = await pm.select_provider()
    assert selected.id == "p1"
    matched = await pm.select_provider(model_hint="deepseek")
    assert matched.id == "p2"
    print(f"[✅] select_provider: 默认选择 {selected.name}, model匹配选择 {matched.name}")

    # 5. update_after_request
    log = RequestLog(
        request_id="r1", provider_id="p1", model="gpt-4o",
        prompt_tokens=100, completion_tokens=50,
        response_time_ms=1200, success=True, cost_usd=0.001,
    )
    pm.update_after_request("p1", log)
    st = pm.get_status("p1")
    assert st.total_requests == 1
    assert st.total_tokens == 150
    assert st.consecutive_successes == 1
    print(f"[✅] update_after_request: requests={st.total_requests}, tokens={st.total_tokens}")

    # 6. mark_provider_status (DOWN)
    pm.mark_provider_status("p1", ProviderState.DOWN, error="connection timeout")
    assert pm.get_status("p1").state == ProviderState.DOWN
    assert pm.get_status("p1").consecutive_failures == 1
    print(f"[✅] mark_provider_status DOWN: {ProviderState.emoji(ProviderState.DOWN)} failures=1")

    # 7. mark_provider_status (HEALTHY 恢复)
    pm.mark_provider_status("p1", ProviderState.HEALTHY)
    assert pm.get_status("p1").state == ProviderState.HEALTHY
    assert pm.get_status("p1").consecutive_failures == 0
    assert pm.get_status("p1").consecutive_successes == 1  # 从DOWN恢复后 successes=1
    print(f"[✅] mark_provider_status HEALTHY: {ProviderState.emoji(ProviderState.HEALTHY)} successes=1")

    # 8. mark_provider_enabled (禁用)
    pm.mark_provider_enabled("p2", False)
    assert pm.get_provider("p2").enabled is False
    assert pm.get_status("p2").state == ProviderState.DISABLED
    print(f"[✅] mark_provider_enabled(False): p2 已禁用")

    # 9. select_provider 无可用时抛异常
    pm.mark_provider_enabled("p1", False)
    try:
        await pm.select_provider()
        assert False, "应抛出 NoProviderAvailable"
    except NoProviderAvailable as exc:
        print(f"[✅] NoProviderAvailable 异常正确抛出: {exc}")

    # 10. unregister_provider
    await pm.unregister_provider("p1")
    assert pm.get_provider("p1") is None
    print(f"[✅] unregister_provider: p1 已注销")

    # 11. load_providers 批量加载
    batch = [
        ProviderConfig(id="p3", name="Claude", model="claude-3-5-sonnet",
                       api_base="https://api.anthropic.com/v1", api_key="sk-zzz", priority=1),
        ProviderConfig(id="p4", name="Gemini", model="gemini-1.5-pro",
                       api_base="https://generativelanguage.googleapis.com/v1", api_key="sk-aaa", priority=2),
    ]
    await pm.load_providers(batch)
    assert len(pm.list_providers()) == 3  # p2(已禁用) + p3 + p4
    print(f"[✅] load_providers: 批量加载 {len(batch)} 个Provider")

    print("\n🎉 全部自测通过!")


if __name__ == "__main__":
    asyncio.run(_self_test())
