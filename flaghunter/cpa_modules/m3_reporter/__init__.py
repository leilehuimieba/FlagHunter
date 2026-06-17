# -*- coding: utf-8 -*-
"""
CPA M3 Reporter 模块 — 渗透测试报告生成与管理

功能概述
========
M3 Reporter 是 FlagHunter 的报告生成子系统，负责：
- 基于模板的报告渲染（HTML / Markdown / PDF）
- 增量式漏洞发现追踪
- 自动截图捕获与附件管理
- 命令执行历史的自动记录
- 多格式报告导出与自动保存

环境变量
========
- ``CPA_M3_REPORTER``     : 总开关，默认 "true"
- ``CPA_M3_OUTPUT_DIR``   : 报告输出目录，默认 "./reports"
- ``CPA_M3_COMPANY_NAME`` : 报告中的公司/团队名称，默认 "CPA安全团队"
- ``CPA_M3_TEMPLATE``     : 默认模板名称，默认 "default"
- ``CPA_M3_AUTO_SAVE``    : 是否启用自动保存，默认 "true"

使用示例
========
>>> import asyncio
>>> from flaghunter.cpa_modules.m3_reporter import init_m3, get_report_generator
>>> asyncio.run(init_m3())
>>> generator = get_report_generator()
>>> generator.create_report("Web渗透测试报告")

:author: CPA安全团队
:version: 1.0.0
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import TYPE_CHECKING

# ---------------------------------------------------------------------------
# 相对导入子模块 — 仅在类型检查时循环引用，运行时正常导入
# ---------------------------------------------------------------------------
from .template_engine import TemplateEngine
from .report_generator import ReportGenerator
from .screenshot_catcher import ScreenshotCatcher
from .incremental_tracker import IncrementalTracker
from .report_models import PentestReport, ReportMeta, Finding, Severity

if TYPE_CHECKING:
    from .template_engine import TemplateEngine as _TemplateEngine
    from .report_generator import ReportGenerator as _ReportGenerator
    from .screenshot_catcher import ScreenshotCatcher as _ScreenshotCatcher
    from .incremental_tracker import IncrementalTracker as _IncrementalTracker

__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# 模块级日志
# ---------------------------------------------------------------------------
logger = logging.getLogger("cpa.m3_reporter")

# ---------------------------------------------------------------------------
# 模块级单例变量 — 由 init_m3() 初始化后填充
# ---------------------------------------------------------------------------
_template_engine: _TemplateEngine | None = None
_report_generator: _ReportGenerator | None = None
_screenshot_catcher: _ScreenshotCatcher | None = None
_incremental_tracker: _IncrementalTracker | None = None
_initialized: bool = False

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_ENV_MASTER_SWITCH = "CPA_M3_REPORTER"
_ENV_OUTPUT_DIR = "CPA_M3_OUTPUT_DIR"
_ENV_COMPANY_NAME = "CPA_M3_COMPANY_NAME"
_ENV_TEMPLATE = "CPA_M3_TEMPLATE"
_ENV_AUTO_SAVE = "CPA_M3_AUTO_SAVE"

_DEFAULT_OUTPUT_DIR = "./reports"
_DEFAULT_COMPANY_NAME = "CPA安全团队"
_DEFAULT_TEMPLATE = "default"


# ===========================================================================
# 初始化
# ===========================================================================

async def init_m3() -> None:
    """初始化 M3 Reporter 模块。

    执行流程：
        1. 读取 ``CPA_M3_REPORTER`` 环境变量，若值为 ``"false"`` 则直接跳过。
        2. 检查重复初始化（``_initialized`` 标志），防止多次调用产生多余实例。
        3. 从环境变量读取各项配置（输出目录、公司名、模板、自动保存）。
        4. 按依赖顺序异步创建子组件：
           ``TemplateEngine`` → ``ReportGenerator`` → ``ScreenshotCatcher`` → ``IncrementalTracker``
        5. 标记 ``_initialized = True``。

    异常处理：
        初始化过程中任何异常均被捕获并记录为 warning，**不会向上抛出**，
        避免阻塞主程序（M1/M2）的正常启动。

    Returns:
        None

    Raises:
        不抛出任何异常（内部全捕获）。

    Example:
        >>> import asyncio
        >>> asyncio.run(init_m3())
    """
    global _template_engine, _report_generator, _screenshot_catcher
    global _incremental_tracker, _initialized

    # -- 1. 总开关检查 ------------------------------------------------------
    if os.getenv(_ENV_MASTER_SWITCH, "true").lower() != "true":
        logger.info("M3 Reporter 已通过 %s 禁用，跳过初始化。", _ENV_MASTER_SWITCH)
        return

    # -- 2. 重复初始化防护 --------------------------------------------------
    if _initialized:
        logger.debug("M3 Reporter 已初始化，跳过重复调用。")
        return

    try:
        # -- 3. 读取配置 ----------------------------------------------------
        output_dir = os.getenv(_ENV_OUTPUT_DIR, _DEFAULT_OUTPUT_DIR)
        company_name = os.getenv(_ENV_COMPANY_NAME, _DEFAULT_COMPANY_NAME)
        template_name = os.getenv(_ENV_TEMPLATE, _DEFAULT_TEMPLATE)
        auto_save = os.getenv(_ENV_AUTO_SAVE, "true").lower() == "true"

        logger.info(
            "M3 Reporter 初始化开始 — output_dir=%s, company=%s, template=%s, auto_save=%s",
            output_dir, company_name, template_name, auto_save,
        )

        # -- 4. 创建子组件 --------------------------------------------------
        # 模板目录：当前模块所在目录下的 templates/ 文件夹
        module_dir = Path(__file__).resolve().parent
        template_dir = module_dir / "templates"

        _template_engine = TemplateEngine(
            template_dir=str(template_dir),
        )
        logger.debug("TemplateEngine 已创建: template_dir=%s", template_dir)

        _report_generator = ReportGenerator(
            template_engine=_template_engine,
            output_dir=output_dir,
        )
        logger.debug("ReportGenerator 已创建: output_dir=%s", output_dir)

        _screenshot_catcher = ScreenshotCatcher(
            output_dir=output_dir,
        )
        logger.debug("ScreenshotCatcher 已创建。")

        _incremental_tracker = IncrementalTracker(
            report_generator=_report_generator,
        )
        logger.debug("IncrementalTracker 已创建。")

        # -- 5. 标记初始化完成 ----------------------------------------------
        _initialized = True
        logger.info("M3 Reporter 初始化完成（版本 %s）。", __version__)

    except Exception as exc:
        # 初始化失败仅记录日志，不阻塞主程序
        logger.warning("M3 Reporter 初始化失败: %s", exc, exc_info=True)
        _initialized = False


# ===========================================================================
# Getter 函数
# ===========================================================================

def get_report_generator() -> ReportGenerator:
    """获取已初始化的 ReportGenerator 单例实例。

    Returns:
        ReportGenerator: 报告生成器实例。

    Raises:
        RuntimeError: 若 M3 Reporter 尚未初始化（未调用 ``init_m3()``）。
    """
    if not _initialized or _report_generator is None:
        raise RuntimeError("M3 Reporter 未初始化，请先调用 init_m3()")
    return _report_generator


def get_screenshot_catcher() -> ScreenshotCatcher:
    """获取已初始化的 ScreenshotCatcher 单例实例。

    Returns:
        ScreenshotCatcher: 截图捕获器实例。

    Raises:
        RuntimeError: 若 M3 Reporter 尚未初始化。
    """
    if not _initialized or _screenshot_catcher is None:
        raise RuntimeError("M3 Reporter 未初始化，请先调用 init_m3()")
    return _screenshot_catcher


def get_incremental_tracker() -> IncrementalTracker:
    """获取已初始化的 IncrementalTracker 单例实例。

    Returns:
        IncrementalTracker: 增量追踪器实例。

    Raises:
        RuntimeError: 若 M3 Reporter 尚未初始化。
    """
    if not _initialized or _incremental_tracker is None:
        raise RuntimeError("M3 Reporter 未初始化，请先调用 init_m3()")
    return _incremental_tracker


# ===========================================================================
# 工具函数
# ===========================================================================

def is_m3_enabled() -> bool:
    """检查 M3 Reporter 模块是否通过环境变量启用。

    Returns:
        bool: 当 ``CPA_M3_REPORTER`` 不为 ``"false"`` 时返回 ``True``。
    """
    return os.getenv(_ENV_MASTER_SWITCH, "true").lower() == "true"


def get_m3_status() -> dict:
    """获取 M3 Reporter 模块当前状态（用于调试与诊断）。

    Returns:
        dict: 包含初始化状态、各组件是否存在、配置信息的字典。
    """
    return {
        "enabled": is_m3_enabled(),
        "initialized": _initialized,
        "version": __version__,
        "components": {
            "template_engine": _template_engine is not None,
            "report_generator": _report_generator is not None,
            "screenshot_catcher": _screenshot_catcher is not None,
            "incremental_tracker": _incremental_tracker is not None,
        },
        "config": {
            "output_dir": os.getenv(_ENV_OUTPUT_DIR, _DEFAULT_OUTPUT_DIR),
            "company_name": os.getenv(_ENV_COMPANY_NAME, _DEFAULT_COMPANY_NAME),
            "template": os.getenv(_ENV_TEMPLATE, _DEFAULT_TEMPLATE),
            "auto_save": os.getenv(_ENV_AUTO_SAVE, "true").lower() == "true",
        },
    }


# ===========================================================================
# 导出声明
# ===========================================================================

__all__ = [
    # 初始化与状态
    "init_m3",
    "is_m3_enabled",
    "get_m3_status",
    # Getter
    "get_report_generator",
    "get_screenshot_catcher",
    "get_incremental_tracker",
    # 类
    "TemplateEngine",
    "ReportGenerator",
    "ScreenshotCatcher",
    "IncrementalTracker",
    # 数据模型
    "PentestReport",
    "ReportMeta",
    "Finding",
    "Severity",
]
