"""Unit tests for angr_solve CTF tool."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from flaghunter.tools.angr_solve import angr_solve


class _MockResult:
    def __init__(self, stdout: str = "", stderr: str = ""):
        self.stdout = stdout
        self.stderr = stderr


class _MockRuntime:
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
async def test_angr_solve_finds_solution():
    runtime = _MockRuntime(responses=[
        "",  # mkdir
        json.dumps({
            "success": True,
            "solution_hex": "4354467b616e67725f6f6b7d",
            "solution_bytes": "CTF{angr_ok}",
            "stdout": "Correct!\n",
            "found_at": "0x401198",
        }),
        "",  # rm -rf
    ])

    result = await angr_solve({
        "binary_path": "/tmp/crackme",
        "find_addrs": ["0x401198"],
        "avoid_addrs": ["0x4011b8"],
        "input_length": 12,
        "stdin_mode": True,
        "arg_mode": False,
    }, runtime=runtime)

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["solution_bytes"] == "CTF{angr_ok}"
    assert parsed["found_at"] == "0x401198"


@pytest.mark.asyncio
async def test_angr_solve_no_path_found():
    runtime = _MockRuntime(responses=[
        "",
        json.dumps({"success": False, "error": "No path found. Deadended: 2", "deadended": 2}),
        "",
    ])

    result = await angr_solve({
        "binary_path": "/tmp/crackme",
        "find_addrs": ["0x999999"],
        "input_length": 12,
    }, runtime=runtime)

    parsed = json.loads(result)
    assert parsed["success"] is False
    assert "No path found" in parsed["error"]


@pytest.mark.asyncio
async def test_angr_solve_no_json_output():
    runtime = _MockRuntime(responses=[
        "",
        "angr loading binary...",
        "",
    ])

    result = await angr_solve({
        "binary_path": "/tmp/crackme",
        "find_addrs": ["0x401198"],
        "input_length": 12,
    }, runtime=runtime)

    parsed = json.loads(result)
    assert parsed["success"] is False
    assert "No JSON output" in parsed["error"]
