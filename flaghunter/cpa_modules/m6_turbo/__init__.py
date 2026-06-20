"""
CPA M6 Turbo 模块 - 高性能渗透测试加速引擎

M6 为 FlagHunter 提供性能加速基础设施：
- 智能结果缓存（``ResultCache``）：避免重复扫描相同目标
- 并发扫描引擎（``ParallelScanner``）：最大化网络扫描效率
- 内存优化管理（``MemoryOptimizer``）：自动GC与内存上限控制
- 懒加载工具（``LazyLoader``）：按需加载重型工具模块

环境变量（均为可选，有默认值）：
    CPA_M6_TURBO: 总开关，默认"true"
    CPA_M6_CACHE_ENABLED: 缓存开关，默认"true"
    CPA_M6_CACHE_SIZE: 缓存条目上限，默认"1000"
    CPA_M6_CACHE_TTL: 缓存TTL(秒)，默认"3600"
    CPA_M6_MAX_CONCURRENT: 最大并发数，默认"5"
    CPA_M6_MAX_PER_HOST: 单主机最大并发，默认"2"
    CPA_M6_MEMORY_LIMIT_MB: 内存上限(MB)，默认"512"

接线现状（与设计意图的差异，避免名实不符）：
    - 初始化：由 ``flaghunter/session/initializer.py`` 的 CPA M6 钩子调用
      ``init_m6()`` 完成（按 CPA_M6_TURBO 门控），并非"M0 侵入点"自动挂载。
    - 交互入口：当前实际可用面是 ``/turbo`` 系列命令（经 TUI 的
      ``_parse_turbo_command`` 硬编码分发）。
    - 透明 wrapper：曾设计一个工具执行入口拦截器对 M2–M5 透明加速，
      但该"自动挂载"始终未接线（工具执行层无调用点），已作为死代码移除。
      ``_wrap_tool()`` 不替换任何工具函数，仅把工具名登记进 ``_wrapped_tools``，
      供 ``/turbo wrap`` 命令与 ``is_turbo_active()`` 查询展示之用。缓存与并发能力
      经 ``ResultCache`` / ``ParallelScanner`` 实例及 ``/turbo`` 命令直接使用。
"""

from __future__ import annotations

import os
import logging
import asyncio
from typing import Any, Set

# ---------------------------------------------------------------------------
# 子模块导入（懒加载失败时提供占位）
# ---------------------------------------------------------------------------
try:
    from .result_cache import ResultCache
except ImportError:
    ResultCache = None  # type: ignore

try:
    from .parallel_scanner import ParallelScanner
except ImportError:
    ParallelScanner = None  # type: ignore

try:
    from .lazy_loader import LazyLoader
except ImportError:
    LazyLoader = None  # type: ignore

try:
    from .memory_optimizer import MemoryOptimizer
except ImportError:
    MemoryOptimizer = None  # type: ignore

# ---------------------------------------------------------------------------
# 模块级Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 单例变量（模块级唯一实例）
# ---------------------------------------------------------------------------
_cache: ResultCache | None = None
_scanner: ParallelScanner | None = None
_loader: LazyLoader | None = None
_optimizer: MemoryOptimizer | None = None
_initialized: bool = False
_wrapped_tools: Set[str] = set()

# ---------------------------------------------------------------------------
# 配置常量（从环境变量读取，带默认值）
# ---------------------------------------------------------------------------
ENV_DEFAULTS = {
    "CPA_M6_TURBO": "true",
    "CPA_M6_CACHE_ENABLED": "true",
    "CPA_M6_CACHE_SIZE": "1000",
    "CPA_M6_CACHE_TTL": "3600",
    "CPA_M6_MAX_CONCURRENT": "5",
    "CPA_M6_MAX_PER_HOST": "2",
    "CPA_M6_MEMORY_LIMIT_MB": "512",
}

# 适合并发扫描的工具列表（网络IO密集型）
_CONCURRENT_TOOLS: Set[str] = {
    "nmap", "sqlmap", "hydra", "nikto", "dirb", "gobuster",
    "wfuzz", "masscan", "zap", "w3af", "whatweb", "wpscan",
}

# 适合缓存的工具列表（结果确定性的工具）
_CACHEABLE_TOOLS: Set[str] = {
    "nmap", "sqlmap", "nikto", "dirb", "gobuster", "whatweb",
    "wpscan", "dnsenum", "sublist3r", "theharvester",
}


