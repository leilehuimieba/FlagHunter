from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_new_task_modal_consumes_model_readiness_from_settings_truth_source() -> None:
    source = _read("web/console/src/components.jsx")

    assert "window.API?.getSettings" in source
    assert "setModelReadiness((settingsData?.model?.readiness) || null);" in source


def test_new_task_modal_disables_launch_when_model_is_not_ready() -> None:
    source = _read("web/console/src/components.jsx")

    assert "const modelBlocked = modelReadiness?.ready === false;" in source
    assert "disabled={loading || modelBlocked}" in source
    assert "if (modelBlocked) { setErr(t('nt.err.modelNotReady'" in source


def test_settings_model_section_renders_readiness_status_and_reason() -> None:
    settings_source = _read("web/console/src/pages/settings.jsx")
    i18n_source = _read("web/console/src/i18n.js")

    assert "m.readiness?.ready === false" in settings_source
    assert "t('st.model.ready')" in settings_source
    assert "t('st.model.notReady')" in settings_source
    assert "t('st.model.reason')" in settings_source

    for key in [
        "nt.err.modelNotReady",
        "st.model.ready",
        "st.model.notReady",
        "st.model.reason",
        "st.model.reason.custom_provider_unconfigured",
    ]:
        assert key in i18n_source
