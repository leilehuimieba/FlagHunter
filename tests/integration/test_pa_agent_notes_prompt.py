"""Integration tests for PentestAgentAgent notes prompt filtering."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.pa_agent import PentestAgentAgent
from flaghunter.tools.notes import set_notes_file
import flaghunter.tools.notes as notes_module


class _StubLLM:
    async def generate(self, *args, **kwargs):
        return SimpleNamespace(content="", tool_calls=None, usage={"total_tokens": 0})


class _StubRuntime:
    def __init__(self):
        self.environment = SimpleNamespace(
            os="Windows",
            os_version="test",
            architecture="x86_64",
            shell="powershell",
            available_tools=[],
        )
        self.plan = None


@pytest.fixture(autouse=True)
def isolated_notes(tmp_path):
    notes_file = tmp_path / "notes.json"
    set_notes_file(notes_file)
    notes_module._notes.clear()
    notes_module._loaded_notes_file = None
    yield notes_file
    notes_module._notes.clear()
    notes_module._custom_notes_file = None
    notes_module._loaded_notes_file = None


async def _call(action: str, **kwargs) -> str:
    args = {"action": action, **kwargs}
    return await notes_module.notes(args, runtime=None)


def _make_agent() -> PentestAgentAgent:
    return PentestAgentAgent(
        llm=_StubLLM(),
        tools=[],
        runtime=_StubRuntime(),
        target="127.0.0.1",
        scope=["127.0.0.1/32"],
    )


@pytest.mark.asyncio
async def test_system_prompt_filters_low_confidence_info_and_folds_non_injectable():
    await _call("create", key="keep_finding", value="Open SSH on port 22", category="finding", confidence="high", target="127.0.0.1", port="22")
    await _call("create", key="drop_info", value="maybe useless banner", category="info", confidence="low")
    await _call("create", key="folded_note", value="POST param id is not injectable after manual checks", category="finding", confidence="medium", target="127.0.0.1", port="80")

    prompt = _make_agent().get_system_prompt("agent")

    assert "keep_finding: Open SSH on port 22" in prompt
    assert "drop_info" not in prompt
    assert "maybe useless banner" not in prompt
    assert "- folded_note" in prompt
    assert "not injectable after manual checks" not in prompt


@pytest.mark.asyncio
async def test_delete_and_archive_remove_notes_from_system_prompt():
    await _call("create", key="delete_me", value="temporary note", category="finding", confidence="high", target="127.0.0.1", port="8080")
    await _call("create", key="archive_me", value="old confirmed issue", category="finding", confidence="high", target="127.0.0.1", port="443")

    before_prompt = _make_agent().get_system_prompt("agent")
    assert "delete_me: temporary note" in before_prompt
    assert "archive_me: old confirmed issue" in before_prompt

    await _call("delete", key="delete_me")
    await _call("archive", key="archive_me")

    after_prompt = _make_agent().get_system_prompt("agent")
    assert "delete_me" not in after_prompt
    assert "archive_me" not in after_prompt
