"""remote_service_login: credentialed SSH access (T1133), mocked at the subprocess seam.

All tests monkeypatch the module-level `_run_ssh` seam — no real network, no real
ssh client, synthetic credentials only.
"""

from __future__ import annotations

import json

import pytest

import flaghunter.tools.remote_service_login as rsl
from flaghunter.tools.registry import get_tool


def test_tool_is_registered_and_tagged():
    tool = get_tool("remote_service_login")
    assert tool is not None
    assert tool.technique_ids == ["T1133"]


@pytest.mark.asyncio
async def test_successful_password_login(monkeypatch):
    def fake_run(ssh_command, *, password, timeout):
        assert password == "hunter2"  # the supplied known password reached the seam
        return {"returncode": 0, "stdout": "uid=0(root) gid=0(root)\n", "stderr": ""}

    monkeypatch.setattr(rsl, "_run_ssh", fake_run)
    out = json.loads(
        await rsl.remote_service_login(
            {"host": "10.0.0.9", "username": "root", "password": "hunter2", "command": "id"}, None
        )
    )
    assert out["authenticated"] is True
    assert out["method"] == "password"
    assert "uid=0" in out["command_output"]
    # raw password is never echoed back
    assert "hunter2" not in json.dumps(out)


@pytest.mark.asyncio
async def test_wrong_credentials_not_authenticated(monkeypatch):
    def fake_run(ssh_command, *, password, timeout):
        return {"returncode": 255, "stdout": "", "stderr": "Permission denied (publickey,password)."}

    monkeypatch.setattr(rsl, "_run_ssh", fake_run)
    out = json.loads(
        await rsl.remote_service_login(
            {"host": "10.0.0.9", "username": "root", "candidate_passwords": ["a", "b", "c"]}, None
        )
    )
    assert out["authenticated"] is False
    assert len(out["attempts"]) == 3  # tried each candidate
    assert "rejected" in out["reason"]


@pytest.mark.asyncio
async def test_candidate_list_stops_at_first_success(monkeypatch):
    calls = {"n": 0}

    def fake_run(ssh_command, *, password, timeout):
        calls["n"] += 1
        # second candidate works
        if password == "good":
            return {"returncode": 0, "stdout": "ok", "stderr": ""}
        return {"returncode": 255, "stdout": "", "stderr": "denied"}

    monkeypatch.setattr(rsl, "_run_ssh", fake_run)
    out = json.loads(
        await rsl.remote_service_login(
            {"host": "h", "username": "u", "candidate_passwords": ["bad", "good", "never"]}, None
        )
    )
    assert out["authenticated"] is True
    assert out["which_credential"] == "candidate#2"
    assert calls["n"] == 2  # short-circuits, never tries "never"


@pytest.mark.asyncio
async def test_no_credentials_is_honest_failure(monkeypatch):
    monkeypatch.setattr(rsl, "_run_ssh", lambda *a, **k: {"returncode": 0, "stdout": "", "stderr": ""})
    out = json.loads(await rsl.remote_service_login({"host": "h", "username": "u"}, None))
    assert out["authenticated"] is False
    assert "no credentials" in out["reason"]


@pytest.mark.asyncio
async def test_key_auth_uses_batch_mode(monkeypatch):
    seen = {}

    def fake_run(ssh_command, *, password, timeout):
        seen["cmd"] = ssh_command
        seen["password"] = password
        return {"returncode": 0, "stdout": "key ok", "stderr": ""}

    monkeypatch.setattr(rsl, "_run_ssh", fake_run)
    out = json.loads(
        await rsl.remote_service_login({"host": "h", "username": "u", "key_path": "/k/id_rsa"}, None)
    )
    assert out["authenticated"] is True
    assert out["method"] == "key"
    assert "BatchMode=yes" in seen["cmd"]
    assert "-i" in seen["cmd"] and "/k/id_rsa" in seen["cmd"]
    assert seen["password"] is None  # key auth carries no password


@pytest.mark.asyncio
async def test_requires_host_and_username():
    assert "host is required" in await rsl.remote_service_login({"username": "u"}, None)
    assert "username is required" in await rsl.remote_service_login({"host": "h"}, None)
