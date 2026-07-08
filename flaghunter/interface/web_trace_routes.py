"""Read-only trace-view HTTP route handlers for the web console.

Fifth and final clean slice extracted from ``web_server._make_handlers`` (the
~1270-line route factory), following the memory / settings / attachment /
knowledge extractions. These two read-only handlers list and fetch trace payloads
for tasks. ``_parse_iso`` (``web_leaf_utils``) is an already-extracted leaf and
the datetime helpers are stdlib.

Two web_server-resident dependencies are **injected** rather than imported: the
core task registry ``_tasks`` (a module-level dict mutated in place, never
reassigned — so the captured reference stays live) and ``_build_trace_payload``
(a local aggregator). Injection keeps this sibling cycle-free and the handler
bodies byte-identical. The task-spawning ``replay_trace`` handler is intentionally
NOT moved: it is bound to the module's stateful core (``_bus``/``_run_agent_task``/
``_persist_tasks`` and the large ingress/resume helper web) and stays in
web_server.

``make_trace_handlers(project_root, _tasks, _build_trace_payload)`` returns the
same ``{route_name: handler}`` slice the factory produced inline; ``_make_handlers``
merges it via ``**trace_handlers`` so the route wiring in ``create_app`` is
unchanged.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from aiohttp import web

from .web_leaf_utils import _parse_iso

# Same logger name as web_server for byte-identical log records (unused on the
# happy path here, kept for parity with the sibling extractions).
logger = logging.getLogger("flaghunter.interface.web_server")


def make_trace_handlers(project_root: Path, _tasks: dict, _build_trace_payload: Callable) -> dict[str, Callable]:
    async def get_traces(req: web.Request) -> web.Response:
        window_filter = str(req.rel_url.query.get("window") or "24h").lower()
        if window_filter not in {"24h", "all"}:
            window_filter = "24h"
        target_filter = str(req.rel_url.query.get("target") or "all").strip()

        now_dt = datetime.now(timezone.utc)
        window_tasks: list[dict[str, Any]] = []
        for task in _tasks.values():
            if window_filter == "24h":
                task_time = _parse_iso(task.get("startedAt")) or _parse_iso(task.get("createdAt"))
                if not task_time or (now_dt - task_time) > timedelta(hours=24):
                    continue
            window_tasks.append(task)

        available_targets = sorted(
            {
                str(task.get("target") or "").strip()
                for task in window_tasks
                if str(task.get("target") or "").strip()
            }
        )
        target_options = ["all", *available_targets]
        if target_filter not in target_options:
            target_filter = "all"

        filtered_tasks = [
            task
            for task in window_tasks
            if target_filter == "all" or str(task.get("target") or "").strip() == target_filter
        ]

        filtered_tasks.sort(key=lambda t: t.get("createdAt") or t.get("startedAt") or "", reverse=True)
        traces = [_build_trace_payload(project_root, t, include_timeline=False) for t in filtered_tasks]
        return web.json_response({
            "items": traces,
            "filters": {
                "window": window_filter,
                "target": target_filter,
                "targets": target_options,
            },
        })

    async def get_trace(req: web.Request) -> web.Response:
        run_id = req.match_info["runId"]
        task = next((t for t in _tasks.values() if t.get("currentRunId", t.get("id")) == run_id), None)
        if not task:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response(_build_trace_payload(project_root, task, include_timeline=True))

    return {
        "get_traces": get_traces,
        "get_trace": get_trace,
    }
