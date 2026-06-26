"""Task-notes loading & matching (debt ledger 第五波·刀11).

Extracted from web_server.py. This themed cluster locates a task's persisted
notes files (project loot + per-target workspace loot), loads them, and selects
the entries that belong to a given task (by run id / task id / target). Members
call only each other plus the shared leaves in web_leaf_utils
(``_workspace_name_for_target`` / ``_load_json_file``, downstreamed in 刀10), so
they carry no upward dependency on web_server — the cluster is down-closed and
out of every test patch face. web_server re-imports the set so the sole
stay-behind caller ``_task_detail_payload`` resolves ``web_server._load_task_notes``
unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .web_leaf_utils import _load_json_file, _workspace_name_for_target


def _candidate_notes_files(project_root: Path, task: dict[str, Any]) -> list[Path]:
    target = str(task.get("target") or "")
    workspace_name = _workspace_name_for_target(target)
    candidates = [
        project_root / "loot" / "notes.json",
    ]
    if workspace_name:
        candidates.append(project_root / "workspaces" / workspace_name / "loot" / "notes.json")
    seen: set[Path] = set()
    result: list[Path] = []
    for path in candidates:
        if path.exists() and path not in seen:
            result.append(path)
            seen.add(path)
    return result


def _note_matches_task(key: str, note: dict[str, Any], task: dict[str, Any]) -> bool:
    target = str(task.get("target") or "").lower()
    run_id = str(task.get("currentRunId") or "")
    task_id = str(task.get("id") or "")
    haystacks = [key.lower(), str(note.get("content") or "").lower()]
    meta = note.get("metadata") if isinstance(note.get("metadata"), dict) else {}
    for value in meta.values():
        if isinstance(value, (str, int, float)):
            haystacks.append(str(value).lower())
    if run_id and any(run_id.lower() in text for text in haystacks):
        return True
    if task_id and any(task_id.lower() in text for text in haystacks):
        return True
    if target and any(target in text for text in haystacks):
        return True
    return False


def _load_task_notes(project_root: Path, task: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    sources: list[str] = []
    for path in _candidate_notes_files(project_root, task):
        raw = _load_json_file(path)
        if not isinstance(raw, dict):
            continue
        relative_source = str(path.relative_to(project_root))
        sources.append(relative_source)
        for idx, (key, note) in enumerate(raw.items(), start=1):
            if not isinstance(note, dict):
                continue
            meta = note.get("metadata") if isinstance(note.get("metadata"), dict) else {}
            entry = {
                "id": f"{path.stem}:{idx}",
                "key": key,
                "value": str(note.get("content") or ""),
                "category": note.get("category") or "info",
                "confidence": note.get("confidence") or "medium",
                "status": note.get("status") or "confirmed",
                "metadata": meta,
                "source": relative_source,
            }
            if _note_matches_task(key, note, task):
                items.append(entry)
    return items[:12], sources
