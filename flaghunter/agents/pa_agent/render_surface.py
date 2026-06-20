"""Render-surface URL / response-fingerprint mixin extracted from ctf_dispatcher.py.

P5 / thirteenth cut: the 9-method render-surface heuristics block (~192
lines) is physically moved out of CTFTaskDispatcher into a
behaviour-preserving mixin. These methods build/normalize render-surface
URLs, track per-strategy surface exhaustion via state observations,
fingerprint responses, inject render payloads and harvest cookie-secret /
candidate-filename hints — a cohesive cluster of URL/response heuristics
over ``self.state`` with zero coupling to the strategy registry.

Method bodies are identical; all ``self.*`` access (``self.state`` and the
intra-cluster ``_normalize_render_surface_url`` /
``_was_strategy_surface_exhausted`` calls) resolves at runtime via the MRO
of the dispatcher that mixes this in, so every call site is unchanged. The
only module-level symbols referenced are ``re`` and ``urllib.parse``
helpers — no constants to sink, no circular-import risk. The adjacent
strategy-context pair (``_strategy_context`` / ``_strategies_for_chain``)
is intentionally left on the dispatcher: it couples to ``StrategyContext`` /
``self.strategy_registry`` and is a better companion to a future
strategy-registry-adjacent extraction. Pure code relocation, near-zero risk.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse


class RenderSurfaceMixin:
    """Render-surface URL normalization, exhaustion tracking and response fingerprinting."""

    def _collect_render_surface_urls(
        self,
        base: str,
        page_features: dict[str, Any],
    ) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()
        seed_values = list(page_features.get("raw_links") or [])
        if self.state is not None:
            for observation in self.state.observations:
                if isinstance(observation.metadata, dict):
                    for key in ("url", "final_url"):
                        value = str(observation.metadata.get(key) or "").strip()
                        if value:
                            seed_values.append(value)
                    for item in list(observation.metadata.get("redirect_history") or []):
                        if isinstance(item, dict):
                            for key in ("url", "location"):
                                value = str(item.get(key) or "").strip()
                                if value:
                                    seed_values.append(value)
                seed_values.append(str(observation.value or "").strip())

        for raw in seed_values:
            text = str(raw or "").strip()
            if not text:
                continue
            absolute = urljoin(base + "/", text)
            parsed = urlparse(absolute)
            params = set(parse_qs(parsed.query).keys())
            if params.intersection({"msg", "message", "error", "render", "template"}):
                normalized = self._normalize_render_surface_url(absolute)
                if normalized not in seen:
                    seen.add(normalized)
                    candidates.append(normalized)
            elif "render" in text.lower() and urljoin(base + "/", "error?msg=Error") not in seen:
                fallback = urljoin(base + "/", "error?msg=Error")
                seen.add(fallback)
                candidates.append(fallback)

        fallback = urljoin(base + "/", "error?msg=Error")
        if fallback not in seen:
            candidates.append(fallback)
        return candidates

    def _normalize_render_surface_url(self, candidate_url: str) -> str:
        parsed = urlparse(candidate_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        normalized_keys = ("msg", "message", "error", "render", "template")
        changed = False
        for key in normalized_keys:
            if key in params:
                params[key] = ["Error"]
                changed = True
        if not changed:
            return candidate_url
        return parsed._replace(query=urlencode(params, doseq=True)).geturl()

    def _strategy_surface_signature(
        self,
        strategy_kind: str,
        values: list[str],
    ) -> str:
        normalized = [str(value or "").strip() for value in values if str(value or "").strip()]
        unique = sorted(dict.fromkeys(normalized))
        return f"{strategy_kind}::" + "||".join(unique)

    def _was_strategy_surface_exhausted(
        self,
        strategy_kind: str,
        signature: str,
    ) -> bool:
        if self.state is None:
            return False
        for observation in reversed(self.state.observations):
            if observation.kind != "strategy_surface_exhausted":
                continue
            metadata = observation.metadata if isinstance(observation.metadata, dict) else {}
            if str(metadata.get("strategy_kind") or "") != strategy_kind:
                continue
            if str(metadata.get("signature") or "") == signature:
                return True
        return False

    def _mark_strategy_surface_exhausted(
        self,
        strategy_kind: str,
        signature: str,
        **metadata: Any,
    ) -> None:
        if self.state is None:
            return
        if self._was_strategy_surface_exhausted(strategy_kind, signature):
            return
        self.state.add_observation(
            "strategy_surface_exhausted",
            strategy_kind,
            source="dispatcher",
            metadata={
                "strategy_kind": strategy_kind,
                "signature": signature,
                **metadata,
            },
        )

    def _response_fingerprint(self, body: str, status: int) -> str:
        plain = re.sub(r"<[^>]+>", " ", str(body or ""))
        normalized = re.sub(r"\s+", " ", plain).strip().lower()
        if len(normalized) > 80:
            normalized = normalized[:80]
        return f"{status}:{normalized}"

    def _inject_render_payload(self, candidate_url: str, payload: str) -> str:
        parsed = urlparse(candidate_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        for key in ("msg", "message", "error", "render", "template", "name"):
            if key in params:
                params[key] = [payload]
                return parsed._replace(query=urlencode(params, doseq=True)).geturl()
        params["msg"] = [payload]
        return parsed._replace(query=urlencode(params, doseq=True)).geturl()

    def _extract_cookie_secret_candidate(
        self,
        body: str,
        *,
        baseline_tokens: set[str] | None = None,
    ) -> str | None:
        plain = re.sub(r"<[^>]+>", " ", str(body or ""))
        known_tokens = set(baseline_tokens or set())
        common_skip = {
            "html", "body", "head", "title", "div", "span", "script", "style",
            "error", "file", "hash", "test", "probe", "true", "false", "null",
            "http", "https", "filehash", "filename", "handler", "settings",
            "cookie", "secret", "cookie_secret", "render", "msg", "message",
        }
        uuid_match = re.search(
            r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
            plain,
            re.IGNORECASE,
        )
        if uuid_match:
            return uuid_match.group(1)

        hex32_match = re.search(r"\b([0-9a-f]{32})\b", plain, re.IGNORECASE)
        if hex32_match and hex32_match.group(1) not in known_tokens:
            return hex32_match.group(1)

        for token in re.findall(r"[A-Za-z0-9_@#$%^&*!+\-]{4,64}", plain):
            if token in known_tokens:
                continue
            if token.lower() in common_skip:
                continue
            if token == "49":
                continue
            return token
        return None

    def _collect_candidate_filenames(self) -> list[str]:
        candidates: list[str] = ["/flag.txt", "/flag", "/flag.php", "/secret", "/hints.txt", "/index.php"]
        if self.state is None:
            return candidates
        sentence_patterns = (
            r"(?:flag|在|in|is\s+at|at|see|check|file\s+is)\s+([/][^\s<>\"']+)",
            r"(?:cat|view|read)\s+([/][^\s<>\"']+)",
        )
        for observation in self.state.observations:
            text = str(observation.value or "")
            for match in re.findall(r"(/[-A-Za-z0-9_./]{3,})", text):
                if not match.startswith("/"):
                    continue
                normalized = match.rstrip(".,;:!?)\"]'")
                if normalized and normalized not in candidates:
                    candidates.append(normalized)
            for pattern in sentence_patterns:
                for match in re.findall(pattern, text, flags=re.IGNORECASE):
                    normalized = str(match or "").strip().rstrip(".,;:!?)\"]'")
                    if normalized.startswith("/") and normalized not in candidates:
                        candidates.append(normalized)
            for candidate_url in re.findall(r"https?://[^\s\"'<>]+", text):
                parsed = urlparse(candidate_url)
                for values in parse_qs(parsed.query, keep_blank_values=True).values():
                    for value in values:
                        normalized = str(value or "").strip()
                        if not normalized or normalized.startswith("php://"):
                            continue
                        if not normalized.startswith("/"):
                            normalized = "/" + normalized.lstrip("/")
                        if normalized not in candidates:
                            candidates.append(normalized)
        return candidates
