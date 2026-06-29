"""Phase 2B: the orchestrator folds M5 shared-blackboard context into its prompt.

Verifies the *wiring* (cached ``_swarm_context`` → system prompt), independent
of M5 being enabled — the read itself is covered in ``test_ctf_swarm_bridge.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

from flaghunter.agents.crew.orchestrator import CrewOrchestrator


def _make_orchestrator() -> CrewOrchestrator:
    runtime = SimpleNamespace(
        environment=SimpleNamespace(
            os="linux",
            os_version="6.0",
            architecture="x86_64",
            available_tools=[],
        )
    )
    return CrewOrchestrator(llm=object(), tools=[], runtime=runtime, target="http://t")


def test_swarm_context_absent_by_default():
    orch = _make_orchestrator()
    assert orch._swarm_context == ""
    prompt = orch._get_system_prompt()
    assert "Swarm Blackboard (peer agents)" not in prompt


def test_swarm_context_folds_into_system_prompt():
    orch = _make_orchestrator()
    orch._swarm_context = (
        "### Peer-agent findings (shared blackboard)\n- [critical] rce here — http://t"
    )
    prompt = orch._get_system_prompt()
    assert "## Swarm Blackboard (peer agents)" in prompt
    assert "rce here" in prompt
