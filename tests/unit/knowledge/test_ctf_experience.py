"""Tests for CTF experience knowledge persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from pentestagent.knowledge.ctf_experience import save_ctf_experience
from pentestagent.knowledge.indexer import resolve_knowledge_scan_paths


@pytest.mark.asyncio
async def test_save_writes_markdown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    out_path = await save_ctf_experience(
        url="http://example.com/challenge",
        chtype="web",
        hint="look at robots.txt",
        flag="flag{demo}",
        successful_steps=["Checked robots.txt", "Found hidden admin page"],
        failed_steps=["Tried dirsearch without wordlist"],
    )

    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "flag{demo}" in content
    assert "## Successful Steps" in content


@pytest.mark.asyncio
async def test_save_path_contains_type(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    out_path = await save_ctf_experience(
        url="http://example.com",
        chtype="sqli",
        hint="try forms",
        flag="flag{sqli}",
        successful_steps=["Ran sqlmap --forms"],
        failed_steps=[],
    )

    assert "sqli" in out_path.name


@pytest.mark.asyncio
async def test_save_empty_steps(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    out_path = await save_ctf_experience(
        url="http://example.com",
        chtype="misc",
        hint="",
        flag="flag{empty}",
        successful_steps=[],
        failed_steps=[],
    )

    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "## Failed Attempts" in content


def test_scan_paths_includes_ctf_sessions(tmp_path):
    base = tmp_path / "knowledge"
    (base / "sources").mkdir(parents=True)
    (base / "sessions").mkdir(parents=True)
    (base / "ctf_sessions").mkdir(parents=True)

    roots = resolve_knowledge_scan_paths(base)
    assert base / "ctf_sessions" in roots
