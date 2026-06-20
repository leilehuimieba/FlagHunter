"""
CPA M6 Turbo 命令模块 - /turbo 系列交互命令

提供命令行接口用于：
- 查看Turbo加速状态与统计信息
- 管理结果缓存（查看统计、清空缓存）
- 监控和优化内存使用
- 动态启用/禁用工具的turbo wrapper
- 预加载/卸载重型模块
- 执行并发扫描任务

命令列表：
    /turbo                         -- 显示Turbo状态
    /turbo status                  -- 缓存命中率+内存使用+并发状态
    /turbo cache stats             -- 缓存统计
    /turbo cache clear [tool]      -- 清空缓存（可指定工具或全部）
    /turbo memory                  -- 内存使用报告
    /turbo memory cleanup          -- 手动触发GC
    /turbo wrap <tool>             -- 为工具启用turbo
    /turbo unwrap <tool>           -- 为工具禁用turbo
    /turbo wrap list               -- 列出已wrap的工具
    /turbo preload <module>        -- 预加载模块
    /turbo unload <module>         -- 卸载模块
    /turbo parallel <targets...>   -- 并发扫描

集成方式：
    由M0侵入点3在 flaghunter/interface/commands.py 中自动注册。
"""

from __future__ import annotations

import os
import sys
import gc
import time
import logging
from typing import Any, List, Optional

# ---------------------------------------------------------------------------
# 模块级Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
CMD_PREFIX = "/turbo"
SEPARATOR = "─" * 50


# ============================================================================
# 命令处理函数
# ============================================================================

async def cmd_turbo(args: list[str], context: Any = None) -> str:
    """处理 /turbo 命令（无子命令时显示状态概览）。

    Args:
        args: 命令参数列表（不含 '/turbo' 本身）。
        context: 可选的执行上下文。

    Returns:
        格式化后的状态字符串。
    """
    if not args:
        return await _show_status()

    subcmd = args[0].lower()

    # /turbo status
    if subcmd == "status":
        return await _show_status(detailed=True)

    # /turbo cache ...
    if subcmd == "cache":
        return await cmd_turbo_cache(args[1:], context)

    # /turbo memory ...
    if subcmd == "memory":
        return await cmd_turbo_memory(args[1:], context)

    # /turbo wrap ...
    if subcmd == "wrap":
        return await cmd_turbo_wrap(args[1:], context)

    # /turbo unwrap ...
    if subcmd == "unwrap":
        return await _cmd_turbo_unwrap(args[1:], context)

    # /turbo preload ...
    if subcmd == "preload":
        return await cmd_turbo_preload(args[1:], context)

    # /turbo unload ...
    if subcmd == "unload":
        return await _cmd_turbo_unload(args[1:], context)

    # /turbo parallel ...
    if subcmd == "parallel":
        return await cmd_turbo_parallel(args[1:], context)

    return (
        f"[M6 Turbo] 未知子命令: '{subcmd}'\n"
        f"使用 '/turbo' 查看状态，'/turbo status' 查看详细信息。\n"
        f"可用命令: status, cache, memory, wrap, unwrap, preload, unload, parallel"
    )


# ============================================================================
# 子命令：status
# ============================================================================