# ---------------------------------------------------------------------------
# 私有辅助函数
# ---------------------------------------------------------------------------
def _read_config() -> dict[str, Any]:
    """从环境变量读取M6模块配置。

    Returns:
        配置字典，包含所有M6相关参数。
    """
    return {
        "turbo_enabled": os.getenv("CPA_M6_TURBO", ENV_DEFAULTS["CPA_M6_TURBO"]).lower() == "true",
        "cache_enabled": os.getenv("CPA_M6_CACHE_ENABLED", ENV_DEFAULTS["CPA_M6_CACHE_ENABLED"]).lower() == "true",
        "cache_size": int(os.getenv("CPA_M6_CACHE_SIZE", ENV_DEFAULTS["CPA_M6_CACHE_SIZE"])),
        "cache_ttl": int(os.getenv("CPA_M6_CACHE_TTL", ENV_DEFAULTS["CPA_M6_CACHE_TTL"])),
        "max_concurrent": int(os.getenv("CPA_M6_MAX_CONCURRENT", ENV_DEFAULTS["CPA_M6_MAX_CONCURRENT"])),
        "max_per_host": int(os.getenv("CPA_M6_MAX_PER_HOST", ENV_DEFAULTS["CPA_M6_MAX_PER_HOST"])),
        "memory_limit_mb": int(os.getenv("CPA_M6_MEMORY_LIMIT_MB", ENV_DEFAULTS["CPA_M6_MEMORY_LIMIT_MB"])),
    }


def _should_cache(tool_name: str) -> bool:
    """检查指定工具的结果是否适合缓存。

    Args:
        tool_name: 工具名称（小写）。

    Returns:
        如果工具结果可缓存返回True。
    """
    if not is_m6_enabled():
        return False
    return tool_name.lower() in _CACHEABLE_TOOLS


def _should_scan(tool_name: str) -> bool:
    """检查指定工具是否适合并发扫描。

    Args:
        tool_name: 工具名称（小写）。

    Returns:
        如果工具适合并发执行返回True。
    """
    if not is_m6_enabled():
        return False
    return tool_name.lower() in _CONCURRENT_TOOLS


# ---------------------------------------------------------------------------
# 透明wrapper注册（私有方法）
# ---------------------------------------------------------------------------
def _wrap_tool(tool_name: str) -> None:
    """把工具名登记为"已 turbo"，供查询/展示之用。

    本函数 **不** 替换或包裹任何工具函数——仅在工具名属于可缓存或可并发列表时
    将其加入 ``_wrapped_tools`` 集合。该集合被 ``is_turbo_active()`` 与
    ``/turbo wrap list`` 命令读取，用于呈现"哪些工具声明启用了 turbo"。

    历史背景：早期设计曾计划由工具执行层统一调用一个 turbo 拦截器做透明加速
    （缓存命中跳过执行 / 未命中走 ParallelScanner / 旁路），但该接线始终不存在，
    相关入口已作为死代码移除。当前实际加速通过 ``ResultCache`` / ``ParallelScanner``
    实例与 ``/turbo`` 命令直接驱动。

    Args:
        tool_name: 要登记的工具名称。
    """
    global _wrapped_tools
    tn = tool_name.lower()

    if tn in _wrapped_tools:
        logger.debug("工具 '%s' 已被wrap，跳过", tn)
        return

    # 检查工具是否支持缓存或并发
    if not _should_cache(tn) and not _should_scan(tn):
        logger.debug("工具 '%s' 不在加速列表中，跳过wrap", tn)
        return

    _wrapped_tools.add(tn)
    logger.info("M6 Turbo: 已为工具 '%s' 注册透明wrapper", tn)


def _wrap_tools(*tool_names: str) -> None:
    """批量wrap多个工具。

    Args:
        tool_names: 要wrap的工具名称列表。
    """
    for name in tool_names:
        _wrap_tool(name)


# ---------------------------------------------------------------------------
# 初始化函数
# ---------------------------------------------------------------------------
async def init_m6() -> bool:
    """初始化M6 Turbo模块。

    执行流程：
        1. 检查CPA_M6_TURBO开关（默认true）
        2. 检查重复初始化
        3. 从环境变量读取配置
        4. 创建ResultCache、ParallelScanner、MemoryOptimizer实例
        5. 启动内存监控（如memory_limit > 0）
        6. 全局wrapper注册（nmap, sqlmap, hydra, nikto）
        7. 标记初始化完成

    Returns:
        初始化成功返回True，否则返回False。
    """
    global _cache, _scanner, _optimizer, _initialized, _wrapped_tools

    # ---- 1. 检查总开关 ----
    cfg = _read_config()
    if not cfg["turbo_enabled"]:
        logger.info("M6 Turbo: 开关关闭 (CPA_M6_TURBO=false)，跳过初始化")
        return False

    # ---- 2. 防重复初始化 ----
    if _initialized:
        logger.debug("M6 Turbo: 已经初始化，跳过")
        return True

    logger.info("M6 Turbo: 开始初始化...")

    # ---- 3. 创建组件（子模块可能缺失，做防护） ----
    try:
        if cfg["cache_enabled"] and ResultCache is not None:
            _cache = ResultCache(
                max_size=cfg["cache_size"],
                default_ttl=cfg["cache_ttl"],
            )
            logger.info("M6 Turbo: ResultCache 已创建 (size=%d, ttl=%ds)",
                        cfg["cache_size"], cfg["cache_ttl"])
        else:
            logger.info("M6 Turbo: 缓存已禁用或ResultCache不可用")

        if ParallelScanner is not None:
            _scanner = ParallelScanner(
                max_concurrent=cfg["max_concurrent"],
                max_per_host=cfg["max_per_host"],
            )
            logger.info("M6 Turbo: ParallelScanner 已创建 (concurrent=%d, per_host=%d)",
                        cfg["max_concurrent"], cfg["max_per_host"])

        if MemoryOptimizer is not None and cfg["memory_limit_mb"] > 0:
            _optimizer = MemoryOptimizer(
                limit_mb=cfg["memory_limit_mb"],
            )
            # 启动内存监控协程（后台）
            asyncio.create_task(_optimizer.start_monitoring())
            logger.info("M6 Turbo: MemoryOptimizer 已创建 (limit=%dMB)",
                        cfg["memory_limit_mb"])
    except Exception as exc:
        logger.error("M6 Turbo: 组件创建失败: %s", exc)
        return False

    # ---- 4. 全局wrapper注册 ----
    default_tools = ("nmap", "sqlmap", "hydra", "nikto")
    _wrap_tools(*default_tools)
    logger.info("M6 Turbo: 已为 %d 个工具注册透明wrapper: %s",
                len(_wrapped_tools), sorted(_wrapped_tools))

    # ---- 5. 标记完成 ----
    _initialized = True
    logger.info("M6 Turbo: 初始化完成，加速引擎已就绪")
    return True


