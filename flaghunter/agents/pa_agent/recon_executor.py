"""Recon phase executor extracted from ctf_dispatcher.py.

P5 / Workstream A first slice (see
``docs/dev/FlagHunter_架构优化方案_黑板控制单元与façade收尾_2026-06-16_V1.md``):
the recon execution body is physically moved out of ``CTFTaskDispatcher`` into a
behaviour-preserving mixin. The method body is identical to the former
``CTFTaskDispatcher._phase_recon``; ``self.*`` resolves at runtime against the
dispatcher that mixes this in, so call sites (``coordinator._apply_recon_contract``
-> ``dispatcher._phase_recon``) are unchanged. Pure code relocation, near-zero risk.
"""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

from .ctf_planner import find_auth_form
from .dispatcher_helpers import (
    _BACKUP_CLUE_RE,
    _SCRIPT_SRC_RE,
    _collect_recon_error,
    _extract_title_from_html,
    _join_relative_url,
    _normalize_exploration_url,
    _normalize_target,
    _parse_forms_from_html,
    _pick_form_field,
    _strip_html_text,
)


class ReconExecutorMixin:
    """Recon phase orchestration extracted from the dispatcher."""

    async def _phase_recon(self, target: str) -> dict[str, Any]:
        features: dict[str, Any] = {
            "html": "",
            "content": "",
            "title": "",
            "forms": [],
            "cookies": "",
            "endpoints": [],
            "recon_errors": [],
            "recon_missing_tools": [],
            "url": target,
        }
        extra_blobs: list[str] = []
        if self.runtime is None:
            return features

        browser_probe: dict[str, Any] = {}
        if hasattr(self.runtime, "browser_action"):
            probe = await self._runtime_browser_action(
                "diagnose",
                timeout=5,
                audit_target=target,
                audit_metadata={"phase": "recon"},
            )
            if isinstance(probe, dict) and not probe.get("error") and probe.get("available", True):
                browser_probe = probe
                features["browser_probe"] = dict(probe)
                supported_actions = set(probe.get("supports_actions") or [])

                if "navigate" in supported_actions:
                    nav = await self._runtime_browser_action(
                        "navigate",
                        url=target,
                        timeout=10,
                        audit_target=target,
                        audit_metadata={"phase": "recon"},
                    )
                    if isinstance(nav, dict) and not nav.get("error"):
                        features["url"] = str(nav.get("url") or target)
                        features["title"] = str(nav.get("title") or "")
                    else:
                        _collect_recon_error(features, nav, "navigate")

                if "get_content" in supported_actions:
                    content = await self._runtime_browser_action(
                        "get_content",
                        timeout=10,
                        audit_target=str(features.get("url") or target),
                        audit_metadata={"phase": "recon"},
                    )
                    if isinstance(content, dict) and not content.get("error"):
                        features["html"] = str(content.get("html") or "")
                        features["content"] = str(content.get("content") or "")
                    else:
                        _collect_recon_error(features, content, "get_content")

                if "get_forms" in supported_actions:
                    forms = await self._runtime_browser_action(
                        "get_forms",
                        timeout=10,
                        audit_target=str(features.get("url") or target),
                        audit_metadata={"phase": "recon"},
                    )
                    if isinstance(forms, dict) and not forms.get("error"):
                        features["forms"] = forms.get("forms") or []
                    else:
                        _collect_recon_error(features, forms, "get_forms")

                if "get_cookies" in supported_actions:
                    cookies = await self._runtime_browser_action(
                        "get_cookies",
                        timeout=10,
                        audit_target=str(features.get("url") or target),
                        audit_metadata={"phase": "recon"},
                    )
                    if isinstance(cookies, dict) and not cookies.get("error"):
                        features["cookies"] = str(cookies.get("cookie_string") or "")
                    else:
                        _collect_recon_error(features, cookies, "get_cookies")
            elif self._is_legacy_browser_runtime_probe(probe):
                features["browser_probe"] = {
                    "available": True,
                    "mode": "legacy_runtime",
                    "supports_actions": ["navigate", "get_content", "get_forms", "get_cookies"],
                }
                nav = await self._runtime_browser_action(
                    "navigate",
                    url=target,
                    timeout=10,
                    audit_target=target,
                    audit_metadata={"phase": "recon"},
                )
                if isinstance(nav, dict) and not nav.get("error"):
                    features["url"] = str(nav.get("url") or target)
                    features["title"] = str(nav.get("title") or "")
                else:
                    _collect_recon_error(features, nav, "navigate")

                content = await self._runtime_browser_action(
                    "get_content",
                    timeout=10,
                    audit_target=str(features.get("url") or target),
                    audit_metadata={"phase": "recon"},
                )
                if isinstance(content, dict) and not content.get("error"):
                    features["html"] = str(content.get("html") or "")
                    features["content"] = str(content.get("content") or "")
                else:
                    _collect_recon_error(features, content, "get_content")

                forms = await self._runtime_browser_action(
                    "get_forms",
                    timeout=10,
                    audit_target=str(features.get("url") or target),
                    audit_metadata={"phase": "recon"},
                )
                if isinstance(forms, dict) and not forms.get("error"):
                    features["forms"] = forms.get("forms") or []
                else:
                    _collect_recon_error(features, forms, "get_forms")

                cookies = await self._runtime_browser_action(
                    "get_cookies",
                    timeout=10,
                    audit_target=str(features.get("url") or target),
                    audit_metadata={"phase": "recon"},
                )
                if isinstance(cookies, dict) and not cookies.get("error"):
                    features["cookies"] = str(cookies.get("cookie_string") or "")
                else:
                    _collect_recon_error(features, cookies, "get_cookies")
            else:
                _collect_recon_error(features, probe, "browser_diagnose")

        if hasattr(self.runtime, "proxy_action"):
            page = await self._proxy_get_with_retry(
                features["url"],
                timeout=10,
                audit_target=str(features.get("url") or target),
                audit_metadata={"phase": "recon"},
            )
            if isinstance(page, dict) and not page.get("error"):
                headers = page.get("headers")
                if isinstance(headers, dict):
                    normalized_headers = {str(k).lower(): str(v) for k, v in headers.items()}
                    features.setdefault("headers", {}).update(normalized_headers)
                    if not features["cookies"]:
                        set_cookie = normalized_headers.get("set-cookie")
                        if set_cookie:
                            features["cookies"] = str(set_cookie)
                body = str(page.get("body") or "")
                if body:
                    if not features["html"]:
                        features["html"] = body
                    if not features["content"]:
                        features["content"] = _strip_html_text(body)
                    if not features["forms"]:
                        features["forms"] = _parse_forms_from_html(body, features["url"])
                    if body not in features["content"]:
                        extra_blobs.append(body)

                script_sources = []
                merged_html = features["html"] or body
                for src in _SCRIPT_SRC_RE.findall(merged_html):
                    absolute = urljoin(features["url"], src.strip())
                    if absolute not in script_sources:
                        script_sources.append(absolute)

                for script_url in script_sources[:3]:
                    script_resp = await self._runtime_proxy_action(
                        "get",
                        url=script_url,
                        timeout=10,
                        audit_target=script_url,
                        audit_metadata={"phase": "recon", "script_source": True},
                    )
                    if isinstance(script_resp, dict) and not script_resp.get("error"):
                        script_body = str(script_resp.get("body") or "")
                        if script_body:
                            extra_blobs.append(script_body)
                    else:
                        _collect_recon_error(features, script_resp, f"script:{script_url}")
            else:
                _collect_recon_error(features, page, "proxy_get")

        if features["html"] and not features["forms"]:
            features["forms"] = _parse_forms_from_html(
                str(features["html"]), features["url"]
            )
        if features["html"] and not features["content"]:
            features["content"] = _strip_html_text(str(features["html"]))
        if browser_probe and not features["content"] and features["html"]:
            features["content"] = _strip_html_text(str(features["html"]))

        post_auth = await self._attempt_post_auth_recon(target, features)
        if post_auth:
            features["pre_auth_url"] = str(features.get("url") or target)
            features["pre_auth_html"] = str(features.get("html") or "")
            features["pre_auth_content"] = str(features.get("content") or "")
            features["pre_auth_forms"] = list(features.get("forms") or [])
            features["url"] = str(post_auth.get("url") or features.get("url") or target)
            features["html"] = str(post_auth.get("html") or features.get("html") or "")
            features["content"] = str(
                post_auth.get("content") or features.get("content") or ""
            )
            features["forms"] = list(post_auth.get("forms") or [])
            features["title"] = str(post_auth.get("title") or features.get("title") or "")
            features["auth_bootstrap"] = {
                "success": True,
                "url": str(post_auth.get("url") or ""),
                "username": str(post_auth.get("username") or ""),
            }
            if self.state is not None:
                self.state.add_observation(
                    "post_auth_recon",
                    str(post_auth.get("url") or ""),
                    source="phase_recon",
                    metadata={
                        "username": str(post_auth.get("username") or ""),
                        "endpoints_hint": list(post_auth.get("raw_links") or []),
                    },
                )
            await self._store_note(
                key="ctf_post_auth_recon",
                value=(
                    f"post-auth recon reached {post_auth.get('url')}; "
                    f"username={post_auth.get('username')}"
                ),
                category="finding",
                target=urlparse(str(post_auth.get("url") or target)).netloc or target,
                url=str(post_auth.get("url") or target),
            )

        merged_source = "\n".join(
            part
            for part in [features["html"], features["content"], *extra_blobs]
            if part
        )
        endpoint_candidates = re.findall(
            r'(?:(?<=^)|(?<=[\s"\'(=]))(/(?:[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*))',
            merged_source,
        )
        features["endpoints"] = sorted(
            {
                candidate
                for candidate in endpoint_candidates
                if not self._should_ignore_exploration_candidate(
                    candidate,
                    base_url=str(features.get("url") or target),
                )
            }
        )
        # P3: 保留完整 href（含 query string），供 HypothesisEngine 检测 filename+filehash 参数
        raw_links: list[str] = []
        for href in re.findall(r'href=["\']([^"\'<>]+)["\']', merged_source, re.IGNORECASE):
            href = href.strip()
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            absolute = _normalize_exploration_url(_join_relative_url(features["url"], href))
            if self._should_ignore_exploration_candidate(absolute, base_url=features["url"]):
                continue
            if absolute not in raw_links:
                raw_links.append(absolute)
        # 也从 <a href> 和 action= 属性里提取
        for action in re.findall(r'action=["\']([^"\'<>]+)["\']', merged_source, re.IGNORECASE):
            action = action.strip()
            if action and not action.startswith(("#", "javascript:")):
                absolute = _normalize_exploration_url(_join_relative_url(features["url"], action))
                if self._should_ignore_exploration_candidate(absolute, base_url=features["url"]):
                    continue
                if absolute not in raw_links:
                    raw_links.append(absolute)
        for discovered in self._extract_embedded_links(merged_source, str(features.get("url") or target)):
            if discovered not in raw_links:
                raw_links.append(discovered)
        features["raw_links"] = raw_links
        if features["recon_errors"]:
            self._emit(
                "[CTF dispatcher] recon warnings: "
                + " | ".join(features["recon_errors"][:4])
            )
        content_lower = f"{features.get('html', '')}\n{features.get('content', '')}".lower()
        backup_clue = bool(_BACKUP_CLUE_RE.search(content_lower))
        visit_admin_clue = "/visit" in features["endpoints"] and "/admin" in features["endpoints"]
        if self.state is not None:
            self.state.add_observation(
                "recon_url",
                str(features.get("url") or target),
                source="phase_recon",
                metadata={
                    "forms": len(features.get("forms") or []),
                    "forms_detail": list(features.get("forms") or []),
                    "endpoints": list(features.get("endpoints") or []),
                    "raw_links": list(features.get("raw_links") or []),
                    "content_preview": str(features.get("content") or "")[:500],
                    "recon_errors": list(features.get("recon_errors") or []),
                    "backup_clue": backup_clue,
                    "visit_admin_clue": visit_admin_clue,
                },
            )
            self._fingerprint_framework(features)
            self._populate_exploration_agenda_from_recon(target, features)
            self.reasoning_layer.record_interpretation(
                self.state,
                observation_ids=["obs:recon_url"],
                content=(
                    f"侦察阶段确认页面更接近 {self.state.detected_type or 'web'} 题面，"
                    f"forms={len(features.get('forms') or [])} endpoints={len(features.get('endpoints') or [])}"
                ),
                hypothesis_ids=[],
                confidence=0.55,
            )
        await self._store_note(
            key="ctf_runtime_fingerprint",
            value=(
                f"url={features['url']}\n"
                f"title={features['title']}\n"
                f"endpoints={features['endpoints']}\n"
                f"cookies={features['cookies']}\n"
                f"recon_errors={features['recon_errors']}"
            ),
            category="finding",
            target=urlparse(features["url"]).netloc or features["url"],
            url=features["url"],
            endpoints=features["endpoints"],
        )
        return features

    def _candidate_auth_page_urls(
        self,
        target: str,
        features: dict[str, Any],
    ) -> list[str]:
        """Auth-page URLs to probe when the landing page has no auth form.

        Drawn from recon-scraped links and the exploration agenda (any path
        mentioning login/register/signin/signup), plus the conventional
        ``/register`` and ``/login`` fallbacks so the flow works even when the
        homepage links nothing scrapable.
        """
        base = str(features.get("url") or target or "")
        urls: list[str] = []
        seen: set[str] = set()

        def add(candidate: str) -> None:
            normalized = _normalize_exploration_url(str(candidate or "").strip())
            if not normalized:
                return
            # Dedupe across default-port variants (http://h/login vs http://h:80/login)
            # so we don't fetch the same auth page twice.
            parsed = urlparse(normalized)
            netloc = parsed.netloc
            if parsed.scheme == "http" and netloc.endswith(":80"):
                netloc = netloc[:-3]
            elif parsed.scheme == "https" and netloc.endswith(":443"):
                netloc = netloc[:-4]
            key = parsed._replace(netloc=netloc).geturl()
            if key not in seen:
                seen.add(key)
                urls.append(key)

        pool = list(features.get("raw_links") or [])
        if self.state is not None:
            pool += [item.url_or_path for item in self.state.exploration_agenda]
        for candidate in pool:
            path = urlparse(str(candidate)).path.lower()
            if any(token in path for token in ("login", "register", "signin", "signup")):
                add(str(candidate))
        # Register first (must create the account before logging in), then login.
        for route in ("/register", "/login"):
            add(_join_relative_url(base, route))
        return urls[:4]

    async def _harvest_auth_forms_from_routes(
        self,
        target: str,
        features: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """GET candidate auth pages and return any forms found on them.

        Form actions are resolved absolute against the page they came from, so
        the downstream submit logic targets /login and /register correctly even
        though recon was anchored at the homepage.
        """
        if self.runtime is None or not hasattr(self.runtime, "proxy_action"):
            return []
        harvested: list[dict[str, Any]] = []
        for url in self._candidate_auth_page_urls(target, features):
            try:
                resp = await self._runtime_proxy_action(
                    "get",
                    url=url,
                    timeout=10,
                    audit_target=url,
                    audit_metadata={"phase": "post_auth_recon", "stage": "harvest_form"},
                )
            except Exception:
                continue
            if not isinstance(resp, dict) or resp.get("error"):
                continue
            body = str(resp.get("body") or "")
            if not body:
                continue
            page_url = str(resp.get("final_url") or url).strip() or url
            harvested.extend(_parse_forms_from_html(body, page_url))
        return harvested

    async def _attempt_post_auth_recon(
        self,
        target: str,
        features: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self.runtime is None or not hasattr(self.runtime, "proxy_action"):
            return None
        forms = list(features.get("forms") or [])
        auth_form = find_auth_form(forms)
        if not auth_form:
            # The landing page often has no auth form — the login/register forms
            # live on /login and /register (Laravel, and most framework apps).
            # Harvest forms from the conventional auth routes so the
            # register→login→re-recon flow still fires instead of stalling the
            # moment the homepage yields no form.
            harvested = await self._harvest_auth_forms_from_routes(target, features)
            if harvested:
                forms = harvested
                auth_form = find_auth_form(forms)
        if not auth_form:
            return None

        method = str(auth_form.get("method") or "GET").upper()
        if method != "POST":
            return None

        username_field = _pick_form_field(auth_form, "username")
        password_field = _pick_form_field(auth_form, "password")
        if not username_field or not password_field:
            return None

        submission: dict[str, str] = {}
        for inp in auth_form.get("inputs") or []:
            if not isinstance(inp, dict):
                continue
            name = str(inp.get("name") or "").strip()
            if not name:
                continue
            field_type = str(inp.get("type") or "text").strip().lower()
            if field_type in {"submit", "button", "image", "reset", "file"}:
                continue
            submission[name] = str(inp.get("value") or "")

        seed = int(time.time() * 1000) % 1_000_000
        username = f"ctf_probe_{seed:06d}"
        email = f"{username}@example.com"
        password = f"Pw{seed:06d}!"
        submission[username_field] = email if "email" in username_field.lower() else username
        submission[password_field] = password
        if email_field := _pick_form_field(auth_form, "email"):
            submission[email_field] = email

        # 真实站点里 browser 渲染态与 proxy session 可能不是同一个 cookie jar。
        # 对 Django/Flask 一类表单先用 proxy GET 预热一次，拿到同 session 的 CSRF cookie，
        # 并尽量用该响应里的 hidden token 覆盖提交值，避免把 403 CSRF 页面误判成登录成功。
        try:
            primed = await self._runtime_proxy_action(
                "get",
                url=target,
                timeout=10,
                audit_target=target,
                audit_metadata={"phase": "post_auth_recon", "stage": "prime"},
            )
        except Exception:
            primed = None
        if isinstance(primed, dict) and not primed.get("error"):
            primed_body = str(primed.get("body") or "")
            primed_url = str(primed.get("final_url") or target).strip() or target
            primed_form = find_auth_form(_parse_forms_from_html(primed_body, primed_url))
            if primed_form:
                for inp in primed_form.get("inputs") or []:
                    if not isinstance(inp, dict):
                        continue
                    name = str(inp.get("name") or "").strip()
                    if not name or name not in submission:
                        continue
                    field_type = str(inp.get("type") or "text").strip().lower()
                    if field_type == "hidden":
                        submission[name] = str(inp.get("value") or "")

        register_form = self._find_registration_form(forms, login_form=auth_form)
        if register_form is not None:
            register_submission = self._build_account_form_submission(
                register_form,
                username=username,
                email=email,
                password=password,
            )
            register_url = self._form_action_url(str(features.get("url") or target), register_form)
            try:
                await self._runtime_proxy_action(
                    "request",
                    method=str(register_form.get("method") or "POST").upper(),
                    url=register_url,
                    data=register_submission,
                    timeout=15,
                    audit_target=register_url,
                    audit_metadata={"phase": "post_auth_recon", "stage": "register"},
                )
            except Exception:
                pass

        action_url = self._form_action_url(str(features.get("url") or target), auth_form)
        response = await self._runtime_proxy_action(
            "request",
            method="POST",
            url=action_url,
            data=submission,
            timeout=15,
            audit_target=action_url,
            audit_metadata={"phase": "post_auth_recon", "stage": "login"},
        )
        status_code = int(response.get("status_code") or 0)
        if not isinstance(response, dict) or response.get("error") or (400 <= status_code < 600):
            return None

        post_body = str(response.get("body") or "")
        final_url = str(response.get("final_url") or action_url or target).strip() or target

        follow_body = post_body
        follow_url = final_url
        if final_url:
            follow = await self._runtime_proxy_action(
                "get",
                url=final_url,
                timeout=10,
                audit_target=final_url,
                audit_metadata={"phase": "post_auth_recon", "stage": "follow"},
            )
            if isinstance(follow, dict) and not follow.get("error"):
                follow_url = str(follow.get("final_url") or final_url or target).strip() or target
                follow_body = str(follow.get("body") or "") or post_body

        follow_forms = _parse_forms_from_html(follow_body, follow_url)
        follow_content = _strip_html_text(follow_body)
        follow_links = self._extract_embedded_links(follow_body, follow_url)
        follow_title = _extract_title_from_html(follow_body)

        success_markers = (
            "/logout",
            "flag?token=",
            "/flag?token=",
            "/contact",
            "/urlstorage",
            "your status:",
            "get flag",
            "store your url",
        )
        combined = f"{follow_body}\n{follow_content}".lower()
        redirected = _normalize_target(follow_url).rstrip("/") != _normalize_target(
            str(features.get("url") or target)
        ).rstrip("/")
        set_cookie_lower = str(response.get("headers", {}).get("set-cookie") or "").lower()
        has_session_cookie = any(
            token in set_cookie_lower
            for token in ("sessionid=", "laravel_session=", "_session_id=", "connect.sid=", "jsessionid=")
        )
        has_success_marker = any(marker in combined for marker in success_markers)
        auth_form_gone = find_auth_form(follow_forms) is None
        obvious_failure_markers = (
            "csrf verification failed",
            "request aborted",
            "forbidden (403)",
            "403 forbidden",
            "permission denied",
            "login failed",
            "invalid credentials",
            "email not registered",
            "email not registed",
            "not registered",
            "not registed",
            "email illegal",
        )
        has_obvious_failure = any(marker in combined for marker in obvious_failure_markers)

        if has_obvious_failure:
            return None

        if not any([redirected, has_session_cookie, has_success_marker, auth_form_gone]):
            return None

        return {
            "url": follow_url,
            "html": follow_body,
            "content": follow_content,
            "forms": follow_forms,
            "raw_links": follow_links,
            "title": follow_title,
            "username": username,
        }

    def _find_registration_form(
        self,
        forms: list[dict[str, Any]],
        *,
        login_form: dict[str, Any],
    ) -> dict[str, Any] | None:
        login_action = str(login_form.get("action") or "").strip()
        for form in forms:
            if not isinstance(form, dict):
                continue
            method = str(form.get("method") or "GET").strip().upper()
            if method != "POST":
                continue
            inputs = [item for item in form.get("inputs") or [] if isinstance(item, dict)]
            names = {str(item.get("name") or "").strip().lower() for item in inputs}
            action = str(form.get("action") or "").strip()
            action_lower = action.lower()
            if action == login_action and form is login_form:
                continue
            has_password = any(str(item.get("type") or "").lower() == "password" for item in inputs)
            has_email = any("email" in name for name in names)
            has_username = any(
                token in name
                for name in names
                for token in ("user", "name", "login")
            )
            looks_like_register = any(
                token in action_lower
                for token in ("register", "signup", "sign-up", "regist")
            )
            if has_password and has_email and (has_username or looks_like_register):
                return form
        return None

    def _build_account_form_submission(
        self,
        form: dict[str, Any],
        *,
        username: str,
        email: str,
        password: str,
    ) -> dict[str, str]:
        submission: dict[str, str] = {}
        for inp in form.get("inputs") or []:
            if not isinstance(inp, dict):
                continue
            name = str(inp.get("name") or "").strip()
            if not name:
                continue
            field_type = str(inp.get("type") or "text").strip().lower()
            if field_type in {"submit", "button", "image", "reset", "file"}:
                continue
            lowered = name.lower()
            value = str(inp.get("value") or "")
            if field_type == "password" or "pass" in lowered:
                value = password
            elif "email" in lowered:
                value = email
            elif any(token in lowered for token in ("user", "name", "login")):
                value = username
            submission[name] = value
        return submission

    def _populate_exploration_agenda_from_recon(
        self,
        target: str,
        features: dict[str, Any],
    ) -> None:
        if self.state is None:
            return

        current_url = str(features.get("url") or target or "").strip()
        # raw_links 保留完整 query string，优先检查；endpoints 作为补充（无 query）
        raw_links = list(features.get("raw_links") or [])
        plain_endpoints = list(features.get("endpoints") or [])
        # 去重：raw_links 里已包含 path 部分的优先用 raw_links
        raw_paths = {urlparse(u).path for u in raw_links if u}
        endpoints_extra = [e for e in plain_endpoints if e not in raw_paths]
        candidates = [current_url, *raw_links, *endpoints_extra]

        for candidate in candidates:
            text = str(candidate or "").strip()
            if not text:
                continue
            if self._should_ignore_exploration_candidate(text, base_url=current_url):
                continue
            discovery_source = "recon_url" if text == current_url else "link_href"
            self.state.add_exploration_item(
                text,
                discovery_source=discovery_source,
                hint_strength=self._classify_exploration_hint_strength(text, discovery_source),
            )

        self._seed_framework_conventional_routes(current_url or target)

    def _seed_framework_conventional_routes(self, base_url: str) -> None:
        """Seed conventional entry routes for any fingerprinted framework.

        Recon's link scrape depends on a usable response body, but CTF instances
        frequently serve an empty/booting body on the first hit even though the
        cookies/headers that drive ``_fingerprint_framework`` come through fine.
        Seeding the detected framework's well-known routes (``/login``,
        ``/register``, ``/admin`` …) keeps the agent on the app's real entry
        points instead of degrading to blind backup/dotfile guessing when the
        landing page yields no scrapable links.
        """
        if self.state is None:
            return
        base = str(base_url or "").strip()
        if not base:
            return
        # Normalize the base to drop the default port so seeded routes dedupe
        # with scraped absolute links (which usually omit :80 / :443).
        parsed = urlparse(base)
        netloc = parsed.netloc
        if parsed.scheme == "http" and netloc.endswith(":80"):
            netloc = netloc[:-3]
        elif parsed.scheme == "https" and netloc.endswith(":443"):
            netloc = netloc[:-4]
        clean_base = parsed._replace(netloc=netloc).geturl()
        frameworks = {
            str(getattr(o, "value", "")).lower()
            for o in self.state.observations
            if str(getattr(o, "kind", "")) == "framework_detected"
        }
        for framework in frameworks:
            for route in self._FRAMEWORK_CONVENTIONAL_ROUTES.get(framework, ()):
                absolute = _normalize_exploration_url(_join_relative_url(clean_base, route))
                if self._should_ignore_exploration_candidate(absolute, base_url=clean_base):
                    continue
                self.state.add_exploration_item(
                    absolute,
                    discovery_source="framework_convention",
                    hint_strength=2,
                )

    async def _explore_agenda_items(self, target: str, items: list[Any]) -> bool:
        if self.state is None:
            return False

        progress = False
        for item in items:
            absolute = urljoin(target, item.url_or_path)
            if self.runtime is None or not hasattr(self.runtime, "proxy_action"):
                item.explored = True
                item.exploration_result = "proxy runtime unavailable"
                continue

            try:
                response = await self.runtime.proxy_action("get", url=absolute, timeout=10)
            except Exception as exc:
                response = {"error": str(exc)}

            if isinstance(response, dict) and not response.get("error"):
                body = str(response.get("body") or "")
                status_code = response.get("status_code")
                item.explored = True
                item.exploration_result = f"status={status_code} body_len={len(body)}"
                self.state.add_observation(
                    "agenda_exploration",
                    absolute,
                    source="exploration_agenda",
                    metadata={
                        "url_or_path": item.url_or_path,
                        "status_code": status_code,
                        "body_length": len(body),
                    },
                )
                if body:
                    await self._scan_and_store(
                        body,
                        absolute,
                        evidence_source="response_body",
                        page_features=None,
                    )
                    progress = True
                continue

            item.explored = True
            item.exploration_result = str((response or {}).get("error") or "exploration failed")

        return progress

