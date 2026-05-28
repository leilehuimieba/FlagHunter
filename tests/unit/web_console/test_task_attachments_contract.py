from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_task_detail_attachments_card_keeps_empty_state_and_live_upload_entry() -> None:
    source = _read("web/console/src/pages/tasks.jsx")

    assert "if (items.length === 0) return null;" not in source
    assert "typeof window.API?.uploadAttachment === 'function'" in source
    assert "const uploadResult = await window.API.uploadAttachment(detailTask.id, files);" in source
    assert "const attachmentsResult = await window.API.getAttachments(detailTask.id);" in source
    assert "type=\"file\"" in source
    assert "multiple" in source

