"""
scope_enforcer.py — 范围强制校验器

PentestAgent M4 Audit Guard 模块的核心拦截组件。
在执行渗透测试操作前，对目标/工具/时间窗口进行多维校验，
自动拦截未授权操作并生成审计记录。

用法::
    enforcer = ScopeEnforcer(roe, logger)
    result = await enforcer.validate("端口扫描", "192.168.1.1", tool="nmap")
    if result["blocked"]:
        raise ScopeBlockedException(target, result["reason"], "端口扫描")
"""
import re, asyncio, ipaddress, inspect, functools
from datetime import datetime
from typing import Dict, List, Optional, Callable
from urllib.parse import urlparse
from .roe_engine import RoEEngine
from .audit_logger import AuditLogger

class ScopeBlockedException(Exception):
    """操作被范围强制拦截时抛出"""

    def __init__(self, target: str, reason: str, action: str = ""):
        """初始化拦截异常

        Args:
            target: 被拦截的目标
            reason: 拦截原因
            action: 被拦截的操作名称
        """
        self.target = target
        self.reason = reason
        self.action = action
        super().__init__(str(self))

    def __str__(self) -> str:
        """返回中文拦截描述字符串"""
        return f"[范围拦截] 操作'{self.action}'被阻断: {self.reason} (目标: {self.target})"


