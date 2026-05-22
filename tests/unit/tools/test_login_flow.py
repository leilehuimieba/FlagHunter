import pytest


@pytest.mark.asyncio
async def test_login_flow_no_runtime():
    from pentestagent.tools.login_flow import run_login_flow

    result = await run_login_flow(
        "http://x",
        "#u",
        "#p",
        "admin",
        "pass",
        runtime=None,
    )

    assert result["success"] is False
    assert "runtime" in result["error"].lower()


@pytest.mark.asyncio
async def test_login_flow_ssh_runtime_rejected():
    from pentestagent.tools.login_flow import run_login_flow

    FakeSSH = type("SSHRuntime", (), {})

    result = await run_login_flow(
        "http://x",
        "#u",
        "#p",
        "admin",
        "pass",
        runtime=FakeSSH(),
    )

    assert result["success"] is False
    assert "LocalRuntime" in result["error"] or "Playwright" in result["error"]


@pytest.mark.asyncio
async def test_login_flow_browser_error_propagates():
    from pentestagent.tools.login_flow import run_login_flow

    class FakeRuntime:
        async def browser_action(self, action, **kw):
            return {"error": "page not found"}

    result = await run_login_flow(
        "http://x",
        "#u",
        "#p",
        "admin",
        "pass",
        runtime=FakeRuntime(),
    )

    assert result["success"] is False
