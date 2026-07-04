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

EXPECTED_ADAPTER_PACKAGES = (
    "flaghunter.adapters",
    "flaghunter.adapters.artifacts",
    "flaghunter.adapters.audit",
    "flaghunter.adapters.crew",
    "flaghunter.adapters.mcp",
    "flaghunter.adapters.runtime",
    "flaghunter.adapters.storage",
    "flaghunter.adapters.tools",
)

FORBIDDEN_INIT_IMPORT_PREFIXES = (
    "flaghunter.agents",
    "flaghunter.interface",
    "flaghunter.mcp",
    "flaghunter.runtime",
    "flaghunter.session",
    "flaghunter.tools",
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


def test_inner_layers_do_not_import_adapter_package() -> None:
    offenders: list[tuple[str, str]] = []

    for root in (DOMAIN_ROOT, PORTS_ROOT):
        for path in _python_sources(root):
            for imported in _imported_module_names(_parse(path)):
                normalized = imported.lstrip(".")
                if normalized.startswith("flaghunter.adapters"):
                    offenders.append((_relative(path), imported))

    assert offenders == []
