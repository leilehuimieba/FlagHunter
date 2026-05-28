from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_logs_drawer_no_longer_invents_payload_fields() -> None:
    source = _read("web/console/src/pages/logs.jsx")

    assert "cwd: '/work/runs/' + log.runId" not in source
    assert "pid: log.source.startsWith('tool.terminal') ? 18472 : null" not in source


def test_logs_drawer_no_longer_uses_hardcoded_prev_next_context() -> None:
    source = _read("web/console/src/pages/logs.jsx")

    assert "orchestrator · plan saved" not in source
    assert "rag · 2 hits (top 0.79)" not in source
    assert "runtime · pid=18472 alive" not in source
    assert "tool.terminal · sqlmap heuristic match" not in source
