"""Tests for CLI header passthrough in web tooling wrappers."""

from __future__ import annotations

import pytest

from pentestagent.tools.dirscan import run_dirscan
from pentestagent.tools.nuclei import run_nuclei
from pentestagent.tools.sqlmap import run_sqlmap


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
        self.commands: list[tuple[str, int]] = []

    async def execute_command(self, command: str, timeout: int = 300):
        self.commands.append((command, timeout))
        if not self._results:
            raise AssertionError("No more fake command results configured")
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_dirscan_headers_appended(tmp_path):
    wordlist = tmp_path / "mini.txt"
    wordlist.write_text("admin\n", encoding="utf-8")
    runtime = _FakeRuntime(
        [_CommandResult(0, stdout='{"input":{"FUZZ":"YWRtaW4="},"status":200,"length":5,"url":"http://example.com/admin"}')]
    )

    await run_dirscan(
        url="http://example.com",
        wordlist=str(wordlist),
        tool="ffuf",
        headers={"Cookie": "s=1", "User-Agent": "UA"},
        runtime=runtime,
    )

    command = runtime.commands[0][0]
    assert '-H "Cookie: s=1"' in command
    assert '-H "User-Agent: UA"' in command


@pytest.mark.asyncio
async def test_nuclei_headers_appended():
    runtime = _FakeRuntime(
        [
            _CommandResult(0, stdout="3.4.0"),
            _CommandResult(0, stdout='{"template-id":"demo","info":{"name":"Demo","severity":"high"},"host":"http://example.com","matched-at":"http://example.com"}'),
        ]
    )

    await run_nuclei(
        "http://example.com",
        headers={"Cookie": "s=1", "User-Agent": "UA"},
        runtime=runtime,
    )

    command = runtime.commands[1][0]
    assert '-H "Cookie: s=1"' in command
    assert '-H "User-Agent: UA"' in command


@pytest.mark.asyncio
async def test_sqlmap_cookie_header():
    runtime = _FakeRuntime([_CommandResult(0, stdout="1.8.5"), _CommandResult(0, stdout="")])

    await run_sqlmap(
        "http://example.com?id=1",
        headers={"Cookie": "s=1"},
        runtime=runtime,
    )

    command = runtime.commands[1][0]
    assert '--cookie="s=1"' in command


@pytest.mark.asyncio
async def test_sqlmap_custom_header():
    runtime = _FakeRuntime([_CommandResult(0, stdout="1.8.5"), _CommandResult(0, stdout="")])

    await run_sqlmap(
        "http://example.com?id=1",
        headers={"X-Forwarded-For": "127.0.0.1"},
        runtime=runtime,
    )

    command = runtime.commands[1][0]
    assert '-H "X-Forwarded-For: 127.0.0.1"' in command


@pytest.mark.asyncio
async def test_empty_headers_no_change(tmp_path):
    wordlist = tmp_path / "mini.txt"
    wordlist.write_text("admin\n", encoding="utf-8")

    dirscan_runtime = _FakeRuntime(
        [_CommandResult(0, stdout='{"input":{"FUZZ":"YWRtaW4="},"status":200,"length":5,"url":"http://example.com/admin"}')]
    )
    await run_dirscan(
        url="http://example.com",
        wordlist=str(wordlist),
        tool="ffuf",
        headers={},
        runtime=dirscan_runtime,
    )
    assert ' -H ' not in dirscan_runtime.commands[0][0]
    assert '--headers' not in dirscan_runtime.commands[0][0]

    nuclei_runtime = _FakeRuntime(
        [
            _CommandResult(0, stdout="3.4.0"),
            _CommandResult(0, stdout='{"template-id":"demo","info":{"name":"Demo","severity":"high"},"host":"http://example.com","matched-at":"http://example.com"}'),
        ]
    )
    await run_nuclei("http://example.com", headers={}, runtime=nuclei_runtime)
    assert ' -H ' not in nuclei_runtime.commands[1][0]

    sqlmap_runtime = _FakeRuntime([_CommandResult(0, stdout="1.8.5"), _CommandResult(0, stdout="")])
    await run_sqlmap("http://example.com?id=1", headers={}, runtime=sqlmap_runtime)
    assert ' -H ' not in sqlmap_runtime.commands[1][0]
    assert "--cookie=" not in sqlmap_runtime.commands[1][0]
