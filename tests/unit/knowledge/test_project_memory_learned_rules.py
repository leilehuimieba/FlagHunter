"""Guard tests for ProjectMemory._load_learned_rules JSONL parsing.

Regression: the reader used to ``json.loads`` the whole strategy_memory.json
file, but the writer (StrategyMemoryStore.save) appends JSONL (one entry dict
per line). For >=2 lines that raised "Extra data" and the rules were silently
dropped, so learned rules never reached the prompt.
"""

from __future__ import annotations

import json
from pathlib import Path

from flaghunter.knowledge.project_memory import ProjectMemory


def _write_jsonl(root: Path, entries: list[dict]) -> None:
    sm_path = root / "loot" / "strategy_memory.json"
    sm_path.parent.mkdir(parents=True, exist_ok=True)
    with sm_path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def test_load_learned_rules_reads_multiline_jsonl(tmp_path) -> None:
    """Multi-line JSONL (the exact scenario that returned [] before) works."""
    _write_jsonl(
        tmp_path,
        [
            {"id": "e1", "learned_rules": ["rule-a", "rule-b"]},
            {"id": "e2", "learned_rules": ["rule-b", "rule-c"]},
        ],
    )

    pm = ProjectMemory(project_root=tmp_path)
    rules = pm._load_learned_rules()

    # Non-empty, deduped (rule-b appears once), first-seen order preserved.
    assert rules == ["rule-a", "rule-b", "rule-c"]


def test_load_learned_rules_last_five_entries_and_rules(tmp_path) -> None:
    """Only the last 5 entries contribute, and at most 5 rules are returned."""
    entries = [
        {"id": f"e{i}", "learned_rules": [f"rule-{i}"]} for i in range(8)
    ]
    _write_jsonl(tmp_path, entries)

    pm = ProjectMemory(project_root=tmp_path)
    rules = pm._load_learned_rules()

    # Entries 0,1,2 are dropped (only last 5 entries), then last 5 rules kept.
    assert rules == ["rule-3", "rule-4", "rule-5", "rule-6", "rule-7"]


def test_load_learned_rules_missing_file_returns_empty(tmp_path) -> None:
    pm = ProjectMemory(project_root=tmp_path)
    assert pm._load_learned_rules() == []


def test_load_learned_rules_empty_file_returns_empty(tmp_path) -> None:
    sm_path = tmp_path / "loot" / "strategy_memory.json"
    sm_path.parent.mkdir(parents=True, exist_ok=True)
    sm_path.write_text("", encoding="utf-8")

    pm = ProjectMemory(project_root=tmp_path)
    assert pm._load_learned_rules() == []


def test_load_learned_rules_skips_bad_line(tmp_path) -> None:
    """A single malformed line must not kill the whole load."""
    sm_path = tmp_path / "loot" / "strategy_memory.json"
    sm_path.parent.mkdir(parents=True, exist_ok=True)
    sm_path.write_text(
        json.dumps({"id": "e1", "learned_rules": ["good-1"]}) + "\n"
        + "{ this is not valid json\n"
        + json.dumps({"id": "e2", "learned_rules": ["good-2"]}) + "\n",
        encoding="utf-8",
    )

    pm = ProjectMemory(project_root=tmp_path)
    assert pm._load_learned_rules() == ["good-1", "good-2"]


def test_load_learned_rules_legacy_single_json_list(tmp_path) -> None:
    """Backward tolerance: a legacy single JSON array of entry dicts."""
    sm_path = tmp_path / "loot" / "strategy_memory.json"
    sm_path.parent.mkdir(parents=True, exist_ok=True)
    sm_path.write_text(
        json.dumps(
            [
                {"id": "e1", "learned_rules": ["legacy-a"]},
                {"id": "e2", "learned_rules": ["legacy-b"]},
            ]
        ),
        encoding="utf-8",
    )

    pm = ProjectMemory(project_root=tmp_path)
    assert pm._load_learned_rules() == ["legacy-a", "legacy-b"]


def test_load_learned_rules_legacy_entries_wrapper(tmp_path) -> None:
    """Backward tolerance: a legacy wrapper dict with an 'entries' key."""
    sm_path = tmp_path / "loot" / "strategy_memory.json"
    sm_path.parent.mkdir(parents=True, exist_ok=True)
    sm_path.write_text(
        json.dumps(
            {"entries": [{"id": "e1", "learned_rules": ["wrap-a", "wrap-b"]}]}
        ),
        encoding="utf-8",
    )

    pm = ProjectMemory(project_root=tmp_path)
    assert pm._load_learned_rules() == ["wrap-a", "wrap-b"]
