"""Pwntools-oriented execution wrapper for CTF workflows."""

import asyncio
import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime

_FLAG_PATTERN = re.compile(r"(flag\{[^}\r\n]+\}|CTF\{[^}\r\n]+\})")
_MAX_OUTPUT_CHARS = 50000


async def run_pwn_script(
    script: str,
    binary_path: str = "",
    host: str = "",
    port: int = 0,
    timeout: int = 30,
) -> dict:
    """
    Execute a Python exploit/helper script and extract common flag formats.

    Returns:
        {
            "success": bool,
            "output": str,
            "flag": str,
            "error": str,
        }
    """
    return await _run_pwn_script_internal(
        script=script,
        binary_path=binary_path,
        host=host,
        port=port,
        timeout=timeout,
        runtime=None,
    )


@register_tool(
    name="pwn",
    description=(
        "Run a Python/pwntools-style script for CTF exploitation and return "
        "structured JSON with success, output, extracted flag, and error."
    ),
    schema=ToolSchema(
        properties={
            "script": {
                "type": "string",
                "description": "Python exploit script source code to execute",
            },
            "binary_path": {
                "type": "string",
                "description": "Optional local binary path for process() style exploits",
            },
            "host": {
                "type": "string",
                "description": "Optional remote host for remote() style exploits",
            },
            "port": {
                "type": "integer",
                "description": "Optional remote port for remote() style exploits",
                "default": 0,
            },
            "timeout": {
                "type": "integer",
                "description": "Execution timeout in seconds (default: 30)",
                "default": 30,
            },
        },
        required=["script"],
    ),
    category="ctf",
)
async def pwn(arguments: dict, runtime: "Runtime") -> str:
    """Registered tool entrypoint that returns JSON text for framework compatibility."""
    result = await _run_pwn_script_internal(
        script=arguments["script"],
        binary_path=arguments.get("binary_path", ""),
        host=arguments.get("host", ""),
        port=arguments.get("port", 0),
        timeout=arguments.get("timeout", 30),
        runtime=runtime,
    )
    return json.dumps(result, ensure_ascii=False)


async def _run_pwn_script_internal(
    script: str,
    binary_path: str = "",
    host: str = "",
    port: int = 0,
    timeout: int = 30,
    runtime: "Runtime | None" = None,
) -> dict:
    script_body = _strip_code_fences(script)
    if not script_body.strip():
        return {
            "success": False,
            "output": "",
            "flag": "",
            "error": "script is empty",
        }

    try:
        timeout = max(1, int(timeout))
    except (TypeError, ValueError):
        timeout = 30

    try:
        port = int(port or 0)
    except (TypeError, ValueError):
        port = 0

    local_binary_path = _normalize_local_binary_path(binary_path)

    with tempfile.TemporaryDirectory(prefix="flaghunter_pwn_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        payload_path = temp_dir / "payload.py"
        launcher_path = temp_dir / "launcher.py"
        payload_path.write_text(script_body, encoding="utf-8")
        launcher_path.write_text(
            _build_launcher(
                payload_name=payload_path.name,
                binary_path=local_binary_path,
                host=host,
                port=port,
            ),
            encoding="utf-8",
        )

        if runtime is not None and hasattr(runtime, "copy_to_container"):
            return await _execute_via_runtime(
                runtime=runtime,
                launcher_path=launcher_path,
                payload_path=payload_path,
                binary_path=local_binary_path,
                host=host,
                port=port,
                timeout=timeout,
            )

        return await _execute_locally(
            launcher_path=launcher_path,
            timeout=timeout,
            binary_path=local_binary_path,
            host=host,
            port=port,
        )


def _build_launcher(payload_name: str, binary_path: str, host: str, port: int) -> str:
    return f'''import pathlib\n\nPAYLOAD_PATH = pathlib.Path(__file__).with_name({payload_name!r})\nglobals_dict = {{\n    "__name__": "__main__",\n    "__file__": str(PAYLOAD_PATH),\n    "BINARY_PATH": {binary_path!r},\n    "HOST": {host!r},\n    "PORT": {port!r},\n}}\ncode = PAYLOAD_PATH.read_text(encoding="utf-8")\nexec(compile(code, str(PAYLOAD_PATH), "exec"), globals_dict, globals_dict)\n'''


def _strip_code_fences(script: str) -> str:
    stripped = script.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)
    return script


