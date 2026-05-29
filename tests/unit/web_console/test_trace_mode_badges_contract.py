from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_trace_list_renders_mode_badge_from_true_trace_mode() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "<ModeBadge mode={r.mode} />" in source


def test_trace_list_renders_subtype_badge_from_true_trace_mode_subtype() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "<SubtypeBadge value={r.modeSubtype} />" in source


def test_trace_detail_header_renders_mode_badge_from_true_run_mode() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "<ModeBadge mode={resolvedRun.mode} />" in source


def test_trace_detail_header_renders_subtype_badge_from_true_run_mode_subtype() -> None:
    source = _read("web/console/src/pages/traces.jsx")

    assert "<SubtypeBadge value={resolvedRun.modeSubtype} />" in source
