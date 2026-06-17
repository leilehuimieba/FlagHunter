"""
IncrementalTracker — 增量报告追踪器

在渗透测试扫描过程中边扫描边更新报告，支持实时预览。
内部维护待写入的发现队列与附录队列，通过 ``flush`` 将数据
批量写入 ``ReportGenerator``，并可按设定间隔自动保存。

依赖：
    - :mod:`report_models` — ``Finding`` / ``PentestReport`` 数据模型
    - :mod:`report_generator` — ``ReportGenerator`` 报告生成器

作者：PentestAgent M3 Reporter 模块
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from .report_models import Finding, PentestReport
from .report_generator import ReportGenerator


class IncrementalTracker:
    """增量报告追踪器 — 边扫描边更新报告，支持实时预览。

    工作流程：
    1. 扫描模块通过 :meth:`queue_finding` / :meth:`queue_appendix` 将数据入队；
    2. 定期调用 :meth:`flush` 将队列数据写入 ``ReportGenerator``；
    3. 可选启动 :meth:`auto_flush_loop` 后台任务自动刷新；
    4. 通过 :meth:`get_preview` 获取当前报告的实时摘要。

    Args:
        report_generator: 已初始化的 ``ReportGenerator`` 实例。
        auto_save_interval: 自动保存间隔（秒），默认 ``300``（5 分钟）。
    """

    def __init__(self, report_generator: ReportGenerator, auto_save_interval: int = 300) -> None:
        self._generator: ReportGenerator = report_generator
        self._interval: int = auto_save_interval
        self._last_save: float = 0.0
        self._pending_findings: List[Finding] = []
        self._pending_appendix: List[Dict[str, Any]] = []
        self._flush_count: int = 0

    # -- 队列操作 -----------------------------------------------------------

    def queue_finding(self, finding: Finding) -> None:
        """将单个发现项追加到待写入队列。

        Args:
            finding: 扫描产生的 ``Finding`` 实例。
        """
        self._pending_findings.append(finding)

    def queue_appendix(self, command: str, output: str) -> None:
        """将命令输出记录追加到待写入附录队列。

        每条记录自动附加 ISO 格式时间戳。

        Args:
            command: 执行的命令字符串。
            output: 命令的标准输出内容。
        """
        entry = {
            "command": command,
            "output": output,
            "timestamp": datetime.now().isoformat(),
        }
        self._pending_appendix.append(entry)

    # -- 批量写入 -----------------------------------------------------------

    async def flush(self) -> Dict[str, Any]:
        """将队列中的待处理数据批量写入报告。

        执行顺序：
        1. 遍历 ``_pending_findings``，调用 ``ReportGenerator.add_finding()``；
        2. 遍历 ``_pending_appendix``，调用 ``ReportGenerator.add_command_output()``；
        3. 清空两个队列；
        4. 若距上次保存已超过 ``auto_save_interval``，触发自动保存。

        Returns:
            字典，包含以下字段：
            - ``findings_flushed`` (int): 本次刷入的发现数量。
            - ``appendix_flushed`` (int): 本次刷入的附录数量。
            - ``auto_saved`` (bool): 是否触发了自动保存。
        """
        findings_flushed = 0
        appendix_flushed = 0
        auto_saved = False

        try:
            # 刷入 findings
            for finding in self._pending_findings:
                try:
                    self._generator.add_finding(finding)
                    findings_flushed += 1
                except Exception:
                    pass  # 单条失败不影响其余

            # 刷入 appendix
            for entry in self._pending_appendix:
                try:
                    self._generator.add_command_output(
                        entry["command"], entry["output"]
                    )
                    appendix_flushed += 1
                except Exception:
                    pass

            # 清空队列
            self._pending_findings.clear()
            self._pending_appendix.clear()
            self._flush_count += 1

            # 检查是否需要自动保存
            now = time.time()
            if now - self._last_save >= self._interval:
                try:
                    self._generator.auto_save()
                    self._last_save = now
                    auto_saved = True
                except Exception:
                    pass
        except Exception:
            pass

        return {
            "findings_flushed": findings_flushed,
            "appendix_flushed": appendix_flushed,
            "auto_saved": auto_saved,
        }

    # -- 后台循环 -----------------------------------------------------------

    async def auto_flush_loop(self) -> None:
        """后台自动刷新循环。

        以 ``auto_save_interval`` 为周期反复调用 :meth:`flush`，
        可通过 ``asyncio.CancelledError`` 安全取消。
        """
        try:
            while True:
                await self.flush()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass  # 安全取消，不抛出

    # -- 实时预览 -----------------------------------------------------------

    def get_preview(self) -> str:
        """获取当前报告的实时预览摘要。

        Returns:
            格式示例：
            ``报告: 5个发现(1严重/2高危/1中危/1低危) | 待写入: 3 | 上次保存: 2分钟前``
            若报告尚未初始化，返回 ``"报告未初始化"``。
        """
        report = self._get_report()
        if report is None:
            return "报告未初始化"

        # 统计各级别发现数量
        findings = report.findings if hasattr(report, "findings") else []
        critical = sum(1 for f in findings if getattr(f, "severity", "").lower() == "critical")
        high = sum(1 for f in findings if getattr(f, "severity", "").lower() == "high")
        medium = sum(1 for f in findings if getattr(f, "severity", "").lower() == "medium")
        low = sum(1 for f in findings if getattr(f, "severity", "").lower() == "low")
        total = len(findings)

        pending = len(self._pending_findings) + len(self._pending_appendix)
        time_ago = self._time_ago(self._last_save) if self._last_save > 0 else "从未"

        return (
            f"报告: {total}个发现"
            f"({critical}严重/{high}高危/{medium}中危/{low}低危)"
            f" | 待写入: {pending}"
            f" | 上次保存: {time_ago}"
        )

    # -- 内部工具 -----------------------------------------------------------

    def _get_report(self) -> Optional[PentestReport]:
        """获取当前 ``ReportGenerator`` 管理的报告实例。

        Returns:
            当前 ``PentestReport`` 对象；若获取失败返回 ``None``。
        """
        try:
            return self._generator.get_current_report()
        except Exception:
            return None

    def _time_ago(self, timestamp: float) -> str:
        """将 Unix 时间戳转换为人类可读的 ``"X分钟前"`` 格式。

        Args:
            timestamp: Unix 时间戳（秒）。

        Returns:
            相对时间描述字符串，例如 ``"3分钟前"``、``"刚刚"``。
        """
        if timestamp <= 0:
            return "从未"

        elapsed = time.time() - timestamp
        if elapsed < 60:
            return "刚刚"
        minutes = int(elapsed // 60)
        if minutes < 60:
            return f"{minutes}分钟前"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}小时前"
        days = hours // 24
        return f"{days}天前"
