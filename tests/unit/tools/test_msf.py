"""Tests for pentestagent.tools.msf."""

import pytest

from pentestagent.tools import msf as msf_module


class _DummyModule:
    def __init__(self):
        self.values = {}
        self.info = {"name": "dummy"}

    def __setitem__(self, key, value):
        self.values[key] = value


class _FakeModules:
    def __init__(self, module_obj=None):
        self.module_obj = module_obj or _DummyModule()
        self.calls = []

    def use(self, module_type, module_name):
        self.calls.append((module_type, module_name))
        return self.module_obj


class _FakeConsole:
    def __init__(self, reads):
        self.reads = list(reads)
        self.writes = []
        self.destroyed = False

    def write(self, command):
        self.writes.append(command)

    def read(self):
        if self.reads:
            return self.reads.pop(0)
        return {"busy": False, "data": ""}

    def destroy(self):
        self.destroyed = True


class _FakeConsoles:
    def __init__(self, consoles):
        self._consoles = list(consoles)

    def console(self):
        if not self._consoles:
            raise AssertionError("No fake console left")
        return self._consoles.pop(0)


class _FakeSession:
    def __init__(self, output):
        self.output = output
        self.commands = []

    def run_with_output(self, cmd):
        self.commands.append(cmd)
        return self.output


class _FakeSessions:
    def __init__(self, listing=None, session_obj=None):
        self.list = listing or {}
        self._session_obj = session_obj or _FakeSession("")
        self.requested_ids = []

    def session(self, session_id):
        self.requested_ids.append(session_id)
        return self._session_obj


class _FakeClient:
    def __init__(self, *, sessions=None, modules=None, consoles=None):
        self.sessions = sessions or _FakeSessions()
        self.modules = modules or _FakeModules()
        self.consoles = consoles or _FakeConsoles([_FakeConsole([{"busy": False, "data": ""}])])


@pytest.mark.asyncio
async def test_missing_pymetasploit3(monkeypatch):
    def _raise_import_error():
        raise ImportError("missing")

    monkeypatch.setattr(msf_module, "_import_msf_rpc_client", _raise_import_error)

    result = await msf_module.run_msf(action="sessions")

    assert result["success"] is False
    assert "pip install pymetasploit3" in result["error"]


@pytest.mark.asyncio
async def test_sessions_list_formats_output(monkeypatch):
    fake_client = _FakeClient(
        sessions=_FakeSessions(
            listing={
                "2": {
                    "type": "shell",
                    "tunnel_local": "10.10.10.5:4444",
                    "tunnel_peer": "10.10.10.10:51123",
                    "info": "www-data @ web01",
                },
                "1": {
                    "type": "meterpreter",
                    "tunnel_local": "10.10.10.5:5555",
                    "tunnel_peer": "10.10.10.11:62001",
                    "info": "NT AUTHORITY\\SYSTEM @ win01",
                },
            }
        )
    )
    monkeypatch.setattr(msf_module, "_create_msf_client", lambda remote=False: fake_client)

    result = await msf_module.run_msf(action="sessions")

    assert result["success"] is True
    assert result["output"].splitlines() == [
        "1 | meterpreter | 10.10.10.5:5555 | 10.10.10.11:62001 | NT AUTHORITY\\SYSTEM @ win01",
        "2 | shell | 10.10.10.5:4444 | 10.10.10.10:51123 | www-data @ web01",
    ]


@pytest.mark.asyncio
async def test_run_timeout(monkeypatch):
    async def _no_sleep(_seconds):
        return None

    setg_console = _FakeConsole([{"busy": False, "data": ""}])
    run_console = _FakeConsole([{"busy": True, "data": "still running\n"}] * 60)
    fake_client = _FakeClient(
        modules=_FakeModules(),
        consoles=_FakeConsoles([setg_console, run_console]),
    )
    monkeypatch.setattr(msf_module, "_create_msf_client", lambda remote=False: fake_client)
    monkeypatch.setattr(msf_module.asyncio, "sleep", _no_sleep)

    result = await msf_module.run_msf(
        action="run",
        module="exploit/multi/handler",
        options={"PAYLOAD": "linux/x64/shell_reverse_tcp"},
    )

    assert result["success"] is True
    assert result["timeout"] is True
    assert result["output"].endswith("(timeout)")
    assert "use exploit/multi/handler\n" in run_console.writes
    assert "run\n" in run_console.writes


@pytest.mark.asyncio
async def test_exec_returns_output(monkeypatch):
    fake_session = _FakeSession("uid=33(www-data) gid=33(www-data)")
    fake_client = _FakeClient(sessions=_FakeSessions(session_obj=fake_session))
    monkeypatch.setattr(msf_module, "_create_msf_client", lambda remote=False: fake_client)

    result = await msf_module.run_msf(action="exec", session_id="7", cmd="id")

    assert result["success"] is True
    assert result["session_id"] == "7"
    assert result["output"] == "uid=33(www-data) gid=33(www-data)"
    assert fake_client.sessions.requested_ids == ["7"]
    assert fake_session.commands == ["id"]
