"""Tests for the structured dirscan wrapper."""

import importlib
import json

import pytest

import pentestagent.tools.dirscan as dirscan_module
from pentestagent.tools.dirscan import run_dirscan
from pentestagent.tools.registry import clear_tools, get_tool


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
async def test_run_dirscan_parses_ffuf_jsonl_using_real_url_path(tmp_path):
    wordlist = tmp_path / "mini.txt"
    wordlist.write_text("admin\nlogin.php\n", encoding="utf-8")

    stdout = "\n".join(
        [
            '{"input":{"FUZZ":"YWRtaW4="},"status":301,"length":0,"url":"http://example.com/admin"}',
            '{"input":{"FUZZ":"bG9naW4ucGhw"},"status":200,"length":24,"url":"http://example.com/login.php"}',
        ]
    )
    runtime = _FakeRuntime([_CommandResult(0, stdout=stdout)])

    result = await run_dirscan(
        url="http://example.com",
        wordlist=str(wordlist),
        extensions=["php"],
        tool="ffuf",
        runtime=runtime,
    )

    assert result["tool_used"] == "ffuf"
    assert result["total_found"] == 2
    assert result["found"][0]["path"] == "/admin"
    assert result["found"][1]["path"] == "/login.php"
    assert "YWRtaW4=" in result["raw"]
    assert "-json" in runtime.commands[0][0]
    assert "-noninteractive" in runtime.commands[0][0]


@pytest.mark.asyncio
async def test_run_dirscan_parses_gobuster_output(tmp_path):
    wordlist = tmp_path / "mini.txt"
    wordlist.write_text("admin\nitem\n", encoding="utf-8")

    stdout = "\n".join(
        [
            "/admin                (Status: 301) [Size: 0]",
            "/item                 (Status: 200) [Size: 11]",
        ]
    )
    runtime = _FakeRuntime([_CommandResult(0, stdout=stdout)])

    result = await run_dirscan(
        url="http://example.com",
        wordlist=str(wordlist),
        tool="gobuster",
        runtime=runtime,
    )

    assert result["tool_used"] == "gobuster"
    assert result["total_found"] == 2
    assert result["found"][0]["path"] == "/admin"
    assert result["found"][1]["size"] == 11
    assert "gobuster dir" in runtime.commands[0][0]


@pytest.mark.asyncio
async def test_run_dirscan_parses_dirsearch_output(tmp_path):
    wordlist = tmp_path / "mini.txt"
    wordlist.write_text("admin\nrobots.txt\n", encoding="utf-8")

    stdout = "\n".join(
        [
            "[14:52:35] 200 -   34B  - http://example.com/robots.txt",
            "[14:52:35] 301 -    0B  - http://example.com/admin  ->  /admin/",
        ]
    )
    runtime = _FakeRuntime([_CommandResult(0, stdout=stdout)])

    result = await run_dirscan(
        url="http://example.com",
        wordlist=str(wordlist),
        tool="dirsearch",
        runtime=runtime,
    )

    assert result["tool_used"] == "dirsearch"
    assert result["total_found"] == 2
    assert result["found"][0]["path"] == "/robots.txt"
    assert result["found"][0]["size"] == 34
    assert result["found"][1]["path"] == "/admin"
    assert "dirsearch" in runtime.commands[0][0]


@pytest.mark.asyncio
async def test_run_dirscan_auto_falls_back_from_ffuf_to_gobuster(
    monkeypatch, tmp_path
):
    wordlist = tmp_path / "mini.txt"
    wordlist.write_text("admin\n", encoding="utf-8")

    calls: list[str] = []

    async def _fake_ffuf(url, wordlist, extensions, runtime, headers=None):
        calls.append("ffuf")
        return {
            "url": url,
            "tool_used": "ffuf",
            "found": [],
            "total_found": 0,
            "raw": "ffuf failed",
        }, False

    async def _fake_gobuster(url, wordlist, extensions, runtime, headers=None):
        calls.append("gobuster")
        return {
            "url": url,
            "tool_used": "gobuster",
            "found": [{"path": "/admin", "status": 301, "size": 0}],
            "total_found": 1,
            "raw": "gobuster success",
        }, True

    async def _fake_dirsearch(url, wordlist, extensions, runtime, headers=None):
        calls.append("dirsearch")
        return {
            "url": url,
            "tool_used": "dirsearch",
            "found": [],
            "total_found": 0,
            "raw": "dirsearch unused",
        }, True

    monkeypatch.setattr(dirscan_module, "_run_with_ffuf", _fake_ffuf)
    monkeypatch.setattr(dirscan_module, "_run_with_gobuster", _fake_gobuster)
    monkeypatch.setattr(dirscan_module, "_run_with_dirsearch", _fake_dirsearch)
    monkeypatch.setattr(dirscan_module, "find_tool", lambda name: f"C:/tools/{name}.exe")

    result = await run_dirscan(
        url="http://example.com",
        wordlist=str(wordlist),
        tool="auto",
        runtime=None,
    )

    assert result["tool_used"] == "gobuster"
    assert calls == ["ffuf", "gobuster"]


@pytest.mark.asyncio
async def test_registered_tool_returns_json_string(tmp_path):
    clear_tools()
    importlib.reload(dirscan_module)

    wordlist = tmp_path / "mini.txt"
    wordlist.write_text("admin\n", encoding="utf-8")

    stdout = '{"input":{"FUZZ":"YWRtaW4="},"status":301,"length":0,"url":"http://example.com/admin"}'
    runtime = _FakeRuntime([_CommandResult(0, stdout=stdout)])
    tool = get_tool("dirscan")

    assert tool is not None
    payload = await tool.execute(
        {
            "url": "http://example.com",
            "wordlist": str(wordlist),
            "extensions": ["php"],
            "tool": "ffuf",
        },
        runtime,
    )
    parsed = json.loads(payload)

    assert parsed["tool_used"] == "ffuf"
    assert parsed["total_found"] == 1
    assert parsed["found"][0]["path"] == "/admin"