async def _show_status(detailed: bool = False) -> str:
    """显示Turbo状态。

    Args:
        detailed: 是否显示详细信息。

    Returns:
        格式化状态字符串。
    """
    try:
        from . import (
            is_m6_enabled, is_turbo_active, get_stats,
            _wrapped_tools, _initialized,
        )
    except ImportError:
        return "[M6 Turbo] 模块未加载，无法获取状态"

    enabled = is_m6_enabled()
    turbo_env = os.getenv("CPA_M6_TURBO", "true")
    lines: List[str] = []

    lines.append(f"[M6 Turbo] 状态概览")
    lines.append(SEPARATOR)
    lines.append(f"  开关状态 (CPA_M6_TURBO): {turbo_env}")
    lines.append(f"  初始化状态: {'已完成' if _initialized else '未初始化'}")
    lines.append(f"  运行状态: {'运行中' if enabled else '已禁用/未就绪'}")
    lines.append(f"  已Wrap工具: {len(_wrapped_tools)} 个")
    if _wrapped_tools:
        lines.append(f"    {', '.join(sorted(_wrapped_tools))}")

    if detailed and enabled:
        stats = await get_stats()

        # 缓存统计
        cache_stats = stats.get("cache", {})
        if cache_stats:
            lines.append("")
            lines.append("[缓存统计]")
            hits = cache_stats.get("hits", 0)
            misses = cache_stats.get("misses", 0)
            total = hits + misses
            hit_rate = (hits / total * 100) if total > 0 else 0
            lines.append(f"  命中次数: {hits}")
            lines.append(f"  未命中次数: {misses}")
            lines.append(f"  命中率: {hit_rate:.1f}%")
            lines.append(f"  缓存条目数: {cache_stats.get('size', 0)}")
            lines.append(f"  缓存上限: {cache_stats.get('maxsize', 'N/A')}")

        # 内存统计
        mem_stats = stats.get("memory", {})
        if mem_stats:
            lines.append("")
            lines.append("[内存统计]")
            lines.append(f"  当前使用: {mem_stats.get('current_mb', 'N/A')} MB")
            lines.append(f"  内存上限: {mem_stats.get('limit_mb', 'N/A')} MB")
            lines.append(f"  GC次数: {mem_stats.get('gc_count', 0)}")

        # 扫描器统计
        scanner_stats = stats.get("scanner", {})
        if scanner_stats:
            lines.append("")
            lines.append("[并发扫描]")
            lines.append(f"  当前活跃任务: {scanner_stats.get('active', 0)}")
            lines.append(f"  最大并发: {scanner_stats.get('max_concurrent', 'N/A')}")
            lines.append(f"  单主机限制: {scanner_stats.get('max_per_host', 'N/A')}")
            lines.append(f"  已执行总数: {scanner_stats.get('total_executed', 0)}")

    lines.append(SEPARATOR)
    lines.append("提示: 使用 '/turbo cache stats' 查看缓存详情")
    lines.append("      使用 '/turbo memory' 查看内存详情")
    return "\n".join(lines)


# ============================================================================
# 子命令：cache
# ============================================================================

async def cmd_turbo_cache(args: list[str], context: Any = None) -> str:
    """处理 /turbo cache 子命令。

    用法:
        /turbo cache stats        -- 显示缓存统计
        /turbo cache clear        -- 清空全部缓存
        /turbo cache clear <tool> -- 清空指定工具的缓存

    Args:
        args: 子命令参数。
        context: 可选执行上下文。

    Returns:
        结果字符串。
    """
    if not args:
        return (
            "[M6 Turbo] 缓存命令用法:\n"
            "  /turbo cache stats        -- 缓存统计\n"
            "  /turbo cache clear        -- 清空全部缓存\n"
            "  /turbo cache clear <tool> -- 清空指定工具缓存"
        )

    sub = args[0].lower()

    # /turbo cache stats
    if sub == "stats":
        return await _cache_stats()

    # /turbo cache clear [tool]
    if sub == "clear":
        tool = args[1] if len(args) > 1 else None
        return await _cache_clear(tool)

    return f"[M6 Turbo] 未知cache子命令: '{sub}'"


