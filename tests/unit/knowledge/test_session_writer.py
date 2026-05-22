"""Tests for session knowledge writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from pentestagent.knowledge.session_writer import write_session_to_knowledge


@pytest.mark.asyncio
async def test_write_session_to_knowledge_writes_only_worthy_notes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    notes = {
        "open_ports": {
            "content": "Found ports 22 and 80",
            "category": "finding",
            "confidence": "high",
        },
        "weak_banner": {
            "content": "Maybe interesting banner",
            "category": "info",
            "confidence": "low",
        },
        "creds": {
            "content": "Recovered admin:password",
            "category": "credential",
            "confidence": "medium",
        },
    }

    out_path = await write_session_to_knowledge("127.0.0.1", notes)

    assert out_path is not None
    assert out_path.exists()
    assert out_path.parent == Path("pentestagent/knowledge/sessions")

    content = out_path.read_text(encoding="utf-8")
    assert "open_ports (finding)" in content
    assert "creds (credential)" in content
    assert "weak_banner" not in content


@pytest.mark.asyncio
async def test_write_session_to_knowledge_returns_none_for_no_worthy_notes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    notes = {
        "noise": {
            "content": "Noisy low-confidence info",
            "category": "info",
            "confidence": "low",
        }
    }

    out_path = await write_session_to_knowledge("127.0.0.1", notes)
    assert out_path is None
