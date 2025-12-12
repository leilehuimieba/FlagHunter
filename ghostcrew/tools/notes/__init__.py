"""Notes tool for GhostCrew - persistent key findings storage."""

import asyncio
import json
from pathlib import Path
from typing import Dict

from ..registry import ToolSchema, register_tool

# Notes storage - kept at loot root for easy access
_notes: Dict[str, str] = {}
_notes_file: Path = Path("loot/notes.json")
# Lock for safe concurrent access from multiple agents (asyncio since agents are async tasks)
_notes_lock = asyncio.Lock()


def _load_notes_unlocked() -> None:
    """Load notes from file (caller must hold lock)."""
    global _notes
    if _notes_file.exists():
        try:
            _notes = json.loads(_notes_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            _notes = {}


def _save_notes_unlocked() -> None:
    """Save notes to file (caller must hold lock)."""
    _notes_file.parent.mkdir(parents=True, exist_ok=True)
    _notes_file.write_text(json.dumps(_notes, indent=2), encoding="utf-8")


async def get_all_notes() -> Dict[str, str]:
    """Get all notes (for TUI /notes command)."""
    async with _notes_lock:
        if not _notes:
            _load_notes_unlocked()
        return _notes.copy()


def get_all_notes_sync() -> Dict[str, str]:
    """Get all notes synchronously (read-only, best effort for prompts)."""
    # If notes are empty, try to load from disk (safe read)
    if not _notes and _notes_file.exists():
        try:
            return json.loads(_notes_file.read_text(encoding="utf-8"))
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
        },
        required=["action"],
    ),
    category="utility",
)
async def notes(arguments: dict, runtime) -> str:
    """
    Manage persistent notes.

    Args:
        arguments: Dictionary with action, key, value
        runtime: The runtime environment (unused)

    Returns:
        Result message
    """
    action = arguments["action"]
    key = arguments.get("key", "").strip()
    value = arguments.get("value", "")

    async with _notes_lock:
        if action == "create":
            if not key:
                return "Error: key is required for create"
            if not value:
                return "Error: value is required for create"
            if key in _notes:
                return f"Error: note '{key}' already exists. Use 'update' to modify."

            _notes[key] = value
            _save_notes_unlocked()
            return f"Created note '{key}'"

        elif action == "read":
            if not key:
                return "Error: key is required for read"
            if key not in _notes:
                return f"Note '{key}' not found"

            return f"[{key}] {_notes[key]}"

        elif action == "update":
            if not key:
                return "Error: key is required for update"
            if not value:
                return "Error: value is required for update"

            existed = key in _notes
            _notes[key] = value
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
            for k, v in _notes.items():
                # Truncate long values for display
                display_val = v if len(v) <= 60 else v[:57] + "..."
                lines.append(f"  [{k}] {display_val}")

            return "\n".join(lines)

        else:
            return f"Unknown action: {action}"
