from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_api_layer_exposes_test_runtime_function() -> None:
    source = _read("web/console/src/api.js")

    assert "async function testRuntime()" in source
    assert "return apiFetch('/api/runtime/test', { method: 'POST' });" in source
    assert "testRuntime," in source


def test_settings_page_binds_runtime_test_button_to_live_action() -> None:
    source = _read("web/console/src/pages/settings.jsx")

    assert "const runtimeTestAvailable = ['connected', 'degraded'].includes(connection?.status)" in source
    assert "&& typeof window.API?.testRuntime === 'function';" in source
    assert "const runtimeTestResult = await window.API.testRuntime();" in source
    assert "title={!runtimeTestAvailable ? runtimeTestUnavailableReason : ''}" in source
