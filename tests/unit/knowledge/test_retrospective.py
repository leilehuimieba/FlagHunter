"""Tests for retrospective knowledge helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pentestagent.agents.pa_agent.pa_agent import PentestAgentAgent
from pentestagent.knowledge import retrospective as retro


class _DummyRuntime:
    def __init__(self):
        self.environment = SimpleNamespace()
        self.plan = None


class _DummyLLM:
    async def generate(self, *args, **kwargs):
        raise AssertionError("llm.generate should not be called in this test")


@pytest.fixture
def retro_paths(tmp_path, monkeypatch):
    retro_json = tmp_path / "pentestagent" / "knowledge" / "retrospective.json"
    knowledge_base = tmp_path / "knowledge"

    monkeypatch.setattr(retro, "RETRO_PATH", retro_json)
    monkeypatch.setattr(
        retro,
        "resolve_knowledge_paths",
        lambda: {"base": knowledge_base},
    )
    yield {
        "retro_json": retro_json,
        "knowledge_base": knowledge_base,
        "retro_root_md": knowledge_base / "retrospective_notes.md",
        "retro_md": knowledge_base / "retrospective_export" / "retrospective_notes.md",
    }


def test_add_entry_persists(retro_paths):
    retro.add_retrospective_entry(
        category="tool_failure",
        description="nuclei missing",
        context={"tool": "nuclei"},
        suggestion="install nuclei",
    )

    entries = retro.load_retrospective()

    assert len(entries) == 1
    assert entries[0]["description"] == "nuclei missing"


def test_get_unresolved_filters(retro_paths):
    retro.add_retrospective_entry(
        category="tool_failure",
        description="first",
        context={},
    )
    retro.add_retrospective_entry(
        category="plan_inefficient",
        description="second",
        context={},
    )
    retro.mark_resolved(1)

    unresolved = retro.get_unresolved_entries()

    assert len(unresolved) == 1
    assert unresolved[0]["id"] == 2


def test_mark_resolved(retro_paths):
    retro.add_retrospective_entry(
        category="other",
        description="needs fix",
        context={},
    )

    retro.mark_resolved(1)

    entries = retro.load_retrospective()
    assert entries[0]["resolved"] is True


def test_export_markdown_created(retro_paths):
    retro.add_retrospective_entry(
        category="success_path",
        description="flag found via sqlmap",
        context={"tool": "sqlmap"},
    )

    root_md_path = retro_paths["retro_root_md"]
    md_path = retro_paths["retro_md"]
    assert root_md_path.exists()
    assert md_path.exists()
    content = md_path.read_text(encoding="utf-8")
    assert "flag found via sqlmap" in content


@pytest.mark.asyncio
async def test_consecutive_fails_triggers(monkeypatch):
    calls: list[dict] = []

    monkeypatch.setattr(
        "pentestagent.knowledge.retrospective.add_retrospective_entry",
        lambda **kwargs: calls.append(kwargs),
    )

    runtime = _DummyRuntime()
    agent = PentestAgentAgent(
        llm=_DummyLLM(),
        tools=[SimpleNamespace(name="sqlmap", enabled=True)],
        runtime=runtime,
        target="http://example.local/",
        scope=[],
    )
    agent._task_plan.original_request = (
        "[CTF MODE] Target: http://example.local/\n"
        "Challenge type: sqli\n"
        "Hint: none\n"
    )

    await agent._handle_failed_plan_step(SimpleNamespace(id=1, description="step one"))
    await agent._handle_failed_plan_step(SimpleNamespace(id=2, description="step two"))
    await agent._handle_failed_plan_step(
        SimpleNamespace(id=3, description="step three")
    )

    assert any(call["category"] == "plan_inefficient" for call in calls)
