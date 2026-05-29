from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_new_task_modal_defaults_mode_to_auto() -> None:
    source = _read("web/console/src/components.jsx")

    assert "mode: 'auto'," in source
    assert "mode: 'agent'," not in source


def test_new_task_modal_exposes_truthful_task_mode_options() -> None:
    source = _read("web/console/src/components.jsx")

    assert "const MODES = ['auto', 'pentest', 'ctf'];" in source


def test_new_task_modal_drops_legacy_agent_mode_options() -> None:
    source = _read("web/console/src/components.jsx")

    assert "const MODES = ['assist', 'agent', 'crew'];" not in source
