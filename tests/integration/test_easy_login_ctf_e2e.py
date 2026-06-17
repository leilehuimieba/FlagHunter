"""Direction-only easy_login grounding E2E.

This file intentionally validates runtime grounding and route selection, not
the full exploit chain. The reusable full-chain acceptance contract lives in
`D:/webstudy/FlagHunter/tests/integration/easy_login_acceptance.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.ctf_planner import get_ctf_quick_path
from flaghunter.agents.pa_agent.pa_agent import PentestAgentAgent
from flaghunter.tools.notes import get_all_notes_sync, set_notes_file
from flaghunter.tools.registry import get_tool
from flaghunter.workspaces.manager import WorkspaceManager

import flaghunter.tools.notes as notes_module


class _EasyLoginRuntime:
    def __init__(self):
        self.environment = SimpleNamespace()
        self.plan = None
        self.target = "http://localhost:3000/"
        self.browser_calls: list[tuple[str, dict]] = []
        self.proxy_calls: list[tuple[str, dict]] = []

    async def browser_action(self, action: str, **kwargs):
        self.browser_calls.append((action, dict(kwargs)))

        if action == "navigate":
            requested_url = kwargs.get("url", "")
            return {
                "url": "http://127.0.0.1:3000/",
                "requested_url": requested_url,
                "title": "easy_login Dashboard",
            }

        if action == "get_content":
            return {
                "content": "easy_login Login Portal Playground /visit /admin",
                "html": """
                <html>
                  <head>
                    <title>easy_login Dashboard</title>
                    <script src="/app.js"></script>
                  </head>
                  <body>
                    <form id="loginForm" action="/login" method="post">
                      <input id="username" name="username" />
                      <input id="password" name="password" />
                      <button type="submit">Login</button>
                    </form>
                  </body>
                </html>
                """,
            }

        if action == "get_forms":
            return {
                "forms": [
                    {
                        "action": "http://127.0.0.1:3000/login",
                        "method": "post",
                        "inputs": [
                            {"name": "username", "type": "text"},
                            {"name": "password", "type": "password"},
                        ],
                    }
                ]
            }

        if action == "get_cookies":
            return {
                "cookie_string": "sid=guest-preview; theme=light",
                "cookies": [
                    {"name": "sid", "value": "guest-preview"},
                    {"name": "theme", "value": "light"},
                ],
            }

        return {"error": f"unexpected browser action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        self.proxy_calls.append((action, dict(kwargs)))
        if action == "get" and kwargs.get("url") == "http://127.0.0.1:3000/app.js":
            return {
                "status_code": 200,
                "body": """
                fetch('/login', {method:'POST'});
                fetch('/visit', {method:'POST'});
                fetch('/admin');
                """,
            }
        return {"status_code": 404, "body": ""}


def _tool_call(call_id: str, name: str, arguments: dict):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments, ensure_ascii=False)),
    )


class _EasyLoginDirectionLLM:
    """A deterministic LLM stub that only proceeds when grounding is correct."""

    def __init__(self):
        self.normal_calls = 0
        self.summary_calls = 0
        self.runtime_blocks: list[str] = []

    async def generate(self, system_prompt, messages, tools, task_hint="default", **kwargs):
        if "Provide a brief, clear summary of what was accomplished" in system_prompt:
            self.summary_calls += 1
            return SimpleNamespace(
                content=(
                    "基于首页、表单、cookie 线索与前端脚本的真实证据，agent 不只锁定了 "
                    "/login、/visit、/admin，还把 easy_login 收敛成 payload -> collector "
                    "-> sid -> /admin 的 exploit 计划语言，同时避免了 /upload 等误导路径。"
                ),
                tool_calls=None,
                usage={"total_tokens": 8},
                finish_reason="stop",
            )

        runtime_block = system_prompt.split("## Runtime Ground Truth", 1)[1]
        self.runtime_blocks.append(runtime_block)

        if self.normal_calls == 0:
            assert "/visit" in runtime_block
            assert "/admin" in runtime_block
            assert "/upload" not in runtime_block
            assert "Observed cookie names: sid, theme" in runtime_block
            assert "Likely bot-XSS / sid-theft convergence" in runtime_block
            assert "payload -> /visit -> collector -> sid -> /admin" in runtime_block
            assert "local collector" in runtime_block
            assert "treat those claims as hypotheses" in runtime_block
            assert "Do not assume cross-origin DOM access" in runtime_block

            self.normal_calls += 1
            return SimpleNamespace(
                content="先复核首页内容，并按 payload -> /visit -> collector -> sid -> /admin 这条链做利用收敛。",
                tool_calls=[
                    _tool_call(
                        "browser-1",
                        "browser",
                        {"action": "get_content", "url": "http://localhost:3000/"},
                    )
                ],
                usage={"total_tokens": 10},
                finish_reason="tool_calls",
            )

        if self.normal_calls == 1:
            tool_messages = [m for m in messages if m.get("role") == "tool"]
            assert any("/visit" in (m.get("content") or "") for m in tool_messages)
            assert any("/admin" in (m.get("content") or "") for m in tool_messages)

            finish_calls = []
            for idx, step in enumerate(get_ctf_quick_path("xss"), start=1):
                if idx == 1:
                    result = "Observed homepage, JS, forms, and confirmed /login /visit /admin are the real routes."
                elif idx == 2:
                    result = "Converged toward a concrete payload shape instead of stopping at generic /upload-style guesses."
                elif idx == 3:
                    result = "Planned a local collector plus /visit trigger so the bot can leak sid without assuming cross-origin DOM tricks."
                elif idx == 4:
                    result = "Locked the next exploit hop as extracting sid from collector output before replaying it to /admin."
                else:
                    result = f"Exploit planning remained grounded while advancing runtime-backed XSS step: {step}"
                finish_calls.append(
                    _tool_call(
                        f"finish-{idx}",
                        "finish",
                        {"action": "complete", "step_id": idx, "result": result},
                    )
                )

            self.normal_calls += 1
            return SimpleNamespace(
                content="记录 easy_login 的 exploit 收敛计划，并完成本轮 E2E 评估。",
                tool_calls=[
                    _tool_call(
                        "notes-1",
                        "notes",
                        {
                            "action": "create",
                            "key": "easy_login_direction_eval",
                            "value": "Confirmed runtime-backed exploit plan: payload -> collector -> sid -> /admin, grounded by /login -> /visit -> /admin and reject /upload plus blind cross-origin assumptions.",
                            "category": "finding",
                            "confidence": "high",
                            "target": "127.0.0.1",
                            "endpoints": [
                                {"path": "/login", "methods": ["POST"]},
                                {"path": "/visit", "methods": ["POST"]},
                                {"path": "/admin", "methods": ["GET"]},
                            ],
                        },
                    ),
                    *finish_calls,
                ],
                usage={"total_tokens": 12},
                finish_reason="tool_calls",
            )

        raise AssertionError("unexpected extra non-summary LLM call")


@pytest.fixture
def isolated_notes(tmp_path: Path):
    notes_file = tmp_path / "notes.json"
    set_notes_file(notes_file)
    notes_module._notes.clear()
    notes_module._loaded_notes_file = None
    yield notes_file
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


@pytest.mark.asyncio
async def test_easy_login_ctf_agent_loop_e2e(monkeypatch, tmp_path, isolated_notes):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CPA_M3_REPORTER", "false")

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("flaghunter.tools.finish._persist_session_knowledge", _noop)
    monkeypatch.setattr("flaghunter.tools.finish._generate_auto_report", _noop)

    mgr = WorkspaceManager(root=tmp_path)
    mgr.create("easy_login_eval")
    mgr.add_targets("easy_login_eval", ["http://127.0.0.1:3000"])
    mgr.set_active("easy_login_eval")

    import flaghunter.tools.browser  # noqa: F401
    import flaghunter.tools.finish  # noqa: F401
    import flaghunter.tools.notes  # noqa: F401

    browser_tool = get_tool("browser")
    notes_tool = get_tool("notes")
    finish_tool = get_tool("finish")
    assert browser_tool is not None
    assert notes_tool is not None
    assert finish_tool is not None

    runtime = _EasyLoginRuntime()
    llm = _EasyLoginDirectionLLM()
    agent = PentestAgentAgent(
        llm=llm,
        tools=[browser_tool, notes_tool, finish_tool],
        runtime=runtime,
        target="http://localhost:3000/",
        scope=["http://127.0.0.1:3000"],
    )

    task = """[CTF MODE] Target: http://localhost:3000/
