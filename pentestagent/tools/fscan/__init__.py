"""Structured fscan wrapper for PentestAgent."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .._tool_env import find_tool, patch_tool_path
from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime

patch_tool_path()


_MISSING_MARKERS = (
    "not found",
    "is not recognized",
    "command not found",
    "no such file",
    "cannot find",
    "could not find",
)
_IP_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
_HOST_RE = re.compile(r"(?P<host>(?:\d{1,3}\.){3}\d{1,3}|[A-Za-z0-9._-]+)")
_HOST_PORT_RE = re.compile(
    r"(?P<host>(?:\d{1,3}\.){3}\d{1,3}|[A-Za-z0-9._-]+)"
    r"(?:\:(?P<port1>\d{1,5})|[\s/]+(?P<port2>\d{1,5})(?:/(?:tcp|udp))?)",
    re.IGNORECASE,
)
_SERVICE_HINT_RE = re.compile(
    r"\b(?P<svc>http|https|ssh|ftp|smb|rdp|mysql|mssql|postgres|redis|ldap|"
    r"rpc|snmp|telnet|rtsp|vnc|mongodb|oracle)\b",
    re.IGNORECASE,
)
_VULN_HINT_RE = re.compile(
    r"\b(?P<vuln>CVE-\d{4}-\d+|MS\d{2}-\d+|Zerologon|PrintNightmare|"
    r"BlueKeep|SMBGhost|EternalBlue)\b",
    re.IGNORECASE,
)


def _decode(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    for encoding in ("utf-8", "gbk", "cp936", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _normalize_text(raw: bytes | str | None) -> str:
    return _decode(raw).encode("utf-8", "replace").decode("utf-8")


def _quote(value: str) -> str:
    return json.dumps(str(value))


def _result(target: str, raw: str = "") -> dict[str, Any]:
    return {
        "target": target,
        "hosts_up": [],
        "services": [],
        "vulnerabilities": [],
        "raw": raw,
    }


def _resolve_output_path(runtime: "Runtime | None", filename: str) -> str:
    if runtime is None or runtime.__class__.__name__ == "LocalRuntime":
        if os.name == "nt":
            return str(Path(tempfile.gettempdir()) / filename)
    return f"/tmp/{filename}"


async def _ensure_runtime(runtime: "Runtime | None") -> "Runtime":
    if runtime is not None:
        return runtime

    from ...runtime import LocalRuntime

    return LocalRuntime()


async def _execute(runtime: "Runtime | None", command: str, timeout: int):
    rt = await _ensure_runtime(runtime)
    return await rt.execute_command(command, timeout=timeout)


async def _cleanup_output(runtime: "Runtime | None", output_path: str) -> None:
    if runtime is None or runtime.__class__.__name__ == "LocalRuntime":
        try:
            Path(output_path).unlink(missing_ok=True)
        except Exception:
            pass
        return

    try:
        await _execute(runtime, f"rm -f {_quote(output_path)}", timeout=20)
    except Exception:
        pass


async def _read_output(runtime: "Runtime | None", output_path: str) -> str:
    if runtime is None or runtime.__class__.__name__ == "LocalRuntime":
        try:
            return Path(output_path).read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ""
        except Exception:
            try:
                return _normalize_text(Path(output_path).read_bytes())
            except Exception:
                return ""

    for command in (
        f"cat {_quote(output_path)}",
        f"python -c \"import pathlib,sys; p=pathlib.Path(sys.argv[1]); sys.stdout.write(p.read_text(encoding='utf-8', errors='replace') if p.exists() else '')\" {_quote(output_path)}",
        f"python3 -c \"import pathlib,sys; p=pathlib.Path(sys.argv[1]); sys.stdout.write(p.read_text(encoding='utf-8', errors='replace') if p.exists() else '')\" {_quote(output_path)}",
    ):
        try:
            result = await _execute(runtime, command, timeout=20)
        except Exception:
            continue
        text = _normalize_text(getattr(result, "stdout", "") or "")
        if text or getattr(result, "exit_code", 1) == 0:
            return text

    return ""


def _looks_missing(command_result, extra_text: str = "") -> bool:
    stdout = _normalize_text(getattr(command_result, "stdout", "") or "")
    stderr = _normalize_text(getattr(command_result, "stderr", "") or "")
    lowered = f"{stdout}\n{stderr}\n{extra_text}".lower()
    return any(marker in lowered for marker in _MISSING_MARKERS)


def _append_unique(items: list[Any], value: Any) -> None:
    if value not in items:
        items.append(value)


def _extract_host(line: str) -> str:
    ip_match = _IP_RE.search(line)
    if ip_match:
        return ip_match.group(0)

    host_match = _HOST_RE.search(line)
    if host_match:
        return host_match.group("host")

    return ""


def _parse_service_line(line: str) -> dict[str, Any] | None:
    match = _HOST_PORT_RE.search(line)
    if not match:
        return None

    host = match.group("host") or ""
    port_text = match.group("port1") or match.group("port2") or ""
    try:
        port = int(port_text)
    except ValueError:
        return None

    remainder = line[match.end() :].strip(" :-\t")
    service = ""

    open_match = re.search(r"\bopen\b[\s:/-]*(?P<svc>[A-Za-z0-9._+-]+)", remainder, re.IGNORECASE)
    if open_match:
        service = open_match.group("svc")
    else:
        hint_match = _SERVICE_HINT_RE.search(remainder)
        if hint_match:
            service = hint_match.group("svc")
        elif remainder:
            service = remainder.split()[0]

    return {
        "host": host,
        "port": port,
        "service": service.lower(),
    }


def _parse_vuln_line(line: str) -> dict[str, Any]:
    detail = line[3:].strip() if line.startswith("[!]") else line.strip()
    host = _extract_host(detail)
    vuln = ""

    vuln_match = _VULN_HINT_RE.search(detail)
    if vuln_match:
        vuln = vuln_match.group("vuln")
    else:
        if host:
            detail_without_host = detail.replace(host, "", 1).strip(" :-\t")
        else:
            detail_without_host = detail
        vuln = detail_without_host.split()[0] if detail_without_host else ""

    return {
        "host": host,
        "vuln": vuln,
        "detail": detail,
    }


def _parse_fscan_output(target: str, raw_text: str) -> dict[str, Any]:
    result = _result(target=target, raw=raw_text)

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("[+]"):
            host = _extract_host(line)
            if host:
                _append_unique(result["hosts_up"], host)
            continue

        if line.startswith("[*]") and re.search(r"(?::\d{1,5}\b|\b\d{1,5}/(?:tcp|udp)\b)", line, re.IGNORECASE):
            service_info = _parse_service_line(line)
            if service_info and service_info not in result["services"]:
                result["services"].append(service_info)
                if service_info["host"]:
                    _append_unique(result["hosts_up"], service_info["host"])
            continue

        if line.startswith("[!]"):
            vuln_info = _parse_vuln_line(line)
            if vuln_info not in result["vulnerabilities"]:
                result["vulnerabilities"].append(vuln_info)
                if vuln_info["host"]:
                    _append_unique(result["hosts_up"], vuln_info["host"])

    return result


async def run_fscan(target: str, ports: str = "top100", runtime=None) -> dict:
    """Run fscan and return parsed hosts, services, and vulnerabilities."""
    tool_path = find_tool("fscan")
    result = _result(target=target)

    if not str(target).strip():
        result["raw"] = "target is required"
        return result

    if runtime is None and not tool_path:
        return result

    output_path = _resolve_output_path(runtime, "fscan_out.txt")
    await _cleanup_output(runtime, output_path)

    command_parts = [
        "fscan",
        "-h",
        _quote(str(target).strip()),
    ]
    if str(ports).strip() and str(ports).strip().lower() != "top100":
        command_parts.extend(["-p", _quote(str(ports).strip())])
    command_parts.extend(["-o", _quote(output_path)])
    command = " ".join(command_parts)

    try:
        execution = await _execute(runtime, command, timeout=1800)
    except Exception as exc:
        result["raw"] = f"runtime execution failed: {exc}"
        return result

    output_text = await _read_output(runtime, output_path)
    stdout = _normalize_text(getattr(execution, "stdout", "") or "")
    stderr = _normalize_text(getattr(execution, "stderr", "") or "")
    raw = "\n".join(part for part in (output_text, stdout, stderr) if part).strip()

    if _looks_missing(execution, extra_text=output_text):
        result["raw"] = raw
        return result

    parsed = _parse_fscan_output(str(target).strip(), output_text or stdout or stderr)
    parsed["raw"] = raw
    return parsed


@register_tool(
    name="fscan",
    description="Run fscan and return structured hosts, services, and vulnerability results.",
    schema=ToolSchema(
        properties={
            "target": {
                "type": "string",
                "description": "Target host, IP, or CIDR for fscan",
            },
            "ports": {
                "type": "string",
                "description": "Optional port selection, e.g. top100 or 80,443,3389",
                "default": "top100",
            },
        },
        required=["target"],
    ),
    category="network",
)
async def fscan(arguments: dict, runtime: "Runtime") -> str:
    result = await run_fscan(
        target=arguments.get("target", ""),
        ports=arguments.get("ports", "top100"),
        runtime=runtime,
    )
    return json.dumps(result, ensure_ascii=False)


__all__ = ["run_fscan", "fscan"]
