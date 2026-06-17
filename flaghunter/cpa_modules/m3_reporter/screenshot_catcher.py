"""
ScreenshotCatcher — 漏洞页面截图捕获器

使用 Playwright 对漏洞验证页面进行自动截图，支持整页截图、
元素级截图与批量截图。采用延迟加载模式确保 Playwright 仅在
实际需要时才被导入，降低模块启动开销。

技术约束：
    - 延迟加载 Playwright（async_playwright）
    - 所有方法均做异常安全防护
    - 中文 docstring

作者：FlagHunter M3 Reporter 模块
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Playwright 延迟加载基础设施
# ---------------------------------------------------------------------------
_PW_AVAILABLE: bool = False
_pw = None


def _get_playwright():
    """延迟加载并返回 async_playwright 入口，失败则返回 None。"""
    global _PW_AVAILABLE, _pw
    if _pw is None:
        try:
            from playwright.async_api import async_playwright

            _pw = async_playwright
            _PW_AVAILABLE = True
        except ImportError:
            _PW_AVAILABLE = False
    return _pw


def _ensure_playwright() -> bool:
    """检查 Playwright 是否可用。"""
    return _get_playwright() is not None


# ---------------------------------------------------------------------------
# ScreenshotCatcher
# ---------------------------------------------------------------------------
class ScreenshotCatcher:
    """漏洞页面截图捕获器 — 用 Playwright 对漏洞页面自动截图。

    支持以下截图模式：
    - 整页/视口截图（:meth:`capture`）
    - 元素级截图（:meth:`capture_element`）
    - 批量串行截图（:meth:`capture_multiple`）

    Args:
        output_dir: 截图文件保存目录，默认为 ``./reports/screenshots``。
    """

    def __init__(self, output_dir: str = "./reports/screenshots") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    # -- 公开 API -----------------------------------------------------------

    async def capture(
        self,
        url: str,
        finding_id: str | None = None,
        full_page: bool = False,
        wait_for: str | None = None,
    ) -> str:
        """对指定 URL 进行截图。

        流程：
        1. 检查 Playwright 可用性；
        2. 启动 headless Chromium 浏览器；
        3. 访问目标页面；
        4. 如指定 ``wait_for``，等待对应 CSS 选择器出现（超时 10 秒）；
        5. 截图并保存到 ``output_dir``；
        6. 关闭浏览器上下文并返回文件路径。

        Args:
            url: 待截图的目标地址。
            finding_id: 关联的发现项 ID，用于构造文件名。
            full_page: 是否截取整页，默认 ``False``（仅当前视口）。
            wait_for: 截图前需等待出现的 CSS 选择器，可选。

        Returns:
            截图文件的绝对路径；任何失败均返回空字符串 ``""``。
        """
        if not _ensure_playwright():
            return ""

        filepath = ""
        pw = _get_playwright()
        browser = None
        try:
            async with pw() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)

                if wait_for:
                    try:
                        await page.wait_for_selector(wait_for, timeout=10000)
                    except Exception:
                        pass  # 等待失败不影响截图

                filename = self._generate_filename(finding_id)
                filepath = str(self._output_dir / filename)
                await page.screenshot(path=filepath, full_page=full_page)
                await browser.close()
        except Exception:
            filepath = ""
        finally:
            if browser and not browser.is_connected() is False:
                try:
                    await browser.close()
                except Exception:
                    pass
        return filepath

    async def capture_element(
        self,
        url: str,
        selector: str,
        finding_id: str | None = None,
    ) -> str:
        """对页面中指定 CSS 选择器匹配的元素进行截图。

        先加载页面，再定位元素并截图；若元素不存在则退化为整页截图。

        Args:
            url: 目标页面地址。
            selector: CSS 选择器，用于定位待截图元素。
            finding_id: 关联的发现项 ID，可选。

        Returns:
            截图文件绝对路径；失败返回空字符串 ``""``。
        """
        if not _ensure_playwright():
            return ""

        filepath = ""
        pw = _get_playwright()
        browser = None
        try:
            async with pw() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)

                element = await page.query_selector(selector)
                if element:
                    filename = self._generate_filename(finding_id)
                    filepath = str(self._output_dir / filename)
                    await element.screenshot(path=filepath)
                else:
                    # 元素未找到，退化为整页截图
                    filename = self._generate_filename(finding_id)
                    filepath = str(self._output_dir / filename)
                    await page.screenshot(path=filepath, full_page=False)
                await browser.close()
        except Exception:
            filepath = ""
        finally:
            if browser and not browser.is_connected() is False:
                try:
                    await browser.close()
                except Exception:
                    pass
        return filepath

    async def capture_multiple(
        self,
        urls: List[str],
        finding_id: str | None = None,
    ) -> List[str]:
        """批量串行截图。

        为避免浏览器实例资源竞争，采用串行方式依次截图。

        Args:
            urls: 待截图 URL 列表。
            finding_id: 关联的发现项 ID，用于文件名前缀。

        Returns:
            成功截图的文件路径列表，失败的条目已被过滤。
        """
        results: List[str] = []
        for idx, url in enumerate(urls):
            # 为每个 URL 生成独立 finding_id 以避免文件名冲突
            fid = f"{finding_id}_{idx}" if finding_id else None
            path = await self.capture(url, finding_id=fid)
            if path:
                results.append(path)
        return results

    # -- 内部工具 -----------------------------------------------------------

    def _generate_filename(self, finding_id: str | None = None) -> str:
        """生成截图文件名。

        格式：
        - 提供 ``finding_id`` → ``{finding_id}_{YYYYMMDD_HHMMSS}.png``
        - 未提供 → ``screenshot_{YYYYMMDD_HHMMSS}.png``

        Args:
            finding_id: 关联发现项 ID，可选。

        Returns:
            构造好的 PNG 文件名。
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if finding_id:
            return f"{finding_id}_{timestamp}.png"
        return f"screenshot_{timestamp}.png"