Challenge type: xss
Hint: maybe /upload kmz xml2json or cross-origin popup tricks

OBJECTIVE: Find and capture the flag as fast as possible.
"""

    messages = []
    async for msg in agent.agent_loop(task):
        messages.append(msg)

    assert agent._task_plan.is_complete() is True
    assert llm.summary_calls == 1
    assert runtime.browser_calls[0][0] == "navigate"
    assert runtime.browser_calls[1][0] == "get_content"
    assert runtime.browser_calls[2][0] == "get_forms"
    assert any(
        action == "get_content" and call.get("url") == "http://localhost:3000/"
        for action, call in runtime.browser_calls
    )
    assert runtime.proxy_calls == [
        ("get", {"url": "http://127.0.0.1:3000/app.js", "timeout": 10})
    ]

    notes = get_all_notes_sync()
    assert "easy_login_direction_eval" in notes
    saved = notes["easy_login_direction_eval"]
    assert saved["category"] == "finding"
    assert any(ep["path"] == "/visit" for ep in saved["metadata"]["endpoints"])
    assert any(ep["path"] == "/admin" for ep in saved["metadata"]["endpoints"])

    runtime_block = llm.runtime_blocks[0]
    assert "/visit" in runtime_block
    assert "/admin" in runtime_block
    assert "/upload" not in runtime_block
    assert "payload -> /visit -> collector -> sid -> /admin" in runtime_block

    completion_msgs = [m for m in messages if m.metadata.get("task_complete")]
    assert completion_msgs, "agent loop should emit a completion summary"
    summary = completion_msgs[-1].content.lower()
    assert "visit" in summary
    assert "admin" in summary
    assert "payload" in summary
    assert "collector" in summary
    assert "sid" in summary
    assert "easy_login" in summary
