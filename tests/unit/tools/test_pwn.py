import importlib
import json

import pytest

from pentestagent.tools.registry import clear_tools, get_tool


@pytest.mark.asyncio
async def test_run_pwn_script_extracts_flag():
    from pentestagent.tools.pwn import run_pwn_script

    result = await run_pwn_script("print('flag{abc123}')")

    assert result["success"] is True
    assert result["flag"] == "flag{abc123}"
    assert "flag{abc123}" in result["output"]
    assert result["error"] == ""


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
