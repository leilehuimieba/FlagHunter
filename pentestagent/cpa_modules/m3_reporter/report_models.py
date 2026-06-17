"""
PentestAgent M3 Reporter — 报告数据模型

定义渗透测试报告所需的核心数据结构，包括漏洞发现、攻击路径、
报告元数据、风险摘要和主报告类。

用法::

    from report_models import PentestReport, Finding, Severity, ReportMeta
    report = PentestReport.create_empty()
    finding = Finding(
        id="FIND-001",
        title="SQL注入",
        severity=Severity.CRITICAL,
        cvss_score=9.8,
        description="...",
        affected_target="192.168.1.1",
        proof_of_concept="...",
        reproduction_steps=["步骤1", "步骤2"],
        impact="数据泄露",
        remediation="参数化查询"
    )
    report.add_finding(finding)
    data = report.to_dict()  # 传递给 TemplateEngine 渲染
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List


__all__ = [
    "Severity",
    "Finding",
    "AttackStep",
    "AttackPath",
    "ReportMeta",
    "RiskSummary",
    "PentestReport",
]


# ---------------------------------------------------------------------------
# Severity 元数据映射 — 模块级别避免 str/Enum 继承冲突
# ---------------------------------------------------------------------------

# (label, score_min, score_max, color)
_SEVERITY_META: Dict[str, tuple] = {
    "CRITICAL": ("严重", 9.0, 10.0, "#dc3545"),
    "HIGH":     ("高危", 7.0, 8.9, "#fd7e14"),
    "MEDIUM":   ("中危", 4.0, 6.9, "#ffc107"),
    "LOW":      ("低危", 0.1, 3.9, "#17a2b8"),
    "INFO":     ("信息", 0.0, 0.0, "#6c757d"),
}


class Severity(str, Enum):
    """漏洞严重级别枚举，映射到 CVSS 分数区间和展示颜色。

    成员::
        CRITICAL -- 严重 (9.0 ~ 10.0)
        HIGH     -- 高危 (7.0 ~ 8.9)
        MEDIUM   -- 中危 (4.0 ~ 6.9)
        LOW      -- 低危 (0.1 ~ 3.9)
        INFO     -- 信息 (0.0)

    示例::
        >>> Severity.from_cvss(9.5)
        <Severity.CRITICAL: 'CRITICAL'>
        >>> Severity.HIGH.color
        '#fd7e14'
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

    # --- 动态属性 ---

    @property
    def label(self) -> str:
        """中文标签，如"严重"、"高危"等。"""
        return _SEVERITY_META[self.value][0]

    @property
    def score_min(self) -> float:
        """CVSS 分数下限（含）。"""
        return _SEVERITY_META[self.value][1]

    @property
    def score_max(self) -> float:
        """CVSS 分数上限（含）。"""
        return _SEVERITY_META[self.value][2]

    @property
    def color(self) -> str:
        """展示用的 CSS 颜色值。"""
        return _SEVERITY_META[self.value][3]

    # --- 类方法 ---

    @classmethod
    def from_cvss(cls, score: float) -> "Severity":
        """根据 CVSS 分数返回对应的严重级别。

        :param score: CVSS 基础分数（0.0 ~ 10.0）
        :return: 匹配的 :class:`Severity` 成员
        :raises ValueError: 分数超出合法范围
        """
        if not 0.0 <= score <= 10.0:
            raise ValueError(f"CVSS 分数必须在 0.0 ~ 10.0 之间，收到 {score}")
        for member in cls:
            if member.score_min <= score <= member.score_max:
                return member
        return cls.INFO

    def to_dict(self) -> dict:
        """将严重级别序列化为字典，包含标签、颜色、分数区间。"""
        return {
            "name": self.value,
            "label": self.label,
            "color": self.color,
            "score_min": self.score_min,
            "score_max": self.score_max,
        }


