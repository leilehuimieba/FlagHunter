"""Pre-approval guards for task ingress production wiring."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK_PATH = (
    REPO_ROOT
    / "docs"
    / "dev"
    / "FlagHunter_Clean_Architecture_Migration_Playbook_v0.1_2026-07-04.md"
)

PRODUCTION_ENTRY_ROOTS = (
    "flaghunter/interface",
    "flaghunter/agents",
    "flaghunter/tools",
    "flaghunter/runtime",
    "flaghunter/session",
    "flaghunter/workspaces",
    "flaghunter/config",
)

FORBIDDEN_TASK_INGRESS_WIRING_TOKENS = {
    "TaskIngressAdapter",
    "TaskIngressPort",
    "SubmitTaskIngress",
    "task_ingress_adapter",
    "task_ingress_service",
    "flaghunter.adapters.mcp",
    "flaghunter.application.challenge.task_ingress_service",
    "flaghunter.ports.task_ingress",
}


def _playbook_text() -> str:
    return PLAYBOOK_PATH.read_text(encoding="utf-8")


def _production_sources() -> list[Path]:
    paths: list[Path] = []
    for root in PRODUCTION_ENTRY_ROOTS:
        root_path = REPO_ROOT / root
        if root_path.exists():
            paths.extend(sorted(root_path.rglob("*.py")))
    return paths


def test_task_ingress_production_entrypoints_remain_unwired_before_approval() -> None:
    playbook = _playbook_text()
    assert "Task ingress production entrypoint pre-wiring guard baseline" in playbook
    assert "Required gate: explicit production wiring approval" in playbook

    offenders: list[tuple[str, str]] = []
    for path in _production_sources():
        source = path.read_text(encoding="utf-8-sig")
        offenders.extend(
            (path.relative_to(REPO_ROOT).as_posix(), token)
            for token in sorted(FORBIDDEN_TASK_INGRESS_WIRING_TOKENS)
            if token in source
        )

    assert offenders == []
