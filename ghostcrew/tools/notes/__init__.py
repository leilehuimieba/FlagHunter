"""Notes tool for GhostCrew - persistent key findings storage."""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict

from ..registry import ToolSchema, register_tool

# Notes storage - kept at loot root for easy access
_notes: Dict[str, Dict[str, Any]] = {}
_notes_file: Path = Path("loot/notes.json")
# Lock for safe concurrent access from multiple agents (asyncio since agents are async tasks)
_notes_lock = asyncio.Lock()


def _load_notes_unlocked() -> None:
    """Load notes from file (caller must hold lock)."""
    global _notes
    if _notes_file.exists():
        try:
            loaded = json.loads(_notes_file.read_text(encoding="utf-8"))
            # Migration: Convert legacy string values to dicts
            _notes = {}
            for k, v in loaded.items():
                if isinstance(v, str):
                    _notes[k] = {"content": v, "category": "info", "confidence": "medium"}
                else:
                    _notes[k] = v
        except (json.JSONDecodeError, IOError):
            _notes = {}


def _save_notes_unlocked() -> None:
    """Save notes to file (caller must hold lock)."""
    _notes_file.parent.mkdir(parents=True, exist_ok=True)
    _notes_file.write_text(json.dumps(_notes, indent=2), encoding="utf-8")


async def get_all_notes() -> Dict[str, Dict[str, Any]]:
    """Get all notes (for TUI /notes command)."""
    async with _notes_lock:
        if not _notes:
            _load_notes_unlocked()
        return _notes.copy()


def get_all_notes_sync() -> Dict[str, Dict[str, Any]]:
    """Get all notes synchronously (read-only, best effort for prompts)."""
    # If notes are empty, try to load from disk (safe read)
    if not _notes and _notes_file.exists():
        try:
            loaded = json.loads(_notes_file.read_text(encoding="utf-8"))
            # Migration for sync read
            result = {}
            for k, v in loaded.items():
                if isinstance(v, str):
                    result[k] = {"content": v, "category": "info", "confidence": "medium"}
                else:
                    result[k] = v
            return result
        except (json.JSONDecodeError, IOError):
            pass
    return _notes.copy()


def set_notes_file(path: Path) -> None:
    """Set custom notes file path."""
    global _notes_file
    _notes_file = path
    # Can't use async here, so load without lock (called at init time)
    _load_notes_unlocked()


# Load notes on module import (init time, no contention yet)
_load_notes_unlocked()


@register_tool(
    name="notes",
    description="Manage persistent notes for key findings. Actions: create, read, update, delete, list.",
    schema=ToolSchema(
        properties={
            "action": {
                "type": "string",
                "enum": ["create", "read", "update", "delete", "list"],
                "description": "The action to perform",
            },
            "key": {
                "type": "string",
                "description": "Note identifier (e.g., 'creds_ssh', 'open_ports', 'vuln_sqli')",
            },
            "value": {
                "type": "string",
                "description": "Note content (for create/update)",
            },
            "category": {
                "type": "string",
                "enum": ["finding", "credential", "task", "info", "vulnerability", "artifact"],
                "description": "Category for organization (default: info)",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Confidence level (default: medium)",
            },
        },
        required=["action"],
    ),
    category="utility",
)
async def notes(arguments: dict, runtime) -> str:
    """
    Manage persistent notes.

    Args:
        arguments: Dictionary with action, key, value, category, confidence
        runtime: The runtime environment (unused)

    Returns:
        Result message
    """
    action = arguments["action"]
    key = arguments.get("key", "").strip()
    value = arguments.get("value", "")
    
    # Soft validation for category
    category = arguments.get("category", "info")
    valid_categories = ["finding", "credential", "task", "info", "vulnerability", "artifact"]
    if category not in valid_categories:
        category = "info"
        
    confidence = arguments.get("confidence", "medium")

    async with _notes_lock:
        if action == "create":
            if not key:
                return "Error: key is required for create"
            if not value:
                return "Error: value is required for create"
            if key in _notes:
                return f"Error: note '{key}' already exists. Use 'update' to modify."

            _notes[key] = {
                "content": value,
                "category": category,
                "confidence": confidence
            }
            _save_notes_unlocked()
            return f"Created note '{key}' ({category})"

        elif action == "read":
            if not key:
                return "Error: key is required for read"
            if key not in _notes:
                return f"Note '{key}' not found"

            note = _notes[key]
            return f"[{key}] ({note['category']}, {note['confidence']}) {note['content']}"

        elif action == "update":
            if not key:
                return "Error: key is required for update"
            if not value:
                return "Error: value is required for update"

            existed = key in _notes
            # Preserve existing metadata if not provided? No, overwrite is cleaner for now, 
            # but maybe we should default to existing if not provided.
            # For now, let's just overwrite with defaults if missing, or use provided.
            # Actually, if updating, we might want to keep category if not specified.
            # But arguments.get("category", "info") defaults to info.
            # Let's stick to simple overwrite for now to match previous behavior.
            
            _notes[key] = {
                "content": value,
                "category": category,
                "confidence": confidence
            }
            _save_notes_unlocked()
            return f"{'Updated' if existed else 'Created'} note '{key}'"

        elif action == "delete":
            if not key:
                return "Error: key is required for delete"
            if key not in _notes:
                return f"Note '{key}' not found"

            del _notes[key]
            _save_notes_unlocked()
            return f"Deleted note '{key}'"

        elif action == "list":
            if not _notes:
                return "No notes saved"

            lines = [f"Notes ({len(_notes)} entries):"]
            
            # Group by category for display
            by_category = {}
            for k, v in _notes.items():
                cat = v["category"]
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append((k, v))
            
            for cat in sorted(by_category.keys()):
                lines.append(f"\n## {cat.title()}")
                for k, v in by_category[cat]:
                    content = v["content"]
                    display_val = content if len(content) <= 60 else content[:57] + "..."
                    conf = v.get("confidence", "medium")
                    lines.append(f"  [{k}] ({conf}) {display_val}")

            return "\n".join(lines)

        else:
            return f"Unknown action: {action}"
