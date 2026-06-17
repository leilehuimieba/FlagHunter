import pytest


@pytest.mark.asyncio
async def test_binary_no_runtime_returns_valid_structure():
    """二进制不存在时，应返回有 error 字段的合法 JSON"""
    from flaghunter.tools.binary import analyze_binary

    result = await analyze_binary("/nonexistent/binary", runtime=None, timeout=5)

    assert isinstance(result, dict)
    assert "protections" in result
    assert "key_strings" in result
    assert "suggestions" in result
    assert "error" in result


def test_binary_suggestions_rule_engine():
    """suggestions 规则引擎独立测试"""
    from flaghunter.tools.binary import _generate_suggestions

    result = _generate_suggestions(
        protections={
            "nx": False,
            "pie": False,
            "canary": False,
            "relro": "No",
            "fortify": False,
        },
        key_functions=["main", "gets", "system"],
        key_strings=["Enter name:", "/bin/sh"],
        flags_found=[],
    )

    assert any("shellcode" in s.lower() or "nx" in s.lower() for s in result)
    assert any("rop" in s.lower() or "pie" in s.lower() for s in result)
    assert any("buffer overflow" in s.lower() or "gets" in s.lower() for s in result)
    assert any("ret2system" in s.lower() or "system" in s.lower() for s in result)
