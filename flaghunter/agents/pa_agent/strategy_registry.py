"""Unified strategy registry for CTF exploitation paths."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from urllib.parse import urlparse

from .chains.base import _ChainOutcome
from .ctf_planner import find_auth_form, find_writable_field_name


@runtime_checkable
class StrategyServices(Protocol):
    """显式服务契约:策略 execute lambda 经 ``ctx.services.<method>`` 无条件调用的
    dispatcher 能力面(P3b L1 收窄,2026-06-21)。

    覆盖 strategy_registry 内 20 个 lambda 必调成员;生产实现 = ``CTFTaskDispatcher``
    (经 MRO 上的 *Executor/*Chain mixin 提供全部方法)。唯一生产构造点
    ``CTFTaskDispatcher._strategy_context`` 仍设 ``services=self``——本 Protocol 只做
    *静态类型收窄*,运行期同一 dispatcher 对象、零行为变化。

    **Protocol 外的 optional duck-typed 面**(刻意不纳入):三个 probe 函数
    (``_execute_jwt_probe`` / ``_execute_graphql_probe`` / ``_execute_nosql_probe``)
    经 ``hasattr`` 守卫探测的 ``_run_jwt_manipulation_strategy`` /
    ``_run_graphql_introspection_strategy`` / ``_run_nosql_injection_strategy``。它们带
    LLM fallback、语义上可缺失,纳入"必有"契约会与运行期 optional 语义矛盾,故保留
    ``hasattr`` duck-typing,不进 Protocol。详见 ADR §5.2 卡 L1。
    """

    async def _run_llm_driven_exploration(self, context: "StrategyContext") -> _ChainOutcome: ...

    async def _attempt_auth_form_sqli(self, target: str, auth_form: dict[str, Any]) -> _ChainOutcome: ...

    async def _attempt_auth_form_union_sqli(self, target: str, auth_form: dict[str, Any]) -> _ChainOutcome: ...

    async def _attempt_generic_param_sqli(self, target: str, page_features: dict[str, Any]) -> _ChainOutcome: ...

    async def _attempt_generic_param_cmdi(self, target: str, page_features: dict[str, Any]) -> _ChainOutcome: ...

    async def _attempt_generic_param_ssrf(self, target: str, page_features: dict[str, Any]) -> _ChainOutcome: ...

    async def _attempt_stored_xss_chain(
        self, base: str, auth_form: dict[str, Any], writable_field: str
    ) -> _ChainOutcome: ...

    async def _run_unicode_numeric_form_bypass_strategy(
        self, target: str, page_features: dict[str, Any]
    ) -> _ChainOutcome: ...

    async def _run_contact_report_chain_strategy(
        self, target: str, page_features: dict[str, Any]
    ) -> _ChainOutcome: ...

    async def _run_artifact_forensics_strategy(
        self, target: str, page_features: dict[str, Any], hint: str
    ) -> _ChainOutcome: ...

    async def _run_backup_source_leak_strategy(
        self, target: str, page_features: dict[str, Any], hint: str
    ) -> _ChainOutcome: ...

    async def _attempt_php_unserialize_chain(
        self, target: str, exploit_info: dict[str, Any], *, artifact_url: str
    ) -> _ChainOutcome: ...

    async def _run_hint_chain_followup_strategy(
        self, target: str, page_features: dict[str, Any]
    ) -> _ChainOutcome: ...

    async def _run_file_read_endpoint_strategy(
        self, target: str, page_features: dict[str, Any]
    ) -> _ChainOutcome: ...

    async def _run_hash_guarded_file_read_strategy(
        self, target: str, page_features: dict[str, Any]
    ) -> _ChainOutcome: ...

    async def _run_hash_reconstruction_attack_strategy(
        self, target: str, cookie_secret: str | None = None
    ) -> _ChainOutcome: ...

    async def _run_render_parameter_ssti_strategy(
        self, target: str, page_features: dict[str, Any]
    ) -> _ChainOutcome: ...

    async def _run_tornado_ssti_strategy(self, target: str, page_features: dict[str, Any]) -> _ChainOutcome: ...

    async def _run_ssti_probe_strategy(self, target: str, page_features: dict[str, Any]) -> _ChainOutcome: ...

    async def _run_ssti_identify_strategy(self, target: str, page_features: dict[str, Any]) -> _ChainOutcome: ...

    async def _run_ssti_exploit_strategy(self, target: str, page_features: dict[str, Any]) -> _ChainOutcome: ...


@dataclass(slots=True)
class ChainContext:
    target: str
    page_features: dict[str, Any]
    hint: str = ""
    extras: dict[str, Any] = field(default_factory=dict)
    # 显式服务面:策略 execute lambda 经此调用 dispatcher 的 _run_*/_attempt_*
    # 方法(`ctx.services._run_X(...)`)。生产构造点 _strategy_context 设
    # ``services=self``。P3b 第③刀已摘除旧的 ``dispatcher`` 透传字段;L1 把类型从
    # ``Any`` 收窄为显式 ``StrategyServices`` Protocol(2026-06-21)。
    services: StrategyServices | None = None
    state: Any | None = None
    ingress_handoff: dict[str, Any] = field(default_factory=dict)
    challenge_context: dict[str, Any] = field(default_factory=dict)


StrategyContext = ChainContext


@dataclass(slots=True)
class StrategyDefinition:
    kind: str
    chain_name: str
    precondition_description: str
    minimal_experiment: str
    success_signal: str
    failure_signal: str
    escalation_condition: str
    precondition: Callable[[StrategyContext], bool]
    execute: Callable[[StrategyContext], Awaitable[Any]]
    # OWASP WSTG (+ ATT&CK) technique IDs this strategy maps onto. Backfilled
    # from the central taxonomy (knowledge.attack_taxonomy) in build_default().
    technique_ids: list[str] = field(default_factory=list)

    def is_applicable(self, context: StrategyContext) -> bool:
        """Input: StrategyContext；Output: 当前策略是否满足前提；Success: 返回稳定布尔值；Failure: 上层 Coordinator/Registry 负责换策略。"""
        return bool(self.precondition(context))

    def contract_summary(self) -> dict[str, str]:
        """Input: 无；Output: 策略契约摘要；Success: 暴露前提/最小实验/成功信号/失败信号；Failure: 调用方负责处理缺失字段。"""
        return {
            "kind": self.kind,
            "chain_name": self.chain_name,
            "precondition": self.precondition_description,
            "minimal_experiment": self.minimal_experiment,
            "success_signal": self.success_signal,
            "failure_signal": self.failure_signal,
            "escalation_condition": self.escalation_condition,
        }


class StrategyRegistry:
    def __init__(self):
        self._strategies: dict[str, StrategyDefinition] = {}

    def register(self, strategy: StrategyDefinition) -> None:
        self._strategies[strategy.kind] = strategy

    def get(self, kind: str) -> StrategyDefinition | None:
        return self._strategies.get(kind)

    def all(self) -> list[StrategyDefinition]:
        """All registered strategies (e.g. for technique-coverage reporting)."""
        return list(self._strategies.values())

    def get_contract(self, kind: str) -> dict[str, str] | None:
        """Input: strategy kind；Output: 契约摘要 dict；Success: 能程序化读取策略契约；Failure: 调用方处理 None。"""
        strategy = self.get(kind)
        if strategy is None:
            return None
        return strategy.contract_summary()

    def list_for_chain(self, chain_name: str, context: StrategyContext) -> list[StrategyDefinition]:
        matched: list[StrategyDefinition] = []
        for strategy in self._strategies.values():
            if strategy.chain_name not in {chain_name, "*"}:
                continue
            if strategy.is_applicable(context):
                matched.append(strategy)
        return matched

    async def execute(self, kind: str, context: StrategyContext):
        strategy = self.get(kind)
        if strategy is None:
            raise KeyError(f"unknown strategy: {kind}")
        return await strategy.execute(context)

    @classmethod
    def build_default(cls) -> "StrategyRegistry":
        registry = cls()
        _register_fallback_strategies(registry)
        _register_injection_strategies(registry)
        _register_web_exploitation_strategies(registry)
        _register_ssti_strategies(registry)
        _register_api_injection_strategies(registry)
        # Backfill WSTG/ATT&CK technique IDs from the central taxonomy
        # (ORCHESTRATION → CAPABILITY import, allowed by I1).
        from ...knowledge.attack_taxonomy import tag_strategies

        tag_strategies(registry.all())
        return registry


def _hint_chain_precondition(context: StrategyContext) -> bool:
    """有提示文件链索可能性时为真。"""
    endpoints = set(context.page_features.get("endpoints") or [])
    raw_links = list(context.page_features.get("raw_links") or [])
    all_paths = list(endpoints) + [str(u) for u in raw_links]
    hint_patterns = ("/hints.txt", "/welcome.txt", "/flag.txt", "/a", "/hint")
    if any(
        any(p in path.lower() for p in hint_patterns)
        for path in all_paths
    ):
        return True

    handoff = getattr(context, "ingress_handoff", None) or {}
    structured_next_action = str(handoff.get("nextAction") or "").strip().lower()
    structured_switched_from = str(handoff.get("switchedFrom") or "").strip().lower()
    structured_trigger_reason = str(handoff.get("triggerReason") or "").strip().lower()
    structured_trigger_action_driver = str(handoff.get("triggerActionDriver") or "").strip().lower()

    return (
        (
            structured_next_action == "collect_initial_facts"
            or structured_switched_from == "probe_discovered_endpoint"
            or structured_trigger_action_driver == "blackboard.discovered_endpoint"
        )
        and any(pattern in structured_trigger_reason for pattern in hint_patterns)
    )


def _file_endpoint_precondition(context: StrategyContext) -> bool:
    """存在 /file、/download 等文件读取端点时为真。"""
    endpoints = set(context.page_features.get("endpoints") or [])
    raw_links = list(context.page_features.get("raw_links") or [])
    all_paths = list(endpoints) + [str(u) for u in raw_links]
    file_patterns = ("/file", "/download", "/read", "/get")
    if any(
        any(p in path.lower() for p in file_patterns)
        for path in all_paths
    ):
        return True
    return any(
        any(token in path.lower() for token in ("?file=", "&file=", "?path=", "&path=", "?page=", "&page=", "?include=", "&include=", "filename="))
        for path in all_paths
    )


def _hash_guarded_precondition(context: StrategyContext) -> bool:
    """
    True 的条件（满足任一）：
    1. raw_links 中存在同时含 filename= 和 filehash= 的 URL（href 形式）
    2. 页面内容（content/html）中包含 filehash 关键词，且 endpoints 含 /file 路由
    3. endpoints 中有 /file 且页面内容提及 filename（宽松匹配，覆盖无 href 的 Tornado 挑战）
    """
    raw_links = list(context.page_features.get("raw_links") or [])
    # 条件1：href 直接包含两个参数
    for url in raw_links:
        lowered = url.lower()
        if "filename=" in lowered and "filehash=" in lowered:
            return True
    # 条件2/3：页面内容 + /file 路由
    endpoints = set(context.page_features.get("endpoints") or [])
    has_file_endpoint = "/file" in endpoints or any("/file" in e for e in endpoints)
    if has_file_endpoint:
        content = (
            str(context.page_features.get("content") or "")
            + " "
            + str(context.page_features.get("html") or "")
        ).lower()
        if "filehash" in content:
            return True
        if "filename" in content:  # 宽松：任意 filename 提及即视为候选
            return True
    context_state = getattr(context, "state", None)
    for observation in list(getattr(context_state, "observations", []) or []):
        if str(getattr(observation, "kind", "") or "").strip() != "local_challenge_source_hint":
            continue
        hint_text = str(getattr(observation, "value", "") or "").lower()
        if "filename" in hint_text and "filehash" in hint_text:
            return True
    return False


def _render_param_precondition(context: StrategyContext) -> bool:
    """
    True 的条件（满足任一）：
    1. raw_links / observation / redirect 中出现 msg= message= error= render= template=
    2. 同时观察到 /error 与 render 文本（覆盖 easy_tornado 一类 redirect -> render 题）
    """
    tokens = ("msg=", "message=", "error=", "render=", "template=")
    seed_values: list[str] = [str(item or "") for item in (context.page_features.get("raw_links") or [])]

    context_state = getattr(context, "state", None)
    observations = list(getattr(context_state, "observations", []) or [])
    for observation in observations:
        seed_values.append(str(getattr(observation, "value", "") or ""))
        metadata = getattr(observation, "metadata", None)
        if not isinstance(metadata, dict):
            continue
        for key in ("url", "final_url"):
            value = str(metadata.get(key) or "").strip()
            if value:
                seed_values.append(value)
        for item in list(metadata.get("redirect_history") or []):
            if not isinstance(item, dict):
                continue
            for key in ("url", "location"):
                value = str(item.get(key) or "").strip()
                if value:
                    seed_values.append(value)

    saw_error = False
    saw_render = False
    for raw in seed_values:
        lowered = str(raw or "").lower()
        if not lowered:
            continue
        if any(token in lowered for token in tokens):
            return True
        if "/error" in lowered or "error" in lowered:
            saw_error = True
        if "render" in lowered:
            saw_render = True
    return saw_error and saw_render


def _contact_report_precondition(context: StrategyContext) -> bool:
    endpoints = set(context.page_features.get("endpoints") or [])
    raw_links = [str(item or "") for item in (context.page_features.get("raw_links") or [])]
    combined = (
        str(context.page_features.get("content") or "")
        + " "
        + str(context.page_features.get("html") or "")
    ).lower()
    if any("/contact" in path.lower() or "/report" in path.lower() for path in endpoints):
        return True
    if any("/contact" in link.lower() or "/report" in link.lower() for link in raw_links):
        return True
    if "flag?token=" in combined and "logout" in combined:
        return True
    return any(token in combined for token in ("captcha", "/static/pow.py", "/static/vpow.py"))


def _artifact_forensics_precondition(context: StrategyContext) -> bool:
    combined = (
        str(context.page_features.get("content") or "")
        + " "
        + str(context.page_features.get("html") or "")
        + " "
        + str(context.hint or "")
    ).lower()
    raw_links = [str(item or "").lower() for item in (context.page_features.get("raw_links") or [])]
    endpoints = [str(item or "").lower() for item in (context.page_features.get("endpoints") or [])]
    tokens = (".zip", ".db", ".sqlite", ".sqlite3", ".wal", ".pcap", ".7z", ".rar", "directory listing", "附件")
    local_artifacts = [
        str(item or "").lower()
        for item in (
            (getattr(context, "challenge_context", None) or {}).get("artifactPaths")
            or []
        )
    ]
    if any(token in combined for token in tokens):
        return True
    if any(token in link for link in raw_links for token in tokens):
        return True
    if any(token in ep for ep in endpoints for token in tokens):
        return True
    if any(token in path for path in local_artifacts for token in tokens):
        return True
    return False


def _unicode_numeric_form_precondition(context: StrategyContext) -> bool:
    forms = context.page_features.get("forms") or []
    combined = (
        str(context.page_features.get("content") or "")
        + " "
        + str(context.page_features.get("html") or "")
    ).lower()
    endpoints = [str(item or "").lower() for item in (context.page_features.get("endpoints") or [])]
    raw_links = [str(item or "").lower() for item in (context.page_features.get("raw_links") or [])]

    semantic_hit = any(
        token in combined
        for token in (
            "purchase",
            "price",
            "item id",
            "only one char",
            "one char",
            "unicorn shop",
        )
    )
    route_hit = any("/charge" in item for item in [*endpoints, *raw_links])

    for form in forms:
        if not isinstance(form, dict):
            continue
        action = str(form.get("action") or "").strip().lower()
        input_names = {
            str(item.get("name") or "").strip().lower()
            for item in (form.get("inputs") or [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        }
        if not {"id", "price"}.issubset(input_names):
            continue
        if "/charge" in action or action.endswith("charge"):
            return True
        if semantic_hit or route_hit:
            return True
    return False


def _generic_param_sqli_precondition(context: StrategyContext) -> bool:
    forms = context.page_features.get("forms") or []
    for form in forms:
        if not isinstance(form, dict):
            continue
        method = str(form.get("method") or "GET").strip().upper()
        if method != "GET":
            continue
        for item in form.get("inputs") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            field_type = str(item.get("type") or "text").strip().lower()
            if field_type in {"submit", "button", "image", "reset", "hidden"}:
                continue
            return True
    return False


def _generic_param_cmdi_precondition(context: StrategyContext) -> bool:
    """存在可注入参数面：带命名输入的 GET 表单，或带 query 参数的链接/观测 URL。"""
    if _generic_param_sqli_precondition(context):
        return True
    from urllib.parse import urlparse

    for raw in context.page_features.get("raw_links") or []:
        if urlparse(str(raw or "")).query:
            return True
    return False


def _xss_admin_bot_precondition(context: StrategyContext) -> bool:
    forms = context.page_features.get("forms") or []
    endpoints = set(context.page_features.get("endpoints") or [])
    has_visit = "/visit" in endpoints
    has_admin = "/admin" in endpoints
    if not (has_visit and has_admin):
        context_state = getattr(context, "state", None)
        source_hint_text = "\n".join(
            str(getattr(observation, "value", "") or "")
            for observation in list(getattr(context_state, "observations", []) or [])
            if str(getattr(observation, "kind", "") or "").strip() == "local_challenge_source_hint"
        ).lower()
        has_visit = has_visit or "/visit" in source_hint_text
        has_admin = has_admin or "/admin" in source_hint_text
    return (
        find_auth_form(forms) is not None
        and bool(find_writable_field_name(forms))
        and has_visit
        and has_admin
    )


# Phase 7 §5: preconditions for three-stage SSTI pipeline

def _ssti_probe_ran(context: StrategyContext) -> bool:
    """True if ssti_probe has already run (render_ssti_response with source='ssti_probe' exists)
    and at least one probe hit was observed, and ssti_identify has NOT yet been attempted."""
    state = getattr(context, "state", None)
    if state is None:
        return False
    probe_ran = False
    probe_hit = False
    identify_attempted = False
    for obs in getattr(state, "observations", []) or []:
        kind = getattr(obs, "kind", "")
        source = getattr(obs, "source", "")
        if kind == "render_ssti_response" and source == "ssti_probe":
            probe_ran = True
        if kind == "ssti_probe_hit":
            probe_hit = True
        if kind == "ssti_identify_attempted":
            identify_attempted = True
    return probe_ran and probe_hit and not identify_attempted


def _ssti_engine_identified_precondition(context: StrategyContext) -> bool:
    """True if ssti_engine_identified observation exists in state."""
    state = getattr(context, "state", None)
    if state is None:
        return False
    for obs in getattr(state, "observations", []) or []:
        if getattr(obs, "kind", "") == "ssti_engine_identified":
            return True
    return False


# P4: New strategy preconditions and executors


def _jwt_precondition(context: StrategyContext) -> bool:
    """请求/响应/Cookie 中存在 JWT token 格式（eyJ...）。"""
    content = (
        str(context.page_features.get("content") or "")
        + " "
        + str(context.page_features.get("html") or "")
        + " "
        + str(context.page_features.get("headers") or "")
        + " "
        + str(context.page_features.get("cookies") or "")
    )
    return "eyJ" in content or "Bearer " in content or "authorization" in content.lower()


async def _execute_jwt_probe(context: StrategyContext):
    """执行 JWT 基础探测：alg:none, RS256→HS256, 弱密钥提示。"""
    # ``_run_jwt_manipulation_strategy`` 是 Protocol 外的 optional duck-typed 面
    # (带 LLM fallback、语义可缺失),刻意经 ``hasattr`` 探测而非纳入 StrategyServices。
    dispatcher = context.services
    target = context.target
    # 委托 dispatcher 的通用 HTTP 探测或 LLM 驱动探索
    if hasattr(dispatcher, "_run_jwt_manipulation_strategy"):
        return await dispatcher._run_jwt_manipulation_strategy(target, context.page_features)
    # fallback: 使用 LLM-driven 探索
    if hasattr(dispatcher, "_run_llm_driven_exploration"):
        return await dispatcher._run_llm_driven_exploration(context)
    return {"progress": False, "reason": "No JWT handler available"}


def _graphql_precondition(context: StrategyContext) -> bool:
    """发现 GraphQL 端点或响应含 GraphQL 特征。"""
    endpoints = set(context.page_features.get("endpoints") or [])
    raw_links = [str(item or "").lower() for item in (context.page_features.get("raw_links") or [])]
    combined = (
        str(context.page_features.get("content") or "")
        + " "
        + str(context.page_features.get("html") or "")
    ).lower()
    gql_patterns = ("/graphql", "/graphiql", "/api/graphql", "/query")
    if any(p in e.lower() for e in endpoints for p in gql_patterns):
        return True
    if any(p in link for link in raw_links for p in gql_patterns):
        return True
    return "graphql" in combined or '"data":' in combined or '"errors":' in combined


async def _execute_graphql_probe(context: StrategyContext):
    """执行 GraphQL 内省查询探测。"""
    # ``_run_graphql_introspection_strategy``:Protocol 外 optional duck-typed 面(见 _execute_jwt_probe)。
    dispatcher = context.services
    target = context.target
    if hasattr(dispatcher, "_run_graphql_introspection_strategy"):
        return await dispatcher._run_graphql_introspection_strategy(target, context.page_features)
    if hasattr(dispatcher, "_run_llm_driven_exploration"):
        return await dispatcher._run_llm_driven_exploration(context)
    return {"progress": False, "reason": "No GraphQL handler available"}


def _nosql_precondition(context: StrategyContext) -> bool:
    """存在 JSON 格式提交的 API 端点，疑似 NoSQL 后端。"""
    content = (
        str(context.page_features.get("content") or "")
        + " "
        + str(context.page_features.get("html") or "")
    ).lower()
    endpoints = [str(e or "").lower() for e in (context.page_features.get("endpoints") or [])]
    raw_links = [str(u or "").lower() for u in (context.page_features.get("raw_links") or [])]
    # MongoDB 线索
    mongo_clues = ("mongodb", "mongoose", "mongo", "bson", "objectid")
    if any(c in content for c in mongo_clues):
        return True
    # JSON API 端点
    json_endpoints = [e for e in (*endpoints, *raw_links) if "/api/" in e or "/auth" in e or "/login" in e]
    if json_endpoints and "application/json" in content:
        return True
    # 参数含 JSON 风格键
    return any(token in content for token in ("$eq", "$ne", "$gt", "$regex", "$where"))


async def _execute_nosql_probe(context: StrategyContext):
    """执行 NoSQL 注入基础探测。"""
    # ``_run_nosql_injection_strategy``:Protocol 外 optional duck-typed 面(见 _execute_jwt_probe)。
    dispatcher = context.services
    target = context.target
    if hasattr(dispatcher, "_run_nosql_injection_strategy"):
        return await dispatcher._run_nosql_injection_strategy(target, context.page_features)
    if hasattr(dispatcher, "_run_llm_driven_exploration"):
        return await dispatcher._run_llm_driven_exploration(context)
    return {"progress": False, "reason": "No NoSQL handler available"}


def _deserialization_precondition(context: StrategyContext) -> bool:
    """疑似不安全反序列化面：序列化 blob 载体或源码/框架线索。

    强信号：cookie / 参数 / 表单字段里出现 Java（base64 ``rO0``/魔数 ``\\xac\\xed``）
    或 Python pickle（base64 ``gA…``/``\\x80\\x0[2-5]``）blob。弱信号：内容里出现
    pickle/ObjectInputStream/ysoserial/反序列化等关键词。
    """
    cookies = str(context.page_features.get("cookies") or "")
    raw_links = [str(item or "") for item in (context.page_features.get("raw_links") or [])]
    blob_carriers = [cookies, *raw_links]
    if any("rO0" in carrier or "\xac\xed" in carrier for carrier in blob_carriers):
        return True
    # base64 pickle blobs start "gA"; require a longer run to avoid false hits.
    for carrier in blob_carriers:
        if re.search(r"\bgA[A-Za-z0-9+/]{16,}={0,2}", carrier):
            return True
    combined = (
        str(context.page_features.get("content") or "")
        + " "
        + str(context.page_features.get("html") or "")
    ).lower()
    clues = (
        "pickle",
        "cpickle",
        "__reduce__",
        "objectinputstream",
        "readobject",
        "ysoserial",
        "deserialization",
        "反序列化",
        "yaml.load",
        "marshal.loads",
    )
    return any(clue in combined for clue in clues)


async def _execute_deserialization_probe(context: StrategyContext):
    """执行不安全反序列化探测（Java 检测 / Python pickle RCE）。"""
    # ``_run_insecure_deserialization_strategy``:Protocol 外 optional duck-typed 面(见 _execute_jwt_probe)。
    dispatcher = context.services
    target = context.target
    if hasattr(dispatcher, "_run_insecure_deserialization_strategy"):
        return await dispatcher._run_insecure_deserialization_strategy(target, context.page_features)
    if hasattr(dispatcher, "_run_llm_driven_exploration"):
        return await dispatcher._run_llm_driven_exploration(context)
    return {"progress": False, "reason": "No deserialization handler available"}


def _xxe_precondition(context: StrategyContext) -> bool:
    """疑似 XML 解析面：XML 内容/内容类型线索，或 XML 风格端点。

    强信号：内容/HTML/响应头出现 ``<?xml``、``application/xml``、``text/xml``、
    ``<!DOCTYPE``/``<!ENTITY``、SOAP/XML-RPC/WSDL 等。结构信号：endpoints/raw_links
    指向 ``/xml``、``.xml``、``/soap``、``/wsdl``、``/rss``、``/feed``、xmlrpc。
    """
    combined = (
        str(context.page_features.get("content") or "")
        + " "
        + str(context.page_features.get("html") or "")
        + " "
        + str(context.page_features.get("headers") or "")
    ).lower()
    clues = (
        "<?xml",
        "application/xml",
        "text/xml",
        "<!doctype",
        "<!entity",
        "soap",
        "xmlrpc",
        "wsdl",
        "xxe",
    )
    if any(clue in combined for clue in clues):
        return True
    endpoints = [str(e or "").lower() for e in (context.page_features.get("endpoints") or [])]
    raw_links = [str(u or "").lower() for u in (context.page_features.get("raw_links") or [])]
    url_patterns = ("/xml", ".xml", "/soap", "/wsdl", "/rss", "/feed", "xmlrpc")
    return any(p in item for item in (*endpoints, *raw_links) for p in url_patterns)


async def _execute_xxe_probe(context: StrategyContext):
    """执行 XXE 探测（外部实体读取文件）。"""
    # ``_run_xxe_injection_strategy``:Protocol 外 optional duck-typed 面(见 _execute_jwt_probe)。
    dispatcher = context.services
    target = context.target
    if hasattr(dispatcher, "_run_xxe_injection_strategy"):
        return await dispatcher._run_xxe_injection_strategy(target, context.page_features)
    if hasattr(dispatcher, "_run_llm_driven_exploration"):
        return await dispatcher._run_llm_driven_exploration(context)
    return {"progress": False, "reason": "No XXE handler available"}


def _reflected_xss_precondition(context: StrategyContext) -> bool:
    """疑似反射型 XSS 面：可注入查询参数面，或搜索/回显类内容线索。

    主信号：带命名输入的 GET 表单或带 query 参数的链接（与 cmdi 同型的可注入面，
    探针走 GET 反射）。弱信号：内容/HTML 出现 search / 关键词回显语义，使裸搜索框
    也能经 fallback 参数名获得一次真实探测。
    """
    if _generic_param_cmdi_precondition(context):
        return True
    combined = (
        str(context.page_features.get("content") or "")
        + " "
        + str(context.page_features.get("html") or "")
    ).lower()
    return any(
        token in combined
        for token in ("search", "type=\"search\"", "type='search'", "?q=", "&q=", "keyword", "echo")
    )


def _idor_precondition(context: StrategyContext) -> bool:
    """疑似 IDOR 面：URL/观测/表单暴露可枚举的数字对象 id，或账户/订单类内容语义。

    主信号：raw_links/观测 URL 带 id 类数字 query 参数（?id=42）或纯数字路径段
    (/user/42)；GET 表单含 id 类命名输入。弱信号：内容出现 account/order/profile/
    invoice/ticket/user id 语义,使带数字 id 的对象面经 fallback 也能获得一次真实探测。
    """
    from urllib.parse import parse_qs, urlparse

    id_names = {
        "id", "uid", "user", "user_id", "userid", "account", "account_id",
        "order", "order_id", "doc", "document", "file", "file_id", "pid",
        "num", "no", "item", "item_id", "record", "profile", "profile_id",
        "invoice", "ticket", "report", "report_id", "message", "msg_id",
    }
    seeds = [str(u or "") for u in (context.page_features.get("raw_links") or [])]
    seeds += [str(e or "") for e in (context.page_features.get("endpoints") or [])]
    for raw in seeds:
        parsed = urlparse(raw)
        for key, values in parse_qs(parsed.query, keep_blank_values=True).items():
            if key.lower() in id_names and values and values[0].isdigit():
                return True
        if any(seg.isdigit() for seg in parsed.path.split("/") if seg):
            return True
    for form in context.page_features.get("forms") or []:
        if not isinstance(form, dict):
            continue
        for item in form.get("inputs") or []:
            if isinstance(item, dict) and str(item.get("name") or "").strip().lower() in id_names:
                return True
    combined = (
        str(context.page_features.get("content") or "")
        + " "
        + str(context.page_features.get("html") or "")
    ).lower()
    return any(
        token in combined
        for token in ("account", "order", "profile", "invoice", "ticket", "user id", "my orders")
    )


async def _execute_idor_probe(context: StrategyContext):
    """执行 IDOR 探测（枚举顺序对象 id，确认返回不同记录）。"""
    # ``_run_idor_strategy``:Protocol 外 optional duck-typed 面(见 _execute_jwt_probe)。
    dispatcher = context.services
    target = context.target
    if hasattr(dispatcher, "_run_idor_strategy"):
        return await dispatcher._run_idor_strategy(target, context.page_features)
    if hasattr(dispatcher, "_run_llm_driven_exploration"):
        return await dispatcher._run_llm_driven_exploration(context)
    return {"progress": False, "reason": "No IDOR handler available"}


def _open_redirect_precondition(context: StrategyContext) -> bool:
    """疑似开放重定向面：URL/表单暴露 redirect 类参数，或内容含重定向 sink 语义。

    主信号：raw_links/观测 URL 带 redirect/url/next/return/dest 类 query 参数，或
    GET 表单含此类命名输入。弱信号：内容/HTML 出现 redirect=/?next=/?url=/returnurl/
    window.location/location.href/http-equiv refresh 等 sink 语义。
    """
    from urllib.parse import parse_qs, urlparse

    redirect_names = {
        "redirect", "redirect_uri", "redirect_url", "redir", "url", "next",
        "returnurl", "return_url", "return", "return_to", "dest", "destination",
        "to", "goto", "continue", "callback", "target", "link", "out", "u", "r",
    }
    seeds = [str(u or "") for u in (context.page_features.get("raw_links") or [])]
    seeds += [str(e or "") for e in (context.page_features.get("endpoints") or [])]
    for raw in seeds:
        if any(key.lower() in redirect_names for key in parse_qs(urlparse(raw).query, keep_blank_values=True)):
            return True
    for form in context.page_features.get("forms") or []:
        if not isinstance(form, dict):
            continue
        for item in form.get("inputs") or []:
            if isinstance(item, dict) and str(item.get("name") or "").strip().lower() in redirect_names:
                return True
    combined = (
        str(context.page_features.get("content") or "")
        + " "
        + str(context.page_features.get("html") or "")
    ).lower()
    return any(
        token in combined
        for token in (
            "redirect=", "?next=", "&next=", "?url=", "&url=", "returnurl",
            "window.location", "location.href", "http-equiv=\"refresh\"",
        )
    )


async def _execute_open_redirect_probe(context: StrategyContext):
    """执行开放重定向探测（注入良性站外 canary，确认到达重定向 sink）。"""
    # ``_run_open_redirect_strategy``:Protocol 外 optional duck-typed 面(见 _execute_jwt_probe)。
    dispatcher = context.services
    target = context.target
    if hasattr(dispatcher, "_run_open_redirect_strategy"):
        return await dispatcher._run_open_redirect_strategy(target, context.page_features)
    if hasattr(dispatcher, "_run_llm_driven_exploration"):
        return await dispatcher._run_llm_driven_exploration(context)
    return {"progress": False, "reason": "No open redirect handler available"}


async def _execute_reflected_xss_probe(context: StrategyContext):
    """执行反射型 XSS 探测（注入 canary，确认未转义回显）。"""
    # ``_run_reflected_xss_strategy``:Protocol 外 optional duck-typed 面(见 _execute_jwt_probe)。
    dispatcher = context.services
    target = context.target
    if hasattr(dispatcher, "_run_reflected_xss_strategy"):
        return await dispatcher._run_reflected_xss_strategy(target, context.page_features)
    if hasattr(dispatcher, "_run_llm_driven_exploration"):
        return await dispatcher._run_llm_driven_exploration(context)
    return {"progress": False, "reason": "No reflected XSS handler available"}


__all__ = [
    "ChainContext",
    "StrategyContext",
    "StrategyDefinition",
    "StrategyRegistry",
    "StrategyServices",
]


def _register_fallback_strategies(registry: "StrategyRegistry") -> None:
    """LLM-driven fallback (the "*" catch-all)."""
    registry.register(
        StrategyDefinition(
            kind="llm_driven_exploration",
            chain_name="*",
            precondition_description="无前提；当其他策略全部不适用或耗尽时启用。",
            minimal_experiment="由 LLM 基于当前 observations 选择下一个 http_request / shell 动作。",
            success_signal="LLM 调用后返回 verified/runtime flag。",
            failure_signal="连续多次 LLM-driven 动作均无 progress 或被 budget 限制。",
            escalation_condition="若 LLM 给出新的结构线索，允许 HypothesisEngine 重排假设。",
            precondition=lambda ctx: True,
            execute=lambda ctx: ctx.services._run_llm_driven_exploration(ctx),  # noqa: SLF001
        )
    )


def _register_injection_strategies(registry: "StrategyRegistry") -> None:
    """SQLi / XSS injection chains."""
    registry.register(
        StrategyDefinition(
            kind="auth_form_sqli",
            chain_name="sqli",
            precondition_description="存在可识别的认证表单，且能定位 username / password 字段。",
            minimal_experiment="提交最小 SQLi 登录绕过 payload 到认证表单。",
            success_signal="认证响应中出现 verified flag，或明显成功登录差异。",
            failure_signal="所有最小 payload 用尽且无 verified/runtime 级信号。",
            escalation_condition="auth-form 最短链未直接出 flag 时，升级到 sqlmap 或其他 SQLi 侦察。",
            precondition=lambda ctx: find_auth_form(ctx.page_features.get("forms") or []) is not None,
            execute=lambda ctx: ctx.services._attempt_auth_form_sqli(  # noqa: SLF001
                ctx.target,
                find_auth_form(ctx.page_features.get("forms") or []),
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="auth_form_union_sqli",
            chain_name="sqli",
            precondition_description="存在可识别的认证表单（可定位 username 字段），适合 UNION 提取库内 flag。",
            minimal_experiment="对登录框 username 字段做 UNION SELECT：先探列数与回显位，再 dump 表/列/行数据并扫 flag。",
            success_signal="回显位反射出 group_concat 的库内数据，且其中出现 verified/runtime flag。",
            failure_signal="探不到可回显的 UNION 列，或 dump 完候选表仍无 flag。",
            escalation_condition="UNION 提取确认注入但未取回 flag 时，升级到 sqlmap 做更深的枚举。",
            precondition=lambda ctx: find_auth_form(ctx.page_features.get("forms") or []) is not None,
            execute=lambda ctx: ctx.services._attempt_auth_form_union_sqli(  # noqa: SLF001
                ctx.target,
                find_auth_form(ctx.page_features.get("forms") or []),
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="generic_param_sqli",
            chain_name="sqli",
            precondition_description="存在带可注入字段的 GET 表单，且适合先做轻量手工 SQLi / stacked-query 探测。",
            minimal_experiment="对 GET 参数做最小 quote probe，再尝试 show tables / show columns / handler read 这类轻量链路。",
            success_signal="HTTP 响应中出现 verified/runtime flag，或出现明确的 stacked-query 结构信息。",
            failure_signal="GET 参数轻量 payload 用尽，既没有 SQL error 也没有结构化表名/列名进展。",
            escalation_condition="轻量 GET 参数链只确认注入但未恢复 flag 时，再升级到 sqlmap 或其他 SQLi 侦察。",
            precondition=lambda ctx: _generic_param_sqli_precondition(ctx),
            execute=lambda ctx: ctx.services._attempt_generic_param_sqli(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="generic_param_cmdi",
            chain_name="cmdi",
            precondition_description="存在可注入参数面（带命名输入的 GET 表单，或带 query 参数的链接）。",
            minimal_experiment="向每个发现的 query 参数注入命令分隔符 payload（;cat /flag;id 等），观察 flag 或 uid=/passwd 标记。",
            success_signal="HTTP 响应出现 verified/runtime flag，或出现命令执行证据（uid=、root:x:0:0:）。",
            failure_signal="所有发现参数的命令分隔符 payload 用尽，既无 flag 也无执行证据。",
            escalation_condition="确认命令执行但未取回 flag 时，再尝试更精细的读取路径或反弹。",
            precondition=lambda ctx: _generic_param_cmdi_precondition(ctx),
            execute=lambda ctx: ctx.services._attempt_generic_param_cmdi(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="generic_param_ssrf",
            chain_name="ssrf",
            precondition_description="存在可注入参数面（带命名输入的 GET 表单，或带 query 参数的链接）。",
            minimal_experiment="把每个发现参数替换为 SSRF payload（file:///flag、file:///etc/passwd、http://127.0.0.1/），观察 flag 或 /etc/passwd 泄露。",
            success_signal="HTTP 响应出现 verified/runtime flag，或出现 root:x:0:0:（内网/本地文件读取证据）。",
            failure_signal="所有发现参数的 SSRF payload 用尽，既无 flag 也无内网读取证据。",
            escalation_condition="确认 SSRF 但未取回 flag 时，再尝试 gopher/dict 等协议或内网端口探测。",
            precondition=lambda ctx: _generic_param_cmdi_precondition(ctx),
            execute=lambda ctx: ctx.services._attempt_generic_param_ssrf(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="xss_admin_bot_sid",
            chain_name="xss",
            precondition_description="存在 /visit + /admin + 可写入表单字段，符合 bot-XSS / sid theft 形状。",
            minimal_experiment="提交最小同源 payload，触发 /visit，回收 sid 并回放到 /admin。",
            success_signal="collector / /admin 回放后获得 verified flag。",
            failure_signal="payload 轮换后 collector 与 admin 信号均未推进。",
            escalation_condition="stored XSS 不成立时，退到 visit-url 路径或其他 XSS 证据链。",
            precondition=lambda ctx: _xss_admin_bot_precondition(ctx),
            execute=lambda ctx: ctx.services._attempt_stored_xss_chain(  # noqa: SLF001
                str(ctx.extras.get("base_target") or ctx.target),
                find_auth_form(ctx.page_features.get("forms") or []),
                find_writable_field_name(ctx.page_features.get("forms") or []),
            ),
        )
    )


def _register_web_exploitation_strategies(registry: "StrategyRegistry") -> None:
    """Web exploitation chains (forms, source leak, deserialize, file read, hashing)."""
    registry.register(
        StrategyDefinition(
            kind="unicode_numeric_form_bypass",
            chain_name="web",
            precondition_description="存在购买/计价表单，同时包含 id + price 字段，并出现 /charge 或 Only one char 这类单字符价格约束语义。",
            minimal_experiment="先提交普通 price=1 建立失败基线，再提交单字符 Unicode 数值 payload（如 万 / 萬 / ፼ / ↈ）验证业务绕过。",
            success_signal="响应中出现 verified/runtime flag，或单字符 Unicode 数值 payload 相比基线出现明确购买成功差异。",
            failure_signal="所有 Unicode numeric payload 均只返回余额不足/单字符限制/无差异失败。",
            escalation_condition="若业务绕过不成立，再回退到 backup/source leak 或其他 web 结构链继续推进。",
            precondition=lambda ctx: _unicode_numeric_form_precondition(ctx),
            execute=lambda ctx: ctx.services._run_unicode_numeric_form_bypass_strategy(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="contact_report_chain",
            chain_name="web",
            precondition_description="登录后页面暴露 /contact / report 链接，或内容包含 captcha/pow 提示，说明存在 admin-report 提交面。",
            minimal_experiment="进入 /contact，抓取表单与 hidden 字段，提交一次最小 payload，判断是否被 captcha/pow 阻塞。",
            success_signal="明确记录 contact/report 已提交，或将 captcha/pow 阻塞沉淀为统一失败回显。",
            failure_signal="无法发现 /contact 页面，或 contact 页面没有可操作表单。",
            escalation_condition="若被 captcha/pow 阻塞，则优先补 solver/绕过；若已提交，则继续沿 admin-visit / callback 链路推进。",
            precondition=lambda ctx: _contact_report_precondition(ctx),
            execute=lambda ctx: ctx.services._run_contact_report_chain_strategy(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="artifact_forensics",
            chain_name="misc",
            precondition_description="页面/目录/附件中存在 zip/db/wal/pcap 等附件型线索，适合先做文件取证与结构分析。",
            minimal_experiment="枚举并下载候选附件，对 zip/sqlite/wal 等进行静态分析、字符串提取、分片重组与局部解码。",
            success_signal="附件分析直接恢复 verified/runtime flag，或沉淀出可执行的下一步利用/解码线索。",
            failure_signal="候选附件分析完成但未恢复 flag，也没有形成更强结构线索。",
            escalation_condition="若附件分析未闭环，则把 artifact 摘要、知识库提示和联网 hint 注入给 LLM 驱动探索继续构造链路。",
            precondition=lambda ctx: _artifact_forensics_precondition(ctx),
            execute=lambda ctx: ctx.services._run_artifact_forensics_strategy(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
                ctx.hint,
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="backup_source_leak",
            chain_name="web",
            precondition_description="页面/源码/提示中存在 backup/source clue，或该链路被 web 假设选中。",
            minimal_experiment="探测常见备份路径并下载分析源码/压缩包。",
            success_signal="发现 verified flag，或获得 source candidate 并定位下一跳 runtime primitive。",
            failure_signal="常见备份路径枚举完毕且无进一步 runtime 证据。",
            escalation_condition="源码中暴露 unserialize/magic-method 等 primitive 时升级到 php_unserialize_magic_method。",
            precondition=lambda ctx: True,
            execute=lambda ctx: ctx.services._run_backup_source_leak_strategy(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
                ctx.hint,
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="php_unserialize_magic_method",
            chain_name="web",
            precondition_description="源码分析已确认存在 unserialize + magic method 组合，并产出 payload 信息。",
            minimal_experiment="构造最小化 serialized object payload 并对运行时入口发起探测。",
            success_signal="运行时响应中出现 verified flag。",
            failure_signal="payload 列表耗尽且无 verified/runtime 级进展。",
            escalation_condition="若 payload exhausted，则回退到其他 runtime primitive 或停止误报。",
            precondition=lambda ctx: bool(ctx.extras.get("exploit_info")),
            execute=lambda ctx: ctx.services._attempt_php_unserialize_chain(  # noqa: SLF001
                ctx.target,
                ctx.extras.get("exploit_info") or {},
                artifact_url=str(ctx.extras.get("artifact_url") or ""),
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="hint_chain_followup",
            chain_name="web",
            precondition_description="发现 /hints.txt、/welcome.txt、/flag.txt 等提示文件，或 exploration_agenda 含提示类条目。",
            minimal_experiment="依次 GET /hints.txt 和 /welcome.txt，将内容写入 observations。",
            success_signal="从提示文件中提取到 flag，或获得 hash 计算规则等关键信息。",
            failure_signal="所有提示文件均 404 或内容为空。",
            escalation_condition="读到 hash 规则后升级到 hash_guarded_file_read / hash_reconstruction_attack。",
            precondition=lambda ctx: _hint_chain_precondition(ctx),
            execute=lambda ctx: ctx.services._run_hint_chain_followup_strategy(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="file_read_endpoint",
            chain_name="web",
            precondition_description="页面存在 /file 或 /download 路由，或 agenda 含带 filename 参数的 URL。",
            minimal_experiment="直接 GET /file?filename=/flag.txt（不带 hash）观察错误信息或内容。",
            success_signal="响应包含 flag，或泄露错误信息暗示 hash 规则。",
            failure_signal="响应 403/500 且无有用信息。",
            escalation_condition="有 hash 规则提示时升级到 hash_guarded_file_read。",
            precondition=lambda ctx: _file_endpoint_precondition(ctx),
            execute=lambda ctx: ctx.services._run_file_read_endpoint_strategy(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="hash_guarded_file_read",
            chain_name="web",
            precondition_description="已知 filehash 参数存在（从 raw_links 检测到 filename+filehash 组合）。",
            minimal_experiment="在 filename 参数注入 Tornado SSTI 表达式（{{handler.settings[\"cookie_secret\"]}}）获取 secret，再计算 hash 读取 /flag.txt。",
            success_signal="SSTI 响应暴露 cookie_secret，或直接返回 flag。",
            failure_signal="SSTI 注入无效，所有 probe 均无有用响应。",
            escalation_condition="获得 secret 后自动进入 hash_reconstruction_attack 计算完整哈希路径。",
            precondition=lambda ctx: _hash_guarded_precondition(ctx),
            execute=lambda ctx: ctx.services._run_hash_guarded_file_read_strategy(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="hash_reconstruction_attack",
            chain_name="web",
            precondition_description="已获得 cookie_secret（由 hash_guarded_file_read 传入 extras）。",
            minimal_experiment="计算 md5(cookie_secret+md5(filename))，请求 /file?filename=/flag.txt&filehash=<hash>。",
            success_signal="响应包含 flag。",
            failure_signal="hash 计算有误，所有目标文件响应均无 flag。",
            escalation_condition="若 /flag.txt 无 flag，尝试 /flag、/secret 等变体。",
            precondition=lambda ctx: bool(ctx.extras.get("cookie_secret")),
            execute=lambda ctx: ctx.services._run_hash_reconstruction_attack_strategy(  # noqa: SLF001
                ctx.target,
                str(ctx.extras.get("cookie_secret") or ""),
            ),
        )
    )


def _register_ssti_strategies(registry: "StrategyRegistry") -> None:
    """SSTI strategies (legacy single-shot + Detect/Identify/Exploit split)."""
    registry.register(
        StrategyDefinition(
            kind="ssti_via_render_parameter",
            # Phase 7: chain_name changed to "web-legacy" so auto-dispatch (fallback loop)
            # no longer picks this up. The 3-stage pipeline (ssti_probe/identify/exploit)
            # is used instead. Kept for direct calls and surface-key tests.
            chain_name="web-legacy",
            precondition_description="已发现 /error?msg=...、render/template/name 等渲染参数面，或运行时 redirect 暴露到这些参数。",
            minimal_experiment="对 render/msg 参数注入最小 SSTI payload（{{7*7}} / cookie_secret 探针），验证模板表达式是否执行。",
            success_signal="响应中出现 49、cookie_secret 或 verified flag，并能继续进入 hash 重构。",
            failure_signal="render 参数探针全部返回静态错误或无差异响应。",
            escalation_condition="若泄露 cookie_secret，则升级到 hash_reconstruction_attack 计算真实 flag 路径。",
            precondition=lambda ctx: _render_param_precondition(ctx),
            execute=lambda ctx: ctx.services._run_render_parameter_ssti_strategy(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="tornado_ssti",
            # Phase 7: chain_name changed to "web-legacy" (see ssti_via_render_parameter comment).
            chain_name="web-legacy",
            precondition_description="提示/文件读取链已显示 Tornado render 迹象，且存在 render 参数面可继续验证 SSTI。",
            minimal_experiment="沿 redirect 暴露的 /error?msg=... 面打 Tornado SSTI，而不是只盯 filename 参数。",
            success_signal="Tornado 渲染响应中出现 cookie_secret、表达式执行结果或 verified flag。",
            failure_signal="render/msg 参数注入无法产生任何运行时差异。",
            escalation_condition="若拿到 cookie_secret，则自动切换到 hash_reconstruction_attack。",
            precondition=lambda ctx: _render_param_precondition(ctx),
            execute=lambda ctx: ctx.services._run_tornado_ssti_strategy(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
            ),
        )
    )

    # Phase 7 §5: three-stage SSTI pipeline (Detect → Identify → Exploit)
    registry.register(
        StrategyDefinition(
            kind="ssti_probe",
            chain_name="web",
            precondition_description="存在渲染参数面（msg=/error 等）；发送四种通用 payload 探测模板执行。",
            minimal_experiment="向 render/msg 参数发送 {{7*7}}、${7*7}、#{7*7}、<%= 7*7 %> 四类 probe，检测 49 出现。",
            success_signal="响应中出现 49，记录 ssti_probe_hit。",
            failure_signal="所有 probe 返回统一失败回显，标记表面耗尽。",
            escalation_condition="probe_hit 后由 ssti_identify 识别引擎，再由 ssti_exploit 执行利用。",
            precondition=lambda ctx: _render_param_precondition(ctx),
            execute=lambda ctx: ctx.services._run_ssti_probe_strategy(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="ssti_identify",
            chain_name="web",
            precondition_description="ssti_probe 已运行（render_ssti_response 存在）且尚未完成引擎识别。",
            minimal_experiment="发送 {{handler.settings}} 等引擎专属 payload，识别模板引擎并记录 ssti_engine_identified。",
            success_signal="记录 ssti_engine_identified 观察（tornado / jinja2 等）。",
            failure_signal="所有引擎特征 payload 无法区分，记录 ssti_identify_attempted=no_match。",
            escalation_condition="识别成功后由 ssti_exploit 执行引擎对应利用路径。",
            precondition=lambda ctx: _ssti_probe_ran(ctx),
            execute=lambda ctx: ctx.services._run_ssti_identify_strategy(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
            ),
        )
    )

    registry.register(
        StrategyDefinition(
            kind="ssti_exploit",
            chain_name="web",
            precondition_description="ssti_engine_identified 观察存在，可执行引擎对应利用链。",
            minimal_experiment="Tornado: 用已提取的 cookie_secret 做 hash 重构；Jinja2: {{config}} dump；其余: LLM fallback。",
            success_signal="获得 verified flag 或 hash 重构成功拿到 flag。",
            failure_signal="所有利用路径均无 flag，返回 progress=False。",
            escalation_condition="若所有已知引擎路径耗尽，触发 LLM-driven 兜底。",
            precondition=lambda ctx: _ssti_engine_identified_precondition(ctx),
            execute=lambda ctx: ctx.services._run_ssti_exploit_strategy(  # noqa: SLF001
                ctx.target,
                ctx.page_features,
            ),
        )
    )


def _register_api_injection_strategies(registry: "StrategyRegistry") -> None:
    """API / token injection (JWT, GraphQL, NoSQL)."""
    registry.register(
        StrategyDefinition(
            kind="jwt_manipulation",
            chain_name="jwt",
            precondition_description="请求/响应/Cookie 中存在 JWT 格式 token（eyJ...），或目标使用 JWT 认证。",
            minimal_experiment="尝试 alg:none、RS256→HS256 算法混淆、弱密钥爆破三种基础探测。",
            success_signal="JWT 篡改后获得认证绕过、权限提升或 verified flag。",
            failure_signal="三种基础探测均无法产生有效 token 或服务器始终拒绝。",
            escalation_condition="若算法混淆成功但无法出 flag，尝试结合 IDOR/BOLA 横向扩展。",
            precondition=lambda ctx: _jwt_precondition(ctx),
            execute=lambda ctx: _execute_jwt_probe(ctx),
        )
    )

    # P4: GraphQL introspection strategy
    registry.register(
        StrategyDefinition(
            kind="graphql_introspection",
            chain_name="graphql",
            precondition_description="发现 /graphql、/graphiql、/api/graphql 等端点，或响应含 GraphQL 错误格式。",
            minimal_experiment="发送内省查询获取完整 Schema，检查是否开放 mutation 和敏感字段。",
            success_signal="内省成功暴露管理 mutation、用户密码字段或直接返回 flag。",
            failure_signal="内省被禁用、Schema 无敏感字段、所有 probe 返回统一错误。",
            escalation_condition="内省被禁用时尝试批量查询深度 DoS 或 SQL 注入 via GraphQL。",
            precondition=lambda ctx: _graphql_precondition(ctx),
            execute=lambda ctx: _execute_graphql_probe(ctx),
        )
    )

    # P4: NoSQL injection strategy
    registry.register(
        StrategyDefinition(
            kind="nosql_injection",
            chain_name="nosql",
            precondition_description="存在 JSON/REST API 登录或查询端点，参数以 JSON 格式提交，疑似 MongoDB 后端。",
            minimal_experiment="尝试 {$ne: null}、{$gt: ''}、数组注入等 NoSQL 绕过 payload。",
            success_signal="认证绕过成功、返回异常数据量或直接拿到 verified flag。",
            failure_signal="所有 NoSQL payload 均被正确拒绝或返回统一错误。",
            escalation_condition="若基础绕过失败，尝试时间盲注或结合 JS 表达式注入。",
            precondition=lambda ctx: _nosql_precondition(ctx),
            execute=lambda ctx: _execute_nosql_probe(ctx),
        )
    )

    # 不安全反序列化策略（Java 检测 / Python pickle RCE）
    registry.register(
        StrategyDefinition(
            kind="insecure_deserialization",
            chain_name="web",
            precondition_description="cookie/参数/表单中出现 Java(rO0/\\xac\\xed)或 Python pickle(gA…)序列化 blob，或源码/页面含 pickle/ObjectInputStream/反序列化线索。",
            minimal_experiment="定位序列化载体；对 Python pickle 载体回灌 stdlib pickle gadget（读 flag + id），对 Java 载体沉淀漏洞 note。",
            success_signal="响应回显 verified/runtime flag，或出现 DESER_RCE_OK / uid= 等命令执行证据。",
            failure_signal="未发现序列化载体，或所有 pickle payload 回灌均无 flag/RCE 证据。",
            escalation_condition="Java 载体需外部 ysoserial gadget 链；pickle 盲打无回显时转向 OOB/时间盲注或 LLM 驱动探索。",
            precondition=lambda ctx: _deserialization_precondition(ctx),
            execute=lambda ctx: _execute_deserialization_probe(ctx),
        )
    )

    # XXE 注入策略（外部实体读取服务端文件 / SSRF 原语）
    registry.register(
        StrategyDefinition(
            kind="xxe_injection",
            chain_name="web",
            precondition_description="内容/响应头出现 XML 解析线索（<?xml、application/xml、SOAP/WSDL、<!DOCTYPE/<!ENTITY），或端点指向 /xml、/soap、/wsdl、.xml、xmlrpc。",
            minimal_experiment="向 XML 端点 POST 经典外部实体 DOCTYPE（<!ENTITY xxe SYSTEM \"file:///flag\">），用 application/xml 与 text/xml 两种 content-type 探读 flag / /etc/passwd。",
            success_signal="响应回显 verified/runtime flag，或出现 root:x:0:0:（外部实体文件读取证据）。",
            failure_signal="未发现 XML 端点，或所有外部实体 payload 均无 flag/文件读取回显。",
            escalation_condition="若实体被禁用或无回显，转向 OOB XXE（外带通道）、参数实体或 LLM 驱动探索。",
            precondition=lambda ctx: _xxe_precondition(ctx),
            execute=lambda ctx: _execute_xxe_probe(ctx),
        )
    )

    # 反射型 XSS 策略（客户端注入原语：未转义回显 canary 确认）
    registry.register(
        StrategyDefinition(
            kind="reflected_xss",
            chain_name="web",
            precondition_description="存在可注入查询参数面（带命名输入的 GET 表单或带 query 参数的链接），或内容含 search/关键词回显语义。",
            minimal_experiment="向每个反射面注入带唯一 marker 的 canary（<script>/<img onerror>/<svg onload>/\"><b>），观察 marker 是否在可执行 HTML 上下文中未转义回显。",
            success_signal="响应未转义回显 canary（证明客户端注入原语），或顺带回显 verified/runtime flag。",
            failure_signal="所有反射面 canary 均被实体编码（&lt;script&gt;）或无回显。",
            escalation_condition="确认反射但需取 flag 时，转 admin-bot / SID 窃取（xss_admin_bot_sid）或 OOB 外带。",
            precondition=lambda ctx: _reflected_xss_precondition(ctx),
            execute=lambda ctx: _execute_reflected_xss_probe(ctx),
        )
    )

    # IDOR 策略（授权缺陷：顺序对象 id 枚举出他人记录）
    registry.register(
        StrategyDefinition(
            kind="idor_sequential",
            chain_name="web",
            precondition_description="存在可枚举的数字对象 id 面（?id=42 类 query 参数、/user/42 类数字路径段，或 id 类命名 GET 表单输入）。",
            minimal_experiment="对每个对象面枚举相邻/低位 id（N±1、1/2/3），观察是否多个 id 返回不同的、内容丰富的成功对象（屏蔽回显 id 后比对去重）。",
            success_signal="两个及以上顺序 id 返回彼此不同的对象记录（证明对象引用可枚举且无授权校验），或顺带回显 verified/runtime flag。",
            failure_signal="所有 id 返回相同的拒绝/重定向页（屏蔽 id 后归一为单一 body）或无对象内容。",
            escalation_condition="确认枚举后，遍历 id 区间收集他人对象/凭据，或定位含 flag 的记录 id。",
            precondition=lambda ctx: _idor_precondition(ctx),
            execute=lambda ctx: _execute_idor_probe(ctx),
        )
    )

    # 开放重定向策略（客户端 URL 重定向：redirect 参数控制跳转目标）
    registry.register(
        StrategyDefinition(
            kind="open_redirect",
            chain_name="web",
            precondition_description="存在 redirect 类参数面（redirect/url/next/return/dest 等 query 参数或命名 GET 表单输入），或内容含重定向 sink 语义。",
            minimal_experiment="向每个 redirect 参数注入良性站外 canary（https://oob-<marker>.example.invalid/），观察 canary 是否落入重定向 sink：Location 头/重定向跳转，或 body 客户端 sink（meta refresh / window.location / location.href）。",
            success_signal="站外 canary 出现在 Location 头/重定向链，或 body 的客户端重定向 sink 中（证明开放重定向原语）。",
            failure_signal="所有 redirect 参数均被校验/剥离，站外 canary 不出现在任何重定向 sink。",
            escalation_condition="确认开放重定向后，构造钓鱼/OAuth token 泄露 pivot（站外接收）。",
            precondition=lambda ctx: _open_redirect_precondition(ctx),
            execute=lambda ctx: _execute_open_redirect_probe(ctx),
        )
    )

