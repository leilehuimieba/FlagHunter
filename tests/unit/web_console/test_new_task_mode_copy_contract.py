from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_i18n_truthifies_new_task_mode_copy() -> None:
    source = _read("web/console/src/i18n.js")

    assert "'nt.mode': 'task mode'," in source
    assert "'nt.mode': '任务模式'," in source
    assert "'nt.mode': 'agent mode'," not in source
    assert "'nt.mode': 'Agent 模式'," not in source


def test_new_task_modal_introduces_ctf_type_enablement_guard() -> None:
    source = _read("web/console/src/components.jsx")

    assert "const ctfTypeEnabled = form.mode === 'ctf' || form.mode === 'auto';" in source
    assert "onClick={() => ctfTypeEnabled && patch('ctfType', tp)}" in source


def test_new_task_modal_shows_ctf_specific_hint_when_ctf_type_is_disabled() -> None:
    source = _read("web/console/src/components.jsx")
    i18n = _read("web/console/src/i18n.js")

    assert "t('nt.ctfTypeHint')" in source
    assert "'nt.ctfTypeHint': 'used only for CTF task routing'," in i18n
    assert "'nt.ctfTypeHint': '仅用于 CTF 任务分类'," in i18n