def _normalize_local_binary_path(binary_path: str) -> str:
    if not binary_path:
        return ""
    try:
        candidate = Path(binary_path)
        if candidate.exists():
            return str(candidate.resolve())
    except OSError:
        pass
    return binary_path


async def _execute_locally(
    launcher_path: Path,
    timeout: int,
    binary_path: str,
    host: str,
    port: int,
) -> dict:
    env = os.environ.copy()
    env.update(
        {
            "PWNLIB_NOTERM": "1",
            "TERM": "dumb",
            "NO_COLOR": "1",
            "PYTHONUNBUFFERED": "1",
            "PWN_BINARY_PATH": binary_path,
            "PWN_HOST": host,
            "PWN_PORT": str(port),
        }
    )

    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(launcher_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(launcher_path.parent),
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        stdout_text = stdout.decode(errors="replace")
        stderr_text = stderr.decode(errors="replace")
        return _build_result(process.returncode or 0, stdout_text, stderr_text)
    except asyncio.TimeoutError:
        if process is not None:
            process.kill()
            await process.communicate()
        return {
            "success": False,
            "output": "",
            "flag": "",
            "error": f"Execution timed out after {timeout} seconds",
        }
    except Exception as exc:
        return {
            "success": False,
            "output": "",
            "flag": "",
            "error": str(exc),
        }


async def _execute_via_runtime(
    runtime: "Runtime",
    launcher_path: Path,
    payload_path: Path,
    binary_path: str,
    host: str,
    port: int,
    timeout: int,
) -> dict:
    remote_base = f"/tmp/flaghunter_pwn_{uuid4().hex}"
    remote_launcher = f"{remote_base}/{launcher_path.name}"
    remote_payload = f"{remote_base}/{payload_path.name}"
    remote_binary = binary_path

    try:
        await runtime.execute_command(f"mkdir -p {shlex.quote(remote_base)}", timeout=timeout)
        await runtime.copy_to_container(launcher_path, remote_launcher)
        await runtime.copy_to_container(payload_path, remote_payload)

        if binary_path:
            local_binary = Path(binary_path)
            if local_binary.exists():
                remote_binary = f"{remote_base}/{local_binary.name}"
                await runtime.copy_to_container(local_binary, remote_binary)

        command = " && ".join(
            [
                f"cd {shlex.quote(remote_base)}",
                (
                    "env "
                    f"PWNLIB_NOTERM=1 TERM=dumb NO_COLOR=1 PYTHONUNBUFFERED=1 "
                    f"PWN_BINARY_PATH={shlex.quote(remote_binary)} "
                    f"PWN_HOST={shlex.quote(host)} "
                    f"PWN_PORT={shlex.quote(str(port))} "
                    f"(command -v python3 >/dev/null 2>&1 && python3 {shlex.quote(launcher_path.name)} || python {shlex.quote(launcher_path.name)})"
                ),
            ]
        )
        result = await runtime.execute_command(command, timeout=timeout)
        return _build_result(result.exit_code, result.stdout or "", result.stderr or "")
    except Exception as exc:
        return {
            "success": False,
            "output": "",
            "flag": "",
            "error": str(exc),
        }
    finally:
        try:
            await runtime.execute_command(f"rm -rf {shlex.quote(remote_base)}", timeout=10)
        except Exception:
            pass


def _build_result(exit_code: int, stdout: str, stderr: str) -> dict:
    combined_output = _truncate_output(_join_output(stdout, stderr))
    flag = _extract_flag(combined_output)
    error = "" if exit_code == 0 else _truncate_output(stderr.strip() or f"Process exited with code {exit_code}")
    return {
        "success": bool(flag) or exit_code == 0,
        "output": combined_output,
        "flag": flag,
        "error": error,
    }


def _join_output(stdout: str, stderr: str) -> str:
    stdout = stdout or ""
    stderr = stderr or ""
    if stdout and stderr:
        return f"{stdout.rstrip()}\n\n--- stderr ---\n{stderr.rstrip()}"
    return stdout or stderr


def _truncate_output(output: str) -> str:
    if len(output) <= _MAX_OUTPUT_CHARS:
        return output
    clipped = len(output) - _MAX_OUTPUT_CHARS
    half = _MAX_OUTPUT_CHARS // 2
    return output[:half] + f"\n\n... [{clipped} chars truncated] ...\n\n" + output[-half:]


def _extract_flag(output: str) -> str:
    match = _FLAG_PATTERN.search(output or "")
    return match.group(1) if match else ""
