"""Run-metrics file discovery & best-match selection (debt ledger 第五波·刀14).

Extracted from web_server.py. This themed cluster locates a task's run-metrics
JSON files (under loot/metrics) and picks the best match for a task by run id /
task id / target plus a start-time / tool-count / duration proximity score.
Members call only each other plus the shared leaves ``_parse_iso`` /
``_duration_ms_for_task`` in web_leaf_utils, so the cluster is down-closed with
zero upward dependency on web_server. It is the base of the knowledge-usage
cluster (簇9, via _task_session_lookup), so it is extracted ahead of it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .web_leaf_utils import _duration_ms_for_task, _parse_iso


def _iter_metric_files(project_root: Path) -> list[Path]:
    metrics_dir = project_root / "loot" / "metrics"
    if not metrics_dir.exists():
        return []
    return sorted(metrics_dir.glob("metrics_*.json"))


def _load_metrics_data(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _pick_metrics_for_task(project_root: Path, task: dict[str, Any]) -> dict[str, Any] | None:
    started = _parse_iso(task.get("startedAt")) or _parse_iso(task.get("createdAt"))
    files = _iter_metric_files(project_root)
    if not files:
        return None

    candidates: list[tuple[int, float, Path, dict[str, Any]]] = []
    expected_tool_calls = int(task.get("toolCalls") or 0)
    expected_duration = _duration_ms_for_task(task)
    expected_run_id = str(task.get("currentRunId") or "")
    expected_task_id = str(task.get("id") or "")
    expected_target = str(task.get("target") or "")

    for path in files:
        data = _load_metrics_data(path)
        if not data:
            continue

        match_rank = 3
        metric_run_id = str(data.get("run_id") or "")
        metric_task_id = str(data.get("task_id") or "")
        metric_target = str(data.get("target") or "")
        if expected_run_id and metric_run_id == expected_run_id:
            match_rank = 0
        elif expected_task_id and metric_task_id == expected_task_id:
            match_rank = 1
        elif expected_target and metric_target and metric_target == expected_target:
            match_rank = 2

        score = 0.0
        metric_started = _parse_iso(data.get("started_at"))
        if started and metric_started:
            score += abs((metric_started - started).total_seconds())
        elif started or metric_started:
            score += 86_400.0

        metric_tools = int(data.get("total_tool_calls") or 0)
        score += abs(metric_tools - expected_tool_calls) * 30.0

        metric_duration = data.get("total_wall_time_ms")
        if expected_duration is not None and metric_duration is not None:
            score += abs(float(metric_duration) - float(expected_duration)) / 1000.0

        candidates.append((match_rank, score, path, data))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates[0][3]
