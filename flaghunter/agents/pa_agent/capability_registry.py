"""Capability primitives and degradation-aware implementation routing."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from ...tools.tool_guard import ToolGuard, ToolStatus


Quality = Literal["high", "medium", "low"]
DecisionType = Literal["use_best", "degrade", "install", "unavailable"]
ToolDecisionType = Literal["approved", "degrade", "install", "unavailable"]

_SOFT_FALLBACK_MAP = {
    "sqlmap": "manual_sqli_payload",
    "nmap": "http_request",
    "dirb": "manual_path_enumeration",
    "gobuster": "manual_path_enumeration",
    "burpsuite": "http_request",
    "burp": "http_request",
}
_INTERNAL_ALWAYS_AVAILABLE = {
    "http_request",
    "browser",
    "terminal",
    "manual_sqli_payload",
    "manual_path_enumeration",
    "collector_server",
}
_DYNAMIC_INTERNAL_TOOLS = {"http_request", "browser", "terminal"}


@dataclass(slots=True)
class CapabilityImplementation:
    method: str
    cost: int
    quality: Quality
    tool_names: list[str] = field(default_factory=list)
    available: bool = False
    requires_install: bool = False
    install_command: str | None = None
    last_checked: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CapabilityPrimitive:
    name: str
    description: str
    implementations: list[CapabilityImplementation] = field(default_factory=list)

    def best_available(self) -> CapabilityImplementation | None:
        available = [item for item in self.implementations if item.available]
        if not available:
            return None
        quality_rank = {"high": 0, "medium": 1, "low": 2}
        return min(available, key=lambda item: (item.cost, quality_rank[item.quality]))

    def can_degrade(self) -> bool:
        return self.best_available() is not None

    def installable_methods(self) -> list[CapabilityImplementation]:
        return [
            item
            for item in self.implementations
            if not item.available and item.requires_install
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "best_available": (
                self.best_available().to_dict() if self.best_available() is not None else None
            ),
            "implementations": [item.to_dict() for item in self.implementations],
        }


@dataclass(slots=True)
class CapabilityRouteDecision:
    primitive: str
    decision_type: DecisionType
    best_available: CapabilityImplementation | None = None
    install_candidates: list[CapabilityImplementation] = field(default_factory=list)
    missing_tools: dict[str, ToolStatus] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "primitive": self.primitive,
            "decision_type": self.decision_type,
            "best_available": (
                self.best_available.to_dict() if self.best_available is not None else None
            ),
            "install_candidates": [item.to_dict() for item in self.install_candidates],
            "missing_tools": {
                name: status.to_dict() for name, status in self.missing_tools.items()
            },
            "reason": self.reason,
        }


@dataclass(slots=True)
class CapabilityEntry:
    tool_name: str
    is_available: bool
    health_state: Literal["healthy", "degraded", "down"]
    last_check_ts: float
    fallback_tool: str | None = None
    install_command: str | None = None
    requires_user_confirm: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ToolRequestDecision:
    tool_name: str
    decision_type: ToolDecisionType
    reason: str
    fallback_tool: str | None = None
    install_command: str | None = None
    requires_user_confirm: bool = True
    entry: CapabilityEntry | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "decision_type": self.decision_type,
            "reason": self.reason,
            "fallback_tool": self.fallback_tool,
            "install_command": self.install_command,
            "requires_user_confirm": self.requires_user_confirm,
            "entry": self.entry.to_dict() if self.entry is not None else None,
        }


@dataclass(slots=True)
class CapabilityRegistry:
    primitives: dict[str, CapabilityPrimitive]
    tool_guard: ToolGuard
    collector_port: int = 7777
    last_full_check: float = 0.0
    capability_table: dict[str, CapabilityEntry] = field(default_factory=dict)
    runtime_tool_statuses: dict[str, ToolStatus] = field(default_factory=dict)
    runtime_tool_details: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def build_default(
        cls,
        *,
        runtime=None,
        tool_guard: ToolGuard | None = None,
        collector_port: int = 7777,
    ) -> "CapabilityRegistry":
        guard = tool_guard or ToolGuard(runtime=runtime)
        return cls(
            primitives={
                "http_request_basic": CapabilityPrimitive(
                    name="http_request_basic",
                    description="基础 HTTP 请求能力",
                    implementations=[
                        CapabilityImplementation(
                            method="requests_via_runtime",
                            cost=1,
                            quality="high",
                            tool_names=["http_request"],
                            requires_install=True,
                        ),
                        CapabilityImplementation(
                            method="curl_subprocess",
                            cost=2,
                            quality="medium",
                            tool_names=["terminal", "curl"],
                            requires_install=True,
                        ),
                    ],
                ),
                "http_request_browser": CapabilityPrimitive(
                    name="http_request_browser",
                    description="浏览器渲染请求能力",
                    implementations=[
                        CapabilityImplementation(
                            method="playwright_browser",
                            cost=3,
                            quality="high",
                            tool_names=["browser"],
                            requires_install=True,
                        )
                    ],
                ),
                "sql_injection_test": CapabilityPrimitive(
                    name="sql_injection_test",
                    description="SQL 注入探测能力",
                    implementations=[
                        CapabilityImplementation(
                            method="sqlmap",
                            cost=2,
                            quality="high",
                            tool_names=["sqlmap"],
                            requires_install=True,
                        ),
                        CapabilityImplementation(
                            method="manual_payload_via_requests",
                            cost=4,
                            quality="medium",
                            tool_names=["http_request"],
                            requires_install=True,
                        ),
                    ],
                ),
                "source_download": CapabilityPrimitive(
                    name="source_download",
                    description="下载并分析源码包",
                    implementations=[
                        CapabilityImplementation(
                            method="requests_plus_zipfile",
                            cost=1,
                            quality="high",
                            tool_names=["http_request"],
                            requires_install=True,
                        ),
                        CapabilityImplementation(
                            method="curl_plus_archive_tools",
                            cost=3,
                            quality="medium",
                            tool_names=["terminal", "curl"],
                            requires_install=True,
                        ),
                    ],
                ),
                "js_execution_in_context": CapabilityPrimitive(
                    name="js_execution_in_context",
                    description="在目标上下文执行 JS",
                    implementations=[
                        CapabilityImplementation(
                            method="playwright_evaluate",
                            cost=3,
                            quality="high",
                            tool_names=["browser"],
                            requires_install=True,
                        )
                    ],
                ),
                "callback_listener": CapabilityPrimitive(
                    name="callback_listener",
                    description="本地监听器/回调接收能力",
                    implementations=[
                        CapabilityImplementation(
                            method="collector_server",
                            cost=1,
                            quality="high",
                            tool_names=[],
                            requires_install=False,
                        )
                    ],
                ),
                "php_deserialization_test": CapabilityPrimitive(
                    name="php_deserialization_test",
                    description="PHP 反序列化 payload 投放",
                    implementations=[
                        CapabilityImplementation(
                            method="manual_payload",
                            cost=2,
                            quality="high",
                            tool_names=["http_request"],
                            requires_install=True,
                        )
                    ],
                ),
                "directory_enumeration": CapabilityPrimitive(
                    name="directory_enumeration",
                    description="目录爆破 / 手工枚举能力",
                    implementations=[
                        CapabilityImplementation(
                            method="ffuf",
                            cost=2,
                            quality="high",
                            tool_names=["ffuf"],
                            requires_install=True,
                        ),
                        CapabilityImplementation(
                            method="manual_wordlist_requests",
                            cost=4,
                            quality="medium",
                            tool_names=["http_request"],
                            requires_install=True,
                        ),
                    ],
                ),
                "xss_scanning": CapabilityPrimitive(
                    name="xss_scanning",
                    description="XSS 漏洞扫描能力",
                    implementations=[
                        CapabilityImplementation(
                            method="dalfox",
                            cost=2,
                            quality="high",
                            tool_names=["dalfox"],
                            requires_install=True,
                        ),
                        CapabilityImplementation(
                            method="manual_xss_payload",
                            cost=4,
                            quality="medium",
                            tool_names=["browser", "http_request"],
                            requires_install=True,
                        ),
                    ],
                ),
                "endpoint_crawling": CapabilityPrimitive(
                    name="endpoint_crawling",
                    description="Web 端点爬取与发现能力",
                    implementations=[
                        CapabilityImplementation(
                            method="katana",
                            cost=2,
                            quality="high",
                            tool_names=["katana"],
                            requires_install=True,
                        ),
                        CapabilityImplementation(
                            method="browser_link_extraction",
                            cost=3,
                            quality="medium",
                            tool_names=["browser"],
                            requires_install=True,
                        ),
                    ],
                ),
                "url_history_discovery": CapabilityPrimitive(
                    name="url_history_discovery",
                    description="历史 URL 发现与回收能力",
                    implementations=[
                        CapabilityImplementation(
                            method="gau",
                            cost=2,
                            quality="high",
                            tool_names=["gau"],
                            requires_install=True,
                        ),
                        CapabilityImplementation(
                            method="manual_archive_search",
                            cost=5,
                            quality="low",
                            tool_names=["http_request", "web_search"],
                            requires_install=True,
                        ),
                    ],
                ),
                "jwt_testing": CapabilityPrimitive(
                    name="jwt_testing",
                    description="JWT 安全测试能力（算法混淆、弱密钥、篡改）",
                    implementations=[
                        CapabilityImplementation(
                            method="manual_jwt_payload",
                            cost=2,
                            quality="high",
                            tool_names=["http_request"],
                            requires_install=True,
                        ),
                    ],
                ),
                "nosql_injection_test": CapabilityPrimitive(
                    name="nosql_injection_test",
                    description="NoSQL 注入探测能力",
                    implementations=[
                        CapabilityImplementation(
                            method="manual_nosql_payload",
                            cost=3,
                            quality="high",
                            tool_names=["http_request"],
                            requires_install=True,
                        ),
                    ],
                ),
            },
            tool_guard=guard,
            collector_port=collector_port,
        )

    @classmethod
    def for_testing(
        cls,
        spec: dict[str, list[dict[str, Any]]],
        *,
        runtime=None,
        tool_guard: ToolGuard | None = None,
        collector_port: int = 7777,
    ) -> "CapabilityRegistry":
        guard = tool_guard or ToolGuard(runtime=runtime)
        primitives: dict[str, CapabilityPrimitive] = {}
        for primitive_name, impl_specs in spec.items():
            primitives[primitive_name] = CapabilityPrimitive(
                name=primitive_name,
                description=f"testing:{primitive_name}",
                implementations=[
                    CapabilityImplementation(
                        method=str(item["method"]),
                        cost=int(item.get("cost", 1)),
                        quality=item.get("quality", "high"),
                        tool_names=list(item.get("tool_names", [])),
                        available=bool(item.get("available", False)),
                        requires_install=bool(item.get("requires_install", False)),
                        install_command=item.get("install_command"),
                    )
                    for item in impl_specs
                ],
            )
        return cls(primitives=primitives, tool_guard=guard, collector_port=collector_port)

    async def full_check(self) -> "CapabilityRegistry":
        await self._collect_runtime_probes()
        for primitive in self.primitives.values():
            for implementation in primitive.implementations:
                self._refresh_implementation(implementation)
        self._refresh_capability_table()
        self.last_full_check = time.time()
        return self

    def get(self, primitive_name: str) -> CapabilityPrimitive | None:
        return self.primitives.get(str(primitive_name or "").strip())

    def best_available(self, primitive_name: str) -> CapabilityImplementation | None:
        primitive = self.get(primitive_name)
        if primitive is None:
            return None
        return primitive.best_available()

    def describe_choice(self, primitive_name: str) -> dict[str, Any]:
        decision = self.resolve_execution_route(primitive_name)
        best = decision.best_available
        return {
            "primitive": primitive_name,
            "available": best is not None,
            "implementation": best.method if best is not None else None,
            "quality": best.quality if best is not None else None,
            "degraded": bool(best is not None and best.quality != "high"),
            "decision_type": decision.decision_type,
            "reason": decision.reason,
        }

    def resolve_execution_route(self, primitive_name: str) -> CapabilityRouteDecision:
        """Input: primitive 名称；Output: use_best/degrade/install/unavailable 决策；Success: 严格按能力判定树返回单一路径；Failure: RecoveryController/上层调度负责处理 install 或 stop。"""
        primitive = self.get(primitive_name)
        if primitive is None:
            return CapabilityRouteDecision(
                primitive=primitive_name,
                decision_type="unavailable",
                reason="unknown primitive",
            )

        best = primitive.best_available()
        install_candidates = primitive.installable_methods()
        missing_tools = self._missing_tools_for_implementations(install_candidates)

        if best is not None:
            if best.quality == "high":
                return CapabilityRouteDecision(
                    primitive=primitive_name,
                    decision_type="use_best",
                    best_available=best,
                    install_candidates=install_candidates,
                    missing_tools=missing_tools,
                    reason="best available implementation is high quality",
                )
            return CapabilityRouteDecision(
                primitive=primitive_name,
                decision_type="degrade",
                best_available=best,
                install_candidates=install_candidates,
                missing_tools=missing_tools,
                reason="degradation path available; per policy it takes priority over install",
            )

        if install_candidates:
            return CapabilityRouteDecision(
                primitive=primitive_name,
                decision_type="install",
                install_candidates=install_candidates,
                missing_tools=missing_tools,
                reason="no available implementation; installable implementations exist",
            )

        return CapabilityRouteDecision(
            primitive=primitive_name,
            decision_type="unavailable",
            install_candidates=[],
            missing_tools={},
            reason="no available implementation and no installable fallback",
        )

    def missing_tools_for(self, primitive_name: str) -> dict[str, ToolStatus]:
        primitive = self.get(primitive_name)
        if primitive is None:
            return {}
        return self._missing_tools_for_implementations(primitive.installable_methods())

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_full_check": self.last_full_check,
            "primitives": {
                name: primitive.to_dict() for name, primitive in self.primitives.items()
            },
            "capability_table": {
                name: entry.to_dict() for name, entry in self.capability_table.items()
            },
        }

    def resolve_tool_request(
        self,
        tool_name: str,
        *,
        auto_install_enabled: bool = False,
    ) -> ToolRequestDecision:
        normalized = str(tool_name or "").strip().lower()
        if not normalized:
            return ToolRequestDecision(
                tool_name="",
                decision_type="unavailable",
                reason="empty tool request",
            )

        entry = self.capability_table.get(normalized) or self._build_capability_entry(normalized)
        self.capability_table[normalized] = entry

        if entry.is_available and entry.health_state == "healthy":
            return ToolRequestDecision(
                tool_name=normalized,
                decision_type="approved",
                reason=f"{normalized} is available",
                fallback_tool=entry.fallback_tool,
                install_command=entry.install_command,
                requires_user_confirm=entry.requires_user_confirm,
                entry=entry,
            )

        if entry.fallback_tool:
            return ToolRequestDecision(
                tool_name=normalized,
                decision_type="degrade",
                reason=f"{normalized} unavailable; degrade to {entry.fallback_tool}",
                fallback_tool=entry.fallback_tool,
                install_command=entry.install_command,
                requires_user_confirm=entry.requires_user_confirm,
                entry=entry,
            )

        if entry.install_command and auto_install_enabled:
            return ToolRequestDecision(
                tool_name=normalized,
                decision_type="install",
                reason=f"{normalized} unavailable; install path allowed",
                install_command=entry.install_command,
                requires_user_confirm=entry.requires_user_confirm,
                entry=entry,
            )

        if entry.install_command:
            return ToolRequestDecision(
                tool_name=normalized,
                decision_type="install",
                reason=f"{normalized} unavailable; install required",
                install_command=entry.install_command,
                requires_user_confirm=entry.requires_user_confirm,
                entry=entry,
            )

        return ToolRequestDecision(
            tool_name=normalized,
            decision_type="unavailable",
            reason=f"{normalized} unavailable with no fallback",
            entry=entry,
        )

    def _refresh_implementation(self, implementation: CapabilityImplementation) -> None:
        implementation.last_checked = time.time()
        if implementation.method == "collector_server":
            implementation.available = self.collector_port > 0
            implementation.details = {"collector_port": self.collector_port}
            return

        details: dict[str, Any] = {}
        available = True
        for tool_name in implementation.tool_names:
            status = self._tool_status(tool_name)
            details[tool_name] = status.to_dict()
            if tool_name == "browser" and tool_name in self.runtime_tool_details:
                details[tool_name]["runtime_probe"] = dict(
                    self.runtime_tool_details[tool_name]
                )
            if not status.available:
                available = False
                if implementation.install_command is None:
                    implementation.install_command = self.tool_guard.suggest_install(tool_name)
        browser_probe = self.runtime_tool_details.get("browser") or {}
        if implementation.method == "playwright_browser" and browser_probe:
            available = available and bool(browser_probe.get("rendered_dom"))
        if implementation.method == "playwright_evaluate" and browser_probe:
            available = available and bool(browser_probe.get("js_execution"))
        implementation.available = available
        implementation.details = details

    def _refresh_capability_table(self) -> None:
        tool_names: set[str] = set(_INTERNAL_ALWAYS_AVAILABLE)
        for primitive in self.primitives.values():
            for implementation in primitive.implementations:
                tool_names.update(
                    str(tool_name or "").strip().lower()
                    for tool_name in implementation.tool_names
                    if str(tool_name or "").strip()
                )
        tool_names.update(_SOFT_FALLBACK_MAP.keys())

        refreshed: dict[str, CapabilityEntry] = {}
        for tool_name in tool_names:
            refreshed[tool_name] = self._build_capability_entry(tool_name)
        self.capability_table = refreshed

    def _build_capability_entry(self, tool_name: str) -> CapabilityEntry:
        normalized = str(tool_name or "").strip().lower()
        now = time.time()
        fallback = _SOFT_FALLBACK_MAP.get(normalized)
        if normalized in _INTERNAL_ALWAYS_AVAILABLE and normalized not in _DYNAMIC_INTERNAL_TOOLS:
            return CapabilityEntry(
                tool_name=normalized,
                is_available=True,
                health_state="healthy",
                last_check_ts=now,
                fallback_tool=fallback,
                install_command=None,
                requires_user_confirm=False,
            )

        status = self.tool_guard.check(normalized)
        probe = self.runtime_tool_details.get(normalized) or {}
        if normalized in self.runtime_tool_statuses:
            status = self.runtime_tool_statuses[normalized]
        install_command = self.tool_guard.suggest_install(normalized)
        health_state: Literal["healthy", "degraded", "down"]
        if status.available:
            if normalized == "browser" and probe and not bool(probe.get("rendered_dom")):
                health_state = "degraded"
            else:
                health_state = "healthy"
        else:
            health_state = "down"
        return CapabilityEntry(
            tool_name=normalized,
            is_available=bool(status.available),
            health_state=health_state,
            last_check_ts=now,
            fallback_tool=fallback,
            install_command=install_command,
            requires_user_confirm=True,
        )

    def _missing_tools_for_implementations(
        self, implementations: list[CapabilityImplementation]
    ) -> dict[str, ToolStatus]:
        missing: dict[str, ToolStatus] = {}
        for implementation in implementations:
            for tool_name in implementation.tool_names:
                status = self._tool_status(tool_name)
                if not status.available:
                    missing[tool_name] = status
        return missing

    async def _collect_runtime_probes(self) -> None:
        self.runtime_tool_statuses = {}
        self.runtime_tool_details = {}
        runtime = getattr(self.tool_guard, "runtime", None)
        if runtime is None or not hasattr(runtime, "browser_action"):
            return
        try:
            probe = await runtime.browser_action("diagnose", timeout=5)
        except Exception as exc:
            probe = {"available": False, "error": str(exc)}
        if not isinstance(probe, dict):
            return
        available = bool(probe.get("available")) and not probe.get("error")
        self.runtime_tool_statuses["browser"] = ToolStatus(
            available=available,
            path=str(probe.get("path") or "runtime.browser_action"),
            version=str(probe.get("engine") or probe.get("mode") or "browser"),
        )
        self.runtime_tool_details["browser"] = dict(probe)

    def _tool_status(self, tool_name: str) -> ToolStatus:
        normalized = str(tool_name or "").strip().lower()
        if normalized in self.runtime_tool_statuses:
            return self.runtime_tool_statuses[normalized]
        return self.tool_guard.check(normalized)


__all__ = [
    "CapabilityEntry",
    "CapabilityImplementation",
    "CapabilityPrimitive",
    "CapabilityRouteDecision",
    "CapabilityRegistry",
    "ToolRequestDecision",
]
