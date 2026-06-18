"""Tests for hierarchical observability spans."""

from __future__ import annotations

from flaghunter.observability import MetricsCollector, SpanScope


def test_nested_spans_export_tree_with_rollup_tokens_and_duration(monkeypatch):
    ticks = iter([10.0, 10.2, 10.3, 10.7, 10.8, 11.5])
    monkeypatch.setattr("flaghunter.observability.time.monotonic", lambda: next(ticks))

    collector = MetricsCollector()

    with collector.span("round-1", SpanScope.ENTRY) as round_span:
        round_span.add_tokens(input_tokens=100, output_tokens=25)
        with collector.span("xss probe", SpanScope.STEP) as step_span:
            step_span.add_tokens(input_tokens=40, output_tokens=10)
            with collector.span(
                "stored-xss-admin-bot",
                SpanScope.CHAIN,
                metadata={"chain": "stored-xss-admin-bot"},
            ) as chain_span:
                chain_span.add_tokens(input_tokens=300, output_tokens=75)

    exported = collector.export_spans()

    assert len(exported) == 1
    round_node = exported[0]
    step_node = round_node["children"][0]
    chain_node = step_node["children"][0]

    assert round_node["name"] == "round-1"
    assert round_node["kind"] == "entry"
    assert round_node["duration_ms"] == 1500.0
    assert round_node["tokens"] == {
        "input": 100,
        "output": 25,
        "total": 125,
    }
    assert round_node["token_rollup"] == {
        "input": 440,
        "output": 110,
        "total": 550,
    }
    assert step_node["kind"] == "step"
    assert step_node["duration_ms"] == 600.0
    assert step_node["token_rollup"]["total"] == 425
    assert chain_node["kind"] == "chain"
    assert chain_node["metadata"]["chain"] == "stored-xss-admin-bot"
    assert chain_node["duration_ms"] == 400.0
    assert chain_node["token_rollup"] == {
        "input": 300,
        "output": 75,
        "total": 375,
    }


def test_span_attribution_by_chain_rolls_up_nested_skill_tokens(monkeypatch):
    ticks = iter([1.0, 1.1, 1.2, 1.4, 1.5, 2.0])
    monkeypatch.setattr("flaghunter.observability.time.monotonic", lambda: next(ticks))

    collector = MetricsCollector()

    with collector.span(
        "web-chain",
        SpanScope.CHAIN,
        metadata={"chain": "web:admin-bot"},
    ) as chain_span:
        chain_span.add_tokens(input_tokens=50, output_tokens=10)
        with collector.span(
            "payload-crafting",
            SpanScope.SKILL,
            metadata={"skill": "xss-payloads"},
        ) as skill_span:
            skill_span.add_tokens(input_tokens=100, output_tokens=25)
        with collector.span(
            "flag-verifier",
            SpanScope.SKILL,
            metadata={"skill": "flag-verifier", "false_flag": True},
        ) as verifier_span:
            verifier_span.add_tokens(input_tokens=20, output_tokens=5)

    attribution = collector.get_span_attribution(SpanScope.CHAIN)

    assert list(attribution) == ["web:admin-bot"]
    assert attribution["web:admin-bot"] == {
        "count": 1,
        "duration_ms": 1000.0,
        "tokens": {"input": 170, "output": 40, "total": 210},
    }
