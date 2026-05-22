"""Full-chain integration tests for FlagHunter / PentestAgent improvements."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from pentestagent.agents.pa_agent.pa_agent import PentestAgentAgent
from pentestagent.agents.crew.swarm_bridge import on_worker_complete
from pentestagent.runtime.runtime import LocalRuntime
from pentestagent.tools.executor import ToolExecutor
from pentestagent.tools.registry import Tool, ToolSchema, get_tool
from pentestagent.tools.sqlmap import run_sqlmap
from pentestagent.tools.pwn import run_pwn_script


class _CommandResult:
    def __init__(self, exit_code: int, stdout: str = "", stderr: str = ""):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class _RoutingRuntime:
    """Simple runtime that dispatches command results by substring match."""

    def __init__(self, routes: dict[str, _CommandResult]):
        self.routes = routes
        self.environment = SimpleNamespace()
        self.plan = None

    async def execute_command(self, command: str, timeout: int = 300):
        for key, result in self.routes.items():
            if key in command:
                return result
        return _CommandResult(127, "", f"unmatched command: {command}")


class _PlanningLLM:
    async def generate(self, system_prompt, messages, tools, task_hint="default", **kwargs):
        return SimpleNamespace(
            content=json.dumps(
                {
                    "objective": "扫描并发现 Web 服务",
                    "phases": [
                        {
                            "phase": 1,
                            "name": "信息收集",
                            "steps": [
                                {
                                    "step": 1,
                                    "tool": "nmap",
                                    "args": {
                                        "target": "192.168.1.100",
                                        "ports": "80,443",
                                    },
                                    "purpose": "扫描开放端口",
                                    "depends_on": [],
                                },
                                {
                                    "step": 2,
                                    "tool": "dirscan",
                                    "args": {"url": "http://192.168.1.100"},
                                    "purpose": "枚举目录",
                                    "depends_on": ["1"],
                                },
                                {
                                    "step": 3,
                                    "tool": "nuclei",
                                    "args": {"target": "http://192.168.1.100"},
                                    "purpose": "漏洞模板扫描",
                                    "depends_on": ["2"],
                                },
                            ],
                        }
                    ],
                    "risk_level": "medium",
                    "estimated_steps": 3,
                },
                ensure_ascii=False,
            ),
            tool_calls=None,
            usage={"total_tokens": 12},
        )


def _load_tool_modules():
    import pentestagent.tools.nmap  # noqa: F401
    import pentestagent.tools.dirscan  # noqa: F401
    import pentestagent.tools.nuclei  # noqa: F401
    import pentestagent.tools.sqlmap  # noqa: F401
    import pentestagent.tools.pwn  # noqa: F401


@pytest.mark.asyncio
async def test_web_task_chain_with_planning_m4_and_structured_tools(monkeypatch):
    _load_tool_modules()

    nmap_tool = get_tool("nmap")
    dirscan_tool = get_tool("dirscan")
    nuclei_tool = get_tool("nuclei")
    assert nmap_tool is not None and dirscan_tool is not None and nuclei_tool is not None

    # 1) planning pass
    agent = PentestAgentAgent(
        llm=_PlanningLLM(),
        tools=[nmap_tool, dirscan_tool, nuclei_tool],
        runtime=_RoutingRuntime({}),
        target="192.168.1.100",
        scope=["192.168.1.0/24"],
    )
    agent.conversation_history.append(
        SimpleNamespace(role="user", content="扫描 192.168.1.100 的 Web 服务")
    )
    plan_msg = await agent._auto_generate_plan()
    assert plan_msg is not None
    assert plan_msg.metadata.get("structured_plan")
    assert len(agent._task_plan.steps) >= 3

    # 2) M4 allow + nmap/dirscan/nuclei structured tool execution
    import pentestagent.tools.executor as executor_module

    monkeypatch.setattr(executor_module, "_m4_scope_check", lambda tool_name, args: (True, ""))

    nmap_runtime = _RoutingRuntime(
        {
            "nmap -oX -": _CommandResult(
                0,
                stdout="""<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <ports>
      <port protocol="tcp" portid="80">
        <state state="open"/>
        <service name="http" product="Apache" version="2.4.51"/>
      </port>
    </ports>
    <os><osmatch name="Linux 4.x"/></os>
  </host>
