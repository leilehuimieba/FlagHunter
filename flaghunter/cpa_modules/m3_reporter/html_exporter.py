"""HTML报告导出器模块。

提供将渗透测试报告导出为独立HTML文件的功能，
所有CSS样式内联以确保HTML文件独立可查看。
"""

from datetime import datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .report_models import PentestReport
    from .template_engine import TemplateEngine

logger = logging.getLogger(__name__)


def export_html(
    report: "PentestReport",
    output_path: str,
    template_engine: "TemplateEngine",
    template_name: str = "default",
) -> str:
    """将渗透测试报告导出为HTML文件。

    参数:
        report: 渗透测试报告对象，提供to_dict()序列化方法。
        output_path: 输出文件路径；若以 ``/`` 结尾则视为目录，
                     自动生成 ``report_{timestamp}.html`` 文件名。
        template_engine: 模板引擎实例，负责渲染HTML模板。
        template_name: 模板名称前缀，默认 ``default``，实际调用时会拼接 ``.html``。

    返回:
        最终生成的HTML文件的绝对路径字符串。
    """
    data = report.to_dict()
    data["css"] = _get_default_css()

    rendered = template_engine.render(template_name + ".html", data)
    rendered = _inject_attack_path_mermaid(rendered)

    out = Path(output_path)
    if str(output_path).endswith("/") or out.is_dir():
        out = out / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

    _ensure_dir(out)
    out.write_text(rendered, encoding="utf-8")
    return str(out.resolve())


def _inject_attack_path_mermaid(rendered_html: str) -> str:
    """Inject a Mermaid attack-path graph block before </body> when notes allow it."""
    try:
        from flaghunter.knowledge.graph import ShadowGraph
        from flaghunter.tools.notes import get_all_notes_sync

        notes = get_all_notes_sync()
        if not notes:
            return rendered_html

        graph = ShadowGraph()
        graph.update_from_notes(notes)

        if graph.graph.number_of_nodes() == 0:
            return rendered_html

        mermaid_code = graph.to_mermaid()
        mermaid_block = (
            '\n<section class="section" id="attack-path-mermaid">\n'
            "  <h2>Attack Path</h2>\n"
            '  <div class="mermaid">\n'
            f"{mermaid_code}\n"
            "  </div>\n"
            "</section>\n"
            '<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>\n'
            "<script>mermaid.initialize({startOnLoad:true});</script>\n"
        )

        if "</body>" in rendered_html:
            return rendered_html.replace("</body>", mermaid_block + "</body>", 1)
        return rendered_html + mermaid_block
    except Exception as exc:
        logger.warning("Failed to inject Mermaid attack path into HTML report: %s", exc)
        return rendered_html


def _ensure_dir(path: Path) -> None:
    """确保输出文件所在的父目录存在，不存在则自动创建。

    参数:
        path: 目标文件路径。
    """
    path.parent.mkdir(parents=True, exist_ok=True)


def _get_default_css() -> str:
    """返回用于内联到HTML模板的默认CSS样式字符串。

    样式采用紧凑单行格式，包含全局布局、封面页、标题、表格、
    严重度徽章、卡片布局、代码块及打印友好媒体查询，
    确保生成的HTML文件独立可查看且在不同设备上表现一致。

    返回:
        紧凑格式的CSS样式字符串，约400-600字符。
    """
    return (
        "body{font-family:Arial,sans-serif;max-width:1200px;margin:0 auto;padding:20px;"
        "background:#f8f9fa;color:#333}"
        ".cover{text-align:center;padding:60px 20px;background:linear-gradient(135deg,#1a1a2e,#16213e);"
        "color:#fff;border-radius:8px}"
        "h1{font-size:2.5em;margin-bottom:10px}"
        "h2{color:#1a1a2e;border-bottom:2px solid #dee2e6;padding-bottom:10px}"
        "table{width:100%;border-collapse:collapse;margin:20px 0}"
        "th,td{padding:12px;text-align:left;border-bottom:1px solid #dee2e6}"
        "th{background:#495057;color:#fff}"
        ".severity-critical{background:#dc3545;color:#fff;padding:4px 8px;border-radius:4px}"
        ".severity-high{background:#fd7e14;color:#fff;padding:4px 8px;border-radius:4px}"
        ".severity-medium{background:#ffc107;color:#000;padding:4px 8px;border-radius:4px}"
        ".severity-low{background:#17a2b8;color:#fff;padding:4px 8px;border-radius:4px}"
        ".severity-info{background:#6c757d;color:#fff;padding:4px 8px;border-radius:4px}"
        ".finding-card{background:#fff;border-radius:8px;padding:20px;margin:15px 0;"
        "box-shadow:0 2px 4px rgba(0,0,0,0.1)}"
        "pre{background:#f8f9fa;padding:15px;border-radius:4px;overflow-x:auto;"
        "border-left:4px solid #495057}"
        "@media print{body{background:#fff}"
        ".finding-card{box-shadow:none;border:1px solid #dee2e6}}"
    )
