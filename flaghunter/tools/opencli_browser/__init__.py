"""OpenCLI browser tool for using the user's logged-in browser profile."""

import asyncio
import shlex
import subprocess
from typing import TYPE_CHECKING

from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


@register_tool(
    name="opencli_browser",
    description=(
        "Use OpenCLI to drive the user's real logged-in browser profile. "
        "Best for authenticated lab platforms such as 春秋、墨者、HTB."
    ),
    schema=ToolSchema(
        properties={
            "action": {
                "type": "string",
                "enum": ["navigate", "extract", "state", "search", "screenshot"],
                "description": "The OpenCLI browser action to perform",
            },
            "url": {
                "type": "string",
                "description": "URL to open when action is 'navigate'",
            },
            "selector": {
                "type": "string",
                "description": (
                    "Selector or query hint for 'extract'/'search' actions"
                ),
            },
        },
        required=["action"],
    ),
    category="web",
)
async def opencli_browser(arguments: dict, runtime: "Runtime") -> str:
    """Use OpenCLI browser commands against the user's default browser profile."""
    action = arguments.get("action", "state")
    url = arguments.get("url", "")
    selector = arguments.get("selector", "")

    cmd_map = {
        "navigate": f"opencli browser default open {shlex.quote(url)}",
        "extract": f"opencli browser default extract {shlex.quote(selector)}",
        "state": "opencli browser default state",
        "search": f"opencli browser default find {shlex.quote(selector)}",
        "screenshot": "opencli browser default screenshot",
    }
    cmd = cmd_map.get(action, "opencli browser default state")

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        return "No output"

    return result.stdout or result.stderr or "No output"
