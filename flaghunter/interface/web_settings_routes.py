"""Settings / MCP / runtime-test HTTP route handlers for the web console.

Second slice extracted from ``web_server._make_handlers`` (the ~1270-line route
factory), following ``web_memory_routes``. These four handlers close over
``project_root`` only and up-call no ``web_server`` module state beyond
``logger`` (which is re-bound here under the same name so error-log records stay
byte-identical). Every helper they call — ``_settings_to_api``/``_apply_settings``
/``_mcp_manager_for_project`` (from ``web_settings_io``) and ``_now_iso`` (from
``web_leaf_utils``) — is an already-extracted leaf, imported directly here, so
the sibling imports nothing from ``web_server`` (no cycle).

``make_settings_handlers(project_root)`` returns the same ``{route_name: handler}``
slice the factory produced inline; ``_make_handlers`` merges it via
``**settings_handlers`` so the route wiring in ``create_app`` is unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from aiohttp import web

from .web_leaf_utils import _now_iso
from .web_settings_io import (
    _apply_settings,
    _mcp_manager_for_project,
    _settings_to_api,
)

# Same logger name as web_server so error-log records stay byte-identical after
# the extraction (these handlers only touch the logger on error paths).
logger = logging.getLogger("flaghunter.interface.web_server")


def make_settings_handlers(project_root: Path) -> dict[str, Callable]:
    async def get_settings_handler(req: web.Request) -> web.Response:
        try:
            data = _settings_to_api(project_root)
            return web.json_response(data)
        except Exception as e:
            logger.exception("get_settings error")
            return web.json_response({"error": str(e)}, status=500)

    async def put_settings_handler(req: web.Request) -> web.Response:
        try:
            payload = await req.json()
            result = _apply_settings(project_root, payload)
            return web.json_response({"ok": True, **result, "settings": _settings_to_api(project_root)})
        except Exception as e:
            logger.exception("put_settings error")
            return web.json_response({"error": str(e)}, status=500)

    async def post_mcp_server(req: web.Request) -> web.Response:
        try:
            payload = await req.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        name = str(payload.get("name") or "").strip()
        url = str(payload.get("url") or "").strip()
        if not name:
            return web.json_response({"error": "name required"}, status=400)
        if not url.startswith("http://") and not url.startswith("https://"):
            return web.json_response({"error": "valid sse url required"}, status=400)

        try:
            mcp_manager = _mcp_manager_for_project(project_root)
            mcp_manager.add_sse_server(name=name, url=url)
            return web.json_response({"ok": True, "settings": _settings_to_api(project_root)})
        except Exception as e:
            logger.exception("post_mcp_server error")
            return web.json_response({"error": str(e)}, status=500)

    async def post_runtime_test(req: web.Request) -> web.Response:
        from ..interface import initializer as initializer_module

        settings_payload = _settings_to_api(project_root)
        runtime_cfg = settings_payload.get("runtime", {})
        mode = str(runtime_cfg.get("mode") or "local")
        docker_enabled = bool(runtime_cfg.get("dockerEnabled"))
        auto_ssh = bool(runtime_cfg.get("autoSsh"))

        runtime = None
        try:
            runtime, runtime_info = await initializer_module.build_runtime(
                docker=(mode == "docker") or docker_enabled,
                ssh=(mode == "ssh"),
                auto_ssh=auto_ssh,
            )
            healthy = bool(runtime_info.get("connected")) or runtime_info.get("selected") == "local"
            return web.json_response({
                "ok": True,
                "healthy": healthy,
                "runtime": runtime_info,
                "testedAt": _now_iso(),
            })
        except Exception as e:
            logger.exception("post_runtime_test error")
            return web.json_response({"ok": False, "error": str(e)}, status=500)
        finally:
            if runtime is not None:
                try:
                    await runtime.stop()
                except Exception:
                    pass

    return {
        "get_settings": get_settings_handler,
        "put_settings": put_settings_handler,
        "post_mcp_server": post_mcp_server,
        "post_runtime_test": post_runtime_test,
    }
