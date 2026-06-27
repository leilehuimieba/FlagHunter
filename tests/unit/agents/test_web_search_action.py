"""N5 guard: web_search 归位 execute_llm_action + ledger 审计.

Pins the fix for the "强能力够不着" gap — the LLM prompt allowed a web_search
tool but execute_llm_action had no branch for it, so an LLM web_search request
returned a blank response and was silently swallowed. These tests assert the
request is dispatched to the real tool, returns the standard response shape (so
the existing downstream scan/observation pipeline handles it), and is recorded
as paired tool_called/tool_finished ledger events (web_search bypasses the
audited runtime actions, so it needs explicit ledger plumbing).
"""

from __future__ import annotations

import inspect

import flaghunter.tools.web_search as web_search_module
from flaghunter.agents.pa_agent.llm_executor import LLMExecContext, LLMExecutor


def _make_ctx(events: list) -> LLMExecContext:
    return LLMExecContext(
        state=None,
        llm=None,
        runtime=None,
        collector_port=0,
        capability_registry=None,
        scan_and_store=None,
        extract_flag=lambda text: None,
        observe_flag=None,
        recent_observed_source_fetch_write_exploit=lambda: None,
        runtime_proxy_action=None,
        runtime_execute_command=None,
        record_session_event=lambda etype, payload: events.append((etype, payload)),
    )


async def test_web_search_dispatched_and_returns_result(monkeypatch):
    async def fake_web_search(arguments, runtime):
        assert arguments["query"] == "ctf flag format"
        return "Results:\n- https://example.com/a\n- https://example.com/b"

    monkeypatch.setattr(web_search_module, "web_search", fake_web_search)
    events: list = []
    result = await LLMExecutor().execute_llm_action(
        {"action_type": "web_search", "payload": {"query": "ctf flag format"}},
        "http://target/",
        _make_ctx(events),
    )

    assert "example.com/a" in result["response_text"]
    assert result["status_code"] == 0
    assert result["evidence_source"] == "web-search"
    # paired ledger events with a parsed result summary
    assert [etype for etype, _ in events] == ["tool_called", "tool_finished"]
    assert events[0][1]["tool_name"] == "web_search"
    assert events[1][1]["ok"] is True
    assert events[1][1]["metadata"]["hit_count"] == 2
    assert events[1][1]["metadata"]["top_url"] == "https://example.com/a"


async def test_web_search_routed_by_tool_name(monkeypatch):
    async def fake_web_search(arguments, runtime):
        return "ok https://x/"

    monkeypatch.setattr(web_search_module, "web_search", fake_web_search)
    result = await LLMExecutor().execute_llm_action(
        {"action_type": "tool_call", "tool_name": "web_search", "payload": {"query": "x"}},
        "http://target/",
        _make_ctx([]),
    )
    assert result["evidence_source"] == "web-search"


async def test_web_search_empty_query_is_explicit_error(monkeypatch):
    called = {"n": 0}

    async def fake_web_search(arguments, runtime):
        called["n"] += 1
        return "should not run"

    monkeypatch.setattr(web_search_module, "web_search", fake_web_search)
    events: list = []
    result = await LLMExecutor().execute_llm_action(
        {"action_type": "web_search", "payload": {}},
        "http://target/",
        _make_ctx(events),
    )
    assert result["status_code"] == 1
    assert result["response_text"].startswith("Error:")
    assert called["n"] == 0  # tool not invoked on empty query
    assert events == []  # nothing to audit


async def test_web_search_backend_error_is_not_silently_swallowed(monkeypatch):
    async def boom(arguments, runtime):
        raise RuntimeError("network down")

    monkeypatch.setattr(web_search_module, "web_search", boom)
    events: list = []
    result = await LLMExecutor().execute_llm_action(
        {"action_type": "web_search", "payload": {"query": "q"}},
        "http://target/",
        _make_ctx(events),
    )
    # explicit error response, not a blank silent swallow (the bug N5 fixes)
    assert result["response_text"].startswith("Error:")
    assert result["status_code"] == 1
    assert [etype for etype, _ in events] == ["tool_called", "tool_finished"]
    assert events[1][1]["ok"] is False


async def test_web_search_records_nothing_without_ledger(monkeypatch):
    async def fake_web_search(arguments, runtime):
        return "ok https://x/"

    monkeypatch.setattr(web_search_module, "web_search", fake_web_search)
    ctx = _make_ctx([])
    object.__setattr__(ctx, "record_session_event", None)  # ledger inactive
    result = await LLMExecutor().execute_llm_action(
        {"action_type": "web_search", "payload": {"query": "q"}},
        "http://target/",
        ctx,
    )
    assert result["evidence_source"] == "web-search"  # still works, just no audit


def test_execute_llm_action_dispatches_web_search():
    """Regression-lock: the dispatch branch must stay wired.

    Guards the original bug class — a tool named in the prompt but with no
    execution branch. If web_search dispatch is removed, this fails.
    """
    source = inspect.getsource(LLMExecutor.execute_llm_action)
    assert "web_search" in source
    assert hasattr(LLMExecutor, "_execute_web_search_action")
