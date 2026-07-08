"""Task-attachment upload/list HTTP route handlers for the web console.

Third slice extracted from ``web_server._make_handlers`` (the ~1270-line route
factory), following ``web_memory_routes`` and ``web_settings_routes``. These two
handlers persist and list per-task uploads under ``loot/uploads/{taskId}/``. They
close over ``project_root`` only and up-call no ``web_server`` module state beyond
``logger`` (re-bound here under the same name so log records stay byte-identical),
so the sibling imports nothing from ``web_server`` (no cycle).

``make_attachment_handlers(project_root)`` returns the same ``{route_name: handler}``
slice the factory produced inline; ``_make_handlers`` merges it via
``**attachment_handlers`` so the route wiring in ``create_app`` is unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from aiohttp import web

# Same logger name as web_server so log records stay byte-identical after the
# extraction.
logger = logging.getLogger("flaghunter.interface.web_server")


def make_attachment_handlers(project_root: Path) -> dict[str, Callable]:
    async def post_attachments(req: web.Request) -> web.Response:
        """POST /api/tasks/{taskId}/attachments  — multipart/form-data
        Saves uploaded files to loot/uploads/{taskId}/ and returns metadata.
        """
        task_id = req.match_info.get("taskId", "").strip()
        if not task_id:
            return web.Response(status=400, text="taskId required")

        upload_dir = project_root / "loot" / "uploads" / task_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        saved: list[dict] = []
        try:
            reader = await req.multipart()
            async for part in reader:
                if part.name != "files":
                    continue
                filename = part.filename or f"file_{len(saved)}"
                # Sanitise filename: strip path separators
                filename = Path(filename).name or f"file_{len(saved)}"
                dest = upload_dir / filename
                # Avoid overwrite: append suffix if exists
                stem, suffix = dest.stem, dest.suffix
                counter = 1
                while dest.exists():
                    dest = upload_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

                size = 0
                with dest.open("wb") as fh:
                    while True:
                        chunk = await part.read_chunk(65536)
                        if not chunk:
                            break
                        fh.write(chunk)
                        size += len(chunk)

                saved.append({
                    "name": filename,
                    "saved_as": dest.name,
                    "size": size,
                    "path": str(dest.relative_to(project_root)),
                })
                logger.info("Attachment saved: %s (%d bytes) for task %s", dest, size, task_id)

        except Exception as exc:
            logger.exception("post_attachments error for task %s: %s", task_id, exc)
            return web.Response(status=500, text=str(exc))

        return web.json_response({"taskId": task_id, "files": saved})

    async def get_attachments(req: web.Request) -> web.Response:
        """GET /api/tasks/{taskId}/attachments — list uploaded files for a task."""
        task_id = req.match_info.get("taskId", "").strip()
        upload_dir = project_root / "loot" / "uploads" / task_id
        if not upload_dir.exists():
            return web.json_response({"taskId": task_id, "files": []})
        files = []
        for p in sorted(upload_dir.iterdir()):
            if p.is_file():
                files.append({
                    "name": p.name,
                    "saved_as": p.name,
                    "size": p.stat().st_size,
                    "path": str(p.relative_to(project_root)),
                })
        return web.json_response({"taskId": task_id, "files": files})

    return {
        "post_attachments": post_attachments,
        "get_attachments": get_attachments,
    }