# ---------------------------------------------------------------------------
# 2. Finding
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """单个漏洞发现，描述渗透测试过程中识别到的安全缺陷。

    :ivar id: 唯一标识，如 ``FIND-001``
    :ivar title: 漏洞标题，简要说明问题
    :ivar severity: 严重级别
    :ivar cvss_score: CVSS 基础分数
    :ivar description: 详细描述
    :ivar affected_target: 受影响目标（IP / URL / 主机名）
    :ivar proof_of_concept: 漏洞验证代码或关键请求/响应
    :ivar reproduction_steps: 复现步骤列表
    :ivar impact: 影响说明
    :ivar remediation: 修复建议
    :ivar references: 参考链接列表
    :ivar screenshots: 截图路径列表
    :ivar discovered_at: 发现时间
    :ivar verified: 是否已人工验证
    :ivar cwe_id: CWE 编号，如 ``CWE-89``
    :ivar owasp_category: OWASP 分类，如 ``A03:2021-Injection``
    """

    id: str
    title: str
    severity: Severity
    cvss_score: float
    description: str
    affected_target: str
    proof_of_concept: str
    reproduction_steps: List[str]
    impact: str
    remediation: str
    references: List[str] = field(default_factory=list)
    screenshots: List[str] = field(default_factory=list)
    discovered_at: datetime = field(default_factory=datetime.now)
    verified: bool = False
    cwe_id: str = ""
    owasp_category: str = ""

    def to_dict(self) -> dict:
        """将发现项序列化为字典，severity 转为完整字典。"""
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity.to_dict(),
            "cvss_score": self.cvss_score,
            "description": self.description,
            "affected_target": self.affected_target,
            "proof_of_concept": self.proof_of_concept,
            "reproduction_steps": self.reproduction_steps,
            "impact": self.impact,
            "remediation": self.remediation,
            "references": self.references,
            "screenshots": self.screenshots,
            "discovered_at": self.discovered_at.isoformat(),
            "verified": self.verified,
            "cwe_id": self.cwe_id,
            "owasp_category": self.owasp_category,
        }

    def summary(self) -> str:
        """返回单行摘要，格式::

            [严重] SQL注入 - 目标: 192.168.1.1
        """
        return f"[{self.severity.label}] {self.title} - 目标: {self.affected_target}"


# ---------------------------------------------------------------------------
# 3. AttackStep
# ---------------------------------------------------------------------------

@dataclass
class AttackStep:
    """攻击路径中的单步操作，记录一次具体攻击行为。

    :ivar order: 步骤序号（从 1 开始）
    :ivar description: 步骤描述
    :ivar tool_used: 使用的工具名称
    :ivar target: 目标主机/端口/URL
    :ivar result: 执行结果描述
    :ivar screenshot: 截图路径（可选）
    :ivar duration_ms: 耗时（毫秒）
    """

    order: int
    description: str
    tool_used: str
    target: str
    result: str
    screenshot: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict:
        """将攻击步骤序列化为字典。"""
        return {
            "order": self.order,
            "description": self.description,
            "tool_used": self.tool_used,
            "target": self.target,
            "result": self.result,
            "screenshot": self.screenshot,
            "duration_ms": self.duration_ms,
        }


# ---------------------------------------------------------------------------
# 4. AttackPath
# ---------------------------------------------------------------------------

