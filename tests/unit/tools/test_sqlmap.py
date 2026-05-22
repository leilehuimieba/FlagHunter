"""Tests for the structured sqlmap wrapper."""

import json

import pytest

from pentestagent.tools.registry import get_tool
from pentestagent.tools.sqlmap import run_sqlmap


class _CommandResult:
    def __init__(self, exit_code: int, stdout: str = "", stderr: str = ""):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class _FakeRuntime:
    def __init__(self, results):
        self._results = list(results)
        self.commands = []

    async def execute_command(self, command: str, timeout: int = 300):
        self.commands.append((command, timeout))
        if not self._results:
            raise AssertionError("No more fake command results configured")
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_run_sqlmap_rejects_excessive_level_and_risk():
    result = await run_sqlmap("http://example.com?id=1", level=4)
    assert result["error"] == "level must be <= 3"

    result = await run_sqlmap("http://example.com?id=1", risk=3)
    assert result["error"] == "risk must be <= 2"


@pytest.mark.asyncio
async def test_run_sqlmap_returns_not_installed_when_probe_fails():
    runtime = _FakeRuntime(
        [
            _CommandResult(
                1,
                stderr="sqlmap : The term 'sqlmap' is not recognized as the name of a cmdlet",
            )
        ]
    )
    result = await run_sqlmap("http://example.com?id=1", runtime=runtime)
    assert result["error"] == "sqlmap not installed"
    assert result["vulnerable"] is False


@pytest.mark.asyncio
async def test_run_sqlmap_parses_injection_points_and_databases():
    scan_output = """
[INFO] testing connection to the target URL
[INFO] GET parameter 'id' is vulnerable. Do you want to keep testing the others (if any)? [y/N]
---
Parameter: id (GET)
    Type: UNION query
    Title: Generic UNION query (NULL) - 3 columns
    Payload: id=1 UNION ALL SELECT NULL,NULL,NULL
---
back-end DBMS: MySQL >= 5.0
available databases [2]:
[*] information_schema
[*] dvwa
"""
    runtime = _FakeRuntime(
        [
            _CommandResult(0, stdout="1.8.5"),
            _CommandResult(0, stdout=scan_output),
        ]
    )
    result = await run_sqlmap("http://example.com?id=1", runtime=runtime)
    assert result["vulnerable"] is True
    assert result["injection_points"][0]["parameter"] == "id"
    assert result["injection_points"][0]["type"] == "UNION query"
    assert "MySQL" in result["injection_points"][0]["dbms"]
    assert "dvwa" in result["databases"]
    assert any("--batch" in command for command, _ in runtime.commands)


@pytest.mark.asyncio
async def test_registered_tool_returns_json_string():
    runtime = _FakeRuntime(
        [
            _CommandResult(0, stdout="1.8.5"),
            _CommandResult(
                0,
                stdout=(
                    "Parameter: id (GET)\n"
                    "Type: boolean-based blind\n"
                    "Payload: id=1 AND 1=1\n"
                ),
            ),
        ]
    )
    tool = get_tool("sqlmap")
    assert tool is not None
    payload = await tool.execute({"url": "http://example.com?id=1"}, runtime)
    parsed = json.loads(payload)
    assert parsed["vulnerable"] is True
    assert parsed["injection_points"][0]["parameter"] == "id"