async def _cache_stats() -> str:
    """获取并格式化缓存统计信息。"""
    try:
        from . import get_cache, is_m6_enabled
    except ImportError:
        return "[M6 Turbo] 模块未加载"

    if not is_m6_enabled():
        return "[M6 Turbo] 加速引擎未启用"

    cache = get_cache()
    if cache is None:
        return "[M6 Turbo] 缓存组件未初始化"

    cs = cache.get_stats()
    hits = cs.total_hits
    misses = cs.total_misses
    total = hits + misses
    hit_rate = cs.hit_rate * 100

    lines: List[str] = []
    lines.append("[M6 Turbo] 缓存统计")
    lines.append(SEPARATOR)
    lines.append(f"  缓存条目: {cs.total_entries} / {cache._max_size}")
    lines.append(f"  命中次数: {hits}")
    lines.append(f"  未命中次数: {misses}")
    lines.append(f"  命中率: {hit_rate:.1f}%")
    lines.append(f"  TTL: {cache._default_ttl} 秒")
    lines.append("")
    lines.append(f"  效率评估: {_rate_cache_efficiency(hit_rate, total)}")
    lines.append(SEPARATOR)
    return "\n".join(lines)


def _rate_cache_efficiency(hit_rate: float, total: int) -> str:
    """评估缓存效率等级。"""
    if total == 0:
        return "暂无数据（尚未有缓存访问）"
    if hit_rate >= 80:
        return "优秀 - 缓存效果极佳"
    elif hit_rate >= 50:
        return "良好 - 缓存效果较好"
    elif hit_rate >= 20:
        return "一般 - 可考虑调整扫描策略"
    else:
        return "较低 - 目标多样性高或缓存TTL过短"


async def _cache_clear(tool: Optional[str] = None) -> str:
    """清空缓存。

    Args:
        tool: 指定工具名则只清空该工具的缓存，None则清空全部。

    Returns:
        结果字符串。
    """
    try:
        from . import get_cache, is_m6_enabled
    except ImportError:
        return "[M6 Turbo] 模块未加载"

    if not is_m6_enabled():
        return "[M6 Turbo] 加速引擎未启用"

    cache = get_cache()
    if cache is None:
        return "[M6 Turbo] 缓存组件未初始化"

    if tool:
        count = cache.invalidate(tool_name=tool.lower())
        return f"[M6 Turbo] 已清空工具 '{tool}' 的缓存 ({count} 条)"
    else:
        count = cache.invalidate()
        return f"[M6 Turbo] 已清空全部缓存 ({count} 条)"


# ============================================================================
# 子命令：memory
# ============================================================================

async def cmd_turbo_memory(args: list[str], context: Any = None) -> str:
    """处理 /turbo memory 子命令。

    用法:
        /turbo memory         -- 显示内存使用报告
        /turbo memory cleanup -- 手动触发垃圾回收

    Args:
        args: 子命令参数。
        context: 可选执行上下文。

    Returns:
        结果字符串。
    """
    if not args:
        return await _memory_report()

    sub = args[0].lower()
    if sub == "cleanup":
        return await _memory_cleanup()

    return f"[M6 Turbo] 未知memory子命令: '{sub}'"


async def _memory_report() -> str:
    """生成内存使用报告。"""
    try:
        import psutil
        has_psutil = True
    except ImportError:
        has_psutil = False

    try:
        from . import get_optimizer, is_m6_enabled
    except ImportError:
        return "[M6 Turbo] 模块未加载"

    lines: List[str] = []
    lines.append("[M6 Turbo] 内存使用报告")
    lines.append(SEPARATOR)

    # 进程内存信息
    if has_psutil:
        process = psutil.Process()
        mem_info = process.memory_info()
        lines.append(f"  进程RSS: {mem_info.rss / 1024 / 1024:.1f} MB")
        lines.append(f"  进程VMS: {mem_info.vms / 1024 / 1024:.1f} MB")
        lines.append(f"  系统可用内存: {psutil.virtual_memory().available / 1024 / 1024:.1f} MB")
    else:
        lines.append("  (psutil未安装，仅显示基础信息)")

    # M6优化器内存信息
    if is_m6_enabled():
        optimizer = get_optimizer()
        if optimizer is not None:
            rep = optimizer.get_memory_report()
            lines.append("")
            lines.append("[M6内存优化器]")
            lines.append(f"  内存上限: {rep.get('limit_mb', 'N/A')} MB")
            lines.append(f"  当前使用: {rep.get('current_mb', 'N/A')} MB")
            gc_stats = rep.get('gc_stats', {})
            lines.append(f"  GC触发次数: {sum(gc_stats.values()) if gc_stats else 0}")
            lines.append(f"  监控状态: {'启用' if optimizer.is_monitoring else '未启用'}")
        else:
            lines.append("")
            lines.append("[M6内存优化器] 未初始化")
    else:
        lines.append("")
        lines.append("[M6 Turbo] 加速引擎未启用")

    lines.append(SEPARATOR)
    return "\n".join(lines)


