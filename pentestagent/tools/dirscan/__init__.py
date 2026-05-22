"""Structured directory enumeration tool wrapper."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from .._tool_env import patch_tool_path, find_tool
from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime

patch_tool_path()


DEFAULT_EXTENSIONS = ["php", "html", "js"]
DEFAULT_WORDLIST = "/usr/share/wordlists/dirb/common.txt"
AUTO_TOOL_PRIORITY = ["ffuf", "gobuster", "dirsearch"]
WORDLIST_CANDIDATES = [
    str(Path(__file__).resolve().parents[2] / "tools" / "wordlists" / "common.txt"),
    "/usr/share/wordlists/dirb/common.txt",
    "/usr/share/dirb/wordlists/common.txt",
    "C:/Tools/wordlists/common.txt",
    str(Path(__file__).parent.parent.parent / "loot" / "common_paths.txt"),
]
MINI_WORDLIST_CONTENT = """admin
login
login.php
index.php
index.html
config
config.php
phpinfo.php
robots.txt
favicon.ico
setup.php
setup
dashboard
wp-admin
wp-login.php
uploads
static
assets
js
css
images
api
v1
v2
docs
swagger
swagger.json
openapi.json
.git
.env
backup
tmp
test
dev
staging
debug
server-status
server-info
phpmyadmin
adminer
console
register
signup
logout
profile
user
users
account
"""


def _decode(raw: bytes) -> str:
    if isinstance(raw, str):
        return raw
    for enc in ("utf-8", "gbk", "cp936", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _normalize_text(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    return _decode(raw).encode("utf-8", "replace").decode("utf-8")


def _quote(value: str) -> str:
    """Best-effort shell-safe quoting for simple string arguments."""
    return json.dumps(str(value))


def _normalize_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    if not headers:
        return normalized

    for key, value in headers.items():
        if key is None or value is None:
            continue
        header_key = str(key).strip()
        if not header_key:
            continue
        normalized[header_key] = str(value)
    return normalized


def _append_dirscan_headers(
    parts: list[str], tool_name: str, headers: dict[str, Any] | None
) -> None:
    normalized_headers = _normalize_headers(headers)
    if not normalized_headers:
        return

    normalized_tool = str(tool_name or "").strip().lower()
    for key, value in normalized_headers.items():
        header_value = f"{key}: {value}"
        if normalized_tool == "gobuster":
            parts.extend(["--headers", _quote(header_value)])
        else:
            parts.extend(["-H", _quote(header_value)])


def _ensure_mini_wordlist() -> str:
    loot_dir = Path(__file__).resolve().parents[3] / "loot"
    loot_dir.mkdir(parents=True, exist_ok=True)
    mini_wordlist = loot_dir / "mini_wordlist.txt"
    if not mini_wordlist.exists():
        mini_wordlist.write_text(MINI_WORDLIST_CONTENT, encoding="utf-8")
    return str(mini_wordlist)


def _resolve_wordlist(wordlist: str | None) -> str | None:
    if wordlist and Path(wordlist).exists():
        return wordlist
    for candidate in WORDLIST_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return _ensure_mini_wordlist()


def _normalize_extensions(extensions: list[str] | None) -> list[str]:
    if not extensions:
        return list(DEFAULT_EXTENSIONS)

    normalized: list[str] = []
    seen: set[str] = set()
    for ext in extensions:
        clean = str(ext).strip().lstrip(".")
        if not clean:
            continue
        lower = clean.lower()
        if lower in seen:
            continue
        seen.add(lower)
        normalized.append(clean)
    return normalized


def _ensure_leading_slash(path: str) -> str:
    if not path:
        return "/"
    return path if path.startswith("/") else f"/{path}"


def _path_from_url(full_url: str, base_url: str) -> str:
    if not full_url:
        return "/"

    try:
        full = urlparse(full_url)
        base = urlparse(base_url)
    except Exception:
        return _ensure_leading_slash(full_url)

    if full.scheme and full.netloc:
        if full.scheme == base.scheme and full.netloc == base.netloc and full.path:
            return _ensure_leading_slash(full.path)
        return full_url

    return _ensure_leading_slash(full.path or full_url)


def _parse_size(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_human_size(value: str | None) -> int:
    if not value:
        return 0

    text = str(value).strip().upper()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMG]?B)?", text)
    if not match:
        return 0

    number = float(match.group(1))
    unit = match.group(2) or "B"
    multiplier = {
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
    }.get(unit, 1)
    return int(number * multiplier)


async def _local_execute(command: str, timeout: int = 300) -> dict[str, Any]:
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        await process.communicate()
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
        }

    return {
        "exit_code": process.returncode or 0,
        "stdout": _normalize_text(stdout),
        "stderr": _normalize_text(stderr),
    }


async def _runtime_execute(
    runtime: "Runtime | None", command: str, timeout: int = 300
) -> dict[str, Any]:
    if runtime is None:
        return await _local_execute(command, timeout=timeout)

    if hasattr(runtime, "execute_command"):
        result = await runtime.execute_command(command, timeout=timeout)
        return {
            "exit_code": getattr(result, "exit_code", 0),
            "stdout": _normalize_text(getattr(result, "stdout", "") or ""),
            "stderr": _normalize_text(getattr(result, "stderr", "") or ""),
        }

    if hasattr(runtime, "execute"):
        result = await runtime.execute(command)
        if isinstance(result, dict):
            return {
                "exit_code": result.get("exit_code", 0),
                "stdout": _normalize_text(result.get("stdout", "") or ""),
                "stderr": _normalize_text(result.get("stderr", "") or ""),
            }
        return {
            "exit_code": getattr(result, "exit_code", 0),
            "stdout": _normalize_text(getattr(result, "stdout", "") or ""),
            "stderr": _normalize_text(getattr(result, "stderr", "") or ""),
        }

    raise RuntimeError("Runtime does not support command execution")


async def _wordlist_exists(wordlist: str, runtime: "Runtime | None") -> bool:
    if Path(wordlist).exists():
        return True

    # Best-effort remote/runtime existence check using Python.
    for python_bin in ("python", "python3"):
        cmd = (
            f'{python_bin} -c "import os,sys;'
            f"sys.stdout.write('1' if os.path.isfile(sys.argv[1]) else '0')\" "
            f"{_quote(wordlist)}"
        )
        try:
            result = await _runtime_execute(runtime, cmd, timeout=20)
        except Exception:
            continue

        if result["exit_code"] == 0 and result["stdout"].strip() == "1":
            return True

    return False


def _build_ffuf_command(
    url: str, wordlist: str, extensions: list[str], headers: dict[str, Any] | None = None
) -> str:
    ext_arg = ",".join(f".{ext}" for ext in extensions) if extensions else ""
    parts = [
        "ffuf",
        "-u",
        _quote(url.rstrip("/") + "/FUZZ"),
        "-w",
        _quote(wordlist),
        "-json",
        "-noninteractive",
    ]
    if ext_arg:
        parts.extend(["-e", _quote(ext_arg)])
    _append_dirscan_headers(parts, "ffuf", headers)
    return " ".join(parts)


def _build_gobuster_command(
    url: str, wordlist: str, extensions: list[str], headers: dict[str, Any] | None = None
) -> str:
    ext_arg = ",".join(extensions) if extensions else ""
    parts = [
        "gobuster",
        "dir",
        "-u",
        _quote(url),
        "-w",
        _quote(wordlist),
        "-q",
        "--no-error",
    ]
    if ext_arg:
        parts.extend(["-x", _quote(ext_arg)])
    _append_dirscan_headers(parts, "gobuster", headers)
    return " ".join(parts)


def _build_dirsearch_command(
    url: str, wordlist: str, extensions: list[str], headers: dict[str, Any] | None = None
) -> str:
    parts = [
        "dirsearch",
        "-u",
        _quote(url),
        "-w",
        _quote(wordlist),
        "--format=plain",
        "-q",
    ]
    if extensions:
        parts.extend(["-e", _quote(",".join(extensions))])
    _append_dirscan_headers(parts, "dirsearch", headers)
    return " ".join(parts)


def _parse_ffuf_output(raw: str, base_url: str) -> tuple[list[dict[str, Any]], bool]:
    raw = raw.strip()
    if not raw:
        return [], True

    findings: list[dict[str, Any]] = []

    # Full JSON document with "results"
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict) and isinstance(payload.get("results"), list):
            for item in payload["results"]:
                if not isinstance(item, dict):
                    continue
                path = _path_from_url(str(item.get("url", "")), base_url)
                if not path or path == "/":
                    input_data = item.get("input")
                    if isinstance(input_data, dict):
                        fuzz_value = str(input_data.get("FUZZ", "")).strip()
                        if fuzz_value:
                            path = _ensure_leading_slash(fuzz_value)

                findings.append(
                    {
                        "path": path,
                        "status": int(item.get("status", 0) or 0),
                        "size": _parse_size(
                            item.get("length", item.get("content-length", 0))
                        ),
                    }
                )
            return findings, True
    except json.JSONDecodeError:
        pass

    # JSONL output (`ffuf -json`)
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    parsed_any = False
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not isinstance(item, dict):
            continue

        parsed_any = True
        path = _path_from_url(str(item.get("url", "")), base_url)
        if not path or path == "/":
            input_data = item.get("input")
            if isinstance(input_data, dict):
                fuzz_value = str(input_data.get("FUZZ", "")).strip()
                if fuzz_value:
                    path = _ensure_leading_slash(fuzz_value)

        findings.append(
            {
                "path": path,
                "status": int(item.get("status", 0) or 0),
                "size": _parse_size(item.get("length", item.get("content-length", 0))),
            }
        )

    return findings, parsed_any


_GOBUSTER_LINE_RE = re.compile(
    r"(?P<path>/\S+)\s+\(Status:\s*(?P<status>\d+)\)(?:\s+\[Size:\s*(?P<size>\d+)\])?",
    re.IGNORECASE,
)


def _parse_gobuster_output(raw: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line in raw.splitlines():
        match = _GOBUSTER_LINE_RE.search(line.strip())
        if not match:
            continue

        findings.append(
            {
                "path": match.group("path"),
                "status": int(match.group("status")),
                "size": _parse_size(match.group("size")),
            }
        )
    return findings


_DIRSEARCH_LINE_RE = re.compile(
    r"^\[\d{2}:\d{2}:\d{2}\]\s+"
    r"(?P<status>\d{3})\s+-\s+"
    r"(?P<size>\S+)\s+-\s+"
    r"(?P<url>\S+?)(?:\s+->\s+\S+)?$"
)


def _parse_dirsearch_output(raw: str, base_url: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line in raw.splitlines():
        match = _DIRSEARCH_LINE_RE.match(line.strip())
        if not match:
            continue

        target_url = match.group("url").strip()
        findings.append(
            {
                "path": _path_from_url(target_url, base_url),
                "status": int(match.group("status")),
                "size": _parse_human_size(match.group("size")),
            }
        )
    return findings


async def _run_with_ffuf(
    url: str,
    wordlist: str,
    extensions: list[str],
    runtime: "Runtime | None",
    headers: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    command = _build_ffuf_command(url, wordlist, extensions, headers=headers)
    execution = await _runtime_execute(runtime, command, timeout=300)
    raw = "\n".join(part for part in (execution["stdout"], execution["stderr"]) if part)
    found, parsed = _parse_ffuf_output(execution["stdout"], url)

    result = {
        "url": url,
        "tool_used": "ffuf",
        "found": found,
        "total_found": len(found),
        "raw": raw,
    }

    success = execution["exit_code"] == 0 and parsed
    return result, success


async def _run_with_gobuster(
    url: str,
    wordlist: str,
    extensions: list[str],
    runtime: "Runtime | None",
    headers: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    command = _build_gobuster_command(url, wordlist, extensions, headers=headers)
    execution = await _runtime_execute(runtime, command, timeout=300)
    raw = "\n".join(part for part in (execution["stdout"], execution["stderr"]) if part)
    found = _parse_gobuster_output(raw)

    result = {
        "url": url,
        "tool_used": "gobuster",
        "found": found,
        "total_found": len(found),
        "raw": raw,
    }

    success = execution["exit_code"] == 0 or bool(found)
    return result, success


async def _run_with_dirsearch(
    url: str,
    wordlist: str,
    extensions: list[str],
    runtime: "Runtime | None",
    headers: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    command = _build_dirsearch_command(url, wordlist, extensions, headers=headers)
    execution = await _runtime_execute(runtime, command, timeout=300)
    raw = "\n".join(part for part in (execution["stdout"], execution["stderr"]) if part)
    found = _parse_dirsearch_output(raw, url)

    result = {
        "url": url,
        "tool_used": "dirsearch",
        "found": found,
        "total_found": len(found),
        "raw": raw,
    }

    success = execution["exit_code"] == 0 or bool(found)
    return result, success


async def run_dirscan(
    url: str,
    wordlist: str | None = DEFAULT_WORDLIST,
    extensions: list[str] = ["php", "html", "js"],
    tool: str = "auto",
    headers: dict[str, Any] | None = None,
    runtime=None,
) -> dict:
    """
    Run directory enumeration and return structured results.

    Returns:
        {
          "url": "http://target.com",
          "tool_used": "ffuf" | "gobuster" | "",
          "found": [{"path": "/admin", "status": 200, "size": 4096}],
          "total_found": 1,
          "raw": "...",
          "error": "..."   # optional
        }
    """
    result: dict[str, Any] = {
        "url": url,
        "tool_used": "",
        "found": [],
        "total_found": 0,
        "raw": "",
    }

    normalized_tool = str(tool or "auto").strip().lower()
    normalized_extensions = _normalize_extensions(extensions)

    if normalized_tool not in {"auto", "ffuf", "gobuster", "dirsearch"}:
        result["error"] = f"unsupported tool: {tool}"
        return result

    if runtime is None:
        available_tools = {
            "ffuf": bool(find_tool("ffuf")),
            "gobuster": bool(find_tool("gobuster")),
            "dirsearch": bool(find_tool("dirsearch")),
        }
        if normalized_tool != "auto" and not available_tools.get(normalized_tool, False):
            result["error"] = f"{normalized_tool} not installed"
            return result
        if normalized_tool == "auto" and not any(available_tools.values()):
            result["error"] = "ffuf, gobuster, and dirsearch are not installed"
            return result

    wordlist = _resolve_wordlist(wordlist)
    if not await _wordlist_exists(wordlist, runtime):
        result["error"] = "wordlist not found"
        return result

    if normalized_tool == "ffuf":
        ffuf_result, _ = await _run_with_ffuf(
            url, wordlist, normalized_extensions, runtime, headers=headers
        )
        return ffuf_result

    if normalized_tool == "gobuster":
        gobuster_result, _ = await _run_with_gobuster(
            url, wordlist, normalized_extensions, runtime, headers=headers
        )
        return gobuster_result

    if normalized_tool == "dirsearch":
        dirsearch_result, _ = await _run_with_dirsearch(
            url, wordlist, normalized_extensions, runtime, headers=headers
        )
        return dirsearch_result

    attempts: list[dict[str, Any]] = []
    runners = {
        "ffuf": _run_with_ffuf,
        "gobuster": _run_with_gobuster,
        "dirsearch": _run_with_dirsearch,
    }
    for tool_name in AUTO_TOOL_PRIORITY:
        if runtime is None and not find_tool(tool_name):
            continue
        tool_result, ok = await runners[tool_name](
            url, wordlist, normalized_extensions, runtime, headers=headers
        )
        attempts.append(tool_result)
        if ok:
            return tool_result

    fallback = attempts[-1] if attempts else result
    raw_parts = [attempt.get("raw", "") for attempt in attempts if attempt.get("raw")]
    if raw_parts:
        fallback["raw"] = "\n\n--- fallback ---\n\n".join(raw_parts)
    fallback["error"] = "ffuf, gobuster, and dirsearch all failed"
    return fallback


@register_tool(
    name="dirscan",
    description="Enumerate web directories/files and return structured JSON results.",
    schema=ToolSchema(
        properties={
            "url": {
                "type": "string",
                "description": "Target base URL, e.g. http://127.0.0.1",
            },
            "wordlist": {
                "type": "string",
                "description": "Path to wordlist file",
                "default": DEFAULT_WORDLIST,
            },
            "extensions": {
                "type": "array",
                "description": "Optional file extensions to append",
            },
            "tool": {
                "type": "string",
                "description": "Tool selector: auto, ffuf, gobuster, or dirsearch",
                "default": "auto",
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers to pass through to the underlying scanner",
            },
        },
        required=["url"],
    ),
    category="recon",
)
async def dirscan(arguments: dict, runtime: "Runtime") -> str:
    result = await run_dirscan(
        url=arguments["url"],
        wordlist=arguments.get("wordlist", DEFAULT_WORDLIST),
        extensions=arguments.get("extensions", list(DEFAULT_EXTENSIONS)),
        tool=arguments.get("tool", "auto"),
        headers=arguments.get("headers", {}) or {},
        runtime=runtime,
    )
    return json.dumps(result, ensure_ascii=False)


__all__ = ["run_dirscan", "_resolve_wordlist"]
