import importlib
import json

import pytest

from pentestagent.tools.registry import clear_tools, get_tool


@pytest.mark.asyncio
async def test_run_pwn_script_extracts_flag():
    from pentestagent.tools.pwn import run_pwn_script

    result = await run_pwn_script("print('flag{abc123}')")

    assert {"success", "flag", "output", "error"} <= result.keys()
    assert result["success"] is True
    assert result["flag"] == "flag{abc123}"
    assert "flag{abc123}" in result["output"]
    assert result["error"] == ""


@pytest.mark.asyncio
async def test_run_pwn_script_returns_structured_error_when_python_missing(monkeypatch):
    import pentestagent.tools.pwn as pwn_module

    async def _raise_file_not_found(*args, **kwargs):
        raise FileNotFoundError("python not found")

    monkeypatch.setattr(pwn_module.asyncio, "create_subprocess_exec", _raise_file_not_found)

    result = await pwn_module.run_pwn_script("print('hello')")

    assert {"success", "flag", "output", "error"} <= result.keys()
    assert result["success"] is False
    assert result["flag"] == ""
    assert result["output"] == ""
    assert "python not found" in result["error"]


@pytest.mark.asyncio
async def test_pwn_tool_returns_json_string():
    clear_tools()
    import pentestagent.tools.pwn as pwn_module

    importlib.reload(pwn_module)
    tool = get_tool("pwn")
    assert tool is not None

    result = await tool.execute({"script": "print('CTF{demo_flag}')"}, runtime=None)
    parsed = json.loads(result)

    assert parsed["success"] is True
    assert parsed["flag"] == "CTF{demo_flag}"
    assert parsed["error"] == ""
