#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
memory_optimizer.py — PentestAgent M6 Turbo 内存监控与优化器

本模块提供 ``MemoryOptimizer`` 类，用于：
1. **实时内存监控** — 异步后台任务定期采样 RSS，超限时触发告警；
2. **跨平台内存读取** — 优先 ``psutil``，降级到 ``/proc/self/status``（Linux）、
   ``ctypes.windll.kernel32``（Windows）、``sys.getsizeof`` 估算（兜底）；
3. **GC 管理** — 提供分代垃圾回收接口并返回统计；
4. **缓存清理** — 通过反射调用各模块的 ``clear_cache`` / ``cleanup`` 方法，
   统一回收模块级缓存；
5. **告警机制** — 支持注册回调函数，在内存超限时异步通知。

技术约束：
- Python 3.10+
- 仅使用标准库（gc, sys, os, asyncio, ctypes, warnings, time 等）
- 零外部依赖（psutil 为可选增强）

作者: PentestAgent M6 模块
"""

from __future__ import annotations

import asyncio
import ctypes
import gc
import os
import platform
import sys
import time
import warnings
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 平台检测与常量
# ---------------------------------------------------------------------------

_SYSTEM = platform.system()
_IS_LINUX = _SYSTEM == "Linux"
_IS_WINDOWS = _SYSTEM == "Windows"

#: Linux proc 文件路径
_PROC_STATUS_PATH = "/proc/self/status"

#: GC 统计信息持久化（用于报表）。
_GC_STATS_DEFAULT: Dict[str, int] = {
    "collections_gen0": 0,
    "collections_gen1": 0,
    "collections_gen2": 0,
    "last_collected": 0,
    "last_uncollectable": 0,
    "total_collected": 0,
}


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

def _try_import_psutil() -> Optional[Any]:
    """尝试导入 psutil，失败返回 ``None``。

    Returns:
        psutil 模块对象，或 ``None``。
    """
    try:
        import psutil  # type: ignore[import]

        return psutil
    except Exception:
        return None


def _read_linux_vmrs() -> int:
    """从 ``/proc/self/status`` 读取 ``VmRSS`` 值（单位：字节）。

    Returns:
        RSS 字节数。若读取失败返回 0。
    """
    try:
        with open(_PROC_STATUS_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS"):
                    # 格式: "VmRSS:    12345 kB"
                    parts = line.split()
                    if len(parts) >= 2:
                        kb = int(parts[1])
                        return kb * 1024
    except Exception:
        pass
    return 0


def _read_windows_memory() -> int:
    """通过 ``ctypes.windll.kernel32.GetProcessMemoryInfo`` 读取工作集大小（字节）。

    Returns:
        WorkingSetSize 字节数。若读取失败返回 0。
    """
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        process_handle = kernel32.GetCurrentProcess()

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        ret = kernel32.GetProcessMemoryInfo(
            process_handle,
            ctypes.byref(pmc),
            pmc.cb,
        )
        if ret:
            return int(pmc.WorkingSetSize)
    except Exception:
        pass
    return 0


def _estimate_memory_fallback() -> int:
    """``sys.getsizeof`` 估算主要对象的内存占用（兜底方案）。

    遍历 ``gc.get_objects()`` 对可达对象进行大小估算。
    注意：该值是**粗略估计**，不包含解释器自身开销和碎片。

    Returns:
        估算字节数。
    """
    total = 0
    try:
        for obj in gc.get_objects():
            try:
                total += sys.getsizeof(obj)
            except Exception:
                # 部分对象不支持 getsizeof
                pass
    except Exception:
        pass
    return total


# ---------------------------------------------------------------------------
# MemoryOptimizer 主类
# ---------------------------------------------------------------------------

class MemoryOptimizer:
    """内存监控与优化器，提供跨平台内存采样、GC 触发、缓存清理与告警能力。

    基本用法：
        >>> mo = MemoryOptimizer(limit_mb=512, gc_interval=300)
        >>> mo.on_alert(lambda current, limit: print(f"内存告警: {current}MB > {limit}MB"))
        >>> await mo.start_monitoring()
        >>> # ... 业务运行中 ...
        >>> report = mo.get_memory_report()
        >>> await mo.cleanup_caches()
        >>> await mo.stop_monitoring()
    """

    def __init__(
        self,
        limit_mb: int = 512,
        gc_interval: int = 300,
        cache_modules: Optional[List[Any]] = None,
    ) -> None:
        """初始化内存优化器。

        Args:
            limit_mb: 内存告警阈值（MB），默认 512。
            gc_interval: 后台监控轮询间隔（秒），默认 300。
            cache_modules: 需要参与缓存清理的模块/对象列表。
                列表中的元素应实现 ``clear_cache()`` 或 ``cleanup()`` 方法。
        """
        self._limit_bytes: int = limit_mb * 1024 * 1024
        self._gc_interval: int = gc_interval
        self._cache_modules: List[Any] = cache_modules or []

        self._monitor_task: Optional[asyncio.Task[None]] = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._peak_bytes: int = 0
        self._current_bytes: int = 0

        self._alert_callbacks: List[Callable[[int, int], None]] = []
        self._gc_stats: Dict[str, int] = dict(_GC_STATS_DEFAULT)

        # psutil 延迟加载缓存
        self._psutil: Optional[Any] = None
        self._psutil_checked: bool = False

    # ------------------------------------------------------------------
    # 公共生命周期
    # ------------------------------------------------------------------

    async def start_monitoring(self) -> None:
        """启动后台异步监控任务。

        创建一个 ``asyncio.Task`` 运行 ``_monitor_loop``，
        按 ``_gc_interval`` 周期采集内存、判断阈值、触发告警与清理。

        Raises:
            RuntimeError: 若监控任务已在运行。
        """
        if self._monitor_task is not None and not self._monitor_task.done():
            raise RuntimeError("内存监控任务已在运行")

        self._stop_event.clear()
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(), name="m6_memory_monitor"
        )

    async def stop_monitoring(self) -> None:
        """停止后台监控任务。

        设置停止事件并等待任务优雅退出，超时 5 秒则强制取消。
        """
        self._stop_event.set()
        if self._monitor_task is None:
            return
        try:
            await asyncio.wait_for(self._monitor_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        finally:
            self._monitor_task = None

    # ------------------------------------------------------------------
    # 监控循环
    # ------------------------------------------------------------------

    async def _monitor_loop(self) -> None:
        """后台监控主循环。

        流程：
        1. 调用 ``get_current_memory()`` 采样 RSS；
        2. 更新峰值；
        3. 若 ``current > limit``，触发所有告警回调，并尝试 ``cleanup_caches``；
        4. 等待 ``_stop_event`` 或 ``_gc_interval`` 超时。
        """
        while not self._stop_event.is_set():
            try:
                current = self.get_current_memory()
                self._current_bytes = current
                if current > self._peak_bytes:
                    self._peak_bytes = current

                if current > self._limit_bytes:
                    # 触发告警
                    self._fire_alerts(current, self._limit_bytes)
                    # 自动尝试清理
                    try:
                        await self.cleanup_caches()
                    except Exception as exc:
                        warnings.warn(
                            f"自动缓存清理失败: {exc}", RuntimeWarning, stacklevel=2
                        )
            except Exception as exc:
                warnings.warn(
                    f"内存监控循环异常: {exc}", RuntimeWarning, stacklevel=2
                )

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=float(self._gc_interval)
                )
            except asyncio.TimeoutError:
                pass  # 正常轮询，继续循环

    def _fire_alerts(self, current_bytes: int, limit_bytes: int) -> None:
        """触发已注册的所有告警回调。

        Args:
            current_bytes: 当前 RSS（字节）。
            limit_bytes: 阈值（字节）。
        """
        current_mb = current_bytes // (1024 * 1024)
        limit_mb = limit_bytes // (1024 * 1024)
        for cb in self._alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    # 异步回调——创建任务不等待
                    asyncio.create_task(cb(current_mb, limit_mb))  # type: ignore[call-arg]
                else:
                    cb(current_mb, limit_mb)
            except Exception as exc:
                warnings.warn(
                    f"告警回调执行失败: {exc}", RuntimeWarning, stacklevel=2
                )

    # ------------------------------------------------------------------
    # 内存读取（跨平台）
    # ------------------------------------------------------------------

    def get_current_memory(self) -> int:
        """获取当前进程 RSS（字节），跨平台实现。

        优先级：
        1. **psutil** — 若已安装则通过 ``psutil.Process().memory_info().rss`` 读取；
        2. **Linux** — 读取 ``/proc/self/status`` 中的 ``VmRSS`` 行；
        3. **Windows** — 通过 ``ctypes.windll.kernel32.GetProcessMemoryInfo`` 读取；
        4. **兜底** — 使用 ``sys.getsizeof`` 对 ``gc.get_objects()`` 进行估算。

        Returns:
            当前 RSS 字节数。所有方法均失败时返回 0。
        """
        # 1) 优先 psutil（延迟加载）
        if not self._psutil_checked:
            self._psutil = _try_import_psutil()
            self._psutil_checked = True

        if self._psutil is not None:
            try:
                proc = self._psutil.Process(os.getpid())
                rss = proc.memory_info().rss
                if isinstance(rss, int) and rss > 0:
                    return rss
            except Exception:
                pass

        # 2) Linux /proc/self/status
        if _IS_LINUX and os.path.exists(_PROC_STATUS_PATH):
            val = _read_linux_vmrs()
            if val > 0:
                return val

        # 3) Windows kernel32
        if _IS_WINDOWS:
            val = _read_windows_memory()
            if val > 0:
                return val

        # 4) 兜底估算
        return _estimate_memory_fallback()

    def get_peak_memory(self) -> int:
        """获取监控期间观测到的峰值 RSS（字节）。

        Returns:
            峰值字节数。若监控尚未启动则返回当前内存值。
        """
        if self._peak_bytes == 0:
            # 尚未采样过，返回当前值并初始化 peak
            self._current_bytes = self.get_current_memory()
            self._peak_bytes = self._current_bytes
        return self._peak_bytes

    # ------------------------------------------------------------------
    # GC 接口
    # ------------------------------------------------------------------

    def trigger_gc(self, generation: int = 2) -> Dict[str, int]:
        """触发 Python 垃圾回收。

        Args:
            generation: 要回收的代（0=年轻代，1=中年代，2=老年代），默认 2（全代）。

        Returns:
            字典包含：
            - ``collected``: 本次回收释放的对象数
            - ``uncollectable``: 无法回收的对象数
            - ``generation``: 执行的代级别
        """
        gen = max(0, min(generation, 2))
        before = gc.get_count()
        collected = gc.collect(generation=gen)
        after = gc.get_count()

        uncollectable = len(gc.garbage)

        # 更新持久化统计
        self._gc_stats["last_collected"] = collected
        self._gc_stats["last_uncollectable"] = uncollectable
        self._gc_stats["total_collected"] += collected
        if gen == 0:
            self._gc_stats["collections_gen0"] += 1
        elif gen == 1:
            self._gc_stats["collections_gen1"] += 1
        elif gen == 2:
            self._gc_stats["collections_gen2"] += 1

        return {
            "collected": collected,
            "uncollectable": uncollectable,
            "generation": gen,
            "gc_count_before": before,
            "gc_count_after": after,
        }

    # ------------------------------------------------------------------
    # 缓存清理
    # ------------------------------------------------------------------

    async def cleanup_caches(self) -> Dict[str, Any]:
        """通过反射调用各模块的清理方法，统一回收缓存。

        对 ``_cache_modules`` 中的每个对象，按以下优先级尝试调用：
        1. ``clear_cache()`` — 同步或异步均可；
        2. ``cleanup()`` — 同步或异步均可；
        3. 若两者皆无，则跳过。

        Returns:
            结果字典：
            - ``cleaned``: 成功清理的模块数
            - ``failed``: 清理失败的模块数
            - ``skipped``: 无清理方法的模块数
            - ``details``: 各模块执行明细
        """
        cleaned = 0
        failed = 0
        skipped = 0
        details: List[Dict[str, str]] = []

        for mod in self._cache_modules:
            mod_name = getattr(mod, "__name__", repr(mod))
            result: Dict[str, str] = {"module": mod_name, "status": "skipped", "detail": ""}

            method = None
            method_name = ""
            for attr_name in ("clear_cache", "cleanup"):
                if hasattr(mod, attr_name):
                    method = getattr(mod, attr_name)
                    method_name = attr_name
                    break

            if method is None:
                skipped += 1
                details.append(result)
                continue

            try:
                if asyncio.iscoroutinefunction(method):
                    await method()
                else:
                    method()
                result["status"] = "cleaned"
                result["detail"] = f"调用 {method_name}() 成功"
                cleaned += 1
            except Exception as exc:
                result["status"] = "failed"
                result["detail"] = f"调用 {method_name}() 失败: {exc}"
                failed += 1

            details.append(result)

        return {
            "cleaned": cleaned,
            "failed": failed,
            "skipped": skipped,
            "details": details,
        }

    # ------------------------------------------------------------------
    # 告警注册
    # ------------------------------------------------------------------

    def on_alert(self, callback: Callable[[int, int], None]) -> None:
        """注册内存超限告警回调函数。

        当 ``get_current_memory()`` 返回值超过 ``limit_mb`` 阈值时，
        所有已注册的回调将被调用，参数为 ``(current_mb, limit_mb)``。

        Args:
            callback: 接收 ``(current_mb: int, limit_mb: int)`` 的回调函数。
                可以是同步函数或异步协程函数。

        Example:
            >>> def my_alert(current: int, limit: int) -> None:
            ...     print(f"告警：内存 {current}MB 超过阈值 {limit}MB")
            >>> mo.on_alert(my_alert)
        """
        self._alert_callbacks.append(callback)

    def remove_alert(self, callback: Callable[[int, int], None]) -> bool:
        """移除已注册的告警回调。

        Args:
            callback: 之前通过 ``on_alert`` 注册的回调函数。

        Returns:
            若找到并移除返回 ``True``，否则 ``False``。
        """
        if callback in self._alert_callbacks:
            self._alert_callbacks.remove(callback)
            return True
        return False

    # ------------------------------------------------------------------
    # 报告
    # ------------------------------------------------------------------

    def get_memory_report(self) -> Dict[str, Any]:
        """生成当前内存状态报告。

        Returns:
            字典包含以下字段：
            - ``current_mb``: 当前 RSS（MB）
            - ``peak_mb``: 峰值 RSS（MB）
            - ``limit_mb``: 告警阈值（MB）
            - ``usage_ratio``: 使用率（current_mb / limit_mb）
            - ``gc_stats``: 垃圾回收累计统计
            - ``timestamp``: 报告生成时间戳
            - ``platform``: 当前操作系统
        """
        current = self.get_current_memory()
        self._current_bytes = current
        if current > self._peak_bytes:
            self._peak_bytes = current

        current_mb = current / (1024 * 1024)
        peak_mb = self._peak_bytes / (1024 * 1024)
        limit_mb = self._limit_bytes / (1024 * 1024)
        ratio = current_mb / limit_mb if limit_mb > 0 else 0.0

        return {
            "current_mb": round(current_mb, 2),
            "peak_mb": round(peak_mb, 2),
            "limit_mb": round(limit_mb, 2),
            "usage_ratio": round(ratio, 4),
            "gc_stats": dict(self._gc_stats),
            "timestamp": time.time(),
            "platform": _SYSTEM,
        }

    # ------------------------------------------------------------------
    # 属性访问
    # ------------------------------------------------------------------

    @property
    def is_monitoring(self) -> bool:
        """判断后台监控任务是否正在运行。"""
        return self._monitor_task is not None and not self._monitor_task.done()

    @property
    def limit_mb(self) -> int:
        """告警阈值（MB）。"""
        return self._limit_bytes // (1024 * 1024)

    @limit_mb.setter
    def limit_mb(self, value: int) -> None:
        """动态修改告警阈值。

        Args:
            value: 新阈值（MB），必须为正整数。
        """
        if value <= 0:
            raise ValueError("limit_mb 必须为正整数")
        self._limit_bytes = value * 1024 * 1024

    def add_cache_module(self, module: Any) -> None:
        """向缓存清理列表追加模块。

        Args:
            module: 需实现 ``clear_cache()`` 或 ``cleanup()`` 方法的对象。
        """
        self._cache_modules.append(module)

    def remove_cache_module(self, module: Any) -> bool:
        """从缓存清理列表移除模块。

        Args:
            module: 之前添加的模块对象。

        Returns:
            成功移除返回 ``True``，未找到返回 ``False``。
        """
        if module in self._cache_modules:
            self._cache_modules.remove(module)
            return True
        return False

    def reset_peak(self) -> None:
        """重置峰值内存记录为当前值。"""
        self._peak_bytes = self.get_current_memory()

    async def force_cleanup(self) -> Dict[str, Any]:
        """强制一键清理：GC + 缓存清理。

        Returns:
            合并结果字典，包含 ``gc_result`` 和 ``cache_result``。
        """
        gc_result = self.trigger_gc(generation=2)
        cache_result = await self.cleanup_caches()
        return {
            "gc_result": gc_result,
            "cache_result": cache_result,
            "current_mb": round(self.get_current_memory() / (1024 * 1024), 2),
        }


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

def get_memory_mb() -> float:
    """获取当前内存使用量的便捷函数（MB）。

    Returns:
        当前 RSS（MB），保留两位小数。
    """
    mo = MemoryOptimizer()
    return round(mo.get_current_memory() / (1024 * 1024), 2)


async def quick_cleanup(cache_modules: Optional[List[Any]] = None) -> Dict[str, Any]:
    """快速一键清理的便捷函数。

    Args:
        cache_modules: 参与缓存清理的模块列表。

    Returns:
        清理结果字典。
    """
    mo = MemoryOptimizer(cache_modules=cache_modules)
    return await mo.force_cleanup()
