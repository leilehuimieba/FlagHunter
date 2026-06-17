"""Unit tests for radare2 CTF tool."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from flaghunter.tools.radare2 import radare2


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
async def test_radare2_analysis_success():
    runtime = _MockRuntime(responses=[
        "",  # mkdir
        json.dumps({
            "success": True,
            "binary": "/tmp/crackme",
            "results": [
                {"command": "afl", "type": "text", "output": "0x00001159    6    135 main\n"},
                {"command": "iz", "type": "text", "output": "0x0000201e CTF{angr_ok}\n"},
            ],
        }),
        "",  # rm -rf
    ])

    result = await radare2({
        "binary_path": "/tmp/crackme",
        "commands": ["afl", "iz"],
    }, runtime=runtime)

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["binary"] == "/tmp/crackme"
    assert len(parsed["results"]) == 2
    assert parsed["results"][0]["command"] == "afl"


@pytest.mark.asyncio
async def test_radare2_binary_not_found():
    runtime = _MockRuntime(responses=[
        "",
        json.dumps({"success": False, "error": "Binary not found: /tmp/missing"}),
        "",
    ])

    result = await radare2({
        "binary_path": "/tmp/missing",
        "commands": ["afl"],
    }, runtime=runtime)

    parsed = json.loads(result)
    assert parsed["success"] is False
    assert "Binary not found" in parsed["error"]


@pytest.mark.asyncio
async def test_radare2_json_commands_parsed():
    runtime = _MockRuntime(responses=[
        "",
        json.dumps({
            "success": True,
            "binary": "/tmp/crackme",
            "results": [
                {"command": "aflj", "type": "json", "data": [{"name": "main", "offset": 4441}]},
            ],
        }),
        "",
    ])

    result = await radare2({
        "binary_path": "/tmp/crackme",
        "commands": ["aflj"],
    }, runtime=runtime)

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["results"][0]["type"] == "json"
    assert parsed["results"][0]["data"][0]["name"] == "main"
