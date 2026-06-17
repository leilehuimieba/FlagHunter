#!/usr/bin/env python3
"""
roe_engine.py — PentestAgent M4 Audit Guard 的 RoE (Rules of Engagement) 规则引擎。

本模块负责：
1. 解析授权范围文档（.txt / .md / .yaml）
2. 提取 IP、域名、时间窗口、工具限制等规则
3. 提供统一的授权校验接口（IP / 域名 / 工具 / 时间 / 目标）
4. 规则增删与配置摘要

技术约束：仅使用 Python 3.10+ 标准库（ipaddress, re, datetime, pathlib, os），零外部依赖。
"""

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class RoERule:
    """单条 RoE 规则。

    Attributes:
        rule_type: 规则类型，取值包括
            "allow_ip" | "allow_cidr" | "allow_domain" | "allow_wildcard_domain" |
            "allow_time" | "deny_ip" | "deny_domain" | "deny_tool" | "require_approval"
        value: 规则值（IP、域名、CIDR、工具名、时间字符串等）
        description: 规则描述说明
        priority: 优先级，数值越大越优先
    """
    rule_type: str
    value: str
    description: str = ""
    priority: int = 1


@dataclass
class RoEConfig:
    """RoE 配置汇总，对应一份授权文档解析后的完整规则集。

    Attributes:
        client_name: 客户名称
        project_name: 项目名称
        tester_name: 测试人员
        allowed_ips: 显式允许的单个 IP 列表
        allowed_cidrs: 允许的 CIDR 网段列表
        allowed_domains: 允许的域名列表（可包含通配符域名如 *.example.com）
        denied_ips: 明确禁止的 IP 列表
        denied_domains: 明确禁止的域名列表
        denied_tools: 禁止使用的工具或参数列表
        time_window_start: 授权时间窗口起始
        time_window_end: 授权时间窗口结束
        require_approval_tools: 需要人工确认后方可使用的工具列表
        emergency_contact: 紧急联系方式
        raw_rules: 解析后的原始规则列表
    """
    client_name: str = ""
    project_name: str = ""
    tester_name: str = ""
    allowed_ips: List[str] = field(default_factory=list)
    allowed_cidrs: List[str] = field(default_factory=list)
    allowed_domains: List[str] = field(default_factory=list)
    denied_ips: List[str] = field(default_factory=list)
    denied_domains: List[str] = field(default_factory=list)
    denied_tools: List[str] = field(default_factory=list)
    time_window_start: Optional[datetime] = None
    time_window_end: Optional[datetime] = None
    require_approval_tools: List[str] = field(default_factory=list)
    emergency_contact: str = ""
    raw_rules: List[RoERule] = field(default_factory=list)


# ---------------------------------------------------------------------------
# RoEEngine 主类
# ---------------------------------------------------------------------------

