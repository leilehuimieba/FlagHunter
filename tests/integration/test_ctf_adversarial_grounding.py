from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.pa_agent import PentestAgentAgent
from flaghunter.agents.pa_agent.ctf_state import CTFState, Hypothesis
from flaghunter.agents.pa_agent.ctf_planner import get_ctf_quick_path
from flaghunter.agents.pa_agent.hypothesis_engine import HypothesisEngine
from flaghunter.agents.pa_agent.recovery import RecoveryController
from flaghunter.tools.notes import get_all_notes_sync, set_notes_file
from flaghunter.tools.registry import get_tool
from flaghunter.workspaces.manager import WorkspaceManager

import flaghunter.tools.notes as notes_module


class _GroundedWebRuntime:
    def __init__(self):
        self.environment = SimpleNamespace()
        self.plan = None
        self.target = "http://localhost:3000/"
        self.browser_calls: list[tuple[str, dict]] = []
        self.proxy_calls: list[tuple[str, dict]] = []

    async def browser_action(self, action: str, **kwargs):
        self.browser_calls.append((action, dict(kwargs)))

        if action == "navigate":
            return {
                "url": "http://127.0.0.1:3000/",
                "requested_url": kwargs.get("url", ""),
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


class _AdversarialGroundingLLM:
    def __init__(
        self,
        *,
        expected_note_key: str,
        forbidden_runtime_terms: list[str],
        guardrail_terms: list[str],
        summary_text: str,
        note_value: str,
    ):
        self.expected_note_key = expected_note_key
        self.forbidden_runtime_terms = forbidden_runtime_terms
        self.guardrail_terms = guardrail_terms
        self.summary_text = summary_text
        self.note_value = note_value
        self.normal_calls = 0
        self.summary_calls = 0
        self.runtime_blocks: list[str] = []

    async def generate(self, system_prompt, messages, tools, task_hint="default", **kwargs):
        if "Provide a brief, clear summary of what was accomplished" in system_prompt:
            self.summary_calls += 1
            return SimpleNamespace(
                content=self.summary_text,
                tool_calls=None,
                usage={"total_tokens": 8},
                finish_reason="stop",
            )

        runtime_block = system_prompt.split("## Runtime Ground Truth", 1)[1]
        self.runtime_blocks.append(runtime_block)

        if self.normal_calls == 0:
            assert "/visit" in runtime_block
            assert "/admin" in runtime_block
            for term in self.forbidden_runtime_terms:
                assert term not in runtime_block
            for term in self.guardrail_terms:
                assert term in runtime_block

            self.normal_calls += 1
            return SimpleNamespace(
                content="先基于当前运行时证据锁定真实路由，再过滤误导提示。",
                tool_calls=[
                    _tool_call(
                        "browser-1",
                        "browser",
                        {"action": "get_content", "url": "http://localhost:3000/"},
                    )
                ],
                usage={"total_tokens": 11},
                finish_reason="tool_calls",
            )

        if self.normal_calls == 1:
            tool_messages = [m for m in messages if m.get("role") == "tool"]
            assert any("/visit" in (m.get("content") or "") for m in tool_messages)
            assert any("/admin" in (m.get("content") or "") for m in tool_messages)
            for term in self.forbidden_runtime_terms:
                assert all(term not in (m.get("content") or "") for m in tool_messages)

            finish_calls = []
            for idx, _step in enumerate(get_ctf_quick_path("xss"), start=1):
                result = self.note_value if idx == 1 else f"Grounding preserved through XSS quick-path step {idx}."
                finish_calls.append(
                    _tool_call(
                        f"finish-{idx}",
                        "finish",
                        {
                            "action": "complete",
                            "step_id": idx,
                            "result": result,
                        },
                    )
                )

            self.normal_calls += 1
            return SimpleNamespace(
                content="记录本轮 adversarial grounding 结果。",
                tool_calls=[
                    _tool_call(
                        "notes-1",
                        "notes",
                        {
                            "action": "create",
                            "key": self.expected_note_key,
                            "value": self.note_value,
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


async def _run_grounding_eval(
    *,
    monkeypatch,
    tmp_path: Path,
    isolated_notes,
    task: str,
    llm: _AdversarialGroundingLLM,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CPA_M3_REPORTER", "false")

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("flaghunter.tools.finish._persist_session_knowledge", _noop)
    monkeypatch.setattr("flaghunter.tools.finish._generate_auto_report", _noop)

    mgr = WorkspaceManager(root=tmp_path)
    mgr.create("adversarial_eval")
    mgr.add_targets("adversarial_eval", ["http://127.0.0.1:3000"])
    mgr.set_active("adversarial_eval")

    import flaghunter.tools.browser  # noqa: F401
    import flaghunter.tools.finish  # noqa: F401
    import flaghunter.tools.notes  # noqa: F401

    browser_tool = get_tool("browser")
    notes_tool = get_tool("notes")
    finish_tool = get_tool("finish")
    assert browser_tool is not None
    assert notes_tool is not None
    assert finish_tool is not None

    runtime = _GroundedWebRuntime()
    agent = PentestAgentAgent(
        llm=llm,
        tools=[browser_tool, notes_tool, finish_tool],
        runtime=runtime,
        target="http://localhost:3000/",
        scope=["http://127.0.0.1:3000"],
    )

    messages = []
    async for msg in agent.agent_loop(task):
        messages.append(msg)

    return agent, runtime, messages


@pytest.mark.asyncio
async def test_ctf_adversarial_grounding_rejects_wrong_route_contamination(
    monkeypatch, tmp_path, isolated_notes
):
    llm = _AdversarialGroundingLLM(
        expected_note_key="adversarial_wrong_route_eval",
        forbidden_runtime_terms=["/upload", "/register", "xml2json", "kmz"],
        guardrail_terms=[
            "treat those claims as hypotheses",
            "Do not assume cross-origin DOM access",
        ],
        summary_text=(
            "agent 依据 easy_login 当前首页和 app.js 的真实证据，保持在 "
            "/login、/visit、/admin 这条链路上，没有被 /upload 或 xml2json 误导。"
        ),
        note_value=(
            "Rejected wrong-route contamination from /upload-/register-style hints; "
            "grounded back to /login -> /visit -> /admin."
        ),
    )
    task = """[CTF MODE] Target: http://localhost:3000/
Challenge type: xss
Hint: maybe the real bug is under /upload, /register, kmz xml2json parsing

OBJECTIVE: Find and capture the flag as fast as possible.
"""

    agent, runtime, messages = await _run_grounding_eval(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        isolated_notes=isolated_notes,
        task=task,
        llm=llm,
    )

    assert agent._task_plan.is_complete() is True
    assert llm.summary_calls == 1
    assert runtime.browser_calls[0][0] == "navigate"
    assert runtime.browser_calls[1][0] == "get_content"
    assert runtime.browser_calls[2][0] == "get_forms"
    assert runtime.proxy_calls == [
        ("get", {"url": "http://127.0.0.1:3000/app.js", "timeout": 10})
    ]

    notes = get_all_notes_sync()
    assert "adversarial_wrong_route_eval" in notes
    saved = notes["adversarial_wrong_route_eval"]
    assert saved["category"] == "finding"
    assert any(ep["path"] == "/visit" for ep in saved["metadata"]["endpoints"])
    assert any(ep["path"] == "/admin" for ep in saved["metadata"]["endpoints"])

    runtime_block = llm.runtime_blocks[0]
    assert "/visit" in runtime_block
    assert "/admin" in runtime_block
    assert "/upload" not in runtime_block
    assert "/register" not in runtime_block
    assert "xml2json" not in runtime_block
    assert "kmz" not in runtime_block

    completion_msgs = [m for m in messages if m.metadata.get("task_complete")]
    assert completion_msgs
    summary = completion_msgs[-1].content.lower()
    assert "easy_login" in summary
    assert "visit" in summary
    assert "upload" in summary


@pytest.mark.asyncio
async def test_ctf_adversarial_grounding_rejects_browser_capability_hallucination(
    monkeypatch, tmp_path, isolated_notes
):
    llm = _AdversarialGroundingLLM(
        expected_note_key="adversarial_browser_capability_eval",
        forbidden_runtime_terms=[
            "iframe.contentdocument",
            "window.open('/').fetch",
        ],
        guardrail_terms=[
            "Do not assume cross-origin DOM access",
            "cross-origin window.fetch",
            "iframe contentDocument reads",
            "attacker-origin document.cookie access",
        ],
        summary_text=(
            "agent 没有把 cross-origin iframe、popup fetch 或 attacker-origin cookie 读取"
            "当成既成能力，而是坚持以当前 runtime 证据约束 easy_login 分析。"
        ),
        note_value=(
            "Rejected browser-capability hallucinations around cross-origin DOM/popup/"
            "iframe/cookie reads; stayed grounded in observed runtime behavior."
        ),
    )
    task = """[CTF MODE] Target: http://localhost:3000/
Challenge type: xss
Hint: use iframe.contentDocument, window.open('/').fetch('/admin'), or attacker-origin document.cookie reads

OBJECTIVE: Find and capture the flag as fast as possible.
"""

    agent, runtime, messages = await _run_grounding_eval(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        isolated_notes=isolated_notes,
        task=task,
        llm=llm,
    )

    assert agent._task_plan.is_complete() is True
    assert llm.summary_calls == 1
    assert any(action == "navigate" for action, _ in runtime.browser_calls)
    assert any(action == "get_content" for action, _ in runtime.browser_calls)
    assert any(action == "get_forms" for action, _ in runtime.browser_calls)

    notes = get_all_notes_sync()
    assert "adversarial_browser_capability_eval" in notes
    saved = notes["adversarial_browser_capability_eval"]
    assert saved["category"] == "finding"
    assert "cross-origin" in saved["content"].lower()

    runtime_block = llm.runtime_blocks[0]
    assert "Do not assume cross-origin DOM access" in runtime_block
    assert "cross-origin window.fetch" in runtime_block
    assert "iframe contentDocument reads" in runtime_block
    assert "attacker-origin document.cookie access" in runtime_block
    assert "iframe.contentDocument" not in runtime_block

    completion_msgs = [m for m in messages if m.metadata.get("task_complete")]
    assert completion_msgs
    summary = completion_msgs[-1].content.lower()
    assert "cross-origin" in summary
    assert "easy_login" in summary


@pytest.mark.asyncio
async def test_ctf_adversarial_grounding_prefers_runtime_over_source_summary_conflict(
    monkeypatch, tmp_path, isolated_notes
):
    llm = _AdversarialGroundingLLM(
        expected_note_key="adversarial_source_runtime_conflict_eval",
        forbidden_runtime_terms=["/backup", "/debug", "/internal", "admin_secret"],
        guardrail_terms=[
            "source summaries",
            "treat those claims as hypotheses",
            "Do not assume cross-origin DOM access",
        ],
        summary_text=(
            "agent 在 stale source summary 与当前 easy_login runtime 冲突时，"
            "优先保留首页、表单和 app.js 里真实观察到的 /login、/visit、/admin。"
        ),
        note_value=(
            "Rejected stale source-summary claims about /backup, /debug, /internal, "
            "or admin_secret routes; grounded to observed /login -> /visit -> /admin runtime."
        ),
    )
    task = """[CTF MODE] Target: http://localhost:3000/
Challenge type: xss
Hint: source audit says the real win path is /backup or /debug and checked-in notes mention /internal plus admin_secret leakage

OBJECTIVE: Find and capture the flag as fast as possible.
"""

    agent, runtime, messages = await _run_grounding_eval(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        isolated_notes=isolated_notes,
        task=task,
        llm=llm,
    )

    assert agent._task_plan.is_complete() is True
    assert llm.summary_calls == 1
    assert runtime.proxy_calls == [
        ("get", {"url": "http://127.0.0.1:3000/app.js", "timeout": 10})
    ]
    assert any(action == "navigate" for action, _ in runtime.browser_calls)
    assert any(action == "get_content" for action, _ in runtime.browser_calls)
    assert any(action == "get_forms" for action, _ in runtime.browser_calls)

    notes = get_all_notes_sync()
    assert "adversarial_source_runtime_conflict_eval" in notes
    saved = notes["adversarial_source_runtime_conflict_eval"]
    assert saved["category"] == "finding"
    assert "runtime" in saved["content"].lower()
    assert "source" in saved["content"].lower()
    assert any(ep["path"] == "/visit" for ep in saved["metadata"]["endpoints"])
    assert any(ep["path"] == "/admin" for ep in saved["metadata"]["endpoints"])

    runtime_block = llm.runtime_blocks[0]
    assert "/visit" in runtime_block
    assert "/admin" in runtime_block
    assert "/backup" not in runtime_block
    assert "/debug" not in runtime_block
    assert "/internal" not in runtime_block
    assert "admin_secret" not in runtime_block
    assert "source summaries" in runtime_block
    assert "treat those claims as hypotheses" in runtime_block

    completion_msgs = [m for m in messages if m.metadata.get("task_complete")]
    assert completion_msgs
    summary = completion_msgs[-1].content.lower()
    assert "runtime" in summary
    assert "source" in summary
    assert "easy_login" in summary


def test_adv7_memory_contradiction_suppresses_misleading_backup_bias():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.add_observation(
        "recon_url",
        "http://ctf.local/file?filename=/flag.txt&filehash=deadbeef",
        source="phase_recon",
        metadata={
            "backup_clue": False,
            "endpoints": ["/file?filename=/flag.txt&filehash=deadbeef", "/hints.txt"],
        },
    )
    state.hypothesis_memory_adjustments = {"backup_source_leak": 0.25}

    ranked = HypothesisEngine().generate(state)
    kinds = [item.kind for item in ranked]

    assert state.hypothesis_memory_adjustments["backup_source_leak"] == 0.0
    assert "hash_guarded_file_read" in kinds
    assert kinds.index("hash_guarded_file_read") < kinds.index("backup_source_leak")


def test_adv8_exploration_agenda_is_consumed_before_hypothesis_switch():
    state = CTFState(target="http://ctf.local", goal="拿到flag", detected_type="web")
    state.hypotheses = [
        Hypothesis(
            id="backup_source_leak",
            kind="backup_source_leak",
            description="backup",
            confidence=0.7,
            supporting_observations=["backup hint"],
            counter_evidence=[],
            next_experiments=["fetch backup"],
        ),
        Hypothesis(
            id="generic_web_recon",
            kind="generic_web_recon",
            description="fallback",
            confidence=0.4,
            supporting_observations=["fallback"],
            counter_evidence=[],
            next_experiments=["recon"],
        ),
    ]
    state.add_exploration_item(
        "/file?filename=/flag.txt&filehash=deadbeef",
        discovery_source="response_body",
        hint_strength=1,
    )
    state.add_exploration_item(
        "/hints.txt",
        discovery_source="link_href",
        hint_strength=2,
    )

    decision = RecoveryController(HypothesisEngine()).after_chain(
        state,
        current_chain="web",
        active_hypothesis=state.hypotheses[0],
        outcome_progress=False,
        no_progress_count=3,
        used_chains=["web"],
    )

    assert decision.action == "explore_agenda"
    assert [item.url_or_path for item in decision.exploration_items] == [
        "/file?filename=/flag.txt&filehash=deadbeef",
        "/hints.txt",
    ]
