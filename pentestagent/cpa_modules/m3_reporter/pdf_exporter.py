"""PDF报告导出器模块。

提供将渗透测试报告导出为PDF文件的功能，
采用延迟加载Playwright策略，先生成临时HTML再转为PDF。
"""

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .report_models import PentestReport
    from .template_engine import TemplateEngine

logger = logging.getLogger(__name__)

_PW_AVAILABLE = False
_pw = None


def _get_playwright():
    """延迟加载并返回Playwright异步上下文管理器。

    首次调用时尝试导入 ``playwright.async_api``；
    若未安装则静默失败，后续可通过 ``_ensure_playwright()`` 检查可用性。

    返回:
        Playwright异步上下文管理器，或 ``None``（导入失败时）。
    """
    global _PW_AVAILABLE, _pw
    if _pw is None:
        try:
            from playwright.async_api import async_playwright
            _pw = async_playwright
            _PW_AVAILABLE = True
        except ImportError:
            pass
    return _pw


def _ensure_playwright() -> bool:
    """检查Playwright是否可用。

    返回:
        若Playwright已成功导入则返回 ``True``，否则返回 ``False``。
    """
    return _get_playwright() is not None


async def export_pdf(
    report: "PentestReport",
    output_path: str,
    template_engine: "TemplateEngine",
    template_name: str = "default",
) -> str:
    """将渗透测试报告导出为PDF文件。

    工作流程：
        1. 检查Playwright可用性，不可用时返回 ``output_path`` 并记录警告。
        2. 调用 ``html_exporter.export_html`` 生成临时HTML文件。
        3. 使用Playwright启动Chromium，打开临时HTML并导出PDF（A4格式）。
        4. 清理临时HTML文件，返回PDF路径。

    参数:
        report: 渗透测试报告对象，提供to_dict()序列化方法。
        output_path: 输出PDF文件路径。
        template_engine: 模板引擎实例，供HTML导出复用。
        template_name: 模板名称前缀，默认 ``default``。

    返回:
        生成的PDF文件路径；若失败则返回空字符串。
    """
    if not _ensure_playwright():
        logger.warning("Playwright未安装，无法导出PDF。请执行: pip install playwright && playwright install")
        return output_path

    tmp_path = ""
    try:
        from . import html_exporter

        tmp_path = html_exporter.export_html(
            report, output_path + ".tmp.html", template_engine, template_name
        )

        pw = _get_playwright()
        async with pw() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(f"file://{Path(tmp_path).resolve()}")
            await page.pdf(
                path=output_path,
                format="A4",
                print_background=True,
                margin={"top": "1cm", "bottom": "1cm", "left": "1cm", "right": "1cm"},
            )
            await browser.close()

        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

        return output_path
    except Exception as exc:
        logger.error("PDF导出失败: %s", exc)
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return ""