async def _memory_cleanup() -> str:
    """手动触发垃圾回收。"""
    import gc

    gc_before = gc.get_count()
    collected = gc.collect()
    gc_after = gc.get_count()

    try:
        from . import get_optimizer, is_m6_enabled
        if is_m6_enabled():
            optimizer = get_optimizer()
            if optimizer is not None:
                await optimizer.cleanup_caches()
    except ImportError:
        pass

    return (
        f"[M6 Turbo] 垃圾回收完成\n"
        f"  回收对象数: {collected}\n"
        f"  GC代计数 (前): {gc_before}\n"
        f"  GC代计数 (后): {gc_after}"
    )


# ============================================================================
# 子命令：wrap / unwrap
# ============================================================================

async def cmd_turbo_wrap(args: list[str], context: Any = None) -> str:
    """处理 /turbo wrap 子命令。

    用法:
        /turbo wrap <tool>  -- 为工具启用turbo加速
        /turbo wrap list    -- 列出已wrap的工具

    Args:
        args: 子命令参数。
        context: 可选执行上下文。

    Returns:
        结果字符串。
    """
    if not args:
        return (
            "[M6 Turbo] wrap命令用法:\n"
            "  /turbo wrap <tool>  -- 为工具启用turbo\n"
            "  /turbo wrap list    -- 列出已wrap的工具"
        )

    if args[0].lower() == "list":
        return await _wrap_list()

    tool_name = args[0]
    return await _wrap_add(tool_name)


async def _wrap_add(tool_name: str) -> str:
    """为工具添加turbo wrapper。"""
    try:
        from . import _wrap_tool, is_turbo_active, is_m6_enabled, _wrapped_tools
    except ImportError:
        return "[M6 Turbo] 模块未加载"

    if not is_m6_enabled():
        return "[M6 Turbo] 加速引擎未启用，无法wrap工具"

    if is_turbo_active(tool_name):
        return f"[M6 Turbo] 工具 '{tool_name}' 已经被wrap了"

    _wrap_tool(tool_name)

    if is_turbo_active(tool_name):
        return f"[M6 Turbo] 已为 '{tool_name}' 启用turbo加速"
    else:
        return f"[M6 Turbo] 工具 '{tool_name}' 不在支持列表中，无法wrap"


async def _wrap_list() -> str:
    """列出已wrap的工具。"""
    try:
        from . import is_m6_enabled, _wrapped_tools, _CACHEABLE_TOOLS, _CONCURRENT_TOOLS
    except ImportError:
        return "[M6 Turbo] 模块未加载"

    if not is_m6_enabled():
        return "[M6 Turbo] 加速引擎未启用"

    lines: List[str] = []
    lines.append("[M6 Turbo] 已wrap的工具列表")
    lines.append(SEPARATOR)

    if _wrapped_tools:
        lines.append("当前已加速:")
        for t in sorted(_wrapped_tools):
            cache_mark = "[缓存]" if t in _CACHEABLE_TOOLS else ""
            scan_mark = "[并发]" if t in _CONCURRENT_TOOLS else ""
            marks = " ".join(filter(None, [cache_mark, scan_mark]))
            lines.append(f"  - {t:<15} {marks}")
    else:
        lines.append("  (无)")

    lines.append("")
    lines.append("可加速的工具:")
    supported = _CACHEABLE_TOOLS | _CONCURRENT_TOOLS
    for t in sorted(supported):
        status = "已启用" if t in _wrapped_tools else "未启用"
        lines.append(f"  - {t:<15} ({status})")

    lines.append(SEPARATOR)
    return "\n".join(lines)


