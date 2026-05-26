"""Unit tests for crypto_solve CTF tool."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from pentestagent.tools.crypto_solve import crypto_solve


class _MockResult:
    def __init__(self, stdout: str = "", stderr: str = ""):
        self.stdout = stdout
        self.stderr = stderr


class _MockRuntime:
    """Mock runtime that skips the base64-fallback path by exposing copy_to_container."""

    def __init__(self, responses: list[str] | None = None):
        self._responses = responses or []
        self._call_idx = 0
        self.commands = []

    async def execute_command(self, cmd: str, timeout: int = 60):
        self.commands.append(cmd)
        stdout = self._responses[self._call_idx] if self._call_idx < len(self._responses) else ""
        self._call_idx += 1
        return _MockResult(stdout=stdout)

    async def copy_to_container(self, local_path, remote_path):
        pass


@pytest.mark.asyncio
async def test_crypto_solve_rsa_small_e():
    runtime = _MockRuntime(responses=[
        "",  # mkdir
        json.dumps({"success": True, "plaintext_int": 42, "plaintext_hex": "0x2a", "plaintext_bytes": "2a"}),
        "",  # rm -rf
    ])

    result = await crypto_solve({
        "task": "rsa_small_e",
        "params": {"c": 74088, "e": 3, "n": 1022117},
    }, runtime=runtime)

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["plaintext_int"] == 42


@pytest.mark.asyncio
async def test_crypto_solve_base64_decode():
    runtime = _MockRuntime(responses=[
        "",
        json.dumps({"success": True, "decoded": "flag{test}"}),
        "",
    ])

    result = await crypto_solve({
        "task": "base64_decode",
        "params": {"data": "ZmxhZ3t0ZXN0fQ=="},
    }, runtime=runtime)

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["decoded"] == "flag{test}"


@pytest.mark.asyncio
async def test_crypto_solve_unknown_task():
    runtime = _MockRuntime(responses=[
        "",
        json.dumps({"success": False, "error": "Unknown task: xyz"}),
        "",
    ])

    result = await crypto_solve({
        "task": "xyz",
        "params": {},
    }, runtime=runtime)

    parsed = json.loads(result)
    assert parsed["success"] is False
    assert "Unknown task" in parsed["error"]


@pytest.mark.asyncio
async def test_crypto_solve_no_json_output():
    runtime = _MockRuntime(responses=[
        "",
        "some garbage output without json",
        "",
    ])

    result = await crypto_solve({
        "task": "base64_decode",
        "params": {"data": "abc"},
    }, runtime=runtime)

    parsed = json.loads(result)
    assert parsed["success"] is False
    assert "No JSON output" in parsed["error"]
