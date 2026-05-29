from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_mock_tasks_use_mode_contract_fields() -> None:
    source = _read("web/console/src/mock.js")

    assert "modeSubtype:" in source
    assert "goalStyle:" in source


def test_mock_tasks_no_longer_define_legacy_detected_type_field() -> None:
    source = _read("web/console/src/mock.js")

    assert "detectedType:" not in source