class RoEEngine:
    """RoE 规则引擎 — 解析授权文档，提供授权校验。

    Usage:
        engine = RoEEngine(strict=True)
        config = engine.load_roe("/path/to/roe.txt")
        allowed, reason = engine.check_target("192.168.1.10")
        allowed, needs_approval, reason = engine.is_tool_allowed("nmap")
    """

    # 用于识别 IPv4 / IPv6 的正则
    _IPV4_RE = re.compile(
        r"^(\d{1,3}\.){3}\d{1,3}$"
    )
    _IPV6_RE = re.compile(
        r"^(\[?([0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}]?)$"
        r"|^\[?::1]?$|^\[?([0-9a-fA-F]{1,4}:){1,4}:([0-9]{1,3}\.){3}\d{1,3}]?$"
    )

    def __init__(self, strict: bool = False) -> None:
        """初始化引擎。

        Args:
            strict: 严格模式。当 strict=True 且没有任何 allow/deny 配置时，
                    默认拒绝访问；strict=False 时默认允许。
        """
        self._config: Optional[RoEConfig] = None
        self._loaded: bool = False
        self._strict: bool = strict

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        """是否已经加载过 RoE 文档。"""
        return self._loaded

    @property
    def config(self) -> Optional[RoEConfig]:
        """当前解析后的 RoEConfig 实例，未加载时返回 None。"""
        return self._config

    # ------------------------------------------------------------------
    # RoE 文档解析
    # ------------------------------------------------------------------

    def load_roe(self, file_path: str) -> RoEConfig:
        """从文件加载 RoE 文档，按扩展名自动选择解析器。

        Args:
            file_path: RoE 文件路径，支持 .txt / .md / .yaml / .yml

        Returns:
            解析后的 RoEConfig。文件不存在时返回空配置并标记 _loaded=False。
        """
        path = Path(file_path)
        if not path.exists():
            self._loaded = False
            self._config = RoEConfig()
            return self._config

        content = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()

        if suffix in (".yaml", ".yml"):
            self._config = self.parse_yaml(content)
        elif suffix in (".txt", ".md", ""):
            self._config = self.parse_txt(content)
        else:
            # 默认按纯文本解析
            self._config = self.parse_txt(content)

        self._loaded = True
        return self._config

    def parse_txt(self, content: str) -> RoEConfig:
        """解析纯文本格式的 RoE 文档。

        每行格式：``KEYWORD: value``（不区分大小写）。
        支持 # 开头的注释行与空行。

        Args:
            content: 纯文本内容

        Returns:
            解析后的 RoEConfig
        """
        cfg = RoEConfig()
        rules: List[RoERule] = []

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            # 分割关键字与值，仅分割第一个冒号
            if ":" not in line:
                continue
            keyword, value = line.split(":", 1)
            keyword = keyword.strip().upper()
            value = value.strip()

            if keyword == "CLIENT":
                cfg.client_name = value

            elif keyword == "PROJECT":
                cfg.project_name = value

            elif keyword == "TESTER":
                cfg.tester_name = value

            elif keyword == "EMERGENCY":
                cfg.emergency_contact = value

            elif keyword == "ALLOW IP":
                ips, cidrs = self._parse_ip_list(value)
                cfg.allowed_ips.extend(ips)
                cfg.allowed_cidrs.extend(cidrs)
                for ip in ips:
                    rules.append(RoERule("allow_ip", ip, f"允许IP: {ip}"))
                for cidr in cidrs:
                    rules.append(RoERule("allow_cidr", cidr, f"允许网段: {cidr}"))

            elif keyword == "ALLOW DOMAIN":
                domains = self._parse_domain_list(value)
                cfg.allowed_domains.extend(domains)
                for d in domains:
                    if d.startswith("*."):
                        rules.append(RoERule("allow_wildcard_domain", d, f"允许通配符域名: {d}"))
                    else:
                        rules.append(RoERule("allow_domain", d, f"允许域名: {d}"))

            elif keyword == "DENY IP":
                ips, cidrs = self._parse_ip_list(value)
                cfg.denied_ips.extend(ips)
                cfg.denied_ips.extend(cidrs)
                for ip in ips:
                    rules.append(RoERule("deny_ip", ip, f"禁止IP: {ip}"))

            elif keyword == "DENY DOMAIN":
                domains = self._parse_domain_list(value)
                cfg.denied_domains.extend(domains)
                for d in domains:
                    rules.append(RoERule("deny_domain", d, f"禁止域名: {d}"))

            elif keyword == "DENY TOOL":
                tools = [t.strip() for t in value.split(",") if t.strip()]
                cfg.denied_tools.extend(tools)
                for t in tools:
                    rules.append(RoERule("deny_tool", t, f"禁止工具: {t}"))

            elif keyword == "TIME WINDOW":
                start_dt, end_dt = self._parse_time_window(value)
                cfg.time_window_start = start_dt
                cfg.time_window_end = end_dt
                if start_dt and end_dt:
                    rules.append(RoERule("allow_time", value,
                                         f"时间窗口: {start_dt} ~ {end_dt}"))

            elif keyword == "REQUIRE APPROVAL":
                tools = [t.strip() for t in value.split(",") if t.strip()]
                cfg.require_approval_tools.extend(tools)
                for t in tools:
                    rules.append(RoERule("require_approval", t,
                                         f"需确认工具: {t}"))

        cfg.raw_rules = rules
        return cfg

    def parse_yaml(self, content: str) -> RoEConfig:
        """解析 YAML-like 格式的 RoE 文档。

        使用简单键值解析（逐行处理），不依赖第三方 YAML 库。
        支持的键名与 parse_txt 的关键字语义一致，但使用小写下划线格式。

        Args:
            content: YAML-like 文本内容

        Returns:
            解析后的 RoEConfig
        """
        cfg = RoEConfig()
        rules: List[RoERule] = []

        # 状态机变量，用于处理列表项
        current_key: Optional[str] = None

        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()

            if not stripped or stripped.startswith("#"):
                continue

            # 检测键值对（支持 key: value 格式）
            if ": " in stripped or stripped.endswith(":"):
                # 提取键
                if ": " in stripped:
                    key_part, val_part = stripped.split(": ", 1)
                else:
                    key_part = stripped.rstrip(":")
                    val_part = ""

                key = key_part.strip().lower()
                current_key = key
                value = val_part.strip()

                # 处理可能带引号的值
                value = value.strip("'\"")

                self._apply_yaml_kv(cfg, rules, key, value)

            # 处理列表项（- item）缩进格式
            elif stripped.startswith("-"):
                item = stripped[1:].strip().strip("'\"")
                if current_key and item:
                    self._apply_yaml_list_item(cfg, rules, current_key, item)

        cfg.raw_rules = rules
        return cfg

    # ------------------------------------------------------------------
    # YAML 辅助方法
    # ------------------------------------------------------------------

    def _apply_yaml_kv(self, cfg: RoEConfig, rules: List[RoERule],
                       key: str, value: str) -> None:
        """将 YAML 键值对应用到 RoEConfig。"""
        if key in ("client", "client_name"):
            cfg.client_name = value
        elif key in ("project", "project_name"):
            cfg.project_name = value
        elif key in ("tester", "tester_name"):
            cfg.tester_name = value
        elif key in ("emergency", "emergency_contact"):
            cfg.emergency_contact = value
        elif key == "time_window":
            start_dt, end_dt = self._parse_time_window(value)
            cfg.time_window_start = start_dt
            cfg.time_window_end = end_dt
            if start_dt and end_dt:
                rules.append(RoERule("allow_time", value,
                                     f"时间窗口: {start_dt} ~ {end_dt}"))
        elif key == "allowed_ips":
            ips, cidrs = self._parse_ip_list(value)
            cfg.allowed_ips.extend(ips)
            cfg.allowed_cidrs.extend(cidrs)
        elif key == "allowed_domains":
            domains = self._parse_domain_list(value)
            cfg.allowed_domains.extend(domains)
        elif key == "denied_ips":
            ips, cidrs = self._parse_ip_list(value)
            cfg.denied_ips.extend(ips)
            cfg.denied_ips.extend(cidrs)
        elif key == "denied_domains":
            domains = self._parse_domain_list(value)
            cfg.denied_domains.extend(domains)
        elif key == "denied_tools":
            tools = [t.strip() for t in value.split(",") if t.strip()]
            cfg.denied_tools.extend(tools)
        elif key == "require_approval_tools":
            tools = [t.strip() for t in value.split(",") if t.strip()]
            cfg.require_approval_tools.extend(tools)

    def _apply_yaml_list_item(self, cfg: RoEConfig, rules: List[RoERule],
                              key: str, item: str) -> None:
        """将 YAML 列表项应用到 RoEConfig。"""
        if key in ("allowed_ips", "allow_ip"):
            if "/" in item:
                cfg.allowed_cidrs.append(item)
                rules.append(RoERule("allow_cidr", item, f"允许网段: {item}"))
            else:
                cfg.allowed_ips.append(item)
                rules.append(RoERule("allow_ip", item, f"允许IP: {item}"))
        elif key in ("allowed_domains", "allow_domain"):
            cfg.allowed_domains.append(item)
            if item.startswith("*."):
                rules.append(RoERule("allow_wildcard_domain", item, f"允许通配符域名: {item}"))
            else:
                rules.append(RoERule("allow_domain", item, f"允许域名: {item}"))
        elif key in ("denied_ips", "deny_ip"):
            cfg.denied_ips.append(item)
            rules.append(RoERule("deny_ip", item, f"禁止IP: {item}"))
        elif key in ("denied_domains", "deny_domain"):
            cfg.denied_domains.append(item)
            rules.append(RoERule("deny_domain", item, f"禁止域名: {item}"))
        elif key in ("denied_tools", "deny_tool"):
            cfg.denied_tools.append(item)
            rules.append(RoERule("deny_tool", item, f"禁止工具: {item}"))
        elif key in ("require_approval_tools", "require_approval"):
            cfg.require_approval_tools.append(item)
            rules.append(RoERule("require_approval", item, f"需确认工具: {item}"))

    # ------------------------------------------------------------------
    # 辅助解析方法
    # ------------------------------------------------------------------

    def _parse_ip_list(self, value: str) -> Tuple[List[str], List[str]]:
        """解析逗号分隔的 IP 列表，区分单个 IP 与 CIDR 网段。

        Args:
            value: 逗号分隔的 IP/CIDR 字符串，如 ``'192.168.1.1, 10.0.0.0/24'``

        Returns:
            (ips, cidrs) 元组，ips 为单个 IP 列表，cidrs 为 CIDR 列表
        """
        ips: List[str] = []
        cidrs: List[str] = []
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            if "/" in part:
                cidrs.append(part)
            else:
                ips.append(part)
        return ips, cidrs

    def _parse_domain_list(self, value: str) -> List[str]:
        """解析逗号分隔的域名列表。

        Args:
            value: 逗号分隔的域名字符串

        Returns:
            去空白后的域名列表
        """
        return [d.strip() for d in value.split(",") if d.strip()]

    def _parse_time_window(self, value: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """解析时间窗口字符串。

        支持格式：
            ``YYYY-MM-DD HH:MM to YYYY-MM-DD HH:MM``
            ``YYYY-MM-DD HH:MM:ss to YYYY-MM-DD HH:MM:ss``

        Args:
            value: 时间窗口字符串

        Returns:
            (start_datetime, end_datetime)，解析失败则返回 (None, None)
        """
        # 统一替换多种分隔符
        normalized = value.replace("  ", " ")
        for sep in (" to ", " TO ", " - ", " ~ ", " -> "):
            normalized = normalized.replace(sep, "|", 1)

        if "|" not in normalized:
            return None, None

        start_str, end_str = normalized.split("|", 1)
        start_str = start_str.strip()
        end_str = end_str.strip()

        start_dt = self._str_to_datetime(start_str)
        end_dt = self._str_to_datetime(end_str)
        return start_dt, end_dt

    @staticmethod
    def _str_to_datetime(s: str) -> Optional[datetime]:
        """将日期时间字符串转为 datetime 对象。

        支持的格式：
            - %Y-%m-%d %H:%M
            - %Y-%m-%d %H:%M:%S
            - %Y/%m/%d %H:%M

        Args:
            s: 日期时间字符串

        Returns:
            datetime 对象或 None
        """
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
                    "%Y/%m/%d %H:%M", "%Y/%m/%d %H:%M:%S"):
            try:
                return datetime.strptime(s.strip(), fmt)
            except ValueError:
                continue
        return None

    # ------------------------------------------------------------------
    # 授权校验
    # ------------------------------------------------------------------

    def is_ip_allowed(self, ip: str) -> Tuple[bool, str]:
        """校验单个 IP 是否在授权范围内。

        检查顺序：
        1. 若在 denied_ips 中 → 拒绝
        2. 若在 allowed_ips 中 → 允许
        3. 若在 allowed_cidrs 中 → 允许
        4. 无配置且非严格模式 → 允许
        5. 无配置且严格模式 → 拒绝
        6. 有配置但不在 allow 中 → 拒绝

        Args:
            ip: 待校验的 IP 地址字符串

        Returns:
            (allowed: bool, reason: str)
        """
        cfg = self._config
        if cfg is None:
            return (not self._strict), "未加载RoE配置" if self._strict else "未加载RoE配置，非严格模式默认允许"

        # 1) denied_ips 精确匹配
        if ip in cfg.denied_ips:
            return False, f"IP {ip} 在禁止列表中"

        # 2) allowed_ips 精确匹配
        if ip in cfg.allowed_ips:
            return True, f"IP {ip} 在允许列表中"

        # 3) allowed_cidrs 网段包含检查
        try:
            target = ipaddress.ip_address(ip)
            for cidr_str in cfg.allowed_cidrs:
                try:
                    network = ipaddress.ip_network(cidr_str, strict=False)
                    if target in network:
                        return True, f"IP {ip} 在允许网段 {cidr_str} 内"
                except ValueError:
                    continue
        except ValueError:
            return False, f"IP {ip} 格式无效"

        has_allow_config = cfg.allowed_ips or cfg.allowed_cidrs

        # 4) 无任何 allow 配置
        if not has_allow_config:
            if self._strict:
                return False, "严格模式：未配置允许的IP/CIDR，默认拒绝"
            else:
                return True, "未配置允许的IP/CIDR，非严格模式默认允许"

        # 5) 有配置但不在 allow 中
        return False, f"IP {ip} 不在任何允许的IP或CIDR范围内"

    def is_domain_allowed(self, domain: str) -> Tuple[bool, str]:
        """校验域名是否在授权范围内，支持通配符匹配。

        通配符规则：
        - ``*.example.com`` 匹配 ``sub.example.com``、``a.b.example.com``
        - ``*.example.com`` 不匹配 ``example.com``

        检查顺序：
        1. 若在 denied_domains 中 → 拒绝
        2. 若在 allowed_domains 中精确匹配 → 允许
        3. 若在 allowed_domains 中通配符匹配 → 允许
        4. 无配置且非严格模式 → 允许
        5. 无配置且严格模式 → 拒绝
        6. 有配置但不在 allow 中 → 拒绝

        Args:
            domain: 待校验的域名

        Returns:
            (allowed: bool, reason: str)
        """
        cfg = self._config
        if cfg is None:
            return (not self._strict), "未加载RoE配置" if self._strict else "未加载RoE配置，非严格模式默认允许"

        # 标准化：去掉尾部点号，转小写
        target = domain.rstrip(".").lower()

        # 1) denied_domains 精确匹配
        for deny in cfg.denied_domains:
            if deny.rstrip(".").lower() == target:
                return False, f"域名 {domain} 在禁止列表中"

        # 2) allowed_domains 精确匹配
        for allow in cfg.allowed_domains:
            allow_norm = allow.rstrip(".").lower()
            if not allow_norm.startswith("*."):
                if allow_norm == target:
                    return True, f"域名 {domain} 在允许列表中"

        # 3) allowed_domains 通配符匹配
        for allow in cfg.allowed_domains:
            allow_norm = allow.rstrip(".").lower()
            if allow_norm.startswith("*."):
                suffix = allow_norm[2:]  # 去掉 *. 后的后缀
                if target != suffix and target.endswith("." + suffix):
                    return True, f"域名 {domain} 匹配通配符规则 {allow}"

        has_allow_config = bool(cfg.allowed_domains)

        # 4) 无任何 allow 配置
        if not has_allow_config:
            if self._strict:
                return False, "严格模式：未配置允许的域名，默认拒绝"
            else:
                return True, "未配置允许的域名，非严格模式默认允许"

        # 5) 有配置但不在 allow 中
        return False, f"域名 {domain} 不在任何允许的域名规则中"

    def is_tool_allowed(self, tool_name: str) -> Tuple[bool, bool, str]:
        """校验工具是否允许使用。

        Args:
            tool_name: 工具名称或命令字符串

        Returns:
            (allowed: bool, requires_approval: bool, reason: str)

            - 若在 denied_tools 中 → (False, False, "工具被禁止")
            - 若在 require_approval_tools 中 → (True, True, "需要确认")
            - 否则 → (True, False, "允许")
        """
        cfg = self._config
        if cfg is not None:
            # 检查禁止列表（支持前缀匹配："sqlmap --dump-all" 也禁止 "sqlmap"）
            for denied in cfg.denied_tools:
                if tool_name == denied or tool_name.startswith(denied + " "):
                    return False, False, f"工具 {tool_name} 被禁止（规则: {denied}）"

            # 检查需确认列表
            for req in cfg.require_approval_tools:
                if tool_name == req or tool_name.startswith(req + " "):
                    return True, True, f"工具 {tool_name} 需要人工确认（规则: {req}）"

        return True, False, f"工具 {tool_name} 允许使用"

    def is_time_allowed(self, check_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """校验当前时间是否在授权时间窗口内。

        Args:
            check_time: 待检查的时间，None 则使用系统当前时间

        Returns:
            (allowed: bool, reason: str)
        """
        cfg = self._config
        if cfg is None or (cfg.time_window_start is None and cfg.time_window_end is None):
            return True, "无时间限制"

        now = check_time if check_time is not None else datetime.now()

        if cfg.time_window_start and now < cfg.time_window_start:
            return False, f"超出授权时间窗口（开始时间: {cfg.time_window_start}）"
        if cfg.time_window_end and now > cfg.time_window_end:
            return False, f"超出授权时间窗口（结束时间: {cfg.time_window_end}）"

        return True, f"在时间窗口内（{cfg.time_window_start} ~ {cfg.time_window_end}）"

    def check_target(self, target: str) -> Tuple[bool, str]:
        """自动识别目标类型（IP 或 域名）并进行授权校验。

        使用正则判断：若匹配 IP 格式则调用 ``is_ip_allowed``，否则调用
        ``is_domain_allowed``。

        Args:
            target: 目标字符串（IP 地址或域名）

        Returns:
            (allowed: bool, reason: str)
        """
        target = target.strip()

        # IPv4 检测
        if self._IPV4_RE.match(target):
            return self.is_ip_allowed(target)

        # IPv6 检测
        if self._IPV6_RE.match(target):
            return self.is_ip_allowed(target)

        # 否则按域名处理
        return self.is_domain_allowed(target)

    # ------------------------------------------------------------------
    # 规则管理
    # ------------------------------------------------------------------

    def add_rule(self, rule: RoERule) -> None:
        """动态添加一条 RoE 规则并同步更新配置。

        Args:
            rule: 要添加的 RoERule 实例
        """
        if self._config is None:
            self._config = RoEConfig()

        self._config.raw_rules.append(rule)

        # 同步更新对应列表
        rt = rule.rule_type
        val = rule.value

        if rt == "allow_ip":
            if val not in self._config.allowed_ips:
                self._config.allowed_ips.append(val)
        elif rt == "allow_cidr":
            if val not in self._config.allowed_cidrs:
                self._config.allowed_cidrs.append(val)
        elif rt in ("allow_domain", "allow_wildcard_domain"):
            if val not in self._config.allowed_domains:
                self._config.allowed_domains.append(val)
        elif rt == "deny_ip":
            if val not in self._config.denied_ips:
                self._config.denied_ips.append(val)
        elif rt == "deny_domain":
            if val not in self._config.denied_domains:
                self._config.denied_domains.append(val)
        elif rt == "deny_tool":
            if val not in self._config.denied_tools:
                self._config.denied_tools.append(val)
        elif rt == "require_approval":
            if val not in self._config.require_approval_tools:
                self._config.require_approval_tools.append(val)

    def remove_rule(self, rule_type: str, value: str) -> bool:
        """按类型和值删除规则。

        Args:
            rule_type: 规则类型
            value: 规则值

        Returns:
            是否成功删除
        """
        if self._config is None:
            return False

        removed = False
        self._config.raw_rules = [
            r for r in self._config.raw_rules
            if not (r.rule_type == rule_type and r.value == value) or not (removed := True)
        ]

        # 同步清理各列表
        if rule_type == "allow_ip" and value in self._config.allowed_ips:
            self._config.allowed_ips.remove(value)
            removed = True
        elif rule_type == "allow_cidr" and value in self._config.allowed_cidrs:
            self._config.allowed_cidrs.remove(value)
            removed = True
        elif rule_type in ("allow_domain", "allow_wildcard_domain") and value in self._config.allowed_domains:
            self._config.allowed_domains.remove(value)
            removed = True
        elif rule_type == "deny_ip" and value in self._config.denied_ips:
            self._config.denied_ips.remove(value)
            removed = True
        elif rule_type == "deny_domain" and value in self._config.denied_domains:
            self._config.denied_domains.remove(value)
            removed = True
        elif rule_type == "deny_tool" and value in self._config.denied_tools:
            self._config.denied_tools.remove(value)
            removed = True
        elif rule_type == "require_approval" and value in self._config.require_approval_tools:
            self._config.require_approval_tools.remove(value)
            removed = True

        return removed

    def get_config_summary(self) -> str:
        """生成当前 RoE 配置的多行文本摘要。

        Returns:
            可读的摘要字符串
        """
        cfg = self._config
        if cfg is None:
            return "RoE配置: 未加载"

        name = cfg.client_name or "未指定客户"
        proj = cfg.project_name or "未指定项目"

        wildcard_count = sum(1 for d in cfg.allowed_domains if d.startswith("*."))
        normal_domain_count = len(cfg.allowed_domains) - wildcard_count

        time_str = "无限制"
        if cfg.time_window_start and cfg.time_window_end:
            time_str = f"{cfg.time_window_start.strftime('%Y-%m-%d %H:%M')} ~ {cfg.time_window_end.strftime('%Y-%m-%d %H:%M')}"
        elif cfg.time_window_start:
            time_str = f"从 {cfg.time_window_start.strftime('%Y-%m-%d %H:%M')} 开始"
        elif cfg.time_window_end:
            time_str = f"直到 {cfg.time_window_end.strftime('%Y-%m-%d %H:%M')}"

        lines = [
            f"RoE配置: {name} - {proj}",
            f"授权IP: {len(cfg.allowed_ips)}个 + {len(cfg.allowed_cidrs)}个CIDR",
            f"授权域名: {normal_domain_count}个 (含{wildcard_count}个通配符)",
            f"禁止IP: {len(cfg.denied_ips)}个",
            f"禁止域名: {len(cfg.denied_domains)}个",
            f"禁止工具: {', '.join(cfg.denied_tools) if cfg.denied_tools else '无'}",
            f"时间窗口: {time_str}",
            f"需确认工具: {', '.join(cfg.require_approval_tools) if cfg.require_approval_tools else '无'}",
            f"紧急联系: {cfg.emergency_contact or '未设置'}",
            f"测试人员: {cfg.tester_name or '未设置'}",
        ]
        return "\n".join(lines)
