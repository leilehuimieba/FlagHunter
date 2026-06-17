"""
data_protection.py — PentestAgent M4 Audit Guard 数据保护模块

提供敏感信息的自动检测、脱敏、哈希处理功能。
覆盖 API Key、密码、Token、IP 地址、邮箱、Flag、信用卡等 8 类敏感信息。

技术约束: Python 3.10+, 仅使用标准库 (re, hashlib, copy), 零外部依赖。
"""

import copy
import hashlib
import re
from typing import Any, Dict, List, Optional


class DataProtector:
    """数据保护器 — 自动检测和脱敏敏感信息。"""

    # 敏感信息正则模式与脱敏函数映射
    # severity: critical=极高危, high=高危, medium=中危
    SENSITIVE_PATTERNS: Dict[str, Dict[str, Any]] = {
        "api_key": {
            "pattern": (
                r"(sk-[a-zA-Z0-9]{20,}"
                r"|AKIA[0-9A-Z]{16}"
                r"|ghp_[a-zA-Z0-9]{36}"
                r"|AIza[a-zA-Z0-9_\-]{35,})"
            ),
            "mask": lambda m: (
                m.group(1)[:4] + "****" + m.group(1)[-4:]
                if len(m.group(1)) > 12
                else "****"
            ),
            "severity": "critical",
        },
        "password": {
            "pattern": r"(?i)(password\s*[=:]\s*)([^\s&;]+)",
            "mask": lambda m: m.group(1) + "****",
            "severity": "critical",
        },
        "token": {
            "pattern": r"(?i)(token\s*[=:]\s*(?:Bearer\s+)?|Bearer\s+)([a-zA-Z0-9_\-\.]+)",
            "mask": lambda m: m.group(1) + "****",
            "severity": "high",
        },
        "ip_address": {
            "pattern": (
                r"(\b(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)"
                r"\.(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\b)"
            ),
            "mask": lambda m: DataProtector._mask_ip(m.group(1)),
            "severity": "medium",
            "configurable": True,
        },
        "email": {
            "pattern": r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)",
            "mask": lambda m: DataProtector._mask_email(m.group(1)),
            "severity": "medium",
            "configurable": True,
        },
        "flag": {
            "pattern": r"(flag\{[a-zA-Z0-9_\-]+\})",
            "mask": lambda m: "flag{***}",
            "severity": "high",
            "configurable": True,
        },
        "credit_card": {
            "pattern": r"\b(\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})\b",
            "mask": lambda m: "****-****-****-" + m.group(1)[-4:],
            "severity": "high",
        },
        "phone_number": {
            "pattern": r"(\b1[3-9]\d{9}\b)",
            "mask": lambda m: m.group(1)[:3] + "****" + m.group(1)[-4:],
            "severity": "medium",
            "configurable": True,
        },
    }

    def __init__(
        self,
        mask_ips: bool = False,
        mask_emails: bool = True,
        mask_flags: bool = False,
        mask_phones: bool = True,
    ) -> None:
        """初始化数据保护器。

        参数:
            mask_ips: 是否脱敏 IP 地址（默认 False，保留内网/公网 IP）
            mask_emails: 是否脱敏邮箱地址（默认 True）
            mask_flags: 是否脱敏 CTF Flag（默认 False，比赛场景保留）
            mask_phones: 是否脱敏手机号码（默认 True）
        """
        self._config: Dict[str, bool] = {
            "ip_address": mask_ips,
            "email": mask_emails,
            "flag": mask_flags,
            "phone_number": mask_phones,
        }

    # ────────────────────────────── 脱敏方法 ──────────────────────────────

    def mask(self, text: str, extra_patterns: Optional[Dict[str, Any]] = None) -> str:
        """对文本进行敏感信息脱敏。

        按照 SENSITIVE_PATTERNS 定义的顺序逐个正则匹配并替换。
        configurable 类型的规则根据 self._config 决定是否处理。
        extra_patterns 可传入额外的自定义脱敏规则。

        参数:
            text: 原始文本
            extra_patterns: 额外的脱敏规则字典，格式与 SENSITIVE_PATTERNS 一致

        返回:
            脱敏后的文本
        """
        if not isinstance(text, str):
            return text

        # 合并内置规则与额外规则
        patterns = dict(self.SENSITIVE_PATTERNS)
        if extra_patterns:
            patterns = {**patterns, **extra_patterns}

        result = text
        for name, rule in patterns.items():
            # configurable 类型需根据配置决定是否处理
            if rule.get("configurable") and not self._config.get(name, True):
                continue
            result = re.sub(rule["pattern"], rule["mask"], result)
        return result

    def mask_file(self, file_path: str, output_path: Optional[str] = None) -> str:
        """读取文件内容进行脱敏，并写入输出文件。

        参数:
            file_path: 输入文件路径
            output_path: 输出文件路径，为 None 则覆盖原文件

        返回:
            输出文件的绝对路径
        """
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        masked = self.mask(content)

        out_path = output_path or file_path
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(masked)

        return out_path

    def mask_structured(
        self, data: dict, fields_to_mask: Optional[List[str]] = None
    ) -> dict:
        """递归遍历字典的所有字段值，对字符串值调用 mask() 进行脱敏。

        参数:
            data: 待脱敏的字典
            fields_to_mask: 指定需要脱敏的字段名列表，为 None 则处理所有字符串值

        返回:
            新的字典（不修改原字典，使用 deepcopy）
        """
        if not isinstance(data, dict):
            return data  # type: ignore[return-value]

        cloned = copy.deepcopy(data)
        return self._mask_structured_recursive(cloned, fields_to_mask)

    # 已知敏感字段名集合（用于结构化数据字段级脱敏）
    _SENSITIVE_FIELD_NAMES = {
        "api_key", "password", "token", "secret", "access_key",
        "private_key", "credit_card", "phone", "phone_number",
    }

    def _mask_structured_recursive(
        self, data: Any, fields_to_mask: Optional[List[str]] = None
    ) -> Any:
        """递归处理字典/列表中的字符串值。

        当字段名在 fields_to_mask 中或属于已知敏感字段名时，直接脱敏值；
        其他字符串值则通过 mask() 进行内容模式匹配脱敏。
        """
        if isinstance(data, dict):
            for key, value in data.items():
                # 判断当前字段是否需要脱敏
                should_mask_field = (
                    fields_to_mask is not None and key in fields_to_mask
                ) or (
                    fields_to_mask is None and key in self._SENSITIVE_FIELD_NAMES
                )

                if should_mask_field and isinstance(value, str):
                    data[key] = "****"
                else:
                    data[key] = self._mask_structured_recursive(value, fields_to_mask)
            return data
        elif isinstance(data, list):
            return [self._mask_structured_recursive(item, fields_to_mask) for item in data]  # type: ignore[return-value]
        elif isinstance(data, str):
            return self.mask(data)
        else:
            return data

    # ────────────────────────────── 检测方法 ──────────────────────────────

    def scan(self, text: str) -> List[Dict[str, Any]]:
        """检测文本中的敏感信息，不进行替换。

        返回包含敏感信息类型、位置、预览和严重程度的列表:
            [
                {
                    "type": "api_key",
                    "position": (start, end),
                    "preview": "sk-ab****cd",
                    "severity": "high"
                },
                ...
            ]

        参数:
            text: 待检测文本

        返回:
            敏感信息检测结果列表
        """
        findings: List[Dict[str, Any]] = []
        if not isinstance(text, str):
            return findings

        for name, rule in self.SENSITIVE_PATTERNS.items():
            # configurable 类型需根据配置决定是否检测
            if rule.get("configurable") and not self._config.get(name, True):
                continue

            for match in re.finditer(rule["pattern"], text):
                start, end = match.span()
                # 生成脱敏预览（避免在报告中暴露真实值）
                preview = rule["mask"](match)
                findings.append(
                    {
                        "type": name,
                        "position": (start, end),
                        "preview": preview,
                        "severity": rule.get("severity", "medium"),
                    }
                )

        return findings

    def scan_file(self, file_path: str) -> List[Dict[str, Any]]:
        """读取文件并检测其中的敏感信息。

        参数:
            file_path: 待检测文件路径

        返回:
            敏感信息检测结果列表
        """
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return self.scan(content)

    def has_sensitive(self, text: str) -> bool:
        """快速检查文本中是否包含任何敏感信息。

        任一模式匹配即返回 True，用于前置快速判断。

        参数:
            text: 待检查文本

        返回:
            若包含敏感信息返回 True，否则返回 False
        """
        if not isinstance(text, str):
            return False

        for name, rule in self.SENSITIVE_PATTERNS.items():
            if rule.get("configurable") and not self._config.get(name, True):
                continue
            if re.search(rule["pattern"], text):
                return True
        return False

    # ────────────────────────────── 报告脱敏专用 ──────────────────────────────

    def sanitize_for_report(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """对报告数据进行脱敏处理。

        脱敏策略:
            - api_key / password / token / credit_card: 始终脱敏
            - ip_address / email / flag / phone_number: 根据 self._config

        递归处理 report_data 中的所有字符串值。

        参数:
            report_data: 原始报告数据字典

        返回:
            脱敏后的新字典
        """
        # 强制脱敏的高危类型
        force_mask_types = {"api_key", "password", "token", "credit_card"}
        # 根据配置脱敏的类型
        config_mask_types = {
            k for k, v in self._config.items() if v
        }
        mask_types = force_mask_types | config_mask_types

        cloned = copy.deepcopy(report_data)
        return self._sanitize_for_report_recursive(cloned, mask_types)

    def _sanitize_for_report_recursive(
        self, data: Any, mask_types: set
    ) -> Any:
        """递归处理报告数据中的字符串值。

        当字段名属于已知敏感字段名且在 mask_types 中时，直接脱敏值；
        其他字符串值则通过内容模式匹配进行选择性脱敏。
        """
        if isinstance(data, dict):
            for key, value in data.items():
                # 字段级脱敏：字段名匹配已知敏感字段且类型在脱敏集合中
                if (
                    key in self._SENSITIVE_FIELD_NAMES
                    and key in mask_types
                    and isinstance(value, str)
                ):
                    data[key] = "****"
                else:
                    data[key] = self._sanitize_for_report_recursive(value, mask_types)
            return data
        elif isinstance(data, list):
            return [self._sanitize_for_report_recursive(item, mask_types) for item in data]  # type: ignore[return-value]
        elif isinstance(data, str):
            return self._mask_selective(data, mask_types)
        else:
            return data

    def _mask_selective(self, text: str, mask_types: set) -> str:
        """根据指定的类型集合对文本进行选择性脱敏。"""
        result = text
        for name, rule in self.SENSITIVE_PATTERNS.items():
            if name not in mask_types:
                continue
            if rule.get("configurable") and not self._config.get(name, True):
                continue
            result = re.sub(rule["pattern"], rule["mask"], result)
        return result

    def sanitize_audit_log(self, log_entry: Dict[str, Any]) -> Dict[str, Any]:
        """审计日志专用脱敏。

        仅脱敏极高危类型（api_key, password），其他类型保留原始值，
        以便审计人员能够追踪操作细节。

        参数:
            log_entry: 单条审计日志字典

        返回:
            脱敏后的新字典
        """
        audit_mask_types = {"api_key", "password"}
        cloned = copy.deepcopy(log_entry)
        return self._sanitize_for_report_recursive(cloned, audit_mask_types)  # type: ignore[return-value]

    # ────────────────────────────── 辅助函数 ──────────────────────────────

    @staticmethod
    def _mask_ip(ip: str) -> str:
        """将 IP 地址脱敏为 192.168.x.x 格式。

        保留前两个网段，后两个网段替换为 x.x。

        参数:
            ip: 原始 IP 地址，如 "192.168.1.100"

        返回:
            脱敏后的 IP 地址，如 "192.168.x.x"
        """
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.x.x"
        return ip

    @staticmethod
    def _mask_email(email: str) -> str:
        """将邮箱地址脱敏为 u***@example.com 格式。

        保留用户名首字符，其余替换为 ***。

        参数:
            email: 原始邮箱地址，如 "user@example.com"

        返回:
            脱敏后的邮箱地址，如 "u***@example.com"
        """
        if "@" not in email:
            return email
        local, domain = email.rsplit("@", 1)
        if len(local) <= 1:
            return f"***@{domain}"
        return f"{local[0]}***@{domain}"

    @staticmethod
    def hash_identifier(value: str) -> str:
        """对标识符进行 SHA256 哈希，取前 16 位十六进制字符。

        用于生成不可逆的匿名化标识符，如用户 ID 哈希、会话指纹等。

        参数:
            value: 原始标识符字符串

        返回:
            16 位十六进制哈希字符串
        """
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    # ────────────────────────────── 批量处理 ──────────────────────────────

    def mask_batch(self, texts: List[str]) -> List[str]:
        """批量对文本列表进行脱敏。

        参数:
            texts: 原始文本列表

        返回:
            脱敏后的文本列表
        """
        return [self.mask(text) for text in texts]

    def scan_batch(self, texts: List[str]) -> List[List[Dict[str, Any]]]:
        """批量对文本列表进行敏感信息检测。

        参数:
            texts: 原始文本列表

        返回:
            每条文本的检测结果列表
        """
        return [self.scan(text) for text in texts]
