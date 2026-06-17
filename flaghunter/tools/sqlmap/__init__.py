"""Structured sqlmap wrapper for PentestAgent."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .._tool_env import patch_tool_path, find_tool
from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime

patch_tool_path()


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


def _shell_quote(value: str) -> str:
    """Best-effort shell quoting compatible with current runtime usage."""
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


def _default_result(raw: str = "") -> dict[str, Any]:
    return {
        "vulnerable": False,
        "injection_points": [],
        "databases": [],
        "raw": raw,
    }


async def _execute_command(
    runtime: "Runtime | None", command: str, timeout: int = 1800
) -> Any:
    if runtime is None:
        from ...runtime import LocalRuntime

        runtime = LocalRuntime()

    if hasattr(runtime, "execute_command"):
        return await runtime.execute_command(command, timeout=timeout)

    if hasattr(runtime, "execute"):
        return await runtime.execute(command, timeout=timeout)

    raise RuntimeError("runtime does not support command execution")


def _is_remote_container_runtime(runtime: "Runtime | None") -> bool:
    """Detect whether runtime supports explicit container file staging."""
    return runtime is not None and hasattr(runtime, "copy_to_container")


async def _probe_sqlmap(runtime: "Runtime | None") -> tuple[bool, str]:
    if runtime is None and not find_tool("sqlmap"):
        return False, "sqlmap not installed"

    result = await _execute_command(runtime, "sqlmap --version", timeout=20)
    raw = "\n".join(
        part
        for part in [
            _normalize_text(getattr(result, "stdout", "") or ""),
            _normalize_text(getattr(result, "stderr", "") or ""),
        ]
        if part
    )
    if getattr(result, "exit_code", 0) == 0:
        return True, raw

    lowered = raw.lower()
    if any(
        marker in lowered
        for marker in ("not recognized", "not found", "command not found", "no such file")
    ):
        return False, raw

    return True, raw


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _parse_injection_points(raw: str) -> list[dict[str, str]]:
    points: list[dict[str, str]] = []
    pattern = re.compile(
        r"Parameter:\s*(?P<parameter>.+?)\s*(?:\([^)]*\))?\s*"
        r"(?:\r?\n|\r)+\s*Type:\s*(?P<type>.+?)\s*"
        r"(?:\r?\n|\r)+.*?"
        r"(?:Payload:\s*(?P<payload>.+?)\s*(?=(?:\r?\n\r?\n|\r\r|---|Parameter:|$)))",
        re.IGNORECASE | re.DOTALL,
    )

    dbms_match = re.search(
        r"(?:back-end DBMS|web application technology and back-end DBMS):\s*(?P<dbms>.+)",
        raw,
        flags=re.IGNORECASE,
    )
    dbms_value = dbms_match.group("dbms").strip() if dbms_match else ""

    for match in pattern.finditer(raw):
        points.append(
            {
                "parameter": match.group("parameter").strip(),
                "type": match.group("type").strip(),
                "dbms": dbms_value,
                "payload": (match.group("payload") or "").strip(),
            }
        )

    if not points:
        simple_param = re.findall(r"Parameter:\s*(.+)", raw, flags=re.IGNORECASE)
        simple_payloads = re.findall(r"Payload:\s*(.+)", raw, flags=re.IGNORECASE)
        simple_types = re.findall(r"Type:\s*(.+)", raw, flags=re.IGNORECASE)
        for idx, parameter in enumerate(simple_param):
            points.append(
                {
                    "parameter": parameter.strip(),
                    "type": simple_types[idx].strip() if idx < len(simple_types) else "",
                    "dbms": dbms_value,
                    "payload": simple_payloads[idx].strip() if idx < len(simple_payloads) else "",
                }
            )

    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for point in points:
        key = (point.get("parameter", ""), point.get("type", ""), point.get("payload", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(point)
    return deduped


def _parse_databases(raw: str) -> list[str]:
    databases: list[str] = []

    block_match = re.search(
        r"available databases\s*\[\d+\]:\s*(?P<body>.*?)(?=(?:\r?\n\r?\n|\r\r|$))",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if block_match:
        body = block_match.group("body")
        for line in body.splitlines():
            candidate = line.strip().lstrip("[*]").strip("- ").strip()
            if candidate:
                databases.append(candidate)

    inline_matches = re.findall(r"Database:\s*([A-Za-z0-9_$-]+)", raw, flags=re.IGNORECASE)
    databases.extend(match.strip() for match in inline_matches if match.strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for db in databases:
        lower = db.lower()
        if lower in seen:
            continue
        seen.add(lower)
        deduped.append(db)
    return deduped


async def _collect_remote_artifacts(
    runtime: "Runtime | None", output_dir: str
) -> str:
    find_cmd = (
        f"find {_shell_quote(output_dir)} -maxdepth 4 -type f "
        f"\\( -name '*.txt' -o -name '*.log' -o -name '*.csv' \\) "
        f"-print 2>/dev/null"
    )
    result = await _execute_command(runtime, find_cmd, timeout=20)
    stdout = _normalize_text(getattr(result, "stdout", "") or "")
    files = [line.strip() for line in stdout.splitlines() if line.strip()]
    collected: list[str] = []
    for file_path in files[:20]:
        cat_result = await _execute_command(
            runtime, f"cat {_shell_quote(file_path)} 2>/dev/null", timeout=20
        )
        content = _normalize_text(getattr(cat_result, "stdout", "") or "")
        if content:
            collected.append(content)
    return "\n".join(collected)


def _collect_local_artifacts(output_dir: Path) -> str:
    contents: list[str] = []
    if not output_dir.exists():
        return ""

    for file in output_dir.rglob("*"):
        if not file.is_file():
            continue
        if file.suffix.lower() not in {".txt", ".log", ".csv"}:
            continue
        content = _read_text(file)
        if content:
            contents.append(content)
    return "\n".join(contents)


async def run_sqlmap(
    url: str,
    data: str = "",
    cookie: str = "",
    level: int = 1,
    risk: int = 1,
    dbms: str = "",
    headers: dict[str, Any] | None = None,
    runtime=None,
) -> dict:
    """
    Run sqlmap and return structured results.

    The registered tool wrapper serializes the returned dictionary to JSON.
    """
    try:
        level = int(level)
        risk = int(risk)
    except (TypeError, ValueError):
        return {
            **_default_result(),
            "error": "level and risk must be integers",
        }

    if level > 3:
        return {**_default_result(), "error": "level must be <= 3"}
    if risk > 2:
        return {**_default_result(), "error": "risk must be <= 2"}
    if level < 1 or risk < 1:
        return {**_default_result(), "error": "level and risk must be >= 1"}

    available, probe_raw = await _probe_sqlmap(runtime)
    if not available:
        return {**_default_result(probe_raw), "error": "sqlmap not installed"}

    remote_mode = _is_remote_container_runtime(runtime)
    temp_dir_obj: tempfile.TemporaryDirectory[str] | None = None
    local_output_dir: Path | None = None

    if remote_mode:
        output_dir_arg = f"/tmp/sqlmap_{uuid4().hex}"
    else:
        temp_dir_obj = tempfile.TemporaryDirectory(prefix="flaghunter_sqlmap_")
        local_output_dir = Path(temp_dir_obj.name)
        output_dir_arg = str(local_output_dir)

    cmd_parts = [
        "sqlmap",
        "-u",
        _shell_quote(url),
        "--batch",
        f"--level={level}",
        f"--risk={risk}",
        f"--output-dir={_shell_quote(output_dir_arg)}",
    ]
    if data:
        cmd_parts.extend(["--data", _shell_quote(data)])
    if cookie:
        cmd_parts.extend(["--cookie", _shell_quote(cookie)])
    if dbms:
        cmd_parts.extend(["--dbms", _shell_quote(dbms)])

    normalized_headers = _normalize_headers(headers)
    if normalized_headers:
        header_cookie = next(
            (value for key, value in normalized_headers.items() if key.lower() == "cookie"),
            "",
        )
        if header_cookie and not cookie:
            cmd_parts.append(f"--cookie={_shell_quote(header_cookie)}")
        for key, value in normalized_headers.items():
            if key.lower() == "cookie":
                continue
            cmd_parts.extend(["-H", _shell_quote(f"{key}: {value}")])

    command = " ".join(cmd_parts)

    try:
        execution = await _execute_command(runtime, command, timeout=1800)
        stdout = _normalize_text(getattr(execution, "stdout", "") or "")
        stderr = _normalize_text(getattr(execution, "stderr", "") or "")
        raw_parts = [probe_raw, stdout, stderr]

        if remote_mode:
            artifact_text = await _collect_remote_artifacts(runtime, output_dir_arg)
        else:
            artifact_text = _collect_local_artifacts(local_output_dir or Path(output_dir_arg))

        if artifact_text:
            raw_parts.append(artifact_text)

        raw = "\n".join(part for part in raw_parts if part).strip()
        injection_points = _parse_injection_points(raw)
        databases = _parse_databases(raw)
        vulnerable = bool(injection_points) or "is vulnerable" in raw.lower()

        result = {
            "vulnerable": vulnerable,
            "injection_points": injection_points,
            "databases": databases,
            "raw": raw,
        }

        if getattr(execution, "exit_code", 0) != 0 and not vulnerable:
            lowered = raw.lower()
            if any(
                marker in lowered
                for marker in ("not recognized", "not found", "command not found", "no such file")
            ):
                result["error"] = "sqlmap not installed"
            elif raw:
                result["error"] = raw
            else:
                result["error"] = "sqlmap execution failed"

        return result
    finally:
        if remote_mode:
            try:
                await _execute_command(runtime, f"rm -rf {_shell_quote(output_dir_arg)}", timeout=20)
            except Exception:
                pass
        elif temp_dir_obj is not None:
            temp_dir_obj.cleanup()


@register_tool(
    name="sqlmap",
    description="Run sqlmap and return structured JSON results for injection findings.",
    schema=ToolSchema(
        properties={
            "url": {
                "type": "string",
                "description": "Target URL to test",
            },
            "data": {
                "type": "string",
                "description": "Optional POST body data",
            },
            "cookie": {
                "type": "string",
                "description": "Optional Cookie header value",
            },
            "level": {
                "type": "integer",
                "description": "sqlmap level (1-3)",
                "default": 1,
            },
            "risk": {
                "type": "integer",
                "description": "sqlmap risk (1-2)",
                "default": 1,
            },
            "dbms": {
                "type": "string",
                "description": "Optional DBMS hint",
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers to pass through to sqlmap",
            },
        },
        required=["url"],
    ),
    category="web_scan",
)
async def sqlmap_tool(arguments: dict, runtime: "Runtime") -> str:
    """Registered PentestAgent sqlmap tool wrapper."""
    result = await run_sqlmap(
        url=arguments["url"],
        data=arguments.get("data", ""),
        cookie=arguments.get("cookie", ""),
        level=arguments.get("level", 1),
        risk=arguments.get("risk", 1),
        dbms=arguments.get("dbms", ""),
        headers=arguments.get("headers", {}) or {},
        runtime=runtime,
    )
    return json.dumps(result, ensure_ascii=False)


__all__ = ["run_sqlmap", "sqlmap_tool"]
