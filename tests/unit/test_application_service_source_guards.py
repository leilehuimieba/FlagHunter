"""Source guards for neutral challenge application services."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_ROOT = REPO_ROOT / "flaghunter" / "application"
UNIT_TEST_ROOT = REPO_ROOT / "tests" / "unit"
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
    "flaghunter.cpa_modules",
    "flaghunter.eval",
    "flaghunter.interface",
    "flaghunter.knowledge",
    "flaghunter.llm",
    "flaghunter.mcp",
    "flaghunter.playbooks",
    "flaghunter.redteam",
    "flaghunter.runtime",
    "flaghunter.session",
    "flaghunter.tools",
    "flaghunter.workspaces",
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

REQUIRED_SIDE_EFFECT_SINKS = {
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

REQUIRED_PROOF_ACTION_TOKENS = {
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

FORBIDDEN_PUBLIC_DOMAIN_TERMS = {
    "ctf",
    "pentest",
    "exploit",
    "vulnerability",
    "hacking",
    "attack",
    "redteam",
}

REQUIRED_APPLICATION_COVERAGE_GUARD_SECTIONS = {
    "Application service side-effect sink coverage guard",
    "Application service proof action coverage guard",
    "Application service production wiring source guard",
    "Application service outer-layer import coverage guard",
    "Specific application service source guard import coverage consistency guard",
    "Public surface domain-neutral naming coverage guard",
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


def test_application_forbidden_import_prefixes_cover_all_outer_layers() -> None:
    required_prefixes = {
        "flaghunter.adapters",
        "flaghunter.agents",
        "flaghunter.config",
        "flaghunter.cpa_modules",
        "flaghunter.eval",
        "flaghunter.interface",
        "flaghunter.knowledge",
        "flaghunter.llm",
        "flaghunter.mcp",
        "flaghunter.playbooks",
        "flaghunter.redteam",
        "flaghunter.runtime",
        "flaghunter.session",
        "flaghunter.tools",
        "flaghunter.workspaces",
    }

    assert required_prefixes <= set(FORBIDDEN_IMPORT_PREFIXES)

    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Application service outer-layer import coverage guard" in playbook
    for prefix in sorted(required_prefixes):
        assert prefix in playbook


def test_specific_application_service_guards_cover_outer_legacy_layers() -> None:
    required_prefixes = {
        "flaghunter.eval",
        "flaghunter.redteam",
    }
    service_test_paths = sorted(
        path
        for path in UNIT_TEST_ROOT.glob("test_application_*_service.py")
        if path.name != "test_application_service_source_guards.py"
    )
    assert service_test_paths

    missing: list[tuple[str, str]] = []
    for path in service_test_paths:
        text = path.read_text(encoding="utf-8")
        missing.extend(
            (_relative(path), prefix)
            for prefix in sorted(required_prefixes)
            if prefix not in text
        )

    assert missing == []

    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert (
        "Specific application service source guard import coverage consistency guard"
        in playbook
    )
    for prefix in sorted(required_prefixes):
        assert prefix in playbook


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


def test_application_side_effect_guard_covers_explicit_sinks() -> None:
    assert REQUIRED_SIDE_EFFECT_SINKS <= FORBIDDEN_CALLS

    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Application service side-effect sink coverage guard" in playbook
    for token in sorted(REQUIRED_SIDE_EFFECT_SINKS):
        assert token in playbook


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


def test_application_proof_action_guard_covers_authority_sinks() -> None:
    assert REQUIRED_PROOF_ACTION_TOKENS <= FORBIDDEN_PROOF_TOKENS

    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Application service proof action coverage guard" in playbook
    for token in sorted(REQUIRED_PROOF_ACTION_TOKENS):
        assert token in playbook


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


def test_application_public_names_docstrings_and_paths_are_domain_neutral() -> None:
    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Public surface domain-neutral naming coverage guard" in playbook
    for term in sorted(FORBIDDEN_PUBLIC_DOMAIN_TERMS):
        assert term in playbook

    offenders: list[tuple[str, str, int]] = []
    for path in _application_sources():
        tree = _parse(path)
        path_parts = [part.lower() for part in path.relative_to(REPO_ROOT).parts[1:]]
        for part in path_parts:
            offenders.extend(
                (_relative(path), f"path part {part} contains {term}", 1)
                for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
                if term in part
            )

        module_doc = (ast.get_docstring(tree) or "").lower()
        offenders.extend(
            (_relative(path), f"module docstring contains {term}", 1)
            for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
            if term in module_doc
        )

        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                lowered_name = node.name.lower()
                offenders.extend(
                    (_relative(path), f"{node.name} contains {term}", node.lineno)
                    for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
                    if term in lowered_name
                )
                lowered_doc = (ast.get_docstring(node) or "").lower()
                offenders.extend(
                    (
                        _relative(path),
                        f"{node.name} docstring contains {term}",
                        node.lineno,
                    )
                    for term in FORBIDDEN_PUBLIC_DOMAIN_TERMS
                    if term in lowered_doc
                )

    assert offenders == []


def test_application_service_source_guard_coverage_completeness_records_all_guard_groups() -> None:
    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Application service source guard coverage completeness guard" in playbook
    for section_name in sorted(REQUIRED_APPLICATION_COVERAGE_GUARD_SECTIONS):
        assert section_name in playbook
