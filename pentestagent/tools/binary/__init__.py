"""Structured binary analysis tool for CTF reverse/pwn workflows."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from .._tool_env import find_tool, patch_tool_path
from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime

patch_tool_path()

_FLAG_PATTERN = re.compile(
    r"flag\{[^}]+\}|CTF\{[^}]+\}|ctf\{[^}]+\}",
    re.IGNORECASE,
)

_KEY_FUNC_NAMES = {
    "main",
    "win",
    "flag",
    "shell",
    "backdoor",
    "get_shell",
    "system",
    "execve",
    "gets",
    "strcpy",
    "sprintf",
    "scanf",
    "read",
    "puts",
    "printf",
    "malloc",
    "free",
}

_MAX_KEY_STRINGS = 100
_MAX_ALL_FUNCTIONS = 200
_MAX_MAIN_ASM_LINES = 200


def _default_result(binary_path: str) -> dict:
    return {
        "path": binary_path,
        "file_type": "",
        "arch": "",
        "bits": 0,
        "endian": "",
        "protections": {
            "nx": False,
            "pie": False,
            "canary": False,
            "relro": "No",
            "fortify": False,
        },
        "key_strings": [],
        "flags_found": [],
        "key_functions": [],
        "all_functions": [],
        "main_asm": "",
        "suggestions": [],
        "error": "",
    }


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


def _shell_quote(value: str, windows: bool = False) -> str:
    if windows:
        return '"' + str(value).replace('"', '\\"') + '"'
    return shlex.quote(str(value))


def _truncate_lines(text: str, max_lines: int = _MAX_MAIN_ASM_LINES) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[:max_lines])


def _append_error(errors: list[str], message: str) -> None:
    message = (message or "").strip()
    if message and message not in errors:
        errors.append(message)


async def _run_local_shell(command: str, timeout: int = 60) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["TERM"] = "dumb"
    env["NO_COLOR"] = "1"

    process = None
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        return (
            process.returncode or 0,
            _normalize_text(stdout),
            _normalize_text(stderr),
        )
    except asyncio.TimeoutError:
        if process is not None:
            process.kill()
            await process.communicate()
        return -1, "", f"Command timed out after {timeout} seconds"
    except Exception as exc:
        return -1, "", str(exc)


def _is_ssh_runtime(runtime) -> bool:
    return runtime is not None and type(runtime).__name__ == "SSHRuntime"


def _is_local_runtime(runtime) -> bool:
    return runtime is not None and type(runtime).__name__ == "LocalRuntime"


async def _execute_tool_command(
    *,
    runtime,
    tool_name: str,
    arguments: str,
    timeout: int,
) -> tuple[int, str, str]:
    is_ssh = _is_ssh_runtime(runtime)
    is_windows_local = os.name == "nt" and not is_ssh
    executable = tool_name if is_ssh else (find_tool(tool_name) or tool_name)
    command = f"{_shell_quote(executable, windows=is_windows_local)} {arguments}".strip()

    if runtime is not None:
        try:
            result = await runtime.execute_command(command, timeout=timeout)
            return (
                int(getattr(result, "exit_code", -1)),
                _normalize_text(getattr(result, "stdout", "")),
                _normalize_text(getattr(result, "stderr", "")),
            )
        except Exception as exc:
            return -1, "", str(exc)

    return await _run_local_shell(command, timeout=timeout)


def _looks_missing(exit_code: int, stdout: str, stderr: str) -> bool:
    combined = f"{stdout}\n{stderr}".lower()
    markers = (
        "not found",
        "is not recognized",
        "cannot find",
        "no such file",
        "could not find",
    )
    return exit_code != 0 and any(marker in combined for marker in markers)


def _parse_file_output(stdout: str) -> tuple[str, str, int, str]:
    if not stdout.strip():
        return "", "", 0, ""

    line = stdout.strip().splitlines()[0]
    file_type = line.split(":", 1)[1].strip() if ":" in line else line.strip()
    lowered = file_type.lower()

    bits = 0
    bit_match = re.search(r"\b(32|64)-bit\b", file_type, re.IGNORECASE)
    if bit_match:
        bits = int(bit_match.group(1))
    elif "pe32+" in lowered:
        bits = 64
    elif "pe32" in lowered:
        bits = 32

    endian = ""
    if "lsb" in lowered or "little endian" in lowered:
        endian = "little"
    elif "msb" in lowered or "big endian" in lowered:
        endian = "big"

    arch = ""
    if any(token in lowered for token in ("x86-64", "x86_64", "amd64")):
        arch = "x86_64"
    elif any(token in lowered for token in ("80386", "i386", "intel 80386", "x86")):
        arch = "x86"
    elif "aarch64" in lowered or "arm64" in lowered:
        arch = "arm64"
    elif "arm" in lowered:
        arch = "arm"
    elif "mips64" in lowered:
        arch = "mips64"
    elif "mips" in lowered:
        arch = "mips"
    elif "powerpc" in lowered or "ppc" in lowered:
        arch = "powerpc"
    elif "risc-v" in lowered or "riscv" in lowered:
        arch = "riscv"
    elif "mach-o 64-bit arm64" in lowered:
        arch = "arm64"

    return file_type, arch, bits, endian


def _parse_checksec_json(stdout: str) -> dict:
    parsed = json.loads(stdout)
    if isinstance(parsed, list):
        entry = parsed[0] if parsed else {}
    elif isinstance(parsed, dict):
        if len(parsed) == 1 and isinstance(next(iter(parsed.values())), dict):
            entry = next(iter(parsed.values()))
        else:
            entry = parsed
    else:
        entry = {}

    def _as_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        return text in {"true", "yes", "enabled", "found", "on"}

    relro_value = (
        entry.get("relro")
        or entry.get("RELRO")
        or entry.get("Relro")
        or entry.get("relro_status")
        or "No"
    )
    relro_text = str(relro_value).strip()
    lowered_relro = relro_text.lower()
    if "full" in lowered_relro:
        relro = "Full"
    elif "partial" in lowered_relro:
        relro = "Partial"
    else:
        relro = "No"

    return {
        "nx": _as_bool(entry.get("nx") or entry.get("NX")),
        "pie": _as_bool(entry.get("pie") or entry.get("PIE")),
        "canary": _as_bool(entry.get("canary") or entry.get("Canary")),
        "relro": relro,
        "fortify": _as_bool(entry.get("fortify") or entry.get("FORTIFY")),
    }


def _merge_protections(current: dict, update: dict) -> dict:
    merged = dict(current)
    for key in ("nx", "pie", "canary", "fortify"):
        if key in update:
            merged[key] = bool(update[key])
    if update.get("relro") in {"No", "Partial", "Full"}:
        merged["relro"] = update["relro"]
    return merged


def _parse_readelf_protections(stdout: str) -> dict:
    lowered = stdout.lower()
    relro = "No"
    if "bind_now" in lowered:
        relro = "Full"
    elif "relro" in lowered or "gnu_relro" in lowered:
        relro = "Partial"

    fortify = "__chk" in lowered or "_chk@" in lowered

    return {
        "nx": False,
        "pie": False,
        "canary": "__stack_chk_fail" in lowered,
        "relro": relro,
        "fortify": fortify,
    }


def _normalize_function_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.strip("<>")
    cleaned = cleaned.split("@", 1)[0]
    cleaned = cleaned.split("+", 1)[0]
    cleaned = cleaned.strip()
    if cleaned.startswith("_") and cleaned[1:] in _KEY_FUNC_NAMES:
        return cleaned[1:]
    return cleaned


def _parse_function_lines(text: str) -> list[str]:
    functions: list[str] = []
    seen: set[str] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        nm_match = re.match(r"^[0-9A-Fa-f]+\s+([A-Za-z])\s+(.+)$", line)
        if nm_match:
            sym_type = nm_match.group(1)
            if sym_type.lower() in {"t", "w"}:
                candidate = _normalize_function_name(nm_match.group(2))
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    functions.append(candidate)
            continue

        if "FUNC" in line:
            parts = line.split()
            candidate = _normalize_function_name(parts[-1]) if parts else ""
            if candidate and candidate != "UND" and candidate not in seen:
                seen.add(candidate)
                functions.append(candidate)

    return functions


def _extract_key_functions(functions: list[str]) -> list[str]:
    key_functions: list[str] = []
    seen: set[str] = set()
    for func in functions:
        normalized = _normalize_function_name(func)
        lowered = normalized.lower()
        if lowered in _KEY_FUNC_NAMES and normalized not in seen:
            seen.add(normalized)
            key_functions.append(normalized)
    return key_functions


def _generate_suggestions(
    *,
    protections: dict,
    key_functions: list[str],
    key_strings: list[str],
    flags_found: list[str],
) -> list[str]:
    suggestions: list[str] = []
    key_function_set = {str(name).lower() for name in key_functions}
    key_string_set = set(key_strings)

    if not protections.get("canary", False) and "gets" in key_function_set:
        suggestions.append(
            "Buffer overflow likely: no stack canary, 'gets' detected"
        )
    if not protections.get("pie", False):
        suggestions.append("Fixed base address: ROP/ret2libc feasible")
    if not protections.get("nx", False):
        suggestions.append("NX disabled: shellcode execution possible")
    if "system" in key_function_set and "/bin/sh" in key_string_set:
        suggestions.append("ret2system: system() + '/bin/sh' string present")
    if flags_found:
        suggestions.append(f"FLAG FOUND IN BINARY: {flags_found}")
    if protections.get("relro") == "No":
        suggestions.append("GOT overwrite attack possible (No RELRO)")

    return suggestions


async def analyze_binary(
    binary_path: str,
    runtime=None,
    timeout: int = 60,
) -> dict:
    """
    多级静态分析二进制文件并返回结构化结果。
    """
    result = _default_result(binary_path)
    errors: list[str] = []

    try:
        timeout = max(1, int(timeout))
    except (TypeError, ValueError):
        timeout = 60

    is_ssh = _is_ssh_runtime(runtime)
    is_local = runtime is None or _is_local_runtime(runtime)

    if is_local:
        try:
            candidate = Path(binary_path)
            if not candidate.exists():
                result["error"] = f"binary not found: {binary_path}"
                return result
        except OSError as exc:
            result["error"] = str(exc)
            return result

    shell_windows = os.name == "nt" and not is_ssh
    quoted_path = _shell_quote(binary_path, windows=shell_windows)

    # Step 1 - file
    file_exit, file_stdout, file_stderr = await _execute_tool_command(
        runtime=runtime,
        tool_name="file",
        arguments=quoted_path,
        timeout=timeout,
    )
    if file_exit == 0 and file_stdout.strip():
        file_type, arch, bits, endian = _parse_file_output(file_stdout)
        result["file_type"] = file_type
        result["arch"] = arch
        result["bits"] = bits
        result["endian"] = endian
    else:
        message = file_stderr or file_stdout or "file command failed"
        if _looks_missing(file_exit, file_stdout, file_stderr):
            message = f"file tool unavailable: {message}"
        _append_error(errors, message)

    # Step 2 - strings
    strings_exit, strings_stdout, strings_stderr = await _execute_tool_command(
        runtime=runtime,
        tool_name="strings",
        arguments=f"-n 6 {quoted_path}",
        timeout=timeout,
    )
    if strings_exit == 0 and strings_stdout:
        lines = [line.strip() for line in strings_stdout.splitlines() if line.strip()]
        result["key_strings"] = lines[:_MAX_KEY_STRINGS]
        result["flags_found"] = [
            line for line in lines if _FLAG_PATTERN.search(line)
        ]
    else:
        message = strings_stderr or strings_stdout or "strings command failed"
        if _looks_missing(strings_exit, strings_stdout, strings_stderr):
            message = f"strings tool unavailable: {message}"
        _append_error(errors, message)

    # Step 3 - checksec (fallback to readelf)
    checksec_exit, checksec_stdout, checksec_stderr = await _execute_tool_command(
        runtime=runtime,
        tool_name="checksec",
        arguments=f"--file={quoted_path} --output=json",
        timeout=timeout,
    )
    if checksec_exit == 0 and checksec_stdout.strip():
        try:
            result["protections"] = _merge_protections(
                result["protections"],
                _parse_checksec_json(checksec_stdout),
            )
        except Exception as exc:
            _append_error(errors, f"checksec parse failed: {exc}")
    else:
        if not _looks_missing(checksec_exit, checksec_stdout, checksec_stderr):
            _append_error(
                errors,
                checksec_stderr or checksec_stdout or "checksec command failed",
            )

        readelf_exit, readelf_stdout, readelf_stderr = await _execute_tool_command(
            runtime=runtime,
            tool_name="readelf",
            arguments=f"-d {quoted_path}",
            timeout=timeout,
        )
        if readelf_exit == 0 and readelf_stdout.strip():
            result["protections"] = _merge_protections(
                result["protections"],
                _parse_readelf_protections(readelf_stdout),
            )
        else:
            message = readelf_stderr or readelf_stdout or "readelf command failed"
            if _looks_missing(readelf_exit, readelf_stdout, readelf_stderr):
                message = f"readelf tool unavailable: {message}"
            _append_error(errors, message)

    # Step 4 - nm or readelf -s
    symbols_exit, symbols_stdout, symbols_stderr = await _execute_tool_command(
        runtime=runtime,
        tool_name="nm",
        arguments=f"-n {quoted_path}",
        timeout=timeout,
    )
    if symbols_exit != 0 or not symbols_stdout.strip():
        readelf_sym_exit, readelf_sym_stdout, readelf_sym_stderr = (
            await _execute_tool_command(
                runtime=runtime,
                tool_name="readelf",
                arguments=f"-s {quoted_path}",
                timeout=timeout,
            )
        )
        symbols_exit, symbols_stdout, symbols_stderr = (
            readelf_sym_exit,
            readelf_sym_stdout,
            readelf_sym_stderr,
        )

    if symbols_exit == 0 and symbols_stdout.strip():
        functions = _parse_function_lines(symbols_stdout)
        result["all_functions"] = functions[:_MAX_ALL_FUNCTIONS]
        result["key_functions"] = _extract_key_functions(functions)
    else:
        message = symbols_stderr or symbols_stdout or "symbol extraction failed"
        _append_error(errors, message)

    # Step 5 - r2 or objdump
    r2_exit, r2_stdout, r2_stderr = await _execute_tool_command(
        runtime=runtime,
        tool_name="r2",
        arguments=f"-q -c \"aaa; s main; pdf\" {quoted_path}",
        timeout=timeout,
    )
    if r2_exit == 0 and r2_stdout.strip():
        result["main_asm"] = _truncate_lines(r2_stdout, _MAX_MAIN_ASM_LINES)
    else:
        objdump_exit, objdump_stdout, objdump_stderr = await _execute_tool_command(
            runtime=runtime,
            tool_name="objdump",
            arguments=f"-d -M intel {quoted_path}",
            timeout=timeout,
        )
        if objdump_exit == 0 and objdump_stdout.strip():
            match = re.search(
                r"<main>:\n(?P<body>(?:.*\n){0,200})",
                objdump_stdout,
                re.MULTILINE,
            )
            main_asm = match.group(0).strip() if match else ""
            result["main_asm"] = _truncate_lines(main_asm, _MAX_MAIN_ASM_LINES)
        else:
            message = objdump_stderr or objdump_stdout or r2_stderr or "disassembly failed"
            _append_error(errors, message)

    # Step 6 - suggestions
    result["suggestions"] = _generate_suggestions(
        protections=result["protections"],
        key_functions=result["key_functions"],
        key_strings=result["key_strings"],
        flags_found=result["flags_found"],
    )

    result["error"] = "; ".join(errors)
    return result


@register_tool(
    name="binary",
    description=(
        "Analyze a binary file (ELF/PE/Mach-O) for CTF reverse/pwn challenges. "
        "Returns architecture, protections (NX/PIE/canary/RELRO), key strings, "
        "key functions, main() disassembly, and actionable CTF suggestions."
    ),
    schema=ToolSchema(
        properties={
            "binary_path": {
                "type": "string",
                "description": "Path to binary file. On SSHRuntime, this is the remote Kali path.",
            },
            "timeout": {
                "type": "integer",
                "description": "Analysis timeout in seconds (default: 60)",
                "default": 60,
            },
        },
        required=["binary_path"],
    ),
    category="ctf",
)
async def binary(arguments: dict, runtime: "Runtime") -> str:
    result = await analyze_binary(
        binary_path=arguments["binary_path"],
        runtime=runtime,
        timeout=arguments.get("timeout", 60),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)
