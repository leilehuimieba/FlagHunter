from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_api_layer_exposes_add_mcp_server_function() -> None:
    source = _read("web/console/src/api.js")

    assert "async function addMcpServer(payload)" in source
    assert "return apiFetch('/api/settings/mcp/servers', {" in source
    assert "method: 'POST'" in source
    assert "addMcpServer," in source


def test_settings_page_binds_mcp_add_server_to_live_action() -> None:
    source = _read("web/console/src/pages/settings.jsx")

    assert "const addServerAvailable = ['connected', 'degraded'].includes(connection?.status)" in source
    assert "&& typeof window.API?.addMcpServer === 'function';" in source
    assert "const result = await window.API.addMcpServer({ name: addServerForm.name, url: addServerForm.url });" in source
    assert "const merged = mergeSettings(result.settings || draft);" in source
    assert "disabled={true} title={t('st.actionReadOnly')}>{t('st.mcp.addServer')}</button>" not in source
