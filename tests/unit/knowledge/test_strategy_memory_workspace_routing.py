"""Guard tests for Bug2: strategy-memory writer and learned-rules reader must
resolve to the SAME workspace-routed file.

Before the fix the writer (StrategyMemoryStore) defaulted to a CWD-relative
``loot/strategy_memory.json`` while the reader (ProjectMemory) read
``<project_root>/loot/strategy_memory.json``. Once notes/loot were routed into
an isolated workspace, the two halves wrote and read different files, so
learned-rule injection silently lost the workspace's memory. Both now resolve
through ``workspaces.utils.get_strategy_memory_file``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flaghunter.agents.pa_agent.strategy_memory import StrategyMemoryStore
from flaghunter.knowledge.project_memory import ProjectMemory
from flaghunter.workspaces.utils import get_strategy_memory_file


@pytest.fixture(autouse=True)
def _no_env_override(monkeypatch):
    # Exercise workspace/global routing, not conftest's env isolation path.
    monkeypatch.delenv("FLAGHUNTER_STRATEGY_MEMORY_PATH", raising=False)


def _activate_workspace(root: Path, name: str) -> Path:
    """Write the .active marker and return the workspace loot dir."""
    marker = root / "workspaces" / name
    marker.mkdir(parents=True, exist_ok=True)
    (root / "workspaces" / ".active").write_text(name, encoding="utf-8")
    return root / "workspaces" / name / "loot"


def test_writer_default_follows_active_workspace(tmp_path, monkeypatch):
    """A default-constructed store lands under the active workspace's loot."""
    ws_loot = _activate_workspace(tmp_path, "ws1")
    monkeypatch.chdir(tmp_path)

    store = StrategyMemoryStore()

    # Writer resolves root=None (CWD-relative); compare resolved against the
    # absolute workspace loot dir — same file after chdir.
    assert store.path.resolve() == (ws_loot / "strategy_memory.json").resolve()


def test_writer_and_reader_agree_under_workspace(tmp_path, monkeypatch):
    """The reader injects exactly what the writer persisted in the same
    workspace — the end-to-end Bug2 regression."""
    _activate_workspace(tmp_path, "ws1")
    monkeypatch.chdir(tmp_path)

    # Writer path (workspace-routed) and a hand-written JSONL entry there.
    writer_path = get_strategy_memory_file()
    writer_path.parent.mkdir(parents=True, exist_ok=True)
    writer_path.write_text(
        json.dumps({"id": "e1", "learned_rules": ["ws1-rule"]}) + "\n",
        encoding="utf-8",
    )

    # Reader resolves through the same helper (root = project root = cwd here).
    reader_path = get_strategy_memory_file(root=tmp_path)
    assert reader_path.resolve() == writer_path.resolve()

    pm = ProjectMemory(project_root=tmp_path)
    assert pm._load_learned_rules() == ["ws1-rule"]


def test_distinct_workspaces_keep_separate_memory(tmp_path, monkeypatch):
    """Switching the active workspace switches the resolved memory file."""
    _activate_workspace(tmp_path, "ws1")
    monkeypatch.chdir(tmp_path)
    p1 = get_strategy_memory_file()

    _activate_workspace(tmp_path, "ws2")
    p2 = get_strategy_memory_file()

    assert p1 != p2
    assert p1.parent.parent.name == "ws1"
    assert p2.parent.parent.name == "ws2"


def test_env_override_wins_over_workspace(tmp_path, monkeypatch):
    """Explicit ops/test env override still takes precedence over routing."""
    _activate_workspace(tmp_path, "ws1")
    monkeypatch.chdir(tmp_path)
    override = tmp_path / "elsewhere" / "mem.json"
    monkeypatch.setenv("FLAGHUNTER_STRATEGY_MEMORY_PATH", str(override))

    assert get_strategy_memory_file() == override
    assert StrategyMemoryStore().path == override
