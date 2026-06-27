"""Unit tests for the KnowledgeMemory front door (关节C).

The facade is a coordinator, not a store: every method must delegate to the
underlying canonical store/sink and never persist a second copy. These tests
pin each delegation and the graceful-degrade behavior the prompt path relies on.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from flaghunter.agents.pa_agent.memory_facade import KnowledgeMemory


def test_from_agent_pulls_injected_deps():
    engine = object()
    agent = SimpleNamespace(rag_engine=engine, project_root="/tmp/proj")
    km = KnowledgeMemory.from_agent(agent)
    assert km._rag_engine is engine
    assert km._project_root == Path("/tmp/proj")


def test_from_agent_handles_missing_deps():
    km = KnowledgeMemory.from_agent(SimpleNamespace())
    assert km._rag_engine is None
    assert km._project_root is None


def test_project_context_delegates_to_project_memory(monkeypatch):
    captured = {}

    class FakePM:
        def get_context_for_prompt(self, target="", phase=""):
            captured["target"] = target
            captured["phase"] = phase
            return "PROJECT-BLOCK"

    monkeypatch.setattr(
        "flaghunter.knowledge.project_memory.ProjectMemory", FakePM
    )
    km = KnowledgeMemory()
    assert km.project_context(target="t", phase="recon") == "PROJECT-BLOCK"
    assert captured == {"target": "t", "phase": "recon"}


def test_project_context_swallows_errors(monkeypatch):
    class Boom:
        def __init__(self):
            raise RuntimeError("nope")

    monkeypatch.setattr("flaghunter.knowledge.project_memory.ProjectMemory", Boom)
    assert KnowledgeMemory().project_context() == ""


def test_rag_search_without_engine_returns_empty():
    assert KnowledgeMemory(rag_engine=None).rag_search("q") == []


def test_rag_search_empty_query_returns_empty():
    engine = SimpleNamespace(search=lambda q: ["x"])
    assert KnowledgeMemory(rag_engine=engine).rag_search("") == []


def test_rag_search_delegates_to_engine():
    engine = SimpleNamespace(search=lambda q: [f"hit:{q}"])
    km = KnowledgeMemory(rag_engine=engine)
    assert km.rag_search("sqli") == ["hit:sqli"]
    # search_knowledge is the front-door alias for the same retrieval.
    assert km.search_knowledge("sqli") == ["hit:sqli"]


def test_rag_search_none_result_becomes_empty():
    engine = SimpleNamespace(search=lambda q: None)
    assert KnowledgeMemory(rag_engine=engine).rag_search("q") == []


def test_session_run_context_requires_run_id_and_root():
    assert KnowledgeMemory(project_root=None).session_run_context("r1") == {}
    assert KnowledgeMemory(project_root=Path("/x")).session_run_context("") == {}


def test_session_run_context_delegates(monkeypatch):
    seen = {}

    class FakeView:
        def __init__(self, *, ledger_root, artifact_root, checkpoint_root):
            seen["ledger_root"] = ledger_root

        def build_run_context(self, run_id, event_limit, artifact_limit):
            seen["run_id"] = run_id
            seen["limits"] = (event_limit, artifact_limit)
            return {"recentEvents": [{"type": "tool"}]}

    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.session_context.SessionContextView", FakeView
    )
    km = KnowledgeMemory(project_root=Path("/proj"))
    out = km.session_run_context("run-9", event_limit=3, artifact_limit=2)
    assert out == {"recentEvents": [{"type": "tool"}]}
    assert seen["run_id"] == "run-9"
    assert seen["limits"] == (3, 2)
    assert seen["ledger_root"] == Path("/proj") / "loot" / "session_ledgers"


def test_attack_graph_builds_from_notes():
    km = KnowledgeMemory()
    graph = km.attack_graph(notes={})
    # Returns a ShadowGraph instance with the standard query surface.
    assert hasattr(graph, "get_strategic_insights")


@pytest.mark.asyncio
async def test_record_finding_delegates_to_notes_sink(monkeypatch):
    calls = []

    async def fake_notes(arguments, runtime):
        calls.append((arguments, runtime))
        return "ok"

    monkeypatch.setattr("flaghunter.tools.notes.notes", fake_notes)
    rt = object()
    await KnowledgeMemory().record_finding(
        runtime=rt, key="k", value="v", category="credential", path="/etc/x"
    )
    assert len(calls) == 1
    args, runtime = calls[0]
    assert runtime is rt
    assert args["action"] == "update"
    assert args["key"] == "k"
    assert args["value"] == "v"
    assert args["category"] == "credential"
    assert args["path"] == "/etc/x"


@pytest.mark.asyncio
async def test_record_learned_delegates_to_strategy_save(monkeypatch):
    saved = []

    class FakeStore:
        async def save(self, entry):
            saved.append(entry)

    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.strategy_memory.StrategyMemoryStore", FakeStore
    )
    entry = object()
    await KnowledgeMemory().record_learned(entry)
    assert saved == [entry]


@pytest.mark.asyncio
async def test_recall_strategy_delegates_to_query(monkeypatch):
    class FakeStore:
        async def query(self, fingerprint, top_k=3):
            return [("entry", 0.9, top_k, fingerprint)]

    monkeypatch.setattr(
        "flaghunter.agents.pa_agent.strategy_memory.StrategyMemoryStore", FakeStore
    )
    fp = object()
    out = await KnowledgeMemory().recall_strategy(fp, top_k=5)
    assert out == [("entry", 0.9, 5, fp)]