@dataclass
class AttackPath:
    """完整攻击路径，描述从入口到最终目标的攻击链条。

    :ivar name: 路径名称
    :ivar description: 路径概述
    :ivar steps: 攻击步骤列表
    :ivar start_point: 攻击入口描述
    :ivar end_point: 攻击终点/达成目标描述
    :ivar total_duration_ms: 总耗时（毫秒）
    """

    name: str
    description: str
    steps: List[AttackStep]
    start_point: str
    end_point: str
    total_duration_ms: int = 0

    def to_mermaid(self) -> str:
        """生成 Mermaid 流程图语法字符串。

        示例输出::

            graph LR
                A[入口: 互联网] -->|nmap扫描| B[发现开放端口]
                B -->|SQLMap| C[获取数据库访问]
                C -->|提权| D[获得root shell]
        """
        lines = ["graph LR"]
        labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        n = len(self.steps)
        if n == 0:
            return lines[0]

        # 起点节点
        lines.append(f"    A[{self.start_point}]")

        for i, step in enumerate(self.steps):
            src = labels[i]
            dst = labels[i + 1] if i + 1 < len(labels) else labels[-1]
            if i < n - 1:
                dst_label = f"[{self.steps[i + 1].description}]"
            else:
                dst_label = f"[{self.end_point}]"
            edge_label = step.tool_used if step.tool_used else step.description
            lines.append(f"    {src} -->|{edge_label}| {dst}{dst_label}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """将攻击路径序列化为字典，包含 Mermaid 语法。"""
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "start_point": self.start_point,
            "end_point": self.end_point,
            "total_duration_ms": self.total_duration_ms,
            "mermaid": self.to_mermaid(),
        }


# ---------------------------------------------------------------------------
# 5. ReportMeta
# ---------------------------------------------------------------------------

_DEFAULT_DISCLAIMER = (
    "本报告仅供授权方内部使用。未经 PentestAgent 及授权方书面同意，"
    "任何第三方不得复制、传播或以任何形式使用本报告的全部或部分内容。"
)


@dataclass
class ReportMeta:
    """报告元数据，包含标题、作者、时间范围、范围声明等。

    :ivar title: 报告标题
    :ivar subtitle: 副标题（可选）
    :ivar version: 报告版本号，默认 ``1.0``
    :ivar author: 报告作者
    :ivar company_name: 客户/公司名称（可选）
    :ivar company_logo: 公司 Logo 路径（可选）
    :ivar start_date: 测试开始时间
    :ivar end_date: 测试结束时间
    :ivar scope: 测试范围描述
    :ivar methodology: 测试方法论，默认 ``OWASP Testing Guide v4``
    :ivar classification: 报告密级，默认 ``机密``
    :ivar disclaimer: 免责声明
    """

    title: str
    subtitle: str = ""
    version: str = "1.0"
    author: str = ""
    company_name: str = ""
    company_logo: str = ""
    start_date: datetime = field(default_factory=datetime.now)
    end_date: datetime = field(default_factory=datetime.now)
    scope: str = ""
    methodology: str = "OWASP Testing Guide v4"
    classification: str = "机密"
    disclaimer: str = _DEFAULT_DISCLAIMER

    def to_dict(self) -> dict:
        """将元数据序列化为字典。"""
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "version": self.version,
            "author": self.author,
            "company_name": self.company_name,
            "company_logo": self.company_logo,
            "start_date": self.start_date.isoformat() if hasattr(self.start_date, 'isoformat') else str(self.start_date),
            "end_date": self.end_date.isoformat() if hasattr(self.end_date, 'isoformat') else str(self.end_date),
            "scope": self.scope,
            "methodology": self.methodology,
            "classification": self.classification,
            "disclaimer": self.disclaimer,
        }


# ---------------------------------------------------------------------------
# 6. RiskSummary
# ---------------------------------------------------------------------------

@dataclass
class RiskSummary:
    """风险摘要，统计各级别漏洞数量并计算加权风险分。

    :ivar critical: 严重级别漏洞数量
    :ivar high: 高危漏洞数量
    :ivar medium: 中危漏洞数量
    :ivar low: 低危漏洞数量
    :ivar info: 信息级别漏洞数量
    """

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0

    @property
    def total_findings(self) -> int:
        """漏洞总数。"""
        return self.critical + self.high + self.medium + self.low + self.info

    @property
    def risk_score(self) -> float:
        """加权风险平均分。

        权重::
            严重=10, 高危=8, 中危=5, 低危=2, 信息=0

        若总数为 0，返回 0.0。
        """
        total = self.total_findings
        if total == 0:
            return 0.0
        weighted = (
            self.critical * 10
            + self.high * 8
            + self.medium * 5
            + self.low * 2
            + self.info * 0
        )
        return round(weighted / total, 2)

    def get_chart_data(self) -> dict:
        """返回图表所需数据，包含标签、数值和颜色数组。

        返回结构::

            {
                "labels": ["严重", "高危", "中危", "低危", "信息"],
                "values": [1, 2, 3, 4, 5],
                "colors": ["#dc3545", "#fd7e14", "#ffc107", "#17a2b8", "#6c757d"]
            }
        """
        return {
            "labels": ["严重", "高危", "中危", "低危", "信息"],
            "values": [self.critical, self.high, self.medium, self.low, self.info],
            "colors": ["#dc3545", "#fd7e14", "#ffc107", "#17a2b8", "#6c757d"],
        }

    def to_dict(self) -> dict:
        """将风险摘要序列化为字典，包含计算属性。"""
        return {
            "critical": self.critical,
            "high": self.high,
            "medium": self.medium,
            "low": self.low,
            "info": self.info,
            "total_findings": self.total_findings,
            "risk_score": self.risk_score,
            "chart_data": self.get_chart_data(),
        }


# ---------------------------------------------------------------------------
# 7. PentestReport（核心）
# ---------------------------------------------------------------------------

@dataclass
class PentestReport:
    """渗透测试报告核心类，聚合所有报告数据。

    这是 M3 Reporter 模块的**核心契约**：通过 :meth:`to_dict` 将完整报告
    序列化为字典，供 :class:`TemplateEngine` 渲染为 HTML/Markdown。

    :ivar meta: 报告元数据
    :ivar executive_summary: 执行摘要
    :ivar risk_summary: 风险摘要（自动维护）
    :ivar findings: 漏洞发现列表
    :ivar attack_paths: 攻击路径列表
    :ivar technical_appendix: 技术附录条目列表
    :ivar compliance_notes: 合规说明
    :ivar generated_at: 报告生成时间
    :ivar report_id: 报告唯一标识
    """

    meta: ReportMeta
    executive_summary: str = ""
    risk_summary: RiskSummary = field(default_factory=RiskSummary)
    findings: List[Finding] = field(default_factory=list)
    attack_paths: List[AttackPath] = field(default_factory=list)
    technical_appendix: List[dict] = field(default_factory=list)
    compliance_notes: str = ""
    generated_at: datetime = field(default_factory=datetime.now)
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # --- 核心契约方法 ---

    def to_dict(self) -> dict:
        """将整个报告序列化为字典 — M3 模块的核心契约。

        返回结构::

            {
                "meta": { ... },
                "executive_summary": "...",
                "risk_summary": { ... },
                "findings": [ ... ],
                "attack_paths": [ ... ],
                "technical_appendix": [ ... ],
                "compliance_notes": "...",
                "generated_at": "2024-01-01T12:00:00",
                "report_id": "uuid-string",
                "css": ""   # 由 html_exporter 填充
            }

        :return: 完整的报告数据字典
        """
        return {
            "meta": self.meta.to_dict(),
            "executive_summary": self.executive_summary,
            "risk_summary": self.risk_summary.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "attack_paths": [p.to_dict() for p in self.attack_paths],
            "technical_appendix": self.technical_appendix,
            "compliance_notes": self.compliance_notes,
            "generated_at": self.generated_at.isoformat(),
            "report_id": self.report_id,
            "css": "",
        }

    # --- 数据操作方法 ---

    def add_finding(self, finding: Finding) -> str:
        """追加一个漏洞发现，并自动更新风险摘要计数。

        :param finding: 要添加的发现项
        :return: 该发现项的 id
        """
        self.findings.append(finding)
        sev = finding.severity
        if sev == Severity.CRITICAL:
            self.risk_summary.critical += 1
        elif sev == Severity.HIGH:
            self.risk_summary.high += 1
        elif sev == Severity.MEDIUM:
            self.risk_summary.medium += 1
        elif sev == Severity.LOW:
            self.risk_summary.low += 1
        else:
            self.risk_summary.info += 1
        return finding.id

    def add_attack_path(self, path: AttackPath) -> None:
        """追加一条攻击路径。

        :param path: 攻击路径实例
        """
        self.attack_paths.append(path)

    def add_appendix_entry(self, cmd: str, output: str) -> None:
        """追加技术附录条目。

        :param cmd: 执行的命令
        :param output: 命令输出
        """
        self.technical_appendix.append({
            "command": cmd,
            "output": output,
            "timestamp": datetime.now().isoformat(),
        })

    def update_executive_summary(self, summary: str) -> None:
        """更新执行摘要。

        :param summary: 新的执行摘要文本
        """
        self.executive_summary = summary

    # --- 类构造方法 ---

    @classmethod
    def from_session(cls, session_id: str) -> "PentestReport":
        """从会话 ID 构建报告（当前实现：创建空报告并设置标题）。

        :param session_id: 渗透测试会话标识
        :return: 新的 :class:`PentestReport` 实例
        """
        now = datetime.now()
        meta = ReportMeta(
            title=f"渗透测试报告 — 会话 {session_id}",
            start_date=now,
            end_date=now,
        )
        return cls(meta=meta, report_id=str(uuid.uuid4()))

    @classmethod
    def create_empty(cls) -> "PentestReport":
        """创建带默认值的空报告。

        :return: 空的 :class:`PentestReport` 实例
        """
        now = datetime.now()
        meta = ReportMeta(
            title="渗透测试报告",
            start_date=now,
            end_date=now,
        )
        return cls(meta=meta, report_id=str(uuid.uuid4()))
