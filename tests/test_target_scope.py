from types import SimpleNamespace

import pytest

from pentestagent.agents.base_agent import BaseAgent
from pentestagent.workspaces.manager import WorkspaceManager


class DummyTool:
    def __init__(self, name="dummy"):
        self.name = name

    async def execute(self, arguments, runtime):
        return "ok"


class SimpleAgent(BaseAgent):
    def get_system_prompt(self, mode: str = "agent") -> str:
        return ""


@pytest.mark.asyncio
async def test_ip_and_cidr_containment(tmp_path, monkeypatch):
    # Use tmp_path as project root so WorkspaceManager writes here
    monkeypatch.chdir(tmp_path)

    wm = WorkspaceManager(root=tmp_path)
    name = "scope-test"
    wm.create(name)
    wm.set_active(name)

    tool = DummyTool("dummy")
    agent = SimpleAgent(llm=object(), tools=[tool], runtime=SimpleNamespace())

    # Helper to run execute_tools with a candidate target
    async def run_with_candidate(candidate):
        call = {"id": "1", "name": "dummy", "arguments": {"target": candidate}}
        results = await agent._execute_tools([call])
        return results[0]

    # 1) Allowed single IP, candidate same IP
    wm.add_targets(name, ["192.0.2.5"])
    res = await run_with_candidate("192.0.2.5")
    assert res.success is True

    # 2) Allowed single IP, candidate single-address CIDR (/32) -> allowed
    res = await run_with_candidate("192.0.2.5/32")
    assert res.success is True

    # 3) Allowed CIDR, candidate IP inside -> allowed
    wm.add_targets(name, ["198.51.100.0/24"])
    res = await run_with_candidate("198.51.100.25")
    assert res.success is True

    # 4) Allowed CIDR, candidate subnet inside -> allowed
    wm.add_targets(name, ["203.0.113.0/24"])
    res = await run_with_candidate("203.0.113.128/25")
    assert res.success is True

    # 5) Allowed single IP, candidate larger network -> not allowed
    wm.add_targets(name, ["192.0.2.5"])
    res = await run_with_candidate("192.0.2.0/24")
    assert res.success is False
