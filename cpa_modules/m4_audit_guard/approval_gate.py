"""
approval_gate.py — 危险操作确认门

PentestAgent M4 Audit Guard 模块的核心安全门控组件。
对高风险操作实施分级风险评估与人工确认机制，
支持异步/同步双模式调用，策略可运行时配置。

Python 3.10+
"""

import asyncio
import copy
import re
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from .audit_logger import AuditLogger, AuditEntry


class ApprovalGate:
    """危险操作确认门 — 高风险操作需人工确认后执行

    工作流程：
        1. check() / check_sync() 接收操作描述
        2. assess_risk() 综合评分确定 risk_level
        3. 低于 auto_approve 阈值 → 自动放行
        4. 高风险 → 生成 approval_id，等待人工 approve()
        5. 所有操作均记录审计日志
    """

    # 默认危险工具列表（触发人工确认的敏感工具名）
    DEFAULT_DANGEROUS_TOOLS = [
        "rm", "del", "remove", "delete",
        "dd", "format", "mkfs", "fdisk",
        "format-volume", "remove-item",
        "msfvenom", "exploit", "exploit -j",
        "sqlmap --dump-all", "sqlmap --os-shell",
        "hydra -t", "john --wordlist",
    ]

    # 默认危险命令正则模式（用于模式匹配检测）
    DEFAULT_DANGEROUS_PATTERNS = [
        r"rm\s+-rf\s+/",
        r">\s*/dev/sd[a-z]",
        r"DROP\s+DATABASE",
        r"DELETE\s+FROM",
        r"shutdown\s+-h",
        r"reboot",
    ]

    # 自动批准风险阈值映射
    _AUTO_APPROVE_LEVELS = {"low": 0, "medium": 1, "high": 2, "none": -1}

    def __init__(
        self,
        audit_logger: AuditLogger,
        dangerous_tools: Optional[List[str]] = None,
        dangerous_patterns: Optional[List[str]] = None,
        approval_timeout: int = 300,
        auto_approve_below_risk: str = "low",
    ):
        """初始化确认门实例

        参数：
            audit_logger: 审计日志实例，用于记录所有操作
            dangerous_tools: 需确认的工具列表（默认使用 DEFAULT_DANGEROUS_TOOLS）
            dangerous_patterns: 需确认的命令正则模式列表
            approval_timeout: 待确认操作的超时秒数，默认 300 秒
            auto_approve_below_risk: 自动批准阈值，可选 "low"|"medium"|"high"|"none"
        """
        self._audit: AuditLogger = audit_logger
        self._dangerous_tools: List[str] = dangerous_tools or self.DEFAULT_DANGEROUS_TOOLS[:]
        self._dangerous_patterns: List[re.Pattern] = [
            re.compile(p, re.IGNORECASE)
            for p in (dangerous_patterns or self.DEFAULT_DANGEROUS_PATTERNS)
        ]
        self._timeout: int = approval_timeout
        self._auto_approve: str = auto_approve_below_risk

        # 待确认操作存储池: {approval_id -> 操作信息字典}
        self._pending_approvals: Dict[str, dict] = {}

        # 统计计数器
        self._approved_count: int = 0
        self._denied_count: int = 0
        self._auto_approved_count: int = 0

    # ------------------------------------------------------------------ #
    #  核心确认流程（异步版本）
    # ------------------------------------------------------------------ #

    async def check(
        self,
        action: str,
        target: str,
        tool: str = "",
        command: str = "",
        context: Optional[dict] = None,
    ) -> dict:
        """异步检查操作是否需要人工确认

        判断流程：
            a. 调用 assess_risk() 计算综合风险等级
            b. 风险等级低于等于 auto_approve 阈值 → 自动通过
            c. 工具名在危险工具列表中 → 需要人工输入确认
            d. 命令匹配危险正则模式 → 需要人工输入确认
            e. 记录审计日志

        参数：
            action: 操作描述（如 "删除文件"、"扫描端口"）
            target: 操作目标（如文件路径、IP 地址、域名）
            tool: 使用的工具名称
            command: 完整的命令字符串
            context: 额外上下文信息字典（可选）

        返回：
            dict，包含以下字段：
                - approved (bool): 是否已批准
                - requires_input (bool): 是否需要人工确认输入
                - approval_id (str): 确认请求唯一 ID（需要确认时）
                - risk_level (str): 风险等级 low/medium/high/critical
                - reason (str): 判断理由说明
                - suggested_action (str): 建议操作提示
        """
        context = context or {}

        # a. 风险评估
        risk_level: str = self.assess_risk(tool, command, target)
        auto_level: int = self._AUTO_APPROVE_LEVELS.get(self._auto_approve, 0)
        risk_value: int = self._risk_level_to_value(risk_level)

        # b. 自动批准（风险等级低于阈值）
        if risk_value <= auto_level:
            self._auto_approved_count += 1
            self._audit.log(AuditEntry(
                timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
                session_id="", action_type="approval", action_detail={"action": action, "tool": tool, "command": command, "risk_level": risk_level, "result": "auto_approved", "details": f"自动通过: 风险等级 {risk_level} 低于阈值 {self._auto_approve}"},
                target=target, result="auto_approved"))
            return {
                "approved": True,
                "requires_input": False,
                "approval_id": "",
                "risk_level": risk_level,
                "reason": f"风险等级 {risk_level} 低于自动批准阈值 {self._auto_approve}",
                "suggested_action": "直接执行",
            }

        # c / d. 判断是否需要人工确认
        tool_match: bool = self._is_tool_dangerous(tool)
        pattern_match: bool = self._is_command_dangerous(command)
        requires_input: bool = tool_match or pattern_match

        # 生成确认 ID 并写入待确认池
        approval_id: str = ""
        if requires_input:
            approval_id = str(uuid.uuid4())[:12]
            self._pending_approvals[approval_id] = {
                "id": approval_id,
                "action": action,
                "target": target,
                "tool": tool,
                "command": command,
                "context": context,
                "risk_level": risk_level,
                "requires_input": True,
                "tool_match": tool_match,
                "pattern_match": pattern_match,
                "created_at": time.time(),
                "status": "pending",
            }

        # e. 记录审计日志
        detail_parts = []
        if tool_match: detail_parts.append("工具匹配")
        if pattern_match: detail_parts.append("命令模式匹配")
        if requires_input: detail_parts.append("需人工确认")
        else: detail_parts.append("等待审查")
        self._audit.log(AuditEntry(
            timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
            session_id="", action_type="approval", action_detail={"action": action, "tool": tool, "command": command, "risk_level": risk_level, "result": "pending_approval" if requires_input else "needs_review", "details": " | ".join(detail_parts)},
            target=target, result="pending_approval" if requires_input else "needs_review"))

        # f. 构造返回结果
        reason_parts: List[str] = []
        if tool_match:
            reason_parts.append(f"工具 '{tool}' 在危险工具列表中")
        if pattern_match:
            reason_parts.append("命令匹配危险模式")
        reason_parts.append(f"综合风险等级: {risk_level}")

        suggested: str = (
            f"请使用 approve('{approval_id}', approved=True) 确认执行"
            if requires_input
            else "建议人工复核后执行"
        )

        return {
            "approved": False,
            "requires_input": requires_input,
            "approval_id": approval_id,
            "risk_level": risk_level,
            "reason": "; ".join(reason_parts),
            "suggested_action": suggested,
        }

    async def approve(
        self,
        approval_id: str,
        approved: bool = True,
        notes: str = "",
    ) -> dict:
        """响应对指定确认请求的人工审批

        从 _pending_approvals 中查找 approval_id，更新状态并记录日志。

        参数：
            approval_id: 确认请求唯一 ID（由 check() 生成）
            approved: True 表示批准执行，False 表示拒绝
            notes: 审批备注说明

        返回：
            dict，包含：
                - success (bool): 审批操作是否成功（ID 存在则为 True）
                - message (str): 状态说明信息
        """
        entry: Optional[dict] = self._pending_approvals.get(approval_id)

        # 确认 ID 不存在或已过期
        if entry is None:
            return {
                "success": False,
                "message": "确认ID不存在或已过期",
            }

        # 检查超时
        elapsed: float = time.time() - entry["created_at"]
        if elapsed > self._timeout:
            del self._pending_approvals[approval_id]
            self._audit.log(AuditEntry(
                timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
                session_id="", action_type="approval", action_detail={"action": entry["action"], "tool": entry["tool"], "command": entry.get("command", ""), "risk_level": entry["risk_level"], "result": "timeout", "details": f"确认请求超时 ({elapsed:.1f}s > {self._timeout}s)"},
                target=entry["target"], result="timeout"))
            return {
                "success": False,
                "message": f"确认请求已超时（超过 {self._timeout} 秒）",
            }

        # 移除待确认池中的该条目
        del self._pending_approvals[approval_id]

        if approved:
            self._approved_count += 1
            entry["status"] = "approved"
            self._audit.log(AuditEntry(
                timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
                session_id="", action_type="approval", action_detail={"action": entry["action"], "tool": entry["tool"], "command": entry.get("command", ""), "risk_level": entry["risk_level"], "result": "approved", "details": f"人工批准 | 备注: {notes}" if notes else "人工批准"},
                target=entry["target"], result="approved"))
            return {
                "success": True,
                "message": "已批准",
            }

        self._denied_count += 1
        entry["status"] = "denied"
        self._audit.log(AuditEntry(
            timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
            session_id="", action_type="approval", action_detail={"action": entry["action"], "tool": entry["tool"], "command": entry.get("command", ""), "risk_level": entry["risk_level"], "result": "denied", "details": f"人工拒绝 | 备注: {notes}" if notes else "人工拒绝"},
            target=entry["target"], result="denied"))
        return {
            "success": True,
            "message": "已拒绝",
        }

    # ------------------------------------------------------------------ #
    #  核心确认流程（同步版本）
    # ------------------------------------------------------------------ #

    def check_sync(
        self,
        action: str,
        target: str,
        tool: str = "",
        command: str = "",
    ) -> dict:
        """同步检查操作是否需要人工确认

        自动完成风险等级判断，若需要人工确认但无法异步等待输入，
        则采用保守策略拒绝执行（approved=False）。

        参数：
            action: 操作描述
            target: 操作目标
            tool: 使用的工具名称
            command: 完整的命令字符串

        返回：
            dict，字段与 check() 一致
        """
        risk_level: str = self.assess_risk(tool, command, target)
        auto_level: int = self._AUTO_APPROVE_LEVELS.get(self._auto_approve, 0)
        risk_value: int = self._risk_level_to_value(risk_level)

        # 自动批准（风险等级低于阈值）
        if risk_value <= auto_level:
            self._auto_approved_count += 1
            self._audit.log(AuditEntry(
                timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
                session_id="", action_type="approval", action_detail={"action": action, "tool": tool, "command": command, "risk_level": risk_level, "result": "auto_approved", "details": f"同步自动通过: 风险等级 {risk_level}"},
                target=target, result="auto_approved"))
            return {
                "approved": True,
                "requires_input": False,
                "approval_id": "",
                "risk_level": risk_level,
                "reason": f"同步模式: 风险等级 {risk_level} 低于阈值 {self._auto_approve}",
                "suggested_action": "直接执行",
            }

        # 判断是否需要人工确认
        tool_match: bool = self._is_tool_dangerous(tool)
        pattern_match: bool = self._is_command_dangerous(command)
        requires_input: bool = tool_match or pattern_match

        # 同步模式下无法等待异步输入，采用保守策略
        if requires_input:
            self._audit.log(AuditEntry(
                timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
                session_id="", action_type="approval", action_detail={"action": action, "tool": tool, "command": command, "risk_level": risk_level, "result": "blocked_sync", "details": "同步模式: 检测到高风险，因无法等待人工确认而拒绝"},
                target=target, result="blocked_sync"))
            return {
                "approved": False,
                "requires_input": True,
                "approval_id": "",
                "risk_level": risk_level,
                "reason": (
                    f"检测到高风险（{'工具匹配' if tool_match else ''}"
                    f"{' | ' if tool_match and pattern_match else ''}"
                    f"{'命令模式匹配' if pattern_match else ''}）"
                    "; 同步模式下无法等待确认，已拒绝"
                ),
                "suggested_action": "请使用异步 check() + approve() 流程进行确认",
            }

        # 不需要人工确认但仍高于阈值的情况（保守拒绝）
        self._audit.log(AuditEntry(
            timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
            session_id="", action_type="approval", action_detail={"action": action, "tool": tool, "command": command, "risk_level": risk_level, "result": "blocked_sync", "details": "同步模式: 风险等级高但无明确模式匹配，保守拒绝"},
            target=target, result="blocked_sync"))
        return {
            "approved": False,
            "requires_input": False,
            "approval_id": "",
            "risk_level": risk_level,
            "reason": f"同步模式: 风险等级 {risk_level} 较高，保守拒绝",
            "suggested_action": "建议使用异步 check() 进行详细确认",
        }

    # ------------------------------------------------------------------ #
    #  风险评估
    # ------------------------------------------------------------------ #

    def assess_risk(self, tool: str, command: str, target: str) -> str:
        """综合风险评估

        三个维度加权求和：
            - 工具风险评分 (_tool_risk_score): 0-10
            - 目标风险评分 (_target_risk_score): 0-10
            - 模式风险评分 (_pattern_risk_score): 0-10

        综合评分区间：
            0-8   → "low"     (低风险)
            9-15  → "medium"  (中风险)
            16-22 → "high"    (高风险)
            23+   → "critical"(严重风险)

        参数：
            tool: 使用的工具名称
            command: 完整的命令字符串
            target: 操作目标

        返回：
            str: 风险等级字符串 "low" / "medium" / "high" / "critical"
        """
        tool_score: int = self._tool_risk_score(tool)
        target_score: int = self._target_risk_score(target)
        pattern_score: int = self._pattern_risk_score(command)

        total: int = tool_score + target_score + pattern_score

        if total <= 8:
            return "low"
        if total <= 15:
            return "medium"
        if total <= 22:
            return "high"
        return "critical"

    def _tool_risk_score(self, tool: str) -> int:
        """计算工具的风险评分

        评分规则（子串匹配）：
            - "rm" / "del" / "format" → 10 分（极高风险：数据销毁）
            - "msfvenom" / "exploit"    → 9  分（高风险：渗透利用）
            - "sqlmap"                   → 6  分（中高风险：SQL 注入）
            - "nmap"                     → 3  分（中低风险：端口扫描）
            - "curl" / "wget"            → 2  分（低风险：数据下载）
            - "ping"                     → 1  分（极低风险：连通性测试）
            - 未匹配                     → 0  分

        参数：
            tool: 工具名称字符串

        返回：
            int: 0-10 的风险评分
        """
        t_lower: str = tool.lower()
        if any(k in t_lower for k in ("rm", "del", "format")):
            return 10
        if any(k in t_lower for k in ("msfvenom", "exploit")):
            return 9
        if "sqlmap" in t_lower:
            return 6
        if "nmap" in t_lower:
            return 3
        if any(k in t_lower for k in ("curl", "wget")):
            return 2
        if "ping" in t_lower:
            return 1
        return 0

    def _target_risk_score(self, target: str) -> int:
        """计算操作目标的风险评分

        评分规则：
            - .gov / .edu / .mil 域名    → 10 分（政府/教育/军事机构）
            - 生产环境域名含 "prod"      → 8  分（生产环境）
            - 外网 IP（非内网/本地）      → 5  分
            - 内网 IP（10.x / 172.16-31 / 192.168）→ 3 分
            - localhost / 127.x          → 1  分
            - 未知目标                   → 0  分

        参数：
            target: 目标地址字符串（IP、域名、文件路径等）

        返回：
            int: 0-10 的风险评分
        """
        t_lower: str = target.lower()

        # 政府/教育/军事域名
        if any(t_lower.endswith(s) for s in (".gov", ".edu", ".mil")):
            return 10
        if any(f".{s}" in t_lower for s in ("gov", "edu", "mil")):
            return 10

        # 生产环境
        if "prod" in t_lower:
            return 8

        # 本地环回地址
        if "localhost" in t_lower or t_lower.startswith("127."):
            return 1

        # 内网 IP 段
        if t_lower.startswith("10."):
            return 3
        if t_lower.startswith("192.168."):
            return 3
        # 172.16.0.0 - 172.31.255.255
        if t_lower.startswith("172."):
            parts: List[str] = t_lower.split(".")
            if len(parts) >= 2 and parts[1].isdigit():
                seg: int = int(parts[1])
                if 16 <= seg <= 31:
                    return 3

        # 外网 IP（简单判断为 IP 地址格式）
        ip_pattern: re.Pattern = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
        if ip_pattern.match(target):
            return 5

        return 0

    def _pattern_risk_score(self, command: str) -> int:
        """计算命令字符串的模式风险评分

        先检查是否匹配已编译的危险正则模式，
        若未匹配则对关键词进行逐项评分。

        关键词评分：
            - rm -rf, dd, mkfs, DROP DATABASE 等关键词 → 逐项累加
            - 最高不超过 10 分

        参数：
            command: 完整的命令字符串

        返回：
            int: 0-10 的风险评分
        """
        if not command:
            return 0

        c_lower: str = command.lower()

        # 检查已编译的正则模式
        for pat in self._dangerous_patterns:
            if pat.search(command):
                return 10

        # 逐项关键词评分
        score: int = 0
        keywords: Dict[str, int] = {
            "rm -rf": 8,
            "dd if=": 7,
            "mkfs": 7,
            "fdisk": 6,
            "drop database": 8,
            "delete from": 5,
            "shutdown": 6,
            "reboot": 5,
            "format": 5,
            "--os-shell": 7,
            "--dump-all": 5,
            "exploit -j": 6,
        }

        for kw, val in keywords.items():
            if kw in c_lower:
                score += val

        return min(score, 10)

    # ------------------------------------------------------------------ #
    #  查询接口
    # ------------------------------------------------------------------ #

    def get_pending_approvals(self) -> List[dict]:
        """获取所有待确认的操作列表

        返回深拷贝的数据副本，防止外部修改内部状态。
        自动过滤掉超时的待确认请求。

        返回：
            List[dict]: 每个字典包含 pending approval 的完整信息
        """
        now: float = time.time()
        expired: List[str] = []
        result: List[dict] = []

        for aid, entry in self._pending_approvals.items():
            if now - entry["created_at"] > self._timeout:
                expired.append(aid)
            else:
                result.append(copy.deepcopy(entry))

        # 清理超时条目
        for aid in expired:
            del self._pending_approvals[aid]

        return result

    def get_stats(self) -> dict:
        """获取确认门统计信息

        返回：
            dict，包含以下计数：
                - approved (int): 人工批准次数
                - denied (int): 人工拒绝次数
                - pending (int): 当前待确认数量
                - auto_approved (int): 自动批准次数
        """
        return {
            "approved": self._approved_count,
            "denied": self._denied_count,
            "pending": len(self._pending_approvals),
            "auto_approved": self._auto_approved_count,
        }

    # ------------------------------------------------------------------ #
    #  配置管理
    # ------------------------------------------------------------------ #

    def add_dangerous_tool(self, tool: str) -> None:
        """向危险工具列表中添加新的工具名称

        若工具已存在则自动去重，不重复添加。

        参数：
            tool: 需要添加的工具名称字符串
        """
        if tool not in self._dangerous_tools:
            self._dangerous_tools.append(tool)

    def remove_dangerous_tool(self, tool: str) -> None:
        """从危险工具列表中移除指定工具名称

        若工具不存在则不执行任何操作，不抛出异常。

        参数：
            tool: 需要移除的工具名称字符串
        """
        if tool in self._dangerous_tools:
            self._pending_approvals  # 占位保持逻辑完整
            self._dangerous_tools.remove(tool)

    def add_dangerous_pattern(self, pattern: str) -> None:
        """向危险模式列表中添加新的正则表达式模式

        自动编译为正则表达式对象（忽略大小写），并追加到模式列表。

        参数：
            pattern: 正则表达式字符串
        """
        compiled: re.Pattern = re.compile(pattern, re.IGNORECASE)
        self._dangerous_patterns.append(compiled)

    # ------------------------------------------------------------------ #
    #  内部辅助方法
    # ------------------------------------------------------------------ #

    def _is_tool_dangerous(self, tool: str) -> bool:
        """判断工具名是否在危险工具列表中（子串匹配）

        参数：
            tool: 工具名称

        返回：
            bool: 是否匹配危险工具
        """
        t_lower: str = tool.lower()
        return any(dt.lower() in t_lower or t_lower in dt.lower() for dt in self._dangerous_tools)

    def _is_command_dangerous(self, command: str) -> bool:
        """判断命令字符串是否匹配危险正则模式

        参数：
            command: 命令字符串

        返回：
            bool: 是否匹配危险模式
        """
        if not command:
            return False
        return any(pat.search(command) for pat in self._dangerous_patterns)

    @staticmethod
    def _risk_level_to_value(level: str) -> int:
        """将风险等级字符串转换为数值（用于阈值比较）

        参数：
            level: "low" / "medium" / "high" / "critical"

        返回：
            int: 对应的数值等级 (0/1/2/3)
        """
        mapping: Dict[str, int] = {
            "low": 0,
            "medium": 1,
            "high": 2,
            "critical": 3,
        }
        return mapping.get(level, 0)
