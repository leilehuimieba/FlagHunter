"""Platform-context snapshot / challenge-alignment mixin extracted from ctf_dispatcher.py.

P5 / Workstream A: the contiguous platform helper cluster (5 methods,
_snapshot_platform_context .. _build_already_solved_reason) is physically moved
out of CTFTaskDispatcher into a behaviour-preserving mixin. Method bodies are
identical; self.* (state, platform_orchestrator) resolves at runtime against the
dispatcher that mixes this in, so call sites are unchanged. The flag-submitter
imports stay in-method (dynamic) as before. Pure code relocation, near-zero risk.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import parse_qs, urlparse


class PlatformExecutorMixin:
    """Platform profile inference, sync snapshot and challenge alignment."""

    async def _snapshot_platform_context(self, target: str) -> None:
        if self.state is None:
            return
        profile = self._infer_platform_profile(target)
        self.state.meta_reasonings.append(
            {
                "type": "platform_profile_snapshot",
                **profile,
            }
        )
        if not profile.get("auto_submit"):
            return
        if str(profile.get("platform_type") or "manual").lower() == "manual":
            return
        base_url = str(profile.get("base_url") or "").strip()
        if not base_url:
            return
        try:
            from flaghunter.cpa_modules.m2_ctf_kit.flag_submitter import get_platform_snapshot

            snapshot = await get_platform_snapshot(
                platform_type=str(profile.get("platform_type") or "manual"),
                base_url=base_url,
                api_key=profile.get("api_key"),
                auth_token=profile.get("auth_token"),
            )
            self.state.meta_reasonings.append(
                {
                    "type": "platform_sync_snapshot",
                    **snapshot,
                }
            )
            queue_snapshot = self.platform_orchestrator.build_queue_snapshot(
                platform_type=str(profile.get("platform_type") or "manual"),
                base_url=base_url,
                challenge_briefs=list(snapshot.get("challenge_briefs") or []),
                current_challenge_id=str(profile.get("challenge_id") or "").strip() or None,
                submit_attempts=[
                    item
                    for item in self.state.meta_reasonings
                    if isinstance(item, dict)
                ],
            )
            self.state.meta_reasonings.append(
                {
                    "type": "platform_task_queue_snapshot",
                    **queue_snapshot.to_dict(),
                }
            )
        except Exception as exc:
            self.state.meta_reasonings.append(
                {
                    "type": "platform_sync_snapshot",
                    "success": False,
                    "platform_type": profile.get("platform_type"),
                    "base_url": base_url,
                    "error": str(exc),
                }
            )

    def _infer_platform_profile(self, target: str) -> dict[str, Any]:
        env_profile: dict[str, str] = {}
        detected_platform = "manual"
        submit_base = str(self.state.submit_base_url or "").strip() if self.state is not None else ""
        try:
            from flaghunter.cpa_modules.m2_ctf_kit.flag_submitter import (
                detect_platform_from_url,
                load_platform_from_env,
            )

            env_profile = load_platform_from_env()
            detected_platform = detect_platform_from_url(submit_base or target)
        except Exception:
            env_profile = {}

        challenge_id = self._infer_challenge_id(
            target,
            explicit=(self.state.submit_challenge_id if self.state is not None else None),
            env_value=env_profile.get("challenge_id") or os.environ.get("CPA_CTF_CHALLENGE_ID", ""),
        )
        env_platform_type = str(env_profile.get("platform_type") or "").strip()
        platform_type = (
            str(self.state.submit_platform_type or "").strip()
            if self.state is not None and self.state.submit_platform_type
            else (
                detected_platform
                if detected_platform and detected_platform != "manual"
                else (env_platform_type or detected_platform or "manual").strip()
            )
        )
        base_url = submit_base or str(env_profile.get("base_url") or "").strip()
        if not base_url:
            parsed = urlparse(target)
            if parsed.scheme and parsed.netloc:
                base_url = f"{parsed.scheme}://{parsed.netloc}"
        auto_submit = False
        if self.state is not None and self.state.submit_auto:
            auto_submit = True
        else:
            auto_submit = str(env_profile.get("auto_submit", "")).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        return {
            "platform_type": platform_type or "manual",
            "base_url": base_url,
            "challenge_id": challenge_id,
            "auto_submit": auto_submit,
            "api_key": str(self.state.submit_api_key or env_profile.get("api_key") or "").strip()
            if self.state is not None
            else str(env_profile.get("api_key") or "").strip(),
            "auth_token": str(self.state.submit_auth_token or env_profile.get("auth_token") or "").strip()
            if self.state is not None
            else str(env_profile.get("auth_token") or "").strip(),
            "target": target,
        }

    def _infer_challenge_id(
        self,
        target: str,
        *,
        explicit: str | None,
        env_value: str | None,
    ) -> str | None:
        if explicit and str(explicit).strip():
            return str(explicit).strip()
        if env_value and str(env_value).strip():
            return str(env_value).strip()

        parsed = urlparse(target)
        params = parse_qs(parsed.query)
        for key in ("challenge_id", "cid", "id", "task_id", "room_code"):
            values = params.get(key) or params.get(key.upper()) or []
            if values and str(values[0]).strip():
                return str(values[0]).strip()

        fragment = str(parsed.fragment or "")
        frag_match = re.search(r"(?:challenge[-_=]?|task[-_=]?|id[-_=]?)([A-Za-z0-9_-]+)", fragment, re.IGNORECASE)
        if frag_match:
            return frag_match.group(1)

        path_parts = [part for part in parsed.path.split("/") if part]
        for part in reversed(path_parts):
            token = str(part).strip()
            if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", token):
                return token
        return None

    def _align_platform_challenge(
        self,
        target: str,
        page_features: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self.state is None:
            return None

        snapshot = None
        profile = None
        for item in reversed(self.state.meta_reasonings):
            if not isinstance(item, dict):
                continue
            if snapshot is None and item.get("type") == "platform_sync_snapshot":
                snapshot = item
            if profile is None and item.get("type") == "platform_profile_snapshot":
                profile = item
            if snapshot and profile:
                break
        if not snapshot or not profile:
            return None

        challenge_briefs = list(snapshot.get("challenge_briefs") or [])
        if not challenge_briefs:
            return None

        explicit_id = str(
            self.state.submit_challenge_id
            or profile.get("challenge_id")
            or ""
        ).strip()
        if explicit_id:
            for item in challenge_briefs:
                if str(item.get("id") or "").strip() == explicit_id:
                    return {
                        "matched": True,
                        "match_reason": "challenge_id_exact",
                        "challenge_id": explicit_id,
                        "challenge_name": str(item.get("name") or ""),
                        "already_solved": bool(item.get("solved")),
                        "status": str(item.get("status") or ""),
                        "confidence": 1.0,
                    }

        title = str(page_features.get("title") or "").strip().lower()
        url_text = str(page_features.get("url") or target or "").strip().lower()
        content = str(page_features.get("content") or "").strip().lower()
        hints = " ".join(part for part in [title, url_text, content[:400]] if part)

        best_match = None
        best_score = 0.0
        for item in challenge_briefs:
            name = str(item.get("name") or "").strip().lower()
            if not name:
                continue
            score = 0.0
            if title and name == title:
                score = 1.0
            elif title and (name in title or title in name):
                score = 0.9
            elif name and name in hints:
                score = 0.8
            else:
                name_tokens = {token for token in re.split(r"[^a-z0-9]+", name) if token}
                hint_tokens = {token for token in re.split(r"[^a-z0-9]+", hints) if token}
                if name_tokens and hint_tokens:
                    overlap = len(name_tokens & hint_tokens)
                    union = len(name_tokens | hint_tokens) or 1
                    score = overlap / union
            if score > best_score:
                best_score = score
                best_match = item

        if best_match is None or best_score < 0.45:
            return {
                "matched": False,
                "match_reason": "no_confident_match",
                "challenge_id": explicit_id,
                "challenge_name": "",
                "already_solved": False,
                "status": "",
                "confidence": best_score,
            }

        return {
            "matched": True,
            "match_reason": "name_similarity",
            "challenge_id": str(best_match.get("id") or explicit_id or ""),
            "challenge_name": str(best_match.get("name") or ""),
            "already_solved": bool(best_match.get("solved")),
            "status": str(best_match.get("status") or ""),
            "confidence": round(best_score, 3),
        }

    def _build_already_solved_reason(self) -> str:
        if self.state is None:
            return "platform challenge already solved"
        next_id = ""
        next_name = ""
        for item in reversed(self.state.meta_reasonings):
            if not isinstance(item, dict):
                continue
            if item.get("type") != "platform_task_queue_snapshot":
                continue
            next_id = str(item.get("next_challenge_id") or "").strip()
            next_name = str(item.get("next_challenge_name") or "").strip()
            break
        if next_id or next_name:
            return (
                "platform challenge already solved"
                f" | next={next_id} {next_name}".strip()
            )
        return "platform challenge already solved"
