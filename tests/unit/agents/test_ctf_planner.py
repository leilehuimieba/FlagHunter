from __future__ import annotations

from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.ctf_planner import (
    CTF_TOOL_CHAINS,
    build_ctf_convergence_hint,
    build_ctf_system_prompt,
    detect_type,
    get_ctf_quick_path,
)
from flaghunter.agents.pa_agent.pa_agent import FlagHunterAgent
from flaghunter.harness.artifact_registry import ArtifactRegistry


class _NoGenerateLLM:
    async def generate(self, *args, **kwargs):
        raise AssertionError("llm.generate should not be called in CTF mode")


class _DummyRuntime:
    def __init__(self):
        self.environment = SimpleNamespace()
        self.plan = None


class _RuntimeWithGroundTruth(_DummyRuntime):
    async def browser_action(self, action, **kwargs):
        if action == "navigate":
            return {
                "url": "http://127.0.0.1:3000/",
                "requested_url": kwargs.get("url"),
                "title": "easy_login Dashboard",
            }
        if action == "get_content":
            return {
                "content": "Login Portal Playground /visit /admin",
                "html": """
                <html><head><title>easy_login Dashboard</title><script src="/app.js"></script></head>
                <body>
                  <form action="/login" method="post">
                    <input name="username" />
                    <input name="password" />
                  </form>
                </body></html>
                """,
            }
        if action == "get_forms":
            return {
                "forms": [
                    {
                        "action": "http://127.0.0.1:3000/login",
                        "method": "post",
                        "inputs": [
                            {"name": "username"},
                            {"name": "password"},
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
        raise AssertionError(f"unexpected browser action: {action}")

    async def proxy_action(self, action, **kwargs):
        assert action == "get"
        return {"status_code": 200, "body": "fetch('/visit'); fetch('/admin');"}


def test_get_quick_path_sqli():
    steps = get_ctf_quick_path("sqli")
    joined = " ".join(steps)
    assert "确认注入点" in joined
    assert "黑名单" in joined
    assert "sqlmap" in joined.lower()


def test_get_quick_path_unknown():
    assert get_ctf_quick_path("unknown") == get_ctf_quick_path("web")


def test_build_system_prompt_hint():
    prompt = build_ctf_system_prompt("web", "admin page")
    assert "Hint from challenge: admin page" in prompt


def test_build_system_prompt_no_hint():
    prompt = build_ctf_system_prompt("web", "")
    assert "Hint from challenge" not in prompt


def test_build_ctf_convergence_hint_for_bot_xss_shape():
    hint = build_ctf_convergence_hint(
        "xss",
        endpoints=["/login", "/visit", "/admin"],
        forms=[
            {
                "action": "http://127.0.0.1:3000/login",
                "method": "post",
                "inputs": [
                    {"name": "username"},
                    {"name": "password"},
                    {"name": "bio"},
                ],
            }
        ],
        cookie_string="sid=guest-preview; theme=light",
        cookies=[{"name": "sid", "value": "guest-preview"}],
        evidence_blobs=["document.cookie", "fetch('/visit'); fetch('/admin');"],
    )

    assert "Likely bot-XSS / sid-theft convergence" in hint
    assert "payload -> /visit -> collector -> sid -> /admin" in hint
    assert "local collector" in hint
    assert "retry once with a second minimal same-origin variant" in hint
    assert "which variant failed and which one worked" in hint
    assert "Do not assume cross-origin iframe" in hint


def test_build_ctf_convergence_hint_requires_runtime_shape():
    hint = build_ctf_convergence_hint(
        "xss",
        endpoints=["/login", "/admin"],
        forms=[
            {
                "action": "http://127.0.0.1:3000/login",
                "method": "post",
                "inputs": [{"name": "username"}, {"name": "password"}],
            }
        ],
        cookie_string="sid=guest-preview",
    )
    assert hint == ""


@pytest.mark.parametrize(
    ("page_source", "url", "expected"),
    [
        ('<form><input name="username"><input name="password"></form><a href="/visit">visit</a>', "http://ctf.local/", "xss"),
        ('<form><input type="file" name="file"></form>', "http://ctf.local/upload", "upload"),
        ("read me", "http://ctf.local/view?file=index.php", "lfi"),
        ("fetcher", "http://ctf.local/proxy?url=http://127.0.0.1/", "ssrf"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoidXNlciJ9.sig", "http://ctf.local/api/me", "jwt"),
        ('<form><input name="username"><input name="password"></form>', "http://ctf.local/login", "sqli"),
        ('<form action="index.php" method="post"><img src="static/piapiapia.gif"><input name="username"><input name="password"></form>', "http://ctf.local/login", "sqli"),
        ('<html><body><h1>因为我有良好的备份网站习惯</h1><script src="index.js"></script></body></html>', "http://ctf.local/", "web"),
    ],
)
def test_detect_type(page_source, url, expected):
    assert detect_type(page_source, url) == expected


def test_ctf_tool_chains_have_payloads():
    for vuln_type in ("xss", "sqli", "lfi", "cmdi", "ssrf", "upload"):
        chain = CTF_TOOL_CHAINS[vuln_type]
        assert chain["tools"]
        assert chain["payloads"]


@pytest.mark.asyncio
async def test_pa_agent_ctf_mode_skips_llm(monkeypatch):
    async def _unexpected_generate_plan(**kwargs):
        raise AssertionError("generate_plan should not be called in CTF mode")

    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.pa_agent.generate_plan",
        _unexpected_generate_plan,
    )

    runtime = _DummyRuntime()
    agent = FlagHunterAgent(
        llm=_NoGenerateLLM(),
        tools=[SimpleNamespace(name="sqlmap", enabled=True)],
        runtime=runtime,
        target="http://dvwa.local/",
        scope=[],
    )
    task = """[CTF MODE] Target: http://dvwa.local/
Challenge type: sqli
Hint: login bypass

OBJECTIVE: Find and capture the flag as fast as possible.
"""
    agent.conversation_history.append(SimpleNamespace(role="user", content=task))

    plan_msg = await agent._auto_generate_plan()

    assert plan_msg is None
    assert runtime.plan is agent._task_plan
    assert runtime.plan.original_request == task
    assert runtime.plan.steps
    assert runtime.plan.steps[0].description == get_ctf_quick_path("sqli")[0]
    assert "CTF Quick-Path Mode: SQLI" in agent.get_system_prompt()


@pytest.mark.asyncio
async def test_pa_agent_ctf_mode_adds_runtime_ground_truth(monkeypatch):
    captured_note = {}

    async def _fake_notes(arguments, runtime=None):
        captured_note.update(arguments)
        return "ok"

    monkeypatch.setattr("flaghunter.tools.notes.notes", _fake_notes)

    runtime = _RuntimeWithGroundTruth()
    agent = FlagHunterAgent(
        llm=_NoGenerateLLM(),
        tools=[SimpleNamespace(name="browser", enabled=True)],
        runtime=runtime,
        target="http://localhost:3000/",
        scope=[],
    )
    task = """[CTF MODE] Target: http://localhost:3000/
Challenge type: xss
Hint: steal sid

OBJECTIVE: Find and capture the flag as fast as possible.
"""
    agent.conversation_history.append(SimpleNamespace(role="user", content=task))

    plan_msg = await agent._auto_generate_plan()

    assert plan_msg is None
    prompt = agent.get_system_prompt()
    assert "## Runtime Ground Truth" in prompt
    assert "/visit" in prompt
    assert "/admin" in prompt
    assert "Observed cookie names: sid, theme" in prompt
    assert "Likely bot-XSS / sid-theft convergence" in prompt
    assert "payload -> /visit -> collector -> sid -> /admin" in prompt
    assert "retry once with a second minimal same-origin variant" in prompt
    assert "treat those claims as hypotheses" in prompt
    assert "Do not assume cross-origin DOM access" in prompt
    assert captured_note["category"] == "finding"
    assert "runtime_fingerprint" in captured_note["key"]


@pytest.mark.asyncio
async def test_pa_agent_ctf_mode_runtime_ground_truth_isolated_from_misleading_hint(
    monkeypatch,
):
    async def _fake_notes(arguments, runtime=None):
        return "ok"

    monkeypatch.setattr("flaghunter.tools.notes.notes", _fake_notes)

    runtime = _RuntimeWithGroundTruth()
    agent = FlagHunterAgent(
        llm=_NoGenerateLLM(),
        tools=[SimpleNamespace(name="browser", enabled=True)],
        runtime=runtime,
        target="http://localhost:3000/",
        scope=[],
    )
    task = """[CTF MODE] Target: http://localhost:3000/
Challenge type: xss
Hint: maybe /upload kmz xml2json or cross-origin window.open fetch

OBJECTIVE: Find and capture the flag as fast as possible.
"""
    agent.conversation_history.append(SimpleNamespace(role="user", content=task))

    plan_msg = await agent._auto_generate_plan()

    assert plan_msg is None
    prompt = agent.get_system_prompt()
    runtime_block = prompt.split("## Runtime Ground Truth", 1)[1]
    assert "/visit" in runtime_block
    assert "/admin" in runtime_block
    assert "/upload" not in runtime_block
    assert "Do not assume cross-origin DOM access" in runtime_block


@pytest.mark.asyncio
async def test_pa_agent_ctf_mode_runtime_context_includes_local_challenge_ground_truth(
    monkeypatch,
    tmp_path,
):
    async def _fake_notes(arguments, runtime=None):
        return "ok"

    monkeypatch.setattr("flaghunter.tools.notes.notes", _fake_notes)

    run_id = "run-ctf-local-summary-context"
    ArtifactRegistry(tmp_path / "loot" / "artifact_registry").register_artifact(
        run_id=run_id,
        kind="local_challenge_root_summary",
        title="easy_login summary",
        path=r"D:\webstudy\CTF\easy_login",
        location=r"D:\webstudy\CTF\easy_login",
        producer="local_challenge_context",
        metadata={
            "kind": "challenge_root_summary",
            "root_name": "easy_login",
            "has_compose": True,
            "key_files": ["README.md", "app.py", "requirements.txt"],
            "detected_stack": ["python"],
            "file_count": 5,
        },
    )

    runtime = _RuntimeWithGroundTruth()
    agent = FlagHunterAgent(
        llm=_NoGenerateLLM(),
        tools=[SimpleNamespace(name="browser", enabled=True)],
        runtime=runtime,
        target="http://localhost:3000/",
        scope=[],
    )
    agent.run_id = run_id
    agent.project_root = tmp_path

    task = """[CTF MODE] Target: http://localhost:3000/
Challenge type: xss
Hint: steal sid

OBJECTIVE: Find and capture the flag as fast as possible.
"""
    agent.conversation_history.append(SimpleNamespace(role="user", content=task))

    plan_msg = await agent._auto_generate_plan()

    assert plan_msg is None
    prompt = agent.get_system_prompt()
    assert "## Runtime Ground Truth" in prompt
    assert "## Local Challenge Ground Truth" in prompt
    assert "- local_root=easy_login" in prompt
    assert "- local_stack=python" in prompt
    assert "- local_key_files=README.md, app.py, requirements.txt" in prompt
    assert "- local_has_compose=true" in prompt


@pytest.mark.asyncio
async def test_pa_agent_ctf_mode_adds_local_challenge_strategy_bias_for_python_compose(
    tmp_path,
):
    run_id = "run-ctf-local-strategy-python"
    ArtifactRegistry(tmp_path / "loot" / "artifact_registry").register_artifact(
        run_id=run_id,
        kind="local_challenge_root_summary",
        title="easy_login summary",
        path=r"D:\webstudy\CTF\easy_login",
        location=r"D:\webstudy\CTF\easy_login",
        producer="local_challenge_context",
        metadata={
            "kind": "challenge_root_summary",
            "root_name": "easy_login",
            "has_compose": True,
            "key_files": ["README.md", "app.py", "requirements.txt"],
            "detected_stack": ["python"],
            "file_count": 5,
        },
    )

    runtime = _DummyRuntime()
    agent = FlagHunterAgent(
        llm=_NoGenerateLLM(),
        tools=[SimpleNamespace(name="browser", enabled=True)],
        runtime=runtime,
        target="http://localhost:3000/",
        scope=[],
    )
    agent.run_id = run_id
    agent.project_root = tmp_path

    task = """[CTF MODE] Target: http://localhost:3000/
Challenge type: web
Hint: local challenge archive

OBJECTIVE: Find and capture the flag as fast as possible.
"""
    agent.conversation_history.append(SimpleNamespace(role="user", content=task))

    await agent._auto_generate_plan()

    prompt = agent.get_system_prompt()
    assert "## Local Challenge Strategy Bias" in prompt
    assert "Prefer local compose logs" in prompt
    assert "Prioritize README.md, app.py, requirements.txt" in prompt


@pytest.mark.asyncio
async def test_pa_agent_ctf_mode_adds_local_challenge_strategy_bias_for_php(
    tmp_path,
):
    run_id = "run-ctf-local-strategy-php"
    ArtifactRegistry(tmp_path / "loot" / "artifact_registry").register_artifact(
        run_id=run_id,
        kind="local_challenge_root_summary",
        title="php challenge summary",
        path=r"D:\webstudy\CTF\php_login",
        location=r"D:\webstudy\CTF\php_login",
        producer="local_challenge_context",
        metadata={
            "kind": "challenge_root_summary",
            "root_name": "php_login",
            "has_compose": False,
            "key_files": ["README.md", "index.php"],
            "detected_stack": ["php"],
            "file_count": 2,
        },
    )

    runtime = _DummyRuntime()
    agent = FlagHunterAgent(
        llm=_NoGenerateLLM(),
        tools=[SimpleNamespace(name="browser", enabled=True)],
        runtime=runtime,
        target="http://localhost:8080/",
        scope=[],
    )
    agent.run_id = run_id
    agent.project_root = tmp_path

    task = """[CTF MODE] Target: http://localhost:8080/
Challenge type: web
Hint: php source available

OBJECTIVE: Find and capture the flag as fast as possible.
"""
    agent.conversation_history.append(SimpleNamespace(role="user", content=task))

    await agent._auto_generate_plan()

    prompt = agent.get_system_prompt()
    assert "## Local Challenge Strategy Bias" in prompt
    assert "Prioritize index.php" in prompt


@pytest.mark.asyncio
async def test_pa_agent_ctf_mode_adds_local_challenge_strategy_bias_for_node(
    tmp_path,
):
    run_id = "run-ctf-local-strategy-node"
    ArtifactRegistry(tmp_path / "loot" / "artifact_registry").register_artifact(
        run_id=run_id,
        kind="local_challenge_root_summary",
        title="node challenge summary",
        path=r"D:\webstudy\CTF\node_login",
        location=r"D:\webstudy\CTF\node_login",
        producer="local_challenge_context",
        metadata={
            "kind": "challenge_root_summary",
            "root_name": "node_login",
            "has_compose": False,
            "key_files": ["README.md", "package.json"],
            "detected_stack": ["node"],
            "file_count": 2,
        },
    )

    runtime = _DummyRuntime()
    agent = FlagHunterAgent(
        llm=_NoGenerateLLM(),
        tools=[SimpleNamespace(name="browser", enabled=True)],
        runtime=runtime,
        target="http://localhost:4000/",
        scope=[],
    )
    agent.run_id = run_id
    agent.project_root = tmp_path

    task = """[CTF MODE] Target: http://localhost:4000/
Challenge type: web
Hint: node service

OBJECTIVE: Find and capture the flag as fast as possible.
"""
    agent.conversation_history.append(SimpleNamespace(role="user", content=task))

    await agent._auto_generate_plan()

    prompt = agent.get_system_prompt()
    assert "## Local Challenge Strategy Bias" in prompt
    assert "Prioritize package.json" in prompt


@pytest.mark.asyncio
async def test_pa_agent_ctf_mode_surfaces_local_challenge_entry_points(
    tmp_path,
):
    run_id = "run-ctf-local-entry-points"
    registry = ArtifactRegistry(tmp_path / "loot" / "artifact_registry")
    registry.register_artifact(
        run_id=run_id,
        kind="local_challenge_root",
        title="easy_login",
        path=r"D:\webstudy\CTF\easy_login",
        location=r"D:\webstudy\CTF\easy_login",
        producer="local_challenge_context",
        metadata={"kind": "challenge_root"},
    )
    registry.register_artifact(
        run_id=run_id,
        kind="local_challenge_compose_file",
        title="docker-compose.yml",
        path=r"D:\webstudy\CTF\easy_login\docker-compose.yml",
        location=r"D:\webstudy\CTF\easy_login\docker-compose.yml",
        producer="local_challenge_context",
        metadata={"kind": "challenge_compose_file"},
    )
    registry.register_artifact(
        run_id=run_id,
        kind="local_challenge_key_file",
        title="README.md",
        path=r"D:\webstudy\CTF\easy_login\README.md",
        location=r"D:\webstudy\CTF\easy_login\README.md",
        producer="local_challenge_context",
        metadata={"kind": "challenge_key_file"},
    )
    registry.register_artifact(
        run_id=run_id,
        kind="local_challenge_key_file",
        title="app.py",
        path=r"D:\webstudy\CTF\easy_login\app.py",
        location=r"D:\webstudy\CTF\easy_login\app.py",
        producer="local_challenge_context",
        metadata={"kind": "challenge_key_file"},
    )

    runtime = _DummyRuntime()
    agent = FlagHunterAgent(
        llm=_NoGenerateLLM(),
        tools=[SimpleNamespace(name="browser", enabled=True)],
        runtime=runtime,
        target="http://localhost:3000/",
        scope=[],
    )
    agent.run_id = run_id
    agent.project_root = tmp_path

    task = """[CTF MODE] Target: http://localhost:3000/
Challenge type: web
Hint: local files available

OBJECTIVE: Find and capture the flag as fast as possible.
"""
    agent.conversation_history.append(SimpleNamespace(role="user", content=task))

    await agent._auto_generate_plan()

    prompt = agent.get_system_prompt()
    assert "## Local Challenge Entry Points" in prompt
    assert r"D:\webstudy\CTF\easy_login" in prompt
    assert r"D:\webstudy\CTF\easy_login\docker-compose.yml" in prompt
    assert r"D:\webstudy\CTF\easy_login\README.md" in prompt
    assert r"D:\webstudy\CTF\easy_login\app.py" in prompt


@pytest.mark.asyncio
async def test_pa_agent_ctf_mode_prepends_local_challenge_plan_steps_for_python_compose(
    tmp_path,
):
    run_id = "run-ctf-local-plan-python"
    registry = ArtifactRegistry(tmp_path / "loot" / "artifact_registry")
    registry.register_artifact(
        run_id=run_id,
        kind="local_challenge_compose_file",
        title="docker-compose.yml",
        path=r"D:\webstudy\CTF\easy_login\docker-compose.yml",
        location=r"D:\webstudy\CTF\easy_login\docker-compose.yml",
        producer="local_challenge_context",
        metadata={"kind": "challenge_compose_file"},
    )
    registry.register_artifact(
        run_id=run_id,
        kind="local_challenge_key_file",
        title="README.md",
        path=r"D:\webstudy\CTF\easy_login\README.md",
        location=r"D:\webstudy\CTF\easy_login\README.md",
        producer="local_challenge_context",
        metadata={"kind": "challenge_key_file"},
    )
    registry.register_artifact(
        run_id=run_id,
        kind="local_challenge_key_file",
        title="app.py",
        path=r"D:\webstudy\CTF\easy_login\app.py",
        location=r"D:\webstudy\CTF\easy_login\app.py",
        producer="local_challenge_context",
        metadata={"kind": "challenge_key_file"},
    )
    registry.register_artifact(
        run_id=run_id,
        kind="local_challenge_key_file",
        title="requirements.txt",
        path=r"D:\webstudy\CTF\easy_login\requirements.txt",
        location=r"D:\webstudy\CTF\easy_login\requirements.txt",
        producer="local_challenge_context",
        metadata={"kind": "challenge_key_file"},
    )

    runtime = _DummyRuntime()
    agent = FlagHunterAgent(
        llm=_NoGenerateLLM(),
        tools=[SimpleNamespace(name="browser", enabled=True)],
        runtime=runtime,
        target="http://localhost:3000/",
        scope=[],
    )
    agent.run_id = run_id
    agent.project_root = tmp_path

    task = """[CTF MODE] Target: http://localhost:3000/
Challenge type: web
Hint: local files available

OBJECTIVE: Find and capture the flag as fast as possible.
"""
    agent.conversation_history.append(SimpleNamespace(role="user", content=task))

    await agent._auto_generate_plan()

    step_descriptions = [step.description for step in agent._task_plan.steps[:4]]
    assert r"README.md" in step_descriptions[0]
    assert r"docker-compose.yml" in step_descriptions[1]
    assert r"app.py" in step_descriptions[2]
    assert get_ctf_quick_path("web")[0] in step_descriptions[3]


@pytest.mark.asyncio
async def test_pa_agent_ctf_mode_prepends_local_challenge_plan_steps_for_php(
    tmp_path,
):
    run_id = "run-ctf-local-plan-php"
    registry = ArtifactRegistry(tmp_path / "loot" / "artifact_registry")
    registry.register_artifact(
        run_id=run_id,
        kind="local_challenge_key_file",
        title="index.php",
        path=r"D:\webstudy\CTF\php_login\index.php",
        location=r"D:\webstudy\CTF\php_login\index.php",
        producer="local_challenge_context",
        metadata={"kind": "challenge_key_file"},
    )

    runtime = _DummyRuntime()
    agent = FlagHunterAgent(
        llm=_NoGenerateLLM(),
        tools=[SimpleNamespace(name="browser", enabled=True)],
        runtime=runtime,
        target="http://localhost:8080/",
        scope=[],
    )
    agent.run_id = run_id
    agent.project_root = tmp_path

    task = """[CTF MODE] Target: http://localhost:8080/
Challenge type: web
Hint: php source available

OBJECTIVE: Find and capture the flag as fast as possible.
"""
    agent.conversation_history.append(SimpleNamespace(role="user", content=task))

    await agent._auto_generate_plan()

    step_descriptions = [step.description for step in agent._task_plan.steps[:2]]
    assert r"index.php" in step_descriptions[0]
    assert get_ctf_quick_path("web")[0] in step_descriptions[1]
