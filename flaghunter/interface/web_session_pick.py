"""Session-snapshot discovery, scoring & selection (debt ledger 第五波·刀15).

Extracted from web_server.py. This themed cluster enumerates a task's session
snapshot files (project loot + per-target workspace loot), scores each by
target / time / session-id proximity, and picks the best match with a confidence
label. Members call only each other plus the shared leaves
``_workspace_name_for_target`` / ``_load_json_file`` / ``_parse_iso`` in
web_leaf_utils, so the cluster is down-closed with zero upward dependency on
web_server. web_server re-imports the set so stay-behind callers
(``_build_trace_payload`` / ``_task_detail_payload``, and ``_iter_session_paths``'s
use in the knowledge-usage cluster) resolve unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .web_leaf_utils import _load_json_file, _parse_iso, _workspace_name_for_target


def _iter_session_paths(project_root: Path, task: dict[str, Any]) -> list[Path]:
    target = str(task.get("target") or "")
    workspace_name = _workspace_name_for_target(target)
    paths = [project_root / "loot" / "sessions"]
    if workspace_name:
        paths.append(project_root / "workspaces" / workspace_name / "loot" / "sessions")
    results: list[Path] = []
    seen: set[Path] = set()
    for base in paths:
        if not base.exists():
            continue
        for path in sorted(base.glob("*.json")):
            if path.name == "index.json":
                continue
            resolved = path.resolve()
            if resolved not in seen:
                results.append(path)
                seen.add(resolved)
    return results


def _score_session_snapshot(snapshot: dict[str, Any], task: dict[str, Any], path: Path) -> float:
    score = 0.0
    task_started = _parse_iso(task.get("startedAt") or task.get("createdAt"))
    snapshot_updated = _parse_iso(snapshot.get("updated_at"))
    if task_started and snapshot_updated:
        score += abs((snapshot_updated - task_started).total_seconds())
    else:
        score += 86_400.0
    target = str(task.get("target") or "").lower()
    snap_target = str(snapshot.get("target") or "").lower()
    if target and snap_target:
        score += 0 if target == snap_target else 10_000.0
    elif target or snap_target:
        score += 20_000.0
    if snapshot.get("session_id") == task.get("sessionId"):
        score -= 50_000.0
    if path.stem == task.get("sessionId"):
        score -= 50_000.0
    message_count = len(snapshot.get("conversation") or [])
    score -= min(message_count, 50) * 10.0
    return score


def _session_confidence_for_score(score: float) -> str:
    if score <= 600:
        return "medium"
    if score <= 3_600:
        return "low"
    return "very_low"


def _pick_session_snapshot(project_root: Path, task: dict[str, Any]) -> tuple[dict[str, Any] | None, Path | None, dict[str, Any]]:
    explicit_id = str(task.get("sessionId") or "")
    meta = {
        "matchedBy": "none",
        "confidence": "none",
        "expectedSessionId": explicit_id or None,
        "blockedReason": None,
        "candidateScore": None,
    }
    if explicit_id:
        for base in [project_root / "loot" / "sessions", project_root / "workspaces" / _workspace_name_for_target(task.get("target")) / "loot" / "sessions"]:
            candidate = base / f"{explicit_id}.json"
            if candidate.exists():
                data = _load_json_file(candidate)
                if isinstance(data, dict):
                    meta["matchedBy"] = "explicit_session_id"
                    meta["confidence"] = "high"
                    return data, candidate, meta
        meta["blockedReason"] = "expected_session_missing"
    best: tuple[float, dict[str, Any], Path] | None = None
    for path in _iter_session_paths(project_root, task):
        data = _load_json_file(path)
        if not isinstance(data, dict):
            continue
        score = _score_session_snapshot(data, task, path)
        if best is None or score < best[0]:
            best = (score, data, path)
    if best is None:
        return None, None, meta
    meta["matchedBy"] = "heuristic_target_time"
    meta["candidateScore"] = round(best[0], 3)
    meta["confidence"] = _session_confidence_for_score(best[0])
    return best[1], best[2], meta
