"""Tests for HybridBrowserRuntime — reachability-routed browser over a curl-only primary."""

import pytest

from flaghunter.runtime.hybrid_runtime import HybridBrowserRuntime
from flaghunter.runtime.runtime import CommandResult


def _const_async(value):
    async def _fn(*args, **kwargs):
        return value

    return _fn


class FakePrimary:
    """Stand-in for a curl-only SSH/Docker runtime."""

    def __init__(self):
        self.host = "10.0.0.5"
        self.user = "kali"
        self.calls = []
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def execute_command(self, command, timeout=300):
        self.calls.append(("exec", command))
        return CommandResult(exit_code=0, stdout="primary-exec", stderr="")

    async def proxy_action(self, action, **kwargs):
        self.calls.append(("proxy", action))
        return {"status_code": 200, "via": "primary"}

    async def browser_action(self, action, **kwargs):
        self.calls.append(("browser", action))
        if action == "diagnose":
            return {
                "available": True,
                "rendered_dom": False,
                "supports_actions": ["navigate", "get_cookies"],
            }
        if action == "get_cookies":
            return {"cookies": [], "cookie_string": "", "note": "no state"}
        return {"content": "primary-curl", "engine": "primary"}

    async def is_running(self):
        return True

    async def get_status(self):
        return {"type": "ssh", "running": True}


class FakeLocal:
    """Stand-in for a LocalRuntime with a real (rendered) browser."""

    instances = 0

    def __init__(self):
        FakeLocal.instances += 1
        self.started = False

    async def start(self):
        self.started = True

    async def stop(self):
        pass

    async def browser_action(self, action, **kwargs):
        if action == "get_cookies":
            return {
                "cookies": [{"name": "session", "value": "abc"}],
                "cookie_string": "session=abc",
            }
        return {"content": "local-rendered", "engine": "local", "rendered_dom": True}


@pytest.mark.asyncio
async def test_browser_routes_to_local_when_reachable(monkeypatch):
    rt = HybridBrowserRuntime(primary=FakePrimary(), browser_factory=FakeLocal)
    monkeypatch.setattr(rt, "_probe_local_reachable", _const_async(True))

    res = await rt.browser_action("navigate", url="http://127.0.0.1:8000/")
    assert res["engine"] == "local"


@pytest.mark.asyncio
async def test_browser_falls_back_to_primary_when_unreachable(monkeypatch):
    FakeLocal.instances = 0
    rt = HybridBrowserRuntime(primary=FakePrimary(), browser_factory=FakeLocal)
    monkeypatch.setattr(rt, "_probe_local_reachable", _const_async(False))

    res = await rt.browser_action("navigate", url="http://10.0.0.9/")
    assert res["engine"] == "primary"
    # Unreachable target must never construct/launch the local browser.
    assert FakeLocal.instances == 0


@pytest.mark.asyncio
async def test_passthrough_delegates_to_primary():
    primary = FakePrimary()
    rt = HybridBrowserRuntime(primary=primary, browser_factory=FakeLocal)

    assert (await rt.execute_command("id")).stdout == "primary-exec"
    assert (await rt.proxy_action("get", url="http://x/"))["via"] == "primary"

    status = await rt.get_status()
    assert status["hybrid_browser"] is True
    assert status["type"] == "ssh"

    # __getattr__ passthrough keeps runtime_info's host/user reads working.
    assert rt.host == "10.0.0.5"
    assert rt.user == "kali"


@pytest.mark.asyncio
async def test_host_engine_decision_is_cached(monkeypatch):
    rt = HybridBrowserRuntime(primary=FakePrimary(), browser_factory=FakeLocal)
    probe_calls = {"n": 0}

    async def fake_probe(url):
        probe_calls["n"] += 1
        return True

    monkeypatch.setattr(rt, "_probe_local_reachable", fake_probe)

    await rt.browser_action("navigate", url="http://t:8000/a")
    await rt.browser_action("get_content", url="http://t:8000/b")
    # A urless action reuses the last host's engine decision.
    await rt.browser_action("get_forms")

    assert probe_calls["n"] == 1


