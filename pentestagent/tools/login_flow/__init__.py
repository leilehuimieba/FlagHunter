"""Automated login flow tool for web applications."""

from __future__ import annotations

import json
import time as _time
from datetime import datetime as _dt
from typing import TYPE_CHECKING

from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


def _cookie_names_from_cookie_string(cookie_string: str) -> list[str]:
    names: list[str] = []
    seen = set()
    for chunk in cookie_string.split(";"):
        name = chunk.split("=", 1)[0].strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names


async def run_login_flow(
    login_url: str,
    username_selector: str,
    password_selector: str,
    username: str,
    password: str,
    submit_selector: str = "",
    runtime=None,
    timeout: int = 30,
) -> dict:
    """
    Automate login and return session cookies in a structured result.

    Returns:
        {
          "success": bool,
          "login_url": str,
          "submitted_url": str,
          "submitted_via": str,
          "cookie_string": str,
          "cookie_count": int,
          "cookie_names": list[str],
          "cookies": list[dict],
          "final_url": str,
          "submission": dict,
          "attempted_actions": list[str],
          "error": str,
        }
    """
    empty_result = {
        "success": False,
        "login_url": login_url,
        "submitted_url": "",
        "submitted_via": "",
        "cookie_string": "",
        "cookie_count": 0,
        "cookie_names": [],
        "cookies": [],
        "final_url": "",
        "submission": {
            "field_selectors": [username_selector, password_selector],
            "submit_selector": submit_selector,
        },
        "attempted_actions": ["navigate", "submit_form", "get_cookies"],
        "error": "",
    }

    if runtime is None:
        return {
            **empty_result,
            "error": "runtime required",
        }

    if type(runtime).__name__ == "SSHRuntime":
        return {
            **empty_result,
            "error": "login_flow requires LocalRuntime with Playwright browser",
        }

    try:
        timeout = max(1, int(timeout))
    except (TypeError, ValueError):
        timeout = 30

    try:
        nav = await runtime.browser_action(
            "navigate",
            url=login_url,
            timeout=timeout,
        )
        if "error" in nav:
            return {
                **empty_result,
                "error": str(nav["error"]),
            }

        sub = await runtime.browser_action(
            "submit_form",
            fields={
                username_selector: username,
                password_selector: password,
            },
            submit=submit_selector,
            timeout=timeout,
        )
        if "error" in sub:
            return {
                **empty_result,
                "error": str(sub["error"]),
            }

        ck = await runtime.browser_action("get_cookies", timeout=timeout)
        if "error" in ck:
            return {
                **empty_result,
                "error": str(ck["error"]),
            }

        cookie_string = str(ck.get("cookie_string") or "").strip()
        cookies = ck.get("cookies", [])
        if not cookie_string and isinstance(cookies, list):
            derived_cookie_string = "; ".join(
                f"{cookie.get('name')}={cookie.get('value')}"
                for cookie in cookies
                if isinstance(cookie, dict) and cookie.get("name")
            )
            cookie_string = derived_cookie_string.strip()

        cookie_count = ck.get("cookie_count")
        if not isinstance(cookie_count, int):
            cookie_count = len(cookies) if isinstance(cookies, list) else 0

        cookie_names = ck.get("cookie_names")
        if not isinstance(cookie_names, list):
            cookie_names = []
        cookie_names = [str(name) for name in cookie_names if str(name).strip()]
        if not cookie_names:
            cookie_names = _cookie_names_from_cookie_string(cookie_string)

        final_url = str(sub.get("url", login_url) or login_url)
        submitted_via = submit_selector or "enter"
        submitted_url = final_url

        if not cookie_string:
            return {
                "success": False,
                "error": f"Login may have failed — still on {final_url}",
                "cookie_string": cookie_string,
                "cookies": cookies,
                "final_url": final_url,
                "login_url": login_url,
                "submitted_url": submitted_url,
                "submitted_via": submitted_via,
                "cookie_count": cookie_count,
                "cookie_names": cookie_names,
                "submission": {
                    "field_selectors": [username_selector, password_selector],
                    "submit_selector": submit_selector,
                },
                "attempted_actions": ["navigate", "submit_form", "get_cookies"],
            }

        if cookie_string:
            try:
                from ..notes import (
                    _ensure_notes_loaded_unlocked,
                    _notes,
                    _notes_lock,
                    _save_notes_unlocked,
                )

                note_key = f"login_cookie_{int(_time.time())}"
                async with _notes_lock:
                    _ensure_notes_loaded_unlocked()
                    _notes[note_key] = {
                        "content": f"Session cookie from {login_url}",
                        "category": "credential",
                        "confidence": "high",
                        "status": "confirmed",
                        "metadata": {
                            "cookie": cookie_string,
                            "cookie_names": cookie_names,
                            "cookie_count": cookie_count,
                            "target": login_url,
                            "username": username,
                            "submitted_url": submitted_url,
                            "submitted_via": submitted_via,
                            "submission": {
                                "field_selectors": [
                                    username_selector,
                                    password_selector,
                                ],
                                "submit_selector": submit_selector,
                            },
                            "obtained_at": _dt.now().isoformat(),
                        },
                    }
                    _save_notes_unlocked()
            except Exception:
                pass

        return {
            "success": True,
            "login_url": login_url,
            "submitted_url": submitted_url,
            "submitted_via": submitted_via,
            "cookie_string": cookie_string,
            "cookies": cookies,
            "cookie_count": cookie_count,
            "cookie_names": cookie_names,
            "final_url": final_url,
            "submission": {
                "field_selectors": [username_selector, password_selector],
                "submit_selector": submit_selector,
            },
            "attempted_actions": ["navigate", "submit_form", "get_cookies"],
            "error": "",
        }

    except Exception as exc:
        return {
            **empty_result,
            "error": str(exc),
        }


@register_tool(
    name="login_flow",
    description=(
        "Automate web application login: navigate to login page, fill credentials, "
        "submit form, and extract session cookies. Returns structured JSON with "
        "success, login_url, submitted_url, cookie_string, cookie_names, cookies, "
        "and submission metadata. Saves cookies to notes automatically so subsequent "
        "sqlmap/dirscan/nuclei steps can use them without manual input."
    ),
    schema=ToolSchema(
        properties={
            "login_url": {
                "type": "string",
                "description": "URL of the login page (e.g. 'http://192.168.1.1/login.php')",
            },
            "username_selector": {
                "type": "string",
                "description": "CSS selector for username field (e.g. '#username', 'input[name=username]')",
            },
            "password_selector": {
                "type": "string",
                "description": "CSS selector for password field (e.g. '#password', 'input[name=password]')",
            },
            "username": {
                "type": "string",
                "description": "Username to log in with",
            },
            "password": {
                "type": "string",
                "description": "Password to log in with",
            },
            "submit_selector": {
                "type": "string",
                "description": "CSS selector for submit button. If empty, presses Enter on password field.",
                "default": "",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout per step in seconds (default: 30)",
                "default": 30,
            },
        },
        required=[
            "login_url",
            "username_selector",
            "password_selector",
            "username",
            "password",
        ],
    ),
    category="web",
)
async def login_flow(arguments: dict, runtime: "Runtime") -> str:
    result = await run_login_flow(
        login_url=arguments["login_url"],
        username_selector=arguments["username_selector"],
        password_selector=arguments["password_selector"],
        username=arguments["username"],
        password=arguments["password"],
        submit_selector=arguments.get("submit_selector", ""),
        runtime=runtime,
        timeout=arguments.get("timeout", 30),
    )
    return json.dumps(result, ensure_ascii=False)
