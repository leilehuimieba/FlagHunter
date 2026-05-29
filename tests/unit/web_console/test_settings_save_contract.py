from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_settings_save_no_longer_bare_calls_put_settings() -> None:
    source = _read("web/console/src/pages/settings.jsx")

    assert "window.API.putSettings(buildSavePayload(draft, meta))" not in source


def test_settings_save_introduces_api_wiring_guard() -> None:
    source = _read("web/console/src/pages/settings.jsx")

    assert "typeof window.API?.putSettings === 'function'" in source


def test_settings_save_uses_honest_not_wired_reason() -> None:
    source = _read("web/console/src/pages/settings.jsx")

    assert "t('c.notWired')" in source
