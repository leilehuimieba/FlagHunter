"""Persist high-value session notes into markdown knowledge artifacts."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any


async def write_session_to_knowledge(target: str, notes: dict) -> Path | None:
    """Serialize high-value session notes into a markdown knowledge file."""
    worthy: dict[str, dict[str, Any]] = {}
    for key, value in (notes or {}).items():
        if not isinstance(value, dict):
            continue
        if value.get("category") not in ("finding", "vulnerability", "credential"):
            continue
        if value.get("confidence") not in ("high", "medium"):
            continue
        worthy[key] = value

    if not worthy:
        return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_safe = re.sub(r"[^\w.-]", "_", target or "unknown")
    out_path = Path("flaghunter/knowledge/sessions") / f"{ts}_{target_safe}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [f"# Session: {target or 'unknown'} @ {ts}\n"]
    for key, data in worthy.items():
        cat = data.get("category", "")
        content = data.get("content", "")
        lines.append(f"## {key} ({cat})")
        lines.append(str(content))
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
