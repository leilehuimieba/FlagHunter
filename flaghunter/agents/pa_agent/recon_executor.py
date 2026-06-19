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
from typing import Any
from urllib.parse import urljoin, urlparse

from .dispatcher_helpers import (
    _BACKUP_CLUE_RE,
    _SCRIPT_SRC_RE,
    _collect_recon_error,
    _join_relative_url,
    _normalize_exploration_url,
    _parse_forms_from_html,
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
