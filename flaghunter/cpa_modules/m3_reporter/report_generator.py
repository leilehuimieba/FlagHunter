"""
report_generator.py — FlagHunter M3 Reporter 报告生成核心模块

提供 ReportGenerator 类，负责：
- 组装渗透测试报告数据（PentestReport）
- 增量添加发现（Finding）、攻击路径（AttackPath）、命令输出等
- 渲染模板并导出多种格式（HTML / Markdown / PDF）
- 自动生成执行摘要与风险统计

Python: 3.10+
文件操作: pathlib
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

# ---------------------------------------------------------------------------
# 从 report_models.py 导入数据模型
# ---------------------------------------------------------------------------
from .report_models import (
    PentestReport,
    ReportMeta,
    RiskSummary,
    Finding,
    AttackStep,
    AttackPath,
    Severity,
)

# ---------------------------------------------------------------------------
# 从 template_engine.py 导入模板引擎
# ---------------------------------------------------------------------------
from .template_engine import TemplateEngine

# ---------------------------------------------------------------------------
# 从各 exporter 导入导出函数
# ---------------------------------------------------------------------------
from .html_exporter import export_html
from .markdown_exporter import export_markdown
from .pdf_exporter import export_pdf


# ---------------------------------------------------------------------------
# Severity → CVSS 默认分值映射（小写键）
# ---------------------------------------------------------------------------
_SEVERITY_TO_CVSS: Dict[str, float] = {
    "critical": 9.5,
    "high": 8.0,
    "medium": 5.5,
    "low": 2.5,
    "info": 0.0,
}

# Severity 字符串 → Severity 枚举成员映射（小写键 → 大写成员名）
_SEVERITY_MAP: Dict[str, Severity] = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "low": Severity.LOW,
    "info": Severity.INFO,
}


class ReportGenerator:
    """报告生成器 — 组装报告数据、渲染模板、导出多种格式。

    典型使用流程::

        engine = TemplateEngine(templates_dir="./templates")
        gen = ReportGenerator(template_engine=engine, output_dir="./reports")

        report = gen.create_report(meta=ReportMeta(title="XX渗透测试报告"))
        gen.add_finding(title="SQL注入", severity="high", description="...", target="192.168.1.1")
        gen.finalize_report()
        gen.export_all()
    """

    def __init__(self, template_engine: TemplateEngine, output_dir: str = "./reports") -> None:
        """初始化报告生成器。

        :param template_engine: 模板引擎实例，负责渲染模板。
        :param output_dir: 报告输出目录，默认当前目录下的 ``reports`` 文件夹。
        """
        self._engine: TemplateEngine = template_engine
        self._output_dir: Path = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._current_report: Optional[PentestReport] = None

    # ========================================================================
    # 报告生命周期
    # ========================================================================

    def create_report(self, meta: ReportMeta) -> PentestReport:
        """创建新的渗透测试报告。

        使用传入的 ``meta`` 初始化报告元数据，同时创建一个空的
        ``RiskSummary``（所有 severity 计数为 0），并将
        ``generated_at`` 设为当前时间。

        :param meta: 报告元数据（标题、客户、作者、日期范围等）。
        :returns: 新创建的 ``PentestReport`` 实例，同时被设为当前编辑报告。
        """
        report = PentestReport(
            meta=meta,
            executive_summary="",
            risk_summary=RiskSummary(),
            findings=[],
            attack_paths=[],
            technical_appendix=[],
            generated_at=datetime.now(),
        )
        self._current_report = report
        return report

    def get_current_report(self) -> Optional[PentestReport]:
        """获取当前正在编辑的报告。

        :returns: 当前 ``PentestReport`` 实例，若尚未创建则返回 ``None``。
        """
        return self._current_report

    def finalize_report(self) -> PentestReport:
        """完成报告的最终化处理。

        依次执行以下操作：

        1. 自动生成执行摘要（基于统计信息）。
        2. 更新风险摘要统计（重新统计各 severity 数量）。
        3. 将 ``generated_at`` 设为当前时间。

        :returns: 已完成(finalized)的 ``PentestReport`` 实例。
        :raises RuntimeError: 当前没有正在编辑的报告。
        """
        if self._current_report is None:
            raise RuntimeError("没有正在编辑的报告，请先调用 create_report()")

        self._current_report.executive_summary = self._generate_executive_summary(self._current_report)
        self._update_risk_summary(self._current_report)
        self._current_report.generated_at = datetime.now()
        return self._current_report

    # ========================================================================
    # 增量更新
    # ========================================================================

    def add_finding(
        self,
        title: str,
        severity: str,
        description: str,
        target: str,
        proof: str = "",
        steps: Optional[List[str]] = None,
        impact: str = "",
        remediation: str = "",
        cvss: Optional[float] = None,
        cwe_id: str = "",
        owasp: str = "",
    ) -> str:
        """向当前报告添加一个新的安全发现（Finding）。

        自动生成 Finding ID（格式 ``FIND-001`` 起递增）；
        若 ``cvss`` 为 ``None``，则根据 ``severity`` 自动映射默认值。

        外部参数（驼峰友好名）与内部 Finding 字段的映射关系::

            target    → affected_target
            proof     → proof_of_concept
            steps     → reproduction_steps
            owasp     → owasp_category

        :param title: 发现标题。
        :param severity: 严重级别字符串，可选 ``critical/high/medium/low/info``。
        :param description: 漏洞描述。
        :param target: 受影响目标/资产。
        :param proof: 漏洞证明（PoC / 截图说明），默认为空。
        :param steps: 复现步骤列表，默认为空列表。
        :param impact: 漏洞影响分析，默认为空。
        :param remediation: 修复建议，默认为空。
        :param cvss: CVSS 基础分值；为 ``None`` 时按 severity 自动赋值。
        :param cwe_id: CWE 编号，如 ``CWE-89``，默认为空。
        :param owasp: OWASP Top 10 分类，如 ``A03:2021``，默认为空。
        :returns: 新生成的 Finding ID。
        :raises RuntimeError: 当前没有正在编辑的报告。
        """
        if self._current_report is None:
            raise RuntimeError("没有正在编辑的报告，请先调用 create_report()")

        finding_id = self._next_finding_id()
        severity_lower = severity.lower()

        if cvss is None:
            cvss = _SEVERITY_TO_CVSS.get(severity_lower, 0.0)

        sev = _SEVERITY_MAP.get(severity_lower, Severity.INFO)

        finding = Finding(
            id=finding_id,
            title=title,
            severity=sev,
            cvss_score=cvss,
            description=description,
            affected_target=target,
            proof_of_concept=proof,
            reproduction_steps=steps or [],
            impact=impact,
            remediation=remediation,
            references=[],
            screenshots=[],
            cwe_id=cwe_id,
            owasp_category=owasp,
        )
        self._current_report.add_finding(finding)
        return finding_id

    def add_screenshot_to_finding(self, finding_id: str, screenshot_path: str) -> None:
        """为指定发现追加截图路径。

        :param finding_id: 目标 Finding 的 ID（如 ``FIND-001``）。
        :param screenshot_path: 截图文件的本地路径。
        :raises RuntimeError: 当前没有正在编辑的报告。
        :raises KeyError: 找不到对应 ID 的 Finding。
        """
        if self._current_report is None:
            raise RuntimeError("没有正在编辑的报告，请先调用 create_report()")

        for finding in self._current_report.findings:
            if finding.id == finding_id:
                finding.screenshots.append(Path(screenshot_path).as_posix())
                return
        raise KeyError(f"未找到 Finding ID: {finding_id}")

    def add_command_output(self, command: str, output: str, target: str = "") -> None:
        """添加命令执行记录到技术附录。

        记录内容以字典形式存储，包含命令、输出（截断至 2000 字符）、
        目标主机和时间戳。

        :param command: 执行的命令。
        :param output: 命令输出内容。
        :param target: 目标主机/资产，默认为空。
        :raises RuntimeError: 当前没有正在编辑的报告。
        """
        if self._current_report is None:
            raise RuntimeError("没有正在编辑的报告，请先调用 create_report()")

        record: Dict[str, Any] = {
            "command": command,
            "output": output[:2000],
            "target": target,
            "timestamp": datetime.now().isoformat(),
        }
        self._current_report.technical_appendix.append(record)

    def add_attack_path(
        self,
        name: str,
        steps: List[AttackStep],
        description: str = "",
        start_point: str = "",
        end_point: str = "",
    ) -> None:
        """创建攻击路径并添加到当前报告。

        :param name: 攻击路径名称（如 ``横向移动：DMZ → 内网``）。
        :param steps: 攻击步骤列表，每个元素为 ``AttackStep`` 实例。
        :param description: 路径描述，默认为空。
        :param start_point: 攻击入口描述，默认为空。
        :param end_point: 攻击终点/达成目标描述，默认为空。
        :raises RuntimeError: 当前没有正在编辑的报告。
        """
        if self._current_report is None:
            raise RuntimeError("没有正在编辑的报告，请先调用 create_report()")

        attack_path = AttackPath(
            name=name,
            steps=steps,
            description=description,
            start_point=start_point,
            end_point=end_point,
        )
        self._current_report.attack_paths.append(attack_path)

    # ========================================================================
    # 导出
    # ========================================================================

    def export_html(self, report: Optional[PentestReport] = None, template: str = "default") -> str:
        """将报告导出为 HTML 格式。

        :param report: 要导出的报告；为 ``None`` 时使用当前正在编辑的报告。
        :param template: 使用的模板名称，默认为 ``"default"``。
        :returns: 生成的 HTML 文件绝对路径。
        :raises RuntimeError: 当前没有可导出的报告。
        """
        report = report or self._current_report
        if report is None:
            raise RuntimeError("没有可导出的报告")
        output_path = self._output_dir / f"{report.report_id}_{template}.html"
        export_html(report, output_path, self._engine, template)
        return str(output_path.resolve())

    def export_markdown(self, report: Optional[PentestReport] = None, template: str = "default") -> str:
        """将报告导出为 Markdown 格式。

        :param report: 要导出的报告；为 ``None`` 时使用当前正在编辑的报告。
        :param template: 使用的模板名称，默认为 ``"default"``。
        :returns: 生成的 Markdown 文件绝对路径。
        :raises RuntimeError: 当前没有可导出的报告。
        """
        report = report or self._current_report
        if report is None:
            raise RuntimeError("没有可导出的报告")
        output_path = self._output_dir / f"{report.report_id}_{template}.md"
        export_markdown(report, output_path, self._engine, template)
        return str(output_path.resolve())

    def export_pdf(self, report: Optional[PentestReport] = None, template: str = "default") -> str:
        """将报告导出为 PDF 格式。

        :param report: 要导出的报告；为 ``None`` 时使用当前正在编辑的报告。
        :param template: 使用的模板名称，默认为 ``"default"``。
        :returns: 生成的 PDF 文件绝对路径。
        :raises RuntimeError: 当前没有可导出的报告。
        """
        report = report or self._current_report
        if report is None:
            raise RuntimeError("没有可导出的报告")
        output_path = self._output_dir / f"{report.report_id}_{template}.pdf"
        export_pdf(report, output_path, self._engine, template)
        return str(output_path.resolve())

    def export_all(self, report: Optional[PentestReport] = None, template: str = "default") -> Dict[str, str]:
        """同时导出 HTML、Markdown、PDF 三种格式。

        :param report: 要导出的报告；为 ``None`` 时使用当前正在编辑的报告。
        :param template: 使用的模板名称，默认为 ``"default"``。
        :returns: 包含三种格式文件路径的字典，键为 ``"html" / "md" / "pdf"``。
        """
        return {
            "html": self.export_html(report, template),
            "md": self.export_markdown(report, template),
            "pdf": self.export_pdf(report, template),
        }

    def auto_save(self, report: Optional[PentestReport] = None) -> str:
        """自动保存报告到 ``auto_save`` 子目录。

        文件名格式为 ``report_{timestamp}.html``，通过 ``export_html`` 实现。

        :param report: 要保存的报告；为 ``None`` 时使用当前正在编辑的报告。
        :returns: 保存的 HTML 文件绝对路径。
        """
        report = report or self._current_report
        if report is None:
            raise RuntimeError("没有可保存的报告")

        auto_save_dir = self._output_dir / "auto_save"
        auto_save_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = auto_save_dir / f"report_{timestamp}.html"
        export_html(report, output_path, self._engine, "default")
        return str(output_path.resolve())

    # ========================================================================
    # 辅助 / 内部方法
    # ========================================================================

    def _generate_executive_summary(self, report: PentestReport) -> str:
        """基于统计数据自动生成执行摘要（executive summary）。

        汇总发现总数、各级别严重数量，并列出关键发现标题。

        :param report: 已完成数据收集的 ``PentestReport`` 实例。
        :returns: 生成的中文执行摘要文本。
        """
        rs = report.risk_summary
        total = rs.total_findings
        critical = rs.critical
        high = rs.high
        medium = rs.medium
        low = rs.low

        # 提取关键发现（CRITICAL + HIGH 级别）
        key_findings: List[str] = [
            f.title for f in report.findings
            if f.severity in (Severity.CRITICAL, Severity.HIGH)
        ][:5]  # 最多取前 5 个

        key_text = "、".join(key_findings) if key_findings else "未发现高危及以上级别问题"

        summary = (
            f"本次渗透测试共发现 {total} 个安全问题，其中 {critical} 个严重、{high} 个高危、"
            f"{medium} 个中危、{low} 个低危。主要风险包括 {key_text}。"
            f"建议优先修复高危漏洞，降低攻击面，并建立持续的安全检测机制。"
        )
        return summary

    def _update_risk_summary(self, report: PentestReport) -> None:
        """遍历报告中的所有发现，重新统计各 severity 数量并更新 risk_summary。

        :param report: 需要更新统计的 ``PentestReport`` 实例。
        """
        counts: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}

        for finding in report.findings:
            sev_name = finding.severity.name.lower()
            if sev_name in counts:
                counts[sev_name] += 1

        report.risk_summary = RiskSummary(
            critical=counts["critical"],
            high=counts["high"],
            medium=counts["medium"],
            low=counts["low"],
            info=counts["info"],
        )

    def _next_finding_id(self) -> str:
        """生成下一个 Finding ID，格式为 ``FIND-NNN``（从 001 递增）。

        :returns: 如 ``FIND-003`` 的字符串 ID。
        :raises RuntimeError: 当前没有正在编辑的报告。
        """
        if self._current_report is None:
            raise RuntimeError("没有正在编辑的报告，请先调用 create_report()")
        next_num = len(self._current_report.findings) + 1
        return f"FIND-{next_num:03d}"