async def _cmd_turbo_unwrap(args: list[str], context: Any = None) -> str:
    """处理 /turbo unwrap <tool> 命令。

    Args:
        args: 命令参数。
        context: 可选执行上下文。

    Returns:
        结果字符串。
    """
    if not args:
        return "用法: /turbo unwrap <tool>"

    tool_name = args[0].lower()

    try:
        from . import is_m6_enabled, _wrapped_tools
    except ImportError:
        return "[M6 Turbo] 模块未加载"

    if not is_m6_enabled():
        return "[M6 Turbo] 加速引擎未启用"

    if tool_name not in _wrapped_tools:
        return f"[M6 Turbo] 工具 '{tool_name}' 未被wrap"

    _wrapped_tools.discard(tool_name)
    return f"[M6 Turbo] 已为 '{tool_name}' 禁用turbo加速"


# ============================================================================
# 子命令：preload / unload
# ============================================================================

async def cmd_turbo_preload(args: list[str], context: Any = None) -> str:
    """处理 /turbo preload <module> 命令。

    预加载指定模块以减少首次调用时的延迟。

    Args:
        args: 命令参数。
        context: 可选执行上下文。

    Returns:
        结果字符串。
    """
    if not args:
        return "用法: /turbo preload <module_name>"

    module_name = args[0]

    try:
        from . import LazyLoader
        if LazyLoader is not None:
            loader = LazyLoader()
            start = time.monotonic()
            await loader.load(module_name)
            elapsed = time.monotonic() - start
            return f"[M6 Turbo] 模块 '{module_name}' 预加载完成 ({elapsed:.2f}s)"
        else:
            # 回退到标准import
            start = time.monotonic()
            __import__(module_name)
            elapsed = time.monotonic() - start
            return f"[M6 Turbo] 模块 '{module_name}' 加载完成 ({elapsed:.2f}s) [标准import模式]"
    except ImportError as e:
        return f"[M6 Turbo] 无法加载模块 '{module_name}': {e}"
    except Exception as e:
        return f"[M6 Turbo] 预加载失败: {e}"


async def _cmd_turbo_unload(args: list[str], context: Any = None) -> str:
    """处理 /turbo unload <module> 命令。

    从sys.modules中卸载指定模块以释放内存。

    Args:
        args: 命令参数。
        context: 可选执行上下文。

    Returns:
        结果字符串。
    """
    if not args:
        return "用法: /turbo unload <module_name>"

    module_name = args[0]

    # 安全检查：不允许卸载核心模块
    protected = {"sys", "os", "asyncio", "logging", "gc", "flaghunter.cpa_modules"}
    if module_name in protected or module_name.startswith("flaghunter.cpa_modules.m6_turbo"):
        return f"[M6 Turbo] 模块 '{module_name}' 受保护，不可卸载"

    removed = []
    for mod_name in list(sys.modules.keys()):
        if mod_name == module_name or mod_name.startswith(f"{module_name}."):
            del sys.modules[mod_name]
            removed.append(mod_name)

    if removed:
        return f"[M6 Turbo] 已卸载模块 '{module_name}' ({len(removed)} 个关联模块)"
    else:
        return f"[M6 Turbo] 模块 '{module_name}' 未在内存中加载"


# ============================================================================
# 子命令：parallel
# ============================================================================

