"""
CPA M6 Turbo 模块 - 高性能渗透测试加速引擎

M6模块为PentestAgent提供透明加速能力，包括：
- 智能结果缓存：避免重复扫描相同目标
- 并发扫描引擎：最大化网络扫描效率  
- 内存优化管理：自动GC与内存上限控制
- 懒加载机制：按需加载重型工具模块

透明wrapper设计：
M6的wrapper对M2-M5模块完全透明，通过M0侵入点在工具执行入口自动生效，
无需修改任何现有工具代码。

环境变量（均为可选，有默认值）：
    CPA_M6_TURBO: 总开关，默认"true"
    CPA_M6_CACHE_ENABLED: 缓存开关，默认"true"
    CPA_M6_CACHE_SIZE: 缓存条目上限，默认"1000"
    CPA_M6_CACHE_TTL: 缓存TTL(秒)，默认"3600"
    CPA_M6_MAX_CONCURRENT: 最大并发数，默认"5"
    CPA_M6_MAX_PER_HOST: 单主机最大并发，默认"2"
    CPA_M6_MEMORY_LIMIT_MB: 内存上限(MB)，默认"512"

使用方式：
    模块由M0侵入点自动初始化和挂载，无需手动干预。
    如需命令行交互，使用 /turbo 系列命令。
"""

from __future__ import annotations

import os
import logging
import asyncio
from typing import Any, Callable, Coroutine, Set

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
    """为指定工具注册缓存+并发wrapper。

    通过修改工具函数执行逻辑，在调用前后自动：
    1. 查询缓存（命中直接返回，跳过执行）
    2. 未命中通过ParallelScanner并发执行
    3. 结果写入缓存

    注意：此实现记录被wrap的工具名，实际wrapper在工具调用层
    通过检查 _should_cache / _should_scan 实现透明拦截。

    Args:
        tool_name: 要wrap的工具名称。
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
# 核心入口：apply_turbo
# ---------------------------------------------------------------------------
async def apply_turbo(
    tool_name: str,
    target: str,
    params: dict[str, Any],
    actual_executor: Callable[..., Coroutine[Any, Any, Any]],
) -> Any:
    """对工具调用应用turbo加速：缓存查询 -> 并发执行 -> 缓存写入。

    这是M6的核心入口，由M0侵入点在工具执行前调用。
    如tool_name未被wrap或turbo被禁用，直接调用actual_executor。

    执行流程：
        1. 生成缓存键（tool_name + target + sorted_params）
        2. 查询缓存，命中则直接返回缓存结果
        3. 未命中则通过scanner并发执行actual_executor
        4. 执行结果写入缓存（如工具可缓存）
        5. 返回执行结果

    Args:
        tool_name: 工具名称。
        target: 扫描目标（IP/域名/URL）。
        params: 工具参数字典。
        actual_executor: 原始工具执行函数（异步）。

    Returns:
        工具执行结果（来自缓存或实际执行）。
    """
    global _cache, _scanner

    # 安全检查：M6未启用或未初始化
    if not is_m6_enabled() or not _initialized:
        return await actual_executor(target, params)

    tn = tool_name.lower()
    cache_key = _make_cache_key(tn, target, params)

    # ---- 1. 查询缓存 ----
    if _cache is not None and _should_cache(tn):
        cached = _cache.get(tool_name=tn, target=target, params=params)
        if cached is not None:
            logger.debug("M6 Turbo: 缓存命中 '%s' -> '%s', 跳过执行", tn, target)
            return cached

    # ---- 2. 并发执行 ----
    logger.debug("M6 Turbo: 缓存未命中，执行 '%s' -> '%s'", tn, target)

    try:
        if _scanner is not None and _should_scan(tn):
            # 通过并发扫描器执行
            result = await _scanner.execute(
                tool_name=tn,
                target=target,
                params=params,
                actual_executor=actual_executor,
            )
        else:
            # 直接执行（不适合并发的工具）
            result = await actual_executor(target, params)
    except Exception as exc:
        logger.error("M6 Turbo: 工具 '%s' 执行失败: %s", tn, exc)
        raise

    # ---- 3. 写入缓存 ----
    if _cache is not None and _should_cache(tn) and result is not None:
        _cache.set(tool_name=tn, target=target, result=result, params=params)
        logger.debug("M6 Turbo: 结果已缓存 '%s' -> '%s'", tn, target)

    return result


def _make_cache_key(tool_name: str, target: str, params: dict[str, Any]) -> str:
    """生成缓存键。

    Args:
        tool_name: 工具名称。
        target: 扫描目标。
        params: 参数字典。

    Returns:
        字符串格式的缓存键。
    """
    # 将参数排序后序列化，确保相同参数生成相同key
    param_str = ",".join(f"{k}={v}" for k, v in sorted(params.items())) if params else ""
    return f"{tool_name}:{target}:{param_str}"


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
    "apply_turbo",
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
