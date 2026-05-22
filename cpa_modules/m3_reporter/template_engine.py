"""
PentestAgent M3 Reporter — Jinja2 模板引擎

封装模板加载、渲染、缓存，并提供面向渗透测试报告的内置过滤器：
严重级别着色、时间格式化、文本截断、CVSS 徽章生成等。

用法::

    from template_engine import TemplateEngine
    from report_models import PentestReport

    engine = TemplateEngine("templates")
    report = PentestReport.create_empty()
    html = engine.render("report.html", report.to_dict())
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, Union

import jinja2

from .report_models import Severity


__all__ = ["TemplateEngine"]


# ---------------------------------------------------------------------------
# 默认 CSS 样式（供 _default_template_data 使用）
# ---------------------------------------------------------------------------

_DEFAULT_CSS = """
body {
    font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
    max-width: 960px; margin: 0 auto; padding: 2rem;
    color: #212529; line-height: 1.7;
}
h1, h2, h3 { color: #1a1a2e; border-bottom: 1px solid #dee2e6; padding-bottom: .4rem; }
.severity-critical { color: #dc3545; font-weight: bold; }
.severity-high     { color: #fd7e14; font-weight: bold; }
.severity-medium   { color: #ffc107; font-weight: bold; }
.severity-low      { color: #17a2b8; font-weight: bold; }
.severity-info     { color: #6c757d; }
table {
    border-collapse: collapse; width: 100%; margin-bottom: 1rem;
}
th, td { border: 1px solid #dee2e6; padding: .6rem .8rem; text-align: left; }
th { background: #f1f3f5; }
.cvss-badge {
    display: inline-block; padding: .25rem .6rem; border-radius: .4rem;
    color: #fff; font-size: .85rem; font-weight: 600;
}
.mermaid {
    background: #f8f9fa; padding: 1rem; border-radius: .4rem;
    font-family: monospace; white-space: pre-wrap;
}
.appendix-entry {
    border-left: 3px solid #adb5bd; padding-left: 1rem; margin-bottom: 1rem;
}
"""


class TemplateEngine:
    """Jinja2 模板引擎 — 管理模板加载、渲染和缓存。

    自动注册一组面向渗透测试报告的内置过滤器（严重级别着色、
    CVSS 徽章、日期格式化、文本截断），并提供默认 CSS 样式变量。

    :param template_dir: 模板文件所在目录路径
    """

    def __init__(self, template_dir: str = "templates") -> None:
        """初始化模板引擎。

        使用 :class:`jinja2.FileSystemLoader` 从 ``template_dir`` 加载模板，
        启用 ``autoescape`` 防止 XSS。

        :param template_dir: 模板根目录，默认为 ``templates``
        """
        self.template_dir: str = template_dir
        self._env: jinja2.Environment = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._setup_builtin_filters()

    # ------------------------------------------------------------------
    # 模板管理
    # ------------------------------------------------------------------

    def load_template(self, name: str) -> jinja2.Template:
        """加载模板文件。

        若 ``name`` 不含文件后缀，依次尝试 ``.html`` 和 ``.md``。

        :param name: 模板名称或相对路径
        :return: 编译后的 :class:`jinja2.Template` 对象
        :raises jinja2.TemplateNotFound: 模板不存在
        """
        if "." not in name:
            for ext in (".html", ".md"):
                try:
                    return self._env.get_template(name + ext)
                except jinja2.TemplateNotFound:
                    continue
        return self._env.get_template(name)

    def list_templates(self) -> List[str]:
        """列出所有可用的模板文件（仅限 ``.html`` 和 ``.md``）。

        :return: 模板文件路径列表
        """
        all_names = self._env.list_templates()
        return [n for n in all_names if n.endswith(".html") or n.endswith(".md")]

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------

    def render(self, template_name: str, data: dict) -> str:
        """渲染指定模板。

        :param template_name: 模板名称
        :param data: 传给模板的数据字典
        :return: 渲染后的字符串（通常为 HTML 或 Markdown）
        """
        template = self.load_template(template_name)
        merged = {**self._default_template_data(), **data}
        return template.render(**merged)

    def render_string(self, template_string: str, data: dict) -> str:
        """从字符串直接渲染（内联模板，无需文件）。

        :param template_string: Jinja2 模板源字符串
        :param data: 传给模板的数据字典
        :return: 渲染后的字符串
        """
        template = self._env.from_string(template_string)
        merged = {**self._default_template_data(), **data}
        return template.render(**merged)

    # ------------------------------------------------------------------
    # 过滤器注册
    # ------------------------------------------------------------------

    def register_filter(self, name: str, func: Callable) -> None:
        """注册自定义 Jinja2 过滤器。

        :param name: 过滤器名称（模板中使用的标识符）
        :param func: 过滤器函数
        """
        self._env.filters[name] = func

    def _setup_builtin_filters(self) -> None:
        """注册内置过滤器。

        内置过滤器清单::

            severity_color  -- Severity -> CSS 颜色
            severity_label  -- Severity -> 中文标签
            format_datetime -- 格式化 datetime 对象或 ISO 字符串
            truncate        -- 截断文本并追加 ...
            cvss_badge      -- float -> CVSS 徽章 HTML
        """
        self.register_filter("severity_color", self._filter_severity_color)
        self.register_filter("severity_label", self._filter_severity_label)
        self.register_filter("format_datetime", self._filter_format_datetime)
        self.register_filter("truncate", self._filter_truncate)
        self.register_filter("cvss_badge", self._filter_cvss_badge)

    # ------------------------------------------------------------------
    # 过滤器实现（私有静态方法）
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_severity_color(value: Union[Severity, str]) -> str:
        """将严重级别转为 CSS 颜色值。

        :param value: :class:`Severity` 枚举或字符串名称
        :return: CSS 颜色十六进制值
        """
        if isinstance(value, Severity):
            return value.color
        try:
            return Severity[value.upper()].color
        except KeyError:
            return "#6c757d"

    @staticmethod
    def _filter_severity_label(value: Union[Severity, str]) -> str:
        """将严重级别转为中文标签。

        :param value: :class:`Severity` 枚举或字符串名称
        :return: 中文标签，如 ``"严重"``
        """
        if isinstance(value, Severity):
            return value.label
        try:
            return Severity[value.upper()].label
        except KeyError:
            return value

    @staticmethod
    def _filter_format_datetime(value: Union[datetime, str], fmt: str = "%Y-%m-%d %H:%M") -> str:
        """格式化日期时间。

        :param value: datetime 对象或 ISO 格式字符串
        :param fmt: 输出格式，默认 ``%Y-%m-%d %H:%M``
        :return: 格式化后的日期字符串
        """
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return value
        if isinstance(value, datetime):
            return value.strftime(fmt)
        return str(value)

    @staticmethod
    def _filter_truncate(value: str, length: int = 80) -> str:
        """截断文本并追加省略号。

        :param value: 原始字符串
        :param length: 最大长度，默认 80
        :return: 截断后的字符串
        """
        if not isinstance(value, str):
            value = str(value)
        if len(value) <= length:
            return value
        return value[:length].rstrip() + "..."

    @staticmethod
    def _filter_cvss_badge(value: float) -> str:
        """生成 CVSS 分数徽章 HTML。

        根据分数自动选择背景色::

            9.0 - 10.0  →  #dc3545 (严重)
            7.0 - 8.9   →  #fd7e14 (高危)
            4.0 - 6.9   →  #ffc107 (中危)
            0.1 - 3.9   →  #17a2b8 (低危)
            0.0         →  #6c757d (信息)

        :param value: CVSS 基础分数 (0.0 ~ 10.0)
        :return: ``<span class=\"cvss-badge\" style=\"background:...\">分数</span>``
        """
        try:
            score = float(value)
        except (TypeError, ValueError):
            score = 0.0
        color = Severity.from_cvss(score).color
        return (
            f'<span class="cvss-badge" style="background:{color}">'
            f'{score:.1f}</span>'
        )

    # ------------------------------------------------------------------
    # 默认模板变量
    # ------------------------------------------------------------------

    def _default_template_data(self) -> dict:
        """返回默认的模板全局变量。

        当前包含::

            css          -- 内联 CSS 样式字符串
            severity_map -- 严重级别名称到完整信息的映射

        :return: 默认变量字典
        """
        return {
            "css": _DEFAULT_CSS,
            "severity_map": {
                "CRITICAL": Severity.CRITICAL.to_dict(),
                "HIGH":     Severity.HIGH.to_dict(),
                "MEDIUM":   Severity.MEDIUM.to_dict(),
                "LOW":      Severity.LOW.to_dict(),
                "INFO":     Severity.INFO.to_dict(),
            },
        }
