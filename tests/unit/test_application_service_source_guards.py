"""Source guards for neutral challenge application services."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_ROOT = REPO_ROOT / "flaghunter" / "application"
PLAYBOOK_PATH = (
    REPO_ROOT
    / "docs"
    / "dev"
    / "FlagHunter_Clean_Architecture_Migration_Playbook_v0.1_2026-07-04.md"
)

ALLOWED_FLAGHUNTER_IMPORT_PREFIXES = (
    "flaghunter.domain",
    "flaghunter.ports",
)

FORBIDDEN_IMPORT_PREFIXES = (
    "flaghunter.adapters",
    "flaghunter.agents",
    "flaghunter.config",
    "flaghunter.interface",
    "flaghunter.knowledge",
    "flaghunter.llm",
    "flaghunter.mcp",
    "flaghunter.runtime",
    "flaghunter.session",
    "flaghunter.tools",
)

FORBIDDEN_CALLS = {
    "open",
    "Path.open",
    "Path.read_text",
    "Path.write_text",
    "Path.read_bytes",
    "Path.write_bytes",
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
    "requests.get",
    "requests.post",
    "requests.request",
    "httpx.get",
    "httpx.post",
    "httpx.request",
    "socket.socket",
}

FORBIDDEN_NAME_TOKENS = {
    "AgentSession",
    "CompositionRoot",
    "CTFTaskDispatcher",
    "CTFVerifier",
    "FlagHunterAgent",
    "MCPRouter",
    "MCPServer",
    "ToolExecutor",
    "WorkerPool",
    "CrewOrchestrator",
    "LocalRuntime",
    "DockerRuntime",
    "SSHRuntime",
    "ProofAuthorityPort",
    "create_agent",
    "run_task_async",
}

FORBIDDEN_PROOF_TOKENS = {
    "verification_decision",
    "upgrade_claim_to_verified",
    "append_verification_record",
    "append_proof_record",
    "confirm_claim",
    'level="verified"',
    "level='verified'",
    "verified_flags",
    "verifiedFlags",
}


def _application_sources() -> list[Path]:
    assert APPLICATION_ROOT.is_dir(), "flaghunter.application package must exist"
    return sorted(
        path
        for path in APPLICATION_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _imported_module_names(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append("." * node.level + (node.module or ""))
    return modules


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def test_application_services_import_only_neutral_contracts_and_ports() -> None:
    offenders: list[tuple[str, str]] = []

    for path in _application_sources():
        for imported in _imported_module_names(_parse(path)):
            normalized = imported.lstrip(".")
            if not normalized.startswith("flaghunter."):
                continue
            if normalized.startswith(ALLOWED_FLAGHUNTER_IMPORT_PREFIXES):
                continue
            offenders.append((_relative(path), imported))

    assert offenders == []


def test_application_services_do_not_import_concrete_execution_layers() -> None:
    offenders: list[tuple[str, str]] = []

    for path in _application_sources():
        for imported in _imported_module_names(_parse(path)):
            normalized = imported.lstrip(".")
            if normalized.startswith(FORBIDDEN_IMPORT_PREFIXES):
                offenders.append((_relative(path), imported))

    assert offenders == []


def test_application_services_have_no_side_effect_sinks() -> None:
    offenders: list[tuple[str, str, int]] = []

    for path in _application_sources():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node.func)
            if call_name in FORBIDDEN_CALLS:
                offenders.append((_relative(path), call_name, node.lineno))

    assert offenders == []


def test_application_services_have_no_proof_upgrade_or_runtime_surfaces() -> None:
    offenders: list[tuple[str, str]] = []

    for path in _application_sources():
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_NAME_TOKENS | FORBIDDEN_PROOF_TOKENS
            if token in text
        )

    assert offenders == []


def test_application_services_have_no_production_wiring_surfaces() -> None:
    required_tokens = {
        "FlagHunterAgent",
        "AgentSession",
        "MCPRouter",
        "MCPServer",
        "CompositionRoot",
        "create_agent",
        "run_task_async",
    }
    assert required_tokens <= FORBIDDEN_NAME_TOKENS

    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Application service production wiring source guard" in playbook
    for token in sorted(required_tokens):
        assert token in playbook

    offenders: list[tuple[str, str]] = []
    for path in _application_sources():
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            (_relative(path), token)
            for token in required_tokens
            if token in text
        )

    assert offenders == []
