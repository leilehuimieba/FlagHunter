from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_new_task_modal_exposes_local_asset_fields() -> None:
    source = _read("web/console/src/components.jsx")

    assert "challengePath: ''," in source
    assert "artifactPathsText: ''," in source
    assert "label>{t('nt.challengePath')}<" in source
    assert "label>{t('nt.artifactPaths')}<" in source


def test_new_task_modal_normalizes_local_asset_contract_into_create_payload() -> None:
    source = _read("web/console/src/components.jsx")

    assert "const challengePath = form.challengePath.trim() || null;" in source
    assert "const artifactPaths = form.artifactPathsText" in source
    assert ".split(/\\r?\\n/" in source
    assert ".map(line => line.trim())" in source
    assert ".filter(Boolean);" in source
    assert "challengePath," in source
    assert "artifactPaths," in source


def test_task_detail_renders_local_asset_truth_card() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "function LocalAssetCard({ task }) {" in source
    assert "const challengePath = String(task?.challengePath || '').trim();" in source
    assert "const artifactPaths = Array.isArray(task?.artifactPaths) ? task.artifactPaths.filter(Boolean) : [];" in source
    assert "if (!challengePath && artifactPaths.length === 0) return null;" in source
    assert "<LocalAssetCard task={detailTask} />" in source


def test_task_detail_local_asset_card_shows_challenge_and_artifact_paths() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "{t('td.challengeAssets')}" in source
    assert "{t('td.challengePath')}" in source
    assert "{t('td.artifactPaths')}" in source
    assert "className=\"code-block\"" in source
    assert "artifactPaths.map((path, index) => (" in source
