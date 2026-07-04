"""Pure sanitization helpers for challenge read models."""

from __future__ import annotations

import re
from typing import Any


SENSITIVE_KEY_PATTERN = (
    r"(?i)(token|api[_-]?key|password|secret|session|cookie|authorization)"
)
RAW_TEXT_KEYS = {
    "stdout",
    "stderr",
    "body",
    "http_body",
    "raw_body",
    "raw_output",
    "prompt",
    "completion",
    "tool_result",
    "tool_results",
    "request",
    "response",
    "full_command",
    "raw_args",
    "command_line",
    "terminal_output",
}


def redact_sensitive_text(value: Any, *, marker: str = "<redacted>") -> str:
    text = str(value or "")
    if not text:
        return ""
    redaction = str(marker or "<redacted>")
    text = re.sub(r"(?im)^\s*set-cookie\s*:.*$", "<redacted>", text)
    text = re.sub(r"(?im)^\s*cookie\s*:.*$", "<redacted>", text)
    text = re.sub(r"(?im)^\s*authorization\s*:.*$", "<redacted>", text)
    text = re.sub(
        r"(?i)\bauthorization\s*:\s*bearer\s+[^\s,;&]+",
        f"authorization={redaction}",
        text,
    )
    text = re.sub(
        r"(?i)\bauthorization\s*=\s*bearer\s+[^\s,;&]+",
        f"authorization={redaction}",
        text,
    )
    text = re.sub(
        r"(?i)\b(token|api[_-]?key|password|secret|session|cookie|authorization)\b\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^\s,;&]+)",
        rf"\1={redaction}",
        text,
    )
    text = re.sub(
        r"(?i)([\"'])(token|api[_-]?key|password|secret|session|cookie|authorization)[\"']\s*:\s*([\"'])(.*?)\3",
        rf"\1\2\1: \3{redaction}\3",
        text,
    )
    return text


def is_sensitive_key(value: Any) -> bool:
    return bool(re.search(SENSITIVE_KEY_PATTERN, str(value or "")))


def looks_like_raw_body(value: Any) -> bool:
    text = str(value or "")
    if not text:
        return False
    stripped = text.strip()
    if len(stripped) > 240 and stripped[:1] in {"{", "["}:
        return True
    return any(
        re.search(pattern, text)
        for pattern in (
            r"(?im)^\s*HTTP/\d(?:\.\d)?\s+\d{3}\b",
            r"(?is)<!doctype\s+html|<html[\s>]",
            r"(?im)^\s*PING\s+",
            r"(?im)^\s*\d+\s+bytes\s+from\s+",
            r"(?im)^\s*uid=\d+\(",
            r"(?im)^\s*gid=\d+\(",
        )
    )


def preview_text(value: Any, *, max_chars: int = 160) -> str:
    limit = max(0, int(max_chars))
    text = redact_sensitive_text(value)
    if looks_like_raw_body(text):
        return "<redacted raw body>"[:limit]
    return text[:limit]


def sanitize_metadata(
    metadata: dict[str, Any] | None,
    *,
    max_chars: int = 160,
    max_items: int = 20,
) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for raw_key, raw_value in dict(metadata or {}).items():
        key = preview_text(raw_key, max_chars=80)
        if not key:
            continue
        if str(raw_key or "") in RAW_TEXT_KEYS:
            safe[key] = "<redacted raw body>"
            continue
        if is_sensitive_key(key):
            safe[key] = "<redacted>"
            continue
        safe[key] = sanitize_json_value(
            raw_value,
            max_chars=max_chars,
            max_items=max_items,
        )
    return safe


def sanitize_json_value(
    value: Any,
    *,
    max_chars: int = 160,
    max_items: int = 20,
) -> dict[str, Any] | list[Any] | str | int | float | bool | None:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        return sanitize_metadata(value, max_chars=max_chars, max_items=max_items)
    if isinstance(value, (list, tuple)):
        return [
            sanitize_json_value(item, max_chars=max_chars, max_items=max_items)
            for item in list(value)[: max(0, int(max_items))]
        ]
    return preview_text(value, max_chars=max_chars)