async def cmd_turbo_parallel(args: list[str], context: Any = None) -> str:
    """处理 /turbo parallel <targets...> 命令。

    对多个目标执行并发扫描。

    Args:
        args: 目标列表（每个元素是一个目标地址）。
        context: 可选执行上下文，可包含tool_name和params。

    Returns:
        结果字符串。
    """
    if not args:
        return (
            "用法: /turbo parallel <target1> [target2] ...\n"
            "  需要上下文提供 tool_name 和 params\n"
            "  示例: /turbo parallel 192.168.1.1 192.168.1.2 192.168.1.3"
        )

    targets = args

    try:
        from . import get_scanner, is_m6_enabled
    except ImportError:
        return "[M6 Turbo] 模块未加载"

    if not is_m6_enabled():
        return "[M6 Turbo] 加速引擎未启用"

    scanner = get_scanner()
    if scanner is None:
        return "[M6 Turbo] 并发扫描器未初始化"

    # 从上下文获取工具名和参数
    tool_name = "nmap"  # 默认
    params: dict[str, Any] = {}
    if context is not None:
        if hasattr(context, "tool_name"):
            tool_name = context.tool_name
        if hasattr(context, "params"):
            params = context.params

    lines: List[str] = []
    lines.append(f"[M6 Turbo] 并发扫描: {tool_name}")
    lines.append(f"  目标: {', '.join(targets)}")
    lines.append(SEPARATOR)

    start = time.monotonic()
    try:
        task_tuples = [(tool_name, t, params) for t in targets]
        batch_result = await scanner.execute_batch_simple(task_tuples)
        elapsed = time.monotonic() - start

        lines.append(f"  完成! 耗时: {elapsed:.2f}s")
        lines.append(f"  目标数: {len(targets)}")
        lines.append(f"  完成: {batch_result.completed}  失败: {batch_result.failed}")

    except Exception as e:
        lines.append(f"  并发扫描失败: {e}")

    lines.append(SEPARATOR)
    return "\n".join(lines)


# ============================================================================
# 命令注册辅助函数（供M0侵入点3调用）
# ============================================================================

def register_turbo_commands(command_registry: Any) -> None:
    """将/turbo系列命令注册到命令注册表。

    .. note::
        预留接口：当前 **尚未接线**。仓库内没有 ``command_registry`` 消费者，
        TUI 的 ``/turbo`` 系列命令实际由 ``interface/tui.py`` 的
        ``_parse_turbo_command`` 硬编码分发。本函数保留以便将来统一命令注册体系。

    Args:
        command_registry: 命令注册表对象，需有 register 方法。
    """
    commands = {
        "/turbo": cmd_turbo,
        "/turbo_status": cmd_turbo_status,
        "/turbo_cache": cmd_turbo_cache,
        "/turbo_memory": cmd_turbo_memory,
        "/turbo_wrap": cmd_turbo_wrap,
        "/turbo_preload": cmd_turbo_preload,
        "/turbo_parallel": cmd_turbo_parallel,
    }

    for name, func in commands.items():
        try:
            command_registry.register(name, func)
            logger.debug("M6 Turbo: 命令 '%s' 已注册", name)
        except Exception as exc:
            logger.warning("M6 Turbo: 命令 '%s' 注册失败: %s", name, exc)

    logger.info("M6 Turbo: %d 个命令已注册到命令系统", len(commands))


# 别名函数（供register_turbo_commands引用）
async def cmd_turbo_status(args: list[str] = None, context: Any = None) -> str:
    """/turbo_status 命令入口。"""
    return await _show_status(detailed=True)


# ============================================================================
# __all__
# ============================================================================

__all__ = [
    # 主命令入口
    "cmd_turbo",
    # 子命令入口
    "cmd_turbo_status",
    "cmd_turbo_cache",
    "cmd_turbo_memory",
    "cmd_turbo_wrap",
    "cmd_turbo_preload",
    "cmd_turbo_parallel",
    # 注册函数
    "register_turbo_commands",
    # 别名（向后兼容）
    "cmd_turbo_unwrap",
    "cmd_turbo_unload",
]

# 向后兼容别名
cmd_turbo_unwrap = _cmd_turbo_unwrap
cmd_turbo_unload = _cmd_turbo_unload