@pytest.mark.asyncio
async def test_get_cookies_returns_real_cookies_via_local(monkeypatch):
    rt = HybridBrowserRuntime(primary=FakePrimary(), browser_factory=FakeLocal)
    monkeypatch.setattr(rt, "_probe_local_reachable", _const_async(True))

    res = await rt.browser_action("get_cookies", url="http://127.0.0.1:8000/")
    # Fixes the Kali-backend gap where get_cookies returned an empty list.
    assert res["cookie_string"] == "session=abc"


@pytest.mark.asyncio
async def test_diagnose_delegates_to_primary_with_hybrid_flag():
    rt = HybridBrowserRuntime(primary=FakePrimary(), browser_factory=FakeLocal)

    res = await rt.browser_action("diagnose")
    assert res["hybrid_browser"] is True
    # Conservative: does not overpromise a rendered DOM before a session starts.
    assert res["rendered_dom"] is False


@pytest.mark.asyncio
async def test_local_session_exception_downgrades_to_primary(monkeypatch):
    class FlakyLocal(FakeLocal):
        async def browser_action(self, action, **kwargs):
            raise RuntimeError("connection refused")

    rt = HybridBrowserRuntime(primary=FakePrimary(), browser_factory=FlakyLocal)
    monkeypatch.setattr(rt, "_probe_local_reachable", _const_async(True))

    res = await rt.browser_action("navigate", url="http://127.0.0.1:9/")
    assert res["engine"] == "primary"
    # Host is downgraded so subsequent calls skip the local engine entirely.
    assert rt._host_engine["127.0.0.1:9"] == "primary"


@pytest.mark.asyncio
async def test_local_unreachable_error_result_downgrades_to_primary(monkeypatch):
    class UnreachableLocal(FakeLocal):
        async def browser_action(self, action, **kwargs):
            return {"error": "net::ERR_CONNECTION_REFUSED"}

    rt = HybridBrowserRuntime(primary=FakePrimary(), browser_factory=UnreachableLocal)
    monkeypatch.setattr(rt, "_probe_local_reachable", _const_async(True))

    res = await rt.browser_action("navigate", url="http://127.0.0.1:9/")
    assert res["engine"] == "primary"
    assert rt._host_engine["127.0.0.1:9"] == "primary"


@pytest.mark.asyncio
async def test_get_browser_status_reports_routing(monkeypatch):
    rt = HybridBrowserRuntime(primary=FakePrimary(), browser_factory=FakeLocal)

    monkeypatch.setattr(rt, "_probe_local_reachable", _const_async(True))
    await rt.browser_action("navigate", url="http://127.0.0.1:8000/")

    monkeypatch.setattr(rt, "_probe_local_reachable", _const_async(False))
    await rt.browser_action("navigate", url="http://10.9.9.9/")

    status = rt.get_browser_status()
    assert status["hybrid_browser"] is True
    assert status["engine_counts"]["local"] >= 1
    assert status["engine_counts"]["primary"] >= 1
    assert status["host_engines"]["127.0.0.1:8000"] == "local"
    assert status["host_engines"]["10.9.9.9:80"] == "primary"
    assert len(status["recent_decisions"]) >= 2
    # Probe latency is recorded on freshly-probed decisions.
    assert any("probe_ms" in decision for decision in status["recent_decisions"])


@pytest.mark.asyncio
async def test_downgrade_recorded_in_browser_status(monkeypatch):
    class FlakyLocal(FakeLocal):
        async def browser_action(self, action, **kwargs):
            raise RuntimeError("connection refused")

    rt = HybridBrowserRuntime(primary=FakePrimary(), browser_factory=FlakyLocal)
    monkeypatch.setattr(rt, "_probe_local_reachable", _const_async(True))

    await rt.browser_action("navigate", url="http://127.0.0.1:9/")

    status = rt.get_browser_status()
    assert status["downgrade_count"] >= 1
    assert any(decision.get("downgrade") for decision in status["recent_decisions"])
    assert status["host_engines"]["127.0.0.1:9"] == "primary"
