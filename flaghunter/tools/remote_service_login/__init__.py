"""
remote_service_login — 用已知/候选凭据访问外部远程服务(SSH),确认获得访问。

这是 ATT&CK **T1133 External Remote Services** 的覆盖能力:面向授权目标,
利用对外暴露的远程服务(首先是 SSH)以凭据完成认证并确认可执行命令,
从而把"侦察拿到的凭据"转化为初始访问。

设计约束:
- **不是暴力破解器**(非 T1110)。接受单个已知凭据或**少量**候选凭据,
  框定为"用凭据访问远程服务";调用方对授权目标负责。
- **无新依赖**:复用 system `ssh` 客户端 + SSH_ASKPASS 喂密码的子进程模式
  (与 flaghunter/runtime/ssh_runtime.py 一致),不引 paramiko。
- 通过 asyncio.to_thread 跑子进程,不阻塞事件循环。
- 凭据不回显明文:报告只暴露用户名与认证方式,密码以占位标签呈现。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


def _build_ssh_command(
    host: str,
    port: int,
    username: str,
    command: str,
    *,
    key_path: str | None,
    batch_mode: bool,
    connect_timeout: int,
) -> list[str]:
    ssh_command = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=" + os.devnull,
        "-o", f"ConnectTimeout={connect_timeout}",
        "-o", "NumberOfPasswordPrompts=1",
    ]
    if batch_mode:
        ssh_command += ["-o", "BatchMode=yes"]
    else:
        ssh_command += ["-o", "PreferredAuthentications=password,keyboard-interactive",
                        "-o", "PubkeyAuthentication=no"]
    if port:
        ssh_command += ["-p", str(port)]
    if key_path:
        ssh_command += ["-i", key_path]
    ssh_command.append(f"{username}@{host}")
    ssh_command.append(command)
    return ssh_command


def _run_ssh(ssh_command: list[str], *, password: str | None, timeout: int) -> dict[str, Any]:
    """Run the ssh subprocess. Module-level seam for monkeypatching in tests.

    Returns {"returncode": int, "stdout": str, "stderr": str}. A returncode of
    255 is ssh's own connect/auth failure; 0 means auth succeeded and the remote
    command ran. -1 indicates a local failure (no ssh client / timeout).
    """
    if not shutil.which(ssh_command[0]):
        return {"returncode": -1, "stdout": "", "stderr": "ssh client not found on PATH"}

    def _decode(b: bytes | None) -> str:
        if not b:
            return ""
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            return b.decode("utf-8", errors="replace")

    try:
        if password is not None:
            with tempfile.TemporaryDirectory(prefix="flaghunter-rsl-") as temp_dir:
                temp_path = Path(temp_dir)
                (temp_path / "password.txt").write_text(password, encoding="utf-8")
                if os.name == "nt":
                    askpass = temp_path / "askpass.cmd"
                    askpass.write_text('@echo off\r\nset /p =<"%~dp0password.txt"\r\n', encoding="utf-8")
                else:
                    askpass = temp_path / "askpass.sh"
                    askpass.write_text('#!/bin/sh\ncat "$(dirname "$0")/password.txt"\n', encoding="utf-8")
                    askpass.chmod(0o700)
                env = os.environ.copy()
                env["SSH_ASKPASS"] = str(askpass)
                env["SSH_ASKPASS_REQUIRE"] = "force"
                env.setdefault("DISPLAY", "flaghunter-ssh:0")
                completed = subprocess.run(
                    ssh_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    stdin=subprocess.DEVNULL, timeout=timeout, env=env,
                )
        else:
            completed = subprocess.run(
                ssh_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL, timeout=timeout,
            )
        return {
            "returncode": completed.returncode,
            "stdout": _decode(completed.stdout),
            "stderr": _decode(completed.stderr),
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": f"timed out after {timeout}s"}
    except Exception as exc:  # noqa: BLE001 — report honestly
        return {"returncode": -1, "stdout": "", "stderr": f"execution error: {exc}"}


def _candidates(password: str | None, candidate_passwords: list[str] | None, key_path: str | None):
    """Yield (label, password_or_None, key_path_or_None, batch_mode) credential attempts."""
    if key_path:
        yield ("key", None, key_path, True)
    if password is not None:
        yield ("password", password, None, False)
    for i, pw in enumerate(candidate_passwords or []):
        yield (f"candidate#{i + 1}", pw, None, False)


async def _login(
    host: str,
    port: int,
    username: str,
    password: str | None,
    candidate_passwords: list[str] | None,
    key_path: str | None,
    command: str,
    timeout: int,
    connect_timeout: int,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    creds = list(_candidates(password, candidate_passwords, key_path))
    if not creds:
        return {
            "host": host, "port": port, "username": username,
            "authenticated": False, "reason": "no credentials supplied (need password, candidate_passwords or key_path)",
            "attempts": attempts,
        }

    for label, pw, key, batch_mode in creds:
        ssh_command = _build_ssh_command(
            host, port, username, command,
            key_path=key, batch_mode=batch_mode, connect_timeout=connect_timeout,
        )
        result = await asyncio.to_thread(_run_ssh, ssh_command, password=pw, timeout=timeout)
        rc = result.get("returncode")
        attempts.append({"credential": label, "method": "key" if batch_mode else "password", "returncode": rc})
        if rc == 0:
            return {
                "host": host, "port": port, "username": username,
                "authenticated": True,
                "method": "key" if batch_mode else "password",
                "which_credential": label,
                "command": command,
                "command_output": (result.get("stdout") or "").strip(),
                "attempts": attempts,
            }

    return {
        "host": host, "port": port, "username": username,
        "authenticated": False,
        "reason": "all credentials rejected or service unreachable",
        "attempts": attempts,
    }


@register_tool(
    name="remote_service_login",
    description=(
        "Access an external remote service (SSH) with known/candidate credentials and "
        "confirm access by running a command. Covers ATT&CK T1133 (External Remote "
        "Services) — turns recovered credentials into initial access. Not a brute-forcer: "
        "supply a known credential or a small candidate set for an authorised target."
    ),
    schema=ToolSchema(
        properties={
            "host": {"type": "string", "description": "Target host/IP exposing the remote service"},
            "port": {"type": "integer", "description": "Service port", "default": 22},
            "username": {"type": "string", "description": "Login username"},
            "password": {"type": "string", "description": "Known password (optional)"},
            "candidate_passwords": {"type": "array", "description": "Small list of candidate passwords (optional)"},
            "key_path": {"type": "string", "description": "Path to a private key for key-based auth (optional)"},
            "command": {"type": "string", "description": "Command to confirm access", "default": "id"},
            "timeout": {"type": "integer", "description": "Per-attempt timeout (s)", "default": 15},
        },
        required=["host", "username"],
    ),
    category="exploitation",
    technique_ids=["T1133"],
)
async def remote_service_login(arguments: dict, runtime: "Runtime") -> str:
    host = arguments.get("host")
    username = arguments.get("username")
    if not host:
        return "Error: host is required"
    if not username:
        return "Error: username is required"
    port = int(arguments.get("port", 22))
    password = arguments.get("password")
    candidate_passwords = arguments.get("candidate_passwords")
    if candidate_passwords is not None:
        candidate_passwords = [str(p) for p in candidate_passwords]
    key_path = arguments.get("key_path")
    command = arguments.get("command") or "id"
    timeout = int(arguments.get("timeout", 15))
    connect_timeout = min(timeout, 10)

    try:
        result = await _login(
            host, port, username, password, candidate_passwords, key_path,
            command, timeout, connect_timeout,
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"host": host, "authenticated": False, "error": str(exc)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)
