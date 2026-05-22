"""Markdown报告导出器模块。

提供将渗透测试报告导出为Markdown文件的功能，
支持模板引擎渲染并在模板缺失时提供默认Markdown模板作为后备。
"""

from pathlib import Path
from typing import TYPE_CHECKING

import jinja2

if TYPE_CHECKING:
    from .report_models import PentestReport
    from .template_engine import TemplateEngine


def export_markdown(
    report: "PentestReport",
    output_path: str,
    template_engine: "TemplateEngine",
    template_name: str = "default",
) -> str:
    """将渗透测试报告导出为Markdown文件。

    首先尝试使用模板引擎渲染指定模板；若模板不存在（抛出
    ``jinja2.TemplateNotFound``），则回退到内置默认Markdown模板。

    参数:
        report: 渗透测试报告对象，提供to_dict()序列化方法。
        output_path: 输出文件路径；若以 ``/`` 结尾则视为目录，
                     自动生成 ``report_{timestamp}.md`` 文件名。
        template_engine: 模板引擎实例，负责渲染Markdown模板。
        template_name: 模板名称前缀，默认 ``default``，实际调用时会拼接 ``.md``。

    返回:
        最终生成的Markdown文件的绝对路径字符串。
    """
    data = report.to_dict()

    try:
        rendered = template_engine.render(template_name + ".md", data)
    except jinja2.TemplateNotFound:
        template_str = _get_default_md_template()
        env = jinja2.Environment()
        env.filters["format_datetime"] = lambda v: str(v)
        template = env.from_string(template_str)
        rendered = template.render(**data)

    out = Path(output_path)
    if str(output_path).endswith("/") or Path(output_path).is_dir():
        from datetime import datetime
        out = out / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out.write_text(rendered, encoding="utf-8")
    return str(out.resolve())


def _get_default_md_template() -> str:
    """返回默认的Markdown Jinja2模板字符串。

    模板包含报告元信息、执行摘要、测试范围、风险摘要表格、
    详细发现列表、攻击路径、技术附录及合规声明等完整结构，
    可在外部模板缺失时作为后备方案使用。

    返回:
        完整的Markdown格式Jinja2模板字符串。
    """
    return (
        "# {{ meta.title }}\n\n"
        "> **版本**: {{ meta.version }} | **作者**: {{ meta.author }} "
        "| **日期**: {{ meta.start_date|format_datetime }} ~ {{ meta.end_date|format_datetime }}\n\n"
        "> **分类**: {{ meta.classification }} | **公司**: {{ meta.company_name }}\n\n"
        "---\n\n"
        "## 执行摘要\n\n{{ executive_summary }}\n\n"
        "## 测试范围\n\n"
        "- **目标范围**: {{ meta.scope }}\n"
        "- **测试方法**: {{ meta.methodology }}\n"
        "- **测试周期**: {{ meta.start_date|format_datetime }} 至 {{ meta.end_date|format_datetime }}\n\n"
        "## 风险摘要\n\n"
        "| 严重度 | 数量 |\n|--------|------|\n"
        "| \U0001f534 严重 | {{ risk_summary.critical }} |\n"
        "| \U0001f7e0 高危 | {{ risk_summary.high }} |\n"
        "| \U0001f7e1 中危 | {{ risk_summary.medium }} |\n"
        "| \U0001f535 低危 | {{ risk_summary.low }} |\n"
        "| \U000026aa 信息 | {{ risk_summary.info }} |\n"
        "| **总计** | **{{ risk_summary.total_findings }}** |\n\n"
        "**风险评分**: {{ \"%.1f\"|format(risk_summary.risk_score) }}/10\n\n"
        "## 详细发现\n\n"
        "{% for finding in findings %}"
        "### {{ finding.severity.label }} {{ finding.id }}: {{ finding.title }}\n\n"
        "- **CVSS评分**: {{ finding.cvss_score }}\n"
        "- **目标**: {{ finding.affected_target }}\n"
        "- **CWE**: {{ finding.cwe_id or \"N/A\" }}\n\n"
        "**描述**:\n{{ finding.description }}\n\n"
        "**影响**:\n{{ finding.impact }}\n\n"
        "**修复建议**:\n{{ finding.remediation }}\n\n"
        "{% endfor %}"
        "{% if attack_paths %}"
        "## 攻击路径\n\n"
        "{% for path in attack_paths %}"
        "### {{ path.name }}\n{{ path.to_mermaid }}\n\n"
        "{% endfor %}"
        "{% endif %}"
        "{% if technical_appendix %}"
        "## 技术附录\n\n"
        "{% for entry in technical_appendix %}"
        "### 命令: `{{ entry.command }}`\n\n"
        "```\n{{ entry.output[:500] }}\n```\n\n"
        "{% endfor %}"
        "{% endif %}"
        "## 合规声明\n\n{{ compliance_notes }}\n\n"
        "---\n"
        "*报告生成时间: {{ generated_at }} | 报告ID: {{ report_id }}*\n"
    )
