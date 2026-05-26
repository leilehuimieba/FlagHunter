from __future__ import annotations

import argparse
import time

from pentestagent.agents.pa_agent.strategy_memory import (
    ChallengeFingerprint,
    StrategyMemoryEntry,
    StrategyMemoryEntryMetadata,
    StrategyMemoryStore,
)
from pentestagent.interface.main import handle_ctf_command


def _seed_memory_store(tmp_path):
    store = StrategyMemoryStore(tmp_path / "strategy_memory.json")
    entry = StrategyMemoryEntry(
        id="mem_cli",
        fingerprint=ChallengeFingerprint(
            detected_type="sqli",
            tech_stack=["php"],
            auth_mechanism="form_login",
        ),
        winning_hypothesis_kinds=["auth_form_sqli"],
        failed_hypothesis_kinds=["generic_web_recon"],
        solved=True,
        metadata=StrategyMemoryEntryMetadata(
            created_at=time.time(),
            manual_status="active",
            applied_count=2,
            successful_applications=2,
            success_correlation=1.0,
        ),
    )
    import asyncio

    asyncio.run(store.save(entry))
    return store


def test_ctf_memory_cli_list(monkeypatch, tmp_path, capsys):
    store = _seed_memory_store(tmp_path)
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.strategy_memory.StrategyMemoryStore",
        lambda: store,
    )

    handle_ctf_command(
        argparse.Namespace(
            ctf_command="memory",
            action="list",
            rest=[],
        )
    )

    output = capsys.readouterr().out
    assert "[CTF memory list]" in output
    assert "mem_cli" in output
    assert "facts=" in output


def test_ctf_memory_cli_list_supports_filter_and_sort(monkeypatch, tmp_path, capsys):
    store = _seed_memory_store(tmp_path)
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.strategy_memory.StrategyMemoryStore",
        lambda: store,
    )

    handle_ctf_command(
        argparse.Namespace(
            ctf_command="memory",
            action="list",
            rest=["5", "filter=active", "sort=applied"],
        )
    )

    output = capsys.readouterr().out
    assert "filter=active" in output
    assert "sort=applied" in output
    assert "mem_cli" in output


def test_ctf_memory_cli_show_and_mute(monkeypatch, tmp_path, capsys):
    store = _seed_memory_store(tmp_path)
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.strategy_memory.StrategyMemoryStore",
        lambda: store,
    )

    handle_ctf_command(
        argparse.Namespace(
            ctf_command="memory",
            action="show",
            rest=["mem_cli"],
        )
    )
    show_output = capsys.readouterr().out
    assert "[CTF memory show] mem_cli" in show_output
    assert "atomic_facts:" in show_output

    handle_ctf_command(
        argparse.Namespace(
            ctf_command="memory",
            action="mute",
            rest=["mem_cli"],
        )
    )
    mute_output = capsys.readouterr().out
    assert "muted mem_cli" in mute_output

    handle_ctf_command(
        argparse.Namespace(
            ctf_command="memory",
            action="rollback",
            rest=["mem_cli"],
        )
    )
    rollback_output = capsys.readouterr().out
    assert "rollback applied to mem_cli" in rollback_output


def test_ctf_memory_cli_audit(monkeypatch, tmp_path, capsys):
    store = _seed_memory_store(tmp_path)
    import asyncio

    asyncio.run(store.record_query_usage(["mem_cli"]))
    asyncio.run(store.record_outcome(["mem_cli"], solved=False))
    asyncio.run(store.record_outcome(["mem_cli"], solved=False))
    asyncio.run(store.record_outcome(["mem_cli"], solved=False))
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.strategy_memory.StrategyMemoryStore",
        lambda: store,
    )

    handle_ctf_command(
        argparse.Namespace(
            ctf_command="memory",
            action="audit",
            rest=["1.1"],
        )
    )
    output = capsys.readouterr().out
    assert "[CTF memory audit]" in output
    assert "mem_cli" in output
    assert "facts=" in output


def test_ctf_memory_cli_audit_supports_sort(monkeypatch, tmp_path, capsys):
    store = _seed_memory_store(tmp_path)
    import asyncio

    asyncio.run(store.record_query_usage(["mem_cli"]))
    asyncio.run(store.record_outcome(["mem_cli"], solved=False))
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.strategy_memory.StrategyMemoryStore",
        lambda: store,
    )

    handle_ctf_command(
        argparse.Namespace(
            ctf_command="memory",
            action="audit",
            rest=["0.9", "sort=correlation"],
        )
    )
    output = capsys.readouterr().out
    assert "sort=correlation" in output
    assert "mem_cli" in output


def test_ctf_memory_cli_delete_export_clear(monkeypatch, tmp_path, capsys):
    store = _seed_memory_store(tmp_path)
    monkeypatch.setattr(
        "pentestagent.agents.pa_agent.strategy_memory.StrategyMemoryStore",
        lambda: store,
    )

    export_path = tmp_path / "memory_export.json"
    handle_ctf_command(
        argparse.Namespace(
            ctf_command="memory",
            action="export",
            rest=[str(export_path)],
        )
    )
    export_output = capsys.readouterr().out
    assert "exported to" in export_output
    assert export_path.exists()

    handle_ctf_command(
        argparse.Namespace(
            ctf_command="memory",
            action="delete",
            rest=["mem_cli"],
        )
    )
    delete_output = capsys.readouterr().out
    assert "deleted mem_cli" in delete_output

    _seed_memory_store(tmp_path)
    handle_ctf_command(
        argparse.Namespace(
            ctf_command="memory",
            action="clear",
            rest=["confirm"],
        )
    )
    clear_output = capsys.readouterr().out
    assert "cleared" in clear_output
