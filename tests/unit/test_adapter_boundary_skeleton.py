"""Boundary tests for the adapter package skeleton."""

from __future__ import annotations

import ast
import importlib
import warnings
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS_ROOT = REPO_ROOT / "flaghunter" / "adapters"
DOMAIN_ROOT = REPO_ROOT / "flaghunter" / "domain"
PORTS_ROOT = REPO_ROOT / "flaghunter" / "ports"
PLAYBOOK_PATH = (
    REPO_ROOT
    / "docs"
    / "dev"
    / "FlagHunter_Clean_Architecture_Migration_Playbook_v0.1_2026-07-04.md"
)

EXPECTED_ADAPTER_PACKAGES = (
    "flaghunter.adapters",
    "flaghunter.adapters.artifacts",
    "flaghunter.adapters.audit",
    "flaghunter.adapters.crew",
    "flaghunter.adapters.mcp",
    "flaghunter.adapters.proof",
    "flaghunter.adapters.runtime",
    "flaghunter.adapters.storage",
    "flaghunter.adapters.tools",
)

EXPECTED_ADAPTER_NAMESPACE_EXPORTS = (
    "artifacts",
    "audit",
    "crew",
    "mcp",
    "proof",
    "runtime",
    "storage",
    "tools",
)

FORBIDDEN_INIT_IMPORT_PREFIXES = (
    "flaghunter.agents",
    "flaghunter.application",
    "flaghunter.config",
    "flaghunter.cpa_modules",
    "flaghunter.interface",
    "flaghunter.knowledge",
    "flaghunter.llm",
    "flaghunter.mcp",
    "flaghunter.playbooks",
    "flaghunter.runtime",
    "flaghunter.session",
    "flaghunter.tools",
    "flaghunter.workspaces",
)

FORBIDDEN_ACTION_TOKENS = {
    "CTFTaskDispatcher",
    "CTFState",
    "CTFVerifier",
    "ToolExecutor",
    "WorkerPool",
    "CrewOrchestrator",
    "LocalRuntime",
    "DockerRuntime",
    "SSHRuntime",
    "subprocess",
    "asyncio.subprocess",
    "Playwright",
    "requests",
    "httpx",
    "socket",
    "open(",
    "write_text",
}

FORBIDDEN_PROOF_ACTION_TOKENS = {
    "verification_decision",
    "upgrade_claim_to_verified",
    "append_verification_record",
    'level="verified"',
    "level='verified'",
    "verified_flags",
}

FORBIDDEN_PRODUCTION_WIRING_TOKENS = {
    "FlagHunterAgent",
    "AgentSession",
    "MCPRouter",
    "MCPServer",
    "CompositionRoot",
    "create_agent",
    "run_task_async",
}


def _parse(path: Path) -> ast.Module:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


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


def _python_sources(root: Path) -> list[Path]:
    assert root.is_dir(), f"missing package root: {_relative(root)}"
    return sorted(root.rglob("*.py"))


def test_adapter_namespace_packages_are_importable() -> None:
    for module_name in EXPECTED_ADAPTER_PACKAGES:
        module = importlib.import_module(module_name)
        assert module.__name__ == module_name


def test_mcp_adapter_namespace_exports_task_ingress_skeleton() -> None:
    package = importlib.import_module("flaghunter.adapters.mcp")
    module = importlib.import_module("flaghunter.adapters.mcp.task_ingress_adapter")

    assert package.TaskIngressAdapter is module.TaskIngressAdapter
    assert package.__all__ == ["TaskIngressAdapter"]


def test_root_adapter_namespace_declares_managed_packages() -> None:
    module = importlib.import_module("flaghunter.adapters")

    assert module.__all__ == EXPECTED_ADAPTER_NAMESPACE_EXPORTS


def test_expected_adapter_package_list_covers_all_package_directories() -> None:
    actual = {
        "flaghunter.adapters"
        + (
            "."
            + path.parent.relative_to(ADAPTERS_ROOT).as_posix().replace("/", ".")
            if path.parent != ADAPTERS_ROOT
            else ""
        )
        for path in sorted(ADAPTERS_ROOT.rglob("__init__.py"))
    }

    assert set(EXPECTED_ADAPTER_PACKAGES) == actual


def test_adapter_package_initializers_do_not_wire_concrete_implementations() -> None:
    offenders: list[tuple[str, str]] = []

    for path in sorted(ADAPTERS_ROOT.rglob("__init__.py")):
        tree = _parse(path)
        for imported in _imported_module_names(tree):
            normalized = imported.lstrip(".")
            if normalized.startswith(FORBIDDEN_INIT_IMPORT_PREFIXES):
                offenders.append((_relative(path), imported))
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_ACTION_TOKENS
            if token in text
        )
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_PROOF_ACTION_TOKENS
            if token in text
        )

    assert offenders == []


def test_adapter_forbidden_import_prefixes_cover_outer_production_layers() -> None:
    required_prefixes = {
        "flaghunter.agents",
        "flaghunter.application",
        "flaghunter.config",
        "flaghunter.cpa_modules",
        "flaghunter.interface",
        "flaghunter.knowledge",
        "flaghunter.llm",
        "flaghunter.mcp",
        "flaghunter.playbooks",
        "flaghunter.runtime",
        "flaghunter.session",
        "flaghunter.tools",
        "flaghunter.workspaces",
    }

    assert required_prefixes <= set(FORBIDDEN_INIT_IMPORT_PREFIXES)

    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Adapter outer-layer import coverage guard" in playbook
    for prefix in sorted(required_prefixes):
        assert prefix in playbook


def test_adapter_implementation_sources_do_not_wire_concrete_implementations() -> None:
    offenders: list[tuple[str, str]] = []

    for path in _python_sources(ADAPTERS_ROOT):
        if path.name == "__init__.py":
            continue

        tree = _parse(path)
        for imported in _imported_module_names(tree):
            normalized = imported.lstrip(".")
            if normalized.startswith(FORBIDDEN_INIT_IMPORT_PREFIXES):
                offenders.append((_relative(path), imported))

        text = path.read_text(encoding="utf-8")
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_ACTION_TOKENS
            if token in text
        )
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_PROOF_ACTION_TOKENS
            if token in text
        )

    assert offenders == []


def test_adapter_sources_do_not_reference_production_wiring_surfaces() -> None:
    playbook = PLAYBOOK_PATH.read_text(encoding="utf-8")
    assert "Adapter production wiring source guard" in playbook
    for token in sorted(FORBIDDEN_PRODUCTION_WIRING_TOKENS):
        assert token in playbook

    offenders: list[tuple[str, str]] = []

    for path in _python_sources(ADAPTERS_ROOT):
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            (_relative(path), token)
            for token in FORBIDDEN_PRODUCTION_WIRING_TOKENS
            if token in text
        )

    assert offenders == []


def test_inner_layers_do_not_import_adapter_package() -> None:
    offenders: list[tuple[str, str]] = []

    for root in (DOMAIN_ROOT, PORTS_ROOT):
        for path in _python_sources(root):
            for imported in _imported_module_names(_parse(path)):
                normalized = imported.lstrip(".")
                if normalized.startswith("flaghunter.adapters"):
                    offenders.append((_relative(path), imported))

    assert offenders == []
