from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_settings_page_no_longer_uses_generic_unavailable_for_disabled_actions() -> None:
    source = _read("web/console/src/pages/settings.jsx")

    assert "title={t('c.unavailable')}>{t('st.rt.testBtn')}" not in source
    assert "title={t('c.unavailable')}>{t('st.mcp.addServer')}" not in source
    assert "title={t('c.unavailable')}>{t('st.kn.rebuild')}" not in source


def test_tasks_page_no_longer_uses_generic_unavailable_for_capability_reasons() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "const continueUnavailableReason = continueSupported ? t('c.unavailable') : t('td.continueUnavailable');" not in source
    assert "hintMode ? (hintAvailable ? t('td.hintDesc') : t('c.unavailable'))" not in source
    assert "title={hintMode ? (!hintAvailable ? t('c.unavailable') : '') : (!continueAvailable ? continueUnavailableReason : '')}" not in source
    assert "<Empty>{t('c.unavailable')}</Empty>" not in source


def test_traces_page_no_longer_reuses_task_retry_copy_for_replay_action() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "title={!replayAvailable ? t('td.retryUnavailable') : ''}" not in source


def test_i18n_defines_specific_disabled_reason_keys() -> None:
    source = _read("web/console/src/i18n.js")

    for key in [
        "c.notConnected",
        "c.notWired",
        "st.actionReadOnly",
        "td.hintUnavailable",
        "tr.replayUnavailable",
    ]:
        assert key in source
