"""Tests for the structured nuclei wrapper."""

import importlib
import json

import pytest

from flaghunter.tools.nuclei import run_nuclei
from flaghunter.tools.registry import clear_tools, get_tool


class _CommandResult:
    def __init__(self, exit_code: int, stdout: str = "", stderr: str = ""):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def success(self) -> bool:
        return self.exit_code == 0


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
async def test_run_nuclei_returns_not_installed_when_probe_fails():
    runtime = _FakeRuntime([
        _CommandResult(1, stderr="nuclei : The term 'nuclei' is not recognized as the name of a cmdlet"),
    ])

    result = await run_nuclei("http://example.com", runtime=runtime)

    assert result["error"] == "nuclei not installed"
    assert result["findings"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_run_nuclei_parses_jsonl_output():
    stdout = "\n".join(
        [
            '{"template-id":"CVE-2021-41773","info":{"name":"Apache Path Traversal","severity":"critical"},"host":"http://example.com","matched-at":"http://example.com/cgi-bin/.%2e/.%2e/etc/passwd","extracted-results":["root:x:0:0"],"ip":"127.0.0.1"}',
            'not-json-noise',
            '{"template-id":"exposed-panel","info":{"name":"Admin Panel","severity":"medium"},"host":"http://example.com","matched-at":"http://example.com/admin","matcher-name":"status-200"}',
        ]
    )
    runtime = _FakeRuntime([
        _CommandResult(0, stdout="3.4.0"),
        _CommandResult(0, stdout=stdout),
    ])

    result = await run_nuclei(
        "http://example.com",
        templates=["http/cves"],
        severity=["critical", "medium"],
        tags=["cve", "panel"],
        runtime=runtime,
    )

    assert result["total"] == 2
    assert result["findings"][0]["template_id"] == "CVE-2021-41773"
    assert result["findings"][0]["severity"] == "critical"
    assert result["findings"][0]["matched"] == "root:x:0:0"
    assert result["findings"][1]["url"] == "http://example.com/admin"
    scan_command = runtime.commands[1][0]
    assert "-j" in scan_command
    assert "-severity" in scan_command
    assert "-tags" in scan_command
    assert '-t "http/cves"' in scan_command


@pytest.mark.asyncio
async def test_registered_tool_returns_json_string():
    clear_tools()
    import flaghunter.tools.nuclei as nuclei_module

    importlib.reload(nuclei_module)
    runtime = _FakeRuntime([
        _CommandResult(0, stdout="3.4.0"),
        _CommandResult(0, stdout='{"template-id":"demo","info":{"name":"Demo","severity":"high"},"host":"http://example.com","matched-at":"http://example.com"}'),
    ])
    tool = get_tool("nuclei")

    assert tool is not None
    payload = await tool.execute({"target": "http://example.com"}, runtime)
    parsed = json.loads(payload)

    assert parsed["total"] == 1
    assert parsed["findings"][0]["template_id"] == "demo"
