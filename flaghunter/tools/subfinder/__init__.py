"""Structured subfinder wrapper for FlagHunter."""

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


def _result(domain: str, raw: str = "") -> dict[str, Any]:
    return {
        "domain": domain,
        "subdomains": [],
        "total": 0,
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


def _parse_subdomains(raw_text: str) -> list[str]:
    subdomains: list[str] = []
    seen: set[str] = set()
    for line in raw_text.splitlines():
        candidate = line.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        subdomains.append(candidate)
    return subdomains


async def run_subfinder(domain: str, runtime=None) -> dict:
    """Run subfinder and return structured subdomain results."""
    tool_path = find_tool("subfinder")
    result = _result(domain=domain)

    if not str(domain).strip():
        result["error"] = "domain is required"
        return result

    if runtime is None and not tool_path:
        result["error"] = "subfinder not installed"
        return result

    output_path = _resolve_output_path(runtime, "subfinder_out.txt")
    await _cleanup_output(runtime, output_path)

    command = (
        f"subfinder -d {_quote(str(domain).strip())} "
        f"-silent -o {_quote(output_path)}"
    )

    try:
        execution = await _execute(runtime, command, timeout=900)
    except Exception as exc:
        result["raw"] = f"runtime execution failed: {exc}"
        return result

    output_text = await _read_output(runtime, output_path)
    stdout = _normalize_text(getattr(execution, "stdout", "") or "")
    stderr = _normalize_text(getattr(execution, "stderr", "") or "")
    raw = "\n".join(part for part in (output_text, stdout, stderr) if part).strip()

    if _looks_missing(execution, extra_text=output_text):
        result["raw"] = raw
        result["error"] = "subfinder not installed"
        return result

    subdomains = _parse_subdomains(output_text or stdout)
    payload = {
        "domain": str(domain).strip(),
        "subdomains": subdomains,
        "total": len(subdomains),
        "raw": raw,
    }

    if getattr(execution, "exit_code", 0) != 0 and not subdomains:
        payload["error"] = stderr or stdout or "subfinder execution failed"

    return payload


@register_tool(
    name="subfinder",
    description="Run subfinder and return structured subdomain enumeration results.",
    schema=ToolSchema(
        properties={
            "domain": {
                "type": "string",
                "description": "Root domain to enumerate, e.g. example.com",
            },
        },
        required=["domain"],
    ),
    category="recon",
)
async def subfinder(arguments: dict, runtime: "Runtime") -> str:
    result = await run_subfinder(
        domain=arguments.get("domain", ""),
        runtime=runtime,
    )
    return json.dumps(result, ensure_ascii=False)


__all__ = ["run_subfinder", "subfinder"]