</nmaprun>""",
            )
        }
    )
    nmap_result = await ToolExecutor(runtime=nmap_runtime, timeout=10).execute(
        nmap_tool, {"target": "192.168.1.100", "ports": "80,443"}
    )
    parsed_nmap = json.loads(nmap_result.result)
    assert nmap_result.success is True
    assert parsed_nmap["status"] == "up"
    assert parsed_nmap["ports"][0]["port"] == 80

    dirscan_runtime = _RoutingRuntime(
        {
            "python -c": _CommandResult(0, stdout="1"),
            "ffuf ": _CommandResult(
                0,
                stdout='{"input":{"FUZZ":"admin"},"status":200,"length":123}\n',
            ),
        }
    )
    dirscan_result = await ToolExecutor(runtime=dirscan_runtime, timeout=10).execute(
        dirscan_tool,
        {"url": "http://192.168.1.100", "wordlist": "virtual.txt"},
    )
    parsed_dirscan = json.loads(dirscan_result.result)
    assert dirscan_result.success is True
    assert parsed_dirscan["found"][0]["path"] == "/admin"

    nuclei_runtime = _RoutingRuntime(
        {
            "nuclei -version": _CommandResult(0, stdout="3.4.0"),
            "nuclei -target": _CommandResult(
                0,
                stdout='{"template-id":"demo","info":{"name":"Demo","severity":"high"},"host":"http://192.168.1.100","matched-at":"http://192.168.1.100"}',
            ),
        }
    )
    nuclei_result = await ToolExecutor(runtime=nuclei_runtime, timeout=10).execute(
        nuclei_tool, {"target": "http://192.168.1.100"}
    )
    parsed_nuclei = json.loads(nuclei_result.result)
    assert nuclei_result.success is True
    assert parsed_nuclei["total"] == 1
    assert parsed_nuclei["findings"][0]["template_id"] == "demo"


@pytest.mark.asyncio
async def test_scope_outside_request_is_blocked(monkeypatch):
    _load_tool_modules()
    nmap_tool = get_tool("nmap")
    assert nmap_tool is not None

    import pentestagent.tools.executor as executor_module

    monkeypatch.setattr(
        executor_module,
        "_m4_scope_check",
        lambda tool_name, args: (False, "target outside allowed scope"),
    )

    runtime = _RoutingRuntime({})
    result = await ToolExecutor(runtime=runtime, timeout=5).execute(
        nmap_tool, {"target": "8.8.8.8"}
    )
    assert result.success is False
    assert result.error is not None
    assert "M4 BLOCKED" in result.error


@pytest.mark.asyncio
async def test_ctf_mode_pwn_wrapper_returns_flag():
    result = await run_pwn_script("print('flag{integration_ok}')", timeout=5)
    assert result["success"] is True
    assert result["flag"] == "flag{integration_ok}"


@pytest.mark.asyncio
async def test_crew_swarm_bridge_writes_blackboard_and_pheromone(tmp_path, monkeypatch):
    monkeypatch.setenv("CPA_M5_SWARM_LINK", "true")
    monkeypatch.setenv("CPA_M5_BLACKBOARD_DB", str(tmp_path / "blackboard.db"))

    import cpa_modules.m5_swarm_link as m5

    m5 = importlib.reload(m5)
    await m5.init_m5()

    await on_worker_complete(
        agent_id="agent-1",
        task="scan web",
        target="192.168.1.100",
        result="found admin panel and interesting banner",
        success=True,
    )

    board = m5.get_blackboard()
    msgs = await board.get_recent(n=10)
    assert len(msgs) > 0
    assert any(msg.target == "192.168.1.100" for msg in msgs)

    router = m5.get_pheromone_router()
    top_targets = await router.get_top_targets(10)
    assert any(target == "192.168.1.100" for target, _ in top_targets)