class ScopeEnforcer:
    """范围强制校验器 — 在执行前拦截未授权操作

    对每次操作进行前置校验，覆盖目标IP/域名合法性、工具授权、
    时间窗口合规性及.gov/.edu/.mil自动拦截。支持同步与异步双模式。

    Attributes:
        _roe: RoEEngine 规则引擎; _audit: AuditLogger 审计日志
        _auto_block_gov: 自动拦截政府/教育/军事域名
        _strict_mode: 严格模式（异常视为阻断）
        _blocked_count: 累计拦截; _allowed_count: 累计放行
        _approval_required_count: 累计需审批
        _blocked_log: 被拦截记录列表（倒序，最新在前）
    """

    # 正则预编译
    _IP_RE = re.compile(r"\d+\.\d+\.\d+\.\d+")
    _CIDR_RE = re.compile(r"\d+\.\d+\.\d+\.\d+/\d+")
    _DOMAIN_RE = re.compile(r"[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}")
    _URL_RE = re.compile(r"https?://[^\s]+")
    _GOV_RE = re.compile(r"(\.gov\.?|\.edu\.?|\.mil\.?|\.gouv\.?)$", re.IGNORECASE)
    _PRIVATE_NETWORKS = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    ]

    def __init__(
        self, roe_engine: RoEEngine, audit_logger: AuditLogger,
        auto_block_gov: bool = True, strict_mode: bool = False,
    ):
        """初始化范围强制校验器

        Args:
            roe_engine: RoEEngine 规则引擎实例
            audit_logger: AuditLogger 审计日志实例
            auto_block_gov: 是否自动拦截政府/教育/军事域名
            strict_mode: 严格模式（异常视为阻断）
        """
        self._roe = roe_engine
        self._audit = audit_logger
        self._auto_block_gov = auto_block_gov
        self._strict_mode = strict_mode
        self._blocked_count = 0
        self._allowed_count = 0
        self._approval_required_count = 0
        self._blocked_log: List[dict] = []

    # --- 核心校验 ---

    async def validate(
        self, action: str, target: str, tool: str = "", command: str = ""
    ) -> dict:
        """异步版本 — 对指定操作进行完整范围校验

        校验流程: target空→本地操作放行; 提取IP/域名/URL;
        .gov/.edu/.mil自动拦截; RoEEngine.check_target()规则判定;
        工具授权检查; 时间窗口检查; 记录审计日志; 更新计数。

        Args:
            action: 操作描述，如"端口扫描"
            target: 目标字符串，可包含IP/域名/URL
            tool: 使用的工具名称，如"nmap"
            command: 原始命令字符串（用于审计）

        Returns:
            {"allowed": bool, "blocked": bool, "reason": str,
             "requires_approval": bool, "auto_blocked": bool}
        """
        result = self._validate_core(action, target, tool, command)
        if asyncio.isfuture(result) or inspect.isawaitable(result):
            return await result
        return result

    def validate_sync(
        self, action: str, target: str, tool: str = "", command: str = ""
    ) -> dict:
        """同步版本 — 对指定操作进行完整范围校验

        逻辑与 :meth:`validate` 完全一致，同步方式执行。
        适用于非异步上下文（脚本入口、传统回调等）。

        Args/Returns: 同 :meth:`validate`
        """
        result = self._validate_core(action, target, tool, command)
        if asyncio.isfuture(result) or inspect.isawaitable(result):
            return self._run_sync(result)
        return result

    def _validate_core(self, action: str, target: str, tool: str, command: str) -> dict:
        """校验核心逻辑（同步实现，供validate/validate_sync共用）"""
        # a) 空目标 → 本地操作放行
        if not target or not target.strip():
            self._allowed_count += 1
            return {"allowed": True, "blocked": False, "reason": "本地操作",
                    "requires_approval": False, "auto_blocked": False}
        target = target.strip()
        extracted = self.extract_targets(target)
        all_targets = extracted["ips"] + extracted["domains"] + extracted["urls"]
        if not all_targets:
            all_targets = [target]
        # c) .gov/.edu/.mil 自动拦截
        if self._auto_block_gov:
            for domain in extracted["domains"]:
                if self._is_gov_domain(domain):
                    return self._block(action, target, f"自动拦截政府/教育/军事域名: {domain}", tool, command, True)
            for url in extracted["urls"]:
                host = urlparse(url).hostname
                if host and self._is_gov_domain(host):
                    return self._block(action, target, f"自动拦截政府/教育/军事URL: {url}", tool, command, True)
        # d) RoEEngine.check_target() 逐个检查
        for t in all_targets:
            try:
                allowed, reason = self._roe.check_target(t)
            except Exception as exc:
                if self._strict_mode:
                    return self._block(action, target, f"规则引擎异常(strict_mode): {exc}", tool, command)
                continue
            if not allowed:
                return self._block(action, target, f"目标未授权: {reason}", tool, command)
        # e) 工具授权检查
        requires_approval = False
        if tool:
            try:
                tool_allowed, requires_approval, tool_reason = self._roe.is_tool_allowed(tool)
            except Exception as exc:
                if self._strict_mode:
                    return self._block(action, target, f"工具检查异常(strict_mode): {exc}", tool, command)
                tool_allowed = True
            if not tool_allowed:
                return self._block(action, target, f"工具未授权: {tool_reason}", tool, command)
        # f) 时间窗口检查
        try:
            time_allowed, time_reason = self._roe.is_time_allowed(datetime.now())
        except Exception as exc:
            if self._strict_mode:
                return self._block(action, target, f"时间检查异常(strict_mode): {exc}", tool, command)
            time_allowed = True
        if not time_allowed:
            return self._block(action, target, f"时间窗口限制: {time_reason}", tool, command)
        # g) 审计日志 + h) 更新计数
        self._allowed_count += 1
        self._audit.log_command(command or action, target, output_preview="ALLOWED: 范围校验通过")
        return {"allowed": True, "blocked": False, "reason": "范围校验通过",
                "requires_approval": requires_approval, "auto_blocked": False}

    def _block(self, action: str, target: str, reason: str,
               tool: str, command: str, auto_blocked: bool = False) -> dict:
        """统一处理拦截逻辑：更新计数、写入审计日志、返回阻断结果"""
        self._blocked_count += 1
        entry = {"timestamp": datetime.now().isoformat(), "action": action,
                 "target": target, "reason": reason, "auto_blocked": auto_blocked}
        self._blocked_log.insert(0, entry)
        self._audit.log_command(command or action, target, output_preview=f"BLOCKED: {reason}")
        return {"allowed": False, "blocked": True, "reason": reason,
                "requires_approval": False, "auto_blocked": auto_blocked}

    def _run_sync(self, awaitable):
        """将awaitable同步执行并返回结果"""
        try:
            loop = asyncio.get_running_loop()
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(awaitable)
            finally:
                new_loop.close()
        except RuntimeError:
            return asyncio.run(awaitable)

    # --- 目标解析 ---

    def extract_targets(self, text: str) -> dict:
        """从文本中提取所有潜在目标实体

        Args:
            text: 原始目标字符串，如 "nmap -sS 192.168.1.1 example.com"

        Returns:
            {"ips": [...], "domains": [...], "urls": [...]}
        """
        def _unique(seq):
            seen = set()
            return [x for x in seq if not (x in seen or seen.add(x))]
        return {
            "ips": _unique(self._IP_RE.findall(text) + self._CIDR_RE.findall(text)),
            "domains": _unique(self._DOMAIN_RE.findall(text)),
            "urls": _unique(self._URL_RE.findall(text)),
        }

    def _is_gov_domain(self, domain: str) -> bool:
        """检查是否为政府/教育/军事机构域名（.gov/.edu/.mil/.gouv及其子域）

        Args:
            domain: 域名字符串，如 "state.gov"

        Returns: True 若属于政府/教育/军事域名
        """
        return bool(domain and self._GOV_RE.search(domain.lower()))

    def _is_private_ip(self, ip: str) -> bool:
        """检查IPv4是否为RFC1918私有地址（10/8, 172.16/12, 192.168/16）

        Args:
            ip: IPv4地址字符串，如 "192.168.1.1"

        Returns: True 若为私有地址
        """
        try:
            addr = ipaddress.ip_address(ip)
            return any(addr in net for net in self._PRIVATE_NETWORKS)
        except ValueError:
            return False

    # --- 拦截记录 ---

    def get_stats(self) -> dict:
        """返回范围校验统计信息

        Returns: {"allowed": int, "blocked": int,
                  "auto_blocked": int, "approval_required": int}
        """
        auto_blocked = sum(1 for e in self._blocked_log if e.get("auto_blocked"))
        return {"allowed": self._allowed_count, "blocked": self._blocked_count,
                "auto_blocked": auto_blocked, "approval_required": self._approval_required_count}

    def get_blocked_log(self, limit: int = 50) -> List[dict]:
        """获取最近被拦截的记录（按时间倒序）

        Args:
            limit: 最大返回条数，默认50

        Returns: 被拦截记录列表，每条含timestamp/action/target/reason/auto_blocked
        """
        return self._blocked_log[:limit]

    # --- 装饰器 ---

    @staticmethod
    def enforce(action_name: str = ""):
        """范围强制装饰器 — 自动校验被装饰函数的target参数

        同时支持同步与异步函数。执行前调用validate/validate_sync，
        阻断时抛出ScopeBlockedException。要求被装饰函数签名包含
        ``enforcer: ScopeEnforcer`` 参数。

        Args:
            action_name: 操作名称，为空时自动使用函数名

        Returns: 装饰器函数

        Raises:
            ScopeBlockedException: 操作被阻断时
            RuntimeError: 未找到ScopeEnforcer参数时

        用法::
            @ScopeEnforcer.enforce(action_name="端口扫描")
            async def port_scan(target: str, enforcer: ScopeEnforcer): ...
            @ScopeEnforcer.enforce()  # action_name 自动为 "dir_brute"
            def dir_brute(target: str, enforcer: ScopeEnforcer): ...
        """
        def decorator(func: Callable) -> Callable:
            sig = inspect.signature(func)
            _action = action_name or func.__name__

            def _extract_enforcer_and_target(args, kwargs):
                """从参数中提取enforcer和target"""
                bound = sig.bind_partial(*args, **kwargs)
                enforcer = bound.arguments.get("enforcer")
                target = bound.arguments.get("target", "")
                for arg in args:
                    if isinstance(arg, ScopeEnforcer) and enforcer is None:
                        enforcer = arg
                    elif isinstance(arg, str) and not target:
                        target = arg
                if enforcer is None:
                    raise RuntimeError(
                        "@enforce装饰器要求函数签名中包含ScopeEnforcer实例"
                        "（参数名'enforcer'）")
                return enforcer, target

            def _handle_result(result: dict, enforcer: ScopeEnforcer, target: str):
                """处理校验结果：阻断/审批/放行"""
                if result["blocked"]:
                    enforcer._audit.log_command(
                        _action, target, output_preview=f"BLOCKED_DECORATOR: {result['reason']}")
                    raise ScopeBlockedException(target, result["reason"], _action)
                if result.get("requires_approval"):
                    enforcer._approval_required_count += 1
                    enforcer._audit.log_command(
                        _action, target, output_preview=f"APPROVAL_REQUIRED: {result['reason']}")

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                enforcer, target = _extract_enforcer_and_target(args, kwargs)
                result = await enforcer.validate(_action, target)
                _handle_result(result, enforcer, target)
                return await func(*args, **kwargs)

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                enforcer, target = _extract_enforcer_and_target(args, kwargs)
                result = enforcer.validate_sync(_action, target)
                _handle_result(result, enforcer, target)
                return func(*args, **kwargs)

            return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper

        return decorator
