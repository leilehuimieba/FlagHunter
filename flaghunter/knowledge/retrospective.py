"""Retrospective entry helpers for CTF improvement loops."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..workspaces.utils import resolve_knowledge_paths

# Module-level path; tests patch this directly.
RETRO_PATH: Path = Path("knowledge") / "retrospective.json"


def _init_retro_path() -> None:
    """Initialize RETRO_PATH from workspace knowledge base at import time."""
    global RETRO_PATH
    try:
        base = Path(resolve_knowledge_paths().get("base", Path("knowledge")))
        RETRO_PATH = base / "retrospective.json"
    except Exception:
        pass


_init_retro_path()


def _get_retro_path() -> Path:
    """Resolve retrospective JSON path, respecting test patches."""
    return RETRO_PATH


def get_retro_export_dir() -> Path:
    base = Path(resolve_knowledge_paths().get("base", Path("knowledge")))
    return base / "retrospective_export"


def get_retro_root_markdown_path() -> Path:
    base = Path(resolve_knowledge_paths().get("base", Path("knowledge")))
    return base / "retrospective_notes.md"


def get_retro_markdown_path() -> Path:
    return get_retro_export_dir() / "retrospective_notes.md"


def load_retrospective() -> list[dict]:
    path = _get_retro_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_retrospective(entries: list[dict]) -> None:
    path = _get_retro_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_unresolved_entries() -> list[dict]:
    return [e for e in load_retrospective() if not e.get("resolved")]


def _export_to_markdown() -> None:
    unresolved = get_unresolved_entries()
    export_dir = get_retro_export_dir()
    root_md_path = get_retro_root_markdown_path()
    md_path = get_retro_markdown_path()
    root_md_path.parent.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# CTF Retrospective Notes",
        "",
        f"Unresolved items: {len(unresolved)}",
        "",
    ]

    for entry in unresolved:
        lines.append(f"## #{entry.get('id')} [{entry.get('category', 'other')}]")
        lines.append(f"- Timestamp: {entry.get('timestamp', '')}")
        lines.append(f"- Description: {entry.get('description', '')}")
        suggestion = str(entry.get("suggestion", "") or "").strip()
        if suggestion:
            lines.append(f"- Suggestion: {suggestion}")

        context = entry.get("context", {})
        if isinstance(context, dict) and context:
            lines.append("- Context:")
            for key, value in context.items():
                lines.append(f"  - {key}: {value}")
        lines.append("")

    content = "\n".join(lines).rstrip() + "\n"
    root_md_path.write_text(content, encoding="utf-8")
    md_path.write_text(content, encoding="utf-8")


def add_retrospective_entry(
    category: str,
    description: str,
    context: dict,
    suggestion: str = "",
) -> None:
    """追加一条复盘条目。"""
    entries = load_retrospective()
    entries.append(
        {
            "id": len(entries) + 1,
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "description": description,
            "context": context,
            "suggestion": suggestion,
            "resolved": False,
        }
    )
    save_retrospective(entries)
    try:
        _export_to_markdown()
    except Exception:
        pass


def mark_resolved(entry_id: int) -> None:
    entries = load_retrospective()
    for entry in entries:
        if entry.get("id") == entry_id:
            entry["resolved"] = True
    save_retrospective(entries)
    try:
        _export_to_markdown()
    except Exception:
        pass


def _safe_list(value):
    """Safely convert a field to a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _extract_flag_values(flag_records):
    """Extract string values from FlagRecord-like objects."""
    values = []
    for rec in flag_records or []:
        if hasattr(rec, "value"):
            values.append(str(rec.value))
        elif isinstance(rec, dict):
            values.append(str(rec.get("value", rec)))
        else:
            values.append(str(rec))
    return values


def _extract_hypothesis_kinds(hypotheses, status_filter):
    """Extract unique hypothesis kinds matching a status filter."""
    kinds = set()
    for h in hypotheses or []:
        h_status = h.status if hasattr(h, "status") else h.get("status", "")
        h_kind = h.kind if hasattr(h, "kind") else h.get("kind", "")
        if h_status in status_filter and h_kind:
            kinds.add(h_kind)
    return sorted(kinds)


def export_ctf_session_retrospective(state, result) -> None:
    """Export a complete CTF session as a retrospective entry.

    This should be called at the end of a CTF solve attempt (success or failure)
    to persist the session's key learnings for future RAG retrieval.
    """
    try:
        entries = load_retrospective()
        entry_id = len(entries) + 1

        # Build structured session record
        session_entry = {
            "id": entry_id,
            "timestamp": datetime.now().isoformat(),
            "category": "ctf_session",
            "target": getattr(state, "target", "") or "",
            "goal": getattr(state, "goal", "") or "",
            "detected_type": getattr(state, "detected_type", None),
            "success": getattr(result, "success", False),
            "flag": getattr(result, "flag", None),
            "chains_executed": list(getattr(result, "chain_used", []) or []),
            "missing_tools": list(getattr(result, "missing_tools", []) or []),
            "stop_reason": getattr(state, "stop_reason", "") or "",
            "no_progress_count": getattr(state, "no_progress_count", 0),
            "hypothesis_count": len(getattr(state, "hypotheses", []) or []),
            "experiment_count": len(getattr(state, "experiments", []) or []),
            "observation_count": len(getattr(state, "observations", []) or []),
            "candidate_flags": _extract_flag_values(getattr(state, "candidate_flags", [])),
            "runtime_flags": _extract_flag_values(getattr(state, "runtime_flags", [])),
            "verified_flags": _extract_flag_values(getattr(state, "verified_flags", [])),
            "rejected_flags": _extract_flag_values(getattr(state, "rejected_flags", [])),
            "winning_hypothesis_kinds": _extract_hypothesis_kinds(
                getattr(state, "hypotheses", []), {"supported", "confirmed"}
            ),
            "failed_hypothesis_kinds": _extract_hypothesis_kinds(
                getattr(state, "hypotheses", []), {"exhausted", "rejected", "aborted"}
            ),
            "retrospectives_summary": [
                str(r)[:500] for r in (getattr(state, "retrospectives", []) or [])[:5]
            ],
            "resolved": False,
        }

        # Also create a human-readable description for markdown export
        status_emoji = "✅" if session_entry["success"] else "❌"
        description = (
            f"{status_emoji} CTF session on {session_entry['target']} "
            f"(type={session_entry['detected_type']}, chains={session_entry['chains_executed']})"
        )
        suggestion = ""
        if session_entry["success"]:
            suggestion = (
                f"Winning chain: {session_entry['chains_executed'][-1] if session_entry['chains_executed'] else 'unknown'}. "
                f"Re-use for similar fingerprints."
            )
        else:
            suggestion = (
                f"Failed hypotheses: {session_entry['failed_hypothesis_kinds']}. "
                f"Missing tools: {session_entry['missing_tools']}. "
                f"Consider improving these capabilities."
            )

        entries.append({
            "id": entry_id,
            "timestamp": session_entry["timestamp"],
            "category": "ctf_session",
            "description": description,
            "context": session_entry,
            "suggestion": suggestion,
            "resolved": False,
        })
        save_retrospective(entries)
        _export_to_markdown()
    except Exception:
        # Best-effort: retrospective must never break the solve flow
        pass
