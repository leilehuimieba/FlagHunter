"""Structured afrog wrapper for FlagHunter."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .._tool_env import find_tool, patch_tool_path
from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime

patch_tool_path()


DEFAULT_SEVERITY = ["critical", "high", "medium"]
_MISSING_MARKERS = (
    "not found",
    "is not recognized",
    "command not found",
    "no such file",
    "cannot find",
    "could not find",
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
        "findings": [],
        "total": 0,
        "raw": raw,
    }


def _local_output_path(filename: str) -> str:
    return str(Path(tempfile.gettempdir()) / filename)


def _resolve_output_path(runtime: "Runtime | None", filename: str) -> str:
    if runtime is None or runtime.__class__.__name__ == "LocalRuntime":
        if os.name == "nt":
            return _local_output_path(filename)
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


def _normalize_severity(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for value in values or []:
        text = str(value).strip().lower()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _parse_afrog_jsonl(raw_text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line in raw_text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue

        try:
            record = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if not isinstance(record, dict):
            continue

        info = record.get("info") if isinstance(record.get("info"), dict) else {}
        vuln_id = (
            record.get("vuln_id")
            or record.get("vul_id")
            or record.get("id")
            or record.get("plugin")
            or record.get("template_id")
            or record.get("rule")
            or ""
        )
        name = (
            record.get("name")
            or info.get("name")
            or record.get("title")
            or record.get("plugin")
            or vuln_id
            or ""
        )
        severity = (
            record.get("severity")
            or info.get("severity")
            or record.get("level")
            or ""
        )
        url = (
            record.get("url")
            or record.get("target")
            or record.get("matched-at")
            or record.get("matched_at")
            or record.get("host")
            or ""
        )
        matched = (
            record.get("matched")
            or record.get("matched-at")
            or record.get("matched_at")
            or record.get("match")
            or record.get("evidence")
            or record.get("detail")
            or record.get("request")
            or url
            or ""
        )

        findings.append(
            {
                "vuln_id": str(vuln_id),
                "name": str(name),
                "severity": str(severity),
                "url": str(url),
                "matched": str(matched),
            }
        )

    return findings


async def run_afrog(
    target: str,
    severity: list[str] = ["critical", "high", "medium"],
    runtime=None,
) -> dict:
    """Run afrog and return structured JSON-style findings."""
    tool_path = find_tool("afrog")
    severity_list = _normalize_severity(severity) or list(DEFAULT_SEVERITY)
    result = _result(target=target)

    if not str(target).strip():
        result["error"] = "target is required"
        return result

    if runtime is None and not tool_path:
        result["error"] = "afrog not installed"
        return result

    output_path = _resolve_output_path(runtime, "afrog_out.json")
    await _cleanup_output(runtime, output_path)

    command = (
        f"afrog -t {_quote(str(target).strip())} "
        f"-s {_quote(','.join(severity_list))} "
        f"-json {_quote(output_path)}"
    )

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
        result["error"] = "afrog not installed"
        return result

    findings = _parse_afrog_jsonl(output_text or stdout)
    payload = {
        "target": str(target).strip(),
        "findings": findings,
        "total": len(findings),
        "raw": raw,
    }

    if getattr(execution, "exit_code", 0) != 0 and not findings:
        payload["error"] = stderr or stdout or "afrog execution failed"

    return payload


@register_tool(
    name="afrog",
    description="Run afrog vulnerability scans and return structured JSON findings.",
    schema=ToolSchema(
        properties={
            "target": {
                "type": "string",
                "description": "Target URL or host for afrog scanning",
            },
            "severity": {
                "type": "array",
                "description": "Severity filters, default critical/high/medium",
                "items": {"type": "string"},
            },
        },
        required=["target"],
    ),
    category="web_scan",
)
async def afrog(arguments: dict, runtime: "Runtime") -> str:
    result = await run_afrog(
        target=arguments.get("target", ""),
        severity=arguments.get("severity", []) or list(DEFAULT_SEVERITY),
        runtime=runtime,
    )
    return json.dumps(result, ensure_ascii=False)


__all__ = ["run_afrog", "afrog"]