async def shutdown_m6() -> None:
    """关闭M6 Turbo模块，释放资源。"""
    global _cache, _scanner, _optimizer, _initialized, _wrapped_tools

    logger.info("M6 Turbo: 正在关闭...")

    if _scanner is not None:
        await _scanner.cancel_all()
        _scanner = None

    if _cache is not None:
        _cache.stop()
        _cache = None

    if _optimizer is not None:
        await _optimizer.stop_monitoring()
        _optimizer = None

    _wrapped_tools.clear()
    _initialized = False
    logger.info("M6 Turbo: 已关闭")


# ---------------------------------------------------------------------------
# Getter函数
# ---------------------------------------------------------------------------
def get_cache() -> ResultCache | None:
    """获取ResultCache单例实例。

    Returns:
        ResultCache实例或None（未初始化或缓存禁用）。
    """
    return _cache


def get_scanner() -> ParallelScanner | None:
    """获取ParallelScanner单例实例。

    Returns:
        ParallelScanner实例或None（未初始化）。
    """
    return _scanner


def get_optimizer() -> MemoryOptimizer | None:
    """获取MemoryOptimizer单例实例。

    Returns:
        MemoryOptimizer实例或None（未初始化或内存优化禁用）。
    """
    return _optimizer


def is_m6_enabled() -> bool:
    """检查M6 Turbo模块是否启用。

    Returns:
        模块开关打开且已初始化返回True。
    """
    return os.getenv("CPA_M6_TURBO", ENV_DEFAULTS["CPA_M6_TURBO"]).lower() == "true"


def is_turbo_active(tool_name: str) -> bool:
    """检查指定工具是否正在被turbo加速。

    Args:
        tool_name: 工具名称。

    Returns:
        工具已被wrap且M6已启用返回True。
    """
    return is_m6_enabled() and tool_name.lower() in _wrapped_tools


# ---------------------------------------------------------------------------
# 统计信息
# ---------------------------------------------------------------------------
async def get_stats() -> dict[str, Any]:
    """获取M6 Turbo模块的运行时统计信息。

    Returns:
        包含缓存命中率、内存使用、并发状态等信息的字典。
    """
    stats: dict[str, Any] = {
        "enabled": is_m6_enabled(),
        "initialized": _initialized,
        "wrapped_tools": sorted(_wrapped_tools),
        "cache": {},
        "memory": {},
        "scanner": {},
    }

    if _cache is not None:
        cs = _cache.get_stats()
        stats["cache"] = {
            "hits": cs.total_hits, "misses": cs.total_misses,
            "size": cs.total_entries, "maxsize": _cache._max_size,
            "ttl": _cache._default_ttl,
        }

    if _optimizer is not None:
        stats["memory"] = _optimizer.get_memory_report()

    if _scanner is not None:
        stats["scanner"] = {
            "active": 0,
            "max_concurrent": _scanner._max_concurrent,
            "max_per_host": _scanner._max_per_host,
            "total_executed": 0,
        }

    return stats


# ---------------------------------------------------------------------------
# __all__ 导出
# ---------------------------------------------------------------------------
__all__ = [
    # 核心函数
    "init_m6",
    "shutdown_m6",
    "get_stats",
    # Getter
    "get_cache",
    "get_scanner",
    "get_optimizer",
    # 状态检查
    "is_m6_enabled",
    "is_turbo_active",
    # 子模块类型（用于类型提示）
    "ResultCache",
    "ParallelScanner",
    "LazyLoader",
    "MemoryOptimizer",
]
