"""Pre-approval guards for task ingress production wiring."""

from __future__ import annotations

import ast
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
    "flaghunter/mcp",
    "flaghunter/agents",
    "flaghunter/tools",
    "flaghunter/runtime",
    "flaghunter/session",
    "flaghunter/workspaces",
    "flaghunter/config",
)

PRODUCTION_ENTRY_FILES = (
    "flaghunter/__main__.py",
    "flaghunter/hooks.py",
    "flaghunter/logging_config.py",
    "flaghunter/observability.py",
    "flaghunter/task_registry.py",
)

REQUIRED_PRODUCTION_ENTRY_ROOTS = {
    "flaghunter/interface",
    "flaghunter/mcp",
    "flaghunter/agents",
    "flaghunter/tools",
    "flaghunter/runtime",
    "flaghunter/session",
    "flaghunter/workspaces",
    "flaghunter/config",
}

REQUIRED_PRODUCTION_ENTRY_FILES = {
    "flaghunter/__main__.py",
    "flaghunter/hooks.py",
    "flaghunter/logging_config.py",
    "flaghunter/observability.py",
    "flaghunter/task_registry.py",
}

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

APPROVED_TASK_INGRESS_WIRING_A_FILE = "flaghunter/mcp/server/mcp_tools.py"

APPROVED_TASK_INGRESS_WIRING_A_TOKENS = {
    "SubmitTaskIngress",
    "task_ingress_service",
    "flaghunter.application.challenge.task_ingress_service",
}

APPROVED_TASK_INGRESS_WIRING_B_FILE = "flaghunter/interface/web_server.py"

APPROVED_TASK_INGRESS_WIRING_B_TOKENS = {
    "SubmitTaskIngress",
    "task_ingress_service",
    "flaghunter.application.challenge.task_ingress_service",
}

APPROVED_TASK_INGRESS_SUBMISSION_SCOPES = {
    "flaghunter/mcp/server/mcp_tools.py": {"_submit_task_ingress"},
    "flaghunter/interface/web_server.py": {"_submit_web_task_ingress"},
}

REQUIRED_TASK_INGRESS_WIRING_TOKENS = {
    "TaskIngressAdapter",
    "TaskIngressPort",
    "SubmitTaskIngress",
    "task_ingress_adapter",
    "task_ingress_service",
    "flaghunter.adapters.mcp",
    "flaghunter.application.challenge.task_ingress_service",
    "flaghunter.ports.task_ingress",
}

REQUIRED_TASK_INGRESS_PRODUCTION_GUARD_SECTIONS = {
    "Task ingress MCP pre-wiring guard baseline",
    "Task ingress production entrypoint pre-wiring guard baseline",
    "Task ingress production entry root coverage guard",
    "Task ingress production entry file coverage guard",
    "Task ingress production wiring token coverage guard",
}


def _playbook_text() -> str:
    return PLAYBOOK_PATH.read_text(encoding="utf-8")


def _production_sources() -> list[Path]:
    paths: list[Path] = []
    for root in PRODUCTION_ENTRY_ROOTS:
        root_path = REPO_ROOT / root
        if root_path.exists():
            paths.extend(sorted(root_path.rglob("*.py")))
    for entry_file in PRODUCTION_ENTRY_FILES:
        file_path = REPO_ROOT / entry_file
        if file_path.exists():
            paths.append(file_path)
    return paths


