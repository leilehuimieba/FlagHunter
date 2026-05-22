"""Structured nuclei wrapper tool for PentestAgent."""

import json
from typing import TYPE_CHECKING, Any

from .._tool_env import patch_tool_path, find_tool
from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime

patch_tool_path()


DEFAULT_SEVERITY = ["critical", "high", "medium"]


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


def _normalize_string_list(values: list[str] | None) -> list[str]:
    """Normalize list-like input into a compact string list."""
    if not values:
        return []
    normalized: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            normalized.append(text)
    return normalized


async def _execute_runtime_command(runtime: "Runtime", command: str, timeout: int = 900):
    """Execute a command using the runtime's supported API."""
    if runtime is None:
        from ...runtime import LocalRuntime

        runtime = LocalRuntime()

    if hasattr(runtime, "execute_command"):
        return await runtime.execute_command(command, timeout=timeout)

    if hasattr(runtime, "execute"):
        return await runtime.execute(command, timeout=timeout)

    raise RuntimeError("runtime does not support command execution")


async def _nuclei_available(runtime: "Runtime") -> tuple[bool, str]:
    """Check whether nuclei is available in the active runtime."""
    if runtime is None and not find_tool("nuclei"):
        return False, "nuclei not installed"

    probe = await _execute_runtime_command(runtime, "nuclei -version", timeout=15)
    raw = "\n".join(
        part
        for part in [
            _normalize_text(getattr(probe, "stdout", "") or ""),
            _normalize_text(getattr(probe, "stderr", "") or ""),
        ]
        if part
    )

    if getattr(probe, "success", getattr(probe, "exit_code", 0) == 0):
        return True, raw

    lowered = raw.lower()
    missing_markers = [
        "not recognized",
        "not found",
        "command not found",
        "no such file",
        "is not installed",
    ]
    if any(marker in lowered for marker in missing_markers):
        return False, raw

    # Non-zero here may still mean a broken runtime or wrapped binary failure; treat as present
    # and let the main scan path return the concrete error.
    return True, raw


def _parse_nuclei_jsonl(stdout: str) -> list[dict[str, Any]]:
    """Parse nuclei JSONL stdout into structured findings."""
    findings: list[dict[str, Any]] = []

    for line in stdout.splitlines():
        candidate = line.strip()
        if not candidate:
            continue

        try:
            record = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if not isinstance(record, dict):
            continue

        info = record.get("info") or {}
        extracted_results = record.get("extracted-results") or []
        if not isinstance(extracted_results, list):
            extracted_results = [str(extracted_results)]

        matched = (
            record.get("matched-line")
            or (extracted_results[0] if extracted_results else "")
            or record.get("matcher-name")
            or record.get("matched-at")
            or record.get("host")
            or ""
        )

        finding = {
            "template_id": record.get("template-id", ""),
            "name": info.get("name", ""),
            "severity": info.get("severity", ""),
            "url": record.get("matched-at") or record.get("host") or record.get("url") or "",
            "matched": matched,
        }

        extra_fields = {
            "host": record.get("host"),
            "ip": record.get("ip"),
            "template": record.get("template"),
            "template_url": record.get("template-url"),
            "type": record.get("type"),
            "timestamp": record.get("timestamp"),
            "matcher_status": record.get("matcher-status"),
            "extracted_results": extracted_results,
        }
        for key, value in extra_fields.items():
            if value not in (None, "", []):
                finding[key] = value

        findings.append(finding)

    return findings


async def run_nuclei(
    target: str,
    templates: list[str] = [],
    severity: list[str] = ["critical", "high", "medium"],
    tags: list[str] = [],
    headers: dict[str, Any] | None = None,
    runtime=None,
) -> dict:
    """Run nuclei and return structured findings parsed from JSONL output."""
    templates = _normalize_string_list(templates)
    severity = _normalize_string_list(severity) or list(DEFAULT_SEVERITY)
    tags = _normalize_string_list(tags)

    base_result: dict[str, Any] = {
        "target": target,
        "findings": [],
        "total": 0,
        "raw": "",
    }

    if not str(target).strip():
        base_result["error"] = "target is required"
        return base_result

    available, probe_raw = await _nuclei_available(runtime)
    if not available:
        base_result["error"] = "nuclei not installed"
        base_result["raw"] = probe_raw
        return base_result

    cmd_parts = [
        "nuclei",
        "-target",
        _shell_quote(str(target).strip()),
        "-silent",
        "-nc",
        "-duc",
        "-j",
        "-or",
        "-ot",
    ]

    if severity:
        cmd_parts.extend(["-severity", _shell_quote(",".join(severity))])

    if tags:
        cmd_parts.extend(["-tags", _shell_quote(",".join(tags))])

    for template in templates:
        cmd_parts.extend(["-t", _shell_quote(template)])

    normalized_headers = _normalize_headers(headers)
    if normalized_headers:
        for key, value in normalized_headers.items():
            cmd_parts.extend(["-H", _shell_quote(f"{key}: {value}")])

    command = " ".join(cmd_parts)
    result = await _execute_runtime_command(runtime, command, timeout=900)
    stdout = _normalize_text(getattr(result, "stdout", "") or "")
    stderr = _normalize_text(getattr(result, "stderr", "") or "")
    raw = "\n".join(part for part in [stdout, stderr] if part)
    findings = _parse_nuclei_jsonl(stdout)

    payload = {
        "target": str(target).strip(),
        "findings": findings,
        "total": len(findings),
        "raw": raw,
    }

    if not getattr(result, "success", getattr(result, "exit_code", 0) == 0) and not findings:
        lowered = raw.lower()
        if any(marker in lowered for marker in ("not recognized", "not found", "command not found", "no such file")):
            payload["error"] = "nuclei not installed"
        elif raw.strip():
            payload["error"] = raw.strip()
        else:
            payload["error"] = "nuclei execution failed"

    return payload


@register_tool(
    name="nuclei",
    description="Run nuclei vulnerability scans and return structured JSON findings.",
    schema=ToolSchema(
        properties={
            "target": {
                "type": "string",
                "description": "Target URL, host, or CIDR to scan",
            },
            "templates": {
                "type": "array",
                "description": "Optional list of nuclei template paths or directories",
            },
            "severity": {
                "type": "array",
                "description": "Optional severity filter list (default: critical, high, medium)",
            },
            "tags": {
                "type": "array",
                "description": "Optional tag filters to restrict templates",
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers to pass through to nuclei",
            },
        },
        required=["target"],
    ),
    category="web_scan",
)
async def nuclei(arguments: dict, runtime: "Runtime") -> str:
    """Framework wrapper that returns JSON string output."""
    result = await run_nuclei(
        target=arguments.get("target", ""),
        templates=arguments.get("templates", []) or [],
        severity=arguments.get("severity", []) or list(DEFAULT_SEVERITY),
        tags=arguments.get("tags", []) or [],
        headers=arguments.get("headers", {}) or {},
        runtime=runtime,
    )
    return json.dumps(result, ensure_ascii=False)


__all__ = ["run_nuclei", "nuclei"]
