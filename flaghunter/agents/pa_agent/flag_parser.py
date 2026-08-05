"""Flag extraction / rejection / candidate-storage mixin extracted from ctf_dispatcher.py.

P5 / Workstream A: the flag text-parsing cluster (7 contiguous methods,
_extract_flag .. _store_flag_candidate) is physically moved out of
CTFTaskDispatcher into a behaviour-preserving mixin. Method bodies are identical;
self.* (state, _store_note) resolves at runtime against the dispatcher that mixes
this in, so call sites are unchanged. Pure code relocation, near-zero risk.
"""

from __future__ import annotations

import base64
import re
from urllib.parse import urlparse

from ...tools.notes import get_all_notes_sync
from .dispatcher_helpers import _FLAG_RE, _STRICT_FLAG_RE

# Flags that only arrive inside a ``data:<mime>;base64,<payload>`` URI (e.g. a
# ``file://`` SSRF read rendered back into an ``<iframe>`` as
# ``data:text/html;base64,...``) never match the raw-body scan. Decode any such
# embedded payloads and re-scan them so the flag lands regardless of transport.
_DATA_URI_BASE64_RE = re.compile(
    r"data:[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+;base64,([A-Za-z0-9+/=\r\n]+)",
    re.IGNORECASE,
)


class FlagParserMixin:
    """Flag text extraction, rejection checks and candidate storage."""

    def _extract_flag(self, text: str) -> str | None:
        blob = str(text or "")
        if flag := self._scan_flag_in_blob(blob):
            return flag
        for decoded in self._decode_embedded_base64_blobs(blob):
            if flag := self._scan_flag_in_blob(decoded):
                return flag
        return None

    def _scan_flag_in_blob(self, blob: str) -> str | None:
        for match in _STRICT_FLAG_RE.finditer(blob):
            candidate = match.group(1)
            if self._looks_like_css_false_flag(candidate, blob):
                continue
            return candidate
        for match in _FLAG_RE.finditer(blob):
            candidate = match.group(1)
            if self._looks_like_css_false_flag(candidate, blob):
                continue
            return candidate
        return None

    def _decode_embedded_base64_blobs(self, text: str) -> list[str]:
        blob = str(text or "")
        decoded_blobs: list[str] = []
        for match in _DATA_URI_BASE64_RE.finditer(blob):
            encoded = re.sub(r"\s+", "", match.group(1))
            if len(encoded) < 8:
                continue
            try:
                raw = base64.b64decode(encoded, validate=False)
            except Exception:
                continue
            decoded_blobs.append(raw.decode("utf-8", errors="ignore"))
        return decoded_blobs

    def _extract_php_var_dump_strings(self, text: str) -> list[str]:
        blob = str(text or "")
        values = re.findall(r'string\(\d+\)\s+"([^"]*)"', blob, flags=re.IGNORECASE)
        return [value for value in values if str(value).strip()]

    def _extract_runtime_flag(self, text: str) -> str | None:
        flag = self._extract_flag(text)
        if not flag or self._is_rejected_flag(flag):
            return None
        return flag

    def _is_rejected_flag(self, flag: str) -> bool:
        if self.state is None:
            return False
        return self.state.is_rejected_flag(flag)

    def _looks_like_css_false_flag(self, candidate: str, text: str) -> bool:
        normalized = str(candidate or "").strip()
        blob = str(text or "")
        lowered = normalized.lower()
        prefix = lowered.split("{", 1)[0]
        body = lowered.split("{", 1)[1].rsplit("}", 1)[0] if "{" in lowered and "}" in lowered else ""
        common_css_selectors = {
            "*",
            "summary",
            "template",
            "body",
            "html",
            "div",
            "span",
            "img",
            "svg",
            "form",
            "input",
            "button",
            "table",
            "thead",
            "tbody",
            "tr",
            "td",
            "th",
            "label",
            "nav",
            "section",
            "article",
            "header",
            "footer",
            "video",
            "audio",
            "canvas",
            "main",
            "aside",
            "figure",
            "figcaption",
            "details",
            "dialog",
            "menu",
            "before",
            "after",
            ":before",
            ":after",
            "::before",
            "::after",
        }
        if prefix not in common_css_selectors:
            return False
        if ":" not in body:
            return False
        css_markers = (
            "display:",
            "margin",
            "padding",
            "font-",
            "border",
            "color:",
            "background",
            "width:",
            "height:",
            "box-sizing",
            "content:",
            "position:",
            "line-height",
        )
        if not any(marker in body for marker in css_markers):
            return False
        if prefix in {"before", "after", ":before", ":after", "::before", "::after", "*"}:
            return True
        return any(
            marker in blob.lower()
            for marker in (
                "{display:",
                "display:block",
                "bootstrap",
                ".container",
                "stylesheet",
                "<style",
                "milligram",
            )
        )

    def _load_rejected_flags(self) -> None:
        if self.state is None:
            return
        notes = get_all_notes_sync()
        for key, data in notes.items():
            if not str(key).startswith("ctf_wrong_flag"):
                continue
            if isinstance(data, dict):
                content = str(data.get("content") or "")
            else:
                content = str(data or "")
            if flag := self._extract_flag(content):
                self.state.add_flag(
                    flag,
                    level="rejected",
                    evidence_source="user-feedback",
                    rationale="loaded from persisted wrong-flag notes",
                    confidence=1.0,
                )

    async def _store_flag_candidate(self, flag: str, target: str, *, reason: str) -> None:
        await self._store_note(
            key="ctf_flag_candidate",
            value=f"candidate={flag}; reason={reason}",
            category="artifact",
            target=urlparse(target).netloc or target,
        )
        if self.state is not None:
            self.state.add_flag(
                flag,
                level="candidate",
                evidence_source="source-leak",
                rationale=reason,
                confidence=0.4,
                requires_followup=True,
                metadata={"target": target},
            )

