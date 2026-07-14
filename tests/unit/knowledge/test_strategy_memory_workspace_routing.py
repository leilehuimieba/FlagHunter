"""Guard tests for the strategy-memory routing contract.

Two invariants are pinned here:

1. **Reader/writer agreement (the original Bug2 fix).** The writer
   (``StrategyMemoryStore``) and the learned-rules reader (``ProjectMemory``)
   must resolve to the SAME file, so learned-rule injection never reads a stale
   store. Both resolve through ``workspaces.utils.get_strategy_memory_file``.

2. **Cross-challenge sharing (the design gap ① fix).** Strategy memory is
   *cross-challenge* by construction — pheromone / failed-payload / fingerprint
   recall aggregate learning ACROSS challenges. It is therefore deliberately
   NOT workspace-routed: it resolves to the global project-root
   ``loot/strategy_memory.json`` regardless of the active workspace, so every
   ephemeral CTF instance shares one warm store instead of a cold per-workspace
   silo. Per-engagement isolation stays opt-in via the env override.
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
    # Exercise the default (global) routing, not conftest's env isolation path.
    monkeypatch.delenv("FLAGHUNTER_STRATEGY_MEMORY_PATH", raising=False)


def _activate_workspace(root: Path, name: str) -> Path:
    """Write the .active marker and return the workspace loot dir."""
    marker = root / "workspaces" / name
    marker.mkdir(parents=True, exist_ok=True)
    (root / "workspaces" / ".active").write_text(name, encoding="utf-8")
    return root / "workspaces" / name / "loot"


def test_writer_default_resolves_to_global_loot(tmp_path, monkeypatch):
    """A default-constructed store lands in the GLOBAL project-root loot, NOT the
    active workspace's loot — strategy memory is shared across challenges."""
    ws_loot = _activate_workspace(tmp_path, "ws1")
    monkeypatch.chdir(tmp_path)

    store = StrategyMemoryStore()

    global_path = (tmp_path / "loot" / "strategy_memory.json").resolve()
    assert store.path.resolve() == global_path
    # Explicitly NOT siloed under the active workspace.
    assert store.path.resolve() != (ws_loot / "strategy_memory.json").resolve()


def test_writer_and_reader_agree(tmp_path, monkeypatch):
    """The reader injects exactly what the writer persisted — reader/writer
    resolve the same global file (the preserved Bug2 agreement)."""
    _activate_workspace(tmp_path, "ws1")
    monkeypatch.chdir(tmp_path)

    writer_path = get_strategy_memory_file()
    writer_path.parent.mkdir(parents=True, exist_ok=True)
    writer_path.write_text(
        json.dumps({"id": "e1", "learned_rules": ["global-rule"]}) + "\n",
        encoding="utf-8",
    )

    # Reader resolves through the same helper (root = project root = cwd here).
    reader_path = get_strategy_memory_file(root=tmp_path)
    assert reader_path.resolve() == writer_path.resolve()

    pm = ProjectMemory(project_root=tmp_path)
    assert pm._load_learned_rules() == ["global-rule"]


def test_distinct_workspaces_share_cross_challenge_memory(tmp_path, monkeypatch):
    """Switching the active workspace does NOT switch the resolved memory file:
    cross-challenge learning is shared, not siloed per workspace."""
    _activate_workspace(tmp_path, "ws1")
    monkeypatch.chdir(tmp_path)
    p1 = get_strategy_memory_file()

    _activate_workspace(tmp_path, "ws2")
    p2 = get_strategy_memory_file()

    assert p1.resolve() == p2.resolve()
    assert p1.resolve() == (tmp_path / "loot" / "strategy_memory.json").resolve()


def test_env_override_wins_over_default(tmp_path, monkeypatch):
    """Explicit ops/test env override still takes precedence — the opt-in path
    for per-engagement isolation."""
    _activate_workspace(tmp_path, "ws1")
    monkeypatch.chdir(tmp_path)
    override = tmp_path / "elsewhere" / "mem.json"
    monkeypatch.setenv("FLAGHUNTER_STRATEGY_MEMORY_PATH", str(override))

    assert get_strategy_memory_file() == override
    assert StrategyMemoryStore().path == override
