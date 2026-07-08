"""Shared pure helpers for the ``task_dag_*`` provenance/redaction module family.

De-dup track: these eight helpers were copy-pasted byte-identically across the
``task_dag_*`` sibling modules (``_redact_text`` alone had 13 identical copies).
Each is a single-variant, self-contained pure function (no cross-helper calls, no
module state) depending only on ``re`` / ``typing.Any``, so consolidating them here
is behavior-preserving — every caller keeps the same underscore-prefixed name via
``from .task_dag_shared import ...``.

Deliberately NOT consolidated (left in place): helpers that have drifted into
multiple variants across the family — ``_safe_metadata`` (8 variants),
``_safe_refs`` / ``_looks_like_raw_body`` / ``_contains_proof_like_value`` /
``_safe_mapping`` / ``_preview`` / ``_coerce_sequence`` — merging those would pick
one variant and change behavior in the others (a real risk for the redaction /
proof-authority helpers), so they stay module-local pending a per-variant review.
"""

from __future__ import annotations

import re
from typing import Any


def _redact_text(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(r"(?im)^\s*set-cookie\s*:.*$", "<redacted>", text)
    text = re.sub(r"(?im)^\s*cookie\s*:.*$", "<redacted>", text)
    text = re.sub(r"(?im)^\s*authorization\s*:.*$", "<redacted>", text)
    text = re.sub(
        r"(?i)\bauthorization\s*:\s*bearer\s+[^\s,;&]+",
        "authorization=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\bauthorization\s*=\s*bearer\s+[^\s,;&]+",
        "authorization=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b(token|api[_-]?key|password|secret|session|sessionid|cookie|authorization)\b\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^\s,;&]+)",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)([\"'])(token|api[_-]?key|password|secret|session|sessionid|cookie|authorization)[\"']\s*:\s*([\"'])(.*?)\3",
        r'\1\2\1: \3<redacted>\3',
        text,
    )
    return text


def _is_sensitive_key(value: Any) -> bool:
    return bool(
        re.search(
            r"(?i)(token|api[_-]?key|password|secret|session|sessionid|cookie|authorization)",
            str(value or ""),
        )
    )


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "").strip()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _clamp_float(value: Any, *, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = minimum
    return max(minimum, min(maximum, result))


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        return dict(result or {}) if isinstance(result, dict) else {}
    return {}


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for item in values:
        if item and item not in result:
            result.append(item)
    return result


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        return []
    return [str(item).strip() for item in items if str(item or "").strip()]


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
