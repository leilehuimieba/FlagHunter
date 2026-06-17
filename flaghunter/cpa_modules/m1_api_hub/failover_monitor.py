"""
FlagHunter M1 API Hub — 故障转移监控器 (FailoverMonitor)

本模块提供 LLM Provider 的后台健康检查、故障转移与自动恢复能力。
核心功能包括：

1. 健康检查 (Health Check)：定期对每个启用的 Provider 发送探测请求，
   根据连续失败次数将 Provider 状态在 HEALTHY ↔ DEGRADED ↔ DOWN 之间转换。

2. 故障转移 (Failover)：当 Provider 被标记为 DOWN 时，由 ProviderManager
   的降级链将流量切走；本监控器负责检测并触发状态变更。

3. 自动恢复 (Auto Recovery)：对 DOWN 状态的 Provider 以较长间隔进行恢复探测，
   连续成功达到阈值后再通过真实请求验证，确认恢复后重新标记为 HEALTHY。

所有方法均为 Python 3.10+ async/await 实现，线程安全通过 asyncio.Lock 保证。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

# ------------------------------------------------------------
# 从 Phase 1 已提供的模型与管理层导入
# ------------------------------------------------------------
from .models import (
    HealthCheckResult,
    ProviderConfig,
    ProviderState,
    ProviderStatus,
)
from .provider_manager import ProviderManager


# ------------------------------------------------------------
# 模块公开接口
# ------------------------------------------------------------
__all__ = ["FailoverMonitor"]


class FailoverMonitor:
    """故障转移监控器 — 后台运行健康检查和自动恢复。

    为每个启用的 Provider 并发启动两套协程：
    - `_health_check_loop`: 高频健康探测，负责 DOWN 检测与 DEGRADED 判定。
    - `_recovery_loop`: 低频恢复探测，负责 DOWN → HEALTHY 的自动恢复。

    状态变更时通过回调机制通知外部（如日志、告警、事件总线）。

    Attributes:
        _pm: ProviderManager 实例，用于读写 Provider 配置与状态。
        _config: 监控器配置字典，覆盖默认参数。
        _tasks: provider_id → asyncio.Task 映射，保存正在运行的监控任务。
        _running: 监控器整体运行标志。
        _callbacks: 已注册的状态变更回调列表。
        _lock: asyncio.Lock，保护 _tasks 和 _callbacks 的并发访问。

    配置项（可通过 config 字典覆盖）：
        health_check_interval:      健康检查间隔（秒），默认 30
        fail_threshold:             触发 DOWN 的连续失败阈值，默认 3
        recovery_check_interval:    恢复检查间隔（秒），默认 60
        recovery_confirm_requests:  恢复确认所需连续成功次数，默认 2
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        config: Optional[dict] = None,
    ) -> None:
        self._pm: ProviderManager = provider_manager
        self._config: dict = config or {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._running: bool = False
        self._callbacks: List[Callable[[str, ProviderState, ProviderState], None]] = []
        self._lock: asyncio.Lock = asyncio.Lock()

    # ============================================================
    # 1. 生命周期管理
    # ============================================================

    async def start(self) -> None:
        """启动所有 Provider 的监控任务。

        遍历 ProviderManager 中所有已注册且 enabled=True 的 Provider，
        为每个 Provider 并发创建并启动：
        - 一个 `_health_check_loop` 协程（高频健康探测）
        - 一个 `_recovery_loop` 协程（低频恢复探测）

        所有任务保存在 `self._tasks` 中，设置 `self._running = True`。
        若监控器已在运行，则静默返回，避免重复启动。
        """
        if self._running:
            return

        self._running = True

        providers: List[ProviderConfig] = self._pm.list_providers()
        async with self._lock:
            for cfg in providers:
                if not cfg.enabled:
                    continue
                pid = cfg.id

                # 健康检查循环
                hc_task = asyncio.create_task(
                    self._health_check_loop(pid),
                    name=f"health-check-{pid}",
                )
                # 恢复检测循环
                rc_task = asyncio.create_task(
                    self._recovery_loop(pid),
                    name=f"recovery-{pid}",
                )

                self._tasks[f"hc:{pid}"] = hc_task
                self._tasks[f"rc:{pid}"] = rc_task

    async def stop(self) -> None:
        """优雅停止所有监控任务。

        流程：
        1. 设置 `self._running = False`，通知所有循环退出。
        2. 取消保存在 `self._tasks` 中的所有 asyncio.Task。
        3. 使用 `asyncio.gather(..., return_exceptions=True)` 等待全部任务结束，
           避免取消异常向上传播。
        4. 清空 `self._tasks`。

        即使部分任务取消失败，也会静默处理异常，确保 stop 操作不会抛异常。
        """
        self._running = False

        async with self._lock:
            tasks_to_cancel = list(self._tasks.values())
            self._tasks.clear()

        if tasks_to_cancel:
            for t in tasks_to_cancel:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

    # ============================================================
    # 2. 回调注册
    # ============================================================

    def on_state_change(
        self,
        callback: Callable[[str, ProviderState, ProviderState], None],
    ) -> None:
        """注册 Provider 状态变更回调函数。

        当任何 Provider 的状态发生变更时（如 HEALTHY → DOWN、DOWN → HEALTHY 等），
        所有已注册的回调会按注册顺序被同步调用。

        Args:
            callback: 回调函数，签名必须为::

                callback(provider_id: str, old_state: ProviderState, new_state: ProviderState) -> None

        Example::

            def my_callback(pid, old_s, new_s):
                print(f"[{pid}] {old_s.value} -> {new_s.value}")

            monitor.on_state_change(my_callback)
        """
        self._callbacks.append(callback)

    # ============================================================
    # 3. 健康检查循环（核心算法）
    # ============================================================

    async def _health_check_loop(self, provider_id: str) -> None:
        """单个 Provider 的健康检查循环。

        以 `health_check_interval` 为间隔定期发送探测请求，根据响应结果
        维护 Provider 的 HEALTHY / DEGRADED / DOWN 状态。

        状态转换规则：
        - 探测成功 → consecutive_failures 清零；若当前非 HEALTHY 则恢复为 HEALTHY。
        - 探测失败 → consecutive_failures 递增；
          * 达到 fail_threshold  → 标记为 DOWN
          * 大于 0 但未达阈值   → 标记为 DEGRADED
        - DOWN 状态的 Provider 由 `_recovery_loop` 负责恢复，本循环跳过探测。

        Args:
            provider_id: 被监控的 Provider 唯一标识。

        Note:
            使用局部变量 `consecutive_failures` 跟踪连续失败次数，
            避免与 recovery_loop 的计数器互相干扰。
        """
        interval: int = self._config.get("health_check_interval", 30)
        fail_threshold: int = self._config.get("fail_threshold", 3)
        consecutive_failures: int = 0

        while self._running:
            try:
                status: Optional[ProviderStatus] = self._pm.get_status(provider_id)
                if status is None:
                    # Provider 已被注销，本循环退出
                    break

                # DOWN 状态的 Provider 由恢复循环处理，本循环跳过
                if status.state == ProviderState.DOWN:
                    consecutive_failures = 0
                    await asyncio.sleep(interval)
                    continue

                result: HealthCheckResult = await self._probe(provider_id)

                if result.success:
                    consecutive_failures = 0
                    if status.state != ProviderState.HEALTHY:
                        old_state = status.state
                        self._pm.mark_provider_status(provider_id, ProviderState.HEALTHY)
                        self._fire_callback(provider_id, old_state, ProviderState.HEALTHY)
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= fail_threshold:
                        old_state = status.state
                        self._pm.mark_provider_status(
                            provider_id,
                            ProviderState.DOWN,
                            result.error_message or "连续探测失败达到阈值",
                        )
                        self._fire_callback(provider_id, old_state, ProviderState.DOWN)
                    elif consecutive_failures > 0 and status.state != ProviderState.DEGRADED:
                        self._pm.mark_provider_status(provider_id, ProviderState.DEGRADED)

            except Exception:
                # 本循环绝不因任何异常而终止，记录后等待下一轮
                pass

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    # ============================================================
    # 4. 恢复检测循环（核心算法）
    # ============================================================

    async def _recovery_loop(self, provider_id: str) -> None:
        """单个 Provider 的自动恢复检测循环。

        仅对状态为 DOWN 的 Provider 以较长间隔进行恢复探测。

        恢复流程：
        1. 探测成功 → consecutive_successes 递增，状态置为 RECOVERING。
        2. 当连续成功次数达到 `recovery_confirm_requests` 时，
           调用 `_verify_with_real_request` 发送真实请求验证。
        3. 真实请求验证通过 → 标记为 HEALTHY，恢复完成。
        4. 真实请求验证失败 或 任一探测失败 → consecutive_successes 清零，
           继续保持 DOWN 状态。

        Args:
            provider_id: 被监控的 Provider 唯一标识。

        Note:
            使用局部变量 `consecutive_successes` 跟踪连续成功次数，
            与 health_check_loop 的计数器独立。
        """
        recovery_interval: int = self._config.get("recovery_check_interval", 60)
        recovery_confirm: int = self._config.get("recovery_confirm_requests", 2)
        consecutive_successes: int = 0

        while self._running:
            try:
                status: Optional[ProviderStatus] = self._pm.get_status(provider_id)
                if status is None:
                    # Provider 已被注销，本循环退出
                    break

                # 仅处理 DOWN / RECOVERING 状态的 Provider
                if status.state not in (ProviderState.DOWN, ProviderState.RECOVERING):
                    consecutive_successes = 0
                    await asyncio.sleep(recovery_interval)
                    continue

                result: HealthCheckResult = await self._probe(provider_id)

                if result.success:
                    consecutive_successes += 1
                    if consecutive_successes >= recovery_confirm:
                        # 达到恢复确认阈值，使用真实请求验证
                        if await self._verify_with_real_request(provider_id):
                            old_state = status.state
                            self._pm.mark_provider_status(provider_id, ProviderState.HEALTHY)
                            self._fire_callback(provider_id, old_state, ProviderState.HEALTHY)
                            consecutive_successes = 0
                        else:
                            # 真实请求验证失败，重置计数器
                            consecutive_successes = 0
                            if status.state != ProviderState.DOWN:
                                old_state = status.state
                                self._pm.mark_provider_status(
                                    provider_id,
                                    ProviderState.DOWN,
                                    "恢复验证失败",
                                )
                                self._fire_callback(provider_id, old_state, ProviderState.DOWN)
                    else:
                        # 恢复中但尚未达到确认阈值
                        if status.state != ProviderState.RECOVERING:
                            old_state = status.state
                            self._pm.mark_provider_status(provider_id, ProviderState.RECOVERING)
                            self._fire_callback(provider_id, old_state, ProviderState.RECOVERING)
                else:
                    # 探测失败，重置恢复计数
                    consecutive_successes = 0
                    if status.state != ProviderState.DOWN:
                        old_state = status.state
                        self._pm.mark_provider_status(
                            provider_id,
                            ProviderState.DOWN,
                            result.error_message or "恢复探测失败",
                        )
                        self._fire_callback(provider_id, old_state, ProviderState.DOWN)

            except Exception:
                # 本循环绝不因任何异常而终止
                pass

            try:
                await asyncio.sleep(recovery_interval)
            except asyncio.CancelledError:
                break

    # ============================================================
    # 5. 探测请求
    # ============================================================

    async def _probe(self, provider_id: str) -> HealthCheckResult:
        """向指定 Provider 发送极简探测请求，检查其可用性。

        使用 litellm.acompletion 发送极简请求：
        - messages=[{"role": "user", "content": "hi"}]
        - max_tokens=1
        - timeout = min(provider_timeout, 10) 秒

        成功时返回包含响应耗时的 HealthCheckResult；
        失败时（包括网络错误、超时、认证失败等）返回包含错误信息的 HealthCheckResult。

        本方法捕获**所有异常**，绝不会向上抛异常，确保调用方的循环安全。

        Args:
            provider_id: 要探测的 Provider 唯一标识。

        Returns:
            HealthCheckResult: 探测结果，success=True 表示可用，success=False 表示不可用。

        Note:
            litellm 的 import 放在方法内部并用 try/except 包裹 ImportError，
            确保本模块在没有 litellm 时也能被加载（探测请求会直接返回失败结果）。
        """
        cfg: Optional[ProviderConfig] = self._pm.get_provider(provider_id)
        if cfg is None:
            return HealthCheckResult(
                provider_id=provider_id,
                success=False,
                response_time_ms=0,
                error_message="Provider 不存在",
            )

        # 尝试导入 litellm；若未安装则返回失败
        try:
            import litellm
        except ImportError:
            return HealthCheckResult(
                provider_id=provider_id,
                success=False,
                response_time_ms=0,
                error_message="litellm 未安装，无法执行探测",
            )

        timeout: int = min(cfg.timeout, 10)
        start_ts: float = time.monotonic()

        try:
            response = await asyncio.wait_for(
                litellm.acompletion(
                    model=cfg.model,
                    messages=[{"role": "user", "content": "hi"}],
                    api_key=cfg.api_key,
                    api_base=cfg.api_base,
                    max_tokens=1,
                    extra_headers=dict(cfg.headers) if cfg.headers else None,
                ),
                timeout=timeout,
            )

            elapsed_ms: int = int((time.monotonic() - start_ts) * 1000)

            # 只要响应返回（无论内容如何）即视为探测成功
            return HealthCheckResult(
                provider_id=provider_id,
                success=True,
                response_time_ms=elapsed_ms,
            )

        except asyncio.TimeoutError:
            return HealthCheckResult(
                provider_id=provider_id,
                success=False,
                response_time_ms=int((time.monotonic() - start_ts) * 1000),
                error_message=f"探测请求超时（>{timeout}s）",
            )

        except Exception as exc:
            return HealthCheckResult(
                provider_id=provider_id,
                success=False,
                response_time_ms=int((time.monotonic() - start_ts) * 1000),
                error_message=f"{type(exc).__name__}: {exc}",
            )

    # ============================================================
    # 6. 真实请求验证
    # ============================================================

    async def _verify_with_real_request(self, provider_id: str) -> bool:
        """使用真实请求验证 Provider 是否已真正恢复。

        在恢复探测连续成功后，发送一个稍长的请求（max_tokens=5）验证 Provider
        能否正常处理完整请求链路，避免"探测能通但真实请求失败"的误判。

        使用 litellm.acompletion 发送请求：
        - messages=[{"role": "user", "content": "Hello, respond with OK"}]
        - max_tokens=5
        - timeout = min(provider_timeout, 15) 秒

        Args:
            provider_id: 要验证的 Provider 唯一标识。

        Returns:
            bool: 验证成功返回 True，失败返回 False。

        Note:
            本方法捕获**所有异常**，绝不会向上抛异常。
            litellm 的 import 放在方法内部并用 try/except 包裹 ImportError。
        """
        cfg: Optional[ProviderConfig] = self._pm.get_provider(provider_id)
        if cfg is None:
            return False

        try:
            import litellm
        except ImportError:
            return False

        timeout: int = min(cfg.timeout, 15)

        try:
            await asyncio.wait_for(
                litellm.acompletion(
                    model=cfg.model,
                    messages=[{"role": "user", "content": "Hello, respond with OK"}],
                    api_key=cfg.api_key,
                    api_base=cfg.api_base,
                    max_tokens=5,
                    extra_headers=dict(cfg.headers) if cfg.headers else None,
                ),
                timeout=timeout,
            )
            return True

        except Exception:
            return False

    # ============================================================
    # 7. 回调触发
    # ============================================================

    def _fire_callback(
        self,
        provider_id: str,
        old_state: ProviderState,
        new_state: ProviderState,
    ) -> None:
        """触发所有已注册的状态变更回调。

        遍历 `self._callbacks` 中的每个回调函数，传入：
        - provider_id: 发生状态变更的 Provider ID
        - old_state:   变更前的状态
        - new_state:   变更后的状态

        每个回调独立捕获异常，避免单个回调失败影响其他回调的执行。

        Args:
            provider_id: 发生状态变更的 Provider 唯一标识。
            old_state:   变更前的 ProviderState。
            new_state:   变更后的 ProviderState。
        """
        for cb in self._callbacks:
            try:
                cb(provider_id, old_state, new_state)
            except Exception:
                # 单个回调失败不影响其他回调
                pass


# ============================================================
# 模块自测试（直接运行 python failover_monitor.py 时执行）
# ============================================================


async def _self_test() -> None:
    """FailoverMonitor 自测函数，验证各方法基本正确性（不依赖 litellm）。"""
    from provider_manager import ProviderConfig as PMProviderConfig
    from provider_manager import ProviderManager as PMProviderManager

    pm = PMProviderManager()

    # 注册两个测试 Provider
    cfg1 = PMProviderConfig(
        id="p1", name="OpenAI", model="gpt-4o",
        api_base="https://api.openai.com/v1", api_key="sk-test",
        timeout=5, priority=1,
    )
    cfg2 = PMProviderConfig(
        id="p2", name="DeepSeek", model="deepseek-chat",
        api_base="https://api.deepseek.com/v1", api_key="sk-test",
        timeout=5, priority=2,
    )
    await pm.register_provider(cfg1)
    await pm.register_provider(cfg2)
    print(f"[✅] 注册 Provider: {len(pm.list_providers())} 个")

    # 1. 创建 FailoverMonitor 实例
    config = {
        "health_check_interval": 1,      # 1秒间隔加速测试
        "fail_threshold": 2,             # 2次失败即标记 DOWN
        "recovery_check_interval": 1,    # 1秒恢复间隔加速测试
        "recovery_confirm_requests": 1,  # 1次成功即尝试验证
    }
    monitor = FailoverMonitor(pm, config=config)
    print("[✅] FailoverMonitor 实例创建成功")

    # 2. 注册回调
    events: list = []

    def test_callback(pid: str, old_s, new_s):
        events.append((pid, old_s.value, new_s.value))
        print(f"   [📡] 回调: {pid} {old_s.emoji(old_s)}{old_s.value} -> {new_s.emoji(new_s)}{new_s.value}")

    monitor.on_state_change(test_callback)
    print("[✅] 状态变更回调注册成功")

    # 3. 启动监控
    await monitor.start()
    print(f"[✅] 监控已启动，运行任务数: {len(monitor._tasks)}")
    assert monitor._running is True
    assert len(monitor._tasks) == 4  # 2 Provider × 2 循环

    # 4. 停止监控
    await monitor.stop()
    print(f"[✅] 监控已停止，剩余任务数: {len(monitor._tasks)}")
    assert monitor._running is False

    # 5. 验证 _probe 对不存在 Provider 的处理
    result = await monitor._probe("nonexistent")
    assert result.success is False
    assert "不存在" in (result.error_message or "")
    print(f"[✅] _probe 不存在Provider: success={result.success}, error='{result.error_message}'")

    # 6. 验证 _verify_with_real_request 对不存在 Provider 的处理
    ok = await monitor._verify_with_real_request("nonexistent")
    assert ok is False
    print(f"[✅] _verify_with_real_request 不存在Provider: {ok}")

    # 7. 验证 _fire_callback 的异常隔离
    def bad_callback(pid, old_s, new_s):
        raise RuntimeError("故意失败")

    monitor2 = FailoverMonitor(pm, config=config)
    monitor2.on_state_change(bad_callback)
    monitor2.on_state_change(test_callback)
    # 不应抛异常
    monitor2._fire_callback("p1", ProviderState.HEALTHY, ProviderState.DOWN)
    assert len(events) >= 1
    print("[✅] _fire_callback 异常隔离: 坏回调不影响好回调")

    print("\n🎉 FailoverMonitor 全部自测通过!")


if __name__ == "__main__":
    asyncio.run(_self_test())