def _call_scopes_for(path: Path, call_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    scopes: set[str] = set()

    class CallScopeVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_Call(self, node: ast.Call) -> None:
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name == call_name:
                scopes.add(".".join(self.scope) or "<module>")
            self.generic_visit(node)

    CallScopeVisitor().visit(tree)
    return scopes


def test_task_ingress_production_entrypoints_only_allow_approved_mcp_submission_wiring() -> None:
    playbook = _playbook_text()
    assert "Task ingress production wiring A implementation landing record" in playbook
    assert "Task ingress production wiring A: implementation landed" in playbook
    assert "Task ingress production wiring B implementation landing record" in playbook
    assert "Task ingress production wiring B: implementation landed" in playbook

    offenders: list[tuple[str, str]] = []
    for path in _production_sources():
        relative = path.relative_to(REPO_ROOT).as_posix()
        source = path.read_text(encoding="utf-8-sig")
        forbidden_tokens = set(FORBIDDEN_TASK_INGRESS_WIRING_TOKENS)
        if relative == APPROVED_TASK_INGRESS_WIRING_A_FILE:
            forbidden_tokens -= APPROVED_TASK_INGRESS_WIRING_A_TOKENS
        if relative == APPROVED_TASK_INGRESS_WIRING_B_FILE:
            forbidden_tokens -= APPROVED_TASK_INGRESS_WIRING_B_TOKENS
        offenders.extend(
            (relative, token)
            for token in sorted(forbidden_tokens)
            if token in source
        )

    assert offenders == []


def test_task_ingress_remaining_entrypoints_stay_unwired_after_a_and_b() -> None:
    playbook = _playbook_text()
    assert "Task ingress remaining entrypoint denial guard" in playbook
    assert "remaining entrypoints not approved" in playbook

    for relative, allowed_scopes in APPROVED_TASK_INGRESS_SUBMISSION_SCOPES.items():
        path = REPO_ROOT / relative
        assert _call_scopes_for(path, "SubmitTaskIngress") == allowed_scopes

    denied_surfaces = {
        "MCPRouter",
        "_drive_task",
        "_make_agent",
        "CLI/TUI",
        "other Web handler",
        "composition root",
    }
    for surface in denied_surfaces:
        assert surface in playbook


def test_task_ingress_pre_wiring_guard_covers_mcp_server_entrypoints() -> None:
    playbook = _playbook_text()

    assert "flaghunter/mcp" in PRODUCTION_ENTRY_ROOTS
    assert "flaghunter/mcp/server" in playbook
    assert "MCP run_task/run_task_async task submission ingress" in playbook
    assert "Web post_task task creation ingress" in playbook


def test_task_ingress_pre_wiring_guard_covers_explicit_wiring_tokens() -> None:
    assert REQUIRED_TASK_INGRESS_WIRING_TOKENS <= FORBIDDEN_TASK_INGRESS_WIRING_TOKENS

    playbook = _playbook_text()
    assert "Task ingress production wiring token coverage guard" in playbook
    for token in sorted(REQUIRED_TASK_INGRESS_WIRING_TOKENS):
        assert token in playbook


def test_task_ingress_pre_wiring_guard_covers_required_entry_roots() -> None:
    assert REQUIRED_PRODUCTION_ENTRY_ROOTS <= set(PRODUCTION_ENTRY_ROOTS)

    playbook = _playbook_text()
    assert "Task ingress production entry root coverage guard" in playbook
    for root in sorted(REQUIRED_PRODUCTION_ENTRY_ROOTS):
        assert root in playbook


def test_task_ingress_pre_wiring_guard_covers_required_entry_files() -> None:
    assert REQUIRED_PRODUCTION_ENTRY_FILES <= set(PRODUCTION_ENTRY_FILES)

    scanned_paths = {
        path.relative_to(REPO_ROOT).as_posix() for path in _production_sources()
    }
    assert REQUIRED_PRODUCTION_ENTRY_FILES <= scanned_paths

    playbook = _playbook_text()
    assert "Task ingress production entry file coverage guard" in playbook
    for entry_file in sorted(REQUIRED_PRODUCTION_ENTRY_FILES):
        assert entry_file in playbook


def test_task_ingress_pre_wiring_guard_coverage_completeness_is_recorded() -> None:
    playbook = _playbook_text()
    assert "Task ingress production pre-wiring coverage completeness guard" in playbook
    assert "Task ingress production wiring A implementation landing record" in playbook
    assert "Task ingress production wiring B implementation landing record" in playbook
    for section_name in sorted(REQUIRED_TASK_INGRESS_PRODUCTION_GUARD_SECTIONS):
        assert section_name in playbook
